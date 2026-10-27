"""Nesne bazli bulut annotation servisi ve donusum yardimcilari."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from src.cloud.supabase_client import get_client
from src.models.annotation import (
    Annotation,
    AnnotationType,
    BBoxAnnotation,
    ClassificationAnnotation,
    KeypointsAnnotation,
    OBBAnnotation,
    PolygonAnnotation,
    parse_annotation_line,
)


class AnnotationError(Exception):
    """Annotation bulut islemi hatasi."""


class AnnotationConflict(AnnotationError):
    """Object version eslesmediginde olusan conflict."""

    def __init__(self, current: Optional[dict]):
        super().__init__("Annotation baska bir kullanici tarafindan degistirildi.")
        self.current = current


def annotation_to_cloud_payload(annotation: Annotation) -> dict:
    data: dict
    if annotation.ann_type == AnnotationType.BBOX:
        data = {
            "x_center": annotation.x_center,
            "y_center": annotation.y_center,
            "width": annotation.width,
            "height": annotation.height,
        }
    elif annotation.ann_type == AnnotationType.POLYGON:
        data = {"points": [[x, y] for x, y in annotation.points]}
    elif annotation.ann_type == AnnotationType.OBB:
        data = {"corners": [[x, y] for x, y in annotation.corners]}
    elif annotation.ann_type == AnnotationType.KEYPOINTS:
        data = {
            "x_center": annotation.x_center,
            "y_center": annotation.y_center,
            "width": annotation.width,
            "height": annotation.height,
            "keypoints": [[x, y, int(v)] for x, y, v in annotation.keypoints],
        }
    else:
        data = {}

    return {
        "uid": annotation.uid,
        "class_index": int(annotation.class_id),
        "type": annotation.ann_type.value,
        "data": data,
    }


def cloud_record_to_annotation(record: dict) -> Annotation:
    ann_type = record.get("type")
    class_id = int(record.get("class_index", 0))
    data = record.get("data") or {}

    if ann_type == "bbox":
        annotation = BBoxAnnotation(
            class_id=class_id,
            x_center=float(data["x_center"]),
            y_center=float(data["y_center"]),
            width=float(data["width"]),
            height=float(data["height"]),
        )
    elif ann_type == "polygon":
        annotation = PolygonAnnotation(
            class_id=class_id,
            points=[(float(p[0]), float(p[1])) for p in data["points"]],
        )
    elif ann_type == "obb":
        annotation = OBBAnnotation(
            class_id=class_id,
            corners=[(float(p[0]), float(p[1])) for p in data["corners"]],
        )
    elif ann_type == "keypoints":
        annotation = KeypointsAnnotation(
            class_id=class_id,
            x_center=float(data["x_center"]),
            y_center=float(data["y_center"]),
            width=float(data["width"]),
            height=float(data["height"]),
            keypoints=[
                (float(p[0]), float(p[1]), int(p[2]))
                for p in data["keypoints"]
            ],
        )
    elif ann_type == "classify":
        annotation = ClassificationAnnotation(class_id=class_id)
    else:
        raise AnnotationError(f"Bilinmeyen annotation tipi: {ann_type}")

    annotation.uid = str(record["uid"])
    annotation.version = max(0, int(record.get("version", 0)))
    return annotation


def materialize_cloud_annotations(
    dataset_root: Path,
    label_path: Path,
    records: Iterable[dict],
) -> bool:
    """DB satirlarini YOLO snapshot + version'li .annotie metadata olarak yazar."""
    from src.io.annotation_identity import identity_metadata_path
    from src.io.label_writer import write_label_file

    annotations = [cloud_record_to_annotation(record) for record in records]
    metadata_path = identity_metadata_path(dataset_root, label_path)
    return write_label_file(label_path, annotations, metadata_path)


