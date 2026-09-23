"""Nesne bazli bulut annotation servisi ve donusum yardimcilari."""

from __future__ import annotations

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


class AnnotationService:
    def __init__(self, user_id: str, client=None):
        self._client = client or get_client()
        self._uid = user_id

    @staticmethod
    def group_by_image(records: Iterable[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for record in records:
            grouped.setdefault(str(record["image_id"]), []).append(record)
        return grouped

    def list_for_images(self, image_ids: Iterable[str], chunk: int = 100) -> list[dict]:
        ids = [str(image_id) for image_id in image_ids]
        records: list[dict] = []
        try:
            for start in range(0, len(ids), chunk):
                batch = ids[start:start + chunk]
                if not batch:
                    continue
                result = (
                    self._client.table("annotations")
                    .select("*")
                    .in_("image_id", batch)
                    .eq("is_deleted", False)
                    .order("image_id")
                    .order("created_at")
                    .execute()
                )
                records.extend(result.data or [])
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
        current = {ann.uid: ann for ann in annotations}
        known = {str(row["uid"]): dict(row) for row in known_records}

        for uid in sorted(set(known) - set(current)):
            self._apply_operation(
                dataset_id, image_id, uid, "delete",
                int(known[uid]["version"]), None,
            )
            known.pop(uid, None)

        for uid, annotation in current.items():
            payload = annotation_to_cloud_payload(annotation)
            previous = known.get(uid)
            if previous is None:
                operation = "create"
                base_version = 0
            else:
                previous_payload = {
                    "uid": previous["uid"],
                    "class_index": previous["class_index"],
                    "type": previous["type"],
                    "data": previous.get("data") or {},
                }
                if payload == previous_payload:
                    annotation.version = int(previous["version"])
                    continue
                only_class_changed = (
                    payload["type"] == previous_payload["type"]
                    and payload["data"] == previous_payload["data"]
                    and payload["class_index"] != previous_payload["class_index"]
                )
                operation = "class_change" if only_class_changed else "modify"
                base_version = int(previous["version"])

            row = self._apply_operation(
                dataset_id, image_id, uid, operation, base_version, payload,
            )
            row["image_id"] = image_id
            known[uid] = row
            annotation.version = int(row["version"])

        return sorted(known.values(), key=lambda row: (row.get("created_at") or "", row["uid"]))

    def _apply_operation(
        self,
        dataset_id: str,
        image_id: str,
        annotation_uid: str,
        operation: str,
        base_version: int,
        payload: Optional[dict],
    ) -> dict:
        import uuid

        try:
            result = self._client.rpc("apply_annotation_operation", {
                "p_dataset_id": dataset_id,
                "p_image_id": image_id,
                "p_client_op_id": str(uuid.uuid4()),
                "p_annotation_uid": annotation_uid,
                "p_operation": operation,
                "p_base_version": base_version,
                "p_annotation": payload,
            }).execute()
        except Exception as exc:
            raise AnnotationError(f"Annotation islemi kaydedilemedi: {exc}") from exc

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
