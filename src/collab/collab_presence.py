"""Presence state yönetimi - diğer kullanıcıların konumlarını takip eder."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal


@dataclass
class RemoteUser:
    user_id: str
    name: str
    color: str
    current_image: Optional[str] = None


class PresenceManager(QObject):
    """Lobideki kullanıcıların presence bilgisini yönetir."""

    # Presence değiştiğinde UI'ı bilgilendirir
    presence_changed = Signal()
    # Aynı görselde başka kullanıcı var/yok (image_stem, user_name veya None)
    same_image_warning = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._users: Dict[str, RemoteUser] = {}
        self._my_user_id: Optional[str] = None
        self._my_current_image: Optional[str] = None

    def set_my_user_id(self, user_id: str):
        self._my_user_id = user_id

    def set_my_current_image(self, image_stem: Optional[str]):
        self._my_current_image = image_stem
        self._check_same_image()

    def update_presence(self, users_data: list):
        """Sunucudan gelen presence listesini günceller."""
        self._users.clear()
        for u in users_data:
            uid = u["user_id"]
            if uid == self._my_user_id:
                continue
            self._users[uid] = RemoteUser(
                user_id=uid,
                name=u["name"],
                color=u["color"],
                current_image=u.get("current_image"),
            )
        self.presence_changed.emit()
        self._check_same_image()

    def on_user_joined(self, user_id: str, display_name: str, color: str):
        if user_id == self._my_user_id:
            return
        self._users[user_id] = RemoteUser(
            user_id=user_id, name=display_name, color=color
        )
        self.presence_changed.emit()

    def on_user_left(self, user_id: str):
        self._users.pop(user_id, None)
        self.presence_changed.emit()
        self._check_same_image()

    def get_users(self) -> List[RemoteUser]:
        return list(self._users.values())

    def get_user(self, user_id: str) -> Optional[RemoteUser]:
        return self._users.get(user_id)

    def get_users_on_image(self, image_stem: str) -> List[RemoteUser]:
        """Belirtilen görselde olan kullanıcıları döndürür."""
        return [u for u in self._users.values() if u.current_image == image_stem]

    def get_image_user_map(self) -> Dict[str, List[RemoteUser]]:
        """image_stem -> [RemoteUser] eşleşmesi."""
        result: Dict[str, List[RemoteUser]] = {}
        for u in self._users.values():
            if u.current_image:
                result.setdefault(u.current_image, []).append(u)
        return result

    def _check_same_image(self):
        """Aynı görselde başka kullanıcı var mı kontrol eder."""
        if not self._my_current_image:
            self.same_image_warning.emit("", None)
            return
        others = self.get_users_on_image(self._my_current_image)
        if others:
            names = ", ".join(u.name for u in others)
            self.same_image_warning.emit(self._my_current_image, names)
        else:
            self.same_image_warning.emit(self._my_current_image, None)

    def clear(self):
        self._users.clear()
        self._my_user_id = None
        self._my_current_image = None
        self.presence_changed.emit()
