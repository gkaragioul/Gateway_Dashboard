import contextlib
import io
import os
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from pc_drive_dashboard import filesystem
from pc_drive_dashboard.filesystem import (
    FileOperationSafetyError,
    _reject_protected,
    delete_item,
    prepare_download,
)
from pc_drive_dashboard.settings import AppSettings

try:
    from fastapi.testclient import TestClient
except (ImportError, RuntimeError):  # TestClient needs httpx, which is not a runtime dependency.
    TestClient = None

from pc_drive_dashboard.app import create_app

ON_WINDOWS = os.name == "nt"
PASSWORD = "correct horse battery staple"


def _forbidden(*args, **kwargs):
    raise AssertionError("A destructive filesystem call was reached; the safety check did not stop it.")


def _make_junction(link: Path, target: Path) -> None:
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


class ProtectedPathRuleTests(unittest.TestCase):
    def test_protected_folder_its_contents_and_its_parents_are_refused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protected = root / "outer" / "dashboard"
            (protected / "config").mkdir(parents=True)
            (root / "sibling").mkdir()

            for target in (protected, protected / "config", root / "outer", root):
                with self.subTest(target=target):
                    with self.assertRaises(FileOperationSafetyError):
                        _reject_protected(target, [protected], "deleted")

            _reject_protected(root / "sibling", [protected], "deleted")


