"""Supabase baglanti ayarlari (URL + anon key).

Yukleme onceligi:
  1. Ortam degiskenleri: SUPABASE_URL / SUPABASE_ANON_KEY
  2. Proje kokunde cloud_config.json
  3. Kullanici config dizininde cloud_config.json
     (~/.annotie/cloud_config.json)

anon key gizli degildir (RLS ile korunur); ancak proje-spesifik
oldugundan ornek dosya (cloud_config.example.json) disinda commit edilmez.
service_role key ASLA istemciye konmaz.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


APP_DIR = Path.home() / ".annotie"
_FILENAME = "cloud_config.json"


def _project_root() -> Path:
    # src/cloud/cloud_config.py -> proje koku
    return Path(__file__).resolve().parents[2]


def _runtime_roots() -> list[Path]:
    roots = [
        Path.cwd(),
        Path(sys.executable).resolve().parent,
    ]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.append(_project_root())
    return roots


def _candidate_files() -> list[Path]:
    seen = set()
    files = []
    for root in [*_runtime_roots(), APP_DIR]:
        path = root / _FILENAME
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            files.append(path)
    return files


class CloudConfig:
    """Supabase baglanti bilgilerini tutar."""

    def __init__(
        self,
        url: Optional[str] = None,
        anon_key: Optional[str] = None,
        collab_url: Optional[str] = None,
    ):
        self.url = url
        self.anon_key = anon_key
        self.collab_url = collab_url

    @classmethod
    def load(cls) -> "CloudConfig":
        # 1) Ortam degiskenleri
        url = os.environ.get("SUPABASE_URL")
        anon_key = os.environ.get("SUPABASE_ANON_KEY")
        collab_url = os.environ.get("COLLAB_URL")
        if url and anon_key:
            return cls(url.strip(), anon_key.strip(), (collab_url or "").strip() or None)

        # 2) / 3) Dosyalar
        for path in _candidate_files():
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                url = (data.get("url") or "").strip()
                anon_key = (data.get("anon_key") or "").strip()
                collab_url = (data.get("collab_url") or "").strip()
                if url and anon_key:
                    return cls(url, anon_key, collab_url or None)

        return cls(None, None, None)

    def is_configured(self) -> bool:
        return bool(self.url and self.anon_key)

    def get_collab_url(self) -> str:
        return self.collab_url or "ws://127.0.0.1:8765/ws"
