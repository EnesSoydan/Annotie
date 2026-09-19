"""Annotie Windows güncelleme yardımcısı."""

from __future__ import annotations

import argparse
import ctypes
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def _message(title: str, text: str, error: bool = False):
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10 if error else 0x40)
    except Exception:
        pass


def _wait_for_process(pid: int):
    if pid <= 0:
        return
    kernel32 = ctypes.windll.kernel32
    process = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not process:
        return
    try:
        kernel32.WaitForSingleObject(process, 120000)
    finally:
        kernel32.CloseHandle(process)


def _safe_extract(archive: zipfile.ZipFile, destination: Path):
    root = destination.resolve()
    for member in archive.infolist():
        name = member.filename.replace("\\", "/")
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"Güvensiz paket yolu: {member.filename}")
        target = (destination / Path(*relative.parts)).resolve()
        if root != target and root not in target.parents:
            raise RuntimeError(f"Güvensiz paket yolu: {member.filename}")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, "r") as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def _find_package_root(extracted: Path) -> Path:
    direct = extracted / "Annotie.exe"
    if direct.is_file():
        return extracted
    nested = extracted / "Annotie" / "Annotie.exe"
    if nested.is_file():
        return nested.parent
    matches = list(extracted.glob("*/Annotie.exe"))
    if len(matches) == 1:
        return matches[0].parent
    raise RuntimeError("Pakette Annotie.exe bulunamadı.")


def _copy_update(
    source: Path,
    install_dir: Path,
    running_executable: Path | None = None,
):
    running_executable = (running_executable or Path(sys.executable)).resolve()
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        destination = install_dir / relative
        if relative.name.lower() == "cloud_config.json":
            continue
        # Kurulu updater çalışıyorsa Windows onun üzerine yazılmasına izin
        # vermez. Geçici klasörden çalışıyorsak yeni updater'ı kuruluma kopyala.
        if (
            relative.name.lower() == "annotieupdater.exe"
            and destination.resolve() == running_executable
        ):
            continue
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def _run(args) -> int:
    package = Path(args.package).resolve()
    install_dir = Path(args.install_dir).resolve()
    if not package.is_file():
        raise RuntimeError("Güncelleme paketi bulunamadı.")
    if not install_dir.is_dir():
        raise RuntimeError("Annotie kurulum klasörü bulunamadı.")

    _wait_for_process(args.pid)
    with tempfile.TemporaryDirectory(prefix="annotie-update-extract-") as temp:
        extracted = Path(temp)
        with zipfile.ZipFile(package, "r") as archive:
            _safe_extract(archive, extracted)
        package_root = _find_package_root(extracted)
        _copy_update(package_root, install_dir)

    try:
        package.unlink(missing_ok=True)
    except OSError:
        pass

    subprocess.Popen([args.restart], cwd=str(install_dir), close_fds=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--restart", required=True)
    args = parser.parse_args()
    try:
        return _run(args)
    except Exception as exc:
        _message("Annotie Güncelleme Hatası", str(exc), error=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
