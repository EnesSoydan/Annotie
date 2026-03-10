"""Otomatik kaydetme yonetimi."""

from PySide6.QtCore import QObject, QTimer
from src.utils.constants import DEFAULT_AUTOSAVE_INTERVAL


class AutosaveController(QObject):
    def __init__(self, dataset_controller, config, parent=None):
        super().__init__(parent)
        self._ds_ctrl = dataset_controller
        self._config = config
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._apply_config()

    def _apply_config(self):
        interval_ms = self._config.autosave_interval * 1000
        if self._config.autosave_enabled:
            self._timer.start(interval_ms)
        else:
            self._timer.stop()

    def _on_tick(self):
        self._ds_ctrl.save_all()

    def restart(self):
        """Ayarlar degistiginde yeniden baslat."""
        self._apply_config()

    def stop(self):
        self._timer.stop()

    def start(self):
        if self._config.autosave_enabled:
            self._timer.start(self._config.autosave_interval * 1000)
