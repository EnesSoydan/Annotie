"""Ana araç çubuğu - araç seçim butonları."""

from PySide6.QtWidgets import QToolBar, QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QActionGroup

from src.widgets.split_selector import SplitSelector


class MainToolbar(QToolBar):
    """Araç seçim ve zoom butonlarını içeren ana toolbar."""

    tool_selected = Signal(str)    # tool name
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    zoom_fit_requested = Signal()
    zoom_100_requested = Signal()
    split_changed = Signal(str)

    TOOLS = [
        ("Seç",           "V",  "Seçim ve Taşıma"),
        ("BBox",          "B",  "Sınır Kutusu (Bounding Box)"),
        ("Polygon",       "P",  "Polygon (Segmentasyon)"),
        ("OBB",           "O",  "Döndürülmüş Sınır Kutusu"),
        ("Keypoint",      "K",  "Keypoint / Poz"),
        ("Sınıflandır",   "C",  "Görsel Sınıflandırma"),
    ]

    def __init__(self, parent=None):
        super().__init__("Araçlar", parent)
        self.setMovable(False)
        self._tool_actions = {}
        self._action_group = QActionGroup(self)
        self._action_group.setExclusive(True)
        self.split_selector = None
        self._setup()

    def _setup(self):
        # Araç butonları
        for name, shortcut, tooltip in self.TOOLS:
            action = QAction(name, self)
            action.setCheckable(True)
            # Kısayollar main_window'daki QShortcut nesneleriyle yönetiliyor;
            # burada setShortcut çakışmaya (Ambiguous shortcut) neden olurdu → kaldırıldı.
            # Sadece tooltip'te göster
            action.setToolTip(f"{tooltip} ({shortcut})")
            # toggled: araç aktif olduğunda (checked=True) sinyal gönder
            action.toggled.connect(
                lambda checked=False, n=name: self.tool_selected.emit(n) if checked else None
            )
            self._action_group.addAction(action)
            self.addAction(action)
            self._tool_actions[name] = action

        # İlk aracı seç
        first = list(self._tool_actions.values())[0]
        first.setChecked(True)

        self.addSeparator()

        # Zoom butonları
        zoom_in = QAction("+ Yakınlaştır", self)
        zoom_in.setShortcut(QKeySequence("Ctrl+="))
        zoom_in.triggered.connect(lambda: self.zoom_in_requested.emit())
        self.addAction(zoom_in)

        zoom_out = QAction("- Uzaklaştır", self)
        zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out.triggered.connect(lambda: self.zoom_out_requested.emit())
        self.addAction(zoom_out)

        zoom_fit = QAction("[ ] Sığdır", self)
        zoom_fit.setShortcut(QKeySequence("Ctrl+0"))
        zoom_fit.triggered.connect(lambda: self.zoom_fit_requested.emit())
        self.addAction(zoom_fit)

        zoom_100 = QAction("100%", self)
        zoom_100.setShortcut(QKeySequence("Ctrl+1"))
        zoom_100.triggered.connect(lambda: self.zoom_100_requested.emit())
        self.addAction(zoom_100)

        self.addSeparator()

        # Split seçici
        self.split_selector = SplitSelector()
        self.split_selector.split_changed.connect(self.split_changed)
        self.addWidget(self.split_selector)

        # Sağ tarafa itme için esnek boşluk
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

    def select_tool(self, name: str):
        """Programatik olarak bir aracı seçer."""
        if name in self._tool_actions:
            self._tool_actions[name].setChecked(True)
