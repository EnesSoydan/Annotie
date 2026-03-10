"""Train/Val/Test split secici widget."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox
from PySide6.QtCore import Signal


class SplitSelector(QWidget):
    split_changed = Signal(str)

    SPLITS = [
        ("train", "Eğitim"),
        ("val", "Doğrulama"),
        ("test", "Test"),
        ("unassigned", "Atanmamış"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel("Split:"))
        self._combo = QComboBox()
        for val, label in self.SPLITS:
            self._combo.addItem(label, val)
        self._combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self._combo)

    def _on_changed(self, idx):
        self.split_changed.emit(self._combo.itemData(idx))

    def set_split(self, split: str):
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == split:
                self._combo.blockSignals(True)
                self._combo.setCurrentIndex(i)
                self._combo.blockSignals(False)
                break

    def get_split(self) -> str:
        return self._combo.currentData()
