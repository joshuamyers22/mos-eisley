"""Assistant proposals need explicit scoped review and fresh source-bound approval."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationState,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_memory import MEMORY_BYTES, MemoryChangedError, MemoryStore
from mos_eisley.conversation_memory_proposals import proposal
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.agent import AgentUsage
from mos_eisley.demo import demo_inputs


def runtime(root: Path, answer: str) -> ConversationMemoryRuntime:
    store = MemoryStore(root / "memory", root)
    cassette = demo_cassette()
    state = ConversationController.fresh(root, cassette)
    state = state.model_copy(
        update={
            "exchanges_consumed": 1,
            "entries": (
                ConversationEntry(
                    text="Suggest a memory preference.",
                    status="completed",
                    answer=answer,
                    usage=AgentUsage(
                        requests=1,
                        tools=0,
                        billed_input=1,
                        billed_output=1,
                        largest_request=1,
                    ),
                ),
            ),
        }
    )
    controller = ConversationController(state, cassette, lambda state: None)
    env = ConversationMemoryRuntime(
        controller, store, lambda memory: demo_cassette(memory=memory)
    )
    controller.validate_memory = env.check
    return env


def answer(**fields: str) -> str:
    return json.dumps(fields, ensure_ascii=False)


class StorageTests(TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.env = runtime(self.root, answer(operation="append", text="Use pytest."))

    def preview(self, scope: str = "project") -> dict[str, object]:
        return self.env.command(f"/memory review-proposal {scope} 0")

    def apply(self, receipt: dict[str, object]) -> dict[str, object]:
        return self.env.command(
            "/memory apply-proposal " + str(receipt["preview_sha256"])
        )

    def change_answer(self, text: str) -> None:
        controller = cast(
            ConversationController[ConversationState], self.env.controller
        )
        entry = controller.state.entries[0].model_copy(update={"answer": text})
        controller.state = controller.state.model_copy(update={"entries": (entry,)})

    def test_unselected_reply_and_preview_create_no_store_then_apply_only_chosen_scope(
        self,
    ):
        env = self.env
        self.assertFalse(env.store.root.exists())
        before = env.controller.state
        receipt = self.preview("user")
        self.assertFalse(env.store.root.exists())
        self.assertEqual(receipt["after_text"], "Use pytest.")
        self.assertEqual(receipt["before"], None)
        saved = self.apply(receipt)
        self.assertEqual(saved["type"], "conversation.memory.proposal.saved")
        self.assertEqual(env.controller.state, before)
        self.assertIsNone(env.store.read("project"))
        user = env.store.read("user")
        assert user is not None
        self.assertEqual(user.document.text, "Use pytest.")
        self.assertEqual(user.document.source, "explicit_user")
        with self.assertRaises(MemoryChangedError):
            env.check()

    def test_strict_schema_rejects_scope_duplicates_and_embedded_instructions(
        self,
    ):
        invalid = [
            '```json\n{"operation":"append","text":"x"}\n```',
            'Explain {"operation":"append","text":"x"}',
            '{"operation":"append","text":"x","scope":"user"}',
            '{"operation":"append","text":"x","text":"y"}',
            '{"operation":"append","text":true}',
            '{"operation":"append","text":"\\ud800"}',
            '{"operation":"set","text":"x"}',
            '{"operation":"append","text":" "}',
            '{"operation":"replace","old":"x","new":"x"}',
            '{"operation":"replace","old":"x","new":""}',
            '[{"operation":"append","text":"x"}]',
            '{"operation":NaN,"text":"x"}',
            "[]",
            "null",
            "[" * 1500 + "0" + "]" * 1500,
            answer(operation="append", text="x" * 8000),
        ]
        for text in invalid:
            with self.subTest(text=text[:80]), self.assertRaises(ValueError):
                proposal(text)
        self.assertFalse(self.env.store.root.exists())

    def test_commands_require_completed_chat_reply_and_explicit_scope(self):
        for line in (
            "/memory review-proposal 0",
            "/memory review-proposal all 0",
            "/memory review-proposal project -1",
            "/memory review-proposal project 1",
            "/memory review-proposal project 00",
            "/memory review-proposal project 0 extra",
            "/memory review-proposal project 0\n",
            "/memory apply-proposal invalid",
            "/memory discard-proposal extra",
        ):
            with self.subTest(line=line), self.assertRaises(ValueError):
                self.env.command(line)
        controller = cast(
            ConversationController[ConversationState], self.env.controller
        )
        controller.state = controller.state.model_copy(
            update={
                "entries": (
                    ConversationEntry(text='{"operation":"append","text":"user text"}'),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "completed assistant"):
            self.preview()
        self.assertFalse(self.env.store.root.exists())

    def test_append_preserves_disabled_text_and_other_scope(self):
        store = self.env.store
        store.change("project", "set", text="Original\n")
        store.change("project", "disable")
        store.change("user", "set", text="Keep")
        user = store.path("user").read_bytes()
        receipt = self.preview()
        self.assertEqual(receipt["after_text"], "Original\n\n\nUse pytest.")
        self.apply(receipt)
        saved = store.read("project")
        assert saved is not None
        self.assertFalse(saved.document.enabled)
        self.assertEqual(saved.document.revision, 3)
        self.assertEqual(store.path("user").read_bytes(), user)

    def test_replace_and_forget_preserve_exact_surrounding_text(self):
        for fields, expected in (
            (
                {"operation": "replace", "old": "OLD\nline", "new": "New café"},
                " Before New café After ",
            ),
            ({"operation": "forget", "old": "OLD\nline"}, " Before  After "),
        ):
            with self.subTest(fields=fields):
                self.env.store.change("project", "set", text=" Before OLD\nline After ")
                self.change_answer(answer(**fields))
                receipt = self.preview()
                self.assertEqual(receipt["after_text"], expected)
                self.apply(receipt)
                saved = self.env.store.read("project")
                assert saved is not None
                self.assertEqual(saved.document.text, expected)

    def test_overlap_missing_and_result_limits_reject_before_review(self):
        self.env.store.change("project", "set", text="aaaa")
        for old in ("aa", "missing"):
            self.change_answer(answer(operation="forget", old=old))
            with self.assertRaisesRegex(ValueError, "unique exact"):
                self.preview()
        self.env.store.change("project", "set", text="x" * (MEMORY_BYTES - 1))
        self.change_answer(answer(operation="append", text="é"))
        with self.assertRaisesRegex(ValueError, "32 KiB"):
            self.preview()
        self.assertIsNone(self.env.proposals.pending)

    def test_missing_target_created_concurrently_rejects_without_overwrite(self):
        receipt = self.preview()
        self.env.store.change("project", "set", text="Concurrent")
        with self.assertRaisesRegex(ValueError, "fresh review"):
            self.apply(receipt)
        saved = self.env.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "Concurrent")
        self.assertIsNone(self.env.proposals.pending)

    def test_existing_target_changed_or_disabled_rejects_stale_review(self):
        self.env.store.change("project", "set", text="Original")
        for action in ("disable", "clear"):
            receipt = self.preview()
            self.env.store.change("project", action)
            before = self.env.store.path("project").read_bytes()
            with self.assertRaises(ValueError):
                self.apply(receipt)
            self.assertEqual(self.env.store.path("project").read_bytes(), before)

    def test_source_session_answer_or_prompt_changed_consumes_review(self):
        controller = cast(
            ConversationController[ConversationState], self.env.controller
        )
        original = controller.state
        for kind in ("session", "answer", "prompt"):
            controller.state = original
            receipt = self.preview()
            if kind == "session":
                changed = original.model_copy(update={"session_id": "0" * 32})
            else:
                entry = original.entries[0].model_copy(
                    update={
                        "answer" if kind == "answer" else "text": "Changed",
                    }
                )
                changed = original.model_copy(update={"entries": (entry,)})
            controller.state = changed
            with self.assertRaisesRegex(ValueError, "source or target changed"):
                self.apply(receipt)
            self.assertIsNone(self.env.proposals.pending)
            self.assertFalse(self.env.store.root.exists())

    def test_reviews_mutually_invalidate_and_wrong_hash_preserves_current_review(self):
        self.env.store.change("project", "set", text="OLD")
        first = self.preview()
        second = self.preview()
        self.assertNotEqual(first["preview_sha256"], second["preview_sha256"])
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.apply(first)
        self.assertIsNotNone(self.env.proposals.pending)
        self.env.command("/memory show project")
        self.assertIsNotNone(self.env.proposals.pending)
        self.env.command('/memory replace project {"old":"OLD","new":"NEW"}')
        self.assertIsNone(self.env.proposals.pending)
        self.preview()
        self.assertIsNone(self.env.replace.pending)
        self.env.command("/memory forget project OLD")
        self.assertIsNone(self.env.proposals.pending)
        with self.assertRaises(ValueError):
            self.env.command("/memory review-proposal project invalid")
        self.assertIsNone(self.env.forget.pending)
        self.preview()
        self.env.command("/memory append user explicit")
        self.assertIsNone(self.env.proposals.pending)
        self.preview()
        self.env.command("/memory discard-proposal")
        with self.assertRaisesRegex(ValueError, "No proposal review"):
            self.apply(second)

    def test_unsafe_or_corrupt_target_rejects_and_does_not_disclose_contents(self):
        self.env.store.change("project", "set", text="Original")
        path = self.env.store.path("project")
        receipt = self.preview()
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.apply(receipt)
        path.chmod(0o600)
        path.write_text("PRIVATE CANARY")
        with self.assertRaises(ValueError) as raised:
            self.preview()
        self.assertNotIn("CANARY", str(raised.exception))

    def test_post_publish_failure_consumes_review_and_reports_uncertainty(self):
        self.env.store.change("project", "set", text="Original")
        receipt = self.preview()
        real = os.replace

        def fail(src: str, dst: str, *, src_dir_fd: int, dst_dir_fd: int) -> None:
            real(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
            raise OSError("interrupted after publication")

        with (
            patch("mos_eisley.conversation_memory.os.replace", side_effect=fail),
            self.assertRaisesRegex(ValueError, "may already have been published"),
        ):
            self.apply(receipt)
        self.assertIsNone(self.env.proposals.pending)
        saved = self.env.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "Original\n\nUse pytest.")

    def test_receipt_mutation_does_not_change_pending_source_or_proposal(self):
        receipt = self.preview()
        source = receipt["source"]
        change = receipt["proposal"]
        assert isinstance(source, dict) and isinstance(change, dict)
        source["answer"] = "Changed"
        change["text"] = "Changed"
        self.apply(receipt)
        saved = self.env.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "Use pytest.")

    def test_target_rebinding_and_symlink_reject_without_touching_other_file(self):
        receipt = self.preview()
        other = self.root / "other"
        other.mkdir()
        store = self.env.proposals.store
        self.env.proposals.store = MemoryStore(store.root, other)
        with self.assertRaisesRegex(ValueError, "source or target changed"):
            self.apply(receipt)
        self.env.proposals.store = store
        store.change("project", "set", text="Original")
        receipt = self.preview()
        victim = self.root / "victim"
        victim.write_text("Untouched")
        path = store.path("project")
        path.unlink()
        path.symlink_to(victim)
        with self.assertRaises(ValueError):
            self.apply(receipt)
        self.assertEqual(victim.read_text(), "Untouched")

    def test_process_death_after_publish_cannot_replay_parent_review(self):
        self.env.store.change("project", "set", text="Original")
        receipt = self.preview()
        code = r"""
