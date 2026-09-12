"""Exact replacement reviews preserve unrelated text and reject stale confirmations."""

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
from mos_eisley.conversation_memory import (
    MEMORY_BYTES,
    MemoryChangedError,
    MemoryRefreshError,
    MemoryStore,
)
from mos_eisley.conversation_memory_replace import MemoryReplace
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_tui import ConversationTUI


def command(old: str, new: str, scope: str = "project") -> str:
    return (
        "/memory replace "
        + scope
        + " "
        + json.dumps({"old": old, "new": new}, ensure_ascii=False)
    )


def runtime(root: Path) -> ConversationMemoryRuntime:
    store = MemoryStore(root / "memory", root)
    store.change("project", "set", text="Before. OLD. After.")
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


class ReplacementTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = MemoryStore(self.root / "memory", self.root)
        self.replace = MemoryReplace(self.store)

    def preview(self, old: str, new: str, scope: str = "project") -> str:
        receipt = self.replace.command(command(old, new, scope))
        assert receipt is not None
        return str(receipt["preview_sha256"])

    def test_preview_and_apply_preserve_other_scope_whitespace_and_disabled_state(
        self,
    ) -> None:
        self.store.change("project", "set", text=" First\nOLD\nLast ")
        self.store.change("project", "disable")
        self.store.change("user", "set", text="untouched")
        before = self.store.path("project").read_bytes()
        user = self.store.path("user").read_bytes()
        token = self.preview("First\nOLD", "New café\n$(command)")
        self.assertEqual(self.store.path("project").read_bytes(), before)
        result = self.replace.apply(token)
        self.assertEqual(result["type"], "conversation.memory.replace.saved")
        self.assertEqual(result["replacement_text"], "New café\n$(command)")
        saved = self.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, " New café\n$(command)\nLast ")
        self.assertFalse(saved.document.enabled)
        self.assertEqual(saved.document.revision, 3)
        self.assertEqual(self.store.path("user").read_bytes(), user)

    def test_invalid_json_types_duplicates_controls_and_noops_never_create_storage(
        self,
    ) -> None:
        payloads = [
            "{}",
            "[]",
            "null",
            '{"old":"x","new":"y","extra":1}',
            '{"old":"x","old":"y","new":"z"}',
            '{"old":"x","new":true}',
            '{"old":"x","new":NaN}',
            '{"old":{"x":"y"},"new":"z"}',
            '{"old":"","new":"x"}',
            '{"old":"x","new":""}',
            '{"old":"x","new":"x"}',
            '{"old":"x","new":"\\ud800"}',
            "[" * 1500 + "0" + "]" * 1500,
            "not json",
        ]
        for payload in payloads:
            with self.subTest(payload=payload[:80]), self.assertRaises(ValueError):
                self.replace.command("/memory replace project " + payload)
            self.assertFalse(self.store.root.exists())
        for line in (
            command("x", "y", "all"),
            command("x", "y") + "\n",
            command("x", "y") + "\x00",
            command("x", "y" * 8000),
            "/memory apply-replace wrong",
            "/memory discard-replace extra",
        ):
            with self.assertRaises(ValueError):
                self.replace.command(line)
            self.assertFalse(self.store.root.exists())

    def test_unique_match_required_including_overlap_and_unicode_exactness(
        self,
    ) -> None:
        self.store.change("project", "set", text="aaaa repeat repeat café")
        before = self.store.path("project").read_bytes()
        for old in ("aa", "repeat", "cafe\u0301", "MISSING"):
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.preview(old, "replacement")
        self.assertEqual(self.store.path("project").read_bytes(), before)

    def test_result_byte_limit_checked_before_review_and_exact_limit_succeeds(
        self,
    ) -> None:
        self.store.change("project", "set", text="x" * (MEMORY_BYTES - 4) + "END")
        before = self.store.path("project").read_bytes()
        with self.assertRaisesRegex(ValueError, "32 KiB"):
            self.preview("END", "ééé")
        self.assertIsNone(self.replace.pending)
        self.assertEqual(self.store.path("project").read_bytes(), before)
        token = self.preview("END", "éé")
        self.replace.apply(token)
        saved = self.store.read("project")
        assert saved is not None
        self.assertEqual(len(saved.document.text.encode()), MEMORY_BYTES)

    def test_stale_and_wrong_tokens_do_not_overwrite_concurrent_edits(self) -> None:
        self.store.change("project", "set", text="OLD")
        token = self.preview("OLD", "NEW")
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.replace.apply("0" * 64)
        self.assertIsNotNone(self.replace.pending)
        self.store.change("project", "append", text="concurrent")
        with self.assertRaisesRegex(ValueError, "fresh preview"):
            self.replace.apply(token)
        self.assertIsNone(self.replace.pending)
        saved = self.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "OLD\n\nconcurrent")

    def test_replaced_discarded_and_cross_session_reviews_cannot_replay(self) -> None:
        self.store.change("project", "set", text="OLD")
        first = self.preview("OLD", "NEW")
        second = self.preview("OLD", "NEW")
        self.assertNotEqual(first, second)
        with self.assertRaises(ValueError):
            self.replace.apply(first)
        with self.assertRaisesRegex(ValueError, "No replace preview"):
            MemoryReplace(self.store).apply(second)
        self.replace.command("/memory discard-replace")
        with self.assertRaises(ValueError):
            self.replace.apply(second)
        self.preview("OLD", "NEW")
        with self.assertRaises(ValueError):
            self.replace.command("/memory replace project {}")
        self.assertIsNone(self.replace.pending)

    def test_unsafe_corrupt_and_retargeted_store_reject_apply(self) -> None:
        self.store.change("project", "set", text="OLD")
        token = self.preview("OLD", "NEW")
        other = self.root / "other"
        other.mkdir()
        self.replace.store = MemoryStore(self.store.root, other)
        with self.assertRaisesRegex(ValueError, "target changed"):
            self.replace.apply(token)
        self.replace.store = self.store
        for kind in ("public", "corrupt", "symlink"):
            with self.subTest(kind=kind):
                path = self.store.path("project")
                path.unlink()
                self.store.change("project", "set", text="OLD")
                token = self.preview("OLD", "NEW")
                victim = self.root / "victim"
                victim.write_text("untouched")
                if kind == "public":
                    path.chmod(0o644)
                elif kind == "corrupt":
                    path.write_text("PRIVATE CANARY")
                else:
                    path.unlink()
                    path.symlink_to(victim)
                with self.assertRaises(ValueError) as raised:
                    self.replace.apply(token)
                self.assertNotIn("CANARY", str(raised.exception))
                self.assertEqual(victim.read_text(), "untouched")

    def test_directory_flush_failure_consumes_review_and_reports_possible_publication(
        self,
    ) -> None:
        self.store.change("project", "set", text="OLD")
        token = self.preview("OLD", "NEW")
        original = os.fsync
        calls = 0

        def fail(fd: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("flush failed")
            original(fd)

        with (
            patch("mos_eisley.conversation_memory.os.fsync", side_effect=fail),
            self.assertRaisesRegex(ValueError, "may already have been published"),
        ):
            self.replace.apply(token)
        self.assertIsNone(self.replace.pending)
        saved = self.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "NEW")


