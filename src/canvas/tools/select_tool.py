"""Seçim, taşıma ve boyutlandırma aracı."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QMouseEvent, QKeyEvent
from src.canvas.tools.base_tool import BaseTool


class SelectTool(BaseTool):
    name = "Seç"
    shortcut = "V"
    use_qt_selection = True  # canvas_view, Qt'nin standart seçim/taşıma mekanizmasını kullanır

    def __init__(self, canvas_view, canvas_scene, annotation_controller=None):
        super().__init__(canvas_view, canvas_scene, annotation_controller)

    def activate(self):
        self.view.setDragMode(self.view.DragMode.NoDrag)

    def deactivate(self):
        self.scene.clearSelection()

    def key_press(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.ctrl:
                self.ctrl.delete_selected()

    def get_cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.ArrowCursor)
