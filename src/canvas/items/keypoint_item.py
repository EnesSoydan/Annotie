"""Keypoint grubu (pose estimation) annotation grafik ogesi."""

from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem, QGraphicsItem
from PySide6.QtGui import QPen, QBrush, QColor, QFont
from PySide6.QtCore import Qt, QRectF, QPointF

from src.canvas.items.base_item import BaseAnnotationItem
from src.canvas.items.keypoint_dot import KeypointDot
from src.models.annotation import KeypointsAnnotation
from src.utils.geometry import center_wh_to_rect


class KeypointItem(QGraphicsItemGroup, BaseAnnotationItem):
    """Poz tahmini annotation ogesi: bbox + keypoint noktalari + iskelet."""

    def __init__(self, annotation: KeypointsAnnotation, img_w: int, img_h: int,
                 class_name: str, class_color: QColor,
                 keypoint_names=None, skeleton=None, parent=None):
        BaseAnnotationItem.__init__(self, annotation, class_name, class_color)
        QGraphicsItemGroup.__init__(self, parent)
        self._img_w = img_w
        self._img_h = img_h
        self._keypoint_names = keypoint_names or []
        self._skeleton = skeleton or []
        self._dots = []
        self._skeleton_lines = []
        self._bbox_rect = None
        self._label = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(1)
        self._build()

    def _build(self):
        ann = self._annotation
        # BBox
        cx = ann.x_center * self._img_w
        cy = ann.y_center * self._img_h
        w = ann.width * self._img_w
        h = ann.height * self._img_h
        x1, y1, x2, y2 = center_wh_to_rect(cx, cy, w, h)

        self._bbox_rect = QGraphicsRectItem(QRectF(QPointF(x1, y1), QPointF(x2, y2)), self)
        pen = QPen(QColor(self._class_color), 2, Qt.PenStyle.DashLine)
        self._bbox_rect.setPen(pen)
        fill = QColor(self._class_color)
        fill.setAlpha(30)
        self._bbox_rect.setBrush(QBrush(fill))

        # Label
        self._label = QGraphicsTextItem(self._class_name, self)
        self._label.setDefaultTextColor(QColor(255, 255, 255))
        self._label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._label.setPos(x1 + 2, y1 - 18)
        self._label.setZValue(5)

        # Keypoint noktalari
        for i, (kx, ky, kv) in enumerate(ann.keypoints):
            name = self._keypoint_names[i] if i < len(self._keypoint_names) else f"kp{i}"
            dot = KeypointDot(self, i, kx * self._img_w, ky * self._img_h, kv, name)
            self._dots.append(dot)

        # Iskelet
        self._draw_skeleton()

    def _draw_skeleton(self):
        for line in self._skeleton_lines:
            self.removeFromGroup(line)
        self._skeleton_lines = []

        for (i, j) in self._skeleton:
            if i < len(self._dots) and j < len(self._dots):
                d1 = self._dots[i]
                d2 = self._dots[j]
                line = QGraphicsLineItem(
                    d1.pos().x(), d1.pos().y(),
                    d2.pos().x(), d2.pos().y(), self
                )
                line.setPen(QPen(QColor(0, 255, 100, 150), 1))
                line.setZValue(11)
                self._skeleton_lines.append(line)

    def keypoint_moved(self, index: int, scene_x: float, scene_y: float):
        """Keypoint tasindiktan sonra sync ve iskelet guncelle."""
        if index < len(self._annotation.keypoints):
            kx = max(0, min(scene_x / self._img_w, 1))
            ky = max(0, min(scene_y / self._img_h, 1))
            kv = self._annotation.keypoints[index][2]
            self._annotation.keypoints[index] = (kx, ky, kv)
        self._draw_skeleton()
        self.signals.geometry_changed.emit(self)

    def keypoint_visibility_changed(self, index: int, visibility: int):
        if index < len(self._annotation.keypoints):
            kx, ky, _ = self._annotation.keypoints[index]
            self._annotation.keypoints[index] = (kx, ky, visibility)
        self.signals.geometry_changed.emit(self)

    def update_from_annotation(self):
        # Tam yeniden olusturma daha basit
        for item in self.childItems():
            self.removeFromGroup(item)
        self._dots = []
        self._skeleton_lines = []
        self._bbox_rect = None
        self._label = None
        self._build()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = QPointF(value.x(), value.y())
            if self._bbox_rect:
                br = self._bbox_rect.rect()
                img_w = float(self._img_w)
                img_h = float(self._img_h)
                left = new_pos.x() + br.x()
                top = new_pos.y() + br.y()
                right = left + br.width()
                bottom = top + br.height()
                if left < 0:
                    new_pos.setX(new_pos.x() - left)
                if top < 0:
                    new_pos.setY(new_pos.y() - top)
                if right > img_w:
                    new_pos.setX(new_pos.x() - (right - img_w))
                if bottom > img_h:
                    new_pos.setY(new_pos.y() - (bottom - img_h))
            return new_pos
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if self._bbox_rect:
                pen = QPen(
                    self._get_selected_color() if bool(value) else QColor(self._class_color),
                    2, Qt.PenStyle.DashLine
                )
                self._bbox_rect.setPen(pen)
            self.signals.selection_changed.emit(self, bool(value))
        return super().itemChange(change, value)
