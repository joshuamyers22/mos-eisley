"""The installed-compatible terminal can curate a span from a normal assistant reply."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import test_conversation_proposal_cli as cli_helpers

from mos_eisley.conversation_cli import DEMO_PROMPTS
from mos_eisley.conversation_memory import MemoryStore


class SelectionCLITests(TestCase):
    def test_selected_prose_apply_refresh_and_resume_on_both_backends(self) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                child = root / "child"
                child.mkdir()
                store = MemoryStore(root / "memory", root)
                common = [
                    "--json",
                    "--plain",
                    "--storage-backend",
                    backend,
                    "-C",
                    str(child),
                    "--memory-storage",
                    str(store.root),
                ]
                environment = {**os.environ, "HOME": str(root)}
                helper = cli_helpers.ProposalCLITests()
                with subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "chat",
                        *common,
                        "--memory-project-root",
                        str(root),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                ) as process:
                    assert process.stdin is not None
                    try:
                        process.stdin.write((DEMO_PROMPTS[0] + "\n").encode())
                        process.stdin.flush()
                        completed = helper.wait_event(process, "message.completed")
                        self.assertEqual(
                            completed["answer"], "The fixture boundary is ten."
                        )
                        self.assertFalse(store.root.exists())
                        process.stdin.write(
                            b'/memory review-text project 0 "boundary is ten"\n'
                        )
                        process.stdin.flush()
                        review = helper.wait_event(
                            process, "conversation.memory.proposal.preview"
                        )
                        self.assertFalse(store.root.exists())
                        self.assertEqual(
                            review["operation"], "accept_selected_assistant_text"
                        )
                        self.assertEqual(review["after_text"], "boundary is ten")
                        self.assertEqual(review["workspace"], str(root))
                        token = str(review["preview_sha256"])
                        output, errors = process.communicate(
                            (
                                f"/memory apply-proposal {token}\n"
                                + "/memory refresh\n"
                            ).encode(),
                            timeout=20,
                        )
                    except BaseException:
                        process.kill()
                        process.communicate()
                        raise
                self.assertEqual(process.returncode, 0, errors.decode())
                events = [json.loads(line) for line in output.splitlines()]
                self.assertIn("conversation.memory.proposal.saved", str(events))
                self.assertIn("conversation.memory.updated", str(events))
                self.assertFalse(
                    any(event["type"] == "message.running" for event in events)
                )
                saved = store.read("project")
                assert saved is not None
                self.assertEqual(saved.document.text, "boundary is ten")
                self.assertIsNone(store.read("user"))
                self.assertIsNone(MemoryStore(store.root, child).read("project"))
                resumed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "resume",
                        "--last",
                        *common,
                    ],
                    input=(
                        f"/memory apply-proposal {token}\n"
                        + '/memory review-text project 0 "boundary is ten"\n'
                    ),
                    env=environment,
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                self.assertIn("No proposal review", resumed.stdout)
                self.assertIn("conversation.memory.proposal.preview", resumed.stdout)
                self.assertEqual(store.read("project"), saved)
