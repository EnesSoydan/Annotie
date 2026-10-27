"""Otomatik etiketleme ayarlari — model, esikler, kapsam ve sinif eslemesi."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QDialogButtonBox, QGroupBox, QAbstractItemView,
)

from src.cloud.datasets import task_label
from src.inference.merge import ClassTarget, auto_class_mapping, can_convert
from src.models.annotation import AnnotationType

SCOPE_ALL = "all"
SCOPE_UNLABELED = "unlabeled"
SPLIT_LABELS = {"train": "Train", "val": "Val", "test": "Test", "unassigned": "Atanmamış"}


class AutoLabelSetupDialog(QDialog):
    def __init__(self, models: List[dict], dataset, parent=None):
        super().__init__(parent)
        self._models = models
        self._dataset = dataset
        self._ds_names = [c.name for c in dataset.classes]
        self.setWindowTitle("Otomatik Etiketle")
        self.resize(620, 620)
        self._build()
        self._on_model_changed()

    # ─── Arayuz ────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.model_combo = QComboBox()
        for m in self._models:
            self.model_combo.addItem(m.get("name", "?"))
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        form.addRow("Model:", self.model_combo)
        self.model_info = QLabel()
        self.model_info.setWordWrap(True)
        form.addRow("", self.model_info)

        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.05, 0.95)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(0.25)
        self.conf_spin.setToolTip("Önizlemede kaydırıcıyla tekrar değiştirilebilir.")
        form.addRow("Güven eşiği:", self.conf_spin)
        self.iou_spin = QDoubleSpinBox()
        self.iou_spin.setRange(0.1, 0.95)
        self.iou_spin.setSingleStep(0.05)
        self.iou_spin.setValue(0.45)
        form.addRow("IoU (NMS):", self.iou_spin)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem(f"Tüm görseller ({self._dataset.image_count})", SCOPE_ALL)
        self.scope_combo.addItem("Sadece etiketsiz görseller", SCOPE_UNLABELED)
        for split, label in SPLIT_LABELS.items():
            n = len(self._dataset.get_images_by_split(split))
            if 0 < n < self._dataset.image_count:
                self.scope_combo.addItem(f"Yalnızca {label} ({n})", split)
        form.addRow("Kapsam:", self.scope_combo)
        root.addLayout(form)

        self.task_warning = QLabel()
        self.task_warning.setWordWrap(True)
        self.task_warning.setStyleSheet("color: #d9534f;")
        root.addWidget(self.task_warning)

        box = QGroupBox("Sınıf eşleme (model sınıfı → dataset sınıfı)")
        bl = QVBoxLayout(box)
        self.map_table = QTableWidget(0, 2)
        self.map_table.setHorizontalHeaderLabels(["Model sınıfı", "Dataset'te"])
        self.map_table.verticalHeader().setVisible(False)
        self.map_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.map_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.map_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        bl.addWidget(self.map_table)
        quick = QHBoxLayout()
        b_new = QPushButton("Eşleşmeyenleri yeni sınıf yap")
        b_new.clicked.connect(lambda: self._set_unmatched("new"))
        b_ign = QPushButton("Eşleşmeyenleri yoksay")
        b_ign.clicked.connect(lambda: self._set_unmatched("ignore"))
        quick.addWidget(b_new)
        quick.addWidget(b_ign)
        quick.addStretch(1)
        bl.addLayout(quick)
        root.addWidget(box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Önizlemeyi Başlat")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _target_combo(self, model_name: str, target: ClassTarget) -> QComboBox:
        cb = QComboBox()
        cb.addItem("— Yoksay —", ClassTarget.ignore())
        cb.addItem(f"+ Yeni sınıf: {model_name}", ClassTarget.new(model_name))
        for i, n in enumerate(self._ds_names):
            cb.addItem(n, ClassTarget.existing(i))
        if target.kind == "new":
            cb.setCurrentIndex(1)
        elif target.kind == "existing":
            cb.setCurrentIndex(2 + int(target.class_id))
        return cb

    def _on_model_changed(self):
        m = self.selected_model
        if m is None:
            return
        names = list(m.get("class_names") or [])
        task = self._model_task(m)
        self.model_info.setText(
            f"{task_label(m.get('task_type'))} · {len(names)} sınıf"
            + (f"\n{m['description']}" if m.get("description") else ""))
        ds_task = self._dataset.task_type
        ok = task is not None and can_convert(task, ds_task)
        if not ok:
            self.task_warning.setText(
                f"Bu model ({task_label(m.get('task_type'))}) bu dataset'in görev tipiyle "
                f"({task_label(ds_task.value if ds_task else None)}) uyumlu değil.")
        elif ds_task is not None and task != ds_task:
            self.task_warning.setText(
                f"Model çıktıları dataset görev tipine ({task_label(ds_task.value)}) "
                "dönüştürülecek (çevreleyen kutu).")
        else:
            self.task_warning.setText("")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok and bool(names))

        mapping = auto_class_mapping(names, self._ds_names)
        self.map_table.setRowCount(len(names))
        for r, n in enumerate(names):
            item = QTableWidgetItem(n)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.map_table.setItem(r, 0, item)
            self.map_table.setCellWidget(r, 1, self._target_combo(n, mapping[r]))

    def _set_unmatched(self, kind: str):
        for r in range(self.map_table.rowCount()):
            cb = self.map_table.cellWidget(r, 1)
            if cb.currentData().kind != "existing":
                cb.setCurrentIndex(1 if kind == "new" else 0)

    @staticmethod
    def _model_task(m: dict) -> Optional[AnnotationType]:
        try:
            return AnnotationType(m.get("task_type"))
        except ValueError:
            return None

    # ─── Sonuc ─────────────────────────────────────────────────────────────
    @property
    def selected_model(self) -> Optional[dict]:
        i = self.model_combo.currentIndex()
        return self._models[i] if 0 <= i < len(self._models) else None

    @property
    def conf(self) -> float:
        return float(self.conf_spin.value())

    @property
    def iou(self) -> float:
        return float(self.iou_spin.value())

    @property
    def scope(self) -> str:
        return self.scope_combo.currentData()

    @property
    def mapping(self) -> Dict[int, ClassTarget]:
        return {r: self.map_table.cellWidget(r, 1).currentData()
                for r in range(self.map_table.rowCount())}
