"""BBox (detection) annotation grafik ogesi."""

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QGraphicsTextItem, QStyle
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
        BaseAnnotationItem.__init__(self, annotation, class_name, class_color)
        self._img_w = img_w
        self._img_h = img_h
        self._handles = []
        self._updating_handles = False
        self._updating_from_annotation = False
        self._drag_start_state = None    # Taşıma başlangıç state'i
        self._resize_start_state = None  # Handle resize başlangıç state'i

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

    def _capture_state(self) -> dict:
        ann = self._annotation
        return {
            'x_center': ann.x_center,
            'y_center': ann.y_center,
            'width':    ann.width,
            'height':   ann.height,
        }

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
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsFocusable, False)
        self._label.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, False)
        self._label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._update_label_pos()

    def _update_label_pos(self):
        r = self.rect()
        self._label.setPos(r.x() + 2, r.y() - 18)

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
        """Tutamac suruklendiginde dikdortgeni gunceller (sadece 4 kose)."""
        self._updating_handles = True

        sp = self.scenePos()
        sx = max(0.0, min(scene_x, float(self._img_w)))
        sy = max(0.0, min(scene_y, float(self._img_h)))
        lx = sx - sp.x()
        ly = sy - sp.y()

        r = self.rect()
        x1, y1, x2, y2 = r.x(), r.y(), r.x() + r.width(), r.y() + r.height()

        if index == 0:   x1, y1 = lx, ly
        elif index == 1: x2, y1 = lx, ly
        elif index == 2: x2, y2 = lx, ly
        elif index == 3: x1, y2 = lx, ly

        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        self.setRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
        self._update_label_pos()
        self._updating_handles = False
        self._update_handle_positions()
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
        self._updating_from_annotation = True
        self.setPos(0, 0)  # Drag offset'ini sifirla
        x1, y1, x2, y2 = self._ann_to_pixel(self._annotation)
        self.setRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
        self._updating_from_annotation = False
        self._update_handle_positions()
        self._update_label_pos()
        self._label.setPlainText(self._class_name)
        self._apply_style(self.isSelected())

    def _clamp_and_crush(self):
        """Gorsel sinirlarina dayanan kenari sabitler, karsi kenari ezer."""
        r = self.rect()
        sp = self.pos()
        img_w = float(self._img_w)
        img_h = float(self._img_h)
        min_size = 5.0

        left = sp.x() + r.x()
        top = sp.y() + r.y()
        right = left + r.width()
        bottom = top + r.height()

        c_left = max(0.0, left)
        c_top = max(0.0, top)
        c_right = min(img_w, right)
        c_bottom = min(img_h, bottom)

        if c_right - c_left < min_size:
            c_right = c_left + min_size
        if c_bottom - c_top < min_size:
            c_bottom = c_top + min_size

        if c_left != left or c_top != top or c_right != right or c_bottom != bottom:
            new_rect = QRectF(c_left - sp.x(), c_top - sp.y(),
                              c_right - c_left, c_bottom - c_top)
            self.setRect(new_rect)

    def _set_handles_visible(self, visible: bool):
        for h in self._handles:
            h.setVisible(visible)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if not self._updating_from_annotation:
                self._clamp_and_crush()
                self._update_handle_positions()
                self._update_label_pos()
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
            pen = QPen(self._get_border_color(), 3)
            self.setPen(pen)
        self._set_handles_visible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self._apply_style(False)
            self._set_handles_visible(False)
        super().hoverLeaveEvent(event)
