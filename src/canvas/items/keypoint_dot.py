"""Tek bir keypoint noktasi grafik ogesi."""

from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtGui import QPen, QBrush, QColor
from PySide6.QtCore import Qt, QRectF

# Gorunurluk sabitleri
VIS_HIDDEN = 0      # Gorsel olarak gizli
VIS_OCCLUDED = 1    # Engelli (var ama gorunmez)
VIS_VISIBLE = 2     # Tam gorunur


class KeypointDot(QGraphicsEllipseItem):
    """Tek bir keypoint noktasini gosteren kucuk daire."""

    RADIUS = 5

    def __init__(self, parent_item, kp_index: int, x: float, y: float,
                 visibility: int = VIS_VISIBLE, name: str = ""):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2, parent_item)
        self._parent_item = parent_item
        self._index = kp_index
        self._visibility = visibility
        self._name = name
        self._dragging = False

        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(12)
        self.setToolTip(name)
        self._apply_style()

    def _apply_style(self):
        if self._visibility == VIS_HIDDEN:
            self.setBrush(QBrush(QColor(100, 100, 100, 180)))
            self.setPen(QPen(QColor(150, 150, 150), 1, Qt.PenStyle.DashLine))
        elif self._visibility == VIS_OCCLUDED:
            self.setBrush(QBrush(QColor(255, 165, 0, 200)))
            self.setPen(QPen(QColor(255, 200, 0), 2))
        else:
            self.setBrush(QBrush(QColor(0, 200, 255, 220)))
            self.setPen(QPen(QColor(255, 255, 255), 2))

    @property
    def visibility(self) -> int:
        return self._visibility

    @property
    def index(self) -> int:
        return self._index

    def set_visibility(self, vis: int):
        self._visibility = vis
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Gorunurlugu donusel degistir
            self._visibility = (self._visibility + 1) % 3
            self._apply_style()
            if hasattr(self._parent_item, 'keypoint_visibility_changed'):
                self._parent_item.keypoint_visibility_changed(self._index, self._visibility)
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            scene_pos = event.scenePos()
            parent_pos = self.parentItem().scenePos() if self.parentItem() else scene_pos
            img_w = self.scene().image_width if self.scene() else 9999
            img_h = self.scene().image_height if self.scene() else 9999
            x = max(0, min(scene_pos.x(), img_w)) - parent_pos.x()
            y = max(0, min(scene_pos.y(), img_h)) - parent_pos.y()
            self.setPos(x, y)
            if hasattr(self._parent_item, 'keypoint_moved'):
                self._parent_item.keypoint_moved(self._index, scene_pos.x(), scene_pos.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)
