"""Kullaniciya (profile) ozgu model kaydi — otomatik etiketleme.

Model dosyasi R2'de `models/<owner_id>/<sha256>` anahtarinda, metadata
`user_models` tablosunda (RLS: yalnizca sahibi) tutulur. Indirilen modeller
`~/.annotie/models/<sha256>.<ext>` altinda cache'lenir. Qt'den bagimsizdir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.cloud.supabase_client import get_client
from src.cloud.storage import StorageClient, sha256_file
from src.inference import ModelMeta, model_format


class ModelError(Exception):
    """Model islemi hatasi (kullaniciya gosterilebilir mesaj)."""


def format_size(size_bytes: Optional[int]) -> str:
    if not size_bytes:
        return "—"
    mb = size_bytes / (1 << 20)
    return f"{mb:.1f} MB" if mb >= 1 else f"{size_bytes // 1024} KB"


class ModelService:
    def __init__(self, user_id: str, client=None, storage: Optional[StorageClient] = None):
        self._client = client or get_client()
        self._uid = user_id
        self._storage = storage

    def storage(self) -> StorageClient:
        if self._storage is None:
            self._storage = StorageClient(self._client)
        return self._storage

    def close(self):
        if self._storage is not None:
            self._storage.close()

    # ─── Okuma ─────────────────────────────────────────────────────────────
    def list_models(self) -> list[dict]:
        try:
            res = (self._client.table("user_models")
                   .select("*")
                   .eq("owner_id", self._uid)
                   .order("created_at", desc=True)
                   .execute())
        except Exception as exc:
            raise ModelError(f"Modeller alınamadı: {exc}")
        return res.data or []

    # ─── Yazma ─────────────────────────────────────────────────────────────
    def register_model(self, name: str, description: str, file_path,
                       meta: ModelMeta) -> dict:
        """Dosyayi yukler, sonra metadata satirini ekler.

        Yukleme bitmeden satir yazilmaz; iptal/hata durumunda R2'de kalan
        yetim blob zararsizdir (gorsel yuklemesindeki kalip).
        """
        name = (name or "").strip()
        if not name:
            raise ModelError("Model adı boş olamaz.")
        file_path = Path(file_path)
        fmt = model_format(file_path)
        if any(m.get("name") == name for m in self.list_models()):
            raise ModelError(f"'{name}' adında bir modeliniz zaten var.")

        content_hash = sha256_file(file_path)
        try:
            up = self.storage().upload_model_file(file_path, content_hash)
        except Exception as exc:
            raise ModelError(str(exc))

        # Yerel cache'e de koy — ayni cihazda tekrar indirmeye gerek kalmasin.
        try:
            import shutil
            from src.cloud.storage import MODEL_CACHE_DIR
            MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            target = MODEL_CACHE_DIR / f"{content_hash}{file_path.suffix.lower()}"
            if not target.exists():
                shutil.copyfile(file_path, target)
        except OSError:
            pass

        payload = {
            "owner_id": self._uid,
            "name": name,
            "description": (description or "").strip() or None,
            "format": fmt,
            "task_type": meta.task_type.value,
            "class_names": list(meta.class_names),
            "imgsz": meta.imgsz,
            "kpt_shape": list(meta.kpt_shape) if meta.kpt_shape else None,
            "content_hash": content_hash,
            "size_bytes": up["size_bytes"],
        }
        try:
            res = self._client.table("user_models").insert(payload).execute()
        except Exception as exc:
            raise ModelError(f"Model kaydedilemedi: {exc}")
        data = res.data or []
        if not data:
            raise ModelError("Model kaydedilemedi.")
        return data[0]

    def update_model(self, model_id: str, name: str, description: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ModelError("Model adı boş olamaz.")
        try:
            res = (self._client.table("user_models")
                   .update({"name": name, "description": (description or "").strip() or None})
                   .eq("id", model_id)
                   .execute())
        except Exception as exc:
            raise ModelError(f"Model güncellenemedi (aynı ad kullanılıyor olabilir): {exc}")
        data = res.data or []
        if not data:
            raise ModelError("Model güncellenemedi.")
        return data[0]

    def delete_model(self, model_id: str):
        try:
            self._client.table("user_models").delete().eq("id", model_id).execute()
        except Exception as exc:
            raise ModelError(f"Model silinemedi: {exc}")

    # ─── Yerel kopya ───────────────────────────────────────────────────────
    def ensure_local(self, model: dict) -> Path:
        suffix = ".onnx" if model.get("format") == "onnx" else ".pt"
        try:
            return self.storage().download_model(model["content_hash"], suffix)
        except Exception as exc:
            raise ModelError(f"Model indirilemedi: {exc}")
