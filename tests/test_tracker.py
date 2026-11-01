"""Black-box contract tests for the local think3 tracker.

Run from the project root with ``python -m unittest discover -s tests -v``.
Every database, including deliberately unrelated databases, lives in a temporary
directory. These tests use only the CLI's JSON interface and Python's stdlib.
"""

import concurrent.futures
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


TRACKER = Path(__file__).resolve().parents[1] / "skills" / "think3" / "scripts" / "tracker.py"
REQUIRED_ITEM_FIELDS = {
    "id", "key", "title", "scope", "action", "basis", "trigger", "success",
    "supersedes", "status", "revision", "created_at", "updated_at",
    "verification_evidence",
}


class TrackerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TRACKER.is_file():
            raise RuntimeError(f"Tracker implementation is missing: {TRACKER}")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="think3-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = self.root / "改进记录.sqlite3"

    def invoke(self, *arguments, store=None):
        return subprocess.run(
            [sys.executable, str(TRACKER), "--store", str(store or self.store), *map(str, arguments)],
            cwd=self.root,
            capture_output=True,
            encoding="utf-8",
            errors="strict",
            timeout=20,
            check=False,
        )

    def parse_result(self, result, *, successful):
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

    def ok(self, *arguments, store=None):
        return self.parse_result(self.invoke(*arguments, store=store), successful=True)

    def error(self, *arguments, store=None):
        return self.parse_result(self.invoke(*arguments, store=store), successful=False)

    @staticmethod
    def add_arguments(key="render-cache", **overrides):
        values = {
            "key": key,
            "title": "回放前核验缓存 🎬",
            "scope": "工作站/达芬奇",
            "action": "先核对缓存位置，再开始回放。",
            "basis": "上次记录：路径含空格，不能猜测。\n保留原始文件。",
            "trigger": "导入素材或升级驱动之后",
            "success": "连续回放通过；导出后读回通过。",
        }
        values.update(overrides)
        arguments = ["add"]
        for key, value in values.items():
            arguments.extend([f"--{key}", str(value)])
        return arguments

    def add(self, key="render-cache", **overrides):
        return self.ok(*self.add_arguments(key, **overrides))["item"]

    def transition(self, item, status, note="记录状态变化", evidence=None):
        arguments = [
            "transition", item["id"], "--to", status,
            "--expected-revision", item["revision"], "--note", note,
        ]
        if evidence is not None:
            arguments.extend(["--evidence", evidence])
        result = self.ok(*arguments)
        self.assertIs(result["changed"], True)
        updated = result["item"]
        self.assertEqual(updated["id"], item["id"])
        self.assertEqual(updated["status"], status)
        self.assertEqual(updated["revision"], item["revision"] + 1)
        self.assertEqual(updated["created_at"], item["created_at"])
        return updated

    def assert_error_preserves_store(self, *arguments):
        before = self.ok("export")
        self.error(*arguments)
        self.assertEqual(self.ok("export"), before)

    def test_reading_a_missing_store_does_not_create_files_or_directories(self):
        missing_store = self.root / "不存在" / "nested" / "tracker.sqlite3"
        for arguments in [("list",), ("show", "missing"), ("history",), ("history", "missing"), ("export",)]:
            with self.subTest(command=arguments):
                result = self.invoke(*arguments, store=missing_store)
                # An empty read or a JSON error is acceptable; creating a store is not.
                self.parse_result(result, successful=result.returncode == 0)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_init_is_idempotent_and_does_not_reset_owned_data(self):
        self.ok("init")
        self.assertTrue(self.store.is_file())
        item = self.add()
        original = self.ok("export")
        self.ok("init")
        self.assertEqual(self.ok("export"), original)
        self.assertEqual(self.ok("show", item["id"])["item"], item)

    def test_store_inside_skill_directory_is_rejected_without_creating_files(self):
        forbidden = TRACKER.parent.parent / f"forbidden-{self.root.name}.sqlite3"
        related = [Path(str(forbidden) + suffix) for suffix in ("", "-journal", "-wal", "-shm")]
        for path in related:
            self.assertFalse(path.exists(), f"Test path must not already exist: {path}")
        # Only submit the forbidden path; a correct implementation never writes here.
        result = self.invoke("init", store=forbidden)
        self.parse_result(result, successful=False)
        for path in related:
            self.assertFalse(path.exists(), f"A forbidden store file was created: {path}")

    def test_unrelated_files_and_databases_are_never_adopted_or_modified(self):
        foreign_file = self.root / "unrelated.sqlite3"
        foreign_file.write_bytes("用户原始文件\n不是数据库".encode("utf-8"))
        foreign_db = self.root / "foreign.sqlite3"
        with closing(sqlite3.connect(foreign_db)) as connection:
            connection.execute("CREATE TABLE original_notes (body TEXT NOT NULL)")
            connection.execute("INSERT INTO original_notes VALUES (?)", ("保留我",))
            connection.commit()
        for store in (foreign_file, foreign_db):
            original_bytes = store.read_bytes()
            for arguments in [("init",), tuple(self.add_arguments()), ("list",), ("export",)]:
                with self.subTest(store=store.name, command=arguments[0]):
                    self.error(*arguments, store=store)
                    self.assertEqual(store.read_bytes(), original_bytes)
            self.assertFalse(Path(str(store) + "-wal").exists())
            self.assertFalse(Path(str(store) + "-journal").exists())
        with closing(sqlite3.connect(foreign_db)) as connection:
            self.assertEqual(connection.execute("SELECT body FROM original_notes").fetchall(), [("保留我",)])

    def test_add_round_trips_utf8_and_is_idempotent_without_losing_history(self):
        self.ok("init")
        arguments = self.add_arguments()
        created = self.ok(*arguments)
        self.assertIs(created["created"], True)
        item = created["item"]
        self.assertTrue(REQUIRED_ITEM_FIELDS <= item.keys())
        self.assertTrue(item["id"])
        self.assertEqual(item["status"], "proposed")
        self.assertEqual(item["revision"], 1)
        self.assertIsNone(item["supersedes"])
        self.assertTrue(item["created_at"])
        self.assertTrue(item["updated_at"])
        for index in range(1, len(arguments), 2):
            self.assertEqual(item[arguments[index][2:]], arguments[index + 1])
        self.assertEqual(self.ok("show", item["id"])["item"], item)
        self.assertEqual(self.ok("list")["items"], [item])
        self.assertEqual(len(self.ok("history", item["id"])["events"]), 1)
        original = self.ok("export")
        repeated = self.ok(*arguments)
        self.assertIs(repeated["created"], False)
        self.assertEqual(repeated["item"], item)
        self.assertEqual(self.ok("export"), original)
        self.assert_error_preserves_store(*self.add_arguments(title="相同 key 的不同内容"))

        implemented = self.transition(item, "implemented", evidence="已实施：缓存路径截图")
        original = self.ok("export")
        repeated = self.ok(*arguments)
        self.assertIs(repeated["created"], False)
        self.assertEqual(repeated["item"], implemented)
        self.assertEqual(self.ok("export"), original)

    def test_state_changes_require_evidence_and_revision_and_keep_audit_history(self):
        self.ok("init")
        item = self.add()
        invalid_attempts = [
            ["transition", item["id"], "--to", "verified", "--expected-revision", 1, "--note", "跳步", "--evidence", "不能跳步"],
            ["transition", item["id"], "--to", "implemented", "--expected-revision", 1, "--note", "缺少证据"],
            ["transition", item["id"], "--to", "implemented", "--expected-revision", 1, "--note", "空白证据", "--evidence", " \t\n"],
            ["transition", item["id"], "--to", "implemented", "--expected-revision", 1, "--note", " \t", "--evidence", "已有证据"],
            ["transition", item["id"], "--to", "implemented", "--expected-revision", 0, "--note", "过期修订", "--evidence", "已有证据"],
        ]
        for arguments in invalid_attempts:
            with self.subTest(arguments=arguments):
                self.assert_error_preserves_store(*arguments)
        implemented = self.transition(item, "implemented", note="完成实施", evidence="实施证据：设置读回 甲")
        self.assertEqual(len(self.ok("history", item["id"])["events"]), 2)
        self.assert_error_preserves_store(
            "transition", item["id"], "--to", "verified", "--expected-revision", 1,
            "--note", "并发客户端使用旧修订", "--evidence", "旧请求不能写入",
        )
        self.assert_error_preserves_store(
            "transition", item["id"], "--to", "verified", "--expected-revision", 2,
            "--note", "验证仍需新证据",
        )
        self.assert_error_preserves_store(
            "transition", item["id"], "--to", "proposed", "--expected-revision", 2,
            "--note", "不能倒退",
        )
        verified = self.transition(implemented, "verified", note="实际工作流验证", evidence="验证证据：导出读回 乙")
        self.assertIn("验证证据：导出读回 乙", json.dumps(verified["verification_evidence"], ensure_ascii=False))
        withdrawn = self.transition(verified, "withdrawn", note="新条件出现，撤回但保留证据")
        self.assertEqual(withdrawn["verification_evidence"], verified["verification_evidence"])
        self.assertEqual(self.ok("show", item["id"])["item"], withdrawn)
        self.assertEqual(len(self.ok("history", item["id"])["events"]), 4)
        exported = self.ok("export")
        self.assertIn("实施证据：设置读回 甲", json.dumps(exported["events"], ensure_ascii=False))
        self.assertIn("验证证据：导出读回 乙", json.dumps(exported["events"], ensure_ascii=False))
        for status in ("proposed", "implemented", "verified", "withdrawn"):
            with self.subTest(terminal_transition=status):
                self.assert_error_preserves_store(
                    "transition", item["id"], "--to", status, "--expected-revision", 4,
                    "--note", "终态不能再次变化", "--evidence", "证据不能解除终态",
                )
        self.assert_error_preserves_store("delete", item["id"])
        self.assert_error_preserves_store("show", "does-not-exist")

    def test_withdrawal_is_allowed_from_each_nonterminal_state(self):
        self.ok("init")
        proposed = self.add("withdraw-proposed")
        implemented = self.add("withdraw-implemented")
        implemented = self.transition(implemented, "implemented", evidence="实施记录")
        for item in (proposed, implemented):
            withdrawn = self.transition(item, "withdrawn", note="范围不再适用")
            self.assertEqual(self.ok("show", item["id"])["item"], withdrawn)
            self.assertEqual(len(self.ok("history", item["id"])["events"]), withdrawn["revision"])

    def test_list_filters_use_exact_scope_and_substring_trigger(self):
        self.ok("init")
        first = self.add("first", scope="系统/图像", trigger="每次升级驱动后检查")
        second = self.add("second", scope="系统/图像增强", trigger="每次升级驱动后检查")
        third = self.add("third", scope="系统/图像", trigger="更换素材盘后检查")
        second = self.transition(second, "implemented", evidence="已实施")
        third = self.transition(third, "withdrawn", note="不适用")

        def ids(*arguments):
            return {item["id"] for item in self.ok("list", *arguments)["items"]}

        self.assertEqual(ids(), {first["id"], second["id"], third["id"]})
        self.assertEqual(ids("--scope", "系统/图像"), {first["id"], third["id"]})
        self.assertEqual(ids("--trigger", "升级驱动"), {first["id"], second["id"]})
        self.assertEqual(ids("--status", "implemented"), {second["id"]})
        self.assertEqual(ids("--status", "proposed", "--scope", "系统/图像", "--trigger", "升级驱动"), {first["id"]})
        self.assertEqual(ids("--status", "verified"), set())
        self.assertEqual(ids("--scope", "系统"), set())
        self.assertEqual(ids("--trigger", "从未出现的条件"), set())

    def test_supersedes_requires_an_existing_withdrawn_item(self):
        self.ok("init")
        original = self.add("original")
        self.assert_error_preserves_store(*self.add_arguments("replacement", supersedes="missing-id"))
        self.assert_error_preserves_store(*self.add_arguments("replacement", supersedes=original["id"]))
        implemented = self.transition(original, "implemented", evidence="原方案已实施")
        self.assert_error_preserves_store(*self.add_arguments("replacement", supersedes=original["id"]))
        withdrawn = self.transition(implemented, "withdrawn", note="由新方案替代")
        replacement = self.add("replacement", supersedes=withdrawn["id"], title="新条件下的替代方案")
        self.assertEqual(replacement["supersedes"], original["id"])
        self.assertNotEqual(replacement["id"], original["id"])
        self.assertEqual(replacement["status"], "proposed")
        self.assertEqual(replacement["revision"], 1)
        self.assertEqual(self.ok("show", original["id"])["item"], withdrawn)
        self.assertEqual(len(self.ok("list")["items"]), 2)

    def test_export_reconciles_with_items_and_per_item_history(self):
        self.ok("init")
        first = self.add("first")
        second = self.add("second")
        first = self.transition(first, "implemented", note="第一项实施", evidence="第一项证据")
        second = self.transition(second, "withdrawn", note="第二项撤回")
        first = self.transition(first, "verified", note="第一项验证", evidence="第一项验证证据")
        exported = self.ok("export")
        self.assertIn("schema_version", exported)
        self.assertEqual({item["id"]: item for item in exported["items"]}, {first["id"]: first, second["id"]: second})
        self.assertEqual(exported["events"], self.ok("history")["events"])
        self.assertEqual(len(exported["events"]), 5)
        per_item_events = []
        for item in (first, second):
            events = self.ok("history", item["id"])["events"]
            self.assertEqual(len(events), item["revision"])
            per_item_events.extend(events)
        canonical = lambda events: sorted(json.dumps(event, sort_keys=True, ensure_ascii=False) for event in events)
        self.assertEqual(canonical(exported["events"]), canonical(per_item_events))
        self.assertEqual({item["id"]: item for item in self.ok("list")["items"]}, {item["id"]: item for item in exported["items"]})

    def test_concurrent_identical_adds_create_one_item_and_one_event(self):
        self.ok("init")
        arguments = self.add_arguments("concurrent-key")
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _: self.invoke(*arguments), range(6)))
        responses = [self.parse_result(result, successful=True) for result in results]
        self.assertEqual(sum(response["created"] is True for response in responses), 1)
        self.assertEqual(len({response["item"]["id"] for response in responses}), 1)
        self.assertEqual(len(self.ok("list")["items"]), 1)
        self.assertEqual(len(self.ok("history")["events"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
