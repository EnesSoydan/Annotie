"""QWebSocket bağlantı yöneticisi - otomatik yeniden bağlantı ve kuyruk desteği."""

import json
import logging
from collections import deque

from PySide6.QtCore import QObject, Signal, QTimer, QUrl
from PySide6.QtWebSockets import QWebSocket

logger = logging.getLogger("annotie.collab.client")


class CollabClient(QObject):
    """WebSocket bağlantı yöneticisi."""

    connected = Signal()
    disconnected = Signal()
    message_received = Signal(object)  # dict, Signal(dict) PySide6'da sorunlu olabiliyor
    connection_error = Signal(str)

    MAX_RETRY = 10
    RETRY_INTERVAL_MS = 3000
    HEARTBEAT_INTERVAL_MS = 10000
    MAX_QUEUE_SIZE = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws = QWebSocket("", parent=self)
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.errorOccurred.connect(self._on_error)

        self._server_url = ""
        self._is_connected = False
        self._should_reconnect = False
        self._retry_count = 0

        # Yeniden bağlantı zamanlayıcısı
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

        # Heartbeat zamanlayıcısı
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)

        # Offline mesaj kuyruğu
        self._queue: deque = deque(maxlen=self.MAX_QUEUE_SIZE)

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect_to_server(self, url: str):
        """Sunucuya bağlanır."""
        self._server_url = url
        self._should_reconnect = True
        self._retry_count = 0
        ws_url = url.rstrip("/") + "/ws"
        logger.info(f"Bağlanılıyor: {ws_url}")
        self._ws.open(QUrl(ws_url))

    def disconnect_from_server(self):
        """Sunucudan ayrılır."""
        self._should_reconnect = False
        self._reconnect_timer.stop()
        self._heartbeat_timer.stop()
        self._is_connected = False
        self._queue.clear()
        self._ws.close()

    def send(self, msg: dict):
        """Mesaj gönderir. Bağlı değilse kuyruğa ekler."""
        text = json.dumps(msg, ensure_ascii=False)
        if self._is_connected:
            print(f"[WS-SEND] {msg.get('type', '?')} ({len(text)} byte)", flush=True)
            self._ws.sendTextMessage(text)
        else:
            print(f"[WS-QUEUE] {msg.get('type', '?')} (bağlı değil)", flush=True)
            self._queue.append(text)

    def _on_connected(self):
        print("[WS] BAĞLANDI!", flush=True)
        self._is_connected = True
        self._retry_count = 0
        self._heartbeat_timer.start(self.HEARTBEAT_INTERVAL_MS)
        self._flush_queue()
        self.connected.emit()

    def _on_disconnected(self):
        was_connected = self._is_connected
        self._is_connected = False
        self._heartbeat_timer.stop()

        if was_connected:
            logger.warning("WebSocket bağlantısı kesildi")
            self.disconnected.emit()

        if self._should_reconnect:
            self._schedule_reconnect()

    def _on_message(self, text: str):
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Geçersiz JSON: {text[:100]}")
            return
        print(f"[WS-RECV] {msg.get('type', '?')} ({len(text)} byte)", flush=True)
        self.message_received.emit(msg)

    def _on_error(self, error):
        error_str = self._ws.errorString()
        logger.warning(f"WebSocket hatası: {error_str}")
        self.connection_error.emit(f"Bağlantı hatası: {error_str}")

    def _schedule_reconnect(self):
        if self._retry_count >= self.MAX_RETRY:
            logger.error(f"{self.MAX_RETRY} deneme başarısız, yeniden bağlanma durduruluyor")
            self.connection_error.emit(
                f"Sunucuya {self.MAX_RETRY} denemede bağlanılamadı"
            )
            self._should_reconnect = False
            return
        self._retry_count += 1
        delay = min(self.RETRY_INTERVAL_MS * self._retry_count, 15000)
        logger.info(f"Yeniden bağlanma denemesi {self._retry_count}/{self.MAX_RETRY} ({delay}ms)")
        self._reconnect_timer.start(delay)

    def _try_reconnect(self):
        if not self._should_reconnect:
            return
        ws_url = self._server_url.rstrip("/") + "/ws"
        self._ws.open(QUrl(ws_url))

    def _flush_queue(self):
        """Kuyruktaki mesajları gönderir."""
        while self._queue and self._is_connected:
            text = self._queue.popleft()
            self._ws.sendTextMessage(text)

    def _send_heartbeat(self):
        if self._is_connected:
            self._ws.sendTextMessage(json.dumps({"type": "heartbeat"}))
