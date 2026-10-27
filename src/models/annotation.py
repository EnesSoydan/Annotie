"""YOLO etiket veri modelleri."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional, Union
import uuid


class AnnotationType(Enum):
    BBOX = "bbox"
    POLYGON = "polygon"
    OBB = "obb"
    KEYPOINTS = "keypoints"
    CLASSIFICATION = "classify"


@dataclass
class BBoxAnnotation:
    """Nesne algilama (detection) etiketi.
    Format: class_id x_center y_center width height
    """
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float
    ann_type: AnnotationType = field(default=AnnotationType.BBOX, init=False)
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 0

    def to_yolo_line(self) -> str:
        return f"{self.class_id} {self.x_center:.6f} {self.y_center:.6f} {self.width:.6f} {self.height:.6f}"

    @classmethod
    def from_yolo_line(cls, parts: List[str]) -> 'BBoxAnnotation':
        return cls(
            class_id=int(parts[0]),
            x_center=float(parts[1]),
            y_center=float(parts[2]),
            width=float(parts[3]),
            height=float(parts[4])
        )


@dataclass
class PolygonAnnotation:
    """Segmentasyon etiketi.
    Format: class_id x1 y1 x2 y2 x3 y3 ...
    """
    class_id: int
    points: List[Tuple[float, float]]
    ann_type: AnnotationType = field(default=AnnotationType.POLYGON, init=False)
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 0

    def to_yolo_line(self) -> str:
        coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in self.points)
        return f"{self.class_id} {coords}"

    @classmethod
    def from_yolo_line(cls, parts: List[str]) -> 'PolygonAnnotation':
        class_id = int(parts[0])
        coords = [float(v) for v in parts[1:]]
        points = [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]
        return cls(class_id=class_id, points=points)


@dataclass
class OBBAnnotation:
    """Dondurulmus sinir kutusu (Oriented Bounding Box) etiketi.
    Format: class_id x1 y1 x2 y2 x3 y3 x4 y4
    """
    class_id: int
    corners: List[Tuple[float, float]]  # 4 kose noktasi
    ann_type: AnnotationType = field(default=AnnotationType.OBB, init=False)
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 0

    def to_yolo_line(self) -> str:
        coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in self.corners)
        return f"{self.class_id} {coords}"

    @classmethod
    def from_yolo_line(cls, parts: List[str]) -> 'OBBAnnotation':
        class_id = int(parts[0])
        coords = [float(v) for v in parts[1:]]
        corners = [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]
        return cls(class_id=class_id, corners=corners)


@dataclass
class KeypointsAnnotation:
    """Poz tahmini (pose estimation) etiketi.
    Format: class_id x_center y_center width height kp1_x kp1_y kp1_vis ...
    """
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float
    keypoints: List[Tuple[float, float, int]]  # (x, y, visibility)
    ann_type: AnnotationType = field(default=AnnotationType.KEYPOINTS, init=False)
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 0
    # Dosyadaki keypoint boyutu: data.yaml kpt_shape [k, 2] (x y) veya [k, 3] (x y v).
    # Yazarken korunur; aksi halde [k, 2] datasetler x y v ile bozulurdu.
    kpt_dims: int = 3

    def to_yolo_line(self) -> str:
        bbox = f"{self.class_id} {self.x_center:.6f} {self.y_center:.6f} {self.width:.6f} {self.height:.6f}"
        if self.kpt_dims == 2:
            kps = " ".join(f"{x:.6f} {y:.6f}" for x, y, _v in self.keypoints)
        else:
            kps = " ".join(f"{x:.6f} {y:.6f} {v}" for x, y, v in self.keypoints)
        return f"{bbox} {kps}".rstrip()

    @classmethod
    def from_yolo_line(cls, parts: List[str], kpt_count: int = None,
                       kpt_dims: int = None) -> 'KeypointsAnnotation':
        class_id = int(parts[0])
        x_center = float(parts[1])
        y_center = float(parts[2])
        width = float(parts[3])
        height = float(parts[4])
        kp_values = [float(v) for v in parts[5:]]
        if kpt_dims not in (2, 3):
            if kpt_count and len(kp_values) == kpt_count * 2:
                kpt_dims = 2
            else:
                kpt_dims = 3
        keypoints = []
        for i in range(0, len(kp_values), kpt_dims):
            chunk = kp_values[i:i + kpt_dims]
            if len(chunk) == 3:
                keypoints.append((chunk[0], chunk[1], int(chunk[2])))
            elif len(chunk) == 2:
                keypoints.append((chunk[0], chunk[1], 2))
        return cls(
            class_id=class_id,
            x_center=x_center, y_center=y_center,
            width=width, height=height,
            keypoints=keypoints,
            kpt_dims=kpt_dims,
        )


@dataclass
class ClassificationAnnotation:
    """Gorsel siniflandirma etiketi.
    Format: class_id
    """
    class_id: int
    ann_type: AnnotationType = field(default=AnnotationType.CLASSIFICATION, init=False)
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 0

    def to_yolo_line(self) -> str:
        return f"{self.class_id}"

    @classmethod
    def from_yolo_line(cls, parts: List[str]) -> 'ClassificationAnnotation':
        return cls(class_id=int(parts[0]))


# Tip birlesimi
Annotation = Union[BBoxAnnotation, PolygonAnnotation, OBBAnnotation, KeypointsAnnotation, ClassificationAnnotation]


def detect_annotation_type(parts: List[str], kpt_shape: Optional[Tuple[int, int]] = None) -> AnnotationType:
    """Bir YOLO satirindaki deger sayisina gore etiket tipini otomatik algilar."""
    n = len(parts) - 1  # class_id haric
    if n == 0:
        return AnnotationType.CLASSIFICATION
    # Pose dataseti (kpt_shape var) uzunlugu tutan satirlari OBB/polygon'a kaptirmaz
    if kpt_shape and n == 4 + kpt_shape[0] * kpt_shape[1]:
        return AnnotationType.KEYPOINTS
    if n == 4:
        return AnnotationType.BBOX
    if n == 8:
        return AnnotationType.OBB
    # 4'ten buyuk cift sayi ve 8 degil -> segmentasyon
    if n > 4 and n % 2 == 0 and n != 8:
        return AnnotationType.POLYGON
    # 4'ten buyuk tek sayi veya kpt_shape varsa -> keypoints
    if n > 4:
        return AnnotationType.KEYPOINTS
    return AnnotationType.BBOX


def parse_annotation_line(line: str, task_type: Optional[AnnotationType] = None,
                          kpt_shape: Optional[Tuple[int, int]] = None) -> Optional[Annotation]:
    """Bir YOLO etiket satirini parse eder."""
    line = line.strip()
    if not line:
        return None

    parts = line.split()
    if not parts:
        return None

    if task_type is None:
        task_type = detect_annotation_type(parts, kpt_shape)

    if task_type == AnnotationType.BBOX:
        return BBoxAnnotation.from_yolo_line(parts)
    elif task_type == AnnotationType.POLYGON:
        return PolygonAnnotation.from_yolo_line(parts)
    elif task_type == AnnotationType.OBB:
        return OBBAnnotation.from_yolo_line(parts)
    elif task_type == AnnotationType.KEYPOINTS:
        if kpt_shape:
            return KeypointsAnnotation.from_yolo_line(parts, kpt_shape[0], kpt_shape[1])
        return KeypointsAnnotation.from_yolo_line(parts)
    elif task_type == AnnotationType.CLASSIFICATION:
        return ClassificationAnnotation.from_yolo_line(parts)
    return None
