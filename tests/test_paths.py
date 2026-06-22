import unittest

from pc_drive_dashboard.filesystem import UploadNameError, preview_media_type, sanitize_upload_filename
from pc_drive_dashboard.path_utils import PathError, format_path_variants, normalize_windows_path


class PathUtilsTests(unittest.TestCase):
    def test_normalizes_drive_paths_without_touching_filesystem(self):
        self.assertEqual(normalize_windows_path("g:/Project Library//DevWork"), "G:\\Project Library\\DevWork")

    def test_rejects_relative_and_unc_paths_for_version_one(self):
        with self.assertRaises(PathError):
            normalize_windows_path("Project Library\\DevWork")

        with self.assertRaises(PathError):
            normalize_windows_path("\\\\server\\share\\folder")

    def test_formats_copy_variants(self):
        variants = format_path_variants("H:\\Backups\\MacBook\\Local_Dev")

        self.assertEqual(variants["windows"], "H:\\Backups\\MacBook\\Local_Dev")
        self.assertEqual(variants["ssh"], "H:/Backups/MacBook/Local_Dev")
        self.assertEqual(variants["posix"], "/h/Backups/MacBook/Local_Dev")
        self.assertEqual(variants["name"], "Local_Dev")

    def test_preview_media_type_supports_browser_formats_safely(self):
        self.assertEqual(preview_media_type("G:\\Photos\\image.jpg"), "image/jpeg")
        self.assertEqual(preview_media_type("G:\\Photos\\iphone.heic"), "image/heic")
        self.assertEqual(preview_media_type("G:\\Scans\\scan.tiff"), "image/tiff")
        self.assertEqual(preview_media_type("G:\\Movies\\clip.mp4"), "video/mp4")
        self.assertEqual(preview_media_type("G:\\Movies\\clip.avi"), "video/x-msvideo")
        self.assertEqual(preview_media_type("G:\\Docs\\file.pdf"), "application/pdf")
        self.assertEqual(preview_media_type("G:\\Docs\\notes.md"), "text/plain; charset=utf-8")
        self.assertEqual(preview_media_type("G:\\Web\\page.html"), "text/plain; charset=utf-8")
        self.assertEqual(preview_media_type("G:\\Vector\\icon.svg"), "text/plain; charset=utf-8")

    def test_upload_filename_validation_rejects_windows_unsafe_names(self):
        self.assertEqual(sanitize_upload_filename("photo library.zip"), "photo library.zip")

        for filename in ("", "..", "folder/file.txt", "folder\\file.txt", "CON", "bad:name.txt", "trailing."):
            with self.subTest(filename=filename):
                with self.assertRaises(UploadNameError):
                    sanitize_upload_filename(filename)


if __name__ == "__main__":
    unittest.main()
