import tempfile
import time
import unittest
from pathlib import Path

from pc_drive_dashboard.security import SecurityStore


class SecurityStoreTests(unittest.TestCase):
    def test_password_hash_does_not_store_raw_password_and_verifies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SecurityStore(Path(temp_dir) / "config.json")

            store.set_password("correct horse battery staple")

            raw_config = store.config_path.read_text(encoding="utf-8")
            self.assertNotIn("correct horse battery staple", raw_config)
            self.assertTrue(store.verify_password("correct horse battery staple"))
            self.assertFalse(store.verify_password("wrong password"))

    def test_trusted_token_is_hashed_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            store = SecurityStore(config_path)
            token = store.create_trusted_token("MacBook Safari", ttl_seconds=60)

            raw_config = config_path.read_text(encoding="utf-8")
            self.assertNotIn(token, raw_config)
            self.assertTrue(SecurityStore(config_path).verify_trusted_token(token))

    def test_expired_trusted_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SecurityStore(Path(temp_dir) / "config.json")
            token = store.create_trusted_token("Expired", ttl_seconds=-1)

            self.assertFalse(store.verify_trusted_token(token, now=time.time()))


if __name__ == "__main__":
    unittest.main()
