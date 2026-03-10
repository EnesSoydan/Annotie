"""Gorsel siniflandirma araci."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QMouseEvent
from src.canvas.tools.base_tool import BaseTool


class ClassifyTool(BaseTool):
    name = "Sınıflandır"
    shortcut = "C"

    def activate(self):
        pass

    def get_cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.PointingHandCursor)