class FileOperationApiTests(unittest.TestCase):
    """Delete and paste: login, CSRF, the write switch and the explicit permanent-delete confirmation."""

    def setUp(self):
        if TestClient is None:
            self.skipTest("API tests need httpx: python -m pip install httpx")
        self._temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self._temp_dir.name)
        self.base = self.root / "outer" / "dashboard"
        self.work = self.root / "work"
        (self.work / "folder").mkdir(parents=True)
        (self.work / "note.txt").write_text("keep me", encoding="utf-8")
        (self.work / "folder" / "inner.txt").write_text("inner", encoding="utf-8")

    def tearDown(self):
        self._temp_dir.cleanup()

    def make_app(self, write_operations_enabled=True):
        settings = AppSettings(
            base_dir=self.base,
            config_path=self.base / "config" / "config.json",
            log_dir=self.base / "logs",
            data_dir=self.base / "data",
            write_operations_enabled=write_operations_enabled,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            return create_app(settings)

    def logged_in(self, app):
        client = TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 50000))
        response = client.post("/api/auth/setup", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        client.headers["X-CSRF-Token"] = client.cookies["pcdd_csrf"]
        return client

    def delete(self, client, path, **extra):
        return client.post("/api/delete", json={"path": str(path), "confirm_permanent": True, **extra})

    def paste(self, client, source, destination, operation):
        return client.post(
            "/api/paste",
            json={"source_path": str(source), "destination_path": str(destination), "operation": operation},
        )

    def assert_work_untouched(self):
        self.assertEqual((self.work / "note.txt").read_text(encoding="utf-8"), "keep me")
        self.assertTrue((self.work / "folder" / "inner.txt").exists())
        self.assertFalse((self.work / "folder" / "note.txt").exists())

    def test_delete_and_paste_require_login(self):
        app = self.make_app()
        self.logged_in(app)
        anonymous = TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 50001))

        self.assertEqual(self.delete(anonymous, self.work / "note.txt").status_code, 401)
        self.assertEqual(self.paste(anonymous, self.work / "note.txt", self.work / "folder", "cut").status_code, 401)
        self.assert_work_untouched()

    def test_delete_and_paste_require_csrf_token(self):
        app = self.make_app()
        client = self.logged_in(app)
        del client.headers["X-CSRF-Token"]

        self.assertEqual(self.delete(client, self.work / "note.txt").status_code, 403)
        self.assertEqual(self.paste(client, self.work / "note.txt", self.work / "folder", "cut").status_code, 403)
        self.assert_work_untouched()

    def test_write_switch_off_refuses_delete_copy_and_move(self):
        app = self.make_app(write_operations_enabled=False)
        client = self.logged_in(app)

        responses = [
            self.delete(client, self.work / "note.txt"),
            self.delete(client, self.work / "folder"),
            self.paste(client, self.work / "note.txt", self.work / "folder", "copy"),
            self.paste(client, self.work / "note.txt", self.work / "folder", "cut"),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 403)
            self.assertIn("PCDD_ENABLE_WRITES=0", response.json()["detail"])
        self.assert_work_untouched()
        results = {(event["event"], event["result"]) for event in app.state.audit_log.tail()}
        self.assertIn(("filesystem.delete", "disabled"), results)
        self.assertIn(("filesystem.paste", "disabled"), results)

    def test_delete_needs_explicit_permanent_confirmation(self):
        app = self.make_app()
        client = self.logged_in(app)

        response = client.post("/api/delete", json={"path": str(self.work / "note.txt")})

        self.assertEqual(response.status_code, 400)
        self.assertIn("permanent", response.json()["detail"])
        self.assert_work_untouched()

    @unittest.skipUnless(ON_WINDOWS, "Filesystem routes only run on Windows.")
    def test_delete_removes_file_and_folder(self):
        client = self.logged_in(self.make_app())

        self.assertEqual(self.delete(client, self.work / "note.txt").json()["kind"], "file")
        self.assertEqual(self.delete(client, self.work / "folder").json()["kind"], "folder")

        self.assertFalse((self.work / "note.txt").exists())
        self.assertFalse((self.work / "folder").exists())

    @unittest.skipUnless(ON_WINDOWS, "Filesystem routes only run on Windows.")
    def test_delete_refuses_drive_root(self):
        client = self.logged_in(self.make_app())
        drive_root = f"{self.root.drive}\\"

        with mock.patch("shutil.rmtree", _forbidden), mock.patch("os.rmdir", _forbidden), mock.patch(
            "os.unlink", _forbidden
        ), mock.patch("pathlib.Path.unlink", _forbidden):
            response = self.delete(client, drive_root)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Drive roots", response.json()["detail"])

    @unittest.skipUnless(ON_WINDOWS, "Filesystem routes only run on Windows.")
    def test_delete_and_move_refuse_the_dashboards_own_folders(self):
        client = self.logged_in(self.make_app())
        config_file = self.base / "config" / "config.json"

        for target in (config_file, self.base / "config", self.base, self.root / "outer"):
            with self.subTest(target=target):
                response = self.delete(client, target)
                self.assertEqual(response.status_code, 400)
                self.assertIn("dashboard's own folders", response.json()["detail"])
        response = self.paste(client, self.base / "config", self.work, "cut")
        self.assertEqual(response.status_code, 400)

        self.assertTrue(config_file.exists())
        self.assertTrue(client.get("/api/auth/state").json()["authenticated"])

    @unittest.skipUnless(ON_WINDOWS, "Filesystem routes only run on Windows.")
    def test_paste_copies_moves_and_never_overwrites(self):
        client = self.logged_in(self.make_app())

        self.assertEqual(self.paste(client, self.work / "note.txt", self.work / "folder", "copy").status_code, 200)
        self.assertEqual(self.paste(client, self.work / "note.txt", self.work / "folder", "copy").status_code, 409)
        self.assertEqual((self.work / "folder" / "note.txt").read_text(encoding="utf-8"), "keep me")

        (self.work / "folder" / "child").mkdir()
        into_itself = self.paste(client, self.work / "folder", self.work / "folder" / "child", "cut")
        self.assertEqual(into_itself.status_code, 400)
        self.assertTrue((self.work / "folder" / "inner.txt").exists())

        (self.work / "elsewhere").mkdir()
        self.assertEqual(self.paste(client, self.work / "folder", self.work / "elsewhere", "cut").status_code, 200)
        self.assertFalse((self.work / "folder").exists())
        self.assertTrue((self.work / "elsewhere" / "folder" / "inner.txt").exists())


