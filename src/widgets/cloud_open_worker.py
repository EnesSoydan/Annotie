"""Ekip datasetini yerel olarak hazırlama worker'ı — Faz 6.

Ekip datasetini standart YOLO klasör yapısına (images/ + labels/ + data.yaml)
'materialize' eder: görselleri R2'den PARALEL indirir, v2 annotation satırlarını
labels/*.txt ve .annotie kimlik metadata'sı olarak yazar. Sonra mevcut editör bu
klasörü normal yerel dataset gibi açar. Qt thread; UI donmaz.
"""

from __future__ import annotations

import concurrent.futures
import shutil
from pathlib import Path

import yaml
from PySide6.QtCore import QThread, Signal


class CloudDatasetOpenWorker(QThread):
    progress = Signal(int, int, str)   # done, total, filename
    done = Signal(str, object, object)  # local_dir, filename->id, image_id->annotations
    failed = Signal(str)

    def __init__(self, dataset_meta, images, classes, storage, dest_dir,
                 annotations_by_image=None,
                 annotation_service=None,
                 download_images: bool = True, max_workers: int = 16, parent=None):
        super().__init__(parent)
        self._meta = dataset_meta
        self._images = images
        self._classes = classes
        self._storage = storage
        self._dest = Path(dest_dir)
        self._annotations_by_image = annotations_by_image
        self._annotation_service = annotation_service
        self._download = download_images   # False → lazy (görseller sonradan)
        self._max_workers = max_workers

    def run(self):
        try:
            if self._annotations_by_image is None and self._annotation_service is not None:
                self._annotations_by_image = self._annotation_service.ensure_dataset_v2(
                    self._meta, self._images
                )
                self._meta["collab_schema_version"] = 2

            images_dir = self._dest / "images"
            labels_dir = self._dest / "labels"
            images_dir.mkdir(parents=True, exist_ok=True)
            labels_dir.mkdir(parents=True, exist_ok=True)

            self._write_yaml()

            # Etiketleri yaz (yerel, hızlı) + filename→id eşleşmesi
            mapping = {}
            for img in self._images:
                mapping[img["filename"]] = img["id"]
                stem = Path(img["filename"]).stem
                lbl = labels_dir / (stem + ".txt")
                if self._annotations_by_image is not None:
                    from src.cloud.annotations import materialize_cloud_annotations

                    records = self._annotations_by_image.get(str(img["id"]), [])
                    if not materialize_cloud_annotations(self._dest, lbl, records):
                        raise RuntimeError(f"Etiket hazırlanamadı: {img['filename']}")
                else:
                    content = (img.get("label_content") or "")
                    if content.strip():
                        lbl.write_text(content, encoding="utf-8")
                    elif lbl.exists():
                        # DB'de etiket boşsa eski yerel etiketi temizle
                        try:
                            lbl.unlink()
                        except OSError:
                            pass

            # Lazy mod: görselleri şimdi indirme (gerektiğinde inecek)
            if not self._download:
                self.done.emit(str(self._dest), mapping, self._annotations_by_image or {})
                return

            # Görselleri paralel indir
            total = len(self._images)
            done_count = 0
            cancelled = False
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers)
            futures = {
                executor.submit(self._fetch_one, img, images_dir): img
                for img in self._images
            }
            try:
                for fut in concurrent.futures.as_completed(futures):
                    if self.isInterruptionRequested():
                        cancelled = True
                        break
                    img = futures[fut]
                    try:
                        fut.result()
                    except Exception:
                        pass  # tek görsel inemezse atla (editör eksiğini gösterir)
                    done_count += 1
                    self.progress.emit(done_count, total, img["filename"])
            finally:
                executor.shutdown(wait=not cancelled, cancel_futures=True)

            if cancelled:
                self.failed.emit("İptal edildi.")
                return

            self.done.emit(str(self._dest), mapping, self._annotations_by_image or {})
        except Exception as exc:
            self.failed.emit(f"Dataset hazırlanamadı: {exc}")

    def _fetch_one(self, img, images_dir: Path):
        dest_path = images_dir / img["filename"]
        if dest_path.exists():
            return  # zaten var (cache)
        blob = self._storage.download_to_cache(img["content_hash"])
        shutil.copyfile(blob, dest_path)

    def _write_yaml(self):
        names = {}
        for c in sorted(self._classes, key=lambda x: x.get("class_index", 0)):
            names[int(c["class_index"])] = c["name"]
        data = {"names": names}
        kpt = self._meta.get("kpt_shape")
        if kpt:
            data["kpt_shape"] = list(kpt)
        (self._dest / "data.yaml").write_text(
            yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
