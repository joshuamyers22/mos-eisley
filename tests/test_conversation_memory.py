"""Scoped persistence, contextual binding, inspection and stale-memory recovery."""

import asyncio
import fcntl
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

from mos_eisley.conversation import (
    ConversationController,
    ConversationState,
    conversation_config,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_memory import (
    MEMORY_BYTES,
    RECORD_BYTES,
    ConversationMemory,
    MemorySnapshot,
    MemoryStore,
)
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.demo import demo_inputs
from mos_eisley.run.conversation_store import ConversationSnapshot


class MemoryStoreTests(TestCase):
    def test_missing_store_is_read_only_and_documents_are_private(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            self.assertIsNone(store.read("user"))
            self.assertIsNone(store.load())
            self.assertFalse(store.root.exists())
            saved = store.change("user", "set", text="Prefer short answers.")
            self.assertEqual(store.root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(store.path("user").stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.read("user"), saved)
            self.assertEqual(saved.document.revision, 1)

    def test_user_crosses_projects_but_project_content_does_not(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "one", root / "two"
            first.mkdir()
            second.mkdir()
            a, b = (
                MemoryStore(root / "memory", first),
                MemoryStore(root / "memory", second),
            )
            user = a.change("user", "set", text="Use metric units.")
            project = a.change("project", "set", text="This project uses miles.")
            self.assertEqual(a.load(), ConversationMemory(user=user, project=project))
            self.assertEqual(b.load(), ConversationMemory(user=user))
            alias = root / "alias"
            alias.symlink_to(first, target_is_directory=True)
            self.assertEqual(MemoryStore(a.root, alias).load(), a.load())

    def test_append_clear_disable_enable_and_stale_edits(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            first = store.change(
                "user", "append", text="one", expected_sha256="missing"
            )
            second = store.change(
                "user", "append", text="two", expected_sha256=first.sha256
            )
            self.assertEqual(second.document.text, "one\n\ntwo")
            before = store.path("user").read_bytes()
            with self.assertRaisesRegex(ValueError, "changed"):
                store.change("user", "clear", expected_sha256=first.sha256)
            self.assertEqual(store.path("user").read_bytes(), before)
            store.change("user", "disable")
            self.assertIsNone(store.load())
            store.change("user", "enable")
            self.assertIsNotNone(store.load())
            cleared = store.change("user", "clear")
            self.assertEqual(cleared.document.revision, 5)
            self.assertEqual(cleared.document.text, "")
            self.assertIsNone(store.load())

    def test_byte_caps_and_invalid_utf8_records(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            saved = store.change("user", "set", text="old")
            with self.assertRaisesRegex(ValueError, "32 KiB"):
                store.change("user", "set", text="é" * (MEMORY_BYTES // 2 + 1))
            self.assertEqual(store.read("user"), saved)
            store.change("user", "set", text="x" * 20000)
            store.change("project", "set", text="y" * 20000)
            with self.assertRaisesRegex(ValueError, "combined"):
                store.load()
            store.path("user").write_bytes(b"x" * (RECORD_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "byte limit"):
                store.read("user")
            store.path("user").write_bytes(b"\xff")
            with self.assertRaises(ValueError):
                store.read("user")

    def test_serialized_context_is_bounded_before_a_request(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            store.change("user", "set", text="\x00" * 6000)
            with self.assertRaisesRegex(ValueError, "serialized"):
                store.load()

    def test_storage_rejects_symlinks_public_paths_hardlinks_and_fifo(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            store.change("user", "set", text="private")
            path = store.path("user")
            before = path.read_bytes()
            os.link(path, root / "alias")
            with self.assertRaises(ValueError):
                store.read("user")
            (root / "alias").unlink()
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                store.read("user")
            path.unlink()
            target = root / "target"
            target.write_bytes(before)
            path.symlink_to(target)
            with self.assertRaises(OSError):
                store.change("user", "clear")
            path.unlink()
            os.mkfifo(path, mode=0o600)
            with self.assertRaises(ValueError):
                store.read("user")
            path.unlink()
            store.root.chmod(0o755)
            with self.assertRaises(ValueError):
                store.load()
            store.root.chmod(0o700)
            alias = root / "root-alias"
            alias.symlink_to(store.root, target_is_directory=True)
            with self.assertRaises(OSError):
                MemoryStore(alias, root).load()

    def test_foreign_owner_project_and_tampered_digest_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            saved = store.change("project", "set", text="private")
            for updates in (
                {"owner_uid": os.getuid() + 1},
                {"workspace": "/another-project"},
            ):
                document = saved.document.model_copy(update=updates)
                altered = MemorySnapshot(
                    document=document, sha256=digest(canonical_bytes(document))
                )
                store.path("project").write_bytes(canonical_bytes(altered))
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    store.read("project")
            altered = saved.model_copy(update={"sha256": "0" * 64})
            store.path("project").write_bytes(canonical_bytes(altered))
            with self.assertRaisesRegex(ValueError, "integrity"):
                store.load()

    def test_lock_contention_and_atomic_write_failure_keep_committed_content(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            saved = store.change("user", "set", text="old")
            with (store.root / "memory.lock").open("rb") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    store.change("user", "clear")
                with self.assertRaises(BlockingIOError):
                    store.load()
            with (
                patch(
                    "mos_eisley.conversation_memory.os.replace",
                    side_effect=OSError("disk failure"),
                ),
                self.assertRaises(OSError),
            ):
                store.change("user", "set", text="new")
            self.assertEqual(store.read("user"), saved)
            self.assertEqual(list(store.root.glob("*.tmp")), [])


class MemoryConversationTests(IsolatedAsyncioTestCase):
    async def test_deleted_memory_pauses_before_dispatch_without_burning_an_attempt(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            store.change("user", "set", text="Preference to forget.")
            memory = store.load()
            cassette = demo_cassette(memory=memory)
            state = ConversationController.fresh(root, cassette, memory)
            controller = ConversationController(
                state,
                cassette,
                lambda state: None,
                validate_memory=lambda: store.check(memory),
            )
            controller.submit(DEMO_PROMPTS[0])
            store.change("user", "clear")
            queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
            queue.put_nowait("/continue")
            queue.put_nowait(None)
            events: list[dict[str, object]] = []
            await terminal(controller, queue, events.append)
            self.assertIn("Saved memory changed", str(events))
            self.assertEqual(controller.state.exchanges_consumed, 0)
            self.assertEqual(controller.state.entries[0].status, "queued")

    async def test_memory_is_in_request_and_preserved_across_transitions(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            store.change("user", "set", text="Prefer metric units.")
            store.change("project", "set", text="For this project use miles.")
            memory = store.load()
            cassette = demo_cassette(memory=memory)
            state = ConversationController.fresh(root, cassette, memory)
            captured: list[ModelRequest] = []

            class Client:
                async def complete(self, request: ModelRequest) -> ModelResponse:
                    captured.append(request)
                    response = cassette.exchanges[0].response
                    assert response is not None
                    return response

            controller = ConversationController(state, cassette, lambda state: None)
            controller.submit(DEMO_PROMPTS[0])
            await controller.step(client=Client())
            request = captured[0]
            self.assertIn("Prefer metric units.", request.system)
            self.assertIn("For this project use miles.", request.system)
            self.assertIn("current user instructions override both", request.system)
            self.assertEqual(request.tools, ())
            self.assertEqual(
                request.turns[0].blocks[0].model_dump()["text"], DEMO_PROMPTS[0]
            )
            self.assertEqual(controller.state.memory, memory)
            controller.submit(DEMO_PROMPTS[1])
            await controller.step()
            self.assertEqual(
                controller.state.entries[-1].answer, "You gave me a boundary of ten."
            )
            self.assertEqual(controller.state.memory, memory)

    async def test_inspection_does_not_dispatch_and_review_stays_isolated(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            store.change("user", "set", text="PRIVATE MEMORY CANARY")
            memory = store.load()
            cassette = demo_cassette(memory=memory)
            controller = ConversationController(
                ConversationController.fresh(root, cassette, memory),
                cassette,
                lambda state: None,
            )
            queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
            for item in ("/memory", "/directory", None):
                queue.put_nowait(item)
            events: list[dict[str, object]] = []
            await terminal(controller, queue, events.append)
            self.assertIn("PRIVATE MEMORY CANARY", str(events))
            self.assertEqual(controller.state.entries, ())
            self.assertEqual(controller.state.exchanges_consumed, 0)
            brief, review_cassette = demo_inputs()
            controller.submit_review(
                ConversationReviewPacket(brief=brief, cassette=review_cassette)
            )
            await controller.step()
            review = controller.state.entries[0]
            self.assertEqual(review.status, "completed")
            self.assertNotIn("PRIVATE MEMORY CANARY", review.model_dump_json())

    async def test_screen_shows_scopes_and_toggles_full_memory_without_dispatch(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MemoryStore(root / "memory", root)
            store.change("user", "set", text="Memory text\n" + "x" * 500 + "END")
            memory = store.load()
            cassette = demo_cassette(memory=memory)
            controller = ConversationController(
                ConversationController.fresh(root, cassette, memory),
                cassette,
                lambda state: None,
            )
            controller.submit(DEMO_PROMPTS[0])
            await controller.step()
            with create_pipe_input() as input:
                ui = ConversationTUI(controller, input=input, output=DummyOutput())
                task = asyncio.create_task(ui.run())

                async def until_visible(value: bool) -> None:
                    async with asyncio.timeout(3):
                        while ui.memory_visible != value:
                            await asyncio.sleep(0.01)

                try:
                    self.assertIn("user r1 / project none", ui.header())
                    self.assertIn("Directory:", ui.header())
                    input.send_text("/memory\r")
                    await until_visible(True)
                    self.assertIn("END", ui.transcript.text)
                    self.assertGreater(
                        ui.transcript.text.index("Memory text"),
                        ui.transcript.text.index("The fixture boundary is ten."),
                    )
                    input.send_text("/memory\r")
                    await until_visible(False)
                    self.assertNotIn("END", ui.transcript.text)
                    self.assertEqual(len(controller.state.entries), 1)
                    input.send_text("/directory\r")
                    async with asyncio.timeout(3):
                        while not ui.directory_visible:
                            await asyncio.sleep(0.01)
                    self.assertTrue(ui.transcript.text.endswith(str(root.resolve())))
                    self.assertEqual(controller.state.exchanges_consumed, 1)
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)

    async def test_legacy_snapshots_and_foreign_memory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            self.assertNotIn("memory", state.model_dump())
            self.assertEqual(
                ConversationState.model_validate_json(canonical_bytes(state)), state
            )
            store = MemoryStore(root / "memory", root)
            project = store.change("project", "set", text="private")
            other = root / "other"
            other.mkdir()
            with self.assertRaisesRegex(ValueError, "different project"):
                ConversationController.fresh(
                    other, cassette, ConversationMemory(project=project)
                )
            # Empty memory leaves old request hashes intact.
            self.assertNotIn(
                "Saved context", conversation_config((state_turn(),)).system
            )


def state_turn():
    from mos_eisley.core.protocol import TextBlock, Turn

    return Turn(role="user", blocks=(TextBlock(text="hello"),))


class MemoryCLITests(TestCase):
    def invoke(
        self, root: Path, *arguments: str, text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *arguments],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "HOME": str(root)},
            timeout=15,
        )

    def test_commands_load_defaults_and_resume_rejects_changed_memory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.invoke(
                root,
                "memory",
                "append",
                "--scope",
                "user",
                "--text",
                "Prefer concise explanations.",
                "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(result.stdout)["snapshot"]
            first = self.invoke(root, text=DEMO_PROMPTS[0] + "\n")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("The fixture boundary is ten.", first.stdout)
            path = next((root / ".mos-eisley-sessions").glob("*.json"))
            state = ConversationSnapshot.model_validate_json(path.read_bytes()).state
            self.assertIsNotNone(state.memory)
            resumed = self.invoke(root, "resume", "--last", text=DEMO_PROMPTS[1] + "\n")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            changed = self.invoke(
                root,
                "memory",
                "clear",
                "--scope",
                "user",
                "--expected-sha256",
                snapshot["sha256"],
            )
            self.assertEqual(changed.returncode, 0, changed.stderr)
            before = path.read_bytes()
            rejected = self.invoke(root, "resume", "--last")
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("Saved memory changed", rejected.stderr)
            self.assertEqual(path.read_bytes(), before)
            fresh = self.invoke(root, "--no-memory", text=DEMO_PROMPTS[0] + "\n")
            self.assertEqual(fresh.returncode, 0, fresh.stderr)

    def test_no_memory_bypasses_unsafe_storage_and_help_has_no_effects(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory_root = root / ".mos-eisley-memory"
            memory_root.mkdir()
            memory_root.chmod(0o755)
            result = self.invoke(root)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / ".mos-eisley-sessions").exists())
            result = self.invoke(root, "--no-memory", text=DEMO_PROMPTS[0] + "\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            state = ConversationSnapshot.model_validate_json(
                next((root / ".mos-eisley-sessions").glob("*.json")).read_bytes()
            ).state
            self.assertIsNone(state.memory)
            self.assertEqual(list(memory_root.iterdir()), [])

    def test_memory_command_validation_and_terminal_escaping(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for arguments in (
                ("set", "--scope", "user"),
                ("clear", "--scope", "user", "--text", "oops"),
                ("show", "--scope", "user", "--expected-sha256", "missing"),
            ):
                result = self.invoke(root, "memory", *arguments)
                self.assertEqual(result.returncode, 2)
                self.assertFalse((root / ".mos-eisley-memory").exists())
            source = root / "notes.md"
            source.write_text("line one\n\x1b[31m\u202e")
            saved = self.invoke(
                root, "memory", "set", "--scope", "project", "--text-file", str(source)
            )
            self.assertEqual(saved.returncode, 0, saved.stderr)
            self.assertNotIn("\x1b", saved.stdout)
            self.assertNotIn("\u202e", saved.stdout)
            self.assertIn("\\u001b", saved.stdout)
            shown = self.invoke(root, "memory", "show", "--scope", "project", "--json")
            self.assertEqual(
                json.loads(shown.stdout)["snapshot"]["document"]["text"],
                source.read_text(),
            )

    def test_explicit_demo_generator_binds_memory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            saved = self.invoke(
                root, "memory", "set", "--scope", "user", "--text", "Prefer examples."
            )
            self.assertEqual(saved.returncode, 0, saved.stderr)
            path = root / "cassette.json"
            demo = self.invoke(root, "conversation-demo", "--output", str(path))
            self.assertEqual(demo.returncode, 0, demo.stderr)
            chat = self.invoke(
                root,
                "chat",
                "--cassette",
                str(path),
                text="\n".join(DEMO_PROMPTS) + "\n",
            )
            self.assertEqual(chat.returncode, 0, chat.stderr)
            self.assertIn("You gave me a boundary of ten.", chat.stdout)
