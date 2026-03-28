"""Canvas uyarı banner'ı - aynı görselde başka kullanıcı olduğunda gösterilir."""

from PySide6.QtWidgets import QLabel, QWidget
from PySide6.QtCore import Qt


class CollabOverlay(QLabel):
    """Canvas üzerinde gösterilen işbirliği uyarı banner'ı."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("""
            QLabel {
                background: rgba(255, 152, 0, 200);
                color: #1e1e1e;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 16px;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
            }
        """)
        self.setFixedHeight(30)
        self.hide()

    def show_warning(self, user_names: str):
        """Uyarı gösterir: 'X de bu görseli düzenliyor'."""
        self.setText(f"{user_names} de bu görseli düzenliyor")
        self._reposition()
        self.show()
        self.raise_()

    def hide_warning(self):
        self.hide()

    def _reposition(self):
        """Parent'ın üstüne ortalar."""
        parent = self.parent()
        if parent:
            w = min(parent.width() - 20, 400)
            self.setFixedWidth(w)
            x = (parent.width() - w) // 2
            self.move(x, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()
