import tempfile
import unittest
from pathlib import Path

from pc_drive_dashboard.app import create_app
from pc_drive_dashboard.settings import AppSettings


class RouteSurfaceTests(unittest.TestCase):
    def test_production_surface_exposes_only_visible_product_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                AppSettings(
                    base_dir=root,
                    config_path=root / "config" / "config.json",
                    log_dir=root / "logs",
                    data_dir=root / "data",
                )
            )

        paths = {route.path for route in app.routes}

        self.assertEqual(app.title, "Gateway Dashboard")
        self.assertIn("/favicon.ico", paths)

        for path in (
            "/api/system",
            "/api/storage/health",
            "/api/storage/diagnostics",
            "/api/settings/sessions",
            "/api/settings/sessions/revoke",
        ):
            self.assertNotIn(path, paths)

        for path in (
            "/api/auth/state",
            "/api/auth/setup",
            "/api/auth/login",
            "/api/auth/logout",
            "/api/drives",
            "/api/locations",
            "/api/tree",
            "/api/file",
            "/api/path/copy",
            "/api/open",
            "/api/upload",
            "/api/jobs",
        ):
            self.assertIn(path, paths)


if __name__ == "__main__":
    unittest.main()
