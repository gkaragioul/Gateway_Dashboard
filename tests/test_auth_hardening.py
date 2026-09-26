import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pc_drive_dashboard.login_limiter import LoginRateLimiter
from pc_drive_dashboard.settings import AppSettings
from pc_drive_dashboard.setup_code import (
    clear_setup_code,
    is_local_request,
    load_or_create_setup_code,
    setup_code_matches,
    setup_code_path,
)

try:
    from fastapi.testclient import TestClient
except (ImportError, RuntimeError):  # TestClient needs httpx, which is not a runtime dependency.
    TestClient = None

from pc_drive_dashboard.app import create_app

PASSWORD = "correct horse battery staple"
REMOTE = ("100.101.102.103", 50000)
OTHER_REMOTE = ("100.101.102.104", 50000)
LOOPBACK = ("127.0.0.1", 50000)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class SetupCodeTests(unittest.TestCase):
    def test_code_is_created_once_and_reused_until_cleared(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            code = load_or_create_setup_code(Path(temp_dir))

            self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")
            self.assertIn(code, setup_code_path(Path(temp_dir)).read_text(encoding="utf-8"))
            self.assertEqual(load_or_create_setup_code(Path(temp_dir)), code)

            clear_setup_code(Path(temp_dir))
            self.assertFalse(setup_code_path(Path(temp_dir)).exists())

    def test_code_comparison_ignores_case_and_separators_only(self):
        self.assertTrue(setup_code_matches("ABCD-EFGH-JKLM", "abcd efgh jklm"))
        self.assertTrue(setup_code_matches("ABCD-EFGH-JKLM", "ABCDEFGHJKLM"))
        self.assertFalse(setup_code_matches("ABCD-EFGH-JKLM", "ABCD-EFGH-JKLN"))
        self.assertFalse(setup_code_matches("ABCD-EFGH-JKLM", ""))
        self.assertFalse(setup_code_matches("ABCD-EFGH-JKLM", None))
        self.assertFalse(setup_code_matches("ABCD-EFGH-JKLM", "ÄBCD-EFGH-JKLM"))

    def test_local_means_loopback_peer_and_loopback_host_name(self):
        self.assertTrue(is_local_request("127.0.0.1", "127.0.0.1"))
        self.assertTrue(is_local_request("127.0.0.1", "localhost"))
        self.assertTrue(is_local_request("::1", "::1"))
        self.assertTrue(is_local_request("::ffff:127.0.0.1", "localhost"))

        # DNS rebinding pages and localhost tunnels/proxies arrive from loopback with a foreign host name.
        self.assertFalse(is_local_request("127.0.0.1", "evil.example"))
        self.assertFalse(is_local_request("127.0.0.1", "pc.tailnet.ts.net"))
        # Other devices, including other Tailscale devices, are never local.
        self.assertFalse(is_local_request("100.101.102.103", "100.101.102.103"))
        self.assertFalse(is_local_request("100.101.102.103", "localhost"))
        self.assertFalse(is_local_request(None, "localhost"))
        self.assertFalse(is_local_request("testclient", "localhost"))


class LoginRateLimiterTests(unittest.TestCase):
    def test_locks_out_after_five_failures_and_doubles_each_time(self):
        clock = FakeClock()
        limiter = LoginRateLimiter(clock=clock)

        for _ in range(4):
            self.assertEqual(limiter.record_failure("a"), 0)
        self.assertEqual(limiter.retry_after("a"), 0)

        self.assertEqual(limiter.record_failure("a"), 30)
        self.assertEqual(limiter.retry_after("a"), 30)
        clock.now += 29
        self.assertEqual(limiter.retry_after("a"), 1)
        clock.now += 1
        self.assertEqual(limiter.retry_after("a"), 0)

        for _ in range(4):
            limiter.record_failure("a")
        self.assertEqual(limiter.record_failure("a"), 60)

    def test_lockout_is_capped(self):
        clock = FakeClock()
        limiter = LoginRateLimiter(clock=clock)
        locked_for = 0
        for _ in range(40):
            for _ in range(5):
                locked_for = limiter.record_failure("a") or locked_for
            clock.now += locked_for
        self.assertEqual(locked_for, 15 * 60)

    def test_clients_are_independent_and_reset_clears(self):
        limiter = LoginRateLimiter(clock=FakeClock())
        for _ in range(5):
            limiter.record_failure("attacker")

        self.assertGreater(limiter.retry_after("attacker"), 0)
        self.assertEqual(limiter.retry_after("owner"), 0)

        limiter.reset("attacker")
        self.assertEqual(limiter.retry_after("attacker"), 0)

    def test_old_failures_are_forgotten(self):
        clock = FakeClock()
        limiter = LoginRateLimiter(clock=clock)
        for _ in range(4):
            limiter.record_failure("a")
        clock.now += 2 * 60 * 60
        self.assertEqual(limiter.record_failure("a"), 0)

    def test_table_is_bounded(self):
        limiter = LoginRateLimiter(max_clients=10, clock=FakeClock())
        for index in range(100):
            limiter.record_failure(f"client-{index}")
        self.assertLessEqual(len(limiter._records), 10)


class ServerLaunchTests(unittest.TestCase):
    @unittest.skipIf(importlib.util.find_spec("uvicorn") is None, "uvicorn is not installed")
    def test_forwarded_client_addresses_are_not_trusted(self):
        from pc_drive_dashboard import server

        with mock.patch("uvicorn.run") as run, mock.patch("sys.argv", ["pc_drive_dashboard", "--host", "127.0.0.1"]):
            server.main()

        self.assertIs(run.call_args.kwargs["proxy_headers"], False)


@unittest.skipIf(TestClient is None, "API tests need httpx: python -m pip install httpx")
class FirstRunAndLoginApiTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self._temp_dir.name)
        self.config_dir = self.root / "config"

    def tearDown(self):
        self._temp_dir.cleanup()

    def make_app(self, write_operations_enabled=True):
        settings = AppSettings(
            base_dir=self.root,
            config_path=self.config_dir / "config.json",
            log_dir=self.root / "logs",
            data_dir=self.root / "data",
            write_operations_enabled=write_operations_enabled,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            app = create_app(settings)
        self.startup_output = output.getvalue()
        return app

    def remote(self, app, client=REMOTE):
        return TestClient(app, base_url="http://100.64.0.10:8787", client=client)

    def local(self, app):
        return TestClient(app, base_url="http://127.0.0.1:8787", client=LOOPBACK)

    def setup_payload(self, **extra):
        return {"password": PASSWORD, "remember": False, "device_name": "Test", **extra}

    def test_setup_code_is_announced_and_saved_at_first_start(self):
        self.make_app()

        code = load_or_create_setup_code(self.config_dir)
        self.assertIn(code, self.startup_output)
        self.assertIn(str(setup_code_path(self.config_dir)), self.startup_output)

    def test_remote_visitor_cannot_claim_setup_without_code(self):
        app = self.make_app()
        client = self.remote(app)

        state = client.get("/api/auth/state").json()
        self.assertFalse(state["configured"])
        self.assertTrue(state["setup_requires_code"])

        for payload in (self.setup_payload(), self.setup_payload(setup_code="AAAA-BBBB-CCCC")):
            response = client.post("/api/auth/setup", json=payload)
            self.assertEqual(response.status_code, 403)
            self.assertIn("Finish setup on the PC", response.json()["detail"])

        self.assertFalse(app.state.security_store.is_configured())
        self.assertNotIn("pcdd_session", client.cookies)

    def test_remote_setup_with_code_works_once_and_removes_code(self):
        app = self.make_app()
        client = self.remote(app)
        code = load_or_create_setup_code(self.config_dir)

        response = client.post("/api/auth/setup", json=self.setup_payload(setup_code=code.lower()))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(app.state.security_store.is_configured())
        self.assertIn("pcdd_session", response.cookies)
        self.assertFalse(setup_code_path(self.config_dir).exists())
        self.assertTrue(client.get("/api/auth/state").json()["authenticated"])

        again = self.remote(app, client=OTHER_REMOTE).post(
            "/api/auth/setup", json=self.setup_payload(setup_code=code)
        )
        self.assertEqual(again.status_code, 409)

    def test_setup_from_the_pc_itself_needs_no_code(self):
        app = self.make_app()
        client = self.local(app)

        self.assertFalse(client.get("/api/auth/state").json()["setup_requires_code"])
        response = client.post("/api/auth/setup", json=self.setup_payload())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(app.state.security_store.is_configured())
        self.assertFalse(setup_code_path(self.config_dir).exists())

    def test_loopback_request_with_foreign_host_name_is_not_local(self):
        app = self.make_app()
        rebinding = TestClient(app, base_url="http://evil.example:8787", client=LOOPBACK)

        response = rebinding.post("/api/auth/setup", json=self.setup_payload())

        self.assertEqual(response.status_code, 403)
        self.assertFalse(app.state.security_store.is_configured())

    def test_setup_code_guessing_is_rate_limited(self):
        app = self.make_app()
        client = self.remote(app)
        code = load_or_create_setup_code(self.config_dir)

        for _ in range(5):
            self.assertEqual(
                client.post("/api/auth/setup", json=self.setup_payload(setup_code="AAAA-BBBB-CCCC")).status_code,
                403,
            )
        blocked = client.post("/api/auth/setup", json=self.setup_payload(setup_code=code))

        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(app.state.security_store.is_configured())

    def test_configured_app_removes_leftover_setup_code(self):
        app = self.make_app()
        self.local(app).post("/api/auth/setup", json=self.setup_payload())
        load_or_create_setup_code(self.config_dir)

        self.make_app()

        self.assertFalse(setup_code_path(self.config_dir).exists())
        self.assertEqual(self.startup_output, "")

    def test_failed_logins_lock_out_that_device_only(self):
        app = self.make_app()
        self.local(app).post("/api/auth/setup", json=self.setup_payload())
        clock = FakeClock()
        app.state.login_limiter.clock = clock
        attacker = self.remote(app)

        for attempt in range(1, 6):
            response = attacker.post("/api/auth/login", json={"password": f"wrong password {attempt}"})
            self.assertEqual(response.status_code, 401)
        self.assertIn("Try again in 30 seconds", response.json()["detail"])

        blocked = attacker.post("/api/auth/login", json={"password": PASSWORD})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers["Retry-After"], "30")
        self.assertNotIn("pcdd_session", blocked.cookies)

        owner = self.remote(app, client=OTHER_REMOTE)
        self.assertEqual(owner.post("/api/auth/login", json={"password": PASSWORD}).status_code, 200)

        clock.now += 30
        self.assertEqual(attacker.post("/api/auth/login", json={"password": PASSWORD}).status_code, 200)

        events = [(event["event"], event["result"]) for event in app.state.audit_log.tail()]
        self.assertIn(("auth.login", "locked_out"), events)

    def test_successful_login_resets_failure_count(self):
        app = self.make_app()
        self.local(app).post("/api/auth/setup", json=self.setup_payload())
        client = self.remote(app)

        for _ in range(4):
            client.post("/api/auth/login", json={"password": "wrong password!"})
        self.assertEqual(client.post("/api/auth/login", json={"password": PASSWORD}).status_code, 200)
        for _ in range(4):
            self.assertEqual(client.post("/api/auth/login", json={"password": "wrong password!"}).status_code, 401)
        self.assertEqual(client.post("/api/auth/login", json={"password": PASSWORD}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
