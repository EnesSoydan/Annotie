"""Tek bir gorseli temsil eden model."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from src.models.annotation import Annotation


@dataclass
class ImageItem:
    """Veriseti icindeki tek bir gorseli temsil eder."""
    path: Path
    split: str = "unassigned"  # "train", "val", "test", "unassigned"
    annotations: List[Annotation] = field(default_factory=list)
    width: int = 0
    height: int = 0
    dirty: bool = False
    _dimensions_loaded: bool = field(default=False, repr=False)

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def label_filename(self) -> str:
        return self.path.stem + '.txt'

    @property
    def annotation_count(self) -> int:
        return len(self.annotations)

    @property
    def has_annotations(self) -> bool:
        return len(self.annotations) > 0

    def load_dimensions(self):
        """Gorsel boyutlarini lazily yukler."""
        if self._dimensions_loaded:
            return
        try:
            from PySide6.QtGui import QImageReader
            reader = QImageReader(str(self.path))
            size = reader.size()
            if size.isValid():
                self.width = size.width()
                self.height = size.height()
                self._dimensions_loaded = True
        except Exception:
            pass

    def mark_dirty(self):
        self.dirty = True

    def mark_clean(self):
        self.dirty = False
