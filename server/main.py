"""FastAPI WebSocket relay sunucusu - Annotie işbirliği."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Dict, Set

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager

from lobby import LobbyManager
from protocol import validate_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("annotie-relay")

# Opsiyonel kimlik doğrulama: bu env'ler verilirse join_room'da kullanıcının
# Supabase token'ı + ekip üyeliği doğrulanır. Verilmezse açık mod (LAN/test).
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
AUTH_ENABLED = bool(SUPABASE_URL and SUPABASE_ANON_KEY)


async def verify_team_access(token: str, room_id: str) -> bool:
    """Token geçerli mi ve kullanıcı bu dataseti (room_id) görebilen ekip üyesi mi?
    Tek bir PostgREST çağrısı hem token'ı doğrular (geçersizse 401) hem de
    RLS ile üyeliği kontrol eder (üye değilse boş döner)."""
    if not AUTH_ENABLED:
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/datasets",
                headers={"apikey": SUPABASE_ANON_KEY,
                         "Authorization": f"Bearer {token}"},
                params={"id": f"eq.{room_id}", "select": "team_id"},
            )
        return r.status_code == 200 and len(r.json()) > 0
    except Exception as exc:
        logger.warning(f"Yetki doğrulama hatası: {exc}")
        return False

manager = LobbyManager()

# lobby_id -> set of websocket connections
lobby_connections: Dict[str, Set] = {}


async def cleanup_task():
    """Periyodik lobi temizliği."""
    while True:
        await asyncio.sleep(60)
        manager.cleanup_stale_lobbies()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_task())
    yield
    task.cancel()


app = FastAPI(title="Annotie Relay Server", lifespan=lifespan)


async def broadcast_to_lobby(lobby_id: str, message: dict, exclude_ws: WebSocket = None):
    """Lobideki tüm bağlantılara mesaj gönderir."""
    connections = lobby_connections.get(lobby_id, set())
    data = json.dumps(message, ensure_ascii=False)
    disconnected = []
    for ws in connections:
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


async def handle_create_lobby(ws: WebSocket, msg: dict):
    display_name = msg["display_name"]
    manifest = msg.get("manifest")

    lobby_id, user_id, color = manager.create_lobby(display_name, manifest)
    manager.register_connection(id(ws), lobby_id, user_id)

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
    room_id = str(msg["room_id"]).strip()
    display_name = msg["display_name"]
    manifest = msg.get("manifest")

    # Kimlik doğrulama (etkinse): token + ekip üyeliği
    if not await verify_team_access(msg.get("token"), room_id):
        await send_error(ws, "Bu ekip datasetine erişim yetkiniz yok")
        return

    user_id, color, existing_manifest = manager.join_or_create(
        room_id, display_name, manifest)

    manager.register_connection(id(ws), room_id, user_id)
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
    logger.info(f"Oda katılım: {room_id} ({display_name})")


async def handle_join_lobby(ws: WebSocket, msg: dict):
    lobby_id = msg["lobby_id"].upper().strip()
    display_name = msg["display_name"]

    try:
        user_id, color, manifest = manager.join_lobby(lobby_id, display_name)
    except ValueError as e:
        await send_error(ws, str(e))
        return

    manager.register_connection(id(ws), lobby_id, user_id)
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

    # Seq numarası ve kullanıcı bilgisi ekle
    relay_msg = dict(msg)
    relay_msg["seq"] = lobby.next_seq()
    relay_msg["user_id"] = user_id
    relay_msg["user_name"] = user.display_name

    await broadcast_to_lobby(lobby_id, relay_msg, exclude_ws=ws)


async def handle_disconnect(ws: WebSocket):
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
    try:
        while True:
            text = await ws.receive_text()
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                await send_error(ws, "Geçersiz JSON")
                continue

            error = validate_message(msg)
            if error:
                await send_error(ws, error)
                continue

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
    return {"status": "ok", "lobbies": lobby_count, "users": total_users}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
