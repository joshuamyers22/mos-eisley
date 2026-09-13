"""User-only terminal edits preserve dispatch selection and storage boundaries."""

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
from mos_eisley.conversation_memory import MemoryChangedError, MemoryStore
from mos_eisley.conversation_memory_commands import run_memory_command
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_tui import ConversationTUI


def runtime(root: Path) -> ConversationMemoryRuntime:
    store = MemoryStore(root / "memory", root)
    cassette = demo_cassette()
    controller = ConversationController(
        ConversationController.fresh(root, cassette), cassette, lambda state: None
    )
    result = ConversationMemoryRuntime(
        controller, store, lambda memory: demo_cassette(memory=memory)
    )
    controller.validate_memory = result.check
    return result


class CommandTests(TestCase):
    def test_scopes_actions_and_literal_payload(self) -> None:
        with TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory", Path(directory))
            receipt = run_memory_command(
                store, '/memory set project "$(touch NO)" /quit'
            )
            self.assertEqual(receipt["scope"], "project")
            project = store.read("project")
            assert project is not None
            self.assertEqual(project.document.text, '"$(touch NO)" /quit')
            self.assertIsNone(store.read("user"))
            run_memory_command(store, "/memory disable project")
            run_memory_command(store, "/memory append project more")
            current = store.read("project")
            assert current is not None
            self.assertFalse(current.document.enabled)
            self.assertEqual(current.document.text, project.document.text + "\n\nmore")
            shown = run_memory_command(store, "/memory show project")
            self.assertIn(current.sha256, str(shown))
            run_memory_command(store, "/memory enable project")
            run_memory_command(store, "/memory clear project")
            final = store.read("project")
            assert final is not None
            self.assertTrue(final.document.enabled)
            self.assertEqual(final.document.text, "")
            self.assertEqual(final.document.revision, 5)

    def test_invalid_or_ambiguous_commands_never_create_storage(self) -> None:
        with TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory", Path(directory))
            for command in (
                "/memory append text",
                "/memory append user",
                "/memory set project",
                "/memory clear user extra",
                "/memory disable",
                "/memory delete user",
                "/memory append everywhere x",
                "/memory append user x\n/quit",
                "/memory append user \x00",
                "/memory append user " + "x" * 8000,
                "remember this everywhere",
                "/memory refresh user",
            ):
                with self.subTest(command=command[:60]), self.assertRaises(ValueError):
                    run_memory_command(store, command)
                self.assertFalse(store.root.exists())
            self.assertIsNone(
                run_memory_command(store, "/memory show user")["document"]
            )
            self.assertFalse(store.root.exists())

    def test_unsafe_corrupt_and_oversized_documents_fail_without_change(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            store.change("user", "set", text="x" * (32 * 1024))
            original = store.path("user").read_bytes()
            with self.assertRaisesRegex(ValueError, "Inspect the saved"):
                run_memory_command(store, "/memory append user overflow")
            self.assertEqual(store.path("user").read_bytes(), original)
            store.path("user").chmod(0o644)
            with self.assertRaises(ValueError):
                run_memory_command(store, "/memory clear user")
            self.assertEqual(store.path("user").read_bytes(), original)
            store.path("user").chmod(0o600)
            store.path("user").write_text("PRIVATE INVALID CANARY")
            with self.assertRaises(ValueError) as raised:
                run_memory_command(store, "/memory show user")
            self.assertNotIn("CANARY", str(raised.exception))
            store.path("user").unlink()
            victim = root / "victim"
            victim.write_text("untouched")
            store.path("user").symlink_to(victim)
            with self.assertRaises(ValueError):
                run_memory_command(store, "/memory set user replace")
            self.assertEqual(victim.read_text(), "untouched")

    def test_failure_after_replace_reports_uncertain_write(self) -> None:
        with TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory", Path(directory))
            store.change("user", "set", text="before")
            original = os.fsync
            calls = 0

            def fail_directory(fd: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("directory flush failed")
                original(fd)

            with (
                patch(
                    "mos_eisley.conversation_memory.os.fsync",
                    side_effect=fail_directory,
                ),
                self.assertRaisesRegex(ValueError, "may already have been published"),
            ):
                run_memory_command(store, "/memory set user after")
            saved = store.read("user")
            assert saved is not None
            self.assertEqual(saved.document.text, "after")


class TerminalTests(IsolatedAsyncioTestCase):
    async def test_edit_keeps_history_selection_and_queue_until_refresh(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.controller.submit(DEMO_PROMPTS[0])
            await env.controller.step()
            prefix = env.controller.cassette.exchanges[:1]
            history = env.controller.state.entries[0]
            env.controller.submit(DEMO_PROMPTS[1])
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            queue.put_nowait("/memory append project new rule")
            queue.put_nowait(None)
            events: list[dict[str, object]] = []
            await terminal(
                env.controller, queue, events.append, memory_command=env.command
            )
            self.assertIsNone(env.controller.state.memory)
            self.assertEqual(env.controller.state.entries[0], history)
            self.assertEqual(env.controller.state.entries[1].status, "queued")
            self.assertEqual(env.controller.state.exchanges_consumed, 1)
            self.assertIn("conversation.memory.saved", str(events))
            with self.assertRaises(MemoryChangedError):
                env.check()
            env.refresh(False)
            self.assertEqual(env.controller.cassette.exchanges[:1], prefix)
            queue.put_nowait("/continue")
            queue.put_nowait(None)
            await terminal(
                env.controller, queue, events.append, memory_command=env.command
            )
            self.assertEqual(env.controller.state.entries[1].status, "completed")
            self.assertIn(
                "new rule",
                str(env.controller.state.memory),
            )

    async def test_disabled_session_and_failed_edit_keep_selection_and_queue(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.refresh(True)
            env.controller.submit(DEMO_PROMPTS[0])
            before = env.controller.state
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            queue.put_nowait("/memory append user saved while off")
            queue.put_nowait(None)
            events: list[dict[str, object]] = []
            await terminal(
                env.controller, queue, events.append, memory_command=env.command
            )
            self.assertEqual(env.controller.state, before)
            self.assertTrue(env.ignore_memory)
            saved = env.store.read("user")
            assert saved is not None
            self.assertEqual(saved.document.text, "saved while off")
            env.check()
            queue.put_nowait("/memory clear user")
            queue.put_nowait(None)
            with patch.object(env.store, "change", side_effect=OSError("write failed")):
                await terminal(
                    env.controller, queue, events.append, memory_command=env.command
                )
            self.assertEqual(env.controller.state, before)
            self.assertEqual(env.store.read("user"), saved)
            self.assertIn("may already have been published", str(events))

    async def test_paste_composer_and_natural_language_never_edit(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(
                ConversationSubmission("/memory clear user", True, accepted)
            )
            queue.put_nowait("/compose")
            queue.put_nowait("/memory append user injected")
            queue.put_nowait("/send")
            queue.put_nowait("remember this everywhere")
            queue.put_nowait(None)
            await terminal(
                env.controller, queue, lambda event: None, memory_command=env.command
            )
            self.assertTrue(accepted.result())
            self.assertFalse(env.store.root.exists())

    async def test_fullscreen_routes_typed_commands_and_preserves_pastes(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            env = runtime(Path(directory))
            ui = ConversationTUI(
                env.controller,
                memory_command=env.command,
                input=input,
                output=DummyOutput(),
            )
            ui.editor.text = "/memory append user typed"
            ui.send()
            self.assertEqual(await ui.queue.get(), "/memory append user typed")
            ui.editor.text = "/memory clear user"
            ui.send(literal=True)
            await asyncio.sleep(0)
            submitted = await ui.queue.get()
            self.assertIsInstance(submitted, ConversationSubmission)
            assert isinstance(submitted, ConversationSubmission)
            self.assertTrue(submitted.literal)
            submitted.accepted.set_result(True)
            assert ui.submission is not None
            await ui.submission
            self.assertFalse(env.store.root.exists())

    async def test_fullscreen_saved_inspection_is_complete_and_escaped(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            env = runtime(Path(directory))
            env.store.change("user", "set", text="x" * 1000 + "\x1b[31mEND CANARY")
            ui = ConversationTUI(env.controller, input=input, output=DummyOutput())
            ui.emit(env.command("/memory show user"))
            self.assertIn("END CANARY", ui.transcript.text)
            self.assertIn("x" * 1000, ui.transcript.text)
            self.assertNotIn("\x1b", ui.transcript.text)
            ui.emit({"type": "conversation.memory"})
            self.assertNotIn("END CANARY", ui.transcript.text)
            self.assertIn("No memory is active", ui.transcript.text)

    async def test_active_request_rejects_memory_management(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            events: list[dict[str, object]] = []
            started = asyncio.Event()
            release = asyncio.Event()

            async def step(**kwargs: object) -> bool:
                started.set()
                await release.wait()
                return False

            with patch.object(env.controller, "step", side_effect=step):
                worker = asyncio.create_task(
                    terminal(
                        env.controller, queue, events.append, memory_command=env.command
                    )
                )
                queue.put_nowait(DEMO_PROMPTS[0])
                await asyncio.wait_for(started.wait(), 2)
                queue.put_nowait("/memory clear user")
                queue.put_nowait("/quit")
                await asyncio.wait_for(worker, 2)
            self.assertIn("Stop active work", str(events))
            self.assertFalse(env.store.root.exists())


class CLITests(TestCase):
    def test_plain_json_commands_use_selected_project_root_on_both_backends(
        self,
    ) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory)
                workspace = root / "child"
                workspace.mkdir()
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "chat",
                        "--plain",
                        "--json",
                        "--storage-backend",
                        backend,
                        "-C",
                        str(workspace),
                        "--memory-project-root",
                        str(root),
                    ],
                    input=(
                        "/memory append project scoped rule\n"
                        "/memory show project\n/memory refresh\n"
                    ),
                    env={**os.environ, "HOME": str(root)},
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                saved = next(
                    event
                    for event in events
                    if event["type"] == "conversation.memory.saved"
                )
                self.assertEqual(
                    saved["document"]["document"]["workspace"], str(root.resolve())
                )
                self.assertIn("conversation.memory.updated", result.stdout)
                store = MemoryStore(root / ".mos-eisley-memory", root)
                self.assertIsNotNone(store.read("project"))
                self.assertIsNone(MemoryStore(store.root, workspace).read("project"))
