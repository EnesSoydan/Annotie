"""P0-C: işbirliği tutarlılığı — rebase'li senkron, tombstone, retry, sayfalama."""

import os
import unittest
import uuid
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.cloud.annotations import (
    AnnotationConflict, AnnotationService, annotation_to_cloud_payload,
)
from src.cloud.auth import is_network_error
from src.models.annotation import BBoxAnnotation


class _FakeDb:
    """apply_annotation_operation (0005) kurallarının bellek içi taklidi."""

    def __init__(self):
        self.rows = {}

    def put(self, ann, version=1, deleted=False):
        payload = annotation_to_cloud_payload(ann)
        self.rows[ann.uid] = {**payload, "version": version, "is_deleted": deleted,
                              "image_id": "img"}

    def apply(self, uid, op, base_version, payload):
        row = self.rows.get(uid)
        if op == "create":
            if row is not None:
                raise AnnotationConflict(dict(row))
            self.rows[uid] = {**payload, "version": 1, "is_deleted": False, "image_id": "img"}
            return dict(self.rows[uid])
        if row is None or row["is_deleted"] or row["version"] != base_version:
            raise AnnotationConflict(dict(row) if row else None)
        if op == "delete":
            row.update(is_deleted=True, version=row["version"] + 1)
        else:
            row.update({**payload, "version": row["version"] + 1})
        return dict(row)

    def live(self):
        return [dict(r) for r in self.rows.values() if not r["is_deleted"]]


class _DbService(AnnotationService):
    def __init__(self, db):
        super().__init__("user", client=object())
        self.db = db
        self.ops = []

    def _apply_operation(self, dataset_id, image_id, uid, operation, base_version, payload):
        self.ops.append(operation)
        return self.db.apply(uid, operation, base_version, payload)

    def list_for_images(self, image_ids, chunk=100, page_size=1000):
        return self.db.live()


def _box(x=0.5, cls=0):
    ann = BBoxAnnotation(cls, x, 0.5, 0.1, 0.1)
    ann.uid = str(uuid.uuid4())
    return ann


def _row(ann, version):
    return {**annotation_to_cloud_payload(ann), "version": version, "image_id": "img"}


class RebaseSyncTests(unittest.TestCase):
    def test_stale_receiver_does_not_get_stuck_in_conflict(self):
        db = _FakeDb()
        a_old = _box(0.3)
        a_new = BBoxAnnotation(0, 0.6, 0.5, 0.1, 0.1)
        a_new.uid = a_old.uid
        db.put(a_new, version=2)            # gönderen DB'ye yazdı (v2)
        b = _box(0.8)                        # alıcının yeni nesnesi
        svc = _DbService(db)

        # Alıcı relay'den v2 geometrisini aldı, ama bilinen taban hâlâ v1
        result = svc.sync_image_detailed("ds", "img", [a_new, b], [_row(a_old, 1)])

        self.assertTrue(result.rebased)
        self.assertEqual(db.rows[a_new.uid]["version"], 2)  # gereksiz modify yok
        self.assertEqual(db.rows[b.uid]["version"], 1)
        self.assertEqual({r["uid"] for r in result.records}, {a_new.uid, b.uid})

    def test_unchanged_local_object_does_not_overwrite_remote_edit(self):
        db = _FakeDb()
        mine, theirs = _box(0.2), _box(0.4)
        base = [_row(mine, 1), _row(theirs, 1)]
        moved = BBoxAnnotation(0, 0.9, 0.5, 0.1, 0.1)
        moved.uid = theirs.uid
        db.put(mine, 1)
        db.put(moved, 2)                     # başkası 'theirs'i taşıdı
        mine.x_center = 0.25                 # ben yalnızca kendiminkini değiştirdim
        svc = _DbService(db)

        svc.sync_image_detailed("ds", "img", [mine, theirs], base)

        self.assertEqual(db.rows[theirs.uid]["data"]["x_center"], 0.9)
        self.assertEqual(db.rows[mine.uid]["data"]["x_center"], 0.25)

    def test_concurrent_edit_of_same_object_rebases_last_writer_wins(self):
        db = _FakeDb()
        a = _box(0.2)
        other = BBoxAnnotation(0, 0.7, 0.5, 0.1, 0.1)
        other.uid = a.uid
        db.put(other, 2)
        a.x_center = 0.3
        svc = _DbService(db)

        svc.sync_image_detailed("ds", "img", [a], [_row(_box(0.2), 1) | {"uid": a.uid}])

        self.assertEqual(db.rows[a.uid]["data"]["x_center"], 0.3)
        self.assertEqual(db.rows[a.uid]["version"], 3)

    def test_recreating_deleted_object_gets_new_uid(self):
        db = _FakeDb()
        a = _box()
        db.put(a, version=2, deleted=True)  # silindi (tombstone)
        svc = _DbService(db)

        result = svc.sync_image_detailed("ds", "img", [a], [])  # silme geri alındı

        new_uid = result.renamed[a.uid]
        self.assertNotEqual(new_uid, a.uid)
        self.assertFalse(db.rows[new_uid]["is_deleted"])
        self.assertTrue(db.rows[a.uid]["is_deleted"])

    def test_refresh_first_skips_the_failing_attempt(self):
        db = _FakeDb()
        a = _box()
        db.put(a, version=5)
        svc = _DbService(db)
        a.x_center = 0.1
        svc.sync_image_detailed("ds", "img", [a], [_row(_box(), 1) | {"uid": a.uid}],
                                refresh_first=True)
        self.assertEqual(svc.ops, ["modify"])