import os, sys
from pathlib import Path
sys.path.insert(0, 'tests')
from test_conversation_memory_proposals import runtime, answer
env = runtime(Path(sys.argv[1]), answer(operation='append', text='Use pytest.'))
review = env.command('/memory review-proposal project 0')
real = os.replace
def crash(*args, **kwargs):
    real(*args, **kwargs)
    os._exit(73)
os.replace = crash
env.command('/memory apply-proposal ' + review['preview_sha256'])
"""
        result = subprocess.run(
            [sys.executable, "-c", code, str(self.root)],
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 73, result.stderr)
        saved = self.env.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "Original\n\nUse pytest.")
        with self.assertRaisesRegex(ValueError, "fresh review"):
            self.apply(receipt)


class TerminalTests(IsolatedAsyncioTestCase):
    async def test_direct_review_apply_pauses_queue_without_model_turn(self):
        with TemporaryDirectory() as directory:
            env = runtime(
                Path(directory), answer(operation="append", text="Preference")
            )
            env.controller.submit(DEMO_PROMPTS[0])
            before = env.controller.state
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            queue.put_nowait("/memory review-proposal project 0")
            events: list[dict[str, object]] = []

            def emit(event: dict[str, object]) -> None:
                events.append(event)
                if event["type"] == "conversation.memory.proposal.preview":
                    queue.put_nowait(
                        "/memory apply-proposal " + str(event["preview_sha256"])
                    )
                    queue.put_nowait(None)

            await terminal(env.controller, queue, emit, memory_command=env.command)
            self.assertEqual(env.controller.state, before)
            self.assertIn("conversation.memory.proposal.saved", str(events))
            self.assertFalse(
                any(event["type"] == "message.running" for event in events)
            )

    async def test_pasted_composed_and_initial_apply_text_is_literal(self):
        with TemporaryDirectory() as directory:
            env = runtime(
                Path(directory), answer(operation="append", text="Preference")
            )
            receipt = env.command("/memory review-proposal project 0")
            apply = "/memory apply-proposal " + str(receipt["preview_sha256"])
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
            self.assertFalse(env.store.root.exists())

    async def test_explicit_refresh_preserves_source_and_off_selection_until_adoption(
        self,
    ):
        with TemporaryDirectory() as directory:
            env = runtime(
                Path(directory), answer(operation="append", text="Preference")
            )
            receipt = env.command("/memory review-proposal project 0")
            old_answer = env.controller.state.entries[0].answer
            env.refresh(True)
            off = env.controller.state
            env.command("/memory apply-proposal " + str(receipt["preview_sha256"]))
            env.check()
            self.assertEqual(env.controller.state, off)
            self.assertTrue(env.ignore_memory)
            env.refresh(False)
            self.assertEqual(env.controller.state.memory, env.store.load())
            self.assertEqual(env.controller.state.entries[0].answer, old_answer)
            self.assertFalse(env.ignore_memory)

    async def test_active_work_blocks_review_apply_and_discard(self):
        with TemporaryDirectory() as directory:
            env = runtime(
                Path(directory), answer(operation="append", text="Preference")
            )
            receipt = env.command("/memory review-proposal project 0")
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
                queue.put_nowait("/memory review-proposal user 0")
                queue.put_nowait(
                    "/memory apply-proposal " + str(receipt["preview_sha256"])
                )
                queue.put_nowait("/memory discard-proposal")
                queue.put_nowait("/quit")
                await asyncio.wait_for(worker, 2)
            self.assertEqual(
                sum("Stop active work" in str(event) for event in events), 3
            )
            self.assertIsNotNone(env.proposals.pending)
            self.assertFalse(env.store.root.exists())

    async def test_review_agent_output_cannot_be_selected_as_chat_proposal(self):
        with TemporaryDirectory() as directory:
            env = runtime(
                Path(directory), answer(operation="append", text="Preference")
            )
            brief, cassette = demo_inputs()
            env.controller.submit_review(
                ConversationReviewPacket(brief=brief, cassette=cassette)
            )
            await env.controller.step()
            with self.assertRaisesRegex(ValueError, "not a review"):
                env.command("/memory review-proposal project 1")
            self.assertFalse(env.store.root.exists())

    async def test_fullscreen_preview_escapes_controls_and_discard_clears_it(self):
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            env = runtime(
                Path(directory),
                answer(operation="append", text="x" * 1000 + "\x1b[31m"),
            )
            ui = ConversationTUI(env.controller, input=input, output=DummyOutput())
            receipt = env.command("/memory review-proposal project 0")
            ui.emit(receipt)
            self.assertIn("x" * 1000, ui.transcript.text)
            self.assertNotIn("\x1b", ui.transcript.text)
            ui.emit(env.command("/memory discard-proposal"))
            self.assertNotIn(str(receipt["preview_sha256"]), ui.transcript.text)
