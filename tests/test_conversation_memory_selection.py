"""Explicit spans of ordinary replies need fresh source-bound memory confirmation."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import test_conversation_memory_proposals as fixtures
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import DEMO_PROMPTS, terminal
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_memory import MEMORY_BYTES
from mos_eisley.conversation_memory_proposals import selected_text
from mos_eisley.conversation_tui import ConversationTUI


def select(text: str, scope: str = "project") -> str:
    return f"/memory review-text {scope} 0 " + json.dumps(text, ensure_ascii=False)


class SelectionTests(TestCase):
    def test_preview_append_retains_complete_source_offsets_and_disabled_state(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            text = 'Use "pytest".\nKeep café fixtures.'
            source = "Suggestion:\n" + text + "\nThat is my suggestion."
            env = fixtures.runtime(Path(directory), source)
            env.store.change("project", "set", text="Original\n")
            env.store.change("project", "disable")
            env.store.change("user", "set", text="Untouched")
            original = env.store.path("project").read_bytes()
            user = env.store.path("user").read_bytes()
            state = env.controller.state
            receipt = env.command(select(text))
            self.assertEqual(receipt["operation"], "accept_selected_assistant_text")
            self.assertEqual(receipt["selection_start"], len("Suggestion:\n"))
            self.assertEqual(receipt["selection_end"], len("Suggestion:\n" + text))
            self.assertEqual(receipt["after_text"], "Original\n\n\n" + text)
            self.assertIn(source, str(receipt["text"]))
            self.assertEqual(env.store.path("project").read_bytes(), original)
            saved_receipt = env.command(
                "/memory apply-proposal " + str(receipt["preview_sha256"])
            )
            self.assertEqual(
                saved_receipt["type"], "conversation.memory.proposal.saved"
            )
            saved = env.store.read("project")
            assert saved is not None
            self.assertEqual(saved.document.text, "Original\n\n\n" + text)
            self.assertFalse(saved.document.enabled)
            self.assertEqual(saved.document.revision, 3)
            self.assertEqual(env.store.path("user").read_bytes(), user)
            self.assertEqual(env.controller.state, state)

    def test_missing_duplicate_overlapping_case_and_normalization_matches_reject(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = fixtures.runtime(Path(directory), "aaaa repeat repeat café")
            for text in ("aa", "repeat", "cafe\u0301", "CAFÉ", "missing"):
                with (
                    self.subTest(text=text),
                    self.assertRaisesRegex(ValueError, "exactly once"),
                ):
                    env.command(select(text))
                self.assertFalse(env.store.root.exists())
                self.assertIsNone(env.proposals.pending)

    def test_selection_requires_bounded_json_string_and_explicit_source_scope(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = fixtures.runtime(Path(directory), "Preference")
            for payload in (
                "Preference",
                '"Preference" extra',
                "[]",
                "{}",
                "null",
                "true",
                "1",
                '""',
                '" "',
                '"\\ud800"',
                "[" * 1500 + "0" + "]" * 1500,
            ):
                with self.subTest(payload=payload[:40]), self.assertRaises(ValueError):
                    env.command("/memory review-text project 0 " + payload)
            for line in (
                '/memory review-text project "Preference"',
                '/memory review-text all 0 "Preference"',
                '/memory review-text user 1 "Preference"',
                select("Preference") + "\n",
                select("Preference") + "\x00",
                select("x" * 8000),
            ):
                with self.subTest(line=line[:40]), self.assertRaises(ValueError):
                    env.command(line)
            self.assertFalse(env.store.root.exists())

    def test_selection_refuses_result_overflow_before_review(self) -> None:
        with TemporaryDirectory() as directory:
            env = fixtures.runtime(Path(directory), "Suggest é.")
            env.store.change("project", "set", text="x" * (MEMORY_BYTES - 3))
            before = env.store.path("project").read_bytes()
            with self.assertRaisesRegex(ValueError, "32 KiB"):
                env.command(select("é"))
            self.assertEqual(env.store.path("project").read_bytes(), before)
            self.assertIsNone(env.proposals.pending)

    def test_source_change_outside_selected_span_rejects_confirmation(self) -> None:
        with TemporaryDirectory() as directory:
            env = fixtures.runtime(Path(directory), "Prefix. Preference. Suffix.")
            receipt = env.command(select("Preference."))
            controller = cast(ConversationController[ConversationState], env.controller)
            entry = controller.state.entries[0].model_copy(
                update={
                    "answer": "Changed prefix. Preference. Suffix.",
                }
            )
            controller.state = controller.state.model_copy(update={"entries": (entry,)})
            with self.assertRaisesRegex(ValueError, "source or target changed"):
                env.command("/memory apply-proposal " + str(receipt["preview_sha256"]))
            self.assertIsNone(env.proposals.pending)
            self.assertFalse(env.store.root.exists())

    def test_all_review_kinds_invalidate_selections_and_wrong_hash_cannot_apply(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = fixtures.runtime(
                Path(directory), '{"operation":"append","text":"NEW"}'
            )
            env.store.change("project", "set", text="OLD")
            first = env.command(select("NEW"))
            second = env.command(select("NEW"))
            self.assertNotEqual(first["preview_sha256"], second["preview_sha256"])
            with self.assertRaisesRegex(ValueError, "does not match"):
                env.command("/memory apply-proposal " + str(first["preview_sha256"]))
            env.command("/memory review-proposal project 0")
            with self.assertRaises(ValueError):
                env.command("/memory apply-proposal " + str(second["preview_sha256"]))
            for command in (
                "/memory forget project OLD",
                '/memory replace project {"old":"OLD","new":"NEW"}',
            ):
                env.command(command)
                with self.assertRaises(ValueError):
                    env.command("/memory review-text project 0 invalid")
                self.assertIsNone(env.forget.pending)
                self.assertIsNone(env.replace.pending)
            env.command(select("NEW"))
            env.command("/memory show project")
            self.assertIsNotNone(env.proposals.pending)
            env.command("/memory discard-proposal")
            self.assertIsNone(env.proposals.pending)

    def test_concurrent_creation_cannot_be_overwritten_by_selection(self) -> None:
        with TemporaryDirectory() as directory:
            env = fixtures.runtime(Path(directory), "Preference")
            receipt = env.command(select("Preference", "user"))
            env.store.change("user", "set", text="Concurrent")
            with self.assertRaisesRegex(ValueError, "fresh review"):
                env.command("/memory apply-proposal " + str(receipt["preview_sha256"]))
            saved = env.store.read("user")
            assert saved is not None
            self.assertEqual(saved.document.text, "Concurrent")

    def test_json_escape_selection_preserves_literal_command_text(self) -> None:
        text = '/memory clear user\n$(command)\n"quoted"'
        selected, offset = selected_text(
            "Before\n" + text + "\nAfter", json.dumps(text)
        )
        self.assertEqual(selected, text)
        self.assertEqual(offset, len("Before\n"))


class SelectionTerminalTests(IsolatedAsyncioTestCase):
    async def test_pasted_or_composed_selection_cannot_create_review(self) -> None:
        with TemporaryDirectory() as directory:
            env = fixtures.runtime(Path(directory), "Preference")
            command = select("Preference")
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(ConversationSubmission(command, True, accepted))
            queue.put_nowait("/compose")
            queue.put_nowait(command)
            queue.put_nowait("/send")
            queue.put_nowait(None)
            await terminal(
                env.controller,
                queue,
                lambda event: None,
                memory_command=env.command,
                initial_prompt=command,
            )
            self.assertTrue(accepted.result())
            self.assertIsNone(env.proposals.pending)
            self.assertFalse(env.store.root.exists())

    async def test_active_work_rejects_selection_and_keeps_old_review(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            env = fixtures.runtime(Path(directory), "Preference")
            receipt = env.command(select("Preference"))
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
                queue.put_nowait(select("Preference", "user"))
                queue.put_nowait("/quit")
                await asyncio.wait_for(worker, 2)
            self.assertIn("Stop active work", str(events))
            assert env.proposals.pending is not None
            self.assertEqual(env.proposals.pending.sha256, receipt["preview_sha256"])
            self.assertFalse(env.store.root.exists())

    async def test_fullscreen_selection_shows_entire_source_and_result_safely(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            text = "Preference\x1b[31m"
            env = fixtures.runtime(Path(directory), "x" * 1000 + text + "y" * 1000)
            ui = ConversationTUI(env.controller, input=input, output=DummyOutput())
            receipt = env.command(select(text))
            ui.emit(receipt)
            self.assertIn("x" * 1000, ui.transcript.text)
            self.assertIn("y" * 1000, ui.transcript.text)
            self.assertNotIn("\x1b", ui.transcript.text)
            self.assertIn("Selected text to append", ui.transcript.text)
            ui.emit(env.command("/memory discard-proposal"))
            self.assertNotIn(str(receipt["preview_sha256"]), ui.transcript.text)
