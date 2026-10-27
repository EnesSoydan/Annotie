"""Buluttan gelen dosya adlarını yerel diske yazmadan önce doğrulama.

`images.filename` ekip üyelerinin yazabildiği bir alandır; doğrudan yerel yola
eklenirse `..\\..\\Startup\\x.bat` gibi bir kayıt dataset klasörünün dışına
dosya yazdırabilir. Burada tek bir güvenli yol bileşeni olarak doğrulanır.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

MAX_FILENAME_LENGTH = 255

# Windows'ta uzantıdan bağımsız olarak aygıta yönlenen ayrılmış adlar
_RESERVED_STEMS = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
}
_FORBIDDEN_CHARS = set('/\\:*?"<>|')


class UnsafeFilenameError(ValueError):
    """Dosya adı tek bir güvenli yol bileşeni değil."""


def safe_cloud_filename(name) -> str:
    """Adı doğrular ve aynen döndürür; güvensizse UnsafeFilenameError fırlatır."""
    if not isinstance(name, str) or not name:
        raise UnsafeFilenameError("Dosya adı boş veya geçersiz.")
    if len(name) > MAX_FILENAME_LENGTH:
        raise UnsafeFilenameError(f"Dosya adı çok uzun: {name[:40]}...")
    if name in (".", ".."):
        raise UnsafeFilenameError(f"Geçersiz dosya adı: {name!r}")
    if any(ch in _FORBIDDEN_CHARS or ord(ch) < 32 for ch in name):
        raise UnsafeFilenameError(f"Dosya adında izin verilmeyen karakter: {name!r}")
    if name[-1] in (" ", "."):
        # Windows sondaki boşluk/noktayı siler; başka bir dosyayla çakışabilir
        raise UnsafeFilenameError(f"Dosya adı boşluk veya noktayla bitemez: {name!r}")
    if name.split(".", 1)[0].upper() in _RESERVED_STEMS:
        raise UnsafeFilenameError(f"Ayrılmış dosya adı: {name!r}")
    return name


def is_safe_cloud_filename(name) -> bool:
    try:
        safe_cloud_filename(name)
        return True
    except UnsafeFilenameError:
        return False


def safe_child_path(base_dir, name) -> Path:
    """`base_dir` altında, doğrulanmış ada sahip doğrudan çocuk yolu döndürür."""
    base = Path(base_dir)
    child = base / safe_cloud_filename(name)
    if child.resolve().parent != base.resolve():
        raise UnsafeFilenameError(f"Dosya adı klasör dışına çıkıyor: {name!r}")
    return child


def split_safe_image_rows(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """DB görsel satırlarını (güvenli, reddedilen) olarak ayırır."""
    safe, rejected = [], []
    for row in rows:
        (safe if is_safe_cloud_filename(row.get("filename")) else rejected).append(row)
    return safe, rejected
