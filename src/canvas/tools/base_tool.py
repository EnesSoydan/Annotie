"""Tüm çizim araçları için soyut taban sınıf."""

from abc import ABC, abstractmethod
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent, QCursor


class BaseTool(ABC):
    """Tüm çizim araçlarının implement ettiği arayüz."""

    name: str = "Taban Araç"
    shortcut: str = ""
    use_qt_selection: bool = False  # True → SelectTool: Qt'nin standart seçim mekanizması kullanılır

    def __init__(self, canvas_view, canvas_scene, annotation_controller=None):
        self.view = canvas_view
        self.scene = canvas_scene
        self.ctrl = annotation_controller

    def activate(self):
        """Araç aktifleştirildiğinde çağrılır."""
        pass

    def deactivate(self):
        """Araç devre dışı bırakıldığında çağrılır."""
        pass

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        pass

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        pass

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        pass

    def mouse_double_click(self, event: QMouseEvent, scene_pos: QPointF):
        pass

    def key_press(self, event: QKeyEvent):
        pass

    def get_cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.ArrowCursor)

    # ── Yardımcı: Görsel sınır kontrolü ──────────────────────────────────────

    def _in_image(self, pos: QPointF) -> bool:
        """Görsel yüklü mü kontrolü.

        Konum kontrolü kaldırıldı: görsel yüklüyse her tıklama geçerli,
        _clamp_to_image zaten koordinatları sınır içine kısar.
        """
        return self.scene.has_image

    def _clamp_to_image(self, pos: QPointF) -> QPointF:
        """Pozisyonu görsel sınırları içine kısar."""
        w = self.scene.image_width
        h = self.scene.image_height
        if w <= 0 or h <= 0:
            return pos
        x = max(0.0, min(pos.x(), float(w)))
        y = max(0.0, min(pos.y(), float(h)))
        return QPointF(x, y)
