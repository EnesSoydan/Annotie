"""Ekip yonetimi diyalogu — Faz 3.

Ekiplerim listesi, yeni ekip olusturma, uye gorme, davet gonderme,
bana gelen davetleri kabul etme ve davet kodu ile katilma.

Servis cagrilari (ag islemleri) bu asamada senkron calisir; diyalog modal
oldugundan kisa bekleme kabul edilebilir. UI sirasinda bekleme imleci gosterilir.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QLineEdit, QComboBox, QGroupBox,
    QInputDialog, QMessageBox, QApplication,
)

from src.cloud.teams import TeamService, TeamError, role_label, ASSIGNABLE_ROLES


class TeamsDialog(QDialog):
    def __init__(self, service: TeamService, parent=None):
        super().__init__(parent)
        self._svc = service
        self._teams: list[dict] = []
        self._current_team: dict | None = None

        self.setWindowTitle("Ekiplerim")
        self.setModal(True)
        self.resize(720, 520)
        self._build()
        self._reload_teams()
        self._reload_my_invites()

    # ─── Arayuz ────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)

        # Ust butonlar
        top = QHBoxLayout()
        btn_new = QPushButton("Yeni Ekip Oluştur")
        btn_new.clicked.connect(self._on_create_team)
        btn_join = QPushButton("Davet Kodu ile Katıl")
        btn_join.clicked.connect(self._on_join_by_code)
        btn_refresh = QPushButton("Yenile")
        btn_refresh.clicked.connect(self._refresh_all)
        top.addWidget(btn_new)
        top.addWidget(btn_join)
        top.addStretch(1)
        top.addWidget(btn_refresh)
        root.addLayout(top)

        # Orta: ekipler | detay
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Sol: ekip listesi
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("Ekiplerim"))
        self.team_list = QListWidget()
        self.team_list.currentRowChanged.connect(self._on_team_selected)
        lv.addWidget(self.team_list, 1)
        splitter.addWidget(left)

        # Sag: secili ekip detayi
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)

        self.detail_header = QLabel("Bir ekip seçin")
        self.detail_header.setStyleSheet("font-weight:bold; font-size:14px;")
        rv.addWidget(self.detail_header)

        rv.addWidget(QLabel("Üyeler"))
        self.member_list = QListWidget()
        rv.addWidget(self.member_list, 1)

        # Davet kutusu (sadece owner/admin)
        self.invite_box = QGroupBox("Davet Et")
        ib = QHBoxLayout(self.invite_box)
        self.invite_input = QLineEdit()
        self.invite_input.setPlaceholderText("kullanıcı adı veya e-posta")
        self.invite_input.returnPressed.connect(self._on_invite)
        self.role_combo = QComboBox()
        for r in ASSIGNABLE_ROLES:
            self.role_combo.addItem(role_label(r), r)
        btn_invite = QPushButton("Davet Gönder")
        btn_invite.clicked.connect(self._on_invite)
        ib.addWidget(self.invite_input, 1)
        ib.addWidget(self.role_combo)
        ib.addWidget(btn_invite)
        rv.addWidget(self.invite_box)

        # Bekleyen davetler (ekibin)
        self.pending_label = QLabel("Bekleyen Davetler")
        rv.addWidget(self.pending_label)
        self.team_invites = QListWidget()
        self.team_invites.setMaximumHeight(110)
        rv.addWidget(self.team_invites)

        splitter.addWidget(right)
        splitter.setSizes([220, 500])

        # Alt: bana gelen davetler
        mine = QGroupBox("Bana Gelen Davetler")
        mv = QVBoxLayout(mine)
        self.my_invites = QListWidget()
        self.my_invites.setMaximumHeight(110)
        mv.addWidget(self.my_invites)
        btn_accept = QPushButton("Seçili Daveti Kabul Et")
        btn_accept.clicked.connect(self._on_accept_selected)
        mv.addWidget(btn_accept)
        root.addWidget(mine)

    # ─── Veri yukleme ──────────────────────────────────────────────────────
    def _reload_teams(self):
        teams = self._busy(self._svc.list_my_teams)
        if teams is None:
            return
        self._teams = teams
        self.team_list.clear()
        for t in teams:
            item = QListWidgetItem(f"{t['name']}  ·  {role_label(t.get('role'))}")
            item.setData(Qt.ItemDataRole.UserRole, t)
            self.team_list.addItem(item)
        if teams:
            self.team_list.setCurrentRow(0)
        else:
            self._current_team = None
            self._clear_detail()

    def _on_team_selected(self, row: int):
        if row < 0 or row >= len(self._teams):
            self._current_team = None
            self._clear_detail()
            return
        self._current_team = self._teams[row]
        self._reload_detail()

    def _reload_detail(self):
        t = self._current_team
        if not t:
            return
        self.detail_header.setText(f"{t['name']}  ({role_label(t.get('role'))})")

        members = self._busy(lambda: self._svc.get_members(t["id"])) or []
        self.member_list.clear()
        for m in members:
            name = m.get("display_name") or m.get("username") or "?"
            self.member_list.addItem(f"{name}  —  {role_label(m.get('role'))}")

        can_manage = t.get("role") in ("owner", "admin")
        self.invite_box.setVisible(can_manage)
        self.pending_label.setVisible(can_manage)
        self.team_invites.setVisible(can_manage)
        if can_manage:
            self._reload_team_invites()

    def _reload_team_invites(self):
        t = self._current_team
        if not t:
            return
        invites = self._busy(lambda: self._svc.team_pending_invites(t["id"])) or []
        self.team_invites.clear()
        for inv in invites:
            who = inv.get("email") or "kullanıcı daveti"
            self.team_invites.addItem(
                f"{who}  ·  {role_label(inv.get('role'))}  ·  kod: {inv.get('token')}"
            )
        if not invites:
            self.team_invites.addItem("(bekleyen davet yok)")

    def _reload_my_invites(self):
        invites = self._busy(self._svc.my_pending_invites)
        self.my_invites.clear()
        for inv in invites or []:
            item = QListWidgetItem(
                f"{inv.get('team_name')}  ·  {role_label(inv.get('role'))}"
                f"  (davet eden: {inv.get('invited_by_name') or '?'})"
            )
            item.setData(Qt.ItemDataRole.UserRole, inv)
            self.my_invites.addItem(item)
        if not invites:
            self.my_invites.addItem("(bekleyen davet yok)")

    def _clear_detail(self):
        self.detail_header.setText("Bir ekip seçin")
        self.member_list.clear()
        self.invite_box.setVisible(False)
        self.pending_label.setVisible(False)
        self.team_invites.setVisible(False)

    def _refresh_all(self):
        self._reload_teams()
        self._reload_my_invites()

    # ─── Eylemler ──────────────────────────────────────────────────────────
    def _on_create_team(self):
        name, ok = QInputDialog.getText(self, "Yeni Ekip", "Ekip adı:")
        if not ok or not name.strip():
            return
        try:
            self._busy_raise(lambda: self._svc.create_team(name))
        except TeamError as exc:
            self._error(str(exc))
            return
        self._reload_teams()
        # Yeni olusturulan ekibi sec
        for i in range(self.team_list.count()):
            data = self.team_list.item(i).data(Qt.ItemDataRole.UserRole)
            if data and data.get("name") == name.strip():
                self.team_list.setCurrentRow(i)
                break

    def _on_invite(self):
        if not self._current_team:
            return
        identifier = self.invite_input.text().strip()
        if not identifier:
            return
        role = self.role_combo.currentData()
        try:
            inv = self._busy_raise(
                lambda: self._svc.invite(self._current_team["id"], identifier, role)
            )
        except TeamError as exc:
            self._error(str(exc))
            return
        self.invite_input.clear()
        token = inv.get("token") if inv else None
        if token:
            self._show_token(identifier, token)
        self._reload_team_invites()

    def _on_accept_selected(self):
        item = self.my_invites.currentItem()
        if not item:
            return
        inv = item.data(Qt.ItemDataRole.UserRole)
        if not inv:
            return
        try:
            self._busy_raise(lambda: self._svc.accept_invite(inv.get("token")))
        except TeamError as exc:
            self._error(str(exc))
            return
        QMessageBox.information(self, "Katıldınız",
                                f"'{inv.get('team_name')}' ekibine katıldınız.")
        self._refresh_all()

    def _on_join_by_code(self):
        token, ok = QInputDialog.getText(self, "Davet Kodu ile Katıl", "Davet kodu:")
        if not ok or not token.strip():
            return
        try:
            self._busy_raise(lambda: self._svc.accept_invite(token))
        except TeamError as exc:
            self._error(str(exc))
            return
        QMessageBox.information(self, "Katıldınız", "Ekibe katıldınız.")
        self._refresh_all()

    # ─── Yardimcilar ───────────────────────────────────────────────────────
    def _busy(self, fn: Callable):
        """Senkron servis cagrisi; hata olursa mesaj gosterir, None doner."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return fn()
        except TeamError as exc:
            self._error(str(exc))
            return None
        except Exception as exc:
            self._error(f"Beklenmeyen hata: {exc}")
            return None
        finally:
            QApplication.restoreOverrideCursor()

    def _busy_raise(self, fn: Callable):
        """Senkron servis cagrisi; hatayi yukari firlatir (cagiran isler)."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return fn()
        finally:
            QApplication.restoreOverrideCursor()

    def _show_token(self, identifier: str, token: str):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Davet Oluşturuldu")
        box.setText(
            f"'{identifier}' için davet oluşturuldu.\n\n"
            f"Davet kodu:\n{token}\n\n"
            "Bu kodu paylaşabilirsiniz; karşı taraf 'Davet Kodu ile Katıl' ile girer.\n"
            "(Kayıtlı kullanıcıya davet ise, kişi 'Bana Gelen Davetler'de de görebilir.)"
        )
        copy_btn = box.addButton("Kodu Kopyala", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is copy_btn:
            QGuiApplication.clipboard().setText(token)

    def _error(self, msg: str):
        QMessageBox.warning(self, "Hata", msg)
