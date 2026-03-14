"""Mevcut gorselin etiket listesi dock paneli."""

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QLabel, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QAction

from src.models.annotation import AnnotationType

TYPE_ICONS = {
    AnnotationType.BBOX: "BBox",
    AnnotationType.POLYGON: "Poly",
    AnnotationType.OBB: "OBB",
    AnnotationType.KEYPOINTS: "Pose",
    AnnotationType.CLASSIFICATION: "Cls",
}


class _AnnotationListWidget(QListWidget):
    """Del tuşu ve sağ tık menüsü destekli liste widget'ı."""
    delete_requested = Signal(object)  # annotation

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            item = self.currentItem()
            if item:
                ann = item.data(Qt.ItemDataRole.UserRole)
                if ann:
                    self.delete_requested.emit(ann)
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            ann = item.data(Qt.ItemDataRole.UserRole)
            if ann:
                menu = QMenu(self)
                act_del = QAction("Sil", self)
                act_del.triggered.connect(lambda: self.delete_requested.emit(ann))
                menu.addAction(act_del)
                menu.exec(event.globalPos())
                event.accept()
                return
        super().contextMenuEvent(event)


class AnnotationListPanel(QDockWidget):
    """Sag dock: mevcut gorselin etiket listesi."""

    annotation_selected = Signal(object)   # annotation
    annotation_delete_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__("Etiketler", parent)
        self._annotations = []
        self._classes = []
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._count_label = QLabel("0 etiket")
        self._count_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._count_label)

        self._list = _AnnotationListWidget()
        self._list.currentItemChanged.connect(self._on_selection_changed)
        self._list.delete_requested.connect(self.annotation_delete_requested)
        layout.addWidget(self._list)

        btn_layout = QHBoxLayout()
        btn_del = QPushButton("Seçiliyi Sil")
        btn_del.clicked.connect(self._delete_selected)
        btn_layout.addWidget(btn_del)
        layout.addLayout(btn_layout)

        self.setWidget(container)
        self.setMinimumWidth(180)

    def load_annotations(self, annotations: list, classes: list):
        """Etiket listesini yukler."""
        self._annotations = annotations
        self._classes = classes
        self._list.clear()

        for ann in annotations:
            type_label = TYPE_ICONS.get(ann.ann_type, "?")
            cls = next((c for c in classes if c.id == ann.class_id), None)
            cls_name = cls.name if cls else f"Sınıf {ann.class_id}"
            color = cls.color if cls else QColor(200, 200, 200)

            item = QListWidgetItem(f"[{type_label}] {cls_name}")
            item.setData(Qt.ItemDataRole.UserRole, ann)
            item.setForeground(color)
            self._list.addItem(item)

        self._count_label.setText(f"{len(annotations)} etiket")

    def _on_selection_changed(self, current, previous):
        if current:
            ann = current.data(Qt.ItemDataRole.UserRole)
            if ann:
                self.annotation_selected.emit(ann)

    def _delete_selected(self):
        item = self._list.currentItem()
        if item:
            ann = item.data(Qt.ItemDataRole.UserRole)
            if ann:
                self.annotation_delete_requested.emit(ann)

    def select_annotation(self, annotation):
        """Belirli bir etiketi secili yapar."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) is annotation:
                self._list.setCurrentItem(item)
                break