class RuntimeTests(IsolatedAsyncioTestCase):
    async def test_review_kinds_invalidate_each_other_and_ordinary_writes(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            old = env.command("/memory forget project OLD")
            new = env.command(command("OLD", "NEW"))
            self.assertIsNone(env.forget.pending)
            with self.assertRaisesRegex(ValueError, "No forget preview"):
                env.command("/memory apply-forget " + str(new["preview_sha256"]))
            with self.assertRaisesRegex(ValueError, "does not match"):
                env.command("/memory apply-replace " + str(old["preview_sha256"]))
            env.command("/memory show project")
            self.assertIsNotNone(env.replace.pending)
            env.command("/memory forget project OLD")
            self.assertIsNone(env.replace.pending)
            with self.assertRaises(ValueError):
                env.command("/memory replace project {}")
            self.assertIsNone(env.forget.pending)
            env.command(command("OLD", "NEW"))
            env.command("/memory append user new rule")
            self.assertIsNone(env.replace.pending)

    async def test_apply_preserves_history_cassette_selection_and_paused_queue(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.controller.submit(DEMO_PROMPTS[0])
            await env.controller.step()
            history = env.controller.state.entries[0]
            cassette = env.controller.cassette
            env.controller.submit(DEMO_PROMPTS[1])
            before = env.controller.state
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            queue.put_nowait(command("OLD", "NEW"))
            events: list[dict[str, object]] = []

            def emit(event: dict[str, object]) -> None:
                events.append(event)
                if event["type"] == "conversation.memory.replace.preview":
                    self.assertEqual(env.store.load(), before.memory)
                    queue.put_nowait(
                        "/memory apply-replace " + str(event["preview_sha256"])
                    )
                    queue.put_nowait(None)

            await terminal(env.controller, queue, emit, memory_command=env.command)
            self.assertEqual(env.controller.state, before)
            self.assertEqual(env.controller.cassette, cassette)
            with self.assertRaises(MemoryChangedError):
                env.check()
            env.refresh(False)
            retained = env.controller.state.entries[0]
            self.assertEqual(
                retained.model_copy(update={"memory_context": None}), history
            )
            assert retained.memory_context is not None
            self.assertEqual(retained.memory_context.memory, before.memory)
            self.assertEqual(env.controller.state.entries[1].status, "queued")
            self.assertEqual(
                env.controller.cassette.exchanges[:1], cassette.exchanges[:1]
            )

    async def test_literal_apply_composer_and_initial_prompt_cannot_mutate(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            receipt = env.command(command("OLD", "NEW"))
            before = env.store.path("project").read_bytes()
            apply = "/memory apply-replace " + str(receipt["preview_sha256"])
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(ConversationSubmission(apply, True, accepted))
            queue.put_nowait("/compose")
            queue.put_nowait(apply)
            queue.put_nowait("/send")
            queue.put_nowait(None)
            await terminal(
                env.controller,
                queue,
                lambda event: None,
                memory_command=env.command,
                initial_prompt=apply,
            )
            self.assertTrue(accepted.result())
            self.assertEqual(env.store.path("project").read_bytes(), before)

    async def test_off_selection_stays_off_after_saved_replacement(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.refresh(True)
            before = env.controller.state
            receipt = env.command(command("OLD", "NEW"))
            env.command("/memory apply-replace " + str(receipt["preview_sha256"]))
            env.check()
            self.assertTrue(env.ignore_memory)
            self.assertEqual(env.controller.state, before)
            env.refresh(False)
            self.assertFalse(env.ignore_memory)
            self.assertEqual(env.controller.state.memory, env.store.load())

    async def test_growth_can_save_but_refresh_rejects_combined_context_limit(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            env.store.change("user", "set", text="u" * 32000)
            env.refresh(False)
            before = env.controller.state
            cassette = env.controller.cassette
            receipt = env.command(command("OLD", "n" * 1000))
            env.command("/memory apply-replace " + str(receipt["preview_sha256"]))
            with self.assertRaisesRegex(MemoryRefreshError, "could not be loaded"):
                env.refresh(False)
            self.assertEqual(env.controller.state, before)
            self.assertEqual(env.controller.cassette, cassette)
            saved = env.store.read("project")
            assert saved is not None
            self.assertIn("n" * 1000, saved.document.text)

    async def test_active_request_rejects_preview_and_apply(self) -> None:
        with TemporaryDirectory() as directory:
            env = runtime(Path(directory))
            receipt = env.command(command("OLD", "NEW"))
            started = asyncio.Event()
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            events: list[dict[str, object]] = []

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
                queue.put_nowait(command("OLD", "OTHER"))
                queue.put_nowait(
                    "/memory apply-replace " + str(receipt["preview_sha256"])
                )
                queue.put_nowait("/quit")
                await asyncio.wait_for(worker, 2)
            self.assertEqual(
                sum("Stop active work" in str(event) for event in events), 2
            )
            self.assertIsNotNone(env.replace.pending)

    async def test_fullscreen_preview_is_complete_escaped_and_discarded(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            env = runtime(Path(directory))
            ui = ConversationTUI(env.controller, input=input, output=DummyOutput())
            receipt = env.command(command("OLD", "x" * 1000 + "\x1b[31mNEW"))
            ui.emit(receipt)
            self.assertIn("x" * 1000, ui.transcript.text)
            self.assertIn(str(receipt["preview_sha256"]), ui.transcript.text)
            self.assertNotIn("\x1b", ui.transcript.text)
            ui.emit(env.command("/memory discard-replace"))
            self.assertNotIn(str(receipt["preview_sha256"]), ui.transcript.text)
            self.assertIn("preview discarded", ui.transcript.text)


class CrashTests(TestCase):
    def test_process_death_after_publish_rejects_old_review(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env = runtime(root)
            preview = env.command(command("OLD", "NEW"))
            code = """
import os, sys
from pathlib import Path
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_replace import MemoryReplace
root=Path(sys.argv[1]); edits=MemoryReplace(MemoryStore(root/'memory',root))
receipt=edits.command('/memory replace project {"old":"OLD","new":"NEW"}')
replace=os.replace
def crash(*args,**kwargs):
    replace(*args,**kwargs)
    os._exit(73)
os.replace=crash
edits.apply(receipt['preview_sha256'])
"""
            result = subprocess.run(
                [sys.executable, "-c", code, str(root)], capture_output=True, timeout=20
            )
            self.assertEqual(result.returncode, 73, result.stderr)
            saved = env.store.read("project")
            assert saved is not None
            self.assertEqual(saved.document.text, "Before. NEW. After.")
            with self.assertRaisesRegex(ValueError, "fresh preview"):
                env.command("/memory apply-replace " + str(preview["preview_sha256"]))


class CLITests(TestCase):
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
                cli_command = [
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
                    cli_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={**os.environ, "HOME": str(root)},
                ) as process:
                    assert process.stdin is not None and process.stdout is not None
                    try:
                        process.stdin.write(
                            (command("Remove.", "New.") + "\n").encode()
                        )
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
                                        == "conversation.memory.replace.preview"
                                    ):
                                        token = str(event["preview_sha256"])
                                        self.assertEqual(
                                            event["after_text"], "Keep. New. End."
                                        )
                                        self.assertEqual(event["workspace"], str(root))
                        output, errors = process.communicate(
                            (
                                f"/memory apply-replace {token}\n" + "/memory refresh\n"
                            ).encode(),
                            timeout=20,
                        )
                    except BaseException:
                        process.kill()
                        process.communicate()
                        raise
                self.assertEqual(process.returncode, 0, errors.decode())
                events = [json.loads(line) for line in output.splitlines()]
                self.assertIn("conversation.memory.replace.saved", str(events))
                self.assertIn("conversation.memory.updated", str(events))
                self.assertFalse(
                    any(event["type"].startswith("message.") for event in events)
                )
                saved = store.read("project")
                assert saved is not None
                self.assertEqual(saved.document.text, "Keep. New. End.")
                self.assertEqual(store.path("user").read_bytes(), user)
                self.assertIsNone(MemoryStore(store.root, child).read("project"))
                resumed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "resume",
                        "--last",
                        "--json",
                        "--plain",
                        "--storage-backend",
                        backend,
                        "-C",
                        str(child),
                        "--memory-storage",
                        str(store.root),
                    ],
                    input=f"/memory apply-replace {token}\n/memory show project\n",
                    env={**os.environ, "HOME": str(root)},
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                self.assertIn("No replace preview", resumed.stdout)
                self.assertIn("Keep. New. End.", resumed.stdout)
                self.assertEqual(store.read("project"), saved)
