"""Actual recorded replies stay inert until reviewed; pending reviews never resume."""

import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange


def proposal_cassette() -> AgentCassette:
    exchange = demo_cassette().exchanges[0]
    assert exchange.response is not None
    response = exchange.response.model_copy(
        update={
            "turn": Turn(
                role="assistant",
                blocks=(
                    TextBlock(
                        text=json.dumps(
                            {
                                "operation": "append",
                                "text": "Use pytest for this project.",
                            }
                        )
                    ),
                ),
            )
        }
    )
    return AgentCassette(
        exchanges=(
            AgentExchange(
                request_sha256=exchange.request_sha256,
                response=response,
            ),
        )
    )


class ProposalCLITests(TestCase):
    def wait_event(
        self, process: subprocess.Popen[bytes], kind: str
    ) -> dict[str, object]:
        assert process.stdout is not None
        pending = b""
        deadline = time.monotonic() + 20
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                self.assertGreater(remaining, 0, f"Timed out waiting for {kind}")
                self.assertTrue(
                    selector.select(remaining), f"Timed out waiting for {kind}"
                )
                chunk = os.read(process.stdout.fileno(), 65536)
                self.assertTrue(chunk, f"CLI closed before {kind}")
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    event = json.loads(line)
                    if event["type"] == kind:
                        return event

    def test_scoped_acceptance_and_pending_review_loss_on_both_backends(self) -> None:
        for backend in ("snapshot", "sqlite"):
            for apply in (False, True):
                with (
                    self.subTest(backend=backend, apply=apply),
                    TemporaryDirectory() as directory,
                ):
                    root = Path(directory).resolve()
                    child = root / "child"
                    child.mkdir()
                    memory = MemoryStore(root / "memory", root)
                    cassette = root / "cassette.json"
                    cassette.write_bytes(canonical_bytes(proposal_cassette()))
                    common = [
                        "--json",
                        "--plain",
                        "--storage-backend",
                        backend,
                        "-C",
                        str(child),
                        "--memory-storage",
                        str(memory.root),
                    ]
                    environment = {**os.environ, "HOME": str(root)}
                    with subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "mos_eisley.cli",
                            "chat",
                            *common,
                            "--memory-project-root",
                            str(root),
                            "--cassette",
                            str(cassette),
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
                            response = self.wait_event(process, "message.completed")
                            self.assertIn("Use pytest", str(response["answer"]))
                            self.assertFalse(memory.root.exists())
                            process.stdin.write(b"/memory review-proposal project 0\n")
                            process.stdin.flush()
                            review = self.wait_event(
                                process, "conversation.memory.proposal.preview"
                            )
                            self.assertFalse(memory.root.exists())
                            self.assertEqual(review["workspace"], str(root))
                            token = str(review["preview_sha256"])
                            output, errors = process.communicate(
                                (
                                    f"/memory apply-proposal {token}\n" if apply else ""
                                ).encode(),
                                timeout=20,
                            )
                        except BaseException:
                            process.kill()
                            process.communicate()
                            raise
                    self.assertEqual(process.returncode, 0, errors.decode())
                    saved = memory.read("project")
                    if apply:
                        self.assertIn(b"conversation.memory.proposal.saved", output)
                        assert saved is not None
                        self.assertEqual(
                            saved.document.text, "Use pytest for this project."
                        )
                        self.assertIsNone(memory.read("user"))
                        self.assertIsNone(
                            MemoryStore(memory.root, child).read("project")
                        )
                    else:
                        self.assertFalse(memory.root.exists())
                    resumed = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "mos_eisley.cli",
                            "resume",
                            "--last",
                            *common,
                            "--cassette",
                            str(cassette),
                            "--refresh-memory",
                            "--no-memory",
                            "--refresh-cassette",
                            str(cassette),
                        ],
                        input=(
                            f"/memory apply-proposal {token}\n/memory show project\n"
                            "/memory review-proposal project 0\n"
                        ),
                        env=environment,
                        text=True,
                        capture_output=True,
                        timeout=20,
                    )
                    self.assertEqual(resumed.returncode, 0, resumed.stderr)
                    self.assertIn("No proposal review", resumed.stdout)
                    self.assertIn(
                        "conversation.memory.proposal.preview", resumed.stdout
                    )
                    if apply:
                        self.assertIn("Use pytest for this project.", resumed.stdout)
                        self.assertEqual(memory.read("project"), saved)
                    else:
                        self.assertFalse(memory.root.exists())
