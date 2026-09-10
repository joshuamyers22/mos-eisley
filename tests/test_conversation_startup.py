"""Default launches, private storage, workspace selection and command compatibility."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.conversation_store import ConversationSnapshot


class StartupTests(TestCase):
    def invoke(
        self, home: Path, *arguments: str, text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *arguments],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "HOME": str(home)},
            timeout=15,
        )

    def test_bare_launch_saves_privately_and_starts_fresh(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            first = self.invoke(home, text="\n".join(DEMO_PROMPTS) + "\n")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("You gave me a boundary of ten.", first.stdout)
            self.assertIn("Recorded preview", first.stdout)
            self.assertNotIn("\x1b[?1049h", first.stdout)
            storage = home / ".mos-eisley-sessions"
            self.assertEqual(storage.stat().st_mode & 0o777, 0o700)
            snapshot_path = next(storage.glob("*.json"))
            self.assertEqual(snapshot_path.stat().st_mode & 0o777, 0o600)
            snapshot = ConversationSnapshot.model_validate_json(
                snapshot_path.read_bytes()
            )
            self.assertEqual(snapshot.state.workspace, str(Path.cwd().resolve()))
            self.assertEqual(snapshot.state.exchanges_consumed, 2)
            second = self.invoke(home)
            self.assertEqual(second.returncode, 0, second.stderr)
            snapshots = [
                ConversationSnapshot.model_validate_json(p.read_bytes())
                for p in storage.glob("*.json")
            ]
            self.assertEqual(sorted(len(s.state.entries) for s in snapshots), [0, 2])

    def test_resume_and_list_use_defaults_and_preserve_workspace_scope(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            first = self.invoke(home, "-C", directory, text=DEMO_PROMPTS[0] + "\n")
            self.assertEqual(first.returncode, 0, first.stderr)
            resumed = self.invoke(
                home, "resume", "--last", "-C", directory, text=DEMO_PROMPTS[1] + "\n"
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertIn("You gave me a boundary of ten.", resumed.stdout)
            listed = self.invoke(home, "sessions", "-C", directory, "--json")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(len(json.loads(listed.stdout)["sessions"]), 1)
            foreign = home / "other"
            foreign.mkdir()
            absent = self.invoke(home, "resume", "--last", "-C", str(foreign))
            self.assertEqual(absent.returncode, 2)
            self.assertIn("No saved conversations", absent.stdout)

    def test_custom_paths_and_json_launch(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            cassette = home / "recording.json"
            cassette.write_bytes(canonical_bytes(demo_cassette()))
            storage = home / "chosen"
            result = self.invoke(
                home,
                "--storage=" + str(storage),
                "--cassette",
                str(cassette),
                "--json",
                text=DEMO_PROMPTS[0] + "\n",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(events[-1]["type"], "conversation.saved")
            self.assertTrue(storage.is_dir())
            self.assertFalse((home / ".mos-eisley-sessions").exists())

    def test_help_version_and_unknown_commands_have_no_side_effects(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            for arguments, code in (
                (["--help"], 0),
                (["--version"], 0),
                (["chat", "--help"], 0),
                (["caht"], 2),
                (["--unknown"], 2),
                (["-C"], 2),
            ):
                with self.subTest(arguments=arguments):
                    result = self.invoke(home, *arguments)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertFalse((home / ".mos-eisley-sessions").exists())

    def test_invalid_workspace_and_recording_do_not_create_default_storage(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            for flag in ("--workspace", "--cassette"):
                result = self.invoke(home, flag, str(home / "missing"))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((home / ".mos-eisley-sessions").exists())

    def test_default_storage_rejects_public_directory_and_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            storage = home / ".mos-eisley-sessions"
            storage.mkdir(mode=0o755)
            storage.chmod(0o755)
            result = self.invoke(home)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(list(storage.iterdir()), [])
            storage.rmdir()
            target = home / "target"
            target.mkdir(mode=0o700)
            storage.symlink_to(target, target_is_directory=True)
            result = self.invoke(home)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(list(target.iterdir()), [])

    def test_default_resume_rejects_a_different_recording_without_rewriting(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            cassette = home / "different.json"
            cassette.write_bytes(canonical_bytes(demo_cassette(multiline=True)))
            result = self.invoke(home, "--cassette", str(cassette))
            self.assertEqual(result.returncode, 0, result.stderr)
            path = next((home / ".mos-eisley-sessions").glob("*.json"))
            before = path.read_bytes()
            resumed = self.invoke(home, "resume", "--last")
            self.assertEqual(resumed.returncode, 2)
            self.assertEqual(path.read_bytes(), before)
