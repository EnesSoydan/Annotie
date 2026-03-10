"""Sinif yonetimi dock paneli."""

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QInputDialog, QMenu, QColorDialog, QLabel
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPixmap, QIcon

from src.models.label_class import LabelClass
from src.utils.colors import get_class_color


class ClassListPanel(QDockWidget):
    """Sag dock: sinif listesi ve yonetimi."""

    class_selected = Signal(int)        # class_id
    class_added = Signal(object)        # LabelClass
    class_removed = Signal(int)         # class_id
    class_changed = Signal(object)      # LabelClass

    def __init__(self, parent=None):
        super().__init__("Sınıflar", parent)
        self._classes = []
        self._dataset = None
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

        # Alt butonlar
        btn_layout = QHBoxLayout()
        self._btn_add = QPushButton("+ Sınıf Ekle")
        self._btn_add.clicked.connect(self._add_class)
        btn_layout.addWidget(self._btn_add)
        layout.addLayout(btn_layout)

        self.setWidget(container)
        self.setMinimumWidth(180)

    def set_dataset(self, dataset):
        self._dataset = dataset
        if dataset:
            self.load_classes(dataset.classes)

    def load_classes(self, classes: list):
        """Sinif listesini yukler."""
        self._classes = list(classes)
        self._list.clear()
        for cls in classes:
            self._add_list_item(cls)

    def _add_list_item(self, cls: LabelClass):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, cls)
        item.setText(f"  {cls.id}: {cls.name}")
        # Renk ikonu
        pix = QPixmap(16, 16)
        pix.fill(cls.color)
        item.setIcon(QIcon(pix))
        self._list.addItem(item)

    def _on_selection_changed(self, current, previous):
        if current:
            cls = current.data(Qt.ItemDataRole.UserRole)
            if cls:
                self.class_selected.emit(cls.id)

    def _show_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        cls = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("Yeniden Adlandır").triggered.connect(lambda: self._rename_class(cls, item))
        menu.addAction("Rengi Değiştir").triggered.connect(lambda: self._change_color(cls, item))
        menu.addSeparator()
        menu.addAction("Sil").triggered.connect(lambda: self._remove_class(cls))
        menu.exec(self._list.viewport().mapToGlobal(pos))

    def _add_class(self):
        if not self._dataset:
            return
        name, ok = QInputDialog.getText(self, "Sınıf Ekle", "Sınıf adı:")
        if ok and name.strip():
            cls = self._dataset.add_class(name.strip())
            self._add_list_item(cls)
            self.class_added.emit(cls)

    def _rename_class(self, cls: LabelClass, item: QListWidgetItem):
        name, ok = QInputDialog.getText(self, "Yeniden Adlandır", "Yeni ad:", text=cls.name)
        if ok and name.strip():
            cls.name = name.strip()
            item.setText(f"  {cls.id}: {cls.name}")
            self.class_changed.emit(cls)

    def _change_color(self, cls: LabelClass, item: QListWidgetItem):
        color = QColorDialog.getColor(cls.color, self, "Renk Seç")
        if color.isValid():
            cls.color = color
            pix = QPixmap(16, 16)
            pix.fill(color)
            item.setIcon(QIcon(pix))
            self.class_changed.emit(cls)

    def _remove_class(self, cls: LabelClass):
        if not self._dataset:
            return
        self._dataset.remove_class(cls.id)
        self.load_classes(self._dataset.classes)
        self.class_removed.emit(cls.id)

    def get_selected_class_id(self) -> int:
        item = self._list.currentItem()
        if item:
            cls = item.data(Qt.ItemDataRole.UserRole)
            if cls:
                return cls.id
        return 0
