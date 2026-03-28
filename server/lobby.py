"""Lobi state yönetimi."""

import time
import uuid
import string
import random
from dataclasses import dataclass, field
from typing import Dict, Optional


LOBBY_CODE_LENGTH = 6
LOBBY_TIMEOUT_SEC = 300  # 5 dakika boş kalırsa kapanır
HEARTBEAT_TIMEOUT_SEC = 30


@dataclass
class User:
    user_id: str
    display_name: str
    color: str
    current_image: Optional[str] = None
    last_heartbeat: float = field(default_factory=time.time)


@dataclass
class Lobby:
    lobby_id: str
    host_id: str
    users: Dict[str, User] = field(default_factory=dict)
    manifest: Optional[dict] = None
    created_at: float = field(default_factory=time.time)
    seq: int = 0

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq


# Kullanıcı renk havuzu
USER_COLORS = [
    "#4caf50", "#2196f3", "#ff9800", "#e91e63",
    "#9c27b0", "#00bcd4", "#ff5722", "#607d8b",
    "#8bc34a", "#3f51b5", "#ffc107", "#795548",
]


class LobbyManager:
    """Tüm lobileri yöneten sınıf."""

    def __init__(self):
        self._lobbies: Dict[str, Lobby] = {}
        # websocket -> (lobby_id, user_id) eşleşmesi
        self._connections: Dict[int, tuple] = {}

    def _generate_code(self) -> str:
        chars = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(random.choices(chars, k=LOBBY_CODE_LENGTH))
            if code not in self._lobbies:
                return code

    def create_lobby(self, display_name: str, manifest: dict = None) -> tuple:
        """Yeni lobi oluşturur. (lobby_id, user_id, user_color) döndürür."""
        lobby_id = self._generate_code()
        user_id = str(uuid.uuid4())[:8]
        color = USER_COLORS[0]

        user = User(user_id=user_id, display_name=display_name, color=color)
        lobby = Lobby(lobby_id=lobby_id, host_id=user_id, manifest=manifest)
        lobby.users[user_id] = user

        self._lobbies[lobby_id] = lobby
        return lobby_id, user_id, color

    def join_lobby(self, lobby_id: str, display_name: str) -> tuple:
        """Lobiye katılır. (user_id, user_color, manifest) döndürür veya hata fırlatır."""
        lobby = self._lobbies.get(lobby_id)
        if not lobby:
            raise ValueError(f"Lobi bulunamadı: {lobby_id}")

        user_id = str(uuid.uuid4())[:8]
        color_idx = len(lobby.users) % len(USER_COLORS)
        color = USER_COLORS[color_idx]

        user = User(user_id=user_id, display_name=display_name, color=color)
        lobby.users[user_id] = user
        return user_id, color, lobby.manifest

    def leave_lobby(self, lobby_id: str, user_id: str) -> bool:
        """Kullanıcıyı lobiden çıkarır. Lobi boşsa True döndürür."""
        lobby = self._lobbies.get(lobby_id)
        if not lobby:
            return True
        lobby.users.pop(user_id, None)
        if not lobby.users:
            del self._lobbies[lobby_id]
            return True
        return False

    def get_lobby(self, lobby_id: str) -> Optional[Lobby]:
        return self._lobbies.get(lobby_id)

    def update_presence(self, lobby_id: str, user_id: str, image_stem: str):
        lobby = self._lobbies.get(lobby_id)
        if lobby and user_id in lobby.users:
            lobby.users[user_id].current_image = image_stem

    def update_heartbeat(self, lobby_id: str, user_id: str):
        lobby = self._lobbies.get(lobby_id)
        if lobby and user_id in lobby.users:
            lobby.users[user_id].last_heartbeat = time.time()

    def get_presence_list(self, lobby_id: str) -> list:
        lobby = self._lobbies.get(lobby_id)
        if not lobby:
            return []
        return [
            {
                "user_id": u.user_id,
                "name": u.display_name,
                "color": u.color,
                "current_image": u.current_image,
            }
            for u in lobby.users.values()
        ]

    def register_connection(self, ws_id: int, lobby_id: str, user_id: str):
        self._connections[ws_id] = (lobby_id, user_id)

    def unregister_connection(self, ws_id: int) -> Optional[tuple]:
        return self._connections.pop(ws_id, None)

    def get_connection_info(self, ws_id: int) -> Optional[tuple]:
        return self._connections.get(ws_id)

    def cleanup_stale_lobbies(self):
        """Boş veya timeout olmuş lobileri temizler."""
        now = time.time()
        to_remove = []
        for lid, lobby in self._lobbies.items():
            if not lobby.users:
                to_remove.append(lid)
                continue
            # Tüm kullanıcılar heartbeat timeout ise
            all_stale = all(
                now - u.last_heartbeat > HEARTBEAT_TIMEOUT_SEC
                for u in lobby.users.values()
            )
            if all_stale and now - lobby.created_at > LOBBY_TIMEOUT_SEC:
                to_remove.append(lid)
        for lid in to_remove:
            del self._lobbies[lid]