@unittest.skipUnless(ON_WINDOWS, "Filesystem operations only run on Windows.")
class LinkAndDownloadSafetyTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self._temp_dir.name)
        self.outside = self.root / "outside"
        self.outside.mkdir()
        (self.outside / "keep.txt").write_text("must survive", encoding="utf-8")
        # Do not depend on the test machine's real free space (the download check keeps 1 GB free).
        plenty = mock.Mock(total=10**15, used=0, free=10**15)
        free_space = mock.patch.object(filesystem.shutil, "disk_usage", return_value=plenty)
        free_space.start()
        self.addCleanup(free_space.stop)

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_deleting_a_folder_does_not_follow_a_junction_inside_it(self):
        victim = self.root / "victim"
        victim.mkdir()
        (victim / "own.txt").write_text("x", encoding="utf-8")
        _make_junction(victim / "link", self.outside)

        delete_item(str(victim))

        self.assertFalse(victim.exists())
        self.assertEqual((self.outside / "keep.txt").read_text(encoding="utf-8"), "must survive")

    def test_deleting_a_junction_removes_only_the_link(self):
        link = self.root / "link"
        _make_junction(link, self.outside)

        result = delete_item(str(link))

        self.assertEqual(result["kind"], "link")
        self.assertFalse(os.path.lexists(link))
        self.assertEqual((self.outside / "keep.txt").read_text(encoding="utf-8"), "must survive")

    def test_whole_drive_download_is_refused_before_reading_anything(self):
        with mock.patch.object(filesystem, "_collect_download_files", _forbidden):
            with self.assertRaises(FileOperationSafetyError):
                prepare_download(f"{self.root.drive}\\", self.root / "downloads")

    def test_folder_zip_skips_its_own_archive_folder_and_links(self):
        source = self.root / "source"
        (source / "sub").mkdir(parents=True)
        (source / "a.txt").write_text("a", encoding="utf-8")
        (source / "sub" / "b.txt").write_text("b", encoding="utf-8")
        archive_dir = source / "dashboard-data" / "downloads"
        archive_dir.mkdir(parents=True)
        (archive_dir / "older-download.bin").write_bytes(b"not part of the folder")
        _make_junction(source / "link", self.outside)

        prepared = prepare_download(str(source), archive_dir)
        with zipfile.ZipFile(prepared.path) as archive:
            names = sorted(archive.namelist())

        self.assertEqual(names, ["a.txt", "sub/b.txt"])
        self.assertTrue(prepared.cleanup)
        self.assertEqual(prepared.path.parent, archive_dir)

    def test_folder_zip_is_refused_when_it_would_fill_the_disk(self):
        source = self.root / "source"
        source.mkdir()
        (source / "a.txt").write_text("a", encoding="utf-8")
        archive_dir = self.root / "downloads"
        tiny = mock.Mock(total=100, used=90, free=10)

        with mock.patch.object(filesystem.shutil, "disk_usage", return_value=tiny):
            with self.assertRaises(FileOperationSafetyError):
                prepare_download(str(source), archive_dir)

        self.assertEqual(list(archive_dir.glob("*.zip")), [])

    def test_leftover_download_zips_are_cleared_but_other_files_kept(self):
        source = self.root / "source"
        source.mkdir()
        (source / "a.txt").write_text("a", encoding="utf-8")
        archive_dir = self.root / "downloads"
        archive_dir.mkdir()
        stale = archive_dir / f"old-{'a' * 32}.zip"
        fresh = archive_dir / f"new-{'b' * 32}.zip"
        unrelated = archive_dir / "keep.zip"
        for path in (stale, fresh, unrelated):
            path.write_bytes(b"zip")
        old = time.time() - 7 * 60 * 60
        os.utime(stale, (old, old))
        os.utime(unrelated, (old, old))

        prepare_download(str(source), archive_dir)

        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
