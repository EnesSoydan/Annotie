"""0008 güvenlik migrasyonu ve presign v2 sözleşme testleri (SQL çalıştırılmaz)."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "supabase" / "migrations" / "0008_security_hardening.sql"
PRESIGN_PATH = ROOT / "supabase" / "functions" / "storage-presign" / "index.ts"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


class SecurityHardeningMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = _normalize(MIGRATION_PATH.read_text(encoding="utf-8"))
        cls.ts = PRESIGN_PATH.read_text(encoding="utf-8")

    def test_role_changes_are_bounded(self):
        self.assertIn("when 'owner' then p_role in ('admin', 'annotator', 'viewer')", self.sql)
        self.assertIn("when 'admin' then p_role in ('annotator', 'viewer')", self.sql)
        for policy in ("memberships_insert", "memberships_update", "invites_insert"):
            self.assertIn(f"create policy {policy}", self.sql)
        self.assertIn("using (public.can_manage_role(team_id, role)) "
                      "with check (public.can_manage_role(team_id, role))", self.sql)
        self.assertIn("grant update (role) on public.memberships to authenticated", self.sql)
        self.assertIn("grant update (name) on public.teams to authenticated", self.sql)

    def test_invite_tokens_hidden_and_bound_to_invitee(self):
        self.assertIn("public.has_team_role(team_id, array['owner', 'admin']::team_role[]) "
                      "or invited_user_id = auth.uid()", self.sql)
        self.assertIn("v_invite.invited_user_id <> auth.uid()", self.sql)
        self.assertIn("lower(v_email) <> lower(v_invite.email)", self.sql)
        self.assertIn("baska bir hesaba ait", self.sql)

    def test_control_columns_not_client_writable(self):
        grants = re.findall(r"grant (?:insert|update) \(([^)]*)\) on public\.(images|datasets)",
                            self.sql)
        self.assertEqual(len(grants), 4)
        for columns, _table in grants:
            for forbidden in ("annotations_migrated_at", "collaboration_sequence",
                              "collab_schema_version"):
                self.assertNotIn(forbidden, columns)
        self.assertIn("revoke insert, update on public.images from anon, authenticated", self.sql)
        self.assertIn("revoke insert, update on public.datasets from anon, authenticated",
                      self.sql)

    def test_migration_rpc_never_deletes_rows(self):
        body = self.sql.split("create or replace function public.migrate_image_annotations_v2", 1)[1]
        body = body.split("$$;", 1)[0]
        self.assertNotIn("delete from public.annotations", body)

    def test_filename_and_hash_checks(self):
        self.assertIn("add constraint images_filename_safe check", self.sql)
        self.assertIn("add constraint images_content_hash_sha256 check", self.sql)

    def test_legacy_blob_grants_populated_once_and_read_only(self):
        self.assertIn("if to_regclass('public.legacy_blob_grants') is null then", self.sql)
        self.assertIn("revoke insert, update, delete on public.legacy_blob_grants", self.sql)

    def test_relay_role_rpc(self):
        self.assertIn("create or replace function public.my_dataset_role(p_dataset_id uuid)",
                      self.sql)
        self.assertIn("grant execute on function public.my_dataset_role(uuid) to authenticated",
                      self.sql)

    def test_presign_uses_team_scoped_keys(self):
        self.assertIn("teams/${ds.team_id}/blobs/${contentHash}", self.ts)
        self.assertIn('.from("legacy_blob_grants")', self.ts)
        self.assertIn('.eq("dataset_id", datasetId).eq("content_hash", contentHash)', self.ts)
        # Anahtar istemcinin yazdığı storage_key'den türetilmemeli
        self.assertNotIn("storage_key", self.ts.split("Deno.serve", 1)[1])


if __name__ == "__main__":
    unittest.main()
