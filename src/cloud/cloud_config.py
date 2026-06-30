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
from pathlib import Path
from typing import Optional


APP_DIR = Path.home() / ".annotie"
_FILENAME = "cloud_config.json"


def _project_root() -> Path:
    # src/cloud/cloud_config.py -> proje koku
    return Path(__file__).resolve().parents[2]


def _candidate_files() -> list[Path]:
    return [
        _project_root() / _FILENAME,
        APP_DIR / _FILENAME,
    ]


class CloudConfig:
    """Supabase baglanti bilgilerini tutar."""

    def __init__(self, url: Optional[str] = None, anon_key: Optional[str] = None):
        self.url = url
        self.anon_key = anon_key

    @classmethod
    def load(cls) -> "CloudConfig":
        # 1) Ortam degiskenleri
        url = os.environ.get("SUPABASE_URL")
        anon_key = os.environ.get("SUPABASE_ANON_KEY")
        if url and anon_key:
            return cls(url.strip(), anon_key.strip())

        # 2) / 3) Dosyalar
        for path in _candidate_files():
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                url = (data.get("url") or "").strip()
                anon_key = (data.get("anon_key") or "").strip()
                if url and anon_key:
                    return cls(url, anon_key)

        return cls(None, None)

    def is_configured(self) -> bool:
        return bool(self.url and self.anon_key)
