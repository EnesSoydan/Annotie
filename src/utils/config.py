"""Uygulama ayarlari (QSettings wrapper)."""

from PySide6.QtCore import QSettings
from src.utils.constants import (
    APP_NAME, ORG_NAME, DEFAULT_AUTOSAVE_INTERVAL, DEFAULT_IMAGE_CACHE_SIZE
)


class AppConfig:
    """Kalici uygulama ayarlarini yonetir."""

    def __init__(self):
        self._settings = QSettings(ORG_NAME, APP_NAME)

    # --- Otomatik kaydetme ---
    @property
    def autosave_enabled(self) -> bool:
        return self._settings.value("autosave/enabled", True, type=bool)

    @autosave_enabled.setter
    def autosave_enabled(self, value: bool):
        self._settings.setValue("autosave/enabled", value)

    @property
    def autosave_interval(self) -> int:
        return self._settings.value("autosave/interval", DEFAULT_AUTOSAVE_INTERVAL, type=int)

    @autosave_interval.setter
    def autosave_interval(self, value: int):
        self._settings.setValue("autosave/interval", value)

    @property
    def instant_save_enabled(self) -> bool:
        return self._settings.value("autosave/instant", True, type=bool)

    @instant_save_enabled.setter
    def instant_save_enabled(self, value: bool):
        self._settings.setValue("autosave/instant", value)

    # --- Canvas ---
    @property
    def canvas_bg_color(self) -> str:
        return self._settings.value("canvas/bg_color", "#2b2b2b")

    @canvas_bg_color.setter
    def canvas_bg_color(self, value: str):
        self._settings.setValue("canvas/bg_color", value)

    @property
    def show_crosshair(self) -> bool:
        return self._settings.value("canvas/crosshair", True, type=bool)

    @show_crosshair.setter
    def show_crosshair(self, value: bool):
        self._settings.setValue("canvas/crosshair", value)

    @property
    def image_cache_size(self) -> int:
        return self._settings.value("canvas/cache_size", DEFAULT_IMAGE_CACHE_SIZE, type=int)

    @image_cache_size.setter
    def image_cache_size(self, value: int):
        self._settings.setValue("canvas/cache_size", value)

    # --- Son acilan dosyalar ---
    @property
    def recent_files(self) -> list:
        return self._settings.value("recent_files", [], type=list)

    @recent_files.setter
    def recent_files(self, value: list):
        self._settings.setValue("recent_files", value[:10])

    def add_recent_file(self, path: str):
        files = self.recent_files
        if path in files:
            files.remove(path)
        files.insert(0, path)
        self.recent_files = files

    # --- Pencere durumu ---
    def save_window_state(self, geometry, state):
        self._settings.setValue("window/geometry", geometry)
        self._settings.setValue("window/state", state)

    def load_window_geometry(self):
        return self._settings.value("window/geometry")

    def load_window_state(self):
        return self._settings.value("window/state")
