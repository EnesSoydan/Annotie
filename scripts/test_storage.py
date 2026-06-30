"""Faz 5 doğrulama — R2 görsel yükleme/indirme + metadata akışı.

Çalıştırma (proje kökünden):
    py -3.12 scripts/test_storage.py

Ön koşul:
  - cloud_config.json hazır, giriş çalışıyor (Faz 1-2)
  - R2 + storage-presign Edge Function kuruldu (docs/R2_KURULUM.md)

Akış: kullanıcı oluştur → ekip → dataset → küçük PNG üret → R2'ye yükle →
images kaydı → cache temizle → R2'den indir → bayt doğrulaması.
"""

from __future__ import annotations

import io
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cloud.cloud_config import CloudConfig
from src.cloud.supabase_client import is_available
from src.cloud.auth import AuthManager
from src.cloud.token_store import TokenStore
from src.cloud.teams import TeamService
from src.cloud.datasets import DatasetService
from src.cloud.images import ImageService
from src.cloud.storage import StorageClient, sha256_bytes


def _ok(m): print(f"  [OK]   {m}")
def _fail(m): print(f"  [FAIL] {m}")


def _make_png() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (64, 48), (123, 200, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> int:
    print("== Annotie Faz 5 — Depolama testi ==\n")
    if not is_available():
        _fail("supabase paketi yok"); return 1
    cfg = CloudConfig.load()
    if not cfg.is_configured():
        _fail("cloud_config.json yok"); return 1

    sfx = uuid.uuid4().hex[:8]
    auth = AuthManager(token_store=TokenStore(Path.home() / ".annotie" / "session.storage.json"))
    user = auth.sign_up(f"store_{sfx}@example.com", "Test1234!", username=f"store_{sfx}")
    if not auth.is_authenticated():
        _fail("Kayıt sonrası oturum yok (Confirm email açık olabilir)"); return 2
    _ok(f"Kullanıcı: {user.username}")

    tsvc = TeamService(user.id)
    dsvc = DatasetService(user.id)
    isvc = ImageService(user.id)
    storage = StorageClient()

    tsvc.create_team("Store Ekip " + sfx[:4])
    team_id = tsvc.list_my_teams()[0]["id"]
    ds = dsvc.create_dataset(team_id, "Görsel Test", "bbox")
    _ok(f"Dataset: {ds['name']}")

    data = _make_png()
    expected_hash = sha256_bytes(data)

    # Yükleme
    try:
        meta = storage.upload_bytes(ds["id"], data)
    except Exception as exc:
        _fail(f"Yükleme hatası: {exc}")
        print("\n  → R2/Edge Function kurulumunu kontrol edin (docs/R2_KURULUM.md).")
        return 1
    if meta["content_hash"] != expected_hash:
        _fail("Hash uyuşmuyor"); return 1
    _ok(f"R2'ye yüklendi: hash={meta['content_hash'][:12]}… "
        f"boyut={meta['width']}x{meta['height']} {meta['size_bytes']}B")

    # Metadata kaydı
    row = isvc.add_image(ds["id"], "test.png", meta["content_hash"], meta["key"],
                         width=meta["width"], height=meta["height"],
                         split="train", size_bytes=meta["size_bytes"])
    if not row:
        _fail("images kaydı oluşmadı"); return 1
    _ok("images kaydı eklendi")

    imgs = isvc.list_images(ds["id"])
    if len(imgs) != 1:
        _fail(f"Beklenen 1 görsel, bulunan {len(imgs)}"); return 1
    _ok(f"list_images: {len(imgs)} kayıt")

    # Cache temizle ve R2'den indir
    cached = storage.cached_path(expected_hash)
    if cached:
        cached.unlink()
    path = storage.download_to_cache(expected_hash)
    downloaded = path.read_bytes()
    if sha256_bytes(downloaded) != expected_hash:
        _fail("İndirilen bayt hash'i uyuşmuyor"); return 1
    _ok(f"R2'den indirildi ve cache'lendi: {path.name[:16]}…")

    # İkinci indirme cache'ten gelmeli (lazy)
    path2 = storage.download_to_cache(expected_hash)
    if path2 == path:
        _ok("İkinci erişim yerel cache'ten geldi (lazy fetch çalışıyor)")

    print("\n== Test tamamlandı: FAZ5_STORAGE_OK ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
