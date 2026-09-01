"""BBox (detection) cizim araci - 2 tikla ciz modu."""

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem
from PySide6.QtGui import QPen, QBrush, QColor, QCursor, QMouseEvent, QKeyEvent
from PySide6.QtCore import Qt, QPointF, QRectF

from src.canvas.tools.base_tool import BaseTool
from src.canvas.items.bbox_style import PixelSizeBadge, bbox_fill_color
from src.utils.constants import MIN_BBOX_SIZE


class BBoxTool(BaseTool):
    name = "BBox"
    shortcut = "B"

    def __init__(self, canvas_view, canvas_scene, annotation_controller=None):
        super().__init__(canvas_view, canvas_scene, annotation_controller)
        self._drawing = False   # True: ilk nokta konuldu, 2. bekleniyor
        self._start_pos = None
        self._preview = None    # Önizleme dikdörtgeni
        self._start_dot = None  # İlk köşe nokta göstergesi
        self._size_badge = None
        self._view_zoom = 1.0

    def activate(self):
        self.view.setDragMode(self.view.DragMode.NoDrag)
        self.scene.clearSelection()

    def deactivate(self):
        self._cancel_draw()

    # ── Fare olayları ─────────────────────────────────────────────────────────

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if not self._drawing:
            # ── 1. Tıklama: ilk köşeyi yerleştir ────────────────────────────
            if not self._in_image(scene_pos):
                return
            clamped = self._clamp_to_image(scene_pos)
            self._drawing = True
            self._start_pos = clamped
            color = self._active_class_color()

            # İlk köşe nokta göstergesi
            r = 4
            self._start_dot = QGraphicsEllipseItem(
                clamped.x() - r, clamped.y() - r, r * 2, r * 2
            )
            self._start_dot.setPen(QPen(color, 2))
            dot_fill = QColor(color)
            dot_fill.setAlpha(210)
            self._start_dot.setBrush(QBrush(dot_fill))
            self._start_dot.setZValue(102)
            self.scene.addItem(self._start_dot)

            # Önizleme dikdörtgeni (henüz sıfır boyut)
            self._preview = QGraphicsRectItem(QRectF(clamped, clamped))
            self._preview.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
            self._preview.setBrush(QBrush(bbox_fill_color(color)))
            self._preview.setZValue(100)
            self.scene.addItem(self._preview)

            self._size_badge = PixelSizeBadge(color)
            self._size_badge.setZValue(103)
            self._size_badge.set_dimensions(0.0, 0.0)
            self._size_badge.set_box_rect(QRectF(clamped, clamped))
            self._size_badge.set_view_zoom(self._view_zoom)
            self.scene.addItem(self._size_badge)

        else:
            # ── 2. Tıklama: BBox'ı tamamla ──────────────────────────────────
            clamped = self._clamp_to_image(scene_pos)
            rect = QRectF(self._start_pos, clamped).normalized()
            self._cleanup_preview()
            self._drawing = False
            self._start_pos = None

            if rect.width() < MIN_BBOX_SIZE or rect.height() < MIN_BBOX_SIZE:
                return

            if self.ctrl:
                self.ctrl.create_bbox(rect)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if not self._drawing or not self._preview or not self._start_pos:
            return
        clamped = self._clamp_to_image(scene_pos)
        rect = QRectF(self._start_pos, clamped).normalized()
        self._preview.setRect(rect)
        if self._size_badge:
            self._size_badge.set_dimensions(rect.width(), rect.height())
            self._size_badge.set_box_rect(rect)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        # 2-tıklama modunda mouse_release hiçbir şey yapmaz
        pass

    def mouse_double_click(self, event: QMouseEvent, scene_pos: QPointF):
        # Çift tıklama = ikinci tıklama ile aynı → BBox tamamla
        if self._drawing:
            self.mouse_press(event, scene_pos)

    def key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_draw()

    # ── Yardımcı ──────────────────────────────────────────────────────────────

    def _cancel_draw(self):
        self._drawing = False
        self._start_pos = None
        self._cleanup_preview()

    def _cleanup_preview(self):
        if self._preview:
            self.scene.removeItem(self._preview)
            self._preview = None
        if self._start_dot:
            self.scene.removeItem(self._start_dot)
            self._start_dot = None
        if self._size_badge:
            self.scene.removeItem(self._size_badge)
            self._size_badge = None

    def _active_class_color(self) -> QColor:
        if self.ctrl:
            return QColor(self.ctrl.get_active_class_color())
        return QColor(255, 255, 0)

    def set_view_zoom(self, zoom: float):
        self._view_zoom = max(0.01, float(zoom))
        if self._size_badge:
            self._size_badge.set_view_zoom(self._view_zoom)

    def get_cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.CrossCursor)
