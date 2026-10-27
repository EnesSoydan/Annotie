"""FastAPI WebSocket relay sunucusu - Annotie işbirliği."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Dict, Optional, Set

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager

from lobby import LobbyManager
from protocol import clean_display_name, sanitize_message, validate_message
from security import (
    AUTH_MISCONFIGURED, AUTH_OPEN, AUTH_SUPABASE, TokenBucket, can_send, load_settings,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("annotie-relay")

# Kimlik doğrulama varsayılan olarak ZORUNLU: SUPABASE_URL + SUPABASE_ANON_KEY
# verilirse join'lerde Supabase token'ı ve ekip rolü doğrulanır. Bunlar yoksa
# sunucu başlamaz; kimlik doğrulamasız LAN/test modu yalnızca
# RELAY_INSECURE_OPEN=1 ile bilerek açılır.
SETTINGS = load_settings(os.environ)

MISCONFIGURED_MESSAGE = (
    "Relay kimlik doğrulaması yapılandırılmamış: SUPABASE_URL ve "
    "SUPABASE_ANON_KEY verin (önerilen) veya yalnızca güvenilir LAN/test için "
    "RELAY_INSECURE_OPEN=1 ayarlayın."
)


def _auth_headers(token: str) -> dict:
    return {
        "apikey": SETTINGS.supabase_anon_key,
        "Authorization": f"Bearer {token}",
    }


async def fetch_dataset_role(token: Optional[str], room_id: str) -> Optional[str]:
    """Kullanıcının bu datasetin ekibindeki rolü; token geçersizse/üye değilse None.
    my_dataset_role RPC'si (0008) token'ı doğrular ve üyeliği RLS dışı okur."""
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                f"{SETTINGS.supabase_url}/rest/v1/rpc/my_dataset_role",
                headers=_auth_headers(token),
                json={"p_dataset_id": room_id},
            )
        if r.status_code != 200:
            return None
        role = r.json()
        return role if isinstance(role, str) else None
    except Exception as exc:
        logger.warning(f"Yetki doğrulama hatası: {exc}")
        return None


async def verify_user_token(token: Optional[str]) -> bool:
    """Token geçerli bir Supabase kullanıcısına mı ait?"""
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{SETTINGS.supabase_url}/auth/v1/user",
                                 headers=_auth_headers(token))
        return r.status_code == 200
    except Exception as exc:
        logger.warning(f"Token doğrulama hatası: {exc}")
        return False


async def resolve_room_role(token: Optional[str], room_id: str) -> Optional[str]:
    """Ekip dataseti odası için rol (None → katılamaz)."""
    if SETTINGS.auth_mode == AUTH_OPEN:
        return "annotator"
    if SETTINGS.auth_mode != AUTH_SUPABASE:
        return None
    return await fetch_dataset_role(token, room_id)


async def resolve_lobby_role(token: Optional[str]) -> Optional[str]:
    """Kodla açılan manuel lobiler: herhangi bir oturumlu kullanıcı düzenleyebilir."""
    if SETTINGS.auth_mode == AUTH_OPEN:
        return "annotator"
    if SETTINGS.auth_mode != AUTH_SUPABASE:
        return None
    return "annotator" if await verify_user_token(token) else None


manager = LobbyManager()

# lobby_id -> set of websocket connections
lobby_connections: Dict[str, Set] = {}
# id(ws) -> ekip rolü (owner/admin/annotator/viewer)
connection_roles: Dict[int, str] = {}


async def cleanup_task():
    """Periyodik lobi temizliği."""
    while True:
        await asyncio.sleep(60)
        manager.cleanup_stale_lobbies()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if SETTINGS.auth_mode == AUTH_MISCONFIGURED:
        logger.error(MISCONFIGURED_MESSAGE)
        raise RuntimeError(MISCONFIGURED_MESSAGE)
    if SETTINGS.auth_mode == AUTH_OPEN:
        logger.warning("UYARI: Relay AÇIK modda (RELAY_INSECURE_OPEN=1) — "
                       "kimlik doğrulama yok, yalnızca güvenilir ağda kullanın.")
    else:
        logger.info("Relay kimlik doğrulaması etkin (Supabase).")
    task = asyncio.create_task(cleanup_task())
    yield
    task.cancel()


app = FastAPI(title="Annotie Relay Server", lifespan=lifespan)


async def broadcast_to_lobby(lobby_id: str, message: dict, exclude_ws: WebSocket = None):
    """Lobideki tüm bağlantılara mesaj gönderir."""
    connections = lobby_connections.get(lobby_id, set())
    data = json.dumps(message, ensure_ascii=False)
    disconnected = []
    # await sırasında başka bağlantılar katılıp ayrılabilir; kopya üzerinde dön
    for ws in list(connections):
        if ws is exclude_ws:
            continue
        try:
            await ws.send_text(data)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        connections.discard(ws)


async def send_json(ws: WebSocket, msg: dict):
    await ws.send_text(json.dumps(msg, ensure_ascii=False))


async def send_error(ws: WebSocket, error: str):
    await send_json(ws, {"type": "error", "message": error})


async def leave_current_lobby(ws: WebSocket):
    """Aynı bağlantı yeniden join ederse eski odada hayalet kullanıcı kalmasın."""
    if manager.get_connection_info(id(ws)) is not None:
        await handle_disconnect(ws)


async def handle_create_lobby(ws: WebSocket, msg: dict):
    await leave_current_lobby(ws)
    role = await resolve_lobby_role(msg.get("token"))
    if role is None:
        await send_error(ws, "Lobi oluşturmak için giriş yapmanız gerekiyor")
        return

    display_name = clean_display_name(msg["display_name"])
    manifest = msg.get("manifest")

    lobby_id, user_id, color = manager.create_lobby(display_name, manifest)
    manager.register_connection(id(ws), lobby_id, user_id)
    connection_roles[id(ws)] = role

    lobby_connections.setdefault(lobby_id, set()).add(ws)

    await send_json(ws, {
        "type": "lobby_created",
        "lobby_id": lobby_id,
        "user_id": user_id,
        "color": color,
    })
    logger.info(f"Lobi oluşturuldu: {lobby_id} (host: {display_name})")


async def handle_join_room(ws: WebSocket, msg: dict):
    """Ekip dataseti odası: room_id (=dataset_id) ile join-or-create."""
    await leave_current_lobby(ws)
    room_id = str(msg["room_id"]).strip().lower()
    display_name = clean_display_name(msg["display_name"])
    manifest = msg.get("manifest")

    # Kimlik doğrulama: token + ekip rolü (viewer katılır ama düzenleme yayınlayamaz)
    role = await resolve_room_role(msg.get("token"), room_id)
    if role is None:
        await send_error(ws, "Bu ekip datasetine erişim yetkiniz yok")
        return

    user_id, color, existing_manifest = manager.join_or_create(
        room_id, display_name, manifest)

    manager.register_connection(id(ws), room_id, user_id)
    connection_roles[id(ws)] = role
    lobby_connections.setdefault(room_id, set()).add(ws)

    await send_json(ws, {
        "type": "lobby_joined",
        "lobby_id": room_id,
        "user_id": user_id,
        "color": color,
        "manifest": existing_manifest,
    })
    await broadcast_to_lobby(room_id, {
        "type": "user_joined",
        "user_id": user_id,
        "display_name": display_name,
        "color": color,
    }, exclude_ws=ws)
    presence = manager.get_presence_list(room_id)
    await broadcast_to_lobby(room_id, {
        "type": "presence_update",
        "users": presence,
    })
    logger.info(f"Oda katılım: {room_id} ({display_name}, {role})")


async def handle_join_lobby(ws: WebSocket, msg: dict):
    await leave_current_lobby(ws)
    role = await resolve_lobby_role(msg.get("token"))
    if role is None:
        await send_error(ws, "Lobiye katılmak için giriş yapmanız gerekiyor")
        return

    lobby_id = msg["lobby_id"].upper().strip()
    display_name = clean_display_name(msg["display_name"])

    try:
        user_id, color, manifest = manager.join_lobby(lobby_id, display_name)
    except ValueError as e:
        await send_error(ws, str(e))
        return

    manager.register_connection(id(ws), lobby_id, user_id)
    connection_roles[id(ws)] = role
    lobby_connections.setdefault(lobby_id, set()).add(ws)

    # Katılan kullanıcıya lobi bilgisi gönder
    await send_json(ws, {
        "type": "lobby_joined",
        "lobby_id": lobby_id,
        "user_id": user_id,
        "color": color,
        "manifest": manifest,
    })

    # Diğer kullanıcılara bildir
    await broadcast_to_lobby(lobby_id, {
        "type": "user_joined",
        "user_id": user_id,
        "display_name": display_name,
        "color": color,
    }, exclude_ws=ws)

    # Presence güncelle
    presence = manager.get_presence_list(lobby_id)
    await broadcast_to_lobby(lobby_id, {
        "type": "presence_update",
        "users": presence,
    })

    logger.info(f"{display_name} lobiye katıldı: {lobby_id}")


async def handle_image_focus(ws: WebSocket, msg: dict, lobby_id: str, user_id: str):
    image_stem = msg["image_stem"]
    manager.update_presence(lobby_id, user_id, image_stem)
    presence = manager.get_presence_list(lobby_id)
    await broadcast_to_lobby(lobby_id, {
        "type": "presence_update",
        "users": presence,
    })


async def handle_heartbeat(ws: WebSocket, lobby_id: str, user_id: str):
    manager.update_heartbeat(lobby_id, user_id)


async def handle_annotation_msg(ws: WebSocket, msg: dict, lobby_id: str, user_id: str):
    """Annotation/class mesajlarını relay eder."""
    lobby = manager.get_lobby(lobby_id)
    if not lobby:
        return

    user = lobby.users.get(user_id)
    if not user:
        return

    # Seq numarası ve kullanıcı bilgisi ekle (istemcinin gönderdiğini ezer)
    relay_msg = dict(msg)
    relay_msg["seq"] = lobby.next_seq()
    relay_msg["user_id"] = user_id
    relay_msg["user_name"] = user.display_name

    await broadcast_to_lobby(lobby_id, relay_msg, exclude_ws=ws)


async def handle_disconnect(ws: WebSocket):
    connection_roles.pop(id(ws), None)
    info = manager.unregister_connection(id(ws))
    if not info:
        return
    lobby_id, user_id = info

    lobby = manager.get_lobby(lobby_id)
    display_name = "?"
    if lobby and user_id in lobby.users:
        display_name = lobby.users[user_id].display_name

    empty = manager.leave_lobby(lobby_id, user_id)
    lobby_connections.get(lobby_id, set()).discard(ws)

    if not empty:
        await broadcast_to_lobby(lobby_id, {
            "type": "user_left",
            "user_id": user_id,
            "display_name": display_name,
        })
        presence = manager.get_presence_list(lobby_id)
        await broadcast_to_lobby(lobby_id, {
            "type": "presence_update",
            "users": presence,
        })
    else:
        lobby_connections.pop(lobby_id, None)

    logger.info(f"{display_name} lobiden ayrıldı: {lobby_id}")


# Annotation/class mesaj tipleri - doğrudan relay edilir
RELAY_TYPES = {
    "ann_create", "ann_delete", "ann_modify", "ann_class_change",
    "class_add", "class_rename", "class_delete",
}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    bucket = TokenBucket(SETTINGS.rate_per_sec, SETTINGS.rate_burst)
    last_rate_warning = 0.0
    try:
        while True:
            text = await ws.receive_text()
            if len(text.encode("utf-8")) > SETTINGS.max_message_bytes:
                await send_error(ws, "Mesaj çok büyük")
                continue
            if not bucket.allow():
                now = time.monotonic()
                if now - last_rate_warning > 1.0:
                    last_rate_warning = now
                    await send_error(ws, "Çok fazla mesaj gönderiliyor; mesaj atlandı")
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                await send_error(ws, "Geçersiz JSON")
                continue

            error = validate_message(msg)
            if error:
                await send_error(ws, error)
                continue
            msg = sanitize_message(msg)

            msg_type = msg["type"]
            conn_info = manager.get_connection_info(id(ws))

            if msg_type == "create_lobby":
                await handle_create_lobby(ws, msg)
            elif msg_type == "join_lobby":
                await handle_join_lobby(ws, msg)
            elif msg_type == "join_room":
                await handle_join_room(ws, msg)
            elif conn_info is None:
                await send_error(ws, "Önce bir lobiye katılmanız gerekiyor")
            else:
                lobby_id, user_id = conn_info
                if msg_type == "leave_lobby":
                    await handle_disconnect(ws)
                    break
                elif msg_type == "heartbeat":
                    await handle_heartbeat(ws, lobby_id, user_id)
                elif msg_type == "image_focus":
                    await handle_image_focus(ws, msg, lobby_id, user_id)
                elif msg_type in RELAY_TYPES:
                    if not can_send(connection_roles.get(id(ws)), msg_type):
                        await send_error(ws, "Bu ekipte düzenleme yetkiniz yok (izleyici)")
                        continue
                    await handle_annotation_msg(ws, msg, lobby_id, user_id)

    except WebSocketDisconnect:
        await handle_disconnect(ws)
    except Exception as e:
        logger.error(f"WebSocket hatası: {e}")
        await handle_disconnect(ws)


@app.get("/health")
async def health():
    lobby_count = len(manager._lobbies)
    total_users = sum(len(l.users) for l in manager._lobbies.values())
    return {"status": "ok", "auth": SETTINGS.auth_mode,
            "lobbies": lobby_count, "users": total_users}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("RELAY_HOST", "0.0.0.0"), port=8765,
                ws_max_size=SETTINGS.max_message_bytes)
