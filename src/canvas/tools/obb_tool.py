"""OBB (Oriented Bounding Box) cizim araci - 3 nokta tiklama."""

from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem
from PySide6.QtGui import QPen, QBrush, QColor, QPolygonF, QCursor, QMouseEvent, QKeyEvent
from PySide6.QtCore import Qt, QPointF

from src.canvas.tools.base_tool import BaseTool
from src.utils.geometry import obb_from_3_points


class OBBTool(BaseTool):
    name = "OBB"
    shortcut = "O"

    def __init__(self, canvas_view, canvas_scene, annotation_controller=None):
        super().__init__(canvas_view, canvas_scene, annotation_controller)
        self._phase = 0  # 0=bos, 1=p1 konuldu, 2=p2 konuldu
        self._p1 = None
        self._p2 = None
        self._preview_line = None
        self._preview_poly = None

    def activate(self):
        self.view.setDragMode(self.view.DragMode.NoDrag)
        self._phase = 0

    def deactivate(self):
        self._cancel_draw()

    def mouse_press(self, event: QMouseEvent, scene_pos):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._in_image(scene_pos):
            return
        clamped = self._clamp_to_image(scene_pos)

        if self._phase == 0:
            self._p1 = clamped
            self._phase = 1
        elif self._phase == 1:
            self._p2 = clamped
            self._phase = 2
        elif self._phase == 2:
            # 3. nokta -> OBB tamamlandi
            p3 = clamped
            corners = obb_from_3_points(
                (self._p1.x(), self._p1.y()),
                (self._p2.x(), self._p2.y()),
                (p3.x(), p3.y())
            )
            self._cleanup_preview()
            self._phase = 0
            if self.ctrl:
                self.ctrl.create_obb(corners)

    def mouse_move(self, event: QMouseEvent, scene_pos):
        clamped = self._clamp_to_image(scene_pos)
        self._cleanup_preview()

        if self._phase == 1 and self._p1:
            self._preview_line = QGraphicsLineItem(
                self._p1.x(), self._p1.y(), clamped.x(), clamped.y()
            )
            self._preview_line.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
            self._preview_line.setZValue(100)
            self.scene.addItem(self._preview_line)

        elif self._phase == 2 and self._p1 and self._p2:
            corners = obb_from_3_points(
                (self._p1.x(), self._p1.y()),
                (self._p2.x(), self._p2.y()),
                (clamped.x(), clamped.y())
            )
            poly_pts = [QPointF(x, y) for x, y in corners]
            poly_pts.append(poly_pts[0])  # kapat
            self._preview_poly = QGraphicsPolygonItem(QPolygonF(poly_pts))
            self._preview_poly.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
            self._preview_poly.setBrush(QBrush(QColor(255, 200, 0, 30)))
            self._preview_poly.setZValue(100)
            self.scene.addItem(self._preview_poly)

    def key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_draw()

    def _cancel_draw(self):
        self._phase = 0
        self._p1 = self._p2 = None
        self._cleanup_preview()

    def _cleanup_preview(self):
        if self._preview_line:
            self.scene.removeItem(self._preview_line)
            self._preview_line = None
        if self._preview_poly:
            self.scene.removeItem(self._preview_poly)
            self._preview_poly = None

    def get_cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.CrossCursor)
