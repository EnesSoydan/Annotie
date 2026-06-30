"""Tekil Supabase istemcisi.

supabase-py paketini tembel (lazy) import eder; boylece bulut
yapilandirilmamissa veya paket kurulu degilse uygulama yine acilir.
"""

from __future__ import annotations

from typing import Optional

from src.cloud.cloud_config import CloudConfig


class SupabaseUnavailable(RuntimeError):
    """supabase paketi yok veya yapilandirma eksik."""


_client = None  # type: ignore[var-annotated]


def is_available() -> bool:
    """supabase paketi kurulu mu?"""
    try:
        import supabase  # noqa: F401
        return True
    except ImportError:
        return False


def get_client(config: Optional[CloudConfig] = None):
    """Tekil Supabase Client dondurur.

    Yapilandirma yoksa veya paket kurulu degilse SupabaseUnavailable firlatir.
    """
    global _client
    if _client is not None:
        return _client

    config = config or CloudConfig.load()
    if not config.is_configured():
        raise SupabaseUnavailable(
            "Supabase yapilandirilmamis. cloud_config.json olusturun veya "
            "SUPABASE_URL / SUPABASE_ANON_KEY ortam degiskenlerini ayarlayin."
        )

    try:
        from supabase import create_client
    except ImportError as exc:
        raise SupabaseUnavailable(
            "supabase paketi kurulu degil. 'pip install supabase' calistirin."
        ) from exc

    _client = create_client(config.url, config.anon_key)
    return _client


def reset_client() -> None:
    """Test/yeniden yapilandirma icin tekil istemciyi sifirlar."""
    global _client
    _client = None
