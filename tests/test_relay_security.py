"""Relay güvenliği: kapalı varsayılan mod, rol kontrolü, şema, hız/boyut sınırı."""

import sys
import unittest
import warnings
from pathlib import Path
from unittest import mock

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import protocol  # noqa: E402
import security  # noqa: E402

ROOM = "0f8fad5b-d9cb-469f-a165-70867728950e"


class ProtocolValidationTests(unittest.TestCase):
    def test_rejects_wrong_field_types(self):
        cases = [
            {"type": "ann_delete", "image_stem": "a", "uid": 5},
            {"type": "ann_class_change", "image_stem": "a", "uid": "u", "new_class_id": True},
            {"type": "ann_modify", "image_stem": "a", "uid": "u", "data": "x"},
            {"type": "join_room", "room_id": "../../etc", "display_name": "A"},
            {"type": "join_room", "room_id": ROOM, "display_name": "A" * 65},
            ["not", "a", "dict"],
        ]
        for msg in cases:
            with self.subTest(msg=msg):
                self.assertIsNotNone(protocol.validate_message(msg))

    def test_accepts_client_messages(self):
        ok = [
            {"type": "join_room", "room_id": ROOM, "display_name": "A", "token": "t"},
            {"type": "class_add", "class_id": 0, "name": "car", "color": None},
            {"type": "ann_create", "image_stem": "img", "annotation": {"uid": "u"}},
            {"type": "heartbeat"},
        ]
        for msg in ok:
            with self.subTest(msg=msg):
                self.assertIsNone(protocol.validate_message(msg))

    def test_sanitize_drops_unknown_fields(self):
        msg = {"type": "ann_delete", "image_stem": "a", "uid": "u",
               "user_id": "spoof", "seq": 99}
        self.assertEqual(protocol.sanitize_message(msg),
                         {"type": "ann_delete", "image_stem": "a", "uid": "u"})

    def test_clean_display_name(self):
        self.assertEqual(protocol.clean_display_name("  Ali\x00\n "), "Ali")
        self.assertEqual(protocol.clean_display_name("\x07"), "Kullanıcı")


class SecurityRuleTests(unittest.TestCase):
    def test_auth_mode_is_fail_closed(self):
        self.assertEqual(security.load_settings({}).auth_mode, security.AUTH_MISCONFIGURED)
        self.assertEqual(
            security.load_settings({"SUPABASE_URL": "https://x.supabase.co"}).auth_mode,
            security.AUTH_MISCONFIGURED)
        self.assertEqual(
            security.load_settings({"RELAY_INSECURE_OPEN": "1"}).auth_mode,
            security.AUTH_OPEN)
        s = security.load_settings({"SUPABASE_URL": "https://x.supabase.co/",
                                    "SUPABASE_ANON_KEY": "k", "RELAY_INSECURE_OPEN": "1"})
        self.assertEqual(s.auth_mode, security.AUTH_SUPABASE)
        self.assertEqual(s.supabase_url, "https://x.supabase.co")

    def test_viewer_cannot_send_edits(self):
        self.assertFalse(security.can_send("viewer", "ann_create"))
        self.assertFalse(security.can_send(None, "class_delete"))
        self.assertTrue(security.can_send("viewer", "image_focus"))
        self.assertTrue(security.can_send("annotator", "ann_modify"))

    def test_token_bucket(self):
        now = [0.0]
        bucket = security.TokenBucket(rate=1.0, burst=2, clock=lambda: now[0])
        self.assertTrue(bucket.allow())
        self.assertTrue(bucket.allow())
        self.assertFalse(bucket.allow())
        now[0] = 1.0
        self.assertTrue(bucket.allow())


try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi.testclient import TestClient
    import main
    from lobby import LobbyManager
except ImportError:  # pragma: no cover - sunucu bağımlılıkları yoksa
    main = None


