"""0007 kullanici modelleri migration sozlesme testleri."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "supabase" / "migrations" / "0007_user_models.sql"
PRESIGN_PATH = ROOT / "supabase" / "functions" / "storage-presign" / "index.ts"


class UserModelsMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normalized = re.sub(r"\s+", " ", MIGRATION_PATH.read_text(encoding="utf-8").lower())

    def test_table_and_constraints(self):
        self.assertIn("create table if not exists public.user_models", self.normalized)
        self.assertIn("unique (owner_id, name)", self.normalized)
        self.assertIn("check (format in ('onnx', 'pt'))", self.normalized)
        self.assertIn("content_hash text not null", self.normalized)

    def test_rls_is_owner_only(self):
        self.assertIn("alter table public.user_models enable row level security", self.normalized)
        for op in ("select", "insert", "update", "delete"):
            self.assertIn(f"create policy user_models_{op} on public.user_models", self.normalized)
        self.assertIn("for select to authenticated using (owner_id = auth.uid())", self.normalized)
        self.assertIn("for insert to authenticated with check (owner_id = auth.uid())", self.normalized)
        self.assertIn("using (owner_id = auth.uid()) with check (owner_id = auth.uid())",
                      self.normalized)
        self.assertIn("for delete to authenticated using (owner_id = auth.uid())", self.normalized)

    def test_presign_uses_per_user_model_prefix(self):
        ts = PRESIGN_PATH.read_text(encoding="utf-8")
        self.assertIn("models/${user.id}/${contentHash}", ts)
        self.assertIn('.from("user_models")', ts)
        self.assertIn("/^[0-9a-f]{64}$/", ts)


if __name__ == "__main__":
    unittest.main()
