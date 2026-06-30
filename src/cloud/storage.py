"""Görsel depolama istemcisi — Faz 5.

İçerik-hash (sha256) adresli görselleri R2'ye yükler/indirir. R2 anahtarları
istemcide YOKTUR; `storage-presign` Edge Function'ı kısa ömürlü presigned URL
üretir, istemci doğrudan R2'ye PUT/GET yapar. İndirilenler yerelde hash ile
cache'lenir (lazy fetch; değişmeyen görsel tekrar indirilmez). Qt'den bağımsız.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Optional

import httpx

from src.cloud.cloud_config import CloudConfig
from src.cloud.supabase_client import get_client


CACHE_DIR = Path.home() / ".annotie" / "cache" / "blobs"


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
                 timeout: float = 120.0):
        self._client = client or get_client()
        self._cfg = config or CloudConfig.load()
        self._timeout = timeout
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

    def _presign(self, dataset_id: Optional[str], content_hash: str, op: str) -> dict:
        url = f"{self._cfg.url}/functions/v1/storage-presign"
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "apikey": self._cfg.anon_key,
            "Content-Type": "application/json",
        }
        payload = {"content_hash": content_hash, "op": op}
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

    def download_to_cache(self, content_hash: str) -> Path:
        existing = self.cached_path(content_hash)
        if existing:
            return existing
        pre = self._presign(None, content_hash, "get")
        try:
            resp = self._http.get(pre["url"])
        except httpx.HTTPError as exc:
            raise StorageError(f"İndirme isteği başarısız: {exc}")
        if resp.status_code != 200:
            raise StorageError(f"İndirme hatası ({resp.status_code}): {resp.text[:200]}")
        return self._write_cache(content_hash, resp.content)

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
        p.write_bytes(data)
        return p