@unittest.skipIf(main is None, "fastapi/httpx kurulu değil")
class RelayEndpointTests(unittest.TestCase):
    ROLES = {"annotator-token": "annotator", "viewer-token": "viewer"}

    def _patch(self, **settings):
        defaults = {"auth_mode": security.AUTH_SUPABASE,
                    "supabase_url": "https://x.supabase.co", "supabase_anon_key": "k"}
        defaults.update(settings)
        patches = [
            mock.patch.object(main, "SETTINGS", security.RelaySettings(**defaults)),
            mock.patch.object(main, "manager", LobbyManager()),
            mock.patch.dict(main.lobby_connections, clear=True),
            mock.patch.dict(main.connection_roles, clear=True),
            mock.patch.object(main, "fetch_dataset_role", self._fake_role),
            mock.patch.object(main, "verify_user_token", self._fake_verify),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    async def _fake_role(self, token, room_id):
        return self.ROLES.get(token)

    async def _fake_verify(self, token):
        return token in self.ROLES

    def _client(self):
        warnings.simplefilter("ignore")
        return TestClient(main.app)

    def _join(self, ws, token, name):
        ws.send_json({"type": "join_room", "room_id": ROOM,
                      "display_name": name, "token": token})
        return ws.receive_json()

    def test_refuses_to_start_without_auth_config(self):
        self._patch(auth_mode=security.AUTH_MISCONFIGURED)
        with self.assertRaises(RuntimeError):
            with self._client():
                pass

    def test_rejects_non_member(self):
        self._patch()
        with self._client() as client, client.websocket_connect("/ws") as ws:
            self.assertEqual(self._join(ws, "stranger", "X")["type"], "error")
            ws.send_json({"type": "ann_create", "image_stem": "a", "annotation": {}})
            self.assertIn("lobiye", ws.receive_json()["message"])

    def test_viewer_edits_are_blocked_and_spoofed_fields_dropped(self):
        self._patch()
        with self._client() as client, \
                client.websocket_connect("/ws") as annot, \
                client.websocket_connect("/ws") as viewer:
            self.assertEqual(self._join(annot, "annotator-token", "A")["type"], "lobby_joined")
            annot.receive_json()  # presence_update
            self.assertEqual(self._join(viewer, "viewer-token", "V")["type"], "lobby_joined")
            viewer.receive_json()  # presence_update
            annot.receive_json()   # user_joined
            annot.receive_json()   # presence_update

            viewer.send_json({"type": "ann_create", "image_stem": "img",
                              "annotation": {"uid": "x"}})
            self.assertEqual(viewer.receive_json()["type"], "error")

            annot.send_json({"type": "ann_create", "image_stem": "img",
                             "annotation": {"uid": "y"}, "user_id": "spoof", "extra": 1})
            relayed = viewer.receive_json()
            self.assertEqual(relayed["type"], "ann_create")
            self.assertNotEqual(relayed["user_id"], "spoof")
            self.assertNotIn("extra", relayed)
            self.assertEqual(relayed["user_name"], "A")

    def test_manual_lobby_requires_login_in_auth_mode(self):
        self._patch()
        with self._client() as client, client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "create_lobby", "display_name": "A"})
            self.assertEqual(ws.receive_json()["type"], "error")
            ws.send_json({"type": "create_lobby", "display_name": "A",
                          "token": "annotator-token"})
            self.assertEqual(ws.receive_json()["type"], "lobby_created")

    def test_open_mode_allows_tokenless_join(self):
        self._patch(auth_mode=security.AUTH_OPEN)
        with self._client() as client, client.websocket_connect("/ws") as ws:
            self.assertEqual(self._join(ws, None, "A")["type"], "lobby_joined")

    def test_message_size_and_rate_limits(self):
        self._patch(max_message_bytes=200, rate_per_sec=0.0, rate_burst=1)
        with self._client() as client, client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "heartbeat", "pad": "' + "x" * 300 + '"}')
            self.assertIn("büyük", ws.receive_json()["message"])
            ws.send_json({"type": "heartbeat"})
            ws.receive_json()  # önce lobiye katılın
            ws.send_json({"type": "heartbeat"})
            self.assertIn("Çok fazla", ws.receive_json()["message"])


if __name__ == "__main__":
    unittest.main()
