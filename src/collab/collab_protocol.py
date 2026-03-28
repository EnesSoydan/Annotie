"""Mesaj tipleri ve serializasyon - client tarafi."""

import json
from typing import Optional


class MsgType:
    # Client -> Server
    CREATE_LOBBY = "create_lobby"
    JOIN_LOBBY = "join_lobby"
    LEAVE_LOBBY = "leave_lobby"
    HEARTBEAT = "heartbeat"
    IMAGE_FOCUS = "image_focus"
    ANN_CREATE = "ann_create"
    ANN_DELETE = "ann_delete"
    ANN_MODIFY = "ann_modify"
    ANN_CLASS_CHANGE = "ann_class_change"
    CLASS_ADD = "class_add"
    CLASS_RENAME = "class_rename"
    CLASS_DELETE = "class_delete"

    # Server -> Client
    LOBBY_CREATED = "lobby_created"
    LOBBY_JOINED = "lobby_joined"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    PRESENCE_UPDATE = "presence_update"
    ERROR = "error"


def make_msg(msg_type: str, **kwargs) -> str:
    """JSON mesaj olusturur."""
    data = {"type": msg_type}
    data.update(kwargs)
    return json.dumps(data, ensure_ascii=False)


def parse_msg(text: str) -> Optional[dict]:
    """JSON mesaji parse eder."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
