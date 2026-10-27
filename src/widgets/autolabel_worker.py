"""Otomatik etiketleme worker'i — modeli hazirlar ve gorselleri sirayla tahmin eder.

Sonuclar gorsel gorsel `image_done` ile akar; onizleme cikarim bitmeden
gezilebilir. Ekip datasetlerinde diskte olmayan gorseller R2 blob cache'inden
okunur (dataset klasorune kopyalanmaz). requestInterruption() ile iptal edilir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal


class AutoLabelWorker(QThread):
    stage = Signal(str)                # durum metni
    progress = Signal(int, int)        # islenen, toplam
    image_done = Signal(str, object)   # (gorsel anahtari, list[Prediction])
    image_failed = Signal(str, str)    # (gorsel anahtari, hata)
    finished_ok = Signal(bool)         # iptal edildi mi
    failed = Signal(str)               # olumcul hata

    def __init__(self, model_path_fn: Callable[[], Path],
                 items: List[Tuple[str, Path, Optional[str]]],
                 storage=None, conf: float = 0.05, iou: float = 0.45, parent=None):
        """items: [(anahtar, yerel_yol, bulut_content_hash|None), ...]"""
        super().__init__(parent)
        self._model_path_fn = model_path_fn
        self._items = items
        self._storage = storage
        self._conf = conf
        self._iou = iou

    def _resolve(self, path: Path, content_hash: Optional[str]) -> Path:
        if path.exists() or not content_hash or self._storage is None:
            return path
        return self._storage.download_to_cache(content_hash)

    def run(self):
        from src.inference import load_predictor
        try:
            self.stage.emit("Model hazırlanıyor...")
            predictor = load_predictor(self._model_path_fn())
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        total = len(self._items)
        self.stage.emit("Tahmin ediliyor...")
        self.progress.emit(0, total)
        try:
            for i, (key, path, content_hash) in enumerate(self._items, 1):
                if self.isInterruptionRequested():
                    self.finished_ok.emit(True)
                    return
                try:
                    preds = predictor.predict(self._resolve(Path(path), content_hash),
                                              self._conf, self._iou)
                    self.image_done.emit(key, preds)
                except Exception as exc:
                    self.image_failed.emit(key, str(exc))
                self.progress.emit(i, total)
        finally:
            predictor.close()
        self.finished_ok.emit(False)
