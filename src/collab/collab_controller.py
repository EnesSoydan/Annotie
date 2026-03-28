"""Ana işbirliği orkestratörü - yerel sinyalleri dinler, uzak değişiklikleri uygular."""

import logging
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer

from src.collab.collab_client import CollabClient
from src.collab.collab_protocol import MsgType, parse_msg
from src.collab.collab_presence import PresenceManager
from src.collab.collab_serializers import (
    annotation_to_dict, dict_to_annotation,
    annotation_modify_data, apply_modify_data,
)

logger = logging.getLogger("annotie.collab")

MODIFY_THROTTLE_MS = 33
REMOTE_SAVE_DEBOUNCE_MS = 500


def _dbg(msg):
    """Debug print - konsola anında yazar."""
    print(f"[COLLAB] {msg}", flush=True)


class CollabController(QObject):
    """İşbirliği sistemi ana kontrolcüsü."""

    lobby_created = Signal(str)
    lobby_joined = Signal(str, object)  # (lobby_id, manifest_dict)
    lobby_left = Signal()
    connection_status_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = CollabClient(self)
        self._presence = PresenceManager(self)

        self._ann_ctrl = None
        self._ds_ctrl = None
        self._dataset = None
        self._main_window = None

        self._lobby_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._user_color: Optional[str] = None
        self._display_name: Optional[str] = None

        self._applying_remote = False

        # Modify throttle
        self._last_modify_time = {}
        self._pending_modify = {}
        self._modify_timer = QTimer(self)
        self._modify_timer.setSingleShot(True)
        self._modify_timer.timeout.connect(self._flush_pending_modifies)

        # Remote save debounce
        self._remote_save_timer = QTimer(self)
        self._remote_save_timer.setSingleShot(True)
        self._remote_save_timer.timeout.connect(self._flush_remote_saves)
        self._remote_dirty_images = set()

        # Client sinyalleri
        self._client.message_received.connect(self._on_message)
        self._client.connected.connect(lambda: self.connection_status_changed.emit(True))
        self._client.disconnected.connect(lambda: self.connection_status_changed.emit(False))
        self._client.connection_error.connect(self.error_occurred.emit)

    @property
    def is_in_lobby(self) -> bool:
        return self._lobby_id is not None

    @property
    def lobby_id(self) -> Optional[str]:
        return self._lobby_id

    @property
    def user_id(self) -> Optional[str]:
        return self._user_id

    @property
    def presence(self) -> PresenceManager:
        return self._presence

    @property
    def client(self) -> CollabClient:
        return self._client

    def set_controllers(self, ann_ctrl, ds_ctrl):
        self._ann_ctrl = ann_ctrl
        self._ds_ctrl = ds_ctrl
        self._connect_annotation_signals()

    def set_main_window(self, window):
        self._main_window = window

    def set_dataset(self, dataset):
        self._dataset = dataset
        _dbg(f"Dataset ayarlandı: {dataset is not None}")

    # ── Lobi işlemleri ──────────────────────────────────────────────────

    def create_lobby(self, server_url: str, display_name: str):
        self._display_name = display_name
        self._client.connect_to_server(server_url)

        def _on_connected():
            manifest = self._build_manifest()
            self._client.send({
                "type": MsgType.CREATE_LOBBY,
                "display_name": display_name,
                "manifest": manifest,
            })
            try:
                self._client.connected.disconnect(_on_connected)
            except RuntimeError:
                pass

        self._client.connected.connect(_on_connected)

    def join_lobby(self, server_url: str, lobby_id: str, display_name: str):
        self._display_name = display_name
        self._client.connect_to_server(server_url)

        def _on_connected():
            self._client.send({
                "type": MsgType.JOIN_LOBBY,
                "lobby_id": lobby_id,
                "display_name": display_name,
            })
            try:
                self._client.connected.disconnect(_on_connected)
            except RuntimeError:
                pass

        self._client.connected.connect(_on_connected)

    def leave_lobby(self):
        if self._lobby_id:
            self._client.send({"type": MsgType.LEAVE_LOBBY})
        self._client.disconnect_from_server()
        self._lobby_id = None
        self._user_id = None
        self._user_color = None
        self._pending_modify.clear()
        self._last_modify_time.clear()
        self._remote_dirty_images.clear()
        self._presence.clear()
        self.lobby_left.emit()

    def send_image_focus(self, image_stem: str):
        if not self.is_in_lobby:
            return
        self._presence.set_my_current_image(image_stem)
        self._client.send({
            "type": MsgType.IMAGE_FOCUS,
            "image_stem": image_stem,
        })

    # ── Yerel -> Uzak ──────────────────────────────────────────────────

    def _connect_annotation_signals(self):
        if not self._ann_ctrl:
            return
        self._ann_ctrl.annotation_created.connect(self._on_local_ann_created)
        self._ann_ctrl.annotation_deleted.connect(self._on_local_ann_deleted)
        self._ann_ctrl.annotation_modified.connect(self._on_local_ann_modified)
        self._ann_ctrl.annotation_class_changed.connect(self._on_local_ann_class_changed)
        _dbg("Annotation sinyalleri bağlandı")

    def _on_local_ann_created(self, image, annotation):
        _dbg(f"_on_local_ann_created ÇAĞRILDI: applying_remote={self._applying_remote} in_lobby={self.is_in_lobby} stem={getattr(image, 'stem', '?')}")
        if self._applying_remote:
            return
        if not self.is_in_lobby:
            return
        _dbg(f"GÖNDERİLİYOR ann_create: stem={image.stem} uid={annotation.uid[:8]}")
        self._client.send({
            "type": MsgType.ANN_CREATE,
            "image_stem": image.stem,
            "annotation": annotation_to_dict(annotation),
        })

    def _on_local_ann_deleted(self, image, annotation):
        if self._applying_remote or not self.is_in_lobby:
            return
        _dbg(f"GÖNDERİLİYOR ann_delete: stem={image.stem} uid={annotation.uid[:8]}")
        self._client.send({
            "type": MsgType.ANN_DELETE,
            "image_stem": image.stem,
            "uid": annotation.uid,
        })

    def _on_local_ann_modified(self, image, annotation):
        if self._applying_remote or not self.is_in_lobby:
            return

        uid = annotation.uid
        now = time.monotonic()
        last = self._last_modify_time.get(uid, 0)

        if now - last >= MODIFY_THROTTLE_MS / 1000.0:
            self._last_modify_time[uid] = now
            self._pending_modify.pop(uid, None)
            self._client.send({
                "type": MsgType.ANN_MODIFY,
                "image_stem": image.stem,
                "uid": uid,
                "data": annotation_modify_data(annotation),
            })
        else:
            self._pending_modify[uid] = (image, annotation)
            if not self._modify_timer.isActive():
                remaining = MODIFY_THROTTLE_MS - int((now - last) * 1000)
                self._modify_timer.start(max(1, remaining))

    def _flush_pending_modifies(self):
        if not self.is_in_lobby:
            self._pending_modify.clear()
            return
        now = time.monotonic()
        for uid, (image, annotation) in list(self._pending_modify.items()):
            self._last_modify_time[uid] = now
            self._client.send({
                "type": MsgType.ANN_MODIFY,
                "image_stem": image.stem,
                "uid": uid,
                "data": annotation_modify_data(annotation),
            })
        self._pending_modify.clear()

    def _on_local_ann_class_changed(self, image, annotation, new_class_id):
        if self._applying_remote or not self.is_in_lobby:
            return
        _dbg(f"GÖNDERİLİYOR ann_class_change: stem={image.stem} uid={annotation.uid[:8]} class={new_class_id}")
        self._client.send({
            "type": MsgType.ANN_CLASS_CHANGE,
            "image_stem": image.stem,
            "uid": annotation.uid,
            "new_class_id": new_class_id,
        })

    # ── Sınıf değişiklikleri ───────────────────────────────────────────

    def send_class_add(self, class_id: int, name: str, color: str):
        if not self.is_in_lobby:
            return
        self._client.send({
            "type": MsgType.CLASS_ADD,
            "class_id": class_id, "name": name, "color": color,
        })

    def send_class_rename(self, class_id: int, new_name: str):
        if not self.is_in_lobby:
            return
        self._client.send({
            "type": MsgType.CLASS_RENAME,
            "class_id": class_id, "new_name": new_name,
        })

    def send_class_delete(self, class_id: int):
        if not self.is_in_lobby:
            return
        self._client.send({
            "type": MsgType.CLASS_DELETE,
            "class_id": class_id,
        })

    # ── Uzak -> Yerel ──────────────────────────────────────────────────

    def _on_message(self, msg):
        _dbg(f"_on_message ÇAĞRILDI: type={msg.get('type') if isinstance(msg, dict) else type(msg)}")
        if not isinstance(msg, dict):
            _dbg(f"  HATA: msg dict değil! type={type(msg)} val={msg}")
            return
        msg_type = msg.get("type")
        if not msg_type:
            return

        handler = {
            MsgType.LOBBY_CREATED: self._handle_lobby_created,
            MsgType.LOBBY_JOINED: self._handle_lobby_joined,
            MsgType.USER_JOINED: self._handle_user_joined,
            MsgType.USER_LEFT: self._handle_user_left,
            MsgType.PRESENCE_UPDATE: self._handle_presence_update,
            MsgType.ERROR: self._handle_error,
            MsgType.ANN_CREATE: self._handle_remote_ann_create,
            MsgType.ANN_DELETE: self._handle_remote_ann_delete,
            MsgType.ANN_MODIFY: self._handle_remote_ann_modify,
            MsgType.ANN_CLASS_CHANGE: self._handle_remote_ann_class_change,
            MsgType.CLASS_ADD: self._handle_remote_class_add,
            MsgType.CLASS_RENAME: self._handle_remote_class_rename,
            MsgType.CLASS_DELETE: self._handle_remote_class_delete,
        }.get(msg_type)

        if handler:
            try:
                handler(msg)
            except Exception as e:
                _dbg(f"HATA mesaj işlenirken ({msg_type}): {e}")
                import traceback
                traceback.print_exc()

    def _handle_lobby_created(self, msg: dict):
        self._lobby_id = msg["lobby_id"]
        self._user_id = msg["user_id"]
        self._user_color = msg.get("color")
        self._presence.set_my_user_id(self._user_id)
        _dbg(f"Lobi oluşturuldu: {self._lobby_id}")
        self.lobby_created.emit(self._lobby_id)

    def _handle_lobby_joined(self, msg: dict):
        self._lobby_id = msg["lobby_id"]
        self._user_id = msg["user_id"]
        self._user_color = msg.get("color")
        manifest = msg.get("manifest")
        self._presence.set_my_user_id(self._user_id)
        _dbg(f"Lobiye katılındı: {self._lobby_id}")
        self.lobby_joined.emit(self._lobby_id, manifest or {})

    def _handle_user_joined(self, msg: dict):
        _dbg(f"Kullanıcı katıldı: {msg.get('display_name')}")
        self._presence.on_user_joined(
            msg["user_id"], msg["display_name"], msg.get("color", "#888")
        )

    def _handle_user_left(self, msg: dict):
        _dbg(f"Kullanıcı ayrıldı: {msg.get('display_name')}")
        self._presence.on_user_left(msg["user_id"])

    def _handle_presence_update(self, msg: dict):
        self._presence.update_presence(msg.get("users", []))

    def _handle_error(self, msg: dict):
        error_msg = msg.get("message", "Bilinmeyen hata")
        _dbg(f"Sunucu hatası: {error_msg}")
        self.error_occurred.emit(error_msg)

    # ── Uzak annotation işlemleri ──────────────────────────────────────

    def _find_image_by_stem(self, stem: str):
        if not self._dataset:
            _dbg(f"UYARI: _dataset None! stem={stem}")
            return None
        for img in self._dataset.images.values():
            if img.stem == stem:
                return img
        _dbg(f"UYARI: Görsel bulunamadı: stem={stem}")
        return None

    def _is_current_image(self, image) -> bool:
        if not self._ann_ctrl:
            return False
        return self._ann_ctrl._current_image is image

    def _ensure_labels_loaded(self, image):
        """Tembel yükleme yapılmadıysa önce diskteki etiketleri yükle."""
        if image._pending_label_path is not None:
            image.load_pending_labels()

    def _handle_remote_ann_create(self, msg: dict):
        stem = msg["image_stem"]
        image = self._find_image_by_stem(stem)
        if not image:
            return

        ann_data = msg["annotation"]
        ann = dict_to_annotation(ann_data)
        _dbg(f"ALINDI ann_create: stem={stem} uid={ann.uid[:8]} type={ann.ann_type.value}")

        # Önce tembel yüklemeyi yap (diskten oku) - yoksa ileride üzerine yazılır
        self._ensure_labels_loaded(image)

        # Duplicate kontrol
        for existing in image.annotations:
            if existing.uid == ann.uid:
                _dbg(f"  -> Duplicate, atlıyor: uid={ann.uid[:8]}")
                return

        self._applying_remote = True
        try:
            image.annotations.append(ann)
            image.mark_dirty()

            # Hemen diske yaz (create/delete için debounce değil, anında)
            self._save_image_now(image)

            is_current = self._is_current_image(image)
            _dbg(f"  -> Model'e eklendi. annotations={len(image.annotations)} is_current={is_current}")

            if is_current:
                self._add_annotation_to_canvas(image, ann)
                self._ann_ctrl._notify_change()
                self._ann_ctrl.scene.update()
                _dbg(f"  -> Canvas'a eklendi")
        finally:
            self._applying_remote = False

    def _handle_remote_ann_delete(self, msg: dict):
        stem = msg["image_stem"]
        image = self._find_image_by_stem(stem)
        if not image:
            return

        uid = msg["uid"]
        _dbg(f"ALINDI ann_delete: stem={stem} uid={uid[:8]}")

        self._ensure_labels_loaded(image)

        self._applying_remote = True
        try:
            ann = self._find_annotation(image, uid)
            if not ann:
                _dbg(f"  -> Annotation bulunamadı, atlıyor")
                return

            image.annotations.remove(ann)
            image.mark_dirty()
            self._save_image_now(image)

            if self._is_current_image(image):
                canvas_item = self._ann_ctrl._ann_to_item.pop(uid, None)
                if canvas_item:
                    self._ann_ctrl._item_to_ann.pop(id(canvas_item), None)
                    self._ann_ctrl.scene.remove_annotation_item(canvas_item)
                self._ann_ctrl._notify_change()
                self._ann_ctrl.scene.update()
                _dbg(f"  -> Canvas'tan silindi")
        finally:
            self._applying_remote = False

    def _handle_remote_ann_modify(self, msg: dict):
        stem = msg["image_stem"]
        image = self._find_image_by_stem(stem)
        if not image:
            return

        uid = msg["uid"]
        data = msg["data"]

        self._ensure_labels_loaded(image)

        self._applying_remote = True
        try:
            ann = self._find_annotation(image, uid)
            if not ann:
                _dbg(f"  UYARI ann_modify: annotation bulunamadı! uid={uid[:8]} stem={stem} mevcut_uid'ler={[a.uid[:8] for a in image.annotations[:5]]}")
                return

            apply_modify_data(ann, data)
            image.mark_dirty()
            self._schedule_remote_save(image)

            if self._is_current_image(image):
                canvas_item = self._ann_ctrl._ann_to_item.get(uid)
                if canvas_item and hasattr(canvas_item, 'update_from_annotation'):
                    canvas_item.update_from_annotation()
                    self._ann_ctrl.scene.update()
        finally:
            self._applying_remote = False

    def _handle_remote_ann_class_change(self, msg: dict):
        image = self._find_image_by_stem(msg["image_stem"])
        if not image:
            return

        uid = msg["uid"]
        new_class_id = msg["new_class_id"]
        _dbg(f"ALINDI ann_class_change: uid={uid[:8]} new_class={new_class_id}")

        self._ensure_labels_loaded(image)

        self._applying_remote = True
        try:
            ann = self._find_annotation(image, uid)
            if not ann:
                _dbg(f"  UYARI: annotation bulunamadı! uid={uid[:8]}")
                return

            ann.class_id = new_class_id
            image.mark_dirty()
            self._save_image_now(image)

            if self._is_current_image(image):
                canvas_item = self._ann_ctrl._ann_to_item.get(uid)
                if canvas_item:
                    self._ann_ctrl._refresh_item_class(canvas_item, new_class_id)
                self._ann_ctrl._notify_change()
                self._ann_ctrl.scene.update()
        finally:
            self._applying_remote = False

    # ── Uzak sınıf işlemleri ───────────────────────────────────────────

    def _handle_remote_class_add(self, msg: dict):
        if not self._dataset:
            return
        if self._dataset.get_class_by_id(msg["class_id"]):
            return
        from PySide6.QtGui import QColor
        color_str = msg.get("color")
        color = QColor(color_str) if color_str else None
        self._dataset.add_class(msg["name"], color)
        if self._main_window and hasattr(self._main_window, 'class_panel'):
            self._main_window.class_panel.load_classes(self._dataset.classes)

    def _handle_remote_class_rename(self, msg: dict):
        if not self._dataset:
            return
        cls = self._dataset.get_class_by_id(msg["class_id"])
        if cls:
            cls.name = msg["new_name"]
            if self._main_window and hasattr(self._main_window, 'class_panel'):
                self._main_window.class_panel.load_classes(self._dataset.classes)

    def _handle_remote_class_delete(self, msg: dict):
        if not self._dataset:
            return
        self._dataset.remove_class(msg["class_id"])
        if self._main_window and hasattr(self._main_window, 'class_panel'):
            self._main_window.class_panel.load_classes(self._dataset.classes)

    # ── Yardımcı ───────────────────────────────────────────────────────

    def _find_annotation(self, image, uid: str):
        for a in image.annotations:
            if a.uid == uid:
                return a
        return None

    def _add_annotation_to_canvas(self, image, ann):
        if not self._ann_ctrl or not self._dataset:
            _dbg(f"  -> UYARI: ann_ctrl={self._ann_ctrl is not None} dataset={self._dataset is not None}")
            return
        image.load_dimensions()
        img_w, img_h = image.width, image.height
        if img_w == 0 or img_h == 0:
            _dbg(f"  -> UYARI: Görsel boyutları 0! w={img_w} h={img_h}")
            return
        item = self._ann_ctrl._create_canvas_item(ann, img_w, img_h)
        if item:
            self._ann_ctrl.scene.add_annotation_item(item)
            self._ann_ctrl._item_to_ann[id(item)] = ann
            self._ann_ctrl._ann_to_item[ann.uid] = item
            item.signals.geometry_changed.connect(
                lambda it: self._ann_ctrl._on_item_geometry_changed(it)
            )
            item.signals.move_finished.connect(
                lambda it, old, new: self._ann_ctrl._on_item_move_finished(it, old, new)
            )
        else:
            _dbg(f"  -> UYARI: Canvas item oluşturulamadı! ann_type={ann.ann_type}")

    def _save_image_now(self, image):
        """Hemen diske yazar (create/delete için)."""
        if self._main_window and hasattr(self._main_window, '_write_image_labels'):
            self._main_window._write_image_labels(image)

    def _schedule_remote_save(self, image):
        """Modify için debounce'lu disk yazma."""
        self._remote_dirty_images.add(id(image))
        if not self._remote_save_timer.isActive():
            self._remote_save_timer.start(REMOTE_SAVE_DEBOUNCE_MS)

    def _flush_remote_saves(self):
        if not self._main_window or not self._dataset:
            self._remote_dirty_images.clear()
            return
        for img in self._dataset.images.values():
            if id(img) in self._remote_dirty_images and img.dirty:
                self._main_window._write_image_labels(img)
        self._remote_dirty_images.clear()

    def _build_manifest(self) -> dict:
        if not self._dataset:
            return {}
        images = [img.stem for img in self._dataset.get_all_images()]
        classes = []
        for cls in self._dataset.classes:
            classes.append({
                "id": cls.id,
                "name": cls.name,
                "color": cls.color.name() if cls.color else None,
            })
        return {
            "images": images,
            "classes": classes,
            "task_type": self._dataset.task_type.value if self._dataset.task_type else None,
        }