class _Rpc:
    def __init__(self, client):
        self._client = client

    def execute(self):
        self._client.calls += 1
        if self._client.calls == 1:
            raise ConnectionError("connection reset")
        return SimpleNamespace(data=[{"result_status": "applied",
                                      "result_annotation": {"uid": "u", "version": 1}}])


class _FlakyClient:
    def __init__(self):
        self.calls = 0
        self.params = []

    def rpc(self, name, params):
        self.params.append(params)
        return _Rpc(self)


class RetryAndPagingTests(unittest.TestCase):
    def test_transient_error_is_retried_with_same_op_id(self):
        client = _FlakyClient()
        svc = AnnotationService("user", client=client)
        svc._sleep = lambda _s: None
        row = svc._apply_operation("ds", "img", "u", "create", 0, {"uid": "u"})
        self.assertEqual(row["version"], 1)
        self.assertEqual(client.calls, 2)
        self.assertEqual(client.params[0]["p_client_op_id"], client.params[1]["p_client_op_id"])

    def test_list_for_images_pages_past_max_rows(self):
        rows = [{"uid": str(i), "image_id": "img"} for i in range(5)]

        class _Query:
            def __init__(self):
                self._range = None

            def select(self, *_a):
                return self

            def in_(self, *_a):
                return self

            def eq(self, *_a):
                return self

            def order(self, *_a):
                return self

            def range(self, start, end):
                self._range = (start, end)
                return self

            def execute(self):
                start, end = self._range
                return SimpleNamespace(data=rows[start:end + 1])

        client = SimpleNamespace(table=lambda _name: _Query())
        svc = AnnotationService("user", client=client)
        self.assertEqual(len(svc.list_for_images(["img"], page_size=2)), 5)


class NetworkErrorTests(unittest.TestCase):
    def test_classification(self):
        class ConnectError(Exception):
            pass

        class AuthApiError(Exception):
            pass

        self.assertTrue(is_network_error(ConnectError("x")))
        self.assertTrue(is_network_error(TimeoutError()))
        wrapped = RuntimeError("auth failed")
        wrapped.__cause__ = ConnectionError("reset")
        self.assertTrue(is_network_error(wrapped))
        self.assertFalse(is_network_error(AuthApiError("Invalid Refresh Token")))


class RemoteApplyTests(unittest.TestCase):
    def test_remote_changes_are_written_locally_without_db_sync(self):
        from PySide6.QtWidgets import QApplication
        from src.collab.collab_controller import CollabController

        QApplication.instance() or QApplication([])
        calls = []
        stale = []
        mw = SimpleNamespace(
            _write_image_labels=lambda image, sync=True: calls.append(sync),
            account_ctrl=SimpleNamespace(mark_cloud_image_stale=stale.append),
        )
        ctrl = CollabController()
        ctrl._main_window = mw
        image = SimpleNamespace(filename="a.jpg")
        ctrl._write_remote_change(image)
        self.assertEqual(calls, [False])
        self.assertEqual(stale, [image])


if __name__ == "__main__":
    unittest.main()
