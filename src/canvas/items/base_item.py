"""Tum annotation grafik ogeleri icin soyut taban."""

from abc import abstractmethod
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt, QObject, Signal


class ItemSignals(QObject):
    """QGraphicsItem QObject degildir, signal/slot icin yardimci sinif."""
    geometry_changed = Signal(object)  # annotation item
    selection_changed = Signal(object, bool)


class BaseAnnotationItem:
    """Tum annotation grafik ogelerinin implement ettigi karisik (mixin) sinif."""

    def __init__(self, annotation=None, class_name: str = "", class_color: QColor = None):
        # PySide6 coklu kalitim (MRO) mekanizmasi Qt base class __init__ cagrisinda
        # bu metodu argumansiz olarak tekrar cagirabilir. Zaten baslatilmissa atla.
        if hasattr(self, '_signals'):
            return
        self._annotation = annotation
        self._class_name = class_name or ""
        self._class_color = class_color
        self._signals = ItemSignals()
        self._label_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        self._selected = False

    @property
    def annotation(self):
        return self._annotation

    @annotation.setter
    def annotation(self, value):
        self._annotation = value

    @property
    def class_color(self) -> QColor:
        return self._class_color

    @class_color.setter
    def class_color(self, value: QColor):
        self._class_color = value

    @property
    def class_name(self) -> str:
        return self._class_name

    @class_name.setter
    def class_name(self, value: str):
        self._class_name = value

    @property
    def signals(self) -> ItemSignals:
        return self._signals

    @abstractmethod
    def update_from_annotation(self):
        """Modelden gorunumu gunceller."""
        pass

    def _get_fill_color(self) -> QColor:
        c = QColor(self._class_color)
        c.setAlpha(60)
        return c

    def _get_border_color(self) -> QColor:
        return QColor(self._class_color)

    def _get_selected_color(self) -> QColor:
        c = QColor(255, 255, 0)
        return c
