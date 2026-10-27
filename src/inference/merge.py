"""Tahminleri dataset siniflarina esleme ve mevcut etiketlerle birlestirme.

Saf fonksiyonlar (Qt'siz) — test edilebilir.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.models.annotation import (
    Annotation, AnnotationType, BBoxAnnotation, KeypointsAnnotation,
)
from src.inference.base import Prediction


# ─── Sinif esleme ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ClassTarget:
    """Bir model sinifinin dataset'teki karsiligi."""
    kind: str                 # "existing" | "new" | "ignore"
    class_id: Optional[int] = None   # kind == "existing"
    name: Optional[str] = None       # kind == "new"

    @staticmethod
    def existing(class_id: int) -> "ClassTarget":
        return ClassTarget("existing", class_id=class_id)

    @staticmethod
    def new(name: str) -> "ClassTarget":
        return ClassTarget("new", name=name)

    @staticmethod
    def ignore() -> "ClassTarget":
        return ClassTarget("ignore")


def _norm(name: str) -> str:
    return " ".join(str(name).strip().lower().replace("_", " ").split())


def auto_class_mapping(model_names: Sequence[str],
                       dataset_names: Sequence[str]) -> Dict[int, ClassTarget]:
    """Isimle otomatik esleme. Eslesmeyenler: dataset'te hic sinif yoksa
    'yeni sinif', varsa 'yoksay' (ornegin 80 sinifli COCO modeli 2 sinifli
    datasete 78 yeni sinif eklemesin)."""
    by_name = {}
    for i, n in enumerate(dataset_names):
        by_name.setdefault(_norm(n), i)
    mapping: Dict[int, ClassTarget] = {}
    for mi, mn in enumerate(model_names):
        ds_id = by_name.get(_norm(mn))
        if ds_id is not None:
            mapping[mi] = ClassTarget.existing(ds_id)
        elif not dataset_names:
            mapping[mi] = ClassTarget.new(str(mn))
        else:
            mapping[mi] = ClassTarget.ignore()
    return mapping


def resolve_mapping(mapping: Dict[int, ClassTarget],
                    dataset_names: Sequence[str]) -> Tuple[Dict[int, int], List[str]]:
    """Eslemeyi (model_idx -> nihai dataset class_id) sozlugune cevirir.

    'new' hedefleri dataset'in sonuna eklenecek siniflar olarak id alir;
    ayni isimli birden fazla 'new' tek sinifa toplanir. Doner:
      (id_map, eklenecek_yeni_sinif_adlari)
    """
    id_map: Dict[int, int] = {}
    new_names: List[str] = []
    existing = {_norm(n): i for i, n in enumerate(dataset_names)}
    for mi in sorted(mapping):
        t = mapping[mi]
        if t.kind == "existing" and t.class_id is not None:
            id_map[mi] = t.class_id
        elif t.kind == "new" and t.name and t.name.strip():
            key = _norm(t.name)
            if key in existing:
                id_map[mi] = existing[key]
            else:
                existing[key] = len(dataset_names) + len(new_names)
                new_names.append(t.name.strip())
                id_map[mi] = existing[key]
    return id_map, new_names


# ─── Gorev uyumu ───────────────────────────────────────────────────────────
def can_convert(model_task: AnnotationType, dataset_task: Optional[AnnotationType]) -> bool:
    if dataset_task is None or dataset_task == model_task:
        return True
    return dataset_task == AnnotationType.BBOX and model_task in (
        AnnotationType.POLYGON, AnnotationType.OBB, AnnotationType.KEYPOINTS)


def _to_bbox(ann: Annotation) -> Optional[BBoxAnnotation]:
    if isinstance(ann, BBoxAnnotation):
        return ann
    if isinstance(ann, KeypointsAnnotation):
        return BBoxAnnotation(ann.class_id, ann.x_center, ann.y_center, ann.width, ann.height)
    pts = getattr(ann, "points", None) or getattr(ann, "corners", None)
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    if x2 <= x1 or y2 <= y1:
        return None
    return BBoxAnnotation(ann.class_id, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)


def finalize_predictions(preds: Iterable[Prediction], id_map: Dict[int, int],
                         conf: float,
                         dataset_task: Optional[AnnotationType] = None) -> List[Annotation]:
    """Esik + esleme + gorev donusumu uygulanmis, yeni uid'li annotation kopyalari."""
    out: List[Annotation] = []
    for p in preds:
        if p.score < conf or p.annotation.class_id not in id_map:
            continue
        ann = copy.deepcopy(p.annotation)
        if dataset_task == AnnotationType.BBOX and ann.ann_type != AnnotationType.BBOX:
            ann = _to_bbox(ann)
            if ann is None:
                continue
        ann.class_id = id_map[p.annotation.class_id]
        ann.uid = str(uuid.uuid4())
        ann.version = 0
        out.append(ann)
    return out


# ─── Birlestirme ───────────────────────────────────────────────────────────
MODE_APPEND = "append"
MODE_UNLABELED_ONLY = "unlabeled_only"
MODE_REPLACE = "replace"


def merge_annotations(existing: List[Annotation], new: List[Annotation],
                      mode: str) -> Optional[List[Annotation]]:
    """Yeni etiket listesini dondurur; None = gorsele dokunulmamali.

    Tahmini olmayan gorsellere hicbir modda dokunulmaz ("degistir" modu da
    modelin bir sey bulamadigi gorseldeki elle girilmis etiketleri silmez).
    """
    if not new:
        return None
    if mode == MODE_REPLACE:
        return list(new)
    if mode == MODE_UNLABELED_ONLY:
        return None if existing else list(new)
    # APPEND — siniflandirmada ayni sinif tekrar eklenmez, farkli sinif da
    # mevcut siniflandirmanin yanina eklenmez (gorsel basina tek sinif).
    has_cls = any(a.ann_type == AnnotationType.CLASSIFICATION for a in existing)
    to_add = [a for a in new
              if not (a.ann_type == AnnotationType.CLASSIFICATION and has_cls)]
    if not to_add:
        return None
    return list(existing) + to_add
