"""Ayarlar diyalogu."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QCheckBox, QSpinBox, QLabel, QPushButton,
    QDialogButtonBox, QSlider
)
from PySide6.QtCore import Qt


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Ayarlar")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Genel
        general = QWidget()
        gform = QFormLayout(general)

        # Otomatik kaydetme
        autosave = QWidget()
        aform = QFormLayout(autosave)

        self._autosave_enabled = QCheckBox("Otomatik Kaydetmeyi Etkinleştir")
        self._autosave_enabled.setChecked(self._config.autosave_enabled)
        aform.addRow("", self._autosave_enabled)

        self._autosave_interval = QSpinBox()
        self._autosave_interval.setRange(10, 600)
        self._autosave_interval.setSuffix(" saniye")
        self._autosave_interval.setValue(self._config.autosave_interval)
        aform.addRow("Kaydetme Aralığı:", self._autosave_interval)

        self._instant_save = QCheckBox("Anlık Kaydetme (her değişiklikte)")
        self._instant_save.setChecked(self._config.instant_save_enabled)
        aform.addRow("", self._instant_save)

        tabs.addTab(autosave, "Kaydetme")

        # Canvas
        canvas = QWidget()
        cform = QFormLayout(canvas)

        self._show_crosshair = QCheckBox("Artı İşareti Göster")
        self._show_crosshair.setChecked(self._config.show_crosshair)
        cform.addRow("", self._show_crosshair)

        tabs.addTab(canvas, "Canvas")

        layout.addWidget(tabs)

        # Tamam / Iptal
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self):
        self._config.autosave_enabled = self._autosave_enabled.isChecked()
        self._config.autosave_interval = self._autosave_interval.value()
        self._config.instant_save_enabled = self._instant_save.isChecked()
        self._config.show_crosshair = self._show_crosshair.isChecked()
        self.accept()
