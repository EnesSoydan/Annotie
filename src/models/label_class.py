"""Etiket sinifi modeli."""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from PySide6.QtGui import QColor
from src.utils.colors import get_class_color


@dataclass
class LabelClass:
    """Bir etiket sinifini temsil eder."""
    id: int
    name: str
    color: QColor = None
    keypoint_names: Optional[List[str]] = None
    skeleton: Optional[List[Tuple[int, int]]] = None

    def __post_init__(self):
        if self.color is None:
            self.color = get_class_color(self.id)
