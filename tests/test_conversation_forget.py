"""Forget previews require direct review/apply and cannot survive session handoff."""

import asyncio
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_memory import MemoryChangedError, MemoryStore
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_remember import memory_phrase_command
from mos_eisley.conversation_tui import ConversationTUI


def runtime(root: Path) -> ConversationMemoryRuntime:
    store = MemoryStore(root / "memory", root)
    store.change("project", "set", text="Keep. Remove. End.")
    memory = store.load()
    cassette = demo_cassette(memory=memory)
    controller = ConversationController(
        ConversationController.fresh(root, cassette, memory),
        cassette,
        lambda state: None,
    )
    result = ConversationMemoryRuntime(
        controller, store, lambda selected: demo_cassette(memory=selected)
    )
    controller.validate_memory = result.check
    return result


class IntentTests(TestCase):
    def test_scope_and_content_are_explicit_and_other_text_is_literal(self) -> None:
        self.assertEqual(
            memory_phrase_command("Forget this everywhere: EXACT: text"),
            "/memory forget user EXACT: text",
        )
        self.assertEqual(
            memory_phrase_command("forget this for this project: exact"),
            "/memory forget project exact",
        )
        for phrase in (
            "forget this: text",
            "forget this everywhere",
            "forget this for this project: ",
            "forget this everywhere: a\nb",
        ):
            with (
                self.subTest(phrase=phrase),
                self.assertRaisesRegex(ValueError, "No memory was changed"),
            ):
                memory_phrase_command(phrase)
        for phrase in (
            '"forget this everywhere: exact"',
            "Explain forget this everywhere: exact",
            "/steer forget this everywhere: exact",
        ):
            self.assertIsNone(memory_phrase_command(phrase))


