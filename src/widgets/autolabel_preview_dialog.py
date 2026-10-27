"""Otomatik etiketleme onizlemesi.

Ayri pencere; ana canvas'a ve dataset'e dokunmaz. Cikarim arka planda akarken
datasetteki tum gorseller gezilebilir: mevcut etiketler gri/ince, tahminler
sinif renginde kesikli cizilir. Guven esigi kaydiriciyla canli filtrelenir.
"Kabul Et..." birlestirme modunu sorar; secim `accepted_mode` / `conf` ile
controller'a doner. "Reddet" hicbir sey yazmaz.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPixmap, QShortcut, QImageReader
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget, QListWidget,
    QListWidgetItem, QLabel, QComboBox, QSlider, QPushButton, QProgressBar,
    QGraphicsScene, QGraphicsView, QMessageBox, QRadioButton, QButtonGroup,
    QDialogButtonBox,
)

from src.inference.base import Prediction
from src.inference.merge import (
    MODE_APPEND, MODE_REPLACE, MODE_UNLABELED_ONLY, finalize_predictions, merge_annotations,
)
from src.widgets.prediction_overlay import add_annotation

FILTER_ALL, FILTER_WITH, FILTER_WITHOUT = range(3)
EXISTING_COLOR = QColor(170, 170, 170)


class _PreviewView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(40, 40, 40))
        self._fit = True

    def fit(self):
        self._fit = True
        if not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self._fit = False
        self.scale(factor, factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self.fit()


class _AcceptDialog(QDialog):
    def __init__(self, counts: Dict[str, tuple], pending: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Otomatik etiketleri kabul et")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Tahminler datasete nasıl kaydedilsin?"))
        self._group = QButtonGroup(self)
        texts = {
            MODE_APPEND: "Mevcut etiketlere ekle",
            MODE_UNLABELED_ONLY: "Sadece etiketsiz görsellere uygula",
            MODE_REPLACE: "Tahmin olan görsellerde mevcut etiketleri DEĞİŞTİR",
        }
        for i, mode in enumerate((MODE_APPEND, MODE_UNLABELED_ONLY, MODE_REPLACE)):
            imgs, anns = counts[mode]
            rb = QRadioButton(f"{texts[mode]}  —  {imgs} görsel, {anns} etiket")
            rb.setProperty("mode", mode)
            self._group.addButton(rb, i)
            lay.addWidget(rb)
            if i == 0:
                rb.setChecked(True)
        note = ("Bu işlem geri alınamaz (Geri Al geçmişine girmez). "
                "Tahmini olmayan görsellere dokunulmaz.")
        if pending:
            note = (f"Çıkarım henüz bitmedi: işlenmemiş {pending} görsel atlanacak.\n" + note)
        lbl = QLabel(note)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #b8860b;")
        lay.addWidget(lbl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Kaydet")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _accept(self):
        if self.mode == MODE_REPLACE and QMessageBox.warning(
                self, "Emin misiniz?",
                "Tahmin olan görsellerdeki mevcut etiketler silinip yerine "
                "model tahminleri yazılacak. Devam edilsin mi?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.accept()

    @property
    def mode(self) -> str:
        return self._group.checkedButton().property("mode")


class AutoLabelPreviewDialog(QDialog):
    def __init__(self, items: list, worker, resolve_path: Callable[[object], Optional[Path]],
                 id_map: Dict[int, int], class_names: List[str], class_colors: List[QColor],
                 dataset_task, conf: float, model_name: str, parent=None):
        super().__init__(parent)
        self._items = items
        self._by_key = {str(it.path): it for it in items}
        self._worker = worker
        self._resolve_path = resolve_path
        self._id_map = id_map
        self._class_names = class_names
        self._class_colors = class_colors
        self._dataset_task = dataset_task
        self._preds: Dict[str, List[Prediction]] = {}
        self._errors: Dict[str, str] = {}
        self._running = True
        self._current_key: Optional[str] = None
        self.accepted_mode: Optional[str] = None

        self.setWindowTitle(f"Otomatik Etiketleme Önizlemesi — {model_name}")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1200, 780)
        self._build(conf)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh_all)

        worker.stage.connect(self._on_stage)
        worker.progress.connect(self._on_progress)
        worker.image_done.connect(self._on_image_done)
        worker.image_failed.connect(self._on_image_failed)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self._rebuild_list()
        worker.start()

    # ─── Arayuz ────────────────────────────────────────────────────────────
    def _build(self, conf: float):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.summary = QLabel()
        top.addWidget(self.summary, 1)
        top.addWidget(QLabel("Güven eşiği:"))
        self.conf_slider = QSlider(Qt.Orientation.Horizontal)
        self.conf_slider.setRange(5, 95)
        self.conf_slider.setValue(int(round(conf * 100)))
        self.conf_slider.setFixedWidth(200)
        self.conf_slider.valueChanged.connect(self._on_conf_changed)
        top.addWidget(self.conf_slider)
        self.conf_label = QLabel()
        self.conf_label.setMinimumWidth(36)
        top.addWidget(self.conf_label)
        root.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Tüm görseller", "Tahmini olanlar", "Tahmini olmayanlar"])
        self.filter_combo.currentIndexChanged.connect(self._rebuild_list)
        ll.addWidget(self.filter_combo)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_current_changed)
        ll.addWidget(self.list, 1)
        split.addWidget(left)

        self.scene = QGraphicsScene(self)
        self.view = _PreviewView(self.scene)
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 920])
        root.addWidget(split, 1)

        legend = QLabel("Gri ince çizgi: mevcut etiketler · Renkli kesikli: model tahmini "
                        "· ←/→ ile gezin · Tekerlek ile yakınlaş, çift tık sığdır")
        legend.setStyleSheet("color: gray;")
        root.addWidget(legend)

        bottom = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m")
        bottom.addWidget(self.progress, 1)
        self.btn_stop = QPushButton("Durdur")
        self.btn_stop.clicked.connect(self._stop)
        bottom.addWidget(self.btn_stop)
        bottom.addSpacing(24)
        self.btn_reject = QPushButton("Reddet")
        self.btn_reject.clicked.connect(self.reject)
        bottom.addWidget(self.btn_reject)
        self.btn_accept = QPushButton("Kabul Et...")
        self.btn_accept.setDefault(True)
        self.btn_accept.clicked.connect(self._on_accept)
        bottom.addWidget(self.btn_accept)
        root.addLayout(bottom)

        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self._step(1))
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self._step(-1))
        self.view.mouseDoubleClickEvent = lambda _e: self.view.fit()
        self._update_conf_label()

    # ─── Yardimcilar ───────────────────────────────────────────────────────
    @property
    def conf(self) -> float:
        return self.conf_slider.value() / 100.0

    def _final_for(self, key: str) -> list:
        """(annotation, score) — kaydedilecek haliyle (esleme + donusum uygulanmis)."""
        out = []
        for p in self._preds.get(key, []):
            anns = finalize_predictions([p], self._id_map, self.conf, self._dataset_task)
            if anns:
                out.append((anns[0], p.score))
        return out

    def _count(self, key: str) -> int:
        return sum(1 for p in self._preds.get(key, [])
                   if p.score >= self.conf and p.annotation.class_id in self._id_map)

    def _item_text(self, key: str) -> str:
        name = self._by_key[key].filename
        if key in self._errors:
            return f"⚠ {name}"
        if key not in self._preds:
            return f"…  {name}"
        return f"{self._count(key):>3}  {name}"

    def _passes_filter(self, key: str) -> bool:
        f = self.filter_combo.currentIndex()
        if f == FILTER_ALL:
            return True
        if key not in self._preds:
            return False
        has = self._count(key) > 0
        return has if f == FILTER_WITH else not has

    def _rebuild_list(self):
        current = self._current_key
        self.list.blockSignals(True)
        self.list.clear()
        select_row = 0
        for it in self._items:
            key = str(it.path)
            if not self._passes_filter(key):
                continue
            li = QListWidgetItem(self._item_text(key))
            li.setData(Qt.ItemDataRole.UserRole, key)
            if key in self._errors:
                li.setToolTip(self._errors[key])
            if key == current:
                select_row = self.list.count()
            self.list.addItem(li)
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(select_row)
            if self.list.currentItem().data(Qt.ItemDataRole.UserRole) != current:
                self._on_current_changed(self.list.currentItem(), None)
        else:
            self._current_key = None
            self.scene.clear()
        self._update_summary()

    def _refresh_all(self):
        if self.filter_combo.currentIndex() != FILTER_ALL:
            self._rebuild_list()
            return
        for row in range(self.list.count()):
            li = self.list.item(row)
            li.setText(self._item_text(li.data(Qt.ItemDataRole.UserRole)))
        self._update_summary()
        self._render()

    def _update_summary(self):
        done = len(self._preds)
        total = len(self._items)
        n_preds = sum(self._count(k) for k in self._preds)
        n_imgs = sum(1 for k in self._preds if self._count(k))
        state = "" if not self._running else "  ·  çıkarım sürüyor"
        self.summary.setText(
            f"<b>{done}/{total}</b> görsel işlendi · <b>{n_preds}</b> tahmin "
            f"· <b>{n_imgs}</b> görselde tahmin var{state}")

    def _update_conf_label(self):
        self.conf_label.setText(f"{self.conf:.2f}")

    def _step(self, delta: int):
        row = self.list.currentRow() + delta
        if 0 <= row < self.list.count():
            self.list.setCurrentRow(row)

    # ─── Cizim ─────────────────────────────────────────────────────────────
    def _on_current_changed(self, current, _previous):
        self._current_key = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._render(refit=True)

    def _render(self, refit: bool = False):
        self.scene.clear()
        key = self._current_key
        if key is None:
            return
        image = self._by_key[key]
        path = self._resolve_path(image)
        pix = QPixmap()
        if path is not None:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                pix = QPixmap.fromImage(img)
        if pix.isNull():
            self.scene.addText("Görsel henüz hazır değil (çıkarım sırasında indirilecek).")
            self.scene.setSceneRect(self.scene.itemsBoundingRect())
            return
        self.scene.addPixmap(pix)
        w, h = pix.width(), pix.height()
        self.scene.setSceneRect(0, 0, w, h)

        image.load_pending_labels()
        for ann in image.annotations:
            add_annotation(self.scene, ann, w, h, EXISTING_COLOR, width=1.0)
        for ann, score in self._final_for(key):
            cid = ann.class_id
            color = self._class_colors[cid] if cid < len(self._class_colors) else QColor("red")
            name = self._class_names[cid] if cid < len(self._class_names) else str(cid)
            add_annotation(self.scene, ann, w, h, color, f"{name} {score:.2f}",
                           dashed=True, fill=True)
        if refit:
            self.view.fit()

    # ─── Worker ────────────────────────────────────────────────────────────
    def _on_stage(self, text: str):
        self.progress.setFormat(f"{text}  %v / %m")

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def _on_image_done(self, key: str, preds):
        self._preds[key] = preds
        self._schedule_item_update(key)

    def _on_image_failed(self, key: str, message: str):
        self._errors[key] = message
        self._schedule_item_update(key)

    def _schedule_item_update(self, key: str):
        if self.filter_combo.currentIndex() == FILTER_ALL:
            for row in range(self.list.count()):
                li = self.list.item(row)
                if li.data(Qt.ItemDataRole.UserRole) == key:
                    li.setText(self._item_text(key))
                    if key in self._errors:
                        li.setToolTip(self._errors[key])
                    break
            if key == self._current_key:
                self._render()
            self._update_summary()
        else:
            self._refresh_timer.start(400)

    def _on_finished(self, cancelled: bool):
        self._running = False
        self.btn_stop.setEnabled(False)
        self.progress.setFormat("Durduruldu  %v / %m" if cancelled else "Tamamlandı  %v / %m")
        self._update_summary()
        if self._errors:
            self.summary.setToolTip("\n".join(f"{Path(k).name}: {m}"
                                              for k, m in list(self._errors.items())[:20]))

    def _on_failed(self, message: str):
        self._running = False
        self.btn_stop.setEnabled(False)
        self.btn_accept.setEnabled(False)
        self.progress.setFormat("Hata")
        QMessageBox.critical(self, "Otomatik etiketleme başarısız", message)

    def _stop(self):
        if self._worker.isRunning():
            self.btn_stop.setEnabled(False)
            self._worker.requestInterruption()

    def _on_conf_changed(self, _v):
        self._update_conf_label()
        self._refresh_timer.start(120)

    # ─── Kabul / Red ───────────────────────────────────────────────────────
    def target_class_ids(self) -> set:
        """Modelin eşlendiği dataset sınıfları ("değiştir" yalnızca bunlara dokunur)."""
        return set(self._id_map.values())

    def predictions_for(self, key: str) -> list:
        return [a for a, _s in self._final_for(key)]

    def _on_accept(self):
        counts = {}
        for mode in (MODE_APPEND, MODE_UNLABELED_ONLY, MODE_REPLACE):
            imgs = anns = 0
            for key in self._preds:
                image = self._by_key[key]
                image.load_pending_labels()
                new = self.predictions_for(key)
                merged = merge_annotations(image.annotations, new, mode,
                                           replace_classes=self.target_class_ids())
                if merged is not None:
                    imgs += 1
                    anns += len(merged) - (len(image.annotations) if mode == MODE_APPEND else 0)
            counts[mode] = (imgs, anns)
        if not any(c[0] for c in counts.values()):
            QMessageBox.information(self, "Kaydedilecek tahmin yok",
                                    "Seçili eşikte kaydedilecek tahmin bulunamadı.")
            return
        pending = len(self._items) - len(self._preds) - len(self._errors)
        dlg = _AcceptDialog(counts, pending if self._running else 0, self)
        if not dlg.exec():
            return
        self.accepted_mode = dlg.mode
        self._shutdown_worker()
        self.accept()

    def _shutdown_worker(self):
        if self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(10000)

    def reject(self):
        if self._preds and QMessageBox.question(
                self, "Önizlemeyi kapat",
                "Otomatik etiketleme sonuçları kaydedilmeden kapatılsın mı?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._shutdown_worker()
        super().reject()

    def closeEvent(self, event):
        event.ignore()
        self.reject()
