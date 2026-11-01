#!/usr/bin/env python3
"""Run a relocation smoke check from a release archive using temporary synthetic data."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    archive_path = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="think3-release-") as directory:
        root = Path(directory).resolve()
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP CRC failed")
            for entry in archive.infolist():
                target = (root / entry.filename).resolve()
                if not target.is_relative_to(root) or not entry.filename.startswith("think3/"):
                    raise ValueError("Unexpected archive path")
            archive.extractall(root)
        tracker = root / "think3/scripts/tracker.py"
        store = root / "模拟项目/ledger.sqlite3"
        version_result = subprocess.run([sys.executable, "-B", str(tracker), "--version"],
                                        cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=20)
        require(version_result.returncode == 0, "Version query failed")
        version = json.loads(version_result.stdout)["version"]

        def run(*args):
            process = subprocess.run([sys.executable, str(tracker), "--store", str(store), *args],
                                     cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=20)
            if process.returncode != 0 or process.stderr:
                raise RuntimeError(process.stderr or process.stdout)
            return json.loads(process.stdout)

        require(run("init")["created"] is True, "Store was not created")
        result = run("add", "--key", "release-smoke", "--title", "模拟跟进项",
                     "--scope", "发布包临时测试", "--action", "等待下一次模拟验证",
                     "--basis", "人工构造夹具", "--trigger", "人工触发", "--success", "字段可读回")
        item = result["item"]
        require(item["status"] == "proposed", "Unexpected initial status")
        require(run("show", item["id"])["item"] == item, "Item did not round-trip")
        observed = run("observe", item["id"], "--expected-revision", "1",
                       "--note", "Synthetic archive observation", "--evidence", "Temporary fixture")
        require(observed["item"]["revision"] == 2, "Observation revision did not advance")
        require(observed["item"]["status"] == "proposed", "Observation changed status")
        exported = run("export")
        require(len(exported["items"]) == 1 and len(exported["events"]) == 2,
                "Exported item/event counts differ")
        require(exported["generator"]["version"] == version, "Archive version differs")
        result = {"result": "passed", "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                  "checks": ["CRC", "safe paths", "relocated execution", "UTF-8 project path", "init/add/show/observe/export"],
                  "data": "synthetic temporary data only", "temporary_cleanup": "completed"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
