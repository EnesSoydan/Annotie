"""Relay güvenlik kuralları: kimlik doğrulama modu, rol yetkisi, hız sınırı."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping, Optional

AUTH_SUPABASE = "supabase"
AUTH_OPEN = "open"
AUTH_MISCONFIGURED = "misconfigured"

_TRUTHY = {"1", "true", "yes", "on"}

# Veri değiştiren mesajlar: viewer bunları yayınlayamaz.
EDIT_TYPES = frozenset({
    "ann_create", "ann_delete", "ann_modify", "ann_class_change",
    "class_add", "class_rename", "class_delete",
})
EDIT_ROLES = frozenset({"owner", "admin", "annotator"})


@dataclass(frozen=True)
class RelaySettings:
    auth_mode: str
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    max_message_bytes: int = 2 * 1024 * 1024
    rate_per_sec: float = 50.0
    rate_burst: int = 200


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(env.get(name) or default)
    except ValueError:
        return default


def load_settings(env: Mapping[str, str]) -> RelaySettings:
    """Ortamdan ayarları okur. Kimlik bilgisi yoksa varsayılan KAPALI moddur;
    açık mod yalnızca RELAY_INSECURE_OPEN=1 ile, bilerek seçilir."""
    url = (env.get("SUPABASE_URL") or "").strip() or None
    key = (env.get("SUPABASE_ANON_KEY") or "").strip() or None
    if url and key:
        mode = AUTH_SUPABASE
    elif (env.get("RELAY_INSECURE_OPEN") or "").strip().lower() in _TRUTHY:
        mode = AUTH_OPEN
    else:
        mode = AUTH_MISCONFIGURED
    return RelaySettings(
        auth_mode=mode,
        supabase_url=url.rstrip("/") if url else None,
        supabase_anon_key=key,
        max_message_bytes=_env_int(env, "RELAY_MAX_MESSAGE_BYTES", 2 * 1024 * 1024),
        rate_per_sec=float(_env_int(env, "RELAY_RATE_PER_SEC", 50)),
        rate_burst=_env_int(env, "RELAY_RATE_BURST", 200),
    )


def can_send(role: Optional[str], msg_type: str) -> bool:
    """Bu roldeki bağlantı bu mesaj tipini yayınlayabilir mi?"""
    if msg_type not in EDIT_TYPES:
        return True
    return role in EDIT_ROLES


class TokenBucket:
    """Bağlantı başına basit hız sınırı (saniyede `rate`, en fazla `burst`)."""

    def __init__(self, rate: float, burst: int, clock=time.monotonic):
        self._rate = float(rate)
        self._burst = float(burst)
        self._tokens = float(burst)
        self._clock = clock
        self._last = clock()

    def allow(self) -> bool:
        now = self._clock()
        self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
