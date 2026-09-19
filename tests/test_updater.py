"""Windows güncelleme paketi ve kopyalama davranışı testleri."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from src.update_service import _extract_packaged_updater
from updater import _copy_update


class PackagedUpdaterTests(unittest.TestCase):
    def test_extracts_updater_from_release_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "release.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("Annotie/Annotie.exe", b"app")
                archive.writestr("Annotie/AnnotieUpdater.exe", b"updater")

            updater, updater_dir = _extract_packaged_updater(package)
            try:
                self.assertEqual(updater.read_bytes(), b"updater")
            finally:
                updater.unlink(missing_ok=True)
                updater_dir.rmdir()

    def test_rejects_package_without_updater(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "release.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("Annotie/Annotie.exe", b"app")

            with self.assertRaisesRegex(RuntimeError, "AnnotieUpdater.exe"):
                _extract_packaged_updater(package)


class CopyUpdateTests(unittest.TestCase):
    def test_temp_updater_installs_packaged_updater_and_preserves_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            install = root / "install"
            source.mkdir()
            install.mkdir()
            (source / "Annotie.exe").write_bytes(b"new-app")
            (source / "AnnotieUpdater.exe").write_bytes(b"new-updater")
            (source / "cloud_config.json").write_text("new", encoding="utf-8")
            (install / "cloud_config.json").write_text("current", encoding="utf-8")

            _copy_update(source, install, root / "temp" / "AnnotieUpdater.exe")

            self.assertEqual((install / "Annotie.exe").read_bytes(), b"new-app")
            self.assertEqual(
                (install / "AnnotieUpdater.exe").read_bytes(), b"new-updater"
            )
            self.assertEqual(
                (install / "cloud_config.json").read_text(encoding="utf-8"),
                "current",
            )

    def test_running_installed_updater_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            install = root / "install"
            source.mkdir()
            install.mkdir()
            (source / "AnnotieUpdater.exe").write_bytes(b"new")
            installed_updater = install / "AnnotieUpdater.exe"
            installed_updater.write_bytes(b"running")

            _copy_update(source, install, installed_updater)

            self.assertEqual(installed_updater.read_bytes(), b"running")


if __name__ == "__main__":
    unittest.main()
