"""Veriseti modeli."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from src.models.label_class import LabelClass
from src.models.image_item import ImageItem
from src.models.annotation import AnnotationType


@dataclass
class Dataset:
    """Bir YOLO verisetini temsil eder."""
    root_path: Optional[Path] = None
    classes: List[LabelClass] = field(default_factory=list)
    images: Dict[str, ImageItem] = field(default_factory=dict)  # key: str(path)
    task_type: Optional[AnnotationType] = None
    kpt_shape: Optional[Tuple[int, int]] = None  # (keypoint_sayisi, deger_sayisi) orn: (17, 3)
    is_temporary: bool = False  # Gecici klasor modu

    # Yollar
    train_images_path: Optional[Path] = None
    train_labels_path: Optional[Path] = None
    val_images_path: Optional[Path] = None
    val_labels_path: Optional[Path] = None
    test_images_path: Optional[Path] = None
    test_labels_path: Optional[Path] = None

    @property
    def class_count(self) -> int:
        return len(self.classes)

    @property
    def image_count(self) -> int:
        return len(self.images)

    @property
    def class_names(self) -> List[str]:
        return [c.name for c in self.classes]

    def get_class_by_id(self, class_id: int) -> Optional[LabelClass]:
        for c in self.classes:
            if c.id == class_id:
                return c
        return None

    def get_class_by_name(self, name: str) -> Optional[LabelClass]:
        for c in self.classes:
            if c.name == name:
                return c
        return None

    def add_class(self, name: str, color=None) -> LabelClass:
        new_id = len(self.classes)
        lc = LabelClass(id=new_id, name=name, color=color)
        self.classes.append(lc)
        return lc

    def remove_class(self, class_id: int):
        self.classes = [c for c in self.classes if c.id != class_id]
        # ID'leri yeniden sirala
        for i, c in enumerate(self.classes):
            c.id = i

    def get_images_by_split(self, split: str) -> List[ImageItem]:
        return [img for img in self.images.values() if img.split == split]

    def get_all_images(self) -> List[ImageItem]:
        return list(self.images.values())

    def add_image(self, image: ImageItem):
        self.images[str(image.path)] = image

    def remove_image(self, path: str):
        if path in self.images:
            del self.images[path]

    def get_image(self, path: str) -> Optional[ImageItem]:
        return self.images.get(path)

    def remove_images_by_split(self, split: str):
        """Belirli split'teki tüm görselleri kaldırır."""
        keys = [k for k, img in self.images.items() if img.split == split]
        for k in keys:
            del self.images[k]

    def get_dirty_images(self) -> List[ImageItem]:
        return [img for img in self.images.values() if img.dirty]

    def get_label_path_for_image(self, image: ImageItem) -> Optional[Path]:
        """Gorsel icin karsilik gelen etiket dosyasi yolunu dondurur.

        Kural:
          - Gorsel 'images/' adli bir klasordeyse → kardes 'labels/' klasorune yaz
            Ornek: dataset/images/img.jpg → dataset/labels/img.txt
          - Diger durumlarda → gorsel klasorunde 'labels/' alt klasorune yaz
            Ornek: photos/img.jpg → photos/labels/img.txt
        """
        if self.is_temporary:
            return self._infer_label_path(image)

        split = image.split
        if split == "train" and self.train_labels_path:
            return self.train_labels_path / image.label_filename
        elif split == "val" and self.val_labels_path:
            return self.val_labels_path / image.label_filename
        elif split == "test" and self.test_labels_path:
            return self.test_labels_path / image.label_filename

        # Fallback: split atanmamis veya path eksik → yola gore tahmin et
        return self._infer_label_path(image)

    def _infer_label_path(self, image: ImageItem) -> Path:
        """Gorsel yoluna bakarak etiket dosyasi yolunu tahmin eder."""
        img_parent = image.path.parent
        if img_parent.name.lower() == 'images':
            # .../images/img.jpg → .../labels/img.txt  (kardes labels/ klasoru)
            return img_parent.parent / 'labels' / image.label_filename
        else:
            # .../folder/img.jpg → .../folder/labels/img.txt
            return img_parent / 'labels' / image.label_filename
