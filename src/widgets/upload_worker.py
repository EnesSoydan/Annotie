"""Görsel yükleme worker'ı — Faz 5/6 (paralel + etiket + split yakalama).

Görselleri R2'ye PARALEL yükler ve metadata'yı (içerik-hash, boyut, split,
YOLO etiket içeriği) toplu yazar. Metadata baytlar yüklendikten SONRA tek
seferde yazıldığından iptal edilirse datasete hiçbir görsel eklenmez.

Yerel YOLO etiketleri (labels/<stem>.txt veya görsel yanındaki .txt) ve split
(train/val/test) klasör yapısından otomatik algılanıp DB'ye taşınır.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from src.cloud.storage import sha256_bytes


def resolve_split_label(img_path: Path):
    """Görsel yoluna bakarak (split, label_path) döndürür.

    split: yol parçalarında train/val(id)/test geçiyorsa o; yoksa 'unassigned'.
    label_path: 'images' klasörü 'labels' ile değiştirilmiş .txt; yoksa görsel
                yanındaki .txt; hiçbiri yoksa None.
    """
    parts_lower = [p.lower() for p in img_path.parts]
    split = "unassigned"
    for p in parts_lower:
        if "train" in p:
            split = "train"; break
        if "val" in p:           # val, valid, validation
            split = "val"; break
        if "test" in p:
            split = "test"; break

    label = None
    pp = list(img_path.parts)
    lower = [x.lower() for x in pp]
    if "images" in lower:
        idx = lower.index("images")
        new = pp[:]
        new[idx] = "labels"
        cand = Path(*new).with_name(img_path.stem + ".txt")
        if cand.exists():
            label = cand
    if label is None:
        sib = img_path.with_suffix(".txt")
        if sib.exists():
            label = sib
    return split, label


class UploadWorker(QThread):
    progress = Signal(int, int, str)   # done, total, filename
    done = Signal(int, int)            # eklenen, basarisiz
    failed = Signal(str)               # olumcul hata

    def __init__(self, dataset_id, items, storage, images,
                 existing=None, max_workers: int = 16, parent=None):
        """items: [{path: Path, split: str, label_path: Path|None}, ...]

        existing: {filename: db_row} — aynı içerik-hash'e sahip görseller için
        R2'ye tekrar PUT yapılmaz (yalnızca metadata/etiket güncellenir).
        """
        super().__init__(parent)
        self._dataset_id = dataset_id
        self._items = items
        self._storage = storage
        self._images = images
        self._existing = existing or {}
        self._max_workers = max_workers

    def _upload_one(self, item) -> dict:
        fp = Path(item["path"])
        data = fp.read_bytes()
        content_hash = sha256_bytes(data)
        ex = self._existing.get(fp.name)
        if ex and ex.get("content_hash") == content_hash:
            # Zaten R2'de — PUT'u atla, metadata'yı mevcut satırdan al
            meta = {
                "content_hash": content_hash,
                "key": ex.get("storage_key") or f"blobs/{content_hash}",
                "width": ex.get("width"),
                "height": ex.get("height"),
                "size_bytes": ex.get("size_bytes") if ex.get("size_bytes") is not None else len(data),
            }
        else:
            meta = self._storage.upload_bytes(self._dataset_id, data)
        meta["filename"] = fp.name
        meta["split"] = item.get("split")
        content = ""
        lp = item.get("label_path")
        if lp:
            try:
                lp = Path(lp)
                if lp.exists():
                    content = lp.read_text(encoding="utf-8")
            except Exception:
                content = ""
        meta["label_content"] = content
        return meta

    def run(self):
        total = len(self._items)
        entries: list[dict] = []
        failed = 0
        done_count = 0
        cancelled = False

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers)
        futures = {executor.submit(self._upload_one, it): it for it in self._items}
        try:
            for fut in concurrent.futures.as_completed(futures):
                if self.isInterruptionRequested():
                    cancelled = True
                    break
                it = futures[fut]
                try:
                    entries.append(fut.result())
                except Exception:
                    failed += 1
                done_count += 1
                name = Path(it["path"]).name
                self.progress.emit(done_count, total, name)
        finally:
            executor.shutdown(wait=not cancelled, cancel_futures=True)

        if cancelled:
            self.done.emit(0, 0)
            return

        try:
            self._images.add_images_bulk(self._dataset_id, entries)
        except Exception as exc:
            self.failed.emit(f"Metadata kaydı başarısız: {exc}")
            return

        self.done.emit(len(entries), failed)
