"""Recorded contextual follow-ups, crash recovery, private storage and terminal I/O."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.core.agent import AgentFailure
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore


class WaitingClient:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.started.set()
        await self.release.wait()
        response = demo_cassette().exchanges[0].response
        assert response is not None
        return response


class ConversationTests(IsolatedAsyncioTestCase):
    def controller(self) -> ConversationController:
        cassette = demo_cassette()
        state = ConversationController.fresh(Path.cwd(), cassette)
        return ConversationController(state, cassette, lambda state: None)

    async def test_contextual_followup_and_fresh_separation(self) -> None:
        controller = self.controller()
        for prompt in DEMO_PROMPTS:
            controller.submit(prompt)
            self.assertTrue(await controller.step())
        self.assertEqual(
            controller.state.entries[-1].answer, "You gave me a boundary of ten."
        )
        self.assertEqual(controller.state.exchanges_consumed, 2)
        self.assertFalse(await controller.step())
        fresh = self.controller()
        fresh.submit(DEMO_PROMPTS[1])
        with self.assertRaises(AgentFailure):
            await fresh.step()
        self.assertIsNone(fresh.state.entries[0].answer)
        self.assertEqual(fresh.state.entries[0].status, "failed")

    async def test_queue_during_active_reply_and_no_concurrent_dispatch(self) -> None:
        controller = self.controller()
        controller.submit(DEMO_PROMPTS[0])
        client = WaitingClient()
        task = asyncio.create_task(controller.step(client))
        await client.started.wait()
        controller.submit(DEMO_PROMPTS[1])
        self.assertEqual(
            [e.status for e in controller.state.entries], ["running", "queued"]
        )
        with self.assertRaisesRegex(ValueError, "already active"):
            await controller.step()
        client.release.set()
        await task
        await controller.step()
        self.assertEqual(controller.state.entries[1].status, "completed")

    async def test_cancel_preserves_text_and_burns_attempt(self) -> None:
        controller = self.controller()
        controller.submit(DEMO_PROMPTS[0])
        client = WaitingClient()
        task = asyncio.create_task(controller.step(client))
        await client.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(controller.state.entries[0].status, "cancelled")
        self.assertEqual(controller.state.entries[0].text, DEMO_PROMPTS[0])
        self.assertEqual(controller.state.exchanges_consumed, 1)
        self.assertFalse(await controller.step())

    async def test_crash_resume_marks_interruption_without_replaying(self) -> None:
        controller = self.controller()
        controller.submit(DEMO_PROMPTS[0])
        controller.submit(DEMO_PROMPTS[1])
        client = WaitingClient()
        task = asyncio.create_task(controller.step(client))
        await client.started.wait()
        crashed = controller.state
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        restored = ConversationController(crashed, demo_cassette(), lambda state: None)
        self.assertEqual(
            [e.status for e in restored.state.entries], ["interrupted", "queued"]
        )
        self.assertEqual(restored.state.exchanges_consumed, 1)
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait(None)
        await terminal(restored, queue, lambda event: None)
        self.assertEqual(restored.state.exchanges_consumed, 1)

    async def test_save_failure_before_dispatch_poisoned_handle(self) -> None:
        controller = self.controller()
        controller.submit(DEMO_PROMPTS[0])
        client = WaitingClient()
        with (
            patch.object(controller, "save", side_effect=OSError("disk unavailable")),
            self.assertRaises(OSError),
        ):
            await controller.step(client)
        self.assertFalse(client.started.is_set())
        with self.assertRaisesRegex(ValueError, "persistence failed"):
            await controller.step(client)

    async def test_reply_save_failure_keeps_durable_running_state(self) -> None:
        controller = self.controller()
        controller.submit(DEMO_PROMPTS[0])
        with (
            patch.object(
                controller, "save", side_effect=[None, OSError("disk unavailable")]
            ),
            self.assertRaises(OSError),
        ):
            await controller.step()
        self.assertEqual(controller.state.entries[0].status, "running")

    async def test_bounds_and_queued_cancellation(self) -> None:
        controller = self.controller()
        for text in ("", "  ", "x" * 8001):
            with self.assertRaises(ValueError):
                controller.submit(text)
        for _ in range(16):
            controller.submit("queued")
        with self.assertRaises(ValueError):
            controller.submit("too many")
        controller.cancel_queued()
        self.assertTrue(all(e.status == "cancelled" for e in controller.state.entries))
        self.assertEqual(controller.state.exchanges_consumed, 0)

    async def test_wrong_cassette_and_exhaustion(self) -> None:
        controller = self.controller()
        with self.assertRaisesRegex(ValueError, "exact recorded cassette"):
            ConversationController(
                controller.state.model_copy(update={"cassette_sha256": "0" * 64}),
                demo_cassette(),
                lambda state: None,
            )
        for prompt in DEMO_PROMPTS:
            controller.submit(prompt)
            await controller.step()
        controller.submit("Another question")
        with self.assertRaisesRegex(ValueError, "no remaining exchange"):
            await controller.step()

    async def test_terminal_eof_drains_new_messages_and_emits_progress(self) -> None:
        controller = self.controller()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        for line in (*DEMO_PROMPTS, None):
            queue.put_nowait(line)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append)
        self.assertEqual(controller.state.entries[-1].status, "completed")
        self.assertIn("message.running", [event["type"] for event in events])

    async def test_terminal_continue_stop_quit_and_failure(self) -> None:
        controller = self.controller()
        controller.submit("wrong prompt")
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        for line in ("/help", "/continue", None):
            queue.put_nowait(line)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append)
        self.assertIn("conversation.error", [event["type"] for event in events])
        self.assertIn("conversation.help", [event["type"] for event in events])
        controller.submit("queued")
        queue.put_nowait("/stop")
        queue.put_nowait("/quit")
        await terminal(controller, queue, events.append)
        self.assertEqual(controller.state.entries[-1].status, "cancelled")

    async def test_terminal_stop_after_eof_cancels_active_reply(self) -> None:
        controller = self.controller()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait(DEMO_PROMPTS[0])
        queue.put_nowait(None)
        client = WaitingClient()
        step = controller.step

        async def waiting_step(**kwargs: object) -> bool:
            return await step(client)

        with patch.object(controller, "step", side_effect=waiting_step):
            task = asyncio.create_task(terminal(controller, queue, lambda event: None))
            await client.started.wait()
            queue.put_nowait("/stop")
            await asyncio.wait_for(task, timeout=2)
        self.assertEqual(controller.state.entries[0].status, "cancelled")

    async def test_terminal_quit_preserves_queue_for_explicit_resume(self) -> None:
        controller = self.controller()
        controller.submit(DEMO_PROMPTS[0])
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/quit")
        await terminal(controller, queue, lambda event: None)
        self.assertEqual(controller.state.entries[0].status, "queued")
        queue.put_nowait("/continue")
        queue.put_nowait(None)
        await terminal(controller, queue, lambda event: None)
        self.assertEqual(controller.state.entries[0].status, "completed")


class ConversationStoreTests(TestCase):
    def test_save_resume_context_and_private_modes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with ConversationStore(root, state.session_id, root) as store:
                store.save(state)
                controller = ConversationController(state, cassette, store.save)
                controller.submit(DEMO_PROMPTS[0])
                asyncio.run(controller.step())
            with ConversationStore(root, state.session_id, root) as store:
                restored = ConversationController(store.load(), cassette, store.save)
                restored.submit(DEMO_PROMPTS[1])
                asyncio.run(restored.step())
                self.assertEqual(restored.state.entries[-1].status, "completed")
            for path in root.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_concurrent_writer_and_stale_revision_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = ConversationController.fresh(root, demo_cassette())
            with ConversationStore(root, state.session_id, root) as store:
                store.save(state)
                with self.assertRaises(BlockingIOError):
                    ConversationStore(root, state.session_id, root)
                with self.assertRaises(ValueError):
                    store.save(state)

    def test_owner_workspace_digest_and_identity_mismatch(self) -> None:
        for changes in (
            {"owner_uid": os.getuid() + 1},
            {"workspace": "/another-workspace"},
            {"session_id": "f" * 32},
        ):
            with self.subTest(changes=changes), TemporaryDirectory() as directory:
                root = Path(directory)
                state = ConversationController.fresh(root, demo_cassette())
                with ConversationStore(root, state.session_id, root) as store:
                    store.save(state)
                    changed = state.model_copy(update=changes)
                    snapshot = ConversationSnapshot(
                        state=changed, sha256=digest(canonical_bytes(changed))
                    )
                    (root / f"{state.session_id}.json").write_bytes(
                        canonical_bytes(snapshot)
                    )
                    with self.assertRaises(ValueError):
                        store.load()

    def test_tamper_external_change_and_missing_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = ConversationController.fresh(root, demo_cassette())
            with ConversationStore(root, state.session_id, root) as store:
                store.save(state)
                path = root / f"{state.session_id}.json"
                original = path.read_bytes()
                path.write_bytes(original.replace(b'"revision":0', b'"revision":1'))
                with self.assertRaises(ValueError):
                    store.load()
                changed = state.model_copy(update={"revision": 10})
                path.write_bytes(
                    canonical_bytes(
                        ConversationSnapshot(
                            state=changed, sha256=digest(canonical_bytes(changed))
                        )
                    )
                )
                with self.assertRaises(ValueError):
                    store.save(state.model_copy(update={"revision": 1}))
                path.unlink()
                with self.assertRaisesRegex(ValueError, "disappeared"):
                    store.save(state.model_copy(update={"revision": 1}))

    def test_symlinks_public_permissions_hardlinks_and_oversize(self) -> None:
        for kind in ("symlink", "public", "hardlink", "oversize", "fifo"):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                root = Path(directory)
                state = ConversationController.fresh(root, demo_cassette())
                with ConversationStore(root, state.session_id, root) as store:
                    store.save(state)
                    path = root / f"{state.session_id}.json"
                    if kind == "symlink":
                        path.rename(root / "target")
                        path.symlink_to(root / "target")
                    elif kind == "public":
                        path.chmod(0o644)
                    elif kind == "hardlink":
                        os.link(path, root / "linked")
                    elif kind == "oversize":
                        path.write_bytes(b"x" * 2_000_001)
                    else:
                        path.unlink()
                        os.mkfifo(path, 0o600)
                    with self.assertRaises((OSError, ValueError)):
                        store.load()

    def test_root_and_identifier_boundaries(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = ConversationController.fresh(root, demo_cassette())
            with self.assertRaises(ValueError):
                ConversationStore(root, "../escape", root)
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                ConversationStore(root, state.session_id, root)
            root.chmod(0o700)
            link = root / "link"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaises(OSError):
                ConversationStore(link, state.session_id, root)

    def test_failed_atomic_replace_preserves_previous_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = ConversationController.fresh(root, demo_cassette())
            with ConversationStore(root, state.session_id, root) as store:
                store.save(state)
                with (
                    patch(
                        "mos_eisley.run.conversation_store.os.replace",
                        side_effect=OSError("disk full"),
                    ),
                    self.assertRaises(OSError),
                ):
                    store.save(state.model_copy(update={"revision": 1}))
                self.assertEqual(store.load(), state)
                self.assertFalse(tuple(root.glob("*.tmp")))


class ConversationCLITests(TestCase):
    def test_redirected_file_and_escaped_terminal_output(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = root / "cassette.json"
            cassette.write_bytes(canonical_bytes(demo_cassette()))
            messages = root / "messages.txt"
            messages.write_text("\n".join(DEMO_PROMPTS))
            with messages.open() as stream:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "chat",
                        "--cassette",
                        str(cassette),
                        "--storage",
                        str(root / "sessions"),
                    ],
                    stdin=stream,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )
            self.assertIn("You gave me a boundary of ten.", result.stdout)
            self.assertIn("Saved session", result.stdout)
            messages.write_text("\x1b[31mprivate-text\n")
            with messages.open() as stream:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "chat",
                        "--cassette",
                        str(cassette),
                        "--storage",
                        str(root / "sessions"),
                    ],
                    stdin=stream,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )
            self.assertNotIn("\x1b", result.stdout)
            self.assertIn("\\u001b", result.stdout)

    def test_real_pipe_and_second_process_resume(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = root / "cassette.json"
            command = [sys.executable, "-m", "mos_eisley.cli"]
            subprocess.run(
                command + ["conversation-demo", "--output", str(cassette)],
                check=True,
                capture_output=True,
            )
            options = [
                "--cassette",
                str(cassette),
                "--storage",
                str(root / "sessions"),
                "--workspace",
                str(root),
                "--json",
            ]
            first = subprocess.run(
                command + ["chat", *options],
                input=DEMO_PROMPTS[0] + "\n",
                text=True,
                capture_output=True,
                timeout=15,
                check=True,
            )
            events = [json.loads(line) for line in first.stdout.splitlines()]
            session_id = events[-1]["session_id"]
            second = subprocess.run(
                command + ["resume", session_id, *options],
                input=DEMO_PROMPTS[1] + "\n",
                text=True,
                capture_output=True,
                timeout=15,
                check=True,
            )
            self.assertIn("You gave me a boundary of ten.", second.stdout)
            self.assertNotIn("Traceback", second.stderr)

    def test_invalid_input_fails_without_echoing_payload(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = root / "cassette.json"
            cassette.write_bytes(canonical_bytes(demo_cassette()))
            command = [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "chat",
                "--cassette",
                str(cassette),
                "--storage",
                str(root / "sessions"),
            ]
            result = subprocess.run(
                command, input=b"\xffPRIVATE", capture_output=True, timeout=15
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"PRIVATE", result.stderr)