class TerminalTests(IsolatedAsyncioTestCase):
    async def test_preview_apply_preserves_history_and_selection_until_refresh(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.controller.submit(DEMO_PROMPTS[0])
            await env.controller.step()
            history = env.controller.state.entries[0]
            recording = env.controller.cassette
            env.controller.submit(DEMO_PROMPTS[1])
            before = env.controller.state
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(
                ConversationSubmission(
                    "forget this for this project: Remove.", False, accepted
                )
            )
            events: list[dict[str, object]] = []

            def emit(event: dict[str, object]) -> None:
                events.append(event)
                if event["type"] == "conversation.memory.forget.preview":
                    self.assertEqual(env.store.load(), before.memory)
                    queue.put_nowait(
                        "/memory apply-forget " + str(event["preview_sha256"])
                    )
                    queue.put_nowait(None)

            await terminal(env.controller, queue, emit, memory_command=env.command)
            self.assertTrue(accepted.result())
            self.assertEqual(env.controller.state, before)
            self.assertEqual(env.controller.cassette, recording)
            self.assertIn("conversation.memory.forget.saved", str(events))
            self.assertEqual(env.controller.state.entries[0], history)
            with self.assertRaises(MemoryChangedError):
                env.check()
            env.refresh(False)
            self.assertEqual(
                env.controller.cassette.exchanges[:1], recording.exchanges[:1]
            )
            self.assertEqual(env.controller.state.entries[1].status, "queued")
            saved = env.store.read("project")
            assert saved is not None
            self.assertEqual(saved.document.text, "Keep.  End.")

    async def test_pasted_and_composed_apply_commands_never_remove_text(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            receipt = env.command("/memory forget project Remove.")
            token = str(receipt["preview_sha256"])
            before = env.store.path("project").read_bytes()
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(
                ConversationSubmission("/memory apply-forget " + token, True, accepted)
            )
            queue.put_nowait("/compose")
            queue.put_nowait("/memory apply-forget " + token)
            queue.put_nowait("/send")
            queue.put_nowait(None)
            await terminal(
                env.controller, queue, lambda event: None, memory_command=env.command
            )
            self.assertTrue(accepted.result())
            self.assertEqual(env.store.path("project").read_bytes(), before)
            self.assertIsNotNone(env.forget.pending)

    async def test_other_edits_invalidate_pending_review_but_inspection_preserves_it(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            receipt = env.command("/memory forget project Remove.")
            env.command("/memory show project")
            self.assertIsNotNone(env.forget.pending)
            env.command("/memory append user new preference")
            self.assertIsNone(env.forget.pending)
            with self.assertRaisesRegex(ValueError, "No forget preview"):
                env.command("/memory apply-forget " + str(receipt["preview_sha256"]))
            env.command("/memory forget project Remove.")
            with (
                patch.object(env.store, "change", side_effect=OSError("failure")),
                self.assertRaises(ValueError),
            ):
                env.command("/memory clear project")
            self.assertIsNone(env.forget.pending)

    async def test_active_work_rejects_preview_and_apply_without_consuming_review(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            receipt = env.command("/memory forget project Remove.")
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            events: list[dict[str, object]] = []
            started = asyncio.Event()

            async def step(**kwargs: object) -> bool:
                started.set()
                await asyncio.Event().wait()
                return False

            with patch.object(env.controller, "step", side_effect=step):
                worker = asyncio.create_task(
                    terminal(
                        env.controller, queue, events.append, memory_command=env.command
                    )
                )
                queue.put_nowait(DEMO_PROMPTS[0])
                await asyncio.wait_for(started.wait(), 2)
                queue.put_nowait("forget this for this project: Keep.")
                queue.put_nowait(
                    "/memory apply-forget " + str(receipt["preview_sha256"])
                )
                queue.put_nowait("/quit")
                await asyncio.wait_for(worker, 2)
            self.assertEqual(
                sum("Stop active work" in str(event) for event in events), 2
            )
            self.assertIsNotNone(env.forget.pending)
            saved = env.store.read("project")
            assert saved is not None
            self.assertEqual(saved.document.text, "Keep. Remove. End.")

    async def test_fullscreen_complete_preview_escaped_and_discard_clears_it(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            env = runtime(Path(directory))
            env.store.change("project", "set", text="x" * 1000 + "\x1b[31mRemove.")
            ui = ConversationTUI(env.controller, input=input, output=DummyOutput())
            receipt = env.command("/memory forget project Remove.")
            ui.emit(receipt)
            self.assertIn("x" * 1000, ui.transcript.text)
            self.assertIn(str(receipt["preview_sha256"]), ui.transcript.text)
            self.assertNotIn("\x1b", ui.transcript.text)
            ui.emit(env.command("/memory discard-forget"))
            self.assertNotIn(str(receipt["preview_sha256"]), ui.transcript.text)
            self.assertIn("preview discarded", ui.transcript.text)


class CLITests(TestCase):
    def test_preview_is_read_only_and_resume_cannot_apply_old_review_on_both_backends(
        self,
    ) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                child = root / "child"
                child.mkdir()
                store = MemoryStore(root / "memory", root)
                store.change("project", "set", text="Keep. Remove.")
                before = store.path("project").read_bytes()
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
                first = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "chat",
                        *common,
                        "--memory-project-root",
                        str(root),
                    ],
                    input="forget this for this project: Remove.\n",
                    env={**os.environ, "HOME": str(root)},
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
                self.assertEqual(first.returncode, 0, first.stderr)
                events = [json.loads(line) for line in first.stdout.splitlines()]
                preview = next(
                    event
                    for event in events
                    if event["type"] == "conversation.memory.forget.preview"
                )
                self.assertEqual(preview["workspace"], str(root))
                self.assertEqual(store.path("project").read_bytes(), before)
                second = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "resume",
                        "--last",
                        *common,
                    ],
                    input="/memory apply-forget " + preview["preview_sha256"] + "\n",
                    env={**os.environ, "HOME": str(root)},
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertIn("No forget preview", second.stdout)
                self.assertEqual(store.path("project").read_bytes(), before)

    def test_process_death_after_publish_does_not_make_stale_review_reusable(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env = runtime(root)
            receipt = env.command("/memory forget project Remove.")
            code = """
import os, sys
from pathlib import Path
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_forget import MemoryForget
root=Path(sys.argv[1])
forget=MemoryForget(MemoryStore(root/'memory',root))
receipt=forget.command('/memory forget project Remove.')
replace=os.replace
def crash(*args,**kwargs):
    replace(*args,**kwargs)
    os._exit(73)
os.replace=crash
forget.apply(receipt['preview_sha256'])
"""
            result = subprocess.run(
                [sys.executable, "-c", code, str(root)], capture_output=True, timeout=20
            )
            self.assertEqual(result.returncode, 73, result.stderr)
            saved = env.store.read("project")
            assert saved is not None
            self.assertEqual(saved.document.text, "Keep.  End.")
            with self.assertRaisesRegex(ValueError, "fresh preview"):
                env.command("/memory apply-forget " + str(receipt["preview_sha256"]))

    def test_cli_preview_confirm_refresh_updates_only_selected_scope_on_both_backends(
        self,
    ) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                child = root / "child"
                child.mkdir()
                store = MemoryStore(root / "memory", root)
                store.change("project", "set", text="Keep. Remove. End.")
                store.change("user", "set", text="Untouched user preference.")
                user = store.path("user").read_bytes()
                command = [
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
                    "--memory-storage",
                    str(store.root),
                ]
                with subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={**os.environ, "HOME": str(root)},
                ) as process:
                    assert process.stdin is not None and process.stdout is not None
                    try:
                        process.stdin.write(b"forget this for this project: Remove.\n")
                        process.stdin.flush()
                        pending = b""
                        token = None
                        deadline = time.monotonic() + 20
                        with selectors.DefaultSelector() as selector:
                            selector.register(process.stdout, selectors.EVENT_READ)
                            while token is None:
                                remaining = deadline - time.monotonic()
                                self.assertGreater(
                                    remaining, 0, "CLI preview timed out"
                                )
                                self.assertTrue(
                                    selector.select(remaining), "CLI preview timed out"
                                )
                                chunk = os.read(process.stdout.fileno(), 65536)
                                self.assertTrue(chunk, "CLI closed before preview")
                                pending += chunk
                                while b"\n" in pending:
                                    line, pending = pending.split(b"\n", 1)
                                    event = json.loads(line)
                                    if (
                                        event["type"]
                                        == "conversation.memory.forget.preview"
                                    ):
                                        token = str(event["preview_sha256"])
                                        self.assertEqual(
                                            event["after_text"], "Keep.  End."
                                        )
                                        self.assertEqual(event["workspace"], str(root))
                        output, errors = process.communicate(
                            f"/memory apply-forget {token}\n/memory refresh\n".encode(),
                            timeout=20,
                        )
                    except BaseException:
                        process.kill()
                        process.communicate()
                        raise
                self.assertEqual(process.returncode, 0, errors.decode())
                events = [json.loads(line) for line in output.splitlines()]
                self.assertIn("conversation.memory.forget.saved", str(events))
                self.assertIn("conversation.memory.updated", str(events))
                self.assertFalse(
                    any(event["type"].startswith("message.") for event in events)
                )
                saved = store.read("project")
                assert saved is not None
                self.assertEqual(saved.document.text, "Keep.  End.")
                self.assertEqual(store.path("user").read_bytes(), user)
                self.assertIsNone(MemoryStore(store.root, child).read("project"))
