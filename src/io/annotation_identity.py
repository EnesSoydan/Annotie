"""Kalici annotation kimlikleri icin .annotie yan dosyasi destegi."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Iterable, Optional

from src.models.annotation import Annotation


IDENTITY_FORMAT_VERSION = 1


def annotation_fingerprint(yolo_line: str) -> str:
    """Canonical YOLO satirinin SHA-256 parmak izini dondurur."""
    normalized = " ".join(yolo_line.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_valid_annotation_uid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False

def new_annotation_uid() -> str:
    return str(uuid.uuid4())


def identity_metadata_path(dataset_root: Path, label_path: Path) -> Path:
    """Bir etiket dosyasini dataset icindeki .annotie yoluna esler."""
    root = Path(dataset_root).resolve(strict=False)
    label = Path(label_path).resolve(strict=False)
    base = root / ".annotie" / "annotation_ids"

    try:
        relative = label.relative_to(root)
        return base / relative.parent / f"{relative.name}.json"
    except ValueError:
        # Dataset disindaki etiketler icin yol bilgisini ifsa etmeyen sabit ad.
        digest = hashlib.sha256(str(label).encode("utf-8")).hexdigest()
        return base / "external" / f"{digest}.json"


def load_identity_metadata(path: Path) -> Optional[list[dict[str, str]]]:
    """Gecerli metadata girdilerini okur; bozuk dosyada None dondurur."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("format_version") != IDENTITY_FORMAT_VERSION:
        return None

    raw_entries = payload.get("annotations")
    if not isinstance(raw_entries, list):
        return None

    entries: list[dict[str, str]] = []
    seen_uids: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            return None
        uid = raw.get("uid")
        fingerprint = raw.get("fingerprint")
        if not is_valid_annotation_uid(uid) or uid in seen_uids:
            return None
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            return None
        try:
            int(fingerprint, 16)
        except ValueError:
            return None
        seen_uids.add(uid)
        entries.append({"uid": uid, "fingerprint": fingerprint.lower()})
    return entries


def build_identity_entries(annotations: Iterable[Annotation]) -> list[dict[str, str]]:
    """Annotation listesinden yazilabilir metadata girdileri uretir."""
    entries = []
    seen_uids: set[str] = set()
    for annotation in annotations:
        uid = getattr(annotation, "uid", None)
        if not is_valid_annotation_uid(uid) or uid in seen_uids:
            uid = new_annotation_uid()
            annotation.uid = uid
        else:
            uid = uid.lower()
            annotation.uid = uid
        seen_uids.add(uid)
        entries.append({
            "uid": uid,
            "fingerprint": annotation_fingerprint(annotation.to_yolo_line()),
        })
    return entries


def write_identity_metadata(path: Path, annotations: Iterable[Annotation]) -> bool:
    """Kimlik metadata'sini atomik olarak yazar."""
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format_version": IDENTITY_FORMAT_VERSION,
            "annotations": build_identity_entries(annotations),
        }
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        print(f"Annotation kimlik metadata'si yazilamadi {path}: {exc}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        return False
