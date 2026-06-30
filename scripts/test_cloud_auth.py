"""Faz 1 dogrulama scripti — UI olmadan auth + RLS akisini test eder.

Calistirma (proje kokunden):
    python scripts/test_cloud_auth.py

On kosul:
  - cloud_config.json olusturulmus (bkz. docs/SUPABASE_KURULUM.md)
  - 0001_init.sql migrasyonu Supabase'de calistirilmis
  - Gelistirme icin Auth ayarlarinda "Confirm email" KAPALI olmali
    (acik ise kayit sonrasi oturum donmez; e-posta onayi gerekir).

Bu script gercek bir kullanici olusturur (Supabase Auth uzerinde kalir).
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

# Proje kokunu yola ekle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cloud.cloud_config import CloudConfig
from src.cloud.supabase_client import get_client, is_available, SupabaseUnavailable
from src.cloud.auth import AuthManager, AuthError
from src.cloud.token_store import TokenStore


def _ok(msg: str):
    print(f"  [OK]   {msg}")


def _fail(msg: str):
    print(f"  [FAIL] {msg}")


def main() -> int:
    print("== Annotie Faz 1 — Bulut/Auth testi ==\n")

    # 1) Paket + yapilandirma
    if not is_available():
        _fail("supabase paketi kurulu degil. 'pip install supabase'")
        return 1
    cfg = CloudConfig.load()
    if not cfg.is_configured():
        _fail("Yapilandirma yok. cloud_config.json olusturun "
              "(docs/SUPABASE_KURULUM.md).")
        return 1
    _ok(f"Yapilandirma yuklendi: {cfg.url}")

    try:
        get_client(cfg)
    except SupabaseUnavailable as exc:
        _fail(str(exc))
        return 1
    _ok("Supabase istemcisi olusturuldu")

    # Test kullanicilari icin ayri token deposu (gercek oturumu ezmemek icin)
    store = TokenStore(Path.home() / ".annotie" / "session.test.json")
    auth = AuthManager(token_store=store)

    suffix = uuid.uuid4().hex[:8]
    email = f"annotie_test_{suffix}@example.com"
    password = "Test1234!"
    username = f"tester_{suffix}"

    # 2) Kayit
    try:
        user = auth.sign_up(email, password, username=username)
    except AuthError as exc:
        _fail(f"Kayit hatasi: {exc}")
        return 1
    if user is None:
        _fail("Kayit oturum/ kullanici dondurmedi.")
        return 1
    _ok(f"Kayit olusturuldu: {email} (id={user.id})")

    if not auth.is_authenticated():
        print("\n  [UYARI] Kayit sonrasi oturum yok — 'Confirm email' acik olabilir.")
        print("          Auth > Providers > Email altinda kapatip tekrar deneyin.\n")
        return 2

    # 3) Profil otomatik olustu mu? (handle_new_user tetikleyicisi)
    time.sleep(1.0)
    auth._enrich_profile()
    if auth.user and auth.user.username:
        _ok(f"Profil otomatik olustu: username={auth.user.username}")
    else:
        _fail("Profil bulunamadi (handle_new_user tetikleyicisi calismadi?).")

    # 4) Cikis + oturum geri yukleme
    auth.sign_out()
    if auth.is_authenticated():
        _fail("Cikis sonrasi hala oturum acik.")
        return 1
    _ok("Cikis yapildi")

    auth2 = AuthManager(token_store=store)
    restored = auth2.restore_session()
    if restored is None:
        _ok("Cikis sonrasi token temizlendi (geri yukleme dogru sekilde basarisiz)")
    else:
        _fail("Cikis sonrasi oturum geri yuklendi — token temizlenmemis.")

    # 5) Tekrar giris
    try:
        auth2.sign_in(email, password)
    except AuthError as exc:
        _fail(f"Giris hatasi: {exc}")
        return 1
    _ok("Tekrar giris basarili")

    # 6) RLS: hicbir ekibe uye degil -> teams bos donmeli
    client = get_client()
    res = client.table("teams").select("*").execute()
    rows = getattr(res, "data", []) or []
    if len(rows) == 0:
        _ok("RLS dogru: uye olunmayan ekipler gorunmuyor (teams=[])")
    else:
        _fail(f"RLS suphesi: teams beklenmedik sekilde {len(rows)} satir dondu")

    auth2.sign_out()
    print("\n== Test tamamlandi ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
