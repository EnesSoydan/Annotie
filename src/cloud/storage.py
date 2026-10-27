"""Görsel depolama istemcisi — Faz 5.

İçerik-hash (sha256) adresli görselleri R2'ye yükler/indirir. R2 anahtarları
istemcide YOKTUR; `storage-presign` Edge Function'ı kısa ömürlü presigned URL
üretir, istemci doğrudan R2'ye PUT/GET yapar. İndirilenler yerelde hash ile
cache'lenir (lazy fetch; değişmeyen görsel tekrar indirilmez). Qt'den bağımsız.
"""

from __future__ import annotations

import hashlib
import io
import threading
from pathlib import Path
from typing import Optional

import httpx

from src.cloud.cloud_config import CloudConfig
from src.cloud.supabase_client import get_client


CACHE_DIR = Path.home() / ".annotie" / "cache" / "blobs"
MODEL_CACHE_DIR = Path.home() / ".annotie" / "models"
MAX_MODEL_BYTES = 500 * 1024 * 1024


class StorageError(Exception):
    """Depolama islemi hatasi (kullaniciya gosterilebilir mesaj)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class StorageClient:
    def __init__(self, client=None, config: Optional[CloudConfig] = None,
                 timeout: float = 120.0, dataset_id: Optional[str] = None):
        self._client = client or get_client()
        self._cfg = config or CloudConfig.load()
        self._timeout = timeout
        # Görsel GET yetkisi dataset üyeliğiyle verilir; indirmelerde varsayılan
        self._dataset_id = dataset_id
        # Paylaşımlı bağlantı havuzu (keep-alive) — her istekte yeni TLS
        # bağlantısı açmayı önler; Windows'ta soket/port tükenmesini ve
        # zamanla yavaşlamayı engeller. httpx.Client eşzamanlı kullanım için güvenli.
        self._http = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=32),
        )

    def close(self):
        try:
            self._http.close()
        except Exception:
            pass

    # ─── Presign ───────────────────────────────────────────────────────────
    def _access_token(self) -> str:
        sess = self._client.auth.get_session()
        if not sess:
            raise StorageError("Oturum yok (giriş gerekli).")
        return sess.access_token

    def _presign(self, dataset_id: Optional[str], content_hash: str, op: str,
                 kind: str = "image") -> dict:
        url = f"{self._cfg.url}/functions/v1/storage-presign"
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "apikey": self._cfg.anon_key,
            "Content-Type": "application/json",
        }
        payload = {"content_hash": content_hash, "op": op}
        if kind != "image":
            payload["kind"] = kind
        if dataset_id:
            payload["dataset_id"] = dataset_id
        try:
            r = self._http.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise StorageError(f"Presign isteği başarısız: {exc}")
        if r.status_code != 200:
            raise StorageError(f"Presign hatası ({r.status_code}): {r.text[:200]}")
        return r.json()

    # ─── Yükleme ───────────────────────────────────────────────────────────
    def upload_file(self, dataset_id: str, file_path) -> dict:
        """Dosyayı R2'ye yükler; {content_hash, key, size_bytes, width, height} döner."""
        file_path = Path(file_path)
        data = file_path.read_bytes()
        return self.upload_bytes(dataset_id, data)

    def upload_bytes(self, dataset_id: str, data: bytes) -> dict:
        content_hash = sha256_bytes(data)
        pre = self._presign(dataset_id, content_hash, "put")
        try:
            resp = self._http.put(pre["url"], content=data)
        except httpx.HTTPError as exc:
            raise StorageError(f"Yükleme isteği başarısız: {exc}")
        if resp.status_code not in (200, 201):
            raise StorageError(f"Yükleme hatası ({resp.status_code}): {resp.text[:200]}")

        self._write_cache(content_hash, data)  # zaten elimizde; cache'e koy
        width, height = self._dimensions(data)
        return {
            "content_hash": content_hash,
            "key": pre["key"],
            "size_bytes": len(data),
            "width": width,
            "height": height,
        }

    # ─── İndirme + cache ───────────────────────────────────────────────────
    def cached_path(self, content_hash: str) -> Optional[Path]:
        p = CACHE_DIR / content_hash
        return p if p.is_file() else None

    def download_to_cache(self, content_hash: str,
                          dataset_id: Optional[str] = None) -> Path:
        existing = self.cached_path(content_hash)
        if existing:
            return existing
        dataset_id = dataset_id or self._dataset_id
        if not dataset_id:
            raise StorageError("Görsel indirmek için dataset kimliği gerekli.")
        pre = self._presign(dataset_id, content_hash, "get")
        try:
            resp = self._http.get(pre["url"])
        except httpx.HTTPError as exc:
            raise StorageError(f"İndirme isteği başarısız: {exc}")
        if resp.status_code != 200:
            raise StorageError(f"İndirme hatası ({resp.status_code}): {resp.text[:200]}")
        # İçerik-adresli depo: bayt hash'i tutmuyorsa nesne bozulmuş ya da
        # üzerine yazılmıştır; cache'e almadan reddet.
        if sha256_bytes(resp.content) != content_hash:
            raise StorageError("İndirilen görsel bozuk (hash uyuşmuyor).")
        return self._write_cache(content_hash, resp.content)

    # ─── Kullanıcı modelleri ───────────────────────────────────────────────
    def upload_model_file(self, file_path, content_hash: Optional[str] = None) -> dict:
        """Model dosyasını kullanıcının R2 önekine yükler (dosyadan akışla)."""
        file_path = Path(file_path)
        size = file_path.stat().st_size
        if size > MAX_MODEL_BYTES:
            raise StorageError(
                f"Model dosyası çok büyük ({size // (1 << 20)} MB). "
                f"Sınır: {MAX_MODEL_BYTES // (1 << 20)} MB."
            )
        content_hash = content_hash or sha256_file(file_path)
        pre = self._presign(None, content_hash, "put", kind="model")
        try:
            with open(file_path, "rb") as f:
                resp = self._http.put(
                    pre["url"], content=f,
                    headers={"Content-Length": str(size)},
                    timeout=max(self._timeout, 600.0),
                )
        except httpx.HTTPError as exc:
            raise StorageError(f"Model yükleme isteği başarısız: {exc}")
        if resp.status_code not in (200, 201):
            raise StorageError(f"Model yükleme hatası ({resp.status_code}): {resp.text[:200]}")
        return {"content_hash": content_hash, "key": pre["key"], "size_bytes": size}

    def download_model(self, content_hash: str, suffix: str) -> Path:
        """Modeli yerel model cache'ine indirir (varsa tekrar indirmez)."""
        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        target = MODEL_CACHE_DIR / f"{content_hash}{suffix}"
        if target.is_file():
            return target
        pre = self._presign(None, content_hash, "get", kind="model")
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with self._http.stream("GET", pre["url"], timeout=max(self._timeout, 600.0)) as resp:
                if resp.status_code != 200:
                    raise StorageError(f"Model indirme hatası ({resp.status_code})")
                h = hashlib.sha256()
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(1 << 20):
                        h.update(chunk)
                        f.write(chunk)
        except httpx.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            raise StorageError(f"Model indirme isteği başarısız: {exc}")
        except StorageError:
            tmp.unlink(missing_ok=True)
            raise
        if h.hexdigest() != content_hash:
            tmp.unlink(missing_ok=True)
            raise StorageError("İndirilen model bozuk (hash uyuşmuyor).")
        tmp.replace(target)
        return target

    # ─── Yardımcılar ───────────────────────────────────────────────────────
    @staticmethod
    def _dimensions(data: bytes):
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                return im.size  # (width, height)
        except Exception:
            return None, None

    @staticmethod
    def _write_cache(content_hash: str, data: bytes) -> Path:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p = CACHE_DIR / content_hash
        # Yarım yazılmış dosya cache'te kalıcı bozuk blob olarak kalmasın
        tmp = p.with_name(f"{content_hash}.{threading.get_ident()}.part")
        try:
            tmp.write_bytes(data)
            try:
                tmp.replace(p)
            except OSError:
                # Aynı blob'u eşzamanlı indiren başka bir iş parçacığı önce yazdı
                # (Windows açık hedefin üzerine yazmaya izin vermez).
                if not p.is_file():
                    raise
        finally:
            tmp.unlink(missing_ok=True)
        return p
