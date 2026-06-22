import unittest

from pc_drive_dashboard.drives import parse_storage_diagnostics, storage_health


class StorageHealthTests(unittest.TestCase):
    def test_reports_ok_without_removed_active_work_drive(self):
        health = storage_health(
            [
                {"letter": "C", "available": True},
                {"letter": "D", "available": True},
                {"letter": "F", "available": True},
                {"letter": "G", "available": True},
                {"letter": "H", "available": True},
            ]
        )

        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["missing_critical"], [])
        self.assertNotIn("E", health["critical_letters"])

    def test_reports_degraded_when_project_library_is_missing(self):
        health = storage_health(
            [
                {"letter": "C", "available": True},
                {"letter": "D", "available": True},
                {"letter": "F", "available": True},
                {"letter": "G", "available": False, "warning": "Drive is not mounted."},
                {"letter": "H", "available": True},
            ]
        )

        self.assertEqual(health["status"], "degraded")
        self.assertEqual([item["letter"] for item in health["missing_critical"]], ["G"])
        self.assertIn("G:", health["message"])

    def test_parse_storage_diagnostics_ignores_removed_active_work_drive(self):
        raw = {
            "pnp_devices": [
                {"Status": "OK", "FriendlyName": "WD Blue SA510 2.5 1000GB"},
            ],
            "volumes": [
                {"DriveLetter": "C", "FileSystemLabel": "System", "HealthStatus": "Healthy"},
                {"DriveLetter": "G", "FileSystemLabel": "Project Library", "HealthStatus": "Healthy"},
                {"DriveLetter": "H", "FileSystemLabel": "Backup", "HealthStatus": "Healthy"},
            ],
        }

        diagnostics = parse_storage_diagnostics(raw)

        self.assertTrue(diagnostics["core_storage_present"])
        self.assertEqual(diagnostics["suspect_devices"], [])
        self.assertIn("Core storage is mounted", diagnostics["summary"])


if __name__ == "__main__":
    unittest.main()
