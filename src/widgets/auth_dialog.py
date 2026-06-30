"""Giris / Kayit diyalogu — Faz 2.

Opsiyonel kullanici sistemi. Yerel calisma icin bu diyalogu acmaya gerek
yoktur; sadece ekip ozelliklerini kullanmak isteyenler giris yapar.
Auth cagrilari arka plan thread'inde (_AuthWorker) calisir; UI donmaz.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QLabel, QTabWidget, QWidget,
)

from src.controllers.account_controller import _AuthWorker


class AuthDialog(QDialog):
    """E-posta/sifre ile giris veya kayit."""

    def __init__(self, auth_manager, parent=None):
        super().__init__(parent)
        self._auth = auth_manager
        self._worker = None
        self.setWindowTitle("Hesap")
        self.setModal(True)
        self.setMinimumWidth(380)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        # --- Giris sekmesi ---
        login = QWidget()
        lf = QFormLayout(login)
        self.login_email = QLineEdit()
        self.login_email.setPlaceholderText("ornek@eposta.com")
        self.login_pass = QLineEdit()
        self.login_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_pass.returnPressed.connect(self._submit)
        lf.addRow("E-posta:", self.login_email)
        lf.addRow("Şifre:", self.login_pass)
        self.tabs.addTab(login, "Giriş Yap")

        # --- Kayit sekmesi ---
        reg = QWidget()
        rf = QFormLayout(reg)
        self.reg_username = QLineEdit()
        self.reg_username.setPlaceholderText("kullanici_adi")
        self.reg_email = QLineEdit()
        self.reg_email.setPlaceholderText("ornek@eposta.com")
        self.reg_pass = QLineEdit()
        self.reg_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_pass.setPlaceholderText("en az 6 karakter")
        self.reg_pass.returnPressed.connect(self._submit)
        rf.addRow("Kullanıcı adı:", self.reg_username)
        rf.addRow("E-posta:", self.reg_email)
        rf.addRow("Şifre:", self.reg_pass)
        self.tabs.addTab(reg, "Kayıt Ol")

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.submit_btn = QPushButton("Devam")
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(self._submit)
        layout.addWidget(self.submit_btn)

        self.tabs.currentChanged.connect(lambda _i: self.status.clear())

    # ─── Gonderim ──────────────────────────────────────────────────────────
    def _submit(self):
        if self._worker is not None:
            return  # zaten calisiyor

        if self.tabs.currentIndex() == 0:  # Giris
            email = self.login_email.text().strip()
            pw = self.login_pass.text()
            if not email or not pw:
                self._error("E-posta ve şifre gerekli.")
                return
            fn = lambda: self._auth.sign_in(email, pw)
        else:  # Kayit
            username = self.reg_username.text().strip()
            email = self.reg_email.text().strip()
            pw = self.reg_pass.text()
            if not username or not email or not pw:
                self._error("Tüm alanları doldurun.")
                return
            if len(pw) < 6:
                self._error("Şifre en az 6 karakter olmalı.")
                return
            fn = lambda: self._auth.sign_up(email, pw, username=username)

        self._run(fn)

    def _run(self, fn):
        self._set_busy(True)
        self._info("Bağlanılıyor...")
        self._worker = _AuthWorker(fn, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._clear_worker)
        self._worker.start()

    def _on_done(self, _user):
        self._set_busy(False)
        # Kayit sonrasi e-posta onayi aciksa oturum acilmamis olabilir.
        if self._auth.is_authenticated():
            self.accept()
        else:
            self._warn(
                "Kayıt alındı ancak oturum açılmadı. E-posta onayı gerekiyor "
                "olabilir; onayladıktan sonra 'Giriş Yap' sekmesini kullanın."
            )

    def _on_failed(self, msg):
        self._set_busy(False)
        self._error(msg)

    def _clear_worker(self):
        self._worker = None

    # ─── Durum mesajlari ───────────────────────────────────────────────────
    def _info(self, msg):
        self.status.setStyleSheet("color:#aaaaaa;")
        self.status.setText(msg)

    def _warn(self, msg):
        self.status.setStyleSheet("color:#e0a030;")
        self.status.setText(msg)

    def _error(self, msg):
        self.status.setStyleSheet("color:#e05555;")
        self.status.setText(msg)

    def _set_busy(self, busy: bool):
        self.submit_btn.setEnabled(not busy)
        self.tabs.setEnabled(not busy)
