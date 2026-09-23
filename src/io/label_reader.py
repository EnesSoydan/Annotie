"""YOLO .txt etiket dosyalarini okuma."""

import hashlib
from collections import defaultdict, deque
from pathlib import Path
from typing import List, Optional, Tuple
from src.io.annotation_identity import (
    annotation_fingerprint,
    build_identity_entries,
    load_identity_metadata,
    new_annotation_uid,
    write_identity_metadata,
)
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
    kpt_shape: Optional[Tuple[int, int]] = None,
    identity_metadata_path: Optional[Path] = None,
) -> List[Annotation]:
    """Bir YOLO .txt etiket dosyasini okur ve annotation listesi dondurur."""
    annotations = []

    if not path.exists():
        return annotations

    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Etiket dosyasi okunamadi {path}: {e}")
        return annotations

    parsed: list[tuple[int, str, Annotation]] = []
    for i, line in enumerate(lines):
        line = line.strip().lstrip("\ufeff").replace(",", ".")
        if not line:
            continue
        try:
            ann = parse_annotation_line(line, task_type, kpt_shape)
        except (ValueError, IndexError) as e:
            print(f"Gecersiz etiket satiri atlandi {path}:{i + 1}: {e}")
            continue
        if ann is not None:
            parsed.append((i, line, ann))

    if identity_metadata_path is None:
        # Eski API davranisi: metadata yolu vermeyen cagrilar deterministik kalir.
        for line_index, line, ann in parsed:
            ann.uid = _deterministic_uid(line_index, line)
            annotations.append(ann)
        return annotations

    stored_entries = load_identity_metadata(identity_metadata_path)
    entries = stored_entries or []
    available_by_fingerprint = defaultdict(deque)
    for entry_index, entry in enumerate(entries):
        available_by_fingerprint[entry["fingerprint"]].append(entry_index)

    fingerprints = [annotation_fingerprint(ann.to_yolo_line()) for _, _, ann in parsed]
    assigned_entry_indexes: list[Optional[int]] = [None] * len(parsed)
    used_entries: set[int] = set()

    # Once parmak iziyle eslestir; satir sirasi degisse bile nesne kimligi korunur.
    for parsed_index, fingerprint in enumerate(fingerprints):
        candidates = available_by_fingerprint[fingerprint]
        while candidates and candidates[0] in used_entries:
            candidates.popleft()
        if candidates:
            entry_index = candidates.popleft()
            assigned_entry_indexes[parsed_index] = entry_index
            used_entries.add(entry_index)

    # Disaridan geometri degisikliginde ayni satir konumunu guvenli fallback say.
    for parsed_index, entry_index in enumerate(assigned_entry_indexes):
        if entry_index is None and parsed_index < len(entries) and parsed_index not in used_entries:
            assigned_entry_indexes[parsed_index] = parsed_index
            used_entries.add(parsed_index)

    for parsed_index, (_, _, ann) in enumerate(parsed):
        entry_index = assigned_entry_indexes[parsed_index]
        ann.uid = entries[entry_index]["uid"] if entry_index is not None else new_annotation_uid()
        annotations.append(ann)

    desired_entries = build_identity_entries(annotations)
    if stored_entries != desired_entries:
        write_identity_metadata(identity_metadata_path, annotations)

    return annotations
