"""Kimlik dogrulama: kayit / giris / cikis / oturum geri yukleme.

Supabase Auth uzerine ince bir sarmalayicidir. Qt'den bagimsizdir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.cloud.supabase_client import get_client
from src.cloud.token_store import TokenStore


class AuthError(Exception):
    """Kimlik dogrulama hatasi (kullaniciya gosterilebilir mesaj)."""


_NETWORK_HINTS = ("connect", "timeout", "timed out", "network", "name resolution",
                  "getaddrinfo", "unreachable", "retryable")


def is_network_error(exc: BaseException) -> bool:
    """Hata ag/baglanti kaynakli mi (token reddi degil)?"""
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (ConnectionError, TimeoutError, OSError)):
            return True
        name = type(current).__name__.lower()
        if any(hint in name for hint in _NETWORK_HINTS):
            return True
        if any(hint in str(current).lower() for hint in ("connection", "timed out",
                                                           "getaddrinfo", "name resolution")):
            return True
        current = current.__cause__ or current.__context__
    return False


@dataclass
class AuthUser:
    id: str
    email: Optional[str]
    username: Optional[str] = None
    display_name: Optional[str] = None


class AuthManager:
    """Supabase Auth oturumunu yonetir."""

    def __init__(self, client=None, token_store: Optional[TokenStore] = None):
        self._client = client or get_client()
        self._store = token_store or TokenStore()
        self._user: Optional[AuthUser] = None
        # Supabase refresh token'i her yenilemede degisir (rotation). Yenisi
        # diske yazilmazsa bir sonraki acilis iptal edilmis token'la denenir
        # ve kullanici sessizce cikis yapmis olur.
        try:
            self._client.auth.on_auth_state_change(self._on_auth_event)
        except Exception:
            pass

    def _on_auth_event(self, event, session) -> None:
        name = str(getattr(event, "value", event)).upper()
        if session is not None and ("TOKEN_REFRESHED" in name or "SIGNED_IN" in name):
            if self._user is not None:
                self._persist_session(session)

    # --- Durum ---
    @property
    def user(self) -> Optional[AuthUser]:
        return self._user

    def is_authenticated(self) -> bool:
        return self._user is not None

    # --- Islemler ---
    def sign_up(self, email: str, password: str,
                username: Optional[str] = None,
                display_name: Optional[str] = None) -> AuthUser:
        """Yeni kullanici kaydeder.

        E-posta dogrulamasi aciksa oturum donmeyebilir; bu durumda
        kullanici e-postasini onayladiktan sonra sign_in cagrilmalidir.
        """
        options = {"data": {}}
        if username:
            options["data"]["username"] = username
        if display_name:
            options["data"]["display_name"] = display_name
        try:
            resp = self._client.auth.sign_up(
                {"email": email, "password": password, "options": options}
            )
        except Exception as exc:  # supabase AuthApiError dahil
            raise AuthError(self._friendly(exc)) from exc

        if resp.session:
            self._persist_session(resp.session)
            self._user = self._build_user(resp.user)
            self._enrich_profile()
        else:
            # Oturum yok: e-posta onayi bekleniyor
            self._user = self._build_user(resp.user) if resp.user else None
        return self._user

    def sign_in(self, email: str, password: str) -> AuthUser:
        try:
            resp = self._client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except Exception as exc:
            raise AuthError(self._friendly(exc)) from exc

        if not resp.session:
            raise AuthError("Giris basarisiz: oturum olusturulamadi.")
        self._persist_session(resp.session)
        self._user = self._build_user(resp.user)
        self._enrich_profile()
        return self._user

    def restore_session(self) -> Optional[AuthUser]:
        """Diskteki token'lardan oturumu geri yukler (varsa)."""
        data = self._store.load()
        if not data:
            return None
        try:
            self._client.auth.set_session(
                data["access_token"], data["refresh_token"]
            )
            user_resp = self._client.auth.get_user()
        except Exception as exc:
            # Cevrimdisi acilis oturumu silmemeli; yalnizca sunucu token'i
            # reddederse (gecersiz/iptal) kayitli oturum temizlenir.
            if not is_network_error(exc):
                self._store.clear()
            return None

        user = getattr(user_resp, "user", None)
        if not user:
            self._store.clear()
            return None
        self._user = self._build_user(user)
        # set_session token'lari yenilemis olabilir; tekrar persist et
        session = self._client.auth.get_session()
        if session:
            self._persist_session(session)
        self._enrich_profile()
        return self._user

    def sign_out(self) -> None:
        try:
            self._client.auth.sign_out()
        except Exception:
            pass
        self._store.clear()
        self._user = None

    # --- Yardimcilar ---
    def _persist_session(self, session) -> None:
        self._store.save(session.access_token, session.refresh_token)

    @staticmethod
    def _build_user(user) -> AuthUser:
        meta = getattr(user, "user_metadata", None) or {}
        return AuthUser(
            id=user.id,
            email=getattr(user, "email", None),
            username=meta.get("username"),
            display_name=meta.get("display_name"),
        )

    def _enrich_profile(self) -> None:
        """profiles tablosundan username/display_name'i tamamlar."""
        if not self._user:
            return
        try:
            res = (
                self._client.table("profiles")
                .select("username, display_name")
                .eq("id", self._user.id)
                .single()
                .execute()
            )
        except Exception:
            return
        row = getattr(res, "data", None)
        if row:
            self._user.username = row.get("username") or self._user.username
            self._user.display_name = (
                row.get("display_name") or self._user.display_name
            )

    @staticmethod
    def _friendly(exc: Exception) -> str:
        msg = str(exc)
        low = msg.lower()
        if "invalid login" in low or "invalid credentials" in low:
            return "E-posta veya sifre hatali."
        if "already registered" in low or "already been registered" in low:
            return "Bu e-posta zaten kayitli."
        if "password" in low and "least" in low:
            return "Sifre cok kisa (en az 6 karakter)."
        return f"Kimlik dogrulama hatasi: {msg}"
