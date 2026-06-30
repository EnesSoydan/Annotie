"""Ekip (team) servis katmani — Faz 3.

Supabase uzerinde ekip/uyelik/davet islemleri. Qt'den bagimsizdir.
Tum islemler giris yapmis kullanicinin oturumuyla calisir; yetki
kontrolu RLS politikalari (0001_init.sql) tarafindan zorlanir.
"""

from __future__ import annotations

from typing import Optional

from src.cloud.supabase_client import get_client


class TeamError(Exception):
    """Ekip islemi hatasi (kullaniciya gosterilebilir mesaj)."""


# Rol etiketleri (TR)
ROLE_LABELS = {
    "owner": "Sahip",
    "admin": "Yönetici",
    "annotator": "Etiketleyici",
    "viewer": "İzleyici",
}

# Davet ederken atanabilecek roller (owner atanamaz)
ASSIGNABLE_ROLES = ["annotator", "admin", "viewer"]


def role_label(role: Optional[str]) -> str:
    return ROLE_LABELS.get(role or "", role or "?")


class TeamService:
    def __init__(self, user_id: str, client=None):
        self._client = client or get_client()
        self._uid = user_id

    # ─── Ekipler ───────────────────────────────────────────────────────────
    def create_team(self, name: str) -> Optional[dict]:
        name = (name or "").strip()
        if not name:
            raise TeamError("Ekip adı boş olamaz.")
        try:
            res = (self._client.table("teams")
                   .insert({"name": name, "owner_id": self._uid})
                   .execute())
        except Exception as exc:
            raise TeamError(f"Ekip oluşturulamadı: {exc}")
        data = res.data or []
        return data[0] if data else None

    def list_my_teams(self) -> list[dict]:
        """Uyesi oldugum ekipler (rol ile)."""
        res = (self._client.table("memberships")
               .select("role, team:teams(id,name,owner_id,created_at)")
               .eq("user_id", self._uid)
               .execute())
        out = []
        for row in res.data or []:
            t = row.get("team") or {}
            if t:
                out.append({**t, "role": row.get("role")})
        out.sort(key=lambda d: d.get("created_at") or "")
        return out

    # ─── Uyeler ────────────────────────────────────────────────────────────
    def get_members(self, team_id: str) -> list[dict]:
        res = (self._client.table("memberships")
               .select("role, user:profiles(id,username,display_name)")
               .eq("team_id", team_id)
               .execute())
        out = []
        for row in res.data or []:
            u = row.get("user") or {}
            out.append({
                "role": row.get("role"),
                "id": u.get("id"),
                "username": u.get("username"),
                "display_name": u.get("display_name"),
            })
        return out

    # ─── Davetler ──────────────────────────────────────────────────────────
    def find_user(self, username: str) -> Optional[dict]:
        res = (self._client.table("profiles")
               .select("id,username,display_name")
               .eq("username", (username or "").strip())
               .limit(1)
               .execute())
        data = res.data or []
        return data[0] if data else None

    def invite(self, team_id: str, identifier: str, role: str = "annotator") -> dict:
        """Kullanici adi veya e-posta ile davet olusturur; davet kaydini doner."""
        identifier = (identifier or "").strip()
        if not identifier:
            raise TeamError("Kullanıcı adı veya e-posta gerekli.")
        if role not in ASSIGNABLE_ROLES:
            role = "annotator"

        payload = {"team_id": team_id, "role": role, "invited_by": self._uid}
        if "@" in identifier:
            payload["email"] = identifier
        else:
            user = self.find_user(identifier)
            if not user:
                raise TeamError(f"Kullanıcı bulunamadı: {identifier}")
            if user["id"] == self._uid:
                raise TeamError("Kendinizi davet edemezsiniz.")
            payload["invited_user_id"] = user["id"]

        try:
            res = self._client.table("invites").insert(payload).execute()
        except Exception as exc:
            raise TeamError(f"Davet oluşturulamadı (yetkiniz olmayabilir): {exc}")
        data = res.data or []
        if not data:
            raise TeamError("Davet oluşturulamadı (yetkiniz olmayabilir).")
        return data[0]

    def team_pending_invites(self, team_id: str) -> list[dict]:
        res = (self._client.table("invites")
               .select("id, email, invited_user_id, role, status, token, expires_at")
               .eq("team_id", team_id)
               .eq("status", "pending")
               .execute())
        return res.data or []

    def my_pending_invites(self) -> list[dict]:
        """Bana gonderilen bekleyen davetler (ekip adiyla, RPC uzerinden)."""
        res = self._client.rpc("my_pending_invites").execute()
        return res.data or []

    def accept_invite(self, token: str) -> str:
        token = (token or "").strip()
        if not token:
            raise TeamError("Davet kodu gerekli.")
        try:
            res = self._client.rpc("accept_invite", {"p_token": token}).execute()
        except Exception as exc:
            raise TeamError(self._friendly_accept(exc))
        return res.data  # team_id

    @staticmethod
    def _friendly_accept(exc: Exception) -> str:
        m = str(exc)
        low = m.lower()
        if "gecersiz" in low or "suresi" in low or "expired" in low or "invalid" in low:
            return "Geçersiz veya süresi dolmuş davet kodu."
        return f"Davet kabul edilemedi: {m}"
