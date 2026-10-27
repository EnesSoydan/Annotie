"""Otomatik etiketleme akisi: Modellerim, ayarlar -> onizleme -> kabul.

Kabul edilen tahminler mevcut kayit yolundan gecer: image.annotations
guncellenir, ds_ctrl uzerinden yazilir; `image_saved` sinyali ekip
datasetlerinde AccountController'in bulut senkronunu tetikler.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from src.inference.merge import finalize_predictions, merge_annotations, resolve_mapping
from src.utils.colors import get_class_color

CLOUD_SYNC_PARALLEL = 6


class AutoLabelController(QObject):
    def __init__(self, main_window, account_ctrl):
        super().__init__(main_window)
        self.mw = main_window
        self.account = account_ctrl
        self._apply_queue: deque = deque()
        self._apply_progress: Optional[QProgressDialog] = None
        self._apply_total = 0
        self._apply_timer = QTimer(self)
        self._apply_timer.setInterval(60)
        self._apply_timer.timeout.connect(self._apply_tick)

    # ─── Modellerim ────────────────────────────────────────────────────────
    def open_models(self):
        if not self.account.is_authenticated():
            return
        from src.widgets.models_dialog import ModelsDialog
        ModelsDialog(self.account.current_user().id, self.mw).exec()

    # ─── Otomatik etiketleme ───────────────────────────────────────────────
    def start(self):
        if not self.account.is_authenticated():
            return
        if self._apply_timer.isActive():
            QMessageBox.information(self.mw, "Otomatik Etiketle",
                                    "Önceki otomatik etiketler hâlâ kaydediliyor.")
            return
        dataset = self.mw.ds_ctrl.dataset
        if dataset is None or not dataset.image_count:
            QMessageBox.information(self.mw, "Otomatik Etiketle",
                                    "Önce bir klasör veya dataset açın.")
            return

        from src.cloud.models import ModelService
        from src.widgets.models_dialog import run_with_progress
        svc = ModelService(self.account.current_user().id,
                           storage=self.account.cloud_storage_client())
        run_with_progress(self.mw, "Modeller alınıyor...", svc.list_models,
                          lambda models: self._with_models(svc, dataset, models))

    def _with_models(self, svc, dataset, models):
        if not models:
            if QMessageBox.question(
                    self.mw, "Model yok",
                    "Hesabınızda kayıtlı model yok. Şimdi bir model yüklemek ister misiniz?",
            ) == QMessageBox.StandardButton.Yes:
                self.open_models()
            return

        from src.widgets.autolabel_setup_dialog import (
            AutoLabelSetupDialog, SCOPE_ALL, SCOPE_UNLABELED,
        )
        setup = AutoLabelSetupDialog(models, dataset, self.mw)
        if not setup.exec():
            return
        model = setup.selected_model
        ds_names = [c.name for c in dataset.classes]
        id_map, new_names = resolve_mapping(setup.mapping, ds_names)
        if not id_map:
            QMessageBox.warning(self.mw, "Otomatik Etiketle",
                                "Tüm model sınıfları 'Yoksay' olarak seçili; "
                                "en az bir sınıfı eşleyin.")
            return

        # Kaydedilmemis degisiklikler onizlemede de gorunsun, sonra cakismasin
        self.mw.ann_ctrl._flush_save()

        scope = setup.scope
        images = self.mw.ds_ctrl.get_image_list() or dataset.get_all_images()
        if scope == SCOPE_UNLABELED:
            images = [im for im in images if not im.has_labels]
        elif scope != SCOPE_ALL:
            images = [im for im in images if im.split == scope]
        if not images:
            QMessageBox.information(self.mw, "Otomatik Etiketle", "Kapsamda görsel yok.")
            return

        storage = self.account.cloud_storage_client()
        items = [(str(im.path), im.path, self.account.cloud_content_hash(im)) for im in images]

        from src.widgets.autolabel_worker import AutoLabelWorker
        from src.widgets.autolabel_preview_dialog import AutoLabelPreviewDialog
        worker = AutoLabelWorker(lambda: svc.ensure_local(model), items, storage=storage,
                                 conf=0.05, iou=setup.iou, parent=self)

        names = ds_names + new_names
        colors = [c.color for c in dataset.classes] + [
            get_class_color(len(ds_names) + i) for i in range(len(new_names))]

        preview = AutoLabelPreviewDialog(
            images, worker, self._preview_path, id_map, names, colors,
            dataset.task_type, setup.conf, model.get("name", "model"), self.mw)
        accepted = preview.exec()
        worker.wait()
        worker.deleteLater()
        if not accepted or not preview.accepted_mode:
            self.mw.status_bar.showMessage("Otomatik etiketleme reddedildi; değişiklik yapılmadı.", 5000)
            return
        self._apply(dataset, images, preview, preview.accepted_mode,
                    len(ds_names), new_names)

    def _preview_path(self, image) -> Optional[Path]:
        if image.path.exists():
            return image.path
        h = self.account.cloud_content_hash(image)
        storage = self.account.cloud_storage_client()
        return storage.cached_path(h) if h and storage else None

    # ─── Kabul ─────────────────────────────────────────────────────────────
    def _apply(self, dataset, images, preview, mode, base_count, new_names):
        # Her gorselin nihai etiket listesini hazirla
        planned = []
        used_new = set()
        for image in images:
            key = str(image.path)
            if key not in preview._preds:
                continue
            image.load_pending_labels()
            new = preview.predictions_for(key)
            merged = merge_annotations(image.annotations, new, mode)
            if merged is None:
                continue
            planned.append((image, merged))
            used_new.update(a.class_id for a in new if a.class_id >= base_count)
        if not planned:
            return

        # Yalnizca kullanilan yeni siniflari ekle; id'leri sikistir
        remap = {}
        for i, name in enumerate(new_names):
            old_id = base_count + i
            if old_id in used_new:
                cls = self.mw.class_panel.add_class_programmatic(name)
                remap[old_id] = cls.id if cls else old_id
        for _image, anns in planned:
            for a in anns:
                if a.class_id in remap:
                    a.class_id = remap[a.class_id]

        for image, anns in planned:
            image.annotations = anns
            image.mark_dirty()

        self._apply_queue = deque(im for im, _ in planned)
        self._apply_total = len(planned)
        self._apply_cloud = self.account.is_cloud_dataset_active()
        self._apply_progress = QProgressDialog("Otomatik etiketler kaydediliyor...", None,
                                               0, self._apply_total, self.mw)
        self._apply_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._apply_progress.setMinimumDuration(300)
        self._apply_progress.setCancelButton(None)
        self._apply_timer.start()

    def _apply_tick(self):
        """Gorselleri parca parca yazar; bulut datasetinde es zamanli senkronu sinirlar."""
        budget = 50
        if self._apply_cloud:
            budget = max(0, CLOUD_SYNC_PARALLEL - self.account.cloud_sync_inflight())
        while budget > 0 and self._apply_queue:
            image = self._apply_queue.popleft()
            self.mw.ds_ctrl._write_image_labels(image)
            self.mw.image_list_panel.refresh_item(image)
            budget -= 1
        done = self._apply_total - len(self._apply_queue)
        if self._apply_progress:
            self._apply_progress.setValue(done)
        if self._apply_queue:
            return
        self._apply_timer.stop()
        if self._apply_progress:
            self._apply_progress.close()
            self._apply_progress = None
        self.mw.ds_ctrl.save_all()  # data.yaml (yeni siniflar) + kalan dirty gorseller
        current = self.mw.ann_ctrl._current_image
        if current is not None:
            self.mw.ann_ctrl.set_current_image(current)
        self.mw.status_bar.showMessage(
            f"Otomatik etiketler {self._apply_total} görsele kaydedildi.", 6000)
