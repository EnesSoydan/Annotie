"""Görsel import diyalogu — split seçimi ve Ekle/Yaz modu."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QPushButton, QDialogButtonBox, QFileDialog,
    QRadioButton, QLabel, QComboBox
)
from PySide6.QtCore import Qt


SPLIT_OPTIONS = [
    ("auto",       "Otomatik (klasör adına göre)"),
    ("train",      "Eğitim"),
    ("val",        "Doğrulama"),
    ("test",       "Test"),
    ("unassigned", "Atanmamış"),
]


class ImportDialog(QDialog):
    """Görsel import parametrelerini toplayan diyalog."""

    def __init__(self, default_split: str = "unassigned", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Görsel İmport Et")
        self.setMinimumWidth(440)
        self._folder = ""
        self._split  = default_split
        self._mode   = "add"
        self._setup_ui(default_split)

    def _setup_ui(self, default_split: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Kaynak klasör ─────────────────────────────────────────────────────
        folder_group = QGroupBox("Kaynak Klasör")
        folder_layout = QHBoxLayout(folder_group)
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Görsel klasörünü seçin...")
        folder_layout.addWidget(self._path_edit)
        btn_browse = QPushButton("Seç...")
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._browse)
        folder_layout.addWidget(btn_browse)
        layout.addWidget(folder_group)

        # ── Hedef split ───────────────────────────────────────────────────────
        split_group = QGroupBox("Hedef Split")
        split_form = QFormLayout(split_group)
        self._split_combo = QComboBox()
        for val, label in SPLIT_OPTIONS:
            self._split_combo.addItem(label, val)
        # Varsayılan değeri ayarla
        for i in range(self._split_combo.count()):
            if self._split_combo.itemData(i) == default_split:
                self._split_combo.setCurrentIndex(i)
                break
        split_form.addRow("Split:", self._split_combo)
        layout.addWidget(split_group)

        # ── Import modu ────────────────────────────────────────────────────────
        mode_group = QGroupBox("Import Modu")
        mode_layout = QVBoxLayout(mode_group)

        self._btn_add = QRadioButton("Ekle  —  Mevcut görseller korunur, yeniler eklenir")
        self._btn_add.setChecked(True)
        mode_layout.addWidget(self._btn_add)

        self._btn_replace = QRadioButton(
            "Yaz  —  Hedef split'teki görseller silinir, sadece yeni görseller kalır"
        )
        mode_layout.addWidget(self._btn_replace)

        hint = QLabel(
            "<small style='color:#888'>Not: 'Yaz' modu yalnızca seçili split'i etkiler.</small>"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        mode_layout.addWidget(hint)
        layout.addWidget(mode_group)

        # ── Butonlar ──────────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("İmport Et")
        btns.accepted.connect(self._validate_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Görsel Klasörü Seç")
        if folder:
            self._path_edit.setText(folder)
            self._folder = folder

    def _validate_accept(self):
        self._folder = self._path_edit.text().strip()
        if not self._folder:
            return
        self._split = self._split_combo.currentData()
        self._mode  = "add" if self._btn_add.isChecked() else "replace"
        self.accept()

    # ── Getters ───────────────────────────────────────────────────────────────

    def get_folder(self) -> str:
        return self._folder

    def get_split(self) -> str:
        return self._split

    def get_mode(self) -> str:
        return self._mode
