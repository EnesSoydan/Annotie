"""Polygon (segmentation) cizim araci."""

from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsEllipseItem
from PySide6.QtGui import QPen, QColor, QCursor, QMouseEvent, QKeyEvent
from PySide6.QtCore import Qt, QPointF

from src.canvas.tools.base_tool import BaseTool
from src.utils.geometry import distance


CLOSE_THRESHOLD = 15  # piksel - ilk noktaya bu kadar yaklasinca kapat


class PolygonTool(BaseTool):
    name = "Polygon"
    shortcut = "P"

    def __init__(self, canvas_view, canvas_scene, annotation_controller=None):
        super().__init__(canvas_view, canvas_scene, annotation_controller)
        self._vertices = []        # QPointF listesi (sahne koordinatlari)
        self._preview_line = None  # Imlecten son noktaya cizgi
        self._lines = []           # Cizilen cizgiler
        self._start_dot = None     # Ilk noktayi gosteren kucuk daire

    def activate(self):
        self.view.setDragMode(self.view.DragMode.NoDrag)

    def deactivate(self):
        self._cancel_draw()

    def mouse_press(self, event: QMouseEvent, scene_pos):
        if event.button() == Qt.MouseButton.RightButton:
            # Son noktayi sil
            self._remove_last_vertex()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if not self._in_image(scene_pos):
            return

        # Ilk noktaya yakin tiklandiysa kapat
        if len(self._vertices) >= 3:
            first = self._vertices[0]
            view_first = self.view.mapFromScene(first)
            view_cur = event.pos()
            if distance((view_cur.x(), view_cur.y()), (view_first.x(), view_first.y())) < CLOSE_THRESHOLD:
                self._finalize()
                return

        self._add_vertex(scene_pos)

    def mouse_move(self, event: QMouseEvent, scene_pos):
        if not self._vertices:
            return
        clamped = self._clamp_to_image(scene_pos)
        last = self._vertices[-1]
        if self._preview_line:
            self.scene.removeItem(self._preview_line)
        self._preview_line = QGraphicsLineItem(last.x(), last.y(), clamped.x(), clamped.y())
        self._preview_line.setPen(QPen(QColor(255, 255, 0, 180), 1, Qt.PenStyle.DashLine))
        self._preview_line.setZValue(100)
        self.scene.addItem(self._preview_line)

        # Ilk noktaya yakin -> kapatma gostergesi
        if len(self._vertices) >= 3 and self._start_dot:
            first = self._vertices[0]
            view_first = self.view.mapFromScene(first)
            view_cur = event.pos()
            near = distance((view_cur.x(), view_cur.y()), (view_first.x(), view_first.y())) < CLOSE_THRESHOLD
            self._start_dot.setPen(QPen(QColor(0, 255, 0) if near else QColor(255, 255, 0), 2))

    def mouse_double_click(self, event: QMouseEvent, scene_pos):
        if len(self._vertices) >= 3:
            self._finalize()

    def key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_draw()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if len(self._vertices) >= 3:
                self._finalize()
        elif event.key() == Qt.Key.Key_Backspace:
            self._remove_last_vertex()

    def _add_vertex(self, pos: QPointF):
        clamped = self._clamp_to_image(pos)
        last = self._vertices[-1] if self._vertices else None
        self._vertices.append(clamped)

        # Ilk noktayi gosteren kucuk daire
        if len(self._vertices) == 1:
            r = 6
            self._start_dot = self.scene.addEllipse(
                clamped.x() - r, clamped.y() - r, r * 2, r * 2,
                QPen(QColor(255, 255, 0), 2),
            )
            self._start_dot.setZValue(101)

        # Onceki noktadan cizgi
        if last:
            line = QGraphicsLineItem(last.x(), last.y(), clamped.x(), clamped.y())
            line.setPen(QPen(QColor(255, 255, 0), 2))
            line.setZValue(99)
            self.scene.addItem(line)
            self._lines.append(line)

    def _remove_last_vertex(self):
        if not self._vertices:
            return
        self._vertices.pop()
        if self._lines:
            self.scene.removeItem(self._lines.pop())
        if not self._vertices and self._start_dot:
            self.scene.removeItem(self._start_dot)
            self._start_dot = None

    def _finalize(self):
        if len(self._vertices) < 3:
            self._cancel_draw()
            return

        points = [(p.x(), p.y()) for p in self._vertices]
        self._cleanup_preview()
        if self.ctrl:
            self.ctrl.create_polygon(points)

    def _cancel_draw(self):
        self._vertices = []
        self._cleanup_preview()

    def _cleanup_preview(self):
        for line in self._lines:
            self.scene.removeItem(line)
        self._lines = []
        if self._preview_line:
            self.scene.removeItem(self._preview_line)
            self._preview_line = None
        if self._start_dot:
            self.scene.removeItem(self._start_dot)
            self._start_dot = None
        self._vertices = []

    def get_cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.CrossCursor)
