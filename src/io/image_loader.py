"""Async gorsel yukleme ve LRU onbellegi."""

from pathlib import Path
from collections import OrderedDict
from PySide6.QtGui import QPixmap
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, QMutex


class ImageLoader(QObject):
    """Arka planda gorsel yukleyen ve LRU onbellekte tutan sinif."""

    image_loaded = Signal(str, object)  # (path_str, QPixmap)

    def __init__(self, cache_size: int = 50, parent=None):
        super().__init__(parent)
        self._cache: OrderedDict = OrderedDict()
        self._cache_size = cache_size
        self._mutex = QMutex()
        self._pool = QThreadPool.globalInstance()

    def load(self, path: str, callback=None):
        """Gorseli asenkron olarak yukler. Onbellekte varsa aninda doner."""
        cached = self._get_cached(path)
        if cached:
            if callback:
                callback(cached)
            return

        task = _LoadTask(path, self._on_loaded)
        self._pool.start(task)

    def load_sync(self, path: str) -> QPixmap:
        """Gorseli senkron olarak yukler."""
        cached = self._get_cached(path)
        if cached:
            return cached
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self._put_cache(path, pixmap)
        return pixmap

    def _on_loaded(self, path: str, pixmap: QPixmap):
        if not pixmap.isNull():
            self._put_cache(path, pixmap)
        self.image_loaded.emit(path, pixmap)

    def _get_cached(self, path: str):
        self._mutex.lock()
        try:
            if path in self._cache:
                self._cache.move_to_end(path)
                return self._cache[path]
        finally:
            self._mutex.unlock()
        return None

    def _put_cache(self, path: str, pixmap: QPixmap):
        self._mutex.lock()
        try:
            if path in self._cache:
                self._cache.move_to_end(path)
            else:
                self._cache[path] = pixmap
                if len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        finally:
            self._mutex.unlock()

    def clear_cache(self):
        self._mutex.lock()
        try:
            self._cache.clear()
        finally:
            self._mutex.unlock()

    def set_cache_size(self, size: int):
        self._cache_size = size


class _LoadTask(QRunnable):
    """Arka planda gorsel yukleyen gorev."""

    def __init__(self, path: str, callback):
        super().__init__()
        self._path = path
        self._callback = callback
        self.setAutoDelete(True)

    def run(self):
        pixmap = QPixmap(self._path)
        self._callback(self._path, pixmap)
