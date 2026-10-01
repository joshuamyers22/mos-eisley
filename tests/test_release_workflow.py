"""The publication gate rejects tags outside the reviewed mainline."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "verify_release.py"


class ReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.run_git("init", "-b", "main")
        self.run_git("config", "user.email", "release-test@example.invalid")
        self.run_git("config", "user.name", "Release Test")
        (self.repo / "pyproject.toml").write_text(
            '[project]\nname = "example"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        self.run_git("add", "pyproject.toml")
        self.run_git("commit", "-m", "main release")
        self.run_git("tag", "v0.1.0")
        self.run_git("update-ref", "refs/remotes/origin/main", "HEAD")

    def run_git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, capture_output=True, check=True)

    def release_result(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--tag",
                "v0.1.0",
                "--main-ref",
                "refs/remotes/origin/main",
            ],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_tagged_main_commit_passes(self) -> None:
        self.assertEqual(self.release_result().returncode, 0)

    def test_side_branch_tag_cannot_publish(self) -> None:
        self.run_git("switch", "-c", "side")
        (self.repo / "side.txt").write_text("side\n", encoding="utf-8")
        self.run_git("add", "side.txt")
        self.run_git("commit", "-m", "unmerged side")
        self.run_git("tag", "-f", "v0.1.0")
        result = self.release_result()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not reachable from main", result.stderr)

    def test_checkout_must_match_tag(self) -> None:
        self.run_git("switch", "-c", "side")
        (self.repo / "side.txt").write_text("side\n", encoding="utf-8")
        self.run_git("add", "side.txt")
        self.run_git("commit", "-m", "untagged checkout")
        result = self.release_result()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the exact tag commit", result.stderr)


if __name__ == "__main__":
    unittest.main()
