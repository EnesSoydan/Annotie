"""Otomatik etiketleme cikarim katmani — ortak tipler.

Qt'den bagimsizdir. Tum predictor'lar koordinatlari orijinal gorsel boyutuna
gore YOLO-normalize ([0,1]) Annotation nesneleri olarak dondurur; sinif
kimlikleri MODELIN sinif indeksleridir (dataset eslemesi merge.py'de yapilir).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from src.models.annotation import Annotation, AnnotationType


class InferenceError(Exception):
    """Cikarim hatasi (kullaniciya gosterilebilir mesaj)."""


# Ultralytics gorev adi -> uygulama AnnotationType'i
TASK_FROM_ULTRALYTICS = {
    "detect": AnnotationType.BBOX,
    "segment": AnnotationType.POLYGON,
    "obb": AnnotationType.OBB,
    "pose": AnnotationType.KEYPOINTS,
    "classify": AnnotationType.CLASSIFICATION,
}

MODEL_FORMATS = {".onnx": "onnx", ".pt": "pt"}


@dataclass
class ModelMeta:
    """Bir model dosyasindan okunan bilgiler (kayit sirasinda DB'ye yazilir)."""
    format: str                                  # "onnx" | "pt"
    task_type: AnnotationType
    class_names: List[str] = field(default_factory=list)
    imgsz: Optional[int] = None
    kpt_shape: Optional[Tuple[int, int]] = None


@dataclass
class Prediction:
    annotation: Annotation   # class_id = model sinif indeksi
    score: float


class Predictor:
    """Tum model arka uclarinin arayuzu."""
    meta: ModelMeta

    @property
    def class_names(self) -> List[str]:
        return self.meta.class_names

    @property
    def task_type(self) -> AnnotationType:
        return self.meta.task_type

    def predict(self, image_path: Path, conf: float = 0.25,
                iou: float = 0.45) -> List[Prediction]:
        raise NotImplementedError

    def close(self):
        pass


def load_rgb(image_path: Path) -> np.ndarray:
    """Gorseli EXIF yonune gore dondurulmus RGB uint8 dizi olarak okur.

    Uygulama gorselleri QImageReader.setAutoTransform(True) ile gosterdigi icin
    normalize koordinatlarin ayni yonelime gore hesaplanmasi gerekir.
    """
    from PIL import Image, ImageOps
    try:
        with Image.open(image_path) as im:
            im = ImageOps.exif_transpose(im)
            return np.asarray(im.convert("RGB"))
    except Exception as exc:
        raise InferenceError(f"Görsel okunamadı: {image_path.name} ({exc})")
