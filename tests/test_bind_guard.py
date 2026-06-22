import unittest

from pc_drive_dashboard.bind_guard import BindAddressError, validate_bind_host


class BindGuardTests(unittest.TestCase):
    def test_accepts_loopback_and_tailscale_addresses(self):
        self.assertEqual(validate_bind_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(validate_bind_host("localhost"), "localhost")
        self.assertEqual(validate_bind_host("100.64.0.1"), "100.64.0.1")

    def test_rejects_public_or_lan_bind_without_override(self):
        with self.assertRaises(BindAddressError):
            validate_bind_host("0.0.0.0")

        with self.assertRaises(BindAddressError):
            validate_bind_host("192.168.2.3")

    def test_override_allows_explicit_public_bind(self):
        self.assertEqual(validate_bind_host("0.0.0.0", allow_public=True), "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
