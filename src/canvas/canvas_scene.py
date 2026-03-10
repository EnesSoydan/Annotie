"""QGraphicsScene: gorsel ve annotation yonetimi."""

from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtCore import Signal, QRectF


class CanvasScene(QGraphicsScene):
    """Gorsel ve etiket ogelerini yoneten sahne."""

    annotation_added = Signal(object)
    annotation_removed = Signal(object)
    annotation_selected = Signal(object)
    annotation_modified = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_item = None
        self._annotation_items = []
        self._image_size = (0, 0)
        self.setBackgroundBrush(QColor("#2b2b2b"))

    def set_image(self, pixmap: QPixmap):
        """Arka plan gorselini ayarlar."""
        self.clear_all()
        self._image_item = self.addPixmap(pixmap)
        self._image_item.setZValue(-1)
        self._image_size = (pixmap.width(), pixmap.height())
        self.setSceneRect(QRectF(0, 0, pixmap.width(), pixmap.height()))

    def clear_all(self):
        """Tum ogeleri temizler."""
        self.clear()
        self._image_item = None
        self._annotation_items = []

    def clear_annotations(self):
        """Sadece annotation ogelerini temizler, gorseli korur."""
        for item in self._annotation_items:
            self.removeItem(item)
        self._annotation_items = []

    def add_annotation_item(self, item):
        """Sahneye bir annotation ogesi ekler."""
        self.addItem(item)
        self._annotation_items.append(item)
        self.annotation_added.emit(item)

    def remove_annotation_item(self, item):
        """Sahneden bir annotation ogesini kaldirir."""
        if item in self._annotation_items:
            self._annotation_items.remove(item)
            self.removeItem(item)
            self.annotation_removed.emit(item)

    def get_annotation_items(self) -> list:
        """Tum annotation ogelerini dondurur."""
        return list(self._annotation_items)

    @property
    def image_width(self) -> int:
        w = self._image_size[0]
        if w == 0 and self._image_item is not None:
            # Fallback: sceneRect'ten al
            return int(self.sceneRect().width())
        return w

    @property
    def image_height(self) -> int:
        h = self._image_size[1]
        if h == 0 and self._image_item is not None:
            return int(self.sceneRect().height())
        return h

    @property
    def has_image(self) -> bool:
        return self._image_item is not None
