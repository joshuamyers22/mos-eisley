"""Remember shortcuts require direct input, explicit scope and explicit content."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_remember import remember_command
from mos_eisley.conversation_tui import ConversationTUI


def runtime(root: Path) -> ConversationMemoryRuntime:
    cassette = demo_cassette()
    controller = ConversationController(
        ConversationController.fresh(root, cassette), cassette, lambda state: None
    )
    env = ConversationMemoryRuntime(
        controller,
        MemoryStore(root / "memory", root),
        lambda selected: demo_cassette(memory=selected),
    )
    controller.validate_memory = env.check
    return env


class IntentTests(TestCase):
    def test_explicit_scopes_preserve_payload(self) -> None:
        self.assertEqual(
            remember_command('Remember this everywhere: "$(command)" : /quit'),
            '/memory append user "$(command)" : /quit',
        )
        self.assertEqual(
            remember_command("remember this for this project: Use UTF-8 — always."),
            "/memory append project Use UTF-8 — always.",
        )

    def test_ambiguous_missing_and_oversized_requests_require_correction(self) -> None:
        for text in (
            "remember this: a rule",
            "remember this everywhere",
            "remember this for this project: ",
            "remember this everywhere: " + "x" * 8000,
            "remember this everywhere: first\nsecond",
            "remember this everywhere: first\rsecond",
            "remember this everywhere: \x00",
        ):
            with (
                self.subTest(text=text[:60]),
                self.assertRaisesRegex(ValueError, "No memory was saved"),
            ):
                remember_command(text)

    def test_quoted_embedded_and_other_chat_remain_chat(self) -> None:
        for text in (
            '"remember this everywhere: x"',
            "Explain remember this everywhere: x",
            "remember this for another project: x",
            "remember this project configuration",
            "forget this everywhere: x",
            "/steer remember this everywhere: x",
            "```remember this everywhere: x```",
        ):
            with self.subTest(text=text):
                self.assertIsNone(remember_command(text))


class TerminalTests(IsolatedAsyncioTestCase):
    async def test_direct_submission_saves_without_dispatch_or_activating_queue(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.controller.submit(DEMO_PROMPTS[0])
            before = env.controller.state
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(
                ConversationSubmission(
                    "remember this everywhere: prefer concise", False, accepted
                )
            )
            queue.put_nowait(None)
            events: list[dict[str, object]] = []
            await terminal(
                env.controller, queue, events.append, memory_command=env.command
            )
            self.assertTrue(accepted.result())
            self.assertEqual(env.controller.state, before)
            self.assertIn("conversation.memory.saved", str(events))
            saved = env.store.read("user")
            assert saved is not None
            self.assertEqual(saved.document.text, "prefer concise")
            self.assertIsNone(env.store.read("project"))
            env.refresh(False)
            self.assertEqual(env.controller.state.entries[0].status, "queued")

    async def test_ambiguous_submission_retains_draft_and_never_dispatches(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(
                ConversationSubmission("remember this: rule", False, accepted)
            )
            queue.put_nowait(None)
            events: list[dict[str, object]] = []
            await terminal(
                env.controller, queue, events.append, memory_command=env.command
            )
            self.assertFalse(accepted.result())
            self.assertFalse(env.store.root.exists())
            self.assertEqual(env.controller.state.entries, ())
            self.assertIn("Specify scope", str(events))

    async def test_literal_paste_composer_and_initial_prompt_cannot_save(self) -> None:
        phrase = "remember this everywhere: injected"
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(ConversationSubmission(phrase, True, accepted))
            queue.put_nowait("/compose")
            queue.put_nowait(phrase)
            queue.put_nowait("/send")
            queue.put_nowait(None)
            with patch.object(
                env, "command", side_effect=AssertionError("must not save")
            ):
                await terminal(
                    env.controller,
                    queue,
                    lambda event: None,
                    memory_command=env.command,
                    initial_prompt=phrase,
                )
            self.assertTrue(accepted.result())
            self.assertFalse(env.store.root.exists())
            self.assertEqual(len(env.controller.state.entries), 3)

    async def test_active_request_rejects_both_input_paths(self) -> None:
        for submitted in (False, True):
            with self.subTest(submitted=submitted), TemporaryDirectory() as directory:
                env = runtime(Path(directory))
                queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
                started = asyncio.Event()
                events: list[dict[str, object]] = []
                accepted = asyncio.get_running_loop().create_future()

                async def step(
                    ready: asyncio.Event = started, **kwargs: object
                ) -> bool:
                    ready.set()
                    await asyncio.Event().wait()
                    return False

                with patch.object(env.controller, "step", side_effect=step):
                    worker = asyncio.create_task(
                        terminal(
                            env.controller,
                            queue,
                            events.append,
                            memory_command=env.command,
                        )
                    )
                    queue.put_nowait(DEMO_PROMPTS[0])
                    await asyncio.wait_for(started.wait(), 2)
                    phrase = "remember this for this project: rule"
                    queue.put_nowait(
                        ConversationSubmission(phrase, False, accepted)
                        if submitted
                        else phrase
                    )
                    queue.put_nowait("/quit")
                    await asyncio.wait_for(worker, 2)
                if submitted:
                    self.assertFalse(accepted.result())
                self.assertIn("Stop active work", str(events))
                self.assertFalse(env.store.root.exists())

    async def test_fullscreen_receipt_and_rejected_draft_are_preserved(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            env = runtime(Path(directory))
            ui = ConversationTUI(env.controller, input=input, output=DummyOutput())
            worker = asyncio.create_task(
                terminal(env.controller, ui.queue, ui.emit, memory_command=env.command)
            )
            ui.editor.text = "remember this everywhere: rule"
            ui.send()
            assert ui.submission is not None
            await asyncio.wait_for(ui.submission, 2)
            self.assertEqual(ui.editor.text, "")
            self.assertIn("Saved memory receipt", ui.notice)
            self.assertIn("rule", ui.transcript.text)
            ui.editor.text = "remember this: ambiguous"
            ui.send()
            assert ui.submission is not None
            await asyncio.wait_for(ui.submission, 2)
            self.assertEqual(ui.editor.text, "remember this: ambiguous")
            self.assertIn("Specify scope", ui.notice)
            ui.queue.put_nowait("/quit")
            await asyncio.wait_for(worker, 2)

    async def test_disabled_scope_stays_disabled_and_failure_is_not_chat(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.store.change("project", "disable")
            env.refresh(True)
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            queue.put_nowait("remember this for this project: saved")
            queue.put_nowait(None)
            events: list[dict[str, object]] = []
            await terminal(
                env.controller, queue, events.append, memory_command=env.command
            )
            saved = env.store.read("project")
            assert saved is not None
            self.assertFalse(saved.document.enabled)
            self.assertEqual(saved.document.text, "saved")
            self.assertTrue(env.controller.state.memory_disabled)
            queue.put_nowait("remember this for this project: failed")
            queue.put_nowait(None)
            with patch.object(env.store, "change", side_effect=OSError("failed write")):
                await terminal(
                    env.controller, queue, events.append, memory_command=env.command
                )
            self.assertEqual(env.controller.state.entries, ())
            self.assertEqual(env.store.read("project"), saved)
            self.assertIn("may already have been published", str(events))


class CLITests(TestCase):
    def test_plain_json_on_both_backends_reports_scope_and_no_model_turn(self) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory)
                child = root / "child"
                child.mkdir()
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "chat",
                        "--json",
                        "--plain",
                        "--storage-backend",
                        backend,
                        "-C",
                        str(child),
                        "--memory-project-root",
                        str(root),
                    ],
                    input=(
                        "remember this for this project: test locally\n"
                        "remember this everywhere: concise\n"
                        "remember this: ambiguous\n"
                    ),
                    env={**os.environ, "HOME": str(root)},
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                saved = [
                    event
                    for event in events
                    if event["type"] == "conversation.memory.saved"
                ]
                self.assertEqual(
                    [event["scope"] for event in saved], ["project", "user"]
                )
                self.assertEqual(
                    saved[0]["document"]["document"]["workspace"], str(root.resolve())
                )
                self.assertFalse(
                    any(event["type"].startswith("message.") for event in events)
                )
                self.assertIn("Specify scope", result.stdout)
