"""Current-version contracts, using disposable stores and an independent v1 fixture."""

from contextlib import closing
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TRACKER = ROOT / "skills/think3/scripts/tracker.py"

# Original schema-1 contract, intentionally not generated from the current schema.
LEGACY_SCHEMA = """
PRAGMA application_id = 1414023987;
PRAGMA user_version = 1;
CREATE TABLE items (
 id TEXT PRIMARY KEY NOT NULL, key TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL, scope TEXT NOT NULL, action TEXT NOT NULL,
 basis TEXT NOT NULL, trigger TEXT NOT NULL, success TEXT NOT NULL,
 supersedes TEXT REFERENCES items(id),
 status TEXT NOT NULL CHECK(status IN ('proposed','implemented','verified','withdrawn')),
 revision INTEGER NOT NULL CHECK(revision >= 1),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, verification_evidence TEXT
);
CREATE TABLE events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL REFERENCES items(id),
 kind TEXT NOT NULL CHECK(kind IN ('created','transitioned')),
 from_status TEXT, to_status TEXT NOT NULL, revision INTEGER NOT NULL,
 note TEXT NOT NULL, evidence TEXT, created_at TEXT NOT NULL,
 UNIQUE(item_id,revision)
);
CREATE INDEX events_by_item ON events(item_id,id);
INSERT INTO items VALUES ('legacy','legacy-key','Original title','synthetic','Keep history',
 'Legacy fixture','Explicit test','Records survive',NULL,'proposed',1,
 '2026-10-30T00:00:00+00:00','2026-10-30T00:00:00+00:00',NULL);
INSERT INTO events VALUES (7,'legacy','created',NULL,'proposed',1,
 'Original event',NULL,'2026-10-30T00:00:00+00:00');
"""


class CurrentContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="think3-current-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = self.root / "ledger.sqlite3"

    def invoke(self, *args, error=None, store=None, env=None, script=TRACKER):
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--store", str(store or self.store), *map(str, args)],
            cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode == 0, error is None, result.stderr or result.stdout)
        value = json.loads(result.stderr if error else result.stdout)
        if error:
            self.assertEqual(value["error"]["code"], error)
        return value

    def add(self):
        return self.invoke("add", "--key", "current", "--title", "Synthetic item", "--scope", "test",
                           "--action", "Check", "--basis", "Fixture", "--trigger", "Explicit",
                           "--success", "Round-trip")["item"]

    def legacy(self):
        with closing(sqlite3.connect(self.store)) as db:
            db.executescript(LEGACY_SCHEMA)

    def test_version_without_store_creates_no_files(self):
        result = subprocess.run([sys.executable, "-B", str(TRACKER), "--version"], cwd=self.root,
                                capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = (TRACKER.parent.parent / "SKILL.md").read_text(encoding="utf-8")
        declared = re.search(r'^  version: "([^"]+)"$', metadata, re.M).group(1)
        self.assertEqual(json.loads(result.stdout), {"name": "think3", "version": declared, "schema_version": 2})
        self.assertEqual(list(self.root.iterdir()), [])

    def test_relocated_version_and_export_follow_entrypoint(self):
        destination = self.root / "relocated"
        shutil.copytree(TRACKER.parent.parent, destination)
        entry = destination / "SKILL.md"
        text = re.sub(r'^  version: "[^"]+"$', '  version: "9.8.7"',
                      entry.read_text(encoding="utf-8"), count=1, flags=re.M)
        entry.write_text(text, encoding="utf-8")
        script = destination / "scripts/tracker.py"
        self.assertEqual(self.invoke("--version", script=script)["version"], "9.8.7")
        self.invoke("init", script=script)
        self.assertEqual(self.invoke("export", script=script)["generator"]["version"], "9.8.7")

    def test_observation_preserves_verified_evidence_and_withdrawal(self):
        self.invoke("init")
        item = self.add()
        for revision, status in [(1, "implemented"), (2, "verified"), (3, "withdrawn")]:
            item = self.invoke("transition", item["id"], "--to", status, "--expected-revision", revision,
                               "--note", "Synthetic transition", "--evidence", "Original evidence")["item"]
        before = self.invoke("export")
        item = self.invoke("observe", item["id"], "--expected-revision", 4,
                           "--note", "New observation", "--evidence", "New fixture")["item"]
        self.assertEqual(item["status"], "withdrawn")
        self.assertEqual(item["revision"], 5)
        self.assertEqual(item["verification_evidence"], before["items"][0]["verification_evidence"])
        after = self.invoke("export")
        self.assertEqual(after["events"][:-1], before["events"])
        self.assertEqual(after["events"][-1]["kind"], "observed")
        self.invoke("observe", item["id"], "--expected-revision", 4, "--note", "Stale",
                    "--evidence", "Stale", error="revision_conflict")
        self.assertEqual(self.invoke("export"), after)

    def test_legacy_init_and_reads_do_not_migrate(self):
        self.legacy()
        before = self.store.read_bytes()
        exported = self.invoke("export")
        self.assertEqual(exported["schema_version"], 1)
        self.assertEqual(self.invoke("init")["schema_version"], 1)
        self.invoke("observe", "legacy", "--expected-revision", 1, "--note", "New",
                    "--evidence", "New", error="migration_required")
        self.assertEqual(self.store.read_bytes(), before)

    def test_migration_preserves_records_and_event_sequence(self):
        self.legacy()
        before = self.invoke("export")
        self.assertTrue(self.invoke("migrate")["migrated"])
        after = self.invoke("export")
        self.assertEqual(after["schema_version"], 2)
        self.assertEqual(after["items"], before["items"])
        self.assertEqual(after["events"], before["events"])
        self.assertFalse(self.invoke("migrate")["migrated"])
        self.invoke("observe", "legacy", "--expected-revision", 1, "--note", "New", "--evidence", "New")
        self.assertEqual(self.invoke("history")["events"][-1]["id"], 8)
        with closing(sqlite3.connect(self.store)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_migration_rejects_external_cascade_without_changes(self):
        self.legacy()
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("CREATE TABLE external_notes(event_id INTEGER REFERENCES events(id) ON DELETE CASCADE)")
            db.execute("INSERT INTO external_notes VALUES (7)")
            db.commit()
        before = self.store.read_bytes()
        self.invoke("migrate", error="unsupported_migration")
        self.assertEqual(self.store.read_bytes(), before)
        with closing(sqlite3.connect(self.store)) as db:
            self.assertEqual(db.execute("SELECT event_id FROM external_notes").fetchall(), [(7,)])

    def test_custom_codex_memory_directories_are_protected(self):
        codex = self.root / "custom-home"
        env = dict(os.environ, CODEX_HOME=str(codex))
        for name in ["memories", "memories_v2"]:
            self.invoke("init", store=codex / name / "forbidden.sqlite3", env=env, error="protected_store")
        self.assertFalse(codex.exists())


if __name__ == "__main__":
    unittest.main()
