"""Literal initial messages, input admission and ordinary session continuation."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.conversation_cli import (
    DEMO_PROMPTS,
    MULTILINE_PROMPT,
    demo_cassette,
    launch_prompt,
)
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot


class LaunchPromptTests(TestCase):
    def invoke(
        self, root: Path, *args: str, text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *args],
            input=text,
            text=True,
            capture_output=True,
            cwd=root,
            env={**os.environ, "HOME": str(root)},
            timeout=15,
        )

    def test_explicit_and_bare_separator_launch_complete_on_eof(self) -> None:
        for prefix in (("chat",), ("--",)):
            with self.subTest(prefix=prefix), TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.invoke(root, *prefix, DEMO_PROMPTS[0])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("The fixture boundary is ten.", result.stdout)
                path = next((root / ".mos-eisley-sessions").glob("*.json"))
                snapshot = ConversationSnapshot.model_validate_json(path.read_bytes())
                self.assertEqual(len(snapshot.state.entries), 1)
                self.assertEqual(snapshot.state.entries[0].text, DEMO_PROMPTS[0])
                self.assertEqual(snapshot.state.entries[0].status, "completed")
                self.assertEqual(snapshot.state.exchanges_consumed, 1)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_launch_options_and_piped_followup_preserve_order_on_both_backends(
        self,
    ) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory)
                project = root / "project"
                project.mkdir()
                result = self.invoke(
                    root,
                    "-C",
                    str(project),
                    "--storage-backend",
                    backend,
                    "--json",
                    DEMO_PROMPTS[0],
                    text=DEMO_PROMPTS[1] + "\n",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                complete = [e for e in events if e["type"] == "message.completed"]
                self.assertEqual([e["text"] for e in complete], list(DEMO_PROMPTS))
                self.assertEqual(
                    complete[-1]["answer"], "You gave me a boundary of ten."
                )
                self.assertEqual(events[-1]["type"], "conversation.saved")
                storage = root / ".mos-eisley-sessions"
                if backend == "sqlite":
                    with SQLiteConversationStore(
                        storage,
                        events[-1]["session_id"],
                        project,
                        create=False,
                        writable=False,
                    ) as store:
                        state = store.inspect_snapshot()[0].state
                else:
                    state = ConversationSnapshot.model_validate_json(
                        next(storage.glob("*.json")).read_bytes()
                    ).state
                self.assertEqual(state.workspace, str(project.resolve()))
                self.assertEqual(state.exchanges_consumed, 2)
                self.assertEqual(len(state.entries), 2)

    def test_multiline_prompt_remains_one_literal_message(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            recording = root / "recording.json"
            recording.write_bytes(canonical_bytes(demo_cassette(multiline=True)))
            result = self.invoke(
                root, "--cassette", str(recording), "--json", "--", MULTILINE_PROMPT
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            queued = [e for e in events if e["type"] == "message.queued"]
            self.assertEqual([e["text"] for e in queued], [MULTILINE_PROMPT])
            self.assertEqual(
                len([e for e in events if e["type"] == "message.completed"]), 1
            )

    def test_slashes_command_names_and_option_text_never_invoke_controls(self) -> None:
        for prompt in ("/quit", "/review", "review this change", "sessions", "--help"):
            with self.subTest(prompt=prompt), TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.invoke(root, "--json", "--", prompt)
                self.assertEqual(result.returncode, 0, result.stderr)
                snapshot = ConversationSnapshot.model_validate_json(
                    next((root / ".mos-eisley-sessions").glob("*.json")).read_bytes()
                )
                self.assertEqual(len(snapshot.state.entries), 1)
                self.assertEqual(snapshot.state.entries[0].text, prompt)
                self.assertFalse(snapshot.state.entries[0].is_review)
                self.assertIn('"type": "conversation.error"', result.stdout)
                self.assertEqual(snapshot.state.entries[0].status, "failed")

    def test_rejected_prompt_has_no_storage_or_rejected_content_echo(self) -> None:
        for prompt in ("", " \n\t", "PRIVATE" + "x" * 8000, "PRIVATE\n" * 257):
            with self.subTest(size=len(prompt)), TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.invoke(root, "chat", prompt)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("PRIVATE", result.stderr)
                self.assertFalse((root / ".mos-eisley-sessions").exists())
        with self.assertRaises(argparse.ArgumentTypeError):
            launch_prompt("PRIVATE\udcff")
        self.assertEqual(launch_prompt("x" * 8000), "x" * 8000)
        self.assertEqual(launch_prompt("\n" * 255 + "x"), "\n" * 255 + "x")

    def test_utf8_pending_byte_rejection_precedes_session_creation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.invoke(
                root, "--pending-text-max-bytes", "4000", "PRIVATE" + "é" * 3000
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("6007", result.stderr)
            self.assertNotIn("PRIVATE", result.stderr)
            self.assertFalse((root / ".mos-eisley-sessions").exists())

    def test_resume_continues_history_without_repeating_launch_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.invoke(root, "--", DEMO_PROMPTS[0])
            self.assertEqual(first.returncode, 0, first.stderr)
            path = next((root / ".mos-eisley-sessions").glob("*.json"))
            before = path.read_bytes()
            passive = self.invoke(root, "resume", "--last")
            self.assertEqual(passive.returncode, 0, passive.stderr)
            self.assertEqual(path.read_bytes(), before)
            resumed = self.invoke(root, "resume", "--last", text=DEMO_PROMPTS[1] + "\n")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            snapshot = ConversationSnapshot.model_validate_json(path.read_bytes())
            self.assertEqual(
                [entry.text for entry in snapshot.state.entries], list(DEMO_PROMPTS)
            )
            rejected = self.invoke(root, "resume", "--last", "--", DEMO_PROMPTS[0])
            self.assertEqual(rejected.returncode, 2)
            self.assertEqual(
                ConversationSnapshot.model_validate_json(path.read_bytes()), snapshot
            )

    def test_help_and_unknown_command_still_do_not_start_a_session(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for arguments, status in (
                (("--help",), 0),
                (("--version",), 0),
                (("chat", "--help"), 0),
                (("caht",), 2),
                (("--unknown",), 2),
            ):
                result = self.invoke(root, *arguments)
                self.assertEqual(result.returncode, status)
                self.assertFalse((root / ".mos-eisley-sessions").exists())
