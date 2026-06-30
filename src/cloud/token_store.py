"""Oturum token'larinin yerel saklanmasi.

~/.annotie/session.json icinde access + refresh token tutulur.
Not (guvenlik): token'lar bu asamada sade JSON olarak saklanir. Ileride
isletim sistemi keyring'i (keyring paketi) ile sifrelenmesi planlanmaktadir.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional


APP_DIR = Path.home() / ".annotie"
_SESSION_FILE = APP_DIR / "session.json"


class TokenStore:
    """access/refresh token'lari diskte saklar."""

    def __init__(self, path: Path = _SESSION_FILE):
        self._path = path

    def save(self, access_token: str, refresh_token: str) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        self._path.write_text(json.dumps(payload), encoding="utf-8")
        # Mumkunse dosyayi yalnizca sahibe okutulabilir yap (POSIX)
        try:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def load(self) -> Optional[dict]:
        if not self._path.is_file():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if data.get("access_token") and data.get("refresh_token"):
            return data
        return None

    def clear(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass
