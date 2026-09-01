"""Görsel metadata servisi — Faz 5.

`images` tablosunda görsel kayıtları (ad, içerik-hash, depo anahtarı, boyut,
split). Gerçek baytlar R2'de (bkz. storage.py). Qt'den bağımsız.
"""

from __future__ import annotations

from typing import Optional

from src.cloud.supabase_client import get_client


class ImageError(Exception):
    """Görsel metadata işlemi hatası."""


class ImageService:
    def __init__(self, user_id: str, client=None):
        self._client = client or get_client()
        self._uid = user_id

    def add_image(self, dataset_id: str, filename: str, content_hash: str,
                  storage_key: str, width: Optional[int] = None,
                  height: Optional[int] = None, split: Optional[str] = None,
                  size_bytes: Optional[int] = None,
                  label_content: Optional[str] = None) -> Optional[dict]:
        """Görsel kaydı ekler/günceller (dataset_id+filename benzersiz → upsert)."""
        payload = {
            "dataset_id": dataset_id,
            "filename": filename,
            "content_hash": content_hash,
            "storage_key": storage_key,
            "created_by": self._uid,
        }
        if width is not None:
            payload["width"] = width
        if height is not None:
            payload["height"] = height
        if split is not None:
            payload["split"] = split
        if size_bytes is not None:
            payload["size_bytes"] = size_bytes
        if label_content is not None:
            payload["label_content"] = label_content
        try:
            res = (self._client.table("images")
                   .upsert(payload, on_conflict="dataset_id,filename")
                   .execute())
        except Exception as exc:
            raise ImageError(f"Görsel kaydı eklenemedi: {exc}")
        data = res.data or []
        return data[0] if data else None

    def add_images_bulk(self, dataset_id: str, entries: list[dict],
                        split: Optional[str] = None, chunk: int = 100) -> list[dict]:
        """Birden çok görseli toplu ekler/günceller (hızlı).

        entries: [{filename, content_hash, key|storage_key, width, height, size_bytes}, ...]
        """
        rows = []
        for e in entries:
            row = {
                "dataset_id": dataset_id,
                "filename": e["filename"],
                "content_hash": e["content_hash"],
                "storage_key": e.get("storage_key") or e.get("key"),
                "created_by": self._uid,
            }
            if e.get("width") is not None:
                row["width"] = e["width"]
            if e.get("height") is not None:
                row["height"] = e["height"]
            if e.get("size_bytes") is not None:
                row["size_bytes"] = e["size_bytes"]
            row_split = e.get("split") or split
            if row_split:
                row["split"] = row_split
            # label_content her satırda bulunmalı: toplu upsert'te bazı satırlarda
            # olup bazılarında olmazsa PostgREST eksik olanlara NULL koyar ve
            # NOT NULL kısıtını ihlal eder. Yoksa boş string yaz.
            row["label_content"] = e.get("label_content") or ""
            rows.append(row)

        out = []
        for i in range(0, len(rows), chunk):
            try:
                res = (self._client.table("images")
                       .upsert(rows[i:i + chunk], on_conflict="dataset_id,filename")
                       .execute())
            except Exception as exc:
                raise ImageError(f"Görsel kayıtları eklenemedi: {exc}")
            out.extend(res.data or [])
        return out

    def list_images(self, dataset_id: str, page_size: int = 1000) -> list[dict]:
        """Tüm görselleri döner (PostgREST 1000 satır limitini sayfalama ile aşar)."""
        out: list[dict] = []
        start = 0
        while True:
            res = (self._client.table("images")
                   .select("*")
                   .eq("dataset_id", dataset_id)
                   .order("filename")
                   .range(start, start + page_size - 1)
                   .execute())
            rows = res.data or []
            out.extend(rows)
            if len(rows) < page_size:
                break
            start += page_size
        return out

    def get_by_filename(self, dataset_id: str, filename: str) -> Optional[dict]:
        res = (self._client.table("images")
               .select("*")
               .eq("dataset_id", dataset_id)
               .eq("filename", filename)
               .limit(1)
               .execute())
        d = res.data or []
        return d[0] if d else None

    def count(self, dataset_id: str) -> int:
        res = (self._client.table("images")
               .select("id", count="exact")
               .eq("dataset_id", dataset_id)
               .execute())
        return res.count or 0

    def update_label(self, image_id: str, content: str):
        """Görselin YOLO etiket içeriğini (write-through) kaydeder."""
        from datetime import datetime, timezone
        try:
            (self._client.table("images")
             .update({
                 "label_content": content or "",
                 "label_updated_by": self._uid,
                 "label_updated_at": datetime.now(timezone.utc).isoformat(),
             })
             .eq("id", image_id)
             .execute())
        except Exception as exc:
            raise ImageError(f"Etiket kaydedilemedi: {exc}")

    def delete_image(self, image_id: str):
        try:
            self._client.table("images").delete().eq("id", image_id).execute()
        except Exception as exc:
            raise ImageError(f"Görsel silinemedi: {exc}")
