"""Ekip Çalışması diyalogu — Faz 4.

Ekip seç → o ekibin datasetlerini listele → yeni dataset oluştur / sil.
Dataset şu an metadata'dir (ad, görev tipi, sınıflar); görsellerin
senkronizasyonu Faz 5'te eklenecek.

Servis çağrıları senkron (modal diyalog, WaitCursor).
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QComboBox, QApplication, QMessageBox,
    QLineEdit, QFormLayout, QPlainTextEdit, QSpinBox, QDialogButtonBox, QGroupBox,
    QFileDialog, QProgressDialog,
)

from src.cloud.teams import TeamService, role_label
from src.cloud.datasets import (
    DatasetService, DatasetError, TASK_TYPES, task_label,
)
from src.cloud.images import ImageService
from src.cloud.storage import StorageClient
from src.widgets.upload_worker import UploadWorker
from src.utils.constants import SUPPORTED_IMAGE_FORMATS


class TeamWorkspaceDialog(QDialog):
    def __init__(self, user_id: str, parent=None, on_open=None):
        super().__init__(parent)
        self._on_open = on_open   # callback(dataset_dict) → editörde aç
        self._team_svc = TeamService(user_id)
        self._ds_svc = DatasetService(user_id)
        self._img_svc = ImageService(user_id)
        self._storage = StorageClient()
        self._upload_worker = None
        self._teams: list[dict] = []
        self._datasets: list[dict] = []

        self.setWindowTitle("Ekip Çalışması")
        self.setModal(True)
        self.resize(760, 540)
        self._build()
        self._reload_teams()

    # ─── Arayüz ────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Ekip:"))
        self.team_combo = QComboBox()
        self.team_combo.currentIndexChanged.connect(self._on_team_changed)
        top.addWidget(self.team_combo, 1)
        btn_refresh = QPushButton("Yenile")
        btn_refresh.clicked.connect(self._reload_teams)
        top.addWidget(btn_refresh)
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Sol: dataset listesi + butonlar
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("Datasetler"))
        self.ds_list = QListWidget()
        self.ds_list.currentRowChanged.connect(self._on_ds_selected)
        lv.addWidget(self.ds_list, 1)
        btns = QHBoxLayout()
        self.btn_new = QPushButton("Yeni Dataset")
        self.btn_new.clicked.connect(self._on_new_dataset)
        self.btn_del = QPushButton("Sil")
        self.btn_del.clicked.connect(self._on_delete_dataset)
        btns.addWidget(self.btn_new)
        btns.addWidget(self.btn_del)
        lv.addLayout(btns)
        splitter.addWidget(left)

        # Sağ: dataset detayı
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.detail_header = QLabel("Bir dataset seçin")
        self.detail_header.setStyleSheet("font-weight:bold; font-size:14px;")
        rv.addWidget(self.detail_header)
        self.detail_info = QLabel("")
        self.detail_info.setWordWrap(True)
        rv.addWidget(self.detail_info)
        rv.addWidget(QLabel("Sınıflar"))
        self.class_list = QListWidget()
        rv.addWidget(self.class_list, 1)

        # Görseller
        img_row = QHBoxLayout()
        self.img_count_label = QLabel("Görseller: —")
        self.btn_upload = QPushButton("Görselleri Yükle...")
        self.btn_upload.clicked.connect(self._on_upload_images)
        img_row.addWidget(self.img_count_label, 1)
        img_row.addWidget(self.btn_upload)
        rv.addLayout(img_row)

        # Datayı editörde aç
        self.btn_open = QPushButton("Datayı Editörde Aç")
        self.btn_open.clicked.connect(self._on_open_dataset_clicked)
        rv.addWidget(self.btn_open)

        note = QLabel("Not: Görseller içerik-hash ile R2'ye yüklenir; "
                      "etiketleme entegrasyonu sonraki adımda gelecek.")
        note.setStyleSheet("color:#888888;")
        note.setWordWrap(True)
        rv.addWidget(note)
        splitter.addWidget(right)
        splitter.setSizes([300, 460])

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    # ─── Ekipler ───────────────────────────────────────────────────────────
    def _reload_teams(self):
        teams = self._busy(self._team_svc.list_my_teams)
        if teams is None:
            return
        self._teams = teams
        self.team_combo.blockSignals(True)
        self.team_combo.clear()
        for t in teams:
            self.team_combo.addItem(f"{t['name']}  ·  {role_label(t.get('role'))}", t)
        self.team_combo.blockSignals(False)
        if teams:
            self.team_combo.setCurrentIndex(0)
            self._on_team_changed(0)
        else:
            self._datasets = []
            self.ds_list.clear()
            self._clear_detail()
            self._update_buttons()

    def _current_team(self) -> Optional[dict]:
        idx = self.team_combo.currentIndex()
        if 0 <= idx < len(self._teams):
            return self._teams[idx]
        return None

    def _on_team_changed(self, _idx: int):
        self._reload_datasets()
        self._update_buttons()

    # ─── Datasetler ────────────────────────────────────────────────────────
    def _reload_datasets(self):
        team = self._current_team()
        self.ds_list.clear()
        self._clear_detail()
        if not team:
            self._datasets = []
            return
        datasets = self._busy(lambda: self._ds_svc.list_team_datasets(team["id"])) or []
        self._datasets = datasets
        for ds in datasets:
            item = QListWidgetItem(f"{ds['name']}  ·  {task_label(ds.get('task_type'))}")
            item.setData(Qt.ItemDataRole.UserRole, ds)
            self.ds_list.addItem(item)
        if datasets:
            self.ds_list.setCurrentRow(0)

    def _on_ds_selected(self, row: int):
        if row < 0 or row >= len(self._datasets):
            self._clear_detail()
            return
        ds = self._datasets[row]
        self.detail_header.setText(ds["name"])
        kpt = ds.get("kpt_shape")
        kpt_txt = f" · kpt_shape: {kpt}" if kpt else ""
        self.detail_info.setText(
            f"Görev tipi: {task_label(ds.get('task_type'))}{kpt_txt}\n"
            f"Oluşturulma: {(ds.get('created_at') or '')[:19].replace('T', ' ')}"
        )
        classes = self._busy(lambda: self._ds_svc.list_classes(ds["id"])) or []
        self.class_list.clear()
        for c in classes:
            self.class_list.addItem(f"{c.get('class_index')}: {c.get('name')}")
        if not classes:
            self.class_list.addItem("(sınıf tanımlı değil)")

        self._refresh_image_count(ds["id"])
        team = self._current_team()
        can_write = team and team.get("role") in ("owner", "admin", "annotator")
        self.btn_upload.setEnabled(bool(can_write))
        self.btn_open.setEnabled(self._on_open is not None)

    def _refresh_image_count(self, dataset_id: str):
        n = self._busy(lambda: self._img_svc.count(dataset_id))
        self.img_count_label.setText(f"Görseller: {n if n is not None else '—'}")

    def _on_new_dataset(self):
        team = self._current_team()
        if not team:
            return
        dlg = _NewDatasetDialog(self)
        if not dlg.exec():
            return
        data = dlg.result_data()
        try:
            self._busy_raise(lambda: self._ds_svc.create_dataset(
                team["id"], data["name"], data["task_type"],
                kpt_shape=data["kpt_shape"], classes=data["classes"]))
        except DatasetError as exc:
            self._error(str(exc))
            return
        self._reload_datasets()
        for i in range(self.ds_list.count()):
            d = self.ds_list.item(i).data(Qt.ItemDataRole.UserRole)
            if d and d.get("name") == data["name"]:
                self.ds_list.setCurrentRow(i)
                break

    def _on_delete_dataset(self):
        row = self.ds_list.currentRow()
        if row < 0 or row >= len(self._datasets):
            return
        ds = self._datasets[row]
        if QMessageBox.question(
            self, "Dataset Sil",
            f"'{ds['name']}' datasetini silmek istediğinize emin misiniz?\n"
            "Bu işlem geri alınamaz."
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._busy_raise(lambda: self._ds_svc.delete_dataset(ds["id"]))
        except DatasetError as exc:
            self._error(str(exc))
            return
        self._reload_datasets()

    def _on_open_dataset_clicked(self):
        row = self.ds_list.currentRow()
        if row < 0 or row >= len(self._datasets) or self._on_open is None:
            return
        ds = self._datasets[row]
        # Diyaloğu kapat ve açma işlemini ana pencereye devret
        self.accept()
        self._on_open(ds)

    # ─── Görsel yükleme ────────────────────────────────────────────────────
    def _on_upload_images(self):
        row = self.ds_list.currentRow()
        if row < 0 or row >= len(self._datasets):
            return
        ds = self._datasets[row]

        folder = QFileDialog.getExistingDirectory(self, "Görsel Klasörü Seç")
        if not folder:
            return

        exts = {e.lower() for e in SUPPORTED_IMAGE_FORMATS}
        from pathlib import Path
        from src.widgets.upload_worker import resolve_split_label
        files = [p for p in Path(folder).rglob("*")
                 if p.is_file() and p.suffix.lower() in exts]
        # YOLO labels/ klasörü içindeki .txt'ler görsel değildir; zaten exts filtreliyor.
        if not files:
            self._error("Seçilen klasörde desteklenen görsel bulunamadı.")
            return

        # Her görsel için split + etiket dosyasını çöz (YOLO yapısından)
        items = []
        labeled = 0
        for fp in files:
            split, lbl = resolve_split_label(fp)
            if lbl:
                labeled += 1
            items.append({"path": fp, "split": split, "label_path": lbl})

        if QMessageBox.question(
            self, "Görselleri Yükle",
            f"{len(files)} görsel '{ds['name']}' datasetine yüklenecek "
            f"({labeled} tanesinin etiketi bulundu). Devam edilsin mi?"
        ) != QMessageBox.StandardButton.Yes:
            return

        # Mevcut görseller (tekrar PUT atlamak için)
        existing = {}
        try:
            for r in self._img_svc.list_images(ds["id"]):
                existing[r["filename"]] = r
        except Exception:
            existing = {}

        progress = QProgressDialog("Görseller yükleniyor...", "İptal", 0, len(items), self)
        progress.setWindowTitle("Yükleme")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        worker = UploadWorker(ds["id"], items, self._storage, self._img_svc,
                              existing=existing, max_workers=16, parent=self)
        self._upload_worker = worker

        def on_progress(done, total, name):
            progress.setMaximum(total)
            progress.setValue(done)
            progress.setLabelText(f"Yükleniyor ({done}/{total}):\n{name}")
            if progress.wasCanceled():
                worker.requestInterruption()

        def on_done(uploaded, failed):
            was_cancel = progress.wasCanceled()
            progress.close()
            self._upload_worker = None
            self._refresh_image_count(ds["id"])
            if was_cancel:
                QMessageBox.information(
                    self, "İptal Edildi",
                    "Yükleme iptal edildi; bu partiden hiçbir görsel datasete eklenmedi.")
                return
            msg = f"{uploaded} görsel yüklendi."
            if failed:
                msg += f" {failed} başarısız."
            QMessageBox.information(self, "Yükleme Tamamlandı", msg)

        worker.progress.connect(on_progress)
        worker.done.connect(on_done)
        worker.failed.connect(lambda m: (progress.close(), self._error(m)))
        worker.start()

    # ─── Yardımcılar ───────────────────────────────────────────────────────
    def _update_buttons(self):
        team = self._current_team()
        role = team.get("role") if team else None
        can_create = role in ("owner", "admin", "annotator")
        can_delete = role in ("owner", "admin")
        self.btn_new.setEnabled(bool(can_create))
        self.btn_del.setEnabled(bool(can_delete))

    def _clear_detail(self):
        self.detail_header.setText("Bir dataset seçin")
        self.detail_info.setText("")
        self.class_list.clear()
        self.img_count_label.setText("Görseller: —")
        self.btn_upload.setEnabled(False)
        self.btn_open.setEnabled(False)

    def _busy(self, fn: Callable):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return fn()
        except (DatasetError, Exception) as exc:
            self._error(f"{exc}")
            return None
        finally:
            QApplication.restoreOverrideCursor()

    def _busy_raise(self, fn: Callable):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return fn()
        finally:
            QApplication.restoreOverrideCursor()

    def _error(self, msg: str):
        QMessageBox.warning(self, "Hata", msg)


class _NewDatasetDialog(QDialog):
    """Yeni dataset olusturma alt-diyalogu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yeni Dataset")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("dataset adı")
        form.addRow("Ad:", self.name_edit)

        self.task_combo = QComboBox()
        for label, value in TASK_TYPES:
            self.task_combo.addItem(label, value)
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        form.addRow("Görev tipi:", self.task_combo)

        # kpt_shape (yalnizca keypoints)
        self.kpt_box = QGroupBox("Keypoint şekli (kpt_shape)")
        kl = QHBoxLayout(self.kpt_box)
        self.kpt_count = QSpinBox()
        self.kpt_count.setRange(1, 1000)
        self.kpt_count.setValue(17)
        self.kpt_dims = QSpinBox()
        self.kpt_dims.setRange(2, 3)
        self.kpt_dims.setValue(3)
        kl.addWidget(QLabel("Sayı:"))
        kl.addWidget(self.kpt_count)
        kl.addWidget(QLabel("Boyut:"))
        kl.addWidget(self.kpt_dims)
        kl.addStretch(1)
        form.addRow(self.kpt_box)

        layout.addLayout(form)

        layout.addWidget(QLabel("Sınıflar (her satıra bir isim, opsiyonel):"))
        self.classes_edit = QPlainTextEdit()
        self.classes_edit.setPlaceholderText("kisi\naraba\nkopek")
        self.classes_edit.setMaximumHeight(120)
        layout.addWidget(self.classes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_task_changed(0)

    def _on_task_changed(self, _idx: int):
        is_kpt = self.task_combo.currentData() == "keypoints"
        self.kpt_box.setVisible(is_kpt)

    def _on_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Eksik", "Dataset adı gerekli.")
            return
        self.accept()

    def result_data(self) -> dict:
        classes = [
            line.strip()
            for line in self.classes_edit.toPlainText().splitlines()
            if line.strip()
        ]
        kpt = None
        if self.task_combo.currentData() == "keypoints":
            kpt = [self.kpt_count.value(), self.kpt_dims.value()]
        return {
            "name": self.name_edit.text().strip(),
            "task_type": self.task_combo.currentData(),
            "kpt_shape": kpt,
            "classes": classes,
        }
