"""Buluttan gelen dosya adlarının path traversal'a karşı doğrulanması."""

import tempfile
import unittest
from pathlib import Path

from src.cloud.safe_paths import (
    UnsafeFilenameError, is_safe_cloud_filename, safe_child_path,
    safe_cloud_filename, split_safe_image_rows,
)


class SafeCloudFilenameTests(unittest.TestCase):
    def test_accepts_normal_image_names(self):
        for name in ("img_001.jpg", "Görsel 1.png", "a.b.c.webp", "x" * 255):
            self.assertEqual(safe_cloud_filename(name), name)

    def test_rejects_traversal_and_separators(self):
        for name in (
            "..", ".", "../evil.bat", "..\\..\\Startup\\x.bat", "sub/img.jpg",
            "C:\\Windows\\x.dll", "C:evil.jpg", "/etc/passwd", "img.jpg:stream",
        ):
            with self.subTest(name=name):
                self.assertFalse(is_safe_cloud_filename(name))

    def test_rejects_control_and_reserved_names(self):
        for name in ("", "a\x00b.jpg", "a\nb.jpg", "CON", "nul.txt", "com1.jpg",
                     "trailing.", "trailing ", "x" * 256, None, 42):
            with self.subTest(name=name):
                with self.assertRaises(UnsafeFilenameError):
                    safe_cloud_filename(name)

    def test_safe_child_path_stays_inside_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertEqual(safe_child_path(base, "a.jpg"), base / "a.jpg")
            with self.assertRaises(UnsafeFilenameError):
                safe_child_path(base, "..\\outside.txt")

    def test_split_safe_image_rows(self):
        rows = [{"filename": "ok.jpg"}, {"filename": "../x.bat"}, {"filename": None}]
        safe, rejected = split_safe_image_rows(rows)
        self.assertEqual([r["filename"] for r in safe], ["ok.jpg"])
        self.assertEqual(len(rejected), 2)


if __name__ == "__main__":
    unittest.main()
