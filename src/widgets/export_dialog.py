"""Export diyalogu."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QDialogButtonBox, QFileDialog,
    QCheckBox, QHBoxLayout
)
from PySide6.QtCore import Qt


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Veriseti Export Et")
        self.setMinimumWidth(400)
        self._export_path = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        path_group = QGroupBox("Export Konumu")
        path_layout = QHBoxLayout(path_group)
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Export klasörü...")
        path_layout.addWidget(self._path_edit)
        btn = QPushButton("Seç...")
        btn.clicked.connect(self._browse)
        path_layout.addWidget(btn)
        layout.addWidget(path_group)

        options_group = QGroupBox("Seçenekler")
        oform = QFormLayout(options_group)
        self._copy_images = QCheckBox("Görselleri kopyala")
        self._copy_images.setChecked(True)
        oform.addRow("", self._copy_images)
        layout.addWidget(options_group)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Export Klasörü Seç")
        if folder:
            self._path_edit.setText(folder)
            self._export_path = folder

    def _validate_accept(self):
        self._export_path = self._path_edit.text().strip()
        if self._export_path:
            self.accept()

    def get_export_path(self) -> str:
        return self._export_path

    def get_copy_images(self) -> bool:
        return self._copy_images.isChecked()
