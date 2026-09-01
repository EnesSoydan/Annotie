"""Yeniden boyutlandirma / tasima tutamaci."""

import math

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PySide6.QtGui import QBrush, QPen, QColor
from PySide6.QtCore import Qt, QRectF


class HandleItem(QGraphicsRectItem):
    """Annotation ogelerinin koselerinde kullanilan suruklenebilir tutamac."""

    HANDLE_SIZE = 7.0      # Normal zoom ekran pikseli
    MIN_HANDLE_SIZE = 4.0  # Yüksek zoom alt sınırı

    def __init__(self, parent_item, handle_index: int, x: float = 0, y: float = 0):
        s = self.HANDLE_SIZE
        super().__init__(-s / 2, -s / 2, s, s, parent_item)
        self._parent_item = parent_item
        self._index = handle_index
        self._dragging = False
        self._drag_start = None
        self._display_size = float(s)

        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # Zoom'dan bagimsiz sabit ekran boyutu
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

        self.setBrush(QBrush(QColor(255, 255, 255)))
        self.setPen(QPen(QColor(0, 0, 0), 1))
        self.setVisible(False)  # Varsayilan: gizli; parent hover/select'te gosterilir

    @property
    def index(self) -> int:
        return self._index

    @property
    def display_size(self) -> float:
        return self._display_size

    def set_view_zoom(self, zoom: float):
        """Yüksek zoomda görsel ve tıklanabilir tutamaç alanını küçültür."""
        zoom = max(0.01, float(zoom))
        size = self.HANDLE_SIZE
        if zoom > 1.0:
            size = max(self.MIN_HANDLE_SIZE, self.HANDLE_SIZE / math.sqrt(zoom))
        if abs(size - self._display_size) < 0.01:
            return

        self._display_size = size
        self.setRect(-size / 2, -size / 2, size, size)

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
            # Resize başlamadan önce parent'a haber ver (undo state capture için)
            if hasattr(self._parent_item, 'handle_pressed'):
                self._parent_item.handle_pressed(self._index)
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
