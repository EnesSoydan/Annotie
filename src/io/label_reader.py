"""YOLO .txt etiket dosyalarini okuma."""

import hashlib
from pathlib import Path
from typing import List, Optional, Tuple
from src.models.annotation import (
    Annotation, AnnotationType, parse_annotation_line
)


def _deterministic_uid(line_index: int, line: str) -> str:
    """Ayni dosyayi okuyan her instance ayni UID'yi uretir."""
    raw = f"{line_index}|{line}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def read_label_file(
    path: Path,
    task_type: Optional[AnnotationType] = None,
    kpt_shape: Optional[Tuple[int, int]] = None
) -> List[Annotation]:
    """Bir YOLO .txt etiket dosyasini okur ve annotation listesi dondurur."""
    annotations = []

    if not path.exists():
        return annotations

    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Etiket dosyasi okunamadi {path}: {e}")
        return annotations

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        ann = parse_annotation_line(line, task_type, kpt_shape)
        if ann is not None:
            # Deterministik UID: ayni dosyayi okuyan her instance ayni UID alir
            ann.uid = _deterministic_uid(i, line)
            annotations.append(ann)

    return annotations
