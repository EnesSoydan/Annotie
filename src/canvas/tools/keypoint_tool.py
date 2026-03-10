"""Keypoint / Pose estimation cizim araci."""

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem
from PySide6.QtGui import QPen, QBrush, QColor, QCursor, QMouseEvent, QKeyEvent
from PySide6.QtCore import Qt, QPointF, QRectF

from src.canvas.tools.base_tool import BaseTool
from src.utils.constants import MIN_BBOX_SIZE


class KeypointTool(BaseTool):
    name = "Keypoint"
    shortcut = "K"

    def __init__(self, canvas_view, canvas_scene, annotation_controller=None):
        super().__init__(canvas_view, canvas_scene, annotation_controller)
        self._phase = "bbox"        # "bbox" | "keypoints"
        self._bbox_start = None
        self._bbox_rect_preview = None   # Suruklerken gosterilen gecici bbox
        self._bbox_persistent = None     # Keypoints fazinda gosterilen kalici bbox
        self._bbox_rect = None           # (x1,y1,x2,y2) piksel
        self._keypoints = []             # [(nx,ny,vis), ...]
        self._kp_index = 0
        self._keypoint_names = []
        self._kp_dots = []               # Yerlestirilmis keypoint'ler icin gecici dotlar

    def activate(self):
        self.view.setDragMode(self.view.DragMode.NoDrag)
        self._reset()
        self._update_status()

    def deactivate(self):
        # Arac degistirilirken yari bitmis annotation varsa otomatik kaydet
        if self._phase == "keypoints" and self._bbox_rect is not None:
            self._finalize()
        else:
            self._cleanup()

    def set_keypoint_names(self, names):
        self._keypoint_names = names

    def mouse_press(self, event: QMouseEvent, scene_pos):
        if event.button() == Qt.MouseButton.RightButton:
            if self._phase == "keypoints":
                # Keypoint'i gorunmez olarak ekle (atla)
                clamped = self._clamp(scene_pos)
                self._keypoints.append((clamped.x() / self.scene.image_width,
                                        clamped.y() / self.scene.image_height, 0))
                self._kp_index += 1
                self._add_kp_dot_preview(clamped.x(), clamped.y(), 0)
                self._check_done()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._phase == "bbox":
            self._bbox_start = self._clamp(scene_pos)
            self._bbox_rect_preview = QGraphicsRectItem(
                QRectF(self._bbox_start, self._bbox_start)
            )
            self._bbox_rect_preview.setPen(QPen(QColor(255, 165, 0), 2, Qt.PenStyle.DashLine))
            self._bbox_rect_preview.setBrush(QBrush(QColor(255, 165, 0, 20)))
            self._bbox_rect_preview.setZValue(100)
            self.scene.addItem(self._bbox_rect_preview)

        elif self._phase == "keypoints":
            clamped = self._clamp(scene_pos)
            kx = clamped.x() / self.scene.image_width
            ky = clamped.y() / self.scene.image_height
            self._keypoints.append((kx, ky, 2))
            self._kp_index += 1
            self._add_kp_dot_preview(clamped.x(), clamped.y(), 2)
            self._check_done()

    def mouse_move(self, event: QMouseEvent, scene_pos):
        if self._phase == "bbox" and self._bbox_start and self._bbox_rect_preview:
            clamped = self._clamp(scene_pos)
            self._bbox_rect_preview.setRect(
                QRectF(self._bbox_start, clamped).normalized()
            )

    def mouse_release(self, event: QMouseEvent, scene_pos):
        if event.button() == Qt.MouseButton.LeftButton and self._phase == "bbox" and self._bbox_start:
            clamped = self._clamp(scene_pos)
            rect = QRectF(self._bbox_start, clamped).normalized()
            # Surukle-birak preview'ini kaldir
            if self._bbox_rect_preview:
                self.scene.removeItem(self._bbox_rect_preview)
                self._bbox_rect_preview = None
            if rect.width() < MIN_BBOX_SIZE or rect.height() < MIN_BBOX_SIZE:
                self._bbox_start = None
                return
            self._bbox_rect = (rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())
            self._bbox_start = None
            self._phase = "keypoints"
            self._kp_index = 0
            self._keypoints = []
            # Keypoints fazinda bbox'i kalici olarak goster
            self._show_persistent_bbox(rect)
            self._update_status()

    def key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self._reset()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Keypoints fazindaysa ve bbox varsa Enter ile bitir (0 keypoint de gecerli)
            if self._phase == "keypoints" and self._bbox_rect is not None:
                self._finalize()

    def _check_done(self):
        total = len(self._keypoint_names) if self._keypoint_names else None
        if total and self._kp_index >= total:
            self._finalize()
        else:
            self._update_status()

    def _update_status(self):
        try:
            win = self._get_main_window()
            if not win:
                return
            if self._phase == "bbox":
                win.update_tool_label("Keypoint — BBox ciz")
                return
            # keypoints fazi
            total = len(self._keypoint_names)
            if total > 0:
                if self._kp_index < total:
                    name = self._keypoint_names[self._kp_index]
                    msg = (f"Keypoint {self._kp_index + 1}/{total}: '{name}' — "
                           f"Sol: gozukuyor  Sag: gizli  Enter: kaydet  ESC: iptal")
                else:
                    msg = "Tum keypoint'ler tamam — Enter: kaydet  ESC: iptal"
            else:
                msg = (f"Keypoint {self._kp_index} adet — "
                       f"Sol: gozukuyor  Sag: gizli  Enter: kaydet  ESC: iptal")
            win.update_tool_label(msg)
        except Exception:
            pass

    def _show_persistent_bbox(self, rect: QRectF):
        """Keypoints fazinda bbox'i kalici olarak goster (surukle preview'i kalktiktan sonra)."""
        if self._bbox_persistent:
            try:
                self.scene.removeItem(self._bbox_persistent)
            except Exception:
                pass
        self._bbox_persistent = QGraphicsRectItem(rect)
        self._bbox_persistent.setPen(QPen(QColor(255, 165, 0), 2, Qt.PenStyle.SolidLine))
        self._bbox_persistent.setBrush(QBrush(QColor(255, 165, 0, 20)))
        self._bbox_persistent.setZValue(99)
        self.scene.addItem(self._bbox_persistent)

    def _add_kp_dot_preview(self, x: float, y: float, visibility: int):
        """Yerlestirilmis keypoint icin gecici gorsel dot ekle."""
        r = 5
        dot = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
        if visibility == 0:
            dot.setBrush(QBrush(QColor(150, 150, 150, 200)))
            dot.setPen(QPen(QColor(200, 200, 200), 1, Qt.PenStyle.DashLine))
        else:
            dot.setBrush(QBrush(QColor(0, 200, 255, 220)))
            dot.setPen(QPen(QColor(255, 255, 255), 2))
        dot.setZValue(101)
        self.scene.addItem(dot)
        self._kp_dots.append(dot)

    def _finalize(self):
        if not self._bbox_rect:
            return
        x1, y1, x2, y2 = self._bbox_rect
        from src.utils.geometry import rect_to_center_wh
        cx, cy, w, h = rect_to_center_wh(x1, y1, x2, y2)
        bbox_norm = (
            cx / self.scene.image_width, cy / self.scene.image_height,
            w / self.scene.image_width, h / self.scene.image_height
        )
        kps = list(self._keypoints)
        self._reset()
        if self.ctrl:
            self.ctrl.create_keypoints(bbox_norm, kps)

    def _reset(self):
        self._phase = "bbox"
        self._bbox_start = None
        self._bbox_rect = None
        self._keypoints = []
        self._kp_index = 0
        self._cleanup()
        # Arac etiketini "BBox ciz" haline getir
        try:
            win = self._get_main_window()
            if win:
                win.update_tool_label("Keypoint — BBox ciz")
        except Exception:
            pass

    def _cleanup(self):
        if self._bbox_rect_preview:
            try:
                self.scene.removeItem(self._bbox_rect_preview)
            except Exception:
                pass
            self._bbox_rect_preview = None
        if self._bbox_persistent:
            try:
                self.scene.removeItem(self._bbox_persistent)
            except Exception:
                pass
            self._bbox_persistent = None
        for dot in self._kp_dots:
            try:
                self.scene.removeItem(dot)
            except Exception:
                pass
        self._kp_dots = []

    def _clamp(self, pos: QPointF) -> QPointF:
        x = max(0, min(pos.x(), self.scene.image_width))
        y = max(0, min(pos.y(), self.scene.image_height))
        return QPointF(x, y)

    def _get_main_window(self):
        try:
            from PySide6.QtWidgets import QApplication
            for w in QApplication.topLevelWidgets():
                if hasattr(w, 'update_annotation_count'):
                    return w
        except Exception:
            pass
        return None

    def get_cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.CrossCursor)
