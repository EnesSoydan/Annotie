"""Bulut annotation donusumu, migration ve diff senaryolari."""

import unittest
import uuid
import tempfile
import json
from pathlib import Path

from src.cloud.annotations import (
    AnnotationError,
    AnnotationService,
    annotation_to_cloud_payload,
    cloud_record_to_annotation,
    materialize_cloud_annotations,
    parse_legacy_label_content,
)
from src.models.annotation import BBoxAnnotation, PolygonAnnotation


class _Response:
    def __init__(self, data=None):
        self.data = data


class _RpcCall:
    def __init__(self, data=None):
        self._data = data

    def execute(self):
        return _Response(self._data)


class _AnnotationQuery:
    def __init__(self, records):
        self._records = records
        self._image_ids = None

    def select(self, _fields):
        return self

    def in_(self, _field, values):
        self._image_ids = {str(value) for value in values}
        return self

    def eq(self, _field, _value):
        return self

    def order(self, _field):
        return self

    def execute(self):
        rows = [
            row for row in self._records
            if self._image_ids is None or str(row["image_id"]) in self._image_ids
        ]
        return _Response(rows)


class _FakeClient:
    def __init__(self, records=None):
        self.records = records or []
        self.rpc_calls = []

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _RpcCall([])

    def table(self, name):
        if name != "annotations":
            raise AssertionError(name)
        return _AnnotationQuery(self.records)


class _RecordingAnnotationService(AnnotationService):
    def __init__(self):
        super().__init__("user", client=object())
        self.operations = []

    def _apply_operation(self, dataset_id, image_id, annotation_uid,
                         operation, base_version, payload):
        self.operations.append((operation, annotation_uid, base_version, payload))
        if payload is None:
            return {"uid": annotation_uid, "version": base_version + 1,
                    "class_index": 0, "type": "bbox", "data": {},
                    "is_deleted": True}
        return {**payload, "version": base_version + 1, "is_deleted": False}


class CloudAnnotationConversionTests(unittest.TestCase):
    def test_cloud_record_round_trip_preserves_geometry_uid_and_version(self):
        source = PolygonAnnotation(
            class_id=3,
            points=[(0.1, 0.2), (0.3, 0.4), (0.5, 0.6)],
        )
        source.version = 4
        payload = annotation_to_cloud_payload(source)
        record = {**payload, "version": source.version}

        restored = cloud_record_to_annotation(record)

        self.assertEqual(restored.uid, source.uid)
        self.assertEqual(restored.version, 4)
        self.assertEqual(restored.class_id, 3)
        self.assertEqual(restored.points, source.points)

    def test_legacy_content_is_parsed_for_migration(self):
        payloads = parse_legacy_label_content(
            "0 0.5 0.5 0.2 0.3\n1 0.1 0.2 0.3 0.4\n",
            task_type="bbox",
        )

        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[0]["type"], "bbox")
        self.assertEqual(payloads[0]["class_index"], 0)
        uuid.UUID(payloads[0]["uid"])

    def test_legacy_task_type_alias_is_supported(self):
        payloads = parse_legacy_label_content(
            "0 0.5 0.5 0.2 0.3\n",
            task_type="detect",
        )
        self.assertEqual(payloads[0]["type"], "bbox")

    def test_invalid_legacy_line_stops_migration(self):
        with self.assertRaises(AnnotationError):
            parse_legacy_label_content("0 broken line\n", task_type="bbox")

    def test_materialization_writes_yolo_and_versioned_identity_metadata(self):
        uid = str(uuid.uuid4())
        record = {
            "uid": uid,
            "class_index": 2,
            "type": "bbox",
            "data": {"x_center": 0.5, "y_center": 0.4, "width": 0.2, "height": 0.1},
            "version": 6,
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            label = root / "labels" / "frame.txt"

            self.assertTrue(materialize_cloud_annotations(root, label, [record]))
            metadata = json.loads((
                root / ".annotie" / "annotation_ids" / "labels" / "frame.txt.json"
            ).read_text(encoding="utf-8"))

            self.assertEqual(label.read_text(encoding="utf-8"),
                             "2 0.500000 0.400000 0.200000 0.100000\n")
            self.assertEqual(metadata["annotations"][0]["uid"], uid)
            self.assertEqual(metadata["annotations"][0]["version"], 6)


class CloudAnnotationServiceTests(unittest.TestCase):
    def test_ensure_v2_migrates_only_pending_images_then_finalizes(self):
        image_a = str(uuid.uuid4())
        image_b = str(uuid.uuid4())
        records = [{
            "image_id": image_a,
            "uid": str(uuid.uuid4()),
            "class_index": 0,
            "type": "bbox",
            "data": {"x_center": 0.5, "y_center": 0.5, "width": 0.2, "height": 0.3},
            "version": 1,
        }]
        client = _FakeClient(records)
        service = AnnotationService("user", client=client)

        grouped = service.ensure_dataset_v2(
            {"id": "dataset", "task_type": "bbox", "collab_schema_version": 1},
            [
                {"id": image_a, "label_content": "0 0.5 0.5 0.2 0.3"},
                {"id": image_b, "label_content": "", "annotations_migrated_at": "done"},
            ],
        )

        self.assertEqual([call[0] for call in client.rpc_calls], [
            "migrate_image_annotations_v2",
            "finalize_dataset_collab_v2",
        ])
        self.assertIn(image_a, grouped)

    def test_v2_viewer_path_only_reads_when_every_image_is_migrated(self):
        image_id = str(uuid.uuid4())
        client = _FakeClient([])
        service = AnnotationService("viewer", client=client)

        grouped = service.ensure_dataset_v2(
            {"id": "dataset", "collab_schema_version": 2},
            [{"id": image_id, "annotations_migrated_at": "done"}],
        )

        self.assertEqual(grouped, {})
        self.assertEqual(client.rpc_calls, [])

    def test_sync_splits_create_modify_class_change_and_delete(self):
        service = _RecordingAnnotationService()
        changed_class = BBoxAnnotation(2, 0.5, 0.5, 0.2, 0.3)
        changed_class.uid = str(uuid.uuid4())
        changed_geometry = BBoxAnnotation(1, 0.7, 0.5, 0.2, 0.3)
        changed_geometry.uid = str(uuid.uuid4())
        created = PolygonAnnotation(0, [(0.1, 0.1), (0.2, 0.2), (0.3, 0.1)])
        deleted_uid = str(uuid.uuid4())

        def known(annotation, class_index, version, x_center=None):
            payload = annotation_to_cloud_payload(annotation)
            payload["class_index"] = class_index
            if x_center is not None:
                payload["data"]["x_center"] = x_center
            return {**payload, "image_id": "image", "version": version}

        records = [
            known(changed_class, 1, 2),
            known(changed_geometry, 1, 4, x_center=0.5),
            {"image_id": "image", "uid": deleted_uid, "class_index": 0,
             "type": "bbox", "data": {}, "version": 3},
        ]

        result = service.sync_image(
            "dataset", "image",
            [changed_class, changed_geometry, created], records,
        )

        self.assertEqual([op[0] for op in service.operations], [
            "delete", "class_change", "modify", "create",
        ])
        self.assertEqual(changed_class.version, 3)
        self.assertEqual(changed_geometry.version, 5)
        self.assertEqual(created.version, 1)
        self.assertEqual({row["uid"] for row in result}, {
            changed_class.uid, changed_geometry.uid, created.uid,
        })


if __name__ == "__main__":
    unittest.main()
