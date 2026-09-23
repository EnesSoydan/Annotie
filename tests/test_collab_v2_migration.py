"""0006 legacy label_content -> collaboration v2 migration sozlesmesi."""

import re
import unittest
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "0006_collab_v2_migration.sql"
)


class CollaborationV2MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION_PATH.read_text(encoding="utf-8")
        cls.normalized = re.sub(r"\s+", " ", cls.sql.lower())

    def test_adds_dataset_version_and_per_image_migration_marker(self):
        self.assertIn(
            "add column if not exists collab_schema_version int not null default 1",
            self.normalized,
        )
        self.assertIn(
            "add column if not exists annotations_migrated_at timestamptz",
            self.normalized,
        )
        self.assertIn("check (collab_schema_version in (1, 2))", self.normalized)

    def test_image_migration_is_locked_idempotent_and_validated(self):
        self.assertIn("function public.migrate_image_annotations_v2", self.normalized)
        function = self.normalized.split(
            "function public.migrate_image_annotations_v2", 1
        )[1].split("function public.finalize_dataset_collab_v2", 1)[0]
        self.assertIn("for update", function)
        self.assertIn("if v_migrated_at is not null", function)
        self.assertIn("delete from public.annotations where image_id = p_image_id", function)
        self.assertIn("perform public.annotation_yolo_line", function)
        self.assertIn("update public.images set annotations_migrated_at = now()", function)

    def test_finalize_requires_every_image_then_marks_v2(self):
        function = self.normalized.split(
            "function public.finalize_dataset_collab_v2", 1
        )[1]
        self.assertIn("annotations_migrated_at is null", function)
        self.assertIn("message = 'dataset_migration_incomplete'", function)
        self.assertIn("update public.datasets set collab_schema_version = 2", function)

    def test_snapshot_trigger_dual_writes_every_annotation_type(self):
        self.assertIn("function public.annotation_yolo_line", self.normalized)
        for annotation_type in ("classify", "bbox", "polygon", "obb", "keypoints"):
            self.assertIn(f"p_type = '{annotation_type}'", self.normalized)
        self.assertIn("function public.refresh_image_label_snapshot", self.normalized)
        self.assertIn("label_content = v_content", self.normalized)
        self.assertIn("create trigger annotation_refresh_label_snapshot", self.normalized)

    def test_migration_rpcs_are_authenticated_only(self):
        self.assertIn(
            "grant execute on function public.migrate_image_annotations_v2",
            self.normalized,
        )
        self.assertIn(
            "grant execute on function public.finalize_dataset_collab_v2",
            self.normalized,
        )
        self.assertIn("from public, anon", self.normalized)


if __name__ == "__main__":
    unittest.main()
