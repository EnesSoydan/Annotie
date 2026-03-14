"""OBB (Oriented Bounding Box) annotation grafik ogesi."""

from PySide6.QtWidgets import QGraphicsPolygonItem, QGraphicsItem, QGraphicsTextItem, QStyle
from PySide6.QtGui import QPen, QBrush, QColor, QPolygonF, QFont
from PySide6.QtCore import Qt, QPointF

from src.canvas.items.base_item import BaseAnnotationItem
from src.canvas.items.handle_item import HandleItem
from src.models.annotation import OBBAnnotation


class OBBItem(QGraphicsPolygonItem, BaseAnnotationItem):
    """Dondurulmus sinir kutusu (OBB) annotation ogesi - 4 kose."""

    def __init__(self, annotation: OBBAnnotation, img_w: int, img_h: int,
                 class_name: str, class_color: QColor, parent=None):
        BaseAnnotationItem.__init__(self, annotation, class_name, class_color)
        self._img_w = img_w
        self._img_h = img_h
        self._handles = []

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

    def _ann_to_polygon(self, ann: OBBAnnotation) -> QPolygonF:
        points = [QPointF(x * self._img_w, y * self._img_h) for x, y in ann.corners]
        return QPolygonF(points)

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
            h = HandleItem(self, i, poly[i].x(), poly[i].y())
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

    def handle_moved(self, index: int, scene_x: float, scene_y: float):
        poly = self.polygon()
        sp = self.scenePos()
        x = max(0, min(scene_x, self._img_w))
        y = max(0, min(scene_y, self._img_h))
        if index < poly.count():
            poly[index] = QPointF(x - sp.x(), y - sp.y())
            self.setPolygon(poly)
            self._update_label_pos()
            self._sync_annotation()
            self.signals.geometry_changed.emit(self)

    def handle_released(self, index: int):
        self._sync_annotation()

    def _sync_annotation(self):
        poly = self.polygon()
        sp = self.scenePos()
        corners = []
        for i in range(poly.count()):
            px = (poly[i].x() + sp.x()) / self._img_w
            py = (poly[i].y() + sp.y()) / self._img_h
            corners.append((max(0, min(px, 1)), max(0, min(py, 1))))
        self._annotation.corners = corners

    def update_from_annotation(self):
        poly = self._ann_to_polygon(self._annotation)
        self.setPolygon(poly)
        self._update_handle_positions()
        self._update_label_pos()
        self._label.setPlainText(self._class_name)

    def _set_handles_visible(self, visible: bool):
        for h in self._handles:
            h.setVisible(visible)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
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
