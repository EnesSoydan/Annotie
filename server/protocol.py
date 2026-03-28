"""Mesaj tipleri ve doğrulaması."""

from __future__ import annotations
from typing import Optional

# Client -> Server mesaj tipleri
CLIENT_TYPES = {
    "create_lobby", "join_lobby", "leave_lobby",
    "heartbeat", "image_focus",
    "ann_create", "ann_delete", "ann_modify", "ann_class_change",
    "class_add", "class_rename", "class_delete",
}

# Server -> Client mesaj tipleri
SERVER_TYPES = {
    "lobby_created", "lobby_joined", "user_joined", "user_left",
    "presence_update", "error",
    "ann_create", "ann_delete", "ann_modify", "ann_class_change",
    "class_add", "class_rename", "class_delete",
}

# Zorunlu alanlar (mesaj tipi -> alan listesi)
REQUIRED_FIELDS = {
    "create_lobby": ["display_name"],
    "join_lobby": ["lobby_id", "display_name"],
    "leave_lobby": [],
    "heartbeat": [],
    "image_focus": ["image_stem"],
    "ann_create": ["image_stem", "annotation"],
    "ann_delete": ["image_stem", "uid"],
    "ann_modify": ["image_stem", "uid", "data"],
    "ann_class_change": ["image_stem", "uid", "new_class_id"],
    "class_add": ["class_id", "name", "color"],
    "class_rename": ["class_id", "new_name"],
    "class_delete": ["class_id"],
}


def validate_message(msg: dict) -> Optional[str]:
    """Mesajı doğrular. Hata varsa hata mesajı, yoksa None döndürür."""
    msg_type = msg.get("type")
    if not msg_type:
        return "Mesajda 'type' alanı eksik"
    if msg_type not in CLIENT_TYPES:
        return f"Bilinmeyen mesaj tipi: {msg_type}"
    required = REQUIRED_FIELDS.get(msg_type, [])
    for field in required:
        if field not in msg:
            return f"'{msg_type}' mesajında '{field}' alanı eksik"
    return None
