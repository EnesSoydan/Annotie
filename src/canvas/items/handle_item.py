"""Yeniden boyutlandirma / tasima tutamaci."""

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PySide6.QtGui import QBrush, QPen, QColor
from PySide6.QtCore import Qt, QRectF


class HandleItem(QGraphicsRectItem):
    """Annotation ogelerinin koselerinde kullanilan suruklenebilir tutamac."""

    HANDLE_SIZE = 6

    def __init__(self, parent_item, handle_index: int, x: float = 0, y: float = 0):
        s = self.HANDLE_SIZE
        super().__init__(-s / 2, -s / 2, s, s, parent_item)
        self._parent_item = parent_item
        self._index = handle_index
        self._dragging = False
        self._drag_start = None

        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

        self.setBrush(QBrush(QColor(255, 255, 255)))
        self.setPen(QPen(QColor(0, 0, 0), 1))

    @property
    def index(self) -> int:
        return self._index

    def set_hover_style(self):
        self.setBrush(QBrush(QColor(0, 160, 255)))

    def set_normal_style(self):
        self.setBrush(QBrush(QColor(255, 255, 255)))

    def hoverEnterEvent(self, event):
        self.set_hover_style()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.set_normal_style()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.scenePos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            scene_pos = event.scenePos()
            # Gorsel sinirlari icinde tut
            img_w = self.scene().image_width
            img_h = self.scene().image_height
            x = max(0, min(scene_pos.x(), img_w))
            y = max(0, min(scene_pos.y(), img_h))
            # Ustuste item koordinatlarina cevir
            parent_scene_pos = self.parentItem().scenePos()
            new_x = x - parent_scene_pos.x()
            new_y = y - parent_scene_pos.y()
            self.setPos(new_x, new_y)
            if hasattr(self._parent_item, 'handle_moved'):
                self._parent_item.handle_moved(self._index, x, y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if hasattr(self._parent_item, 'handle_released'):
                self._parent_item.handle_released(self._index)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
