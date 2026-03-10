"""BBox (detection) annotation grafik ogesi."""

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QGraphicsTextItem
from PySide6.QtGui import QPen, QBrush, QColor, QFont
from PySide6.QtCore import Qt, QRectF, QPointF

from src.canvas.items.base_item import BaseAnnotationItem
from src.canvas.items.handle_item import HandleItem
from src.models.annotation import BBoxAnnotation
from src.utils.geometry import center_wh_to_rect, rect_to_center_wh, normalize_bbox


class BBoxItem(QGraphicsRectItem, BaseAnnotationItem):
    """BBox dikdortgen annotation ogesi."""

    # Handle indeksleri: 0=sol-ust, 1=sag-ust, 2=sag-alt, 3=sol-alt  (sadece 4 kose)
    HANDLES = [
        (0.0, 0.0), (1.0, 0.0),
        (1.0, 1.0), (0.0, 1.0),
    ]
    CURSORS = [
        Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
        Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
    ]

    def __init__(self, annotation: BBoxAnnotation, img_w: int, img_h: int,
                 class_name: str, class_color: QColor, parent=None):
        # Once BaseAnnotationItem init
        BaseAnnotationItem.__init__(self, annotation, class_name, class_color)
        self._img_w = img_w
        self._img_h = img_h
        self._handles = []
        self._updating_handles = False

        # Piksel koordinatlarina cevir
        x1, y1, x2, y2 = self._ann_to_pixel(annotation)
        QGraphicsRectItem.__init__(self, QRectF(QPointF(x1, y1), QPointF(x2, y2)), parent)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self._apply_style()
        self._create_handles()
        self._create_label()

    def _ann_to_pixel(self, ann: BBoxAnnotation):
        cx = ann.x_center * self._img_w
        cy = ann.y_center * self._img_h
        w = ann.width * self._img_w
        h = ann.height * self._img_h
        return center_wh_to_rect(cx, cy, w, h)

    def _apply_style(self, selected=False):
        fill = self._get_fill_color()
        border = self._get_selected_color() if selected else self._get_border_color()
        self.setBrush(QBrush(fill))
        pen = QPen(border, 2)
        if selected:
            pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)

    def _create_handles(self):
        r = self.rect()
        for i, (fx, fy) in enumerate(self.HANDLES):
            x = r.x() + fx * r.width()
            y = r.y() + fy * r.height()
            h = HandleItem(self, i, x, y)
            self._handles.append(h)

    def _update_handle_positions(self):
        if self._updating_handles:
            return
        r = self.rect()
        for i, (fx, fy) in enumerate(self.HANDLES):
            x = r.x() + fx * r.width()
            y = r.y() + fy * r.height()
            self._handles[i].setPos(x, y)

    def _create_label(self):
        self._label = QGraphicsTextItem(self._class_name, self)
        self._label.setDefaultTextColor(QColor(255, 255, 255))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        self._label.setFont(font)
        self._label.setZValue(5)
        # Label tıklama/odak olaylarını yutmasın
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsFocusable, False)
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, False)
        self._label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._update_label_pos()

    def _update_label_pos(self):
        r = self.rect()
        self._label.setPos(r.x() + 2, r.y() - 18)

    def handle_moved(self, index: int, scene_x: float, scene_y: float):
        """Tutamac suruklendiginde dikdortgeni gunceller (sadece 4 kose)."""
        self._updating_handles = True

        # Sahne koordinatlarini gorsel sinirlarinda kilple, sonra yerel koordinata cevir
        # rect() yerel koordinatlarla calisir; scenePos() = ogrenin sahne uzayi orijini
        sp = self.scenePos()
        sx = max(0.0, min(scene_x, float(self._img_w)))
        sy = max(0.0, min(scene_y, float(self._img_h)))
        lx = sx - sp.x()
        ly = sy - sp.y()

        r = self.rect()
        x1, y1, x2, y2 = r.x(), r.y(), r.x() + r.width(), r.y() + r.height()

        # Kose indeksi: 0=sol-ust, 1=sag-ust, 2=sag-alt, 3=sol-alt
        if index == 0:   x1, y1 = lx, ly
        elif index == 1: x2, y1 = lx, ly
        elif index == 2: x2, y2 = lx, ly
        elif index == 3: x1, y2 = lx, ly

        # Koordinat siralamasini duzelt (kose cevrilirse)
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        self.setRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
        self._update_label_pos()
        self._updating_handles = False
        # setRect ItemPositionHasChanged degil ItemRectHasChanged tetikler,
        # bu yuzden diger kose tutamaclari elle guncellenmeli
        self._update_handle_positions()
        self._sync_annotation()
        self.signals.geometry_changed.emit(self)

    def handle_released(self, index: int):
        self._sync_annotation()

    def _sync_annotation(self):
        """Grafik konumundan annotation modelini gunceller."""
        r = self.rect()
        sp = self.scenePos()
        x1 = r.x() + sp.x()
        y1 = r.y() + sp.y()
        x2 = x1 + r.width()
        y2 = y1 + r.height()
        cx, cy, w, h = rect_to_center_wh(x1, y1, x2, y2)
        ann = self._annotation
        ann.x_center = cx / self._img_w
        ann.y_center = cy / self._img_h
        ann.width = w / self._img_w
        ann.height = h / self._img_h

    def update_from_annotation(self):
        """Annotation modelinden gorunumu gunceller."""
        x1, y1, x2, y2 = self._ann_to_pixel(self._annotation)
        self.setRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
        self._update_handle_positions()
        self._update_label_pos()
        self._label.setPlainText(self._class_name)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._update_handle_positions()
            self._sync_annotation()
            self.signals.geometry_changed.emit(self)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._apply_style(bool(value))
            self.signals.selection_changed.emit(self, bool(value))
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            pen = QPen(self._get_border_color(), 3)
            self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self._apply_style(False)
        super().hoverLeaveEvent(event)
