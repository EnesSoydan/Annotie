"""Modellerim diyalogu — kullaniciya ozgu YOLO modelleri.

Listele / yukle (ad + opsiyonel aciklama) / duzenle / sil. Model metadata'si
(gorev tipi, siniflar) dosyadan otomatik okunur. Agir isler (metadata okuma,
yukleme) QThread'de calisir; UI donmaz.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox,
    QLineEdit, QFormLayout, QPlainTextEdit, QDialogButtonBox, QFileDialog,
    QProgressDialog, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from src.cloud.datasets import task_label
from src.cloud.models import ModelService, format_size


class TaskWorker(QThread):
    """Bir fonksiyonu arka planda calistirir."""
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


def run_with_progress(parent, text: str, fn: Callable, on_done, on_failed=None):
    """fn'i arka planda calistirir; bitene kadar iptal edilemez ilerleme gosterir."""
    progress = QProgressDialog(text, None, 0, 0, parent)
    progress.setWindowTitle("Lütfen bekleyin")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setCancelButton(None)
    worker = TaskWorker(fn, parent)

    def finish():
        progress.close()
        worker.deleteLater()

    def ok(result):
        finish()
        on_done(result)

    def bad(message):
        finish()
        if on_failed:
            on_failed(message)
        else:
            QMessageBox.warning(parent, "Hata", message)

    worker.done.connect(ok)
    worker.failed.connect(bad)
    parent._active_worker = worker  # GC korumasi
    worker.start()
    progress.show()


class _ModelInfoDialog(QDialog):
    """Ad + aciklama girisi (yukleme ve duzenleme icin)."""

    def __init__(self, parent=None, title="Model", name="", description="", info=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 280)
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("Örn. Balon dedektörü v2")
        form.addRow("Ad *:", self.name_edit)
        self.desc_edit = QPlainTextEdit(description or "")
        self.desc_edit.setPlaceholderText("Opsiyonel — modelin ne yaptığı, eğitim verisi vb.")
        form.addRow("Açıklama:", self.desc_edit)
        if info:
            lbl = QLabel(info)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow("Model:", lbl)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Eksik bilgi", "Model adı zorunludur.")
            return
        self.accept()

    @property
    def name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def description(self) -> str:
        return self.desc_edit.toPlainText().strip()


def describe_meta(meta) -> str:
    names = meta.class_names
    shown = ", ".join(names[:12]) + (f" … (+{len(names) - 12})" if len(names) > 12 else "")
    return (f"{task_label(meta.task_type.value)} · {meta.format.upper()} · "
            f"{len(names)} sınıf\n{shown}")


class ModelsDialog(QDialog):
    def __init__(self, user_id: str, parent=None):
        super().__init__(parent)
        self._svc = ModelService(user_id)
        self._models: list[dict] = []
        self._active_worker = None
        self.setWindowTitle("Modellerim")
        self.resize(820, 460)
        self._build()
        self._reload()

    def _build(self):
        root = QVBoxLayout(self)
        info = QLabel("Modelleriniz hesabınıza kaydedilir; giriş yaptığınız her cihazda "
                      "<b>Otomatik Etiketle</b> ile kullanabilirsiniz. Desteklenen: "
                      "<b>.onnx</b> (önerilen) ve <b>.pt</b> (ultralytics kuruluysa).")
        info.setWordWrap(True)
        root.addWidget(info)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Ad", "Görev", "Sınıf", "Boyut", "Açıklama"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.doubleClicked.connect(lambda _i: self._edit())
        root.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.btn_upload = QPushButton("Model Yükle...")
        self.btn_upload.clicked.connect(self._upload)
        self.btn_edit = QPushButton("Düzenle...")
        self.btn_edit.clicked.connect(self._edit)
        self.btn_delete = QPushButton("Sil")
        self.btn_delete.clicked.connect(self._delete)
        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        for b in (self.btn_upload, self.btn_edit, self.btn_delete):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(btn_close)
        root.addLayout(row)
        self._update_buttons()

    # ─── Veri ──────────────────────────────────────────────────────────────
    def _reload(self):
        run_with_progress(self, "Modeller alınıyor...", self._svc.list_models, self._fill)

    def _fill(self, models):
        self._models = models or []
        self.table.setRowCount(len(self._models))
        for r, m in enumerate(self._models):
            names = m.get("class_names") or []
            cells = [
                m.get("name", ""),
                f"{task_label(m.get('task_type'))} ({(m.get('format') or '').upper()})",
                str(len(names)),
                format_size(m.get("size_bytes")),
                (m.get("description") or "").replace("\n", " "),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 4 and m.get("description"):
                    item.setToolTip(m["description"])
                if c == 2 and names:
                    item.setToolTip(", ".join(names))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._update_buttons()

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        return self._models[rows[0].row()] if rows else None

    def _update_buttons(self):
        has = self._selected() is not None
        self.btn_edit.setEnabled(has)
        self.btn_delete.setEnabled(has)

    # ─── Islemler ──────────────────────────────────────────────────────────
    def _upload(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Model Seç", "", "YOLO modelleri (*.onnx *.pt);;ONNX (*.onnx);;PyTorch (*.pt)")
        if not path:
            return
        from src.inference import read_model_meta
        run_with_progress(self, "Model okunuyor...", lambda: read_model_meta(path),
                          lambda meta: self._upload_with_meta(Path(path), meta))

    def _upload_with_meta(self, path: Path, meta):
        dlg = _ModelInfoDialog(self, "Model Yükle", name=path.stem, info=describe_meta(meta))
        if not dlg.exec():
            return
        name, desc = dlg.name, dlg.description
        run_with_progress(
            self, f"'{name}' yükleniyor ({path.stat().st_size / (1 << 20):.1f} MB)...",
            lambda: self._svc.register_model(name, desc, path, meta),
            lambda _row: self._reload())

    def _edit(self):
        m = self._selected()
        if not m:
            return
        dlg = _ModelInfoDialog(self, "Modeli Düzenle", m.get("name", ""), m.get("description") or "")
        if not dlg.exec():
            return
        run_with_progress(self, "Kaydediliyor...",
                          lambda: self._svc.update_model(m["id"], dlg.name, dlg.description),
                          lambda _row: self._reload())

    def _delete(self):
        m = self._selected()
        if not m:
            return
        if QMessageBox.question(
                self, "Modeli Sil",
                f"'{m.get('name')}' modeli hesabınızdan silinsin mi?") != QMessageBox.StandardButton.Yes:
            return
        run_with_progress(self, "Siliniyor...", lambda: self._svc.delete_model(m["id"]),
                          lambda _r: self._reload())

    def done(self, result):
        self._svc.close()
        super().done(result)
