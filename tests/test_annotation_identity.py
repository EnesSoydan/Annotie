"""Kalici annotation kimligi ve .annotie metadata testleri."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from src.io.annotation_identity import identity_metadata_path
from src.io.label_reader import read_label_file
from src.io.label_writer import write_label_file


class AnnotationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.label_path = self.root / "labels" / "train" / "frame.txt"
        self.label_path.parent.mkdir(parents=True)
        self.label_path.write_text(
            "0 0.500000 0.500000 0.200000 0.300000\n"
            "1 0.250000 0.250000 0.100000 0.100000\n",
            encoding="utf-8",
        )
        self.identity_path = identity_metadata_path(self.root, self.label_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_metadata_is_created_and_reused(self):
        first = read_label_file(
            self.label_path,
            identity_metadata_path=self.identity_path,
        )
        second = read_label_file(
            self.label_path,
            identity_metadata_path=self.identity_path,
        )

        self.assertTrue(self.identity_path.exists())
        self.assertEqual([ann.uid for ann in first], [ann.uid for ann in second])
        for annotation in first:
            self.assertEqual(str(uuid.UUID(annotation.uid)), annotation.uid)

    def test_geometry_change_keeps_uid_after_save_and_reload(self):
        annotations = read_label_file(
            self.label_path,
            identity_metadata_path=self.identity_path,
        )
        original_uid = annotations[0].uid
        annotations[0].x_center = 0.75

        self.assertTrue(write_label_file(
            self.label_path,
            annotations,
            self.identity_path,
        ))
        reloaded = read_label_file(
            self.label_path,
            identity_metadata_path=self.identity_path,
        )

        self.assertEqual(reloaded[0].uid, original_uid)
        self.assertAlmostEqual(reloaded[0].x_center, 0.75)

    def test_reordered_lines_follow_fingerprint_identity(self):
        annotations = read_label_file(
            self.label_path,
            identity_metadata_path=self.identity_path,
        )
        expected_by_class = {ann.class_id: ann.uid for ann in annotations}
        self.label_path.write_text(
            "1 0.250000 0.250000 0.100000 0.100000\n"
            "0 0.500000 0.500000 0.200000 0.300000\n",
            encoding="utf-8",
        )

        reloaded = read_label_file(
            self.label_path,
            identity_metadata_path=self.identity_path,
        )

        self.assertEqual(
            {ann.class_id: ann.uid for ann in reloaded},
            expected_by_class,
        )

    def test_corrupt_metadata_is_replaced_with_valid_document(self):
        self.identity_path.parent.mkdir(parents=True)
        self.identity_path.write_text("{broken", encoding="utf-8")

        annotations = read_label_file(
            self.label_path,
            identity_metadata_path=self.identity_path,
        )
        payload = json.loads(self.identity_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["format_version"], 1)
        self.assertEqual(len(payload["annotations"]), len(annotations))
        self.assertEqual(
            [entry["uid"] for entry in payload["annotations"]],
            [ann.uid for ann in annotations],
        )

    def test_legacy_call_without_metadata_path_remains_deterministic(self):
        first = read_label_file(self.label_path)
        second = read_label_file(self.label_path)

        self.assertEqual([ann.uid for ann in first], [ann.uid for ann in second])
        self.assertFalse(self.identity_path.exists())

    def test_metadata_path_stays_under_dataset_annotie_directory(self):
        self.assertEqual(
            self.identity_path,
            self.root / ".annotie" / "annotation_ids" / "labels" / "train" / "frame.txt.json",
        )


if __name__ == "__main__":
    unittest.main()
