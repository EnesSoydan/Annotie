"""Polygon (segmentation) annotation grafik ogesi."""

from PySide6.QtWidgets import QGraphicsPolygonItem, QGraphicsItem, QGraphicsTextItem, QStyle
from PySide6.QtGui import QPen, QBrush, QColor, QPolygonF, QFont
from PySide6.QtCore import Qt, QPointF

from src.canvas.items.base_item import BaseAnnotationItem
from src.canvas.items.handle_item import HandleItem
from src.models.annotation import PolygonAnnotation


class PolygonItem(QGraphicsPolygonItem, BaseAnnotationItem):
    """Polygon segmentasyon annotation ogesi."""

    def __init__(self, annotation: PolygonAnnotation, img_w: int, img_h: int,
                 class_name: str, class_color: QColor, parent=None):
        BaseAnnotationItem.__init__(self, annotation, class_name, class_color)
        self._img_w = img_w
        self._img_h = img_h
        self._handles = []
        self._updating_from_annotation = False
        self._drag_start_state = None
        self._resize_start_state = None

        poly = self._ann_to_polygon(annotation)
        QGraphicsPolygonItem.__init__(self, poly, parent)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self._apply_style()
        self._create_handles()
        self._create_label()

    def _ann_to_polygon(self, ann: PolygonAnnotation) -> QPolygonF:
        points = [QPointF(x * self._img_w, y * self._img_h) for x, y in ann.points]
        return QPolygonF(points)

    def _capture_state(self) -> dict:
        return {'points': [list(p) for p in self._annotation.points]}

    def _apply_style(self, selected=False):
        fill = self._get_fill_color()
        border = self._get_selected_color() if selected else self._get_border_color()
        self.setBrush(QBrush(fill))
        pen = QPen(border, 2)
        if selected:
            pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)

    def _create_handles(self):
        poly = self.polygon()
        for i in range(poly.count()):
            p = poly[i]
            h = HandleItem(self, i, p.x(), p.y())
            self._handles.append(h)

    def _update_handle_positions(self):
        poly = self.polygon()
        for i, h in enumerate(self._handles):
            if i < poly.count():
                h.setPos(poly[i].x(), poly[i].y())

    def _create_label(self):
        self._label = QGraphicsTextItem(self._class_name, self)
        self._label.setDefaultTextColor(QColor(255, 255, 255))
        self._label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._label.setZValue(5)
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsFocusable, False)
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, False)
        self._label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._update_label_pos()

    def _update_label_pos(self):
        poly = self.polygon()
        if poly.isEmpty():
            return
        br = poly.boundingRect()
        self._label.setPos(br.x() + 2, br.y() - 18)

    # --- Taşıma undo ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_state = self._capture_state()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_state is not None:
            new_state = self._capture_state()
            if new_state != self._drag_start_state:
                self.signals.move_finished.emit(self, self._drag_start_state, new_state)
            self._drag_start_state = None

    # --- Handle resize undo ---

    def handle_pressed(self, index: int):
        self._resize_start_state = self._capture_state()

    def handle_moved(self, index: int, scene_x: float, scene_y: float):
        """Bir kosesi sururuken polygon'u gunceller."""
        poly = self.polygon()
        if index < poly.count():
            x = max(0, min(scene_x, self._img_w))
            y = max(0, min(scene_y, self._img_h))
            parent_pos = self.scenePos()
            poly[index] = QPointF(x - parent_pos.x(), y - parent_pos.y())
            self.setPolygon(poly)
            self._update_label_pos()
            self._sync_annotation()
            self.signals.geometry_changed.emit(self)

    def handle_released(self, index: int):
        self._sync_annotation()
        if self._resize_start_state is not None:
            new_state = self._capture_state()
            if new_state != self._resize_start_state:
                self.signals.move_finished.emit(self, self._resize_start_state, new_state)
            self._resize_start_state = None

    def _sync_annotation(self):
        poly = self.polygon()
        sp = self.scenePos()
        points = []
        for i in range(poly.count()):
            px = (poly[i].x() + sp.x()) / self._img_w
            py = (poly[i].y() + sp.y()) / self._img_h
            points.append((max(0, min(px, 1)), max(0, min(py, 1))))
        self._annotation.points = points

    def update_from_annotation(self):
        self._updating_from_annotation = True
        self.setPos(0, 0)
        poly = self._ann_to_polygon(self._annotation)
        self.setPolygon(poly)
        self._updating_from_annotation = False
        self._update_handle_positions()
        self._update_label_pos()
        self._label.setPlainText(self._class_name)
        self._apply_style(self.isSelected())

    def _set_handles_visible(self, visible: bool):
        for h in self._handles:
            h.setVisible(visible)

    def add_vertex(self, scene_x: float, scene_y: float):
        """Polygon'a yeni bir kose ekler."""
        poly = self.polygon()
        sp = self.scenePos()
        poly.append(QPointF(scene_x - sp.x(), scene_y - sp.y()))
        self.setPolygon(poly)
        h = HandleItem(self, len(self._handles), scene_x - sp.x(), scene_y - sp.y())
        h.setVisible(True)
        self._handles.append(h)
        self._sync_annotation()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if not self._updating_from_annotation:
                new_pos = QPointF(value.x(), value.y())
                poly = self.polygon()
                if not poly.isEmpty():
                    br = poly.boundingRect()
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
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if not self._updating_from_annotation:
                self._update_handle_positions()
                self._sync_annotation()
                self.signals.geometry_changed.emit(self)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._apply_style(bool(value))
            self._set_handles_visible(bool(value))
            self.signals.selection_changed.emit(self, bool(value))
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        option.state = option.state & ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            self.setPen(QPen(self._get_border_color(), 3))
        self._set_handles_visible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self._apply_style(False)
            self._set_handles_visible(False)
        super().hoverLeaveEvent(event)
