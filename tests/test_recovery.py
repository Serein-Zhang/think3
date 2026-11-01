"""Recovery and first-initialization regressions using disposable stores only.

Run with ``python -B -m unittest discover -s tests -v``.  SQLite is deliberately
not allowed to reopen the foreign hot-journal fixture before its byte snapshot.
"""

import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TRACKER = Path(__file__).resolve().parents[1] / "skills" / "think3" / "scripts" / "tracker.py"


class TrackerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="think3-recovery-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = self.root / "tracker.sqlite3"
        self.environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def run_python(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", *map(str, arguments)],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            check=False,
        )

    def invoke(self, *arguments, store=None):
        return self.run_python(TRACKER, "--store", store or self.store, *arguments)

    def result_json(self, result, *, successful):
        detail = (
            f"command: {result.args!r}\nreturncode: {result.returncode}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        if successful:
            self.assertEqual(result.returncode, 0, detail)
            self.assertEqual(result.stderr, "", detail)
            payload = result.stdout
        else:
            self.assertNotEqual(result.returncode, 0, detail)
            self.assertEqual(result.stdout, "", detail)
            payload = result.stderr
        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            self.fail(f"Expected one JSON response.\n{detail}")
        self.assertIsInstance(data, dict, detail)
        return data

    def test_rejecting_foreign_hot_journal_preserves_database_and_journal_bytes(self):
        foreign = self.root / "foreign.sqlite3"
        # A tiny cache forces uncommitted changes out to the main database.
        # os._exit bypasses SQLite cleanup, retaining a genuine hot journal.
        fixture = self.run_python("-c", r'''
import os
import sqlite3
import sys

db = sqlite3.connect(sys.argv[1], isolation_level=None)
db.execute("PRAGMA page_size = 1024")
assert db.execute("PRAGMA journal_mode = DELETE").fetchone()[0] == "delete"
db.execute("PRAGMA synchronous = FULL")
db.execute("PRAGMA cache_size = 8")
db.execute("CREATE TABLE original_notes (id INTEGER PRIMARY KEY, body BLOB NOT NULL)")
db.execute("BEGIN IMMEDIATE")
db.executemany("INSERT INTO original_notes VALUES (?, ?)",
               ((index, b"A" * 700) for index in range(1, 513)))
db.execute("COMMIT")
db.execute("BEGIN IMMEDIATE")
db.execute("UPDATE original_notes SET body = ?", (b"B" * 700,))
os._exit(0)
''', foreign)
        self.assertEqual(fixture.returncode, 0, fixture.stderr)
        journal = Path(str(foreign) + "-journal")
        self.assertTrue(journal.is_file(), "Crash fixture did not retain its rollback journal.")
        before_database = foreign.read_bytes()
        before_journal = journal.read_bytes()
        self.assertGreater(len(before_journal), 512)
        self.assertEqual(before_journal[:8], bytes.fromhex("d9d505f920a163d7"),
                         "Fixture must have a live rollback-journal header.")

        rejected = self.invoke(
            "add", "--key", "foreign", "--title", "Foreign database",
            "--scope", "temporary regression", "--action", "Reject unchanged",
            "--basis", "Fixture is unrelated", "--trigger", "Explicit test",
            "--success", "Both original files retain every byte", store=foreign,
        )
        self.result_json(rejected, successful=False)
        # Check both assertions even if SQLite removed the journal as it rolled
        # back the unrelated database during identity validation.
        with self.subTest(file="database"):
            self.assertEqual(foreign.read_bytes(), before_database,
                             "Rejecting an unrelated database changed its main-file bytes.")
        with self.subTest(file="rollback journal"):
            self.assertTrue(journal.is_file(),
                            "Rejecting an unrelated database removed its rollback journal.")
            self.assertEqual(journal.read_bytes(), before_journal,
                             "Rejecting an unrelated database changed its rollback journal.")

    def test_failed_schema_initialization_can_be_retried_normally(self):
        injected = self.run_python("-c", r'''
import importlib.util
import json
from pathlib import Path
import sys
from unittest import mock

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("think3_fault_fixture", sys.argv[1])
tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker)
store = Path(sys.argv[2])
original_validate = tracker.validate_database

def fail_after_schema_creation(db):
    original_validate(db)
    raise RuntimeError("injected failure after new-schema validation")

with mock.patch.object(tracker, "validate_database", side_effect=fail_after_schema_creation):
    try:
        tracker.initialize(store)
    except RuntimeError as exc:
        assert str(exc) == "injected failure after new-schema validation"
    else:
        raise AssertionError("Schema-validation fault was not reached")
print(json.dumps({"exists_after_failure": store.exists(),
                  "bytes_after_failure": store.stat().st_size if store.exists() else None}))
''', TRACKER, self.store)
        fault_state = self.result_json(injected, successful=True)
        initialized = self.invoke("init")
        response = self.result_json(initialized, successful=True)
        self.assertIn("created", response, fault_state)
        exported = self.result_json(self.invoke("export"), successful=True)
        self.assertEqual(exported["items"], [], fault_state)
        self.assertEqual(exported["events"], [], fault_state)

    def make_owned_hot_journal(self):
        self.result_json(self.invoke("init"), successful=True)

        def add_arguments(key):
            return (
                "add", "--key", key, "--title", "Committed title",
                "--scope", "temporary recovery", "--action", "Retain committed data",
                "--basis", "Owned hot-journal fixture", "--trigger", "Explicit test",
                "--success", "Original item and audit event survive recovery",
            )

        original = self.result_json(self.invoke(*add_arguments("original")), successful=True)["item"]
        committed = self.result_json(self.invoke("export"), successful=True)
        # Dirty the committed item's page and then create enough uncommitted
        # rows to spill pages. Recovery must undo both parts of the transaction.
        fixture = self.run_python("-c", r'''
import os
import sqlite3
import sys

db = sqlite3.connect(sys.argv[1], isolation_level=None)
assert db.execute("PRAGMA journal_mode = DELETE").fetchone()[0] == "delete"
db.execute("PRAGMA synchronous = FULL")
db.execute("PRAGMA cache_size = 8")
db.execute("BEGIN IMMEDIATE")
db.execute("UPDATE items SET title = 'Uncommitted title' WHERE key = 'original'")
for index in range(256):
    db.execute("""INSERT INTO items
        SELECT ?, ?, title, scope, action, basis, trigger, success,
               supersedes, status, revision, created_at, updated_at, verification_evidence
        FROM items WHERE key = 'original'""",
        ("uncommitted-" + str(index), "uncommitted-" + str(index) + "x" * 1200))
os._exit(0)
''', self.store)
        self.assertEqual(fixture.returncode, 0, fixture.stderr)
        journal = Path(str(self.store) + "-journal")
        self.assertTrue(journal.is_file())
        self.assertEqual(journal.read_bytes()[:8], bytes.fromhex("d9d505f920a163d7"))

        return original, committed, add_arguments

    def test_owned_hot_journal_recovers_before_a_successful_add(self):
        original, committed, add_arguments = self.make_owned_hot_journal()
        journal = Path(str(self.store) + "-journal")
        added = self.result_json(self.invoke(*add_arguments("after-recovery")), successful=True)
        self.assertIs(added["created"], True)
        exported = self.result_json(self.invoke("export"), successful=True)
        self.assertEqual({item["id"]: item for item in exported["items"]},
                         {original["id"]: original, added["item"]["id"]: added["item"]})
        self.assertEqual(exported["events"][:len(committed["events"])], committed["events"])
        self.assertEqual(len(exported["events"]), len(committed["events"]) + 1)
        self.assertEqual(exported["events"][-1]["item_id"], added["item"]["id"])
        self.assertFalse(journal.exists())

    def test_reads_request_explicit_recovery_without_changing_owned_files(self):
        original, committed, _ = self.make_owned_hot_journal()
        journal = Path(str(self.store) + "-journal")
        before_database, before_journal = self.store.read_bytes(), journal.read_bytes()
        commands = [("list",), ("show", original["id"]), ("history",), ("export",)]
        for arguments in commands:
            with self.subTest(command=arguments[0]):
                response = self.result_json(self.invoke(*arguments), successful=False)
                self.assertEqual(response["error"]["code"], "recovery_required")
                self.assertIn("init", response["error"]["message"])
                self.assertIn("--store", response["error"]["message"])
                self.assertEqual(self.store.read_bytes(), before_database)
                self.assertEqual(journal.read_bytes(), before_journal)

        recovered = self.result_json(self.invoke("init"), successful=True)
        self.assertIs(recovered["created"], False)
        self.assertEqual(self.result_json(self.invoke("export"), successful=True), committed)
        self.assertFalse(journal.exists())
        for arguments in commands:
            with self.subTest(recovered_command=arguments[0]):
                self.result_json(self.invoke(*arguments), successful=True)

    def test_read_recovery_classification_handles_legacy_and_unrelated_errors(self):
        result = self.run_python("-c", r'''
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

spec = importlib.util.spec_from_file_location("think3_error_fixture", sys.argv[1])
tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker)
path = Path(sys.argv[2])
legacy = sqlite3.OperationalError("attempt to write a readonly database")
assert getattr(legacy, "sqlite_errorcode", None) is None
assert tracker.needs_read_recovery(legacy, path) is False
Path(str(path) + "-journal").write_bytes(b"synthetic identity-only fixture")
assert tracker.needs_read_recovery(legacy, path) is True
assert tracker.needs_read_recovery(sqlite3.OperationalError("database is locked"), path) is False
assert tracker.needs_read_recovery(ValueError("attempt to write a readonly database"), path) is False
coded = sqlite3.OperationalError("attempt to write a readonly database")
coded.sqlite_errorcode = 8  # SQLITE_READONLY, not SQLITE_READONLY_ROLLBACK
assert tracker.needs_read_recovery(coded, path) is False
coded.sqlite_errorcode = 776
assert tracker.needs_read_recovery(coded, path) is True
print(json.dumps({"classification": "passed"}))
''', TRACKER, self.store)
        self.result_json(result, successful=True)

    def test_concurrent_first_initializations_publish_one_valid_store(self):
        self.assertFalse(self.store.exists())
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.invoke("init"), range(8)))
        responses = [self.result_json(result, successful=True) for result in results]
        self.assertEqual(sum(response["created"] is True for response in responses), 1)
        self.assertEqual(sum(response["created"] is False for response in responses), 7)
        exported = self.result_json(self.invoke("export"), successful=True)
        self.assertEqual(exported["items"], [])
        self.assertEqual(exported["events"], [])
        repeated = self.result_json(self.invoke("init"), successful=True)
        self.assertIs(repeated["created"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
