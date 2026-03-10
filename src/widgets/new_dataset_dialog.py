"""Yeni veriseti olusturma diyalogu."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QDialogButtonBox, QFileDialog,
    QListWidget, QListWidgetItem, QInputDialog, QColorDialog, QLabel, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap

from src.models.dataset import Dataset
from src.models.label_class import LabelClass
from src.utils.colors import get_class_color


class NewDatasetDialog(QDialog):
    """Yeni YOLO veriseti olusturma diyalogu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yeni Veriseti Oluştur")
        self.setMinimumSize(500, 450)
        self._classes = []
        self._root_path = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Klasor sec
        path_group = QGroupBox("Veriseti Konumu")
        path_layout = QHBoxLayout(path_group)
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Klasor yolu...")
        path_layout.addWidget(self._path_edit)
        btn_browse = QPushButton("Seç...")
        btn_browse.clicked.connect(self._browse_path)
        path_layout.addWidget(btn_browse)
        layout.addWidget(path_group)

        # Sınıflar
        cls_group = QGroupBox("Sınıflar")
        cls_layout = QVBoxLayout(cls_group)
        self._cls_list = QListWidget()
        cls_layout.addWidget(self._cls_list)
        cls_btn_layout = QHBoxLayout()
        btn_add = QPushButton("+ Ekle")
        btn_add.clicked.connect(self._add_class)
        btn_remove = QPushButton("- Sil")
        btn_remove.clicked.connect(self._remove_class)
        cls_btn_layout.addWidget(btn_add)
        cls_btn_layout.addWidget(btn_remove)
        cls_layout.addLayout(cls_btn_layout)
        layout.addWidget(cls_group)

        # Tamam / Iptal
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Veriseti Klasörü Seç")
        if folder:
            self._path_edit.setText(folder)
            self._root_path = folder

    def _add_class(self):
        name, ok = QInputDialog.getText(self, "Sınıf Ekle", "Sınıf adı:")
        if ok and name.strip():
            cls_id = len(self._classes)
            color = get_class_color(cls_id)
            cls = LabelClass(id=cls_id, name=name.strip(), color=color)
            self._classes.append(cls)
            item = QListWidgetItem(f"{cls_id}: {name.strip()}")
            pix = QPixmap(16, 16)
            pix.fill(color)
            item.setIcon(QIcon(pix))
            self._cls_list.addItem(item)

    def _remove_class(self):
        row = self._cls_list.currentRow()
        if row >= 0:
            self._cls_list.takeItem(row)
            if row < len(self._classes):
                self._classes.pop(row)
            # ID'leri guncelle
            for i, cls in enumerate(self._classes):
                cls.id = i
            self._cls_list.clear()
            for cls in self._classes:
                pix = QPixmap(16, 16)
                pix.fill(cls.color)
                item = QListWidgetItem(f"{cls.id}: {cls.name}")
                item.setIcon(QIcon(pix))
                self._cls_list.addItem(item)

    def _validate_and_accept(self):
        self._root_path = self._path_edit.text().strip()
        if not self._root_path:
            return
        self.accept()

    def get_result(self):
        """Olusturulacak dataset bilgilerini dondurur."""
        return {
            "root_path": self._root_path,
            "classes": self._classes,
        }
