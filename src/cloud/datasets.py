"""Dataset (veri seti) servis katmani — Faz 4.

Ekibe bagli dataset metadata'sinin (ad, gorev tipi, siniflar) Supabase'de
yonetimi. Qt'den bagimsizdir. Gercek gorsel baytlari Faz 5'te (nesne deposu).
Gorev tipleri uygulamanin AnnotationType enum'i ile birebir ayni
(bbox/polygon/obb/keypoints/classify).
"""

from __future__ import annotations

from typing import Optional

from src.cloud.supabase_client import get_client


class DatasetError(Exception):
    """Dataset islemi hatasi (kullaniciya gosterilebilir mesaj)."""


# (etiket, deger) — deger AnnotationType.value ile ayni olmali
TASK_TYPES = [
    ("Nesne Algılama (BBox)", "bbox"),
    ("Segmentasyon (Polygon)", "polygon"),
    ("Yönlü Kutu (OBB)", "obb"),
    ("Keypoint (Pose)", "keypoints"),
    ("Sınıflandırma", "classify"),
]
_TASK_LABELS = {v: k for k, v in TASK_TYPES}


def task_label(value: Optional[str]) -> str:
    return _TASK_LABELS.get(value or "", value or "—")


class DatasetService:
    def __init__(self, user_id: str, client=None):
        self._client = client or get_client()
        self._uid = user_id

    # ─── Datasetler ────────────────────────────────────────────────────────
    def create_dataset(self, team_id: str, name: str, task_type: str,
                        kpt_shape: Optional[list[int]] = None,
                        classes: Optional[list] = None) -> dict:
        name = (name or "").strip()
        if not name:
            raise DatasetError("Dataset adı boş olamaz.")
        if not task_type:
            raise DatasetError("Görev tipi seçilmeli.")

        payload = {
            "team_id": team_id,
            "name": name,
            "task_type": task_type,
            "created_by": self._uid,
        }
        if kpt_shape:
            payload["kpt_shape"] = list(kpt_shape)

        try:
            res = self._client.table("datasets").insert(payload).execute()
        except Exception as exc:
            raise DatasetError(f"Dataset oluşturulamadı (yetkiniz olmayabilir): {exc}")
        data = res.data or []
        if not data:
            raise DatasetError("Dataset oluşturulamadı (yetkiniz olmayabilir).")
        ds = data[0]

        if classes:
            self.replace_classes(ds["id"], classes)
        return ds

    def list_team_datasets(self, team_id: str) -> list[dict]:
        res = (self._client.table("datasets")
               .select("*")
               .eq("team_id", team_id)
               .order("created_at")
               .execute())
        return res.data or []

    def get_dataset(self, dataset_id: str) -> Optional[dict]:
        res = (self._client.table("datasets")
               .select("*")
               .eq("id", dataset_id)
               .single()
               .execute())
        return res.data

    def delete_dataset(self, dataset_id: str):
        try:
            self._client.table("datasets").delete().eq("id", dataset_id).execute()
        except Exception as exc:
            raise DatasetError(f"Dataset silinemedi (yetkiniz olmayabilir): {exc}")

    # ─── Siniflar ──────────────────────────────────────────────────────────
    def list_classes(self, dataset_id: str) -> list[dict]:
        res = (self._client.table("dataset_classes")
               .select("*")
               .eq("dataset_id", dataset_id)
               .order("class_index")
               .execute())
        return res.data or []

    def replace_classes(self, dataset_id: str, classes: list):
        """Datasetin siniflarini tamamen yeniden yazar.

        classes: ["isim", ...] veya [("isim", "#renk"), ...]
        """
        try:
            self._client.table("dataset_classes").delete().eq("dataset_id", dataset_id).execute()
            rows = []
            for i, c in enumerate(classes):
                if isinstance(c, (tuple, list)):
                    name = (c[0] or "").strip()
                    color = c[1] if len(c) > 1 else None
                else:
                    name = (c or "").strip()
                    color = None
                if not name:
                    continue
                rows.append({
                    "dataset_id": dataset_id,
                    "class_index": len(rows),
                    "name": name,
                    "color": color,
                })
            if rows:
                self._client.table("dataset_classes").insert(rows).execute()
        except Exception as exc:
            raise DatasetError(f"Sınıflar kaydedilemedi: {exc}")
