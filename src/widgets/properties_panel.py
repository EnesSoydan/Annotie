"""Secili etiketin ozellik duzenleme paneli."""

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QComboBox, QGroupBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal

from src.models.annotation import AnnotationType


class PropertiesPanel(QDockWidget):
    """Secili etiketin koordinat ozelliklerini gosteren panel."""

    property_changed = Signal(object, dict)   # (annotation, new_values)

    def __init__(self, parent=None):
        super().__init__("Özellikler", parent)
        self._annotation = None
        self._canvas_item = None
        self._dataset = None
        self._blocking = False
        self._setup_ui()

    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)
        self._layout.addStretch()

        scroll.setWidget(self._container)
        self.setWidget(scroll)
        self.setMinimumWidth(200)

    def set_dataset(self, dataset):
        self._dataset = dataset

    def show_annotation(self, annotation, canvas_item=None):
        """Secili annotationun ozelliklerini goster."""
        self._annotation = annotation
        self._canvas_item = canvas_item
        self._rebuild()

    def clear(self):
        self._annotation = None
        self._canvas_item = None
        self._rebuild()

    def _rebuild(self):
        """Panel icericini sifirdan olusturur."""
        # Mevcut widget'lari temizle
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._annotation:
            self._layout.addWidget(QLabel("Etiket secilmedi"))
            self._layout.addStretch()
            return

        ann = self._annotation
        ann_type = ann.ann_type

        # Sinif
        cls_group = QGroupBox("Sınıf")
        cls_form = QFormLayout(cls_group)
        cls_combo = QComboBox()
        if self._dataset:
            for cls in self._dataset.classes:
                cls_combo.addItem(f"{cls.id}: {cls.name}", cls.id)
            # Mevcut sınıfı seç
            for i in range(cls_combo.count()):
                if cls_combo.itemData(i) == ann.class_id:
                    cls_combo.setCurrentIndex(i)
                    break
        cls_form.addRow("Sınıf:", cls_combo)
        self._layout.addWidget(cls_group)

        # Tip bazinda koordinatlar
        if ann_type == AnnotationType.BBOX:
            self._add_bbox_fields(ann)
        elif ann_type == AnnotationType.POLYGON:
            self._add_polygon_fields(ann)
        elif ann_type == AnnotationType.OBB:
            self._add_obb_fields(ann)
        elif ann_type == AnnotationType.KEYPOINTS:
            self._add_keypoints_fields(ann)
        elif ann_type == AnnotationType.CLASSIFICATION:
            self._layout.addWidget(QLabel("Görsel sınıflandırma etiketi"))

        self._layout.addStretch()

    def _add_bbox_fields(self, ann):
        group = QGroupBox("BBox Koordinatlari (normalize)")
        form = QFormLayout(group)
        for label, val in [("X Merkez:", ann.x_center), ("Y Merkez:", ann.y_center),
                            ("Genislik:", ann.width), ("Yukseklik:", ann.height)]:
            spin = QDoubleSpinBox()
            spin.setRange(0, 1)
            spin.setDecimals(6)
            spin.setSingleStep(0.001)
            spin.setValue(val)
            spin.setReadOnly(True)
            form.addRow(label, spin)
        self._layout.addWidget(group)

    def _add_polygon_fields(self, ann):
        group = QGroupBox(f"Polygon Noktalari ({len(ann.points)} nokta)")
        form = QFormLayout(group)
        for i, (x, y) in enumerate(ann.points[:10]):  # Ilk 10u goster
            lbl = QLabel(f"  ({x:.4f}, {y:.4f})")
            lbl.setStyleSheet("color: #aaa;")
            form.addRow(f"P{i}:", lbl)
        if len(ann.points) > 10:
            form.addRow("...", QLabel(f"  +{len(ann.points)-10} daha"))
        self._layout.addWidget(group)

    def _add_obb_fields(self, ann):
        group = QGroupBox("OBB Koseleri (normalize)")
        form = QFormLayout(group)
        for i, (x, y) in enumerate(ann.corners):
            lbl = QLabel(f"  ({x:.4f}, {y:.4f})")
            lbl.setStyleSheet("color: #aaa;")
            form.addRow(f"K{i}:", lbl)
        self._layout.addWidget(group)

    def _add_keypoints_fields(self, ann):
        bbox_group = QGroupBox("BBox (normalize)")
        bbox_form = QFormLayout(bbox_group)
        for label, val in [("X:", ann.x_center), ("Y:", ann.y_center),
                            ("G:", ann.width), ("Y:", ann.height)]:
            lbl = QLabel(f"  {val:.4f}")
            lbl.setStyleSheet("color: #aaa;")
            bbox_form.addRow(label, lbl)
        self._layout.addWidget(bbox_group)

        kp_group = QGroupBox(f"Keypoints ({len(ann.keypoints)})")
        kp_form = QFormLayout(kp_group)
        VIS = {0: "Gizli", 1: "Engelli", 2: "Görünür"}
        for i, (x, y, v) in enumerate(ann.keypoints[:10]):
            lbl = QLabel(f"  ({x:.3f}, {y:.3f}) {VIS.get(v, v)}")
            lbl.setStyleSheet("color: #aaa;")
            kp_form.addRow(f"KP{i}:", lbl)
        self._layout.addWidget(kp_group)
