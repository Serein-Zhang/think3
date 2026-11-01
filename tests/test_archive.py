"""Archive validation from symlinked temporary roots, using isolated files."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_archive.py"
SKILL = ROOT / "skills/think3"


class ArchivePathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="think3-archive-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def invoke(self, archive, *, environment=None):
        return subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(archive)],
            cwd=self.root, env=environment, capture_output=True,
            encoding="utf-8", timeout=30,
        )

    def test_release_smoke_passes_with_a_symlinked_temporary_directory(self):
        actual = self.root / "actual-temp"
        actual.mkdir()
        alias = self.root / "temp-alias"
        try:
            alias.symlink_to(actual, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Directory symlinks are unavailable: {exc}")
        archive = self.root / "release.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for source in sorted(SKILL.rglob("*")):
                if source.is_file():
                    output.write(source, "think3/" + source.relative_to(SKILL).as_posix())
        environment = dict(os.environ)
        environment.update(TMPDIR=str(alias), TEMP=str(alias), TMP=str(alias))
        result = self.invoke(archive, environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "passed")
        self.assertEqual(list(actual.iterdir()), [], "Temporary extraction was not cleaned up")

    def test_normalizing_the_root_still_rejects_archive_path_escape(self):
        archive = self.root / "escape.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("think3/../../escaped.txt", "must never be extracted")
        environment = dict(os.environ)
        environment.update(TMPDIR=str(self.root), TEMP=str(self.root), TMP=str(self.root))
        result = self.invoke(archive, environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "escaped.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
