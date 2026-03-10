"""YOLO .txt etiket dosyalarini okuma."""

from pathlib import Path
from typing import List, Optional, Tuple
from src.models.annotation import (
    Annotation, AnnotationType, parse_annotation_line
)


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

    for line in lines:
        line = line.strip()
        if not line:
            continue
        ann = parse_annotation_line(line, task_type, kpt_shape)
        if ann is not None:
            annotations.append(ann)

    return annotations