def parse_legacy_label_content(
    content: str,
    task_type: Optional[str] = None,
    kpt_shape: Optional[Iterable[int]] = None,
) -> list[dict]:
    """Eski YOLO snapshot'ini kayipsiz migration payload'ina cevirir."""
    parsed_type = None
    if task_type:
        task_type = {
            "detect": "bbox",
            "segment": "polygon",
            "pose": "keypoints",
        }.get(task_type, task_type)
        try:
            parsed_type = AnnotationType(task_type)
        except ValueError as exc:
            raise AnnotationError(f"Bilinmeyen dataset gorev tipi: {task_type}") from exc

    parsed_kpt = tuple(kpt_shape) if kpt_shape else None
    payloads = []
    for line_number, raw_line in enumerate((content or "").splitlines(), start=1):
        line = raw_line.strip().lstrip("\ufeff").replace(",", ".")
        if not line:
            continue
        try:
            annotation = parse_annotation_line(line, parsed_type, parsed_kpt)
        except (ValueError, IndexError, TypeError) as exc:
            raise AnnotationError(
                f"Gecersiz legacy etiket satiri ({line_number}): {exc}"
            ) from exc
        if annotation is None:
            raise AnnotationError(f"Gecersiz legacy etiket satiri: {line_number}")
        payloads.append(annotation_to_cloud_payload(annotation))
    return payloads


def _record_payload(row: dict) -> dict:
    return {
        "uid": str(row["uid"]),
        "class_index": row["class_index"],
        "type": row["type"],
        "data": row.get("data") or {},
    }


def _is_tombstone(current: Optional[dict]) -> bool:
    return bool(current and current.get("is_deleted"))


@dataclass
class SyncResult:
    records: list[dict]
    # Tombstone cakismasi nedeniyle yeni uid ile olusturulanlar: eski -> yeni
    renamed: dict[str, str] = field(default_factory=dict)
    rebased: bool = False


