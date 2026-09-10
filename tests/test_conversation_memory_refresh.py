"""Explicit memory changes preserve history and apply before later requests only."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import (
    DEMO_PROMPTS,
    MULTILINE_PROMPT,
    demo_cassette,
    terminal,
)
from mos_eisley.conversation_memory import (
    MemoryRefreshError,
    MemoryStore,
)
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_store import ConversationSnapshot


def runtime(root: Path) -> ConversationMemoryRuntime:
    store = MemoryStore(root / "memory", root)
    store.change("user", "set", text="OLD MEMORY CANARY")
    memory = store.load()
    cassette = demo_cassette(memory=memory)
    controller = ConversationController(
        ConversationController.fresh(root, cassette, memory),
        cassette,
        lambda state: None,
    )
    result = ConversationMemoryRuntime(
        controller, store, lambda memory: demo_cassette(memory=memory)
    )
    controller.validate_memory = result.check
    return result


class RefreshTests(IsolatedAsyncioTestCase):
    async def test_completed_turn_keeps_old_context_and_next_request_uses_new_memory(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            controller = env.controller
            old = controller.state.memory
            controller.submit(DEMO_PROMPTS[0])
            await controller.step()
            prefix = controller.cassette.exchanges[0]
            env.store.change("user", "set", text="NEW MEMORY CANARY")
            env.refresh(False)
            self.assertEqual(controller.cassette.exchanges[0], prefix)
            context = controller.state.entries[0].memory_context
            assert context is not None
            self.assertEqual(context.memory, old)
            self.assertEqual(controller.state.exchanges_consumed, 1)
            captured: list[ModelRequest] = []

            class Client:
                async def complete(self, request: ModelRequest) -> ModelResponse:
                    captured.append(request)
                    response = controller.cassette.exchanges[1].response
                    assert response is not None
                    return response

            controller.submit(DEMO_PROMPTS[1])
            await controller.step(client=Client())
            self.assertNotIn("OLD MEMORY CANARY", captured[0].model_dump_json())
            self.assertIn("NEW MEMORY CANARY", captured[0].system)
            self.assertEqual(
                digest(canonical_bytes(captured[0])),
                controller.cassette.exchanges[1].request_sha256,
            )
            context = controller.state.entries[1].memory_context
            assert context is not None
            self.assertEqual(context.memory, controller.state.memory)
            self.assertEqual(controller.state.retained_cassette, controller.cassette)

    async def test_refresh_off_and_refresh_again_do_not_rewrite_consumed_recordings(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            controller = env.controller
            controller.submit(DEMO_PROMPTS[0])
            await controller.step()
            consumed = controller.cassette.exchanges[:1]
            with patch.object(
                env.store, "load", side_effect=AssertionError("must not read")
            ):
                env.refresh(True)
                env.check()
            self.assertTrue(controller.state.memory_disabled)
            self.assertIsNone(controller.state.memory)
            env.store.change("project", "set", text="Project rule")
            env.refresh(False)
            self.assertFalse(controller.state.memory_disabled)
            self.assertEqual(controller.cassette.exchanges[:1], consumed)
            controller.submit(DEMO_PROMPTS[1])
            await controller.step()
            self.assertEqual(controller.state.entries[1].status, "completed")

    async def test_replacement_must_preserve_prefix_and_validate_project_identity(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            env = runtime(root)
            controller = env.controller
            controller.submit(DEMO_PROMPTS[0])
            await controller.step()
            before = controller.state
            env.store.change("user", "set", text="changed")
            memory = env.store.load()
            with self.assertRaisesRegex(MemoryRefreshError, "consumed exchange"):
                controller.refresh_memory(memory, demo_cassette(memory=memory))
            self.assertEqual(controller.state, before)
            other = root / "other"
            other.mkdir()
            foreign = MemoryStore(env.store.root, other)
            foreign.change("project", "set", text="foreign")
            with self.assertRaisesRegex(MemoryRefreshError, "invalid"):
                controller.refresh_memory(foreign.load(), controller.cassette)
            self.assertEqual(controller.state, before)

    async def test_failed_save_does_not_publish_new_memory_or_cassette(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            before, cassette = env.controller.state, env.controller.cassette
            env.store.change("user", "set", text="new")

            def fail(state: ConversationState) -> None:
                raise OSError("disk failure")

            env.controller.save = fail
            with self.assertRaises(OSError):
                env.refresh(False)
            self.assertEqual(env.controller.state, before)
            self.assertEqual(env.controller.cassette, cassette)
            self.assertFalse(env.ignore_memory)
            with self.assertRaisesRegex(ValueError, "persistence failed"):
                env.controller.submit("cannot continue")

    async def test_active_request_rejects_refresh_and_cancelled_context_stays_frozen(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.refresh(False)
            env.controller.submit(DEMO_PROMPTS[0])
            started = asyncio.Event()

            class WaitingClient:
                async def complete(self, request: ModelRequest) -> ModelResponse:
                    started.set()
                    await asyncio.Event().wait()
                    raise AssertionError("unreachable")

            task = asyncio.create_task(env.controller.step(client=WaitingClient()))
            try:
                await asyncio.wait_for(started.wait(), 3)
                before = env.controller.state
                env.store.change("user", "set", text="changed while active")
                with self.assertRaisesRegex(MemoryRefreshError, "Stop active"):
                    env.refresh(False)
                self.assertEqual(env.controller.state, before)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            context = env.controller.state.entries[0].memory_context
            env.refresh(False)
            self.assertEqual(env.controller.state.entries[0].memory_context, context)
            self.assertEqual(env.controller.state.entries[0].status, "cancelled")

    async def test_terminal_refresh_keeps_queue_paused_until_explicit_continue(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.controller.submit(DEMO_PROMPTS[0])
            env.store.change("user", "set", text="updated")
            queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
            queue.put_nowait("/memory refresh")
            queue.put_nowait(None)
            events: list[dict[str, object]] = []
            await terminal(
                env.controller, queue, events.append, refresh_memory=env.refresh
            )
            self.assertEqual(env.controller.state.entries[0].status, "queued")
            self.assertEqual(env.controller.state.exchanges_consumed, 0)
            self.assertIn("conversation.memory.updated", str(events))
            queue.put_nowait("/continue")
            queue.put_nowait(None)
            await terminal(
                env.controller, queue, events.append, refresh_memory=env.refresh
            )
            self.assertEqual(env.controller.state.entries[0].status, "completed")

    async def test_invalid_store_rejects_refresh_but_off_recovers(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            before = env.controller.state
            env.store.path("user").write_bytes(b"invalid")
            with self.assertRaisesRegex(MemoryRefreshError, "could not be loaded"):
                env.refresh(False)
            self.assertEqual(env.controller.state, before)
            env.refresh(True)
            env.controller.submit(DEMO_PROMPTS[0])
            await env.controller.step()
            self.assertEqual(env.controller.state.entries[0].status, "completed")

    async def test_review_context_does_not_receive_memory_history(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.refresh(False)
            brief, cassette = demo_inputs()
            env.controller.submit_review(
                ConversationReviewPacket(brief=brief, cassette=cassette)
            )
            await env.controller.step()
            env.refresh(True)
            entry = env.controller.state.entries[0]
            self.assertIsNone(entry.memory_context)
            self.assertNotIn("OLD MEMORY CANARY", entry.model_dump_json())
            self.assertEqual(entry.status, "completed")

    async def test_custom_recording_requires_explicit_replacement(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.builtin = False
            before = env.controller.state
            with self.assertRaisesRegex(MemoryRefreshError, "refresh-cassette"):
                env.refresh(True)
            self.assertEqual(env.controller.state, before)
            env.refresh(True, replacement=demo_cassette())
            self.assertFalse(env.controller.state.builtin_recording)

    async def test_keyboard_refresh_updates_header_and_paste_stays_literal(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            with create_pipe_input() as input:
                ui = ConversationTUI(
                    env.controller,
                    input=input,
                    output=DummyOutput(),
                    refresh_memory=env.refresh,
                )
                task = asyncio.create_task(ui.run())

                async def wait_for_revision(revision: int) -> None:
                    async with asyncio.timeout(3):
                        while env.controller.state.revision < revision:
                            await asyncio.sleep(0.01)

                try:
                    input.send_text("/memory off\r")
                    await wait_for_revision(1)
                    self.assertIn("memory off", ui.header())
                    env.store.change("user", "set", text="updated")
                    input.send_text("/memory refresh\r")
                    await wait_for_revision(2)
                    self.assertIn("user r2", ui.header())
                    input.send_text("\x1b[200~/memory off\x1b[201~\r")
                    await wait_for_revision(3)
                    self.assertFalse(env.controller.state.memory_disabled)
                    self.assertEqual(
                        env.controller.state.entries[0].text, "/memory off"
                    )
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)


class RefreshCLITests(TestCase):
    def invoke(
        self, home: Path, *args: str, text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *args],
            env={**os.environ, "HOME": str(home)},
            input=text,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_resume_refresh_off_and_later_resume_keep_same_session(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            store = MemoryStore(home / ".mos-eisley-memory", Path.cwd())
            store.change("user", "set", text="original")
            first = self.invoke(home, text=DEMO_PROMPTS[0] + "\n")
            self.assertEqual(first.returncode, 0, first.stderr)
            path = next((home / ".mos-eisley-sessions").glob("*.json"))
            old = ConversationSnapshot.model_validate_json(path.read_bytes()).state
            store.change("user", "clear")
            refresh = self.invoke(
                home, "resume", "--last", "--refresh-memory", "--no-memory"
            )
            self.assertEqual(refresh.returncode, 0, refresh.stderr)
            refreshed = ConversationSnapshot.model_validate_json(
                path.read_bytes()
            ).state
            self.assertEqual(refreshed.session_id, old.session_id)
            self.assertTrue(refreshed.memory_disabled)
            self.assertEqual(refreshed.exchanges_consumed, 1)
            store.root.chmod(0o755)
            resumed = self.invoke(home, "resume", "--last", text=DEMO_PROMPTS[1] + "\n")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            final = ConversationSnapshot.model_validate_json(path.read_bytes()).state
            self.assertEqual(final.entries[1].answer, "You gave me a boundary of ten.")
            self.assertIsNotNone(final.entries[0].memory_context)
            context = final.entries[1].memory_context
            assert context is not None
            self.assertIsNone(context.memory)

    def test_repeated_refresh_retains_recording_without_requiring_original_file(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            store = MemoryStore(home / ".mos-eisley-memory", Path.cwd())
            store.change("user", "set", text="one")
            self.assertEqual(
                self.invoke(home, text=DEMO_PROMPTS[0] + "\n").returncode, 0
            )
            for text in ("two", "three"):
                store.change("user", "set", text=text)
                result = self.invoke(home, "resume", "--last", "--refresh-memory")
                self.assertEqual(result.returncode, 0, result.stderr)
            result = self.invoke(home, "resume", "--last", text=DEMO_PROMPTS[1] + "\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("You gave me a boundary of ten.", result.stdout)

    def test_custom_cli_replacement_and_prefix_rejection(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            old = demo_cassette(multiline=True)
            old_path = home / "old.json"
            old_path.write_bytes(canonical_bytes(old))
            result = self.invoke(
                home,
                "--cassette",
                str(old_path),
                text="/compose\n" + MULTILINE_PROMPT + "\n/send\n",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path = next((home / ".mos-eisley-sessions").glob("*.json"))
            before = path.read_bytes()
            store = MemoryStore(home / ".mos-eisley-memory", Path.cwd())
            store.change("user", "set", text="new")
            new = demo_cassette(multiline=True, memory=store.load())
            new_path = home / "new.json"
            new_path.write_bytes(canonical_bytes(new))
            args = (
                "resume",
                "--last",
                "--cassette",
                str(old_path),
                "--refresh-memory",
                "--refresh-cassette",
                str(new_path),
            )
            rejected = self.invoke(home, *args)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("consumed exchange", rejected.stderr)
            self.assertEqual(path.read_bytes(), before)
            new_path.write_bytes(
                canonical_bytes(
                    AgentCassette(exchanges=(old.exchanges[0], new.exchanges[1]))
                )
            )
            accepted = self.invoke(home, *args)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            resumed = self.invoke(home, "resume", "--last", text=DEMO_PROMPTS[1] + "\n")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertIn("You gave me a boundary of ten.", resumed.stdout)

    def test_replacement_flag_requires_explicit_refresh_without_writing(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.invoke(
                home, "resume", "--last", "--refresh-cassette", "missing.json"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("requires --refresh-memory", result.stderr)
            self.assertFalse((home / ".mos-eisley-sessions").exists())
