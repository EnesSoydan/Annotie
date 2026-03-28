"""Lobi UI - oluştur/katıl/kullanıcı listesi dock paneli."""

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QStackedWidget, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QIcon


class CollabPanel(QDockWidget):
    """Sağ dock: işbirliği lobi paneli."""

    create_lobby_requested = Signal(str, str)    # server_url, display_name
    join_lobby_requested = Signal(str, str, str)  # server_url, lobby_id, display_name
    leave_lobby_requested = Signal()

    DEFAULT_SERVER = "ws://localhost:8765"

    def __init__(self, parent=None):
        super().__init__("İşbirliği", parent)
        self._collab_ctrl = None
        self._setup_ui()

    def set_collab_controller(self, ctrl):
        self._collab_ctrl = ctrl
        ctrl.lobby_created.connect(self._on_lobby_created)
        ctrl.lobby_joined.connect(self._on_lobby_joined)
        ctrl.lobby_left.connect(self._on_lobby_left)
        ctrl.connection_status_changed.connect(self._on_connection_changed)
        ctrl.error_occurred.connect(self._on_error)
        ctrl.presence.presence_changed.connect(self._refresh_user_list)

    def _setup_ui(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        self._stack = QStackedWidget()

        # Sayfa 0: Lobi oluştur/katıl
        self._join_page = self._build_join_page()
        self._stack.addWidget(self._join_page)

        # Sayfa 1: Aktif lobi
        self._lobby_page = self._build_lobby_page()
        self._stack.addWidget(self._lobby_page)

        main_layout.addWidget(self._stack)
        self.setWidget(container)
        self.setMinimumWidth(200)

    def _build_join_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Sunucu URL
        layout.addWidget(QLabel("Sunucu:"))
        self._server_input = QLineEdit()
        self._server_input.setPlaceholderText(self.DEFAULT_SERVER)
        self._server_input.setText(self.DEFAULT_SERVER)
        layout.addWidget(self._server_input)

        # Takma ad
        layout.addWidget(QLabel("Takma Ad:"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Adınızı girin...")
        layout.addWidget(self._name_input)

        # Lobi oluştur
        self._btn_create = QPushButton("Lobi Oluştur")
        self._btn_create.clicked.connect(self._on_create_clicked)
        layout.addWidget(self._btn_create)

        # Ayırıcı
        sep = QLabel("─── veya ───")
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(sep)

        # Lobi kodu
        layout.addWidget(QLabel("Lobi Kodu:"))
        self._code_input = QLineEdit()
        self._code_input.setPlaceholderText("6 haneli kod...")
        self._code_input.setMaxLength(6)
        font = self._code_input.font()
        font.setPointSize(14)
        font.setBold(True)
        self._code_input.setFont(font)
        self._code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._code_input)

        # Katıl butonu
        self._btn_join = QPushButton("Lobiye Katıl")
        self._btn_join.clicked.connect(self._on_join_clicked)
        layout.addWidget(self._btn_join)

        # Hata mesajı
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        layout.addStretch()
        return page

    def _build_lobby_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Bağlantı durumu
        self._status_label = QLabel()
        self._status_label.setStyleSheet("font-size: 11px; padding: 3px;")
        layout.addWidget(self._status_label)

        # Lobi kodu - kopyalanabilir
        code_layout = QHBoxLayout()
        code_layout.setSpacing(4)
        code_layout.addWidget(QLabel("Kod:"))
        self._lobby_code_label = QLabel()
        self._lobby_code_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #2196f3; "
            "background: #2a2d2e; padding: 4px 8px; border-radius: 3px;"
        )
        code_layout.addWidget(self._lobby_code_label)

        self._btn_copy = QPushButton("Kopyala")
        self._btn_copy.setFixedWidth(60)
        self._btn_copy.setStyleSheet("font-size: 10px; padding: 4px;")
        self._btn_copy.clicked.connect(self._copy_code)
        code_layout.addWidget(self._btn_copy)
        code_layout.addStretch()
        layout.addLayout(code_layout)

        # Kullanıcı listesi
        layout.addWidget(QLabel("Katılımcılar:"))
        self._user_list = QListWidget()
        self._user_list.setMaximumHeight(150)
        layout.addWidget(self._user_list)

        # Ayrıl butonu
        self._btn_leave = QPushButton("Lobiden Ayrıl")
        self._btn_leave.setStyleSheet(
            "background: #c0392b; color: white;"
        )
        self._btn_leave.clicked.connect(self._on_leave_clicked)
        layout.addWidget(self._btn_leave)

        layout.addStretch()
        return page

    # ── Event handler'lar ───────────────────────────────────────────────

    def _on_create_clicked(self):
        server = self._server_input.text().strip() or self.DEFAULT_SERVER
        name = self._name_input.text().strip()
        if not name:
            self._show_error("Lütfen bir takma ad girin")
            return
        self._error_label.hide()
        self._btn_create.setEnabled(False)
        self._btn_create.setText("Bağlanılıyor...")
        self.create_lobby_requested.emit(server, name)

    def _on_join_clicked(self):
        server = self._server_input.text().strip() or self.DEFAULT_SERVER
        name = self._name_input.text().strip()
        code = self._code_input.text().strip().upper()
        if not name:
            self._show_error("Lütfen bir takma ad girin")
            return
        if len(code) != 6:
            self._show_error("Lobi kodu 6 haneli olmalı")
            return
        self._error_label.hide()
        self._btn_join.setEnabled(False)
        self._btn_join.setText("Bağlanılıyor...")
        self.join_lobby_requested.emit(server, code, name)

    def _on_leave_clicked(self):
        self.leave_lobby_requested.emit()

    def _copy_code(self):
        code = self._lobby_code_label.text()
        if code:
            QApplication.clipboard().setText(code)
            self._btn_copy.setText("OK!")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self._btn_copy.setText("Kopyala"))

    # ── Collab controller sinyalleri ────────────────────────────────────

    def _on_lobby_created(self, lobby_id: str):
        self._lobby_code_label.setText(lobby_id)
        self._status_label.setText("Bağlı - Host")
        self._status_label.setStyleSheet(
            "font-size: 11px; padding: 3px; color: #4caf50; background: #1a2e1a; border-radius: 3px;"
        )
        self._stack.setCurrentIndex(1)
        self._reset_join_buttons()
        self._refresh_user_list()

    def _on_lobby_joined(self, lobby_id: str, manifest: dict):
        self._lobby_code_label.setText(lobby_id)
        self._status_label.setText("Bağlı - Peer")
        self._status_label.setStyleSheet(
            "font-size: 11px; padding: 3px; color: #2196f3; background: #1a2030; border-radius: 3px;"
        )
        self._stack.setCurrentIndex(1)
        self._reset_join_buttons()
        self._refresh_user_list()

    def _on_lobby_left(self):
        self._stack.setCurrentIndex(0)
        self._reset_join_buttons()
        self._user_list.clear()

    def _on_connection_changed(self, connected: bool):
        if not connected and self._stack.currentIndex() == 1:
            self._status_label.setText("Bağlantı kesildi - yeniden deneniyor...")
            self._status_label.setStyleSheet(
                "font-size: 11px; padding: 3px; color: #ff9800; background: #2e2a1a; border-radius: 3px;"
            )

    def _on_error(self, error: str):
        if self._stack.currentIndex() == 0:
            self._show_error(error)
            self._reset_join_buttons()
        else:
            self._status_label.setText(f"Hata: {error}")
            self._status_label.setStyleSheet(
                "font-size: 11px; padding: 3px; color: #e74c3c; background: #2e1a1a; border-radius: 3px;"
            )

    def _refresh_user_list(self):
        if not self._collab_ctrl:
            return
        self._user_list.clear()
        users = self._collab_ctrl.presence.get_users()

        # Önce kendimizi ekle
        if self._collab_ctrl._display_name:
            item = QListWidgetItem()
            item.setText(f"  {self._collab_ctrl._display_name} (Sen)")
            pix = QPixmap(12, 12)
            color = self._collab_ctrl._user_color or "#4caf50"
            pix.fill(QColor(color))
            item.setIcon(QIcon(pix))
            self._user_list.addItem(item)

        for user in users:
            item = QListWidgetItem()
            img_info = f" - {user.current_image}" if user.current_image else ""
            item.setText(f"  {user.name}{img_info}")
            pix = QPixmap(12, 12)
            pix.fill(QColor(user.color))
            item.setIcon(QIcon(pix))
            self._user_list.addItem(item)

    def _show_error(self, text: str):
        self._error_label.setText(text)
        self._error_label.show()

    def _reset_join_buttons(self):
        self._btn_create.setEnabled(True)
        self._btn_create.setText("Lobi Oluştur")
        self._btn_join.setEnabled(True)
        self._btn_join.setText("Lobiye Katıl")
