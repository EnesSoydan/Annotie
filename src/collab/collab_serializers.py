"""Annotation <-> JSON dönüşümü."""

from src.models.annotation import (
    Annotation, AnnotationType,
    BBoxAnnotation, PolygonAnnotation, OBBAnnotation,
    KeypointsAnnotation, ClassificationAnnotation,
)


def annotation_to_dict(ann: Annotation) -> dict:
    """Annotation modelini JSON-serializable dict'e çevirir."""
    d = {
        "uid": ann.uid,
        "ann_type": ann.ann_type.value,
        "class_id": ann.class_id,
    }

    if ann.ann_type == AnnotationType.BBOX:
        d.update({
            "x_center": ann.x_center,
            "y_center": ann.y_center,
            "width": ann.width,
            "height": ann.height,
        })
    elif ann.ann_type == AnnotationType.POLYGON:
        d["points"] = [[x, y] for x, y in ann.points]
    elif ann.ann_type == AnnotationType.OBB:
        d["corners"] = [[x, y] for x, y in ann.corners]
    elif ann.ann_type == AnnotationType.KEYPOINTS:
        d.update({
            "x_center": ann.x_center,
            "y_center": ann.y_center,
            "width": ann.width,
            "height": ann.height,
            "keypoints": [[x, y, v] for x, y, v in ann.keypoints],
        })
    elif ann.ann_type == AnnotationType.CLASSIFICATION:
        pass  # class_id zaten eklendi

    return d


def dict_to_annotation(d: dict) -> Annotation:
    """JSON dict'ten annotation modeli oluşturur."""
    ann_type = d["ann_type"]
    uid = d.get("uid")
    class_id = d["class_id"]

    if ann_type == "bbox":
        ann = BBoxAnnotation(
            class_id=class_id,
            x_center=d["x_center"],
            y_center=d["y_center"],
            width=d["width"],
            height=d["height"],
        )
    elif ann_type == "polygon":
        points = [(p[0], p[1]) for p in d["points"]]
        ann = PolygonAnnotation(class_id=class_id, points=points)
    elif ann_type == "obb":
        corners = [(c[0], c[1]) for c in d["corners"]]
        ann = OBBAnnotation(class_id=class_id, corners=corners)
    elif ann_type == "keypoints":
        keypoints = [(k[0], k[1], int(k[2])) for k in d["keypoints"]]
        ann = KeypointsAnnotation(
            class_id=class_id,
            x_center=d["x_center"],
            y_center=d["y_center"],
            width=d["width"],
            height=d["height"],
            keypoints=keypoints,
        )
    elif ann_type == "classify":
        ann = ClassificationAnnotation(class_id=class_id)
    else:
        raise ValueError(f"Bilinmeyen annotation tipi: {ann_type}")

    if uid:
        ann.uid = uid
    return ann


def annotation_modify_data(ann: Annotation) -> dict:
    """Annotation'ın güncel geometri verisini dict olarak döndürür."""
    return annotation_to_dict(ann)


def apply_modify_data(ann: Annotation, data: dict):
    """Modify verisini mevcut annotation'a uygular."""
    if ann.ann_type == AnnotationType.BBOX:
        ann.x_center = data.get("x_center", ann.x_center)
        ann.y_center = data.get("y_center", ann.y_center)
        ann.width = data.get("width", ann.width)
        ann.height = data.get("height", ann.height)
    elif ann.ann_type == AnnotationType.POLYGON:
        if "points" in data:
            ann.points = [(p[0], p[1]) for p in data["points"]]
    elif ann.ann_type == AnnotationType.OBB:
        if "corners" in data:
            ann.corners = [(c[0], c[1]) for c in data["corners"]]
    elif ann.ann_type == AnnotationType.KEYPOINTS:
        ann.x_center = data.get("x_center", ann.x_center)
        ann.y_center = data.get("y_center", ann.y_center)
        ann.width = data.get("width", ann.width)
        ann.height = data.get("height", ann.height)
        if "keypoints" in data:
            ann.keypoints = [(k[0], k[1], int(k[2])) for k in data["keypoints"]]
