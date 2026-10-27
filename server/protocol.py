"""Mesaj tipleri ve doğrulaması."""

from __future__ import annotations

import re
from typing import Optional

# Alan türleri
STR = "str"
STR_OR_NONE = "str_or_none"
INT = "int"
DICT = "dict"

MAX_DISPLAY_NAME = 64
MAX_TOKEN = 8192
MAX_STEM = 512
MAX_UID = 64
MAX_CLASS_NAME = 256
MAX_COLOR = 32

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

# Mesaj tipi -> {alan: (tür, zorunlu mu, en fazla uzunluk)}
# Yalnızca burada tanımlı alanlar relay edilir; istemcinin eklediği diğer
# alanlar (ör. sahte user_id) atılır.
FIELD_SPECS = {
    "create_lobby": {
        "display_name": (STR, True, MAX_DISPLAY_NAME),
        "manifest": (DICT, False, None),
        "token": (STR, False, MAX_TOKEN),
    },
    "join_lobby": {
        "lobby_id": (STR, True, 16),
        "display_name": (STR, True, MAX_DISPLAY_NAME),
        "token": (STR, False, MAX_TOKEN),
    },
    "join_room": {
        "room_id": (STR, True, 64),
        "display_name": (STR, True, MAX_DISPLAY_NAME),
        "manifest": (DICT, False, None),
        "token": (STR, False, MAX_TOKEN),
    },
    "leave_lobby": {},
    "heartbeat": {},
    "image_focus": {"image_stem": (STR, True, MAX_STEM)},
    "ann_create": {
        "image_stem": (STR, True, MAX_STEM),
        "annotation": (DICT, True, None),
    },
    "ann_delete": {
        "image_stem": (STR, True, MAX_STEM),
        "uid": (STR, True, MAX_UID),
    },
    "ann_modify": {
        "image_stem": (STR, True, MAX_STEM),
        "uid": (STR, True, MAX_UID),
        "data": (DICT, True, None),
    },
    "ann_class_change": {
        "image_stem": (STR, True, MAX_STEM),
        "uid": (STR, True, MAX_UID),
        "new_class_id": (INT, True, None),
    },
    "class_add": {
        "class_id": (INT, True, None),
        "name": (STR, True, MAX_CLASS_NAME),
        "color": (STR_OR_NONE, True, MAX_COLOR),
    },
    "class_rename": {
        "class_id": (INT, True, None),
        "new_name": (STR, True, MAX_CLASS_NAME),
    },
    "class_delete": {"class_id": (INT, True, None)},
}

# Client -> Server mesaj tipleri
CLIENT_TYPES = set(FIELD_SPECS)

# Server -> Client mesaj tipleri
SERVER_TYPES = {
    "lobby_created", "lobby_joined", "user_joined", "user_left",
    "presence_update", "error",
    "ann_create", "ann_delete", "ann_modify", "ann_class_change",
    "class_add", "class_rename", "class_delete",
}

# Zorunlu alanlar (mesaj tipi -> alan listesi)
REQUIRED_FIELDS = {
    msg_type: [name for name, (_, required, _) in spec.items() if required]
    for msg_type, spec in FIELD_SPECS.items()
}


def _check_field(msg_type: str, name: str, value, kind: str,
                 max_len: Optional[int]) -> Optional[str]:
    if kind == STR_OR_NONE and value is None:
        return None
    if kind in (STR, STR_OR_NONE):
        if not isinstance(value, str):
            return f"'{msg_type}.{name}' metin olmalı"
        if max_len is not None and len(value) > max_len:
            return f"'{msg_type}.{name}' çok uzun"
    elif kind == INT:
        # bool, int'in alt sınıfı; sınıf kimliği olarak kabul etme
        if not isinstance(value, int) or isinstance(value, bool):
            return f"'{msg_type}.{name}' tam sayı olmalı"
    elif kind == DICT:
        if not isinstance(value, dict):
            return f"'{msg_type}.{name}' nesne olmalı"
    return None


def validate_message(msg) -> Optional[str]:
    """Mesajı doğrular. Hata varsa hata mesajı, yoksa None döndürür."""
    if not isinstance(msg, dict):
        return "Mesaj bir JSON nesnesi olmalı"
    msg_type = msg.get("type")
    if not msg_type:
        return "Mesajda 'type' alanı eksik"
    if not isinstance(msg_type, str) or msg_type not in CLIENT_TYPES:
        return f"Bilinmeyen mesaj tipi: {msg_type}"
    for name, (kind, required, max_len) in FIELD_SPECS[msg_type].items():
        if name not in msg:
            if required:
                return f"'{msg_type}' mesajında '{name}' alanı eksik"
            continue
        if msg[name] is None and not required:
            continue
        error = _check_field(msg_type, name, msg[name], kind, max_len)
        if error:
            return error
    if msg_type == "join_room" and not UUID_RE.match(msg["room_id"].strip()):
        return "Geçersiz oda kimliği"
    return None


def sanitize_message(msg: dict) -> dict:
    """Doğrulanmış mesajdan yalnızca tanımlı alanları içeren bir kopya döndürür."""
    spec = FIELD_SPECS[msg["type"]]
    clean = {"type": msg["type"]}
    for name in spec:
        if name in msg:
            clean[name] = msg[name]
    return clean


def clean_display_name(name: str) -> str:
    """Kontrol karakterlerini atar, kırpar; boşsa varsayılan ad verir."""
    cleaned = "".join(ch for ch in name if ch.isprintable()).strip()
    return cleaned[:MAX_DISPLAY_NAME] or "Kullanıcı"
