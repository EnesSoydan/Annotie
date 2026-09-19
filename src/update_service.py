"""GitHub Releases tabanlı otomatik güncelleme servisi."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from src.utils.constants import APP_VERSION


GITHUB_REPOSITORY = "EnesSoydan/Annotie"
RELEASES_API_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
)


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    release_url: str
    download_url: str
    asset_name: str
    sha256: Optional[str] = None


def _version_key(value: str) -> tuple[int, ...]:
    text = (value or "").strip().lstrip("vV")
    match = re.match(r"^(\d+(?:\.\d+)*)", text)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def _windows_asset(assets: list[dict]) -> Optional[dict]:
    zips = [
        asset for asset in assets
        if str(asset.get("name", "")).lower().endswith(".zip")
    ]
    windows = [
        asset for asset in zips
        if "windows" in str(asset.get("name", "")).lower()
    ]
    return (windows or zips or [None])[0]


def _extract_packaged_updater(package_path: Path) -> tuple[Path, Path]:
    """Paketlenmiş updater'ı güvenli bir geçici klasöre çıkarır.

    Dönüş değeri ``(updater_yolu, geçici_klasör)`` biçimindedir. Çağıran,
    yardımcı başlatılamazsa geçici klasörü temizlemelidir.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="annotie-updater-"))
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            candidates = []
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                relative = PurePosixPath(name)
                if (
                    member.is_dir()
                    or relative.is_absolute()
                    or ".." in relative.parts
                ):
                    continue
                if relative.name.lower() == "annotieupdater.exe":
                    candidates.append(member)

            if len(candidates) != 1:
                raise RuntimeError(
                    "Güncelleme paketinde AnnotieUpdater.exe bulunamadı."
                )

            updater = temp_dir / "AnnotieUpdater.exe"
            with archive.open(candidates[0], "r") as source, updater.open("wb") as output:
                shutil.copyfileobj(source, output)
        return updater, temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def check_latest_release() -> Optional[UpdateInfo]:
    """GitHub'daki son release daha yeniyse indirme bilgilerini döndürür."""
    request = urllib.request.Request(
        RELEASES_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Annotie-Updater",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        release = json.loads(response.read().decode("utf-8"))

    remote_version = str(release.get("tag_name") or release.get("name") or "")
    if _version_key(remote_version) <= _version_key(APP_VERSION):
        return None

    asset = _windows_asset(release.get("assets") or [])
    if not asset or not asset.get("browser_download_url"):
        return None

    digest = asset.get("digest")
    if isinstance(digest, str) and digest.lower().startswith("sha256:"):
        digest = digest.split(":", 1)[1].lower()
    else:
        digest = None

    return UpdateInfo(
        version=remote_version.lstrip("vV"),
        release_url=str(release.get("html_url") or ""),
        download_url=str(asset["browser_download_url"]),
        asset_name=str(asset.get("name") or "Annotie-Windows.zip"),
        sha256=digest,
    )


class UpdateCheckWorker(QThread):
    finished = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.finished.emit(check_latest_release())
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDownloadWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, info: UpdateInfo, parent=None):
        super().__init__(parent)
        self._info = info
        self._temp_path: Optional[Path] = None

    def run(self):
        fd, temp_name = tempfile.mkstemp(prefix="annotie-update-", suffix=".zip")
        os.close(fd)
        self._temp_path = Path(temp_name)
        try:
            request = urllib.request.Request(
                self._info.download_url,
                headers={"User-Agent": "Annotie-Updater"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                digest = hashlib.sha256()
                with self._temp_path.open("wb") as output:
                    while True:
                        if self.isInterruptionRequested():
                            raise RuntimeError("İndirme iptal edildi.")
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total)

            if self._info.sha256 and digest.hexdigest().lower() != self._info.sha256:
                raise RuntimeError("İndirilen paketin güvenlik doğrulaması başarısız.")
            self.finished.emit(str(self._temp_path))
        except Exception as exc:
            try:
                self._temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.failed.emit(str(exc))


class UpdateManager(QObject):
    """Başlangıçta sessiz, menüden çağrıldığında etkileşimli kontrol yöneticisi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._check_worker: Optional[UpdateCheckWorker] = None
        self._download_worker: Optional[UpdateDownloadWorker] = None
        self._progress: Optional[QProgressDialog] = None
        self._interactive = False

    @staticmethod
    def is_supported_runtime() -> bool:
        return sys.platform == "win32" and bool(getattr(sys, "frozen", False))

    def check_silently(self):
        if self._check_worker is not None or not self.is_supported_runtime():
            return
        self._interactive = False
        self._start_check()

    def check_interactive(self):
        if not self.is_supported_runtime():
            QMessageBox.information(
                self.parent(), "Güncellemeler",
                "Güncelleme kontrolü yalnızca paketlenmiş Windows sürümünde çalışır."
            )
            return
        if self._check_worker is not None:
            return
        self._interactive = True
        self._start_check()

    def _start_check(self):
        worker = UpdateCheckWorker(self)
        self._check_worker = worker
        worker.finished.connect(self._on_check_finished)
        worker.failed.connect(self._on_check_failed)
        worker.finished.connect(lambda _value: self._clear_check_worker(worker))
        worker.failed.connect(lambda _message: self._clear_check_worker(worker))
        worker.start()

    def _clear_check_worker(self, worker):
        if self._check_worker is worker:
            self._check_worker = None
            worker.deleteLater()

    def _on_check_finished(self, info):
        if info is None:
            if self._interactive:
                QMessageBox.information(
                    self.parent(), "Güncellemeler",
                    f"Annotie {APP_VERSION} sürümü güncel."
                )
            return

        answer = QMessageBox.question(
            self.parent(), "Güncelleme Mevcut",
            f"Annotie için {info.version} sürümü mevcut.\n\n"
            "Güncellemeyi şimdi indirip uygulamak ister misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_download(info)

    def _on_check_failed(self, message: str):
        if self._interactive:
            QMessageBox.warning(
                self.parent(), "Güncelleme Kontrolü",
                f"Güncellemeler kontrol edilemedi:\n{message}"
            )

    def _start_download(self, info: UpdateInfo):
        self._progress = QProgressDialog(
            "Güncelleme indiriliyor...", "İptal", 0, 100, self.parent()
        )
        self._progress.setWindowTitle("Annotie Güncelleniyor")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.show()

        worker = UpdateDownloadWorker(info, self)
        self._download_worker = worker
        worker.progress.connect(self._on_download_progress)
        worker.finished.connect(self._on_download_finished)
        worker.failed.connect(self._on_download_failed)
        worker.start()

    def _on_download_progress(self, downloaded: int, total: int):
        if not self._progress:
            return
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(downloaded)
            self._progress.setLabelText(
                f"Güncelleme indiriliyor... {downloaded / 1048576:.1f} / "
                f"{total / 1048576:.1f} MB"
            )
        else:
            self._progress.setRange(0, 0)
        if self._progress.wasCanceled() and self._download_worker:
            self._download_worker.requestInterruption()

    def _on_download_failed(self, message: str):
        if self._progress:
            self._progress.close()
        self._download_worker = None
        QMessageBox.warning(
            self.parent(), "Güncelleme Başarısız",
            f"Güncelleme indirilemedi:\n{message}"
        )

    def _on_download_finished(self, package_path: str):
        if self._progress:
            self._progress.close()
        self._download_worker = None
        self._launch_updater(Path(package_path))

    def _launch_updater(self, package_path: Path) -> bool:
        install_dir = Path(sys.executable).resolve().parent
        updater = install_dir / "AnnotieUpdater.exe"
        temporary_updater_dir: Optional[Path] = None
        if not updater.is_file():
            try:
                updater, temporary_updater_dir = _extract_packaged_updater(
                    package_path
                )
            except Exception as exc:
                QMessageBox.warning(
                    self.parent(), "Güncelleme Başarısız",
                    "Güncelleme yardımcısı bulunamadı. "
                    f"Yeni paketi elle kurmanız gerekiyor.\n\n{exc}"
                )
                return False

        try:
            subprocess.Popen(
                [
                    str(updater),
                    "--pid", str(os.getpid()),
                    "--install-dir", str(install_dir),
                    "--package", str(package_path),
                    "--restart", str(Path(sys.executable).resolve()),
                ],
                cwd=str(install_dir),
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                ),
                close_fds=True,
            )
        except Exception as exc:
            if temporary_updater_dir is not None:
                shutil.rmtree(temporary_updater_dir, ignore_errors=True)
            try:
                package_path.unlink(missing_ok=True)
            except OSError:
                pass
            QMessageBox.warning(
                self.parent(), "Güncelleme Başarısız",
                f"Güncelleme yardımcısı başlatılamadı:\n{exc}"
            )
            return False

        QMessageBox.information(
            self.parent(), "Güncelleme Hazır",
            "Güncelleme indirildi. Annotie kapanıp yeni sürümle yeniden açılacak."
        )
        QApplication.instance().quit()
        return True
