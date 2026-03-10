"""Görsel listesi dock paneli — split tabları ve import desteği."""

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLineEdit, QLabel,
    QPushButton, QMenu, QButtonGroup, QAbstractButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


SPLIT_COLORS = {
    "train":      "#4caf50",
    "val":        "#2196f3",
    "test":       "#ff9800",
    "unassigned": "#757575",
}
SPLIT_LABELS = {
    "train":      "E",
    "val":        "D",
    "test":       "T",
    "unassigned": "-",
}
SPLIT_NAMES = [
    ("all",        "Tümü"),
    ("train",      "Eğitim"),
    ("val",        "Doğrulama"),
    ("test",       "Test"),
    ("unassigned", "Atanmamış"),
]


class ImageListPanel(QDockWidget):
    """Sol dock: split tabları + görsel listesi + import butonu."""

    image_selected  = Signal(object)   # ImageItem
    import_requested = Signal(str)     # split adı ("train", "val", "test", "unassigned", "all")

    def __init__(self, parent=None):
        super().__init__("Görseller", parent)
        self._images = []
        self._all_items = []
        self._active_split = "all"
        self._setup_ui()

    # ── UI kurulum ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ── Split tab butonları ───────────────────────────────────────────────
        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(2)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_btns = {}

        for split, label in SPLIT_NAMES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(22)
            btn.setStyleSheet("""
                QPushButton {
                    background: #3c3c3c; color: #aaa; border: 1px solid #555;
                    border-radius: 3px; font-size: 11px; padding: 0 5px;
                }
                QPushButton:checked {
                    background: #094771; color: #fff; border-color: #1177bb;
                }
                QPushButton:hover:!checked { background: #4a4a4a; }
            """)
            btn.clicked.connect(lambda checked=False, s=split: self._on_tab_clicked(s))
            self._tab_group.addButton(btn)
            tab_layout.addWidget(btn)
            self._tab_btns[split] = btn

        self._tab_btns["all"].setChecked(True)
        main_layout.addLayout(tab_layout)

        # ── Arama kutusu ─────────────────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setPlaceholderText("Ara...")
        self._search.textChanged.connect(self._filter)
        main_layout.addWidget(self._search)

        # ── Sayaç etiketi ─────────────────────────────────────────────────────
        self._count_label = QLabel("0 görsel")
        self._count_label.setStyleSheet("color: #888; font-size: 11px;")
        main_layout.addWidget(self._count_label)

        # ── Görsel listesi ────────────────────────────────────────────────────
        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        self._list.setSpacing(1)
        main_layout.addWidget(self._list, stretch=1)

        # ── Import butonu ─────────────────────────────────────────────────────
        self._btn_import = QPushButton("+ İmport Et")
        self._btn_import.setToolTip(
            "Seçili split'e görsel ekle/yaz\n"
            "Sağ tık → sadece belirli split için"
        )
        self._btn_import.clicked.connect(self._on_import_clicked)
        self._btn_import.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn_import.customContextMenuRequested.connect(self._show_import_menu)
        main_layout.addWidget(self._btn_import)

        self.setWidget(container)
        self.setMinimumWidth(210)

    # ── Veri yükleme ──────────────────────────────────────────────────────────

    def load_images(self, images: list):
        """Görsel listesini yükler."""
        self._images = images
        self._list.clear()
        self._all_items = []

        for img in images:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, img)
            self._update_item_text(item, img)
            self._list.addItem(item)
            self._all_items.append(item)

        self._apply_filter()
        self._refresh_tab_counts()

    def _update_item_text(self, item: QListWidgetItem, img):
        split = img.split
        label = SPLIT_LABELS.get(split, "-")
        ann_count = len(img.annotations)
        text = f"[{label}] {img.filename}"
        if ann_count > 0:
            text += f"  ({ann_count})"
        item.setText(text)
        item.setForeground(QColor(204, 204, 204))

    def refresh_item(self, image_item):
        """Belirli bir görselin satırını günceller."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) is image_item:
                self._update_item_text(item, image_item)
                break
        self._refresh_tab_counts()

    def select_image(self, image_item):
        """Belirli bir görseli seçili yapar (görünür olmayan ise tümü tabına geçer)."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) is image_item:
                if item.isHidden():
                    # Başka bir tab'da, tümüne geç
                    self._switch_tab("all")
                self._list.setCurrentItem(item)
                self._list.scrollToItem(item)
                break

    # ── Tab yönetimi ──────────────────────────────────────────────────────────

    def _on_tab_clicked(self, split: str):
        self._switch_tab(split)

    def _switch_tab(self, split: str):
        self._active_split = split
        if split in self._tab_btns:
            self._tab_btns[split].setChecked(True)
        self._apply_filter()

    def _apply_filter(self):
        """Aktif tab ve arama metnine göre listeyi filtreler."""
        search = self._search.text().lower()
        visible_count = 0
        for item in self._all_items:
            img = item.data(Qt.ItemDataRole.UserRole)
            split_ok = (self._active_split == "all" or img.split == self._active_split)
            search_ok = (not search or search in img.filename.lower())
            hidden = not (split_ok and search_ok)
            item.setHidden(hidden)
            if not hidden:
                visible_count += 1
        self._count_label.setText(f"{visible_count} görsel")

    def _filter(self, text: str):
        """Arama kutusuna göre filtrele."""
        self._apply_filter()

    def _refresh_tab_counts(self):
        """Tab butonlarının üstündeki sayıları günceller."""
        counts = {"all": 0, "train": 0, "val": 0, "test": 0, "unassigned": 0}
        for img in self._images:
            counts["all"] += 1
            if img.split in counts:
                counts[img.split] += 1

        labels = {"all": "Tümü", "train": "Eğitim", "val": "Doğrulama",
                  "test": "Test", "unassigned": "Atanmamış"}
        for split, btn in self._tab_btns.items():
            n = counts.get(split, 0)
            btn.setText(f"{labels[split]} ({n})" if n > 0 else labels[split])

    # ── Seçim olayı ───────────────────────────────────────────────────────────

    def _on_selection_changed(self, current, previous):
        if current:
            img = current.data(Qt.ItemDataRole.UserRole)
            if img:
                self.image_selected.emit(img)

    # ── Sağ tık menüsü (görsel üzerinde) ─────────────────────────────────────

    def _show_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        img = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addSection("Split Ata")
        for split, label in [("train", "Eğitim"), ("val", "Doğrulama"),
                              ("test", "Test"), ("unassigned", "Atanmamış")]:
            action = menu.addAction(f"{label} olarak ata")
            action.triggered.connect(lambda checked=False, s=split, i=img: self._set_split(i, s))
        menu.exec(self._list.viewport().mapToGlobal(pos))

    def _set_split(self, image_item, split: str):
        image_item.split = split
        image_item.mark_dirty()
        self.refresh_item(image_item)
        self._apply_filter()

    # ── Import butonu ─────────────────────────────────────────────────────────

    def _on_import_clicked(self):
        """Aktif tab'ın split'i ile import sinyali gönderir."""
        self.import_requested.emit(self._active_split)

    def _show_import_menu(self, pos):
        """Import butonuna sağ tık → split seçimi."""
        menu = QMenu(self)
        for split, label in [("all", "Tümü (otomatik)"), ("train", "Eğitim"),
                              ("val", "Doğrulama"), ("test", "Test"),
                              ("unassigned", "Atanmamış")]:
            action = menu.addAction(f"{label} için İmport Et")
            action.triggered.connect(lambda checked=False, s=split: self.import_requested.emit(s))
        menu.exec(self._btn_import.mapToGlobal(pos))