class AnnotationService:
    # Gecici ag hatalarinda RPC yeniden denemesi (saniye)
    RETRY_DELAYS = (0.5, 1.5)

    def __init__(self, user_id: str, client=None):
        self._client = client or get_client()
        self._uid = user_id
        self._sleep = time.sleep

    @staticmethod
    def group_by_image(records: Iterable[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for record in records:
            grouped.setdefault(str(record["image_id"]), []).append(record)
        return grouped

    def list_for_images(self, image_ids: Iterable[str], chunk: int = 100,
                        page_size: int = 1000) -> list[dict]:
        """Gorsellerin silinmemis satirlari. PostgREST yanitlari max_rows (varsayilan
        1000) ile kesildiginden her parti sayfa sayfa okunur."""
        ids = [str(image_id) for image_id in image_ids]
        records: list[dict] = []
        try:
            for start in range(0, len(ids), chunk):
                batch = ids[start:start + chunk]
                if not batch:
                    continue
                offset = 0
                while True:
                    result = (
                        self._client.table("annotations")
                        .select("*")
                        .in_("image_id", batch)
                        .eq("is_deleted", False)
                        .order("image_id")
                        .order("created_at")
                        .order("id")
                        .range(offset, offset + page_size - 1)
                        .execute()
                    )
                    rows = result.data or []
                    records.extend(rows)
                    if len(rows) < page_size:
                        break
                    offset += page_size
        except Exception as exc:
            raise AnnotationError(f"Annotation satirlari alinamadi: {exc}") from exc
        return records

    def ensure_dataset_v2(self, dataset: dict, images: list[dict]) -> dict[str, list[dict]]:
        """Legacy label_content verisini bir kez tasir ve v2 kaynagini dondurur."""
        dataset_id = str(dataset["id"])
        needs_finalize = int(dataset.get("collab_schema_version") or 1) < 2
        try:
            for image in images:
                if image.get("annotations_migrated_at"):
                    continue
                needs_finalize = True
                payloads = parse_legacy_label_content(
                    image.get("label_content") or "",
                    task_type=dataset.get("task_type"),
                    kpt_shape=dataset.get("kpt_shape"),
                )
                self._migrate_image_payloads(dataset_id, str(image["id"]), payloads)

            if needs_finalize:
                self._client.rpc("finalize_dataset_collab_v2", {
                    "p_dataset_id": dataset_id,
                }).execute()
        except AnnotationError:
            raise
        except Exception as exc:
            raise AnnotationError(f"Dataset collaboration v2 tasinamadi: {exc}") from exc

        records = self.list_for_images(image["id"] for image in images)
        return self.group_by_image(records)

    def migrate_image(
        self,
        dataset_id: str,
        image_id: str,
        annotations: Iterable[Annotation],
    ) -> list[dict]:
        payloads = [annotation_to_cloud_payload(ann) for ann in annotations]
        self._migrate_image_payloads(dataset_id, image_id, payloads)
        return self.list_for_images([image_id])

    def _migrate_image_payloads(
        self,
        dataset_id: str,
        image_id: str,
        payloads: list[dict],
    ) -> None:
        try:
            self._client.rpc("migrate_image_annotations_v2", {
                "p_dataset_id": dataset_id,
                "p_image_id": image_id,
                "p_annotations": payloads,
            }).execute()
        except Exception as exc:
            raise AnnotationError(f"Gorsel annotation'lari tasinamadi: {exc}") from exc

    def sync_image(
        self,
        dataset_id: str,
        image_id: str,
        annotations: Iterable[Annotation],
        known_records: Iterable[dict],
    ) -> list[dict]:
        """Yerel goruntuyu nesne islemlerine ayirip version kontrollu kaydeder."""
        return self.sync_image_detailed(
            dataset_id, image_id, annotations, known_records).records

    def sync_image_detailed(
        self,
        dataset_id: str,
        image_id: str,
        annotations: Iterable[Annotation],
        known_records: Iterable[dict],
        *,
        refresh_first: bool = False,
        max_rebases: int = 2,
    ) -> "SyncResult":
        """Yerel degisiklikleri, baskalarinin degisikliklerini ezmeden kaydeder.

        known_records son bilinen DB durumudur (taban). Yalnizca yerelde tabana
        gore degisen nesneler gonderilir. Bir islem version conflict verirse
        gorselin guncel satirlari yeniden cekilir ve plan onlara gore tekrar
        kurulur (uc yonlu birlestirme: taban / yerel / uzak); boylece eski bir
        tabanla calisan istemci (ör. relay'den duzenleme almis bir alici) kalici
        conflict'e dusmez. refresh_first ilk denemeden once tazeler.
        """
        annotations = list(annotations)
        base = {str(row["uid"]): dict(row) for row in known_records}
        remote = self._fetch_image_rows(image_id) if refresh_first else dict(base)
        renamed: dict[str, str] = {}
        rebased = refresh_first
        attempts = 0
        while True:
            try:
                records = self._push_changes(
                    dataset_id, image_id, annotations, base, remote, renamed)
                break
            except AnnotationConflict:
                attempts += 1
                if attempts > max_rebases:
                    raise
                remote = self._fetch_image_rows(image_id)
                rebased = True
        if rebased:
            # Yeniden temellenince baskalarinin satirlari da yeni taban olur
            records = list(self._fetch_image_rows(image_id).values())
        records.sort(key=lambda row: (row.get("created_at") or "", str(row["uid"])))
        return SyncResult(records=records, renamed=renamed, rebased=rebased)

    def _fetch_image_rows(self, image_id: str) -> dict[str, dict]:
        return {str(row["uid"]): dict(row) for row in self.list_for_images([image_id])}

    def _push_changes(
        self,
        dataset_id: str,
        image_id: str,
        annotations: list,
        base: dict[str, dict],
        remote: dict[str, dict],
        renamed: dict[str, str],
    ) -> list[dict]:
        state = {uid: dict(row) for uid, row in remote.items()}
        local = {renamed.get(ann.uid, ann.uid): ann for ann in annotations}

        # Yerelde silinenler (tabanda var, yerelde yok); uzakta zaten yoksa atla
        for uid in sorted(set(base) - set(local)):
            remote_row = state.get(uid)
            if remote_row is None:
                continue
            self._apply_operation(
                dataset_id, image_id, uid, "delete", int(remote_row["version"]), None,
            )
            state.pop(uid, None)

        for uid, annotation in local.items():
            payload = annotation_to_cloud_payload(annotation)
            payload["uid"] = uid
            base_row = base.get(uid)
            remote_row = state.get(uid)
            if base_row is not None and payload == _record_payload(base_row):
                # Yerelde degismedi: uzaktaki (belki baskasinin) durumu gecerli
                if remote_row is not None:
                    annotation.version = int(remote_row["version"])
                continue

            if remote_row is not None:
                remote_payload = _record_payload(remote_row)
                if payload == remote_payload:
                    annotation.version = int(remote_row["version"])
                    continue
                only_class_changed = (
                    payload["type"] == remote_payload["type"]
                    and payload["data"] == remote_payload["data"]
                    and payload["class_index"] != remote_payload["class_index"]
                )
                operation = "class_change" if only_class_changed else "modify"
                row = self._apply_operation(
                    dataset_id, image_id, uid, operation,
                    int(remote_row["version"]), payload,
                )
            else:
                try:
                    row = self._apply_operation(
                        dataset_id, image_id, uid, "create", 0, payload)
                except AnnotationConflict as exc:
                    if not _is_tombstone(exc.current):
                        raise
                    # Silinmis (tombstone) uid yeniden olusturulamaz: ör. silme
                    # geri alindi. Ayni nesneyi yeni bir uid ile olustur.
                    new_uid = str(uuid.uuid4())
                    renamed[annotation.uid] = new_uid
                    uid = new_uid
                    payload["uid"] = new_uid
                    row = self._apply_operation(
                        dataset_id, image_id, uid, "create", 0, payload)

            row["image_id"] = image_id
            state[uid] = row
            annotation.version = int(row["version"])

        return list(state.values())

    def _apply_operation(
        self,
        dataset_id: str,
        image_id: str,
        annotation_uid: str,
        operation: str,
        base_version: int,
        payload: Optional[dict],
    ) -> dict:
        # Ayni client_op_id ile yeniden deneme idempotenttir: yanit kaybolsa
        # bile sunucu ilk sonucu dondurur, islem iki kez uygulanmaz.
        params = {
            "p_dataset_id": dataset_id,
            "p_image_id": image_id,
            "p_client_op_id": str(uuid.uuid4()),
            "p_annotation_uid": annotation_uid,
            "p_operation": operation,
            "p_base_version": base_version,
            "p_annotation": payload,
        }
        delays = self.RETRY_DELAYS
        for attempt in range(len(delays) + 1):
            try:
                result = self._client.rpc("apply_annotation_operation", params).execute()
                break
            except Exception as exc:
                if attempt >= len(delays):
                    raise AnnotationError(f"Annotation islemi kaydedilemedi: {exc}") from exc
                self._sleep(delays[attempt])

        data = result.data or []
        row = data[0] if isinstance(data, list) and data else data
        if not isinstance(row, dict):
            raise AnnotationError("Annotation RPC gecersiz sonuc dondurdu.")
        if row.get("result_status") == "conflict":
            raise AnnotationConflict(row.get("result_annotation"))
        if row.get("result_status") != "applied":
            raise AnnotationError(f"Annotation RPC sonucu: {row.get('result_status')}")

        canonical = dict(row.get("result_annotation") or {})
        if not canonical:
            raise AnnotationError("Annotation RPC canonical sonuc dondurmedi.")
        return canonical
