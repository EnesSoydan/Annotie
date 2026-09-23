"""0005 nesne bazli annotation migration sozlesme testleri."""

import re
import unittest
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "0005_annotation_operations.sql"
)


class AnnotationOperationsMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION_PATH.read_text(encoding="utf-8")
        cls.normalized = re.sub(r"\s+", " ", cls.sql.lower())

    def test_adds_dataset_sequence_and_annotation_tombstone(self):
        self.assertIn(
            "add column if not exists collaboration_sequence bigint not null default 0",
            self.normalized,
        )
        self.assertIn("add column if not exists is_deleted boolean", self.normalized)
        self.assertIn("add column if not exists deleted_at timestamptz", self.normalized)
        self.assertIn("annotations_version_positive", self.normalized)
        self.assertIn("annotations_tombstone_consistent", self.normalized)

    def test_event_log_is_ordered_and_idempotent(self):
        self.assertIn("create table if not exists public.annotation_events", self.normalized)
        self.assertIn("unique (dataset_id, sequence)", self.normalized)
        self.assertIn("unique (dataset_id, client_op_id)", self.normalized)
        self.assertIn("request_payload jsonb", self.normalized)
        self.assertIn("annotation_payload jsonb not null", self.normalized)
        self.assertIn("actor_id uuid not null", self.normalized)

    def test_rpc_serializes_before_idempotency_check(self):
        lock_position = self.normalized.index("for update")
        duplicate_position = self.normalized.index(
            "from public.annotation_events e where e.dataset_id = p_dataset_id"
        )
        image_check_position = self.normalized.index(
            "i.id = p_image_id and i.dataset_id = p_dataset_id"
        )
        self.assertLess(lock_position, duplicate_position)
        self.assertLess(duplicate_position, image_check_position)
        self.assertIn("result_was_duplicate boolean", self.normalized)
        self.assertIn("v_event.annotation_payload, true", self.normalized)
        self.assertIn("message = 'idempotency_key_reused'", self.normalized)
        self.assertIn(
            "v_event.request_payload is distinct from v_request_payload",
            self.normalized,
        )

    def test_rpc_uses_compare_and_swap_versions(self):
        self.assertIn("a.version = p_base_version", self.normalized)
        self.assertGreaterEqual(self.normalized.count("a.version = p_base_version"), 2)
        self.assertIn("version = a.version + 1", self.normalized)
        self.assertGreaterEqual(self.normalized.count("version = a.version + 1"), 2)
        self.assertIn("'conflict'::text", self.normalized)

    def test_class_change_cannot_mutate_geometry_or_type(self):
        class_change = self.normalized.split(
            "elsif p_operation = 'class_change' then", 1
        )[1].split("else update public.annotations", 1)[0]
        self.assertIn("class_index = v_class_index", class_change)
        self.assertNotIn("data = v_data,", class_change)
        self.assertNotIn("type = v_type,", class_change)
        self.assertIn("and a.type = v_type", class_change)
        self.assertIn("and a.data = v_data", class_change)

    def test_rpc_checks_auth_role_and_image_ownership(self):
        self.assertIn("v_actor uuid := auth.uid()", self.normalized)
        self.assertIn("public.has_team_role", self.normalized)
        self.assertIn("'owner', 'admin', 'annotator'", self.normalized)
        self.assertIn("i.id = p_image_id and i.dataset_id = p_dataset_id", self.normalized)
        self.assertIn(
            "jsonb_typeof(p_annotation->'class_index') is distinct from 'number'",
            self.normalized,
        )

    def test_direct_writes_are_blocked_and_event_reads_use_rls(self):
        self.assertIn("drop policy if exists annotations_write", self.normalized)
        self.assertIn(
            "revoke insert, update, delete on table public.annotations from anon, authenticated",
            self.normalized,
        )
        self.assertIn("alter table public.annotation_events enable row level security", self.normalized)
        self.assertIn("create policy annotation_events_select", self.normalized)
        self.assertIn("security definer", self.normalized)
        self.assertIn("grant execute on function public.apply_annotation_operation", self.normalized)


if __name__ == "__main__":
    unittest.main()
