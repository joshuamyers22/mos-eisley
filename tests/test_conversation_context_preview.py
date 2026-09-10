"""Read-only context provenance matches dispatch without expanding artifacts."""

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
from test_conversation_context import CapturingClient, TextMessage
from test_conversation_tui import until

from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationState,
    conversation_config,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_context import RequestContext, project_context
from mos_eisley.conversation_context_preview import (
    ContextPreview,
    ContextPreviewUnavailable,
    preview_context,
)
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    WorkingConversationState,
)
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.agent import AgentUsage, RequestBudgetError
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


def controller() -> ConversationController:
    cassette = demo_cassette()
    return ConversationController(
        ConversationController.fresh(Path.cwd(), cassette), cassette, lambda _: None
    )


class ContextPreviewTests(TestCase):
    def test_projection_reports_complete_steering_sources_and_omissions(self) -> None:
        projection = project_context(
            (
                TextMessage("private original", "interrupted"),
                TextMessage("private refinement", "cancelled", steering_for=0),
                TextMessage("private finish", "completed", "private answer", 1),
                TextMessage("private unrelated", "failed"),
                TextMessage("private question"),
                TextMessage("private future"),
            ),
            4,
        )
        self.assertEqual(projection.selection.policy_version, 1)
        self.assertEqual(
            [
                (source.role, source.positions)
                for source in projection.selection.turn_sources
            ],
            [("user", (0, 1, 2)), ("assistant", (2,)), ("user", (4,))],
        )
        self.assertEqual(
            [(item.position, item.reason) for item in projection.selection.omitted],
            [(3, "no_completed_answer_or_required_link"), (5, "after_target")],
        )
        self.assertNotIn("private", projection.selection.model_dump_json())
        self.assertEqual(
            projection.turns[0].blocks,
            tuple(
                TextBlock(text=text)
                for text in ("private original", "private refinement", "private finish")
            ),
        )

    def test_preview_measures_exact_escaped_utf8_and_reports_over_budget(self) -> None:
        chat = controller()
        chat.resize_context(4000)
        chat.submit('é"\\' * 1800)
        before = chat.state
        preview = preview_context(before)
        config = conversation_config(project_context(before.entries, 0).turns)
        encoded = canonical_bytes(
            RequestContext(system=config.system, turns=config.initial_turns)
        )
        self.assertEqual(preview.context_bytes, len(encoded))
        self.assertEqual(preview.context_sha256, digest(encoded))
        self.assertFalse(preview.within_context_budget)
        self.assertTrue(preview.request.within_budget)
        self.assertIn("over saved context budget", preview.describe())
        self.assertEqual(preview.revision, before.revision)
        self.assertIs(chat.state, before)
        self.assertEqual(chat.state.exchanges_consumed, 0)

    def test_request_envelope_reserves_affect_request_hash_and_usable_budget(
        self,
    ) -> None:
        chat = controller()
        chat.submit("question")
        before = preview_context(chat.state)
        config = conversation_config(project_context(chat.state.entries, 0).turns)
        changed = config.model_copy(
            update={
                "budget": config.budget.model_copy(update={"reserve_high_bytes": 16000})
            }
        )
        with patch(
            "mos_eisley.conversation_context_preview.conversation_config",
            return_value=changed,
        ):
            after = preview_context(chat.state)
        self.assertEqual(before.context_sha256, after.context_sha256)
        self.assertNotEqual(before.request.sha256, after.request.sha256)
        self.assertEqual(
            (
                before.request.output_reserve_bytes,
                before.request.headroom_bytes,
                before.request.max_bytes,
            ),
            (12000, 4200, 79800),
        )
        self.assertEqual(
            (
                after.request.output_reserve_bytes,
                after.request.headroom_bytes,
                after.request.max_bytes,
            ),
            (16000, 4000, 76000),
        )

    def test_preview_schema_two_roundtrip_and_old_version_rejection(self) -> None:
        chat = controller()
        chat.submit("question")
        preview = preview_context(chat.state)
        self.assertEqual(preview.schema_version, 2)
        self.assertEqual(preview.selection.policy_version, 1)
        self.assertEqual(
            ContextPreview.model_validate_json(preview.model_dump_json()), preview
        )
        old = preview.model_dump(mode="json")
        old["schema_version"] = 1
        old.pop("request")
        with self.assertRaises(ValueError):
            ContextPreview.model_validate_json(json.dumps(old))

    def test_saved_memory_is_measured_without_disclosing_its_text(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory_store = MemoryStore(root / "memory", root)
            memory_store.change("user", "set", text="PRIVATE MEMORY é")
            memory = memory_store.load()
            cassette = demo_cassette(memory=memory)
            chat = ConversationController(
                ConversationController.fresh(root, cassette, memory),
                cassette,
                lambda _: None,
            )
            chat.submit("PRIVATE QUESTION")
            preview = preview_context(chat.state)
            config = conversation_config(
                project_context(chat.state.entries, 0).turns, memory
            )
            self.assertEqual(
                preview.context_sha256,
                digest(
                    canonical_bytes(
                        RequestContext(system=config.system, turns=config.initial_turns)
                    )
                ),
            )
            self.assertTrue(preview.memory_selected)
            self.assertNotIn("PRIVATE", preview.model_dump_json() + preview.describe())

    def test_no_chat_target_never_skips_over_an_isolated_review(self) -> None:
        chat = controller()
        with self.assertRaisesRegex(ContextPreviewUnavailable, "No queued"):
            preview_context(chat.state)
        brief, cassette = demo_inputs()
        chat.submit_review(ConversationReviewPacket(brief=brief, cassette=cassette))
        chat.submit("later chat")
        before = chat.state
        with self.assertRaisesRegex(
            ContextPreviewUnavailable, "isolated review packet"
        ):
            preview_context(chat.state)
        self.assertIs(chat.state, before)

    def test_active_work_is_explicitly_provisional_and_keeps_steering(self) -> None:
        chat = controller()
        chat.submit("original")
        running = chat.state.model_copy(
            update={
                "entries": (
                    chat.state.entries[0].model_copy(update={"status": "running"}),
                ),
                "exchanges_consumed": 1,
            }
        )
        chat.state = running
        chat.steer("refinement")
        preview = preview_context(chat.state)
        self.assertTrue(preview.active_work)
        self.assertEqual(preview.selection.turn_sources[0].positions, (0, 1))
        self.assertIn("may change", preview.describe())
        self.assertEqual(chat.state.exchanges_consumed, 1)

    def test_archived_review_in_future_needs_no_artifact_hydration(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with SQLiteConversationStore(
                root / "sessions", state.session_id, root
            ) as store:
                store.save(state)
                chat = ConversationController(state, cassette, store.save)
                chat.submit("PRIVATE queued chat")
                brief, recording = demo_inputs()
                chat.submit_review(
                    ConversationReviewPacket(brief=brief, cassette=recording)
                )
                working = store.load_working()
                assert isinstance(working, WorkingConversationState)
                self.assertIsInstance(working.entries[1], ArchivedConversationEntry)
                before = store.snapshot_sha256
                with patch.object(
                    store, "load_working_entry", side_effect=AssertionError("hydrated")
                ):
                    preview = preview_context(working)
                self.assertEqual(preview.selection.message_index, 0)
                self.assertEqual(preview.selection.omitted[0].position, 1)
                self.assertNotIn("PRIVATE", preview.model_dump_json())
                self.assertEqual(store.snapshot_sha256, before)
                self.assertEqual(working.exchanges_consumed, 0)


class ContextPreviewTerminalTests(IsolatedAsyncioTestCase):
    async def test_request_preview_agrees_with_exact_dispatch_limit(self) -> None:
        cassette = AgentCassette(exchanges=demo_cassette().exchanges * 4)
        initial = ConversationController.fresh(
            Path.cwd(), cassette, context_max_bytes=1_000_000
        )
        usage = AgentUsage(
            requests=1, tools=0, billed_input=1, billed_output=1, largest_request=1
        )
        entries = tuple(
            ConversationEntry(
                text="x" * 7200, answer="y" * 7200, status="completed", usage=usage
            )
            for _ in range(5)
        )
        state = ConversationState.model_validate(
            initial.model_copy(
                update={
                    "entries": entries + (ConversationEntry(text="z"),),
                    "exchanges_consumed": 5,
                }
            ).model_dump()
        )
        baseline = preview_context(state)
        length = baseline.request.max_bytes - baseline.request.bytes + 1
        self.assertTrue(1 <= length < 8000)
        for overflow in (False, True):
            with self.subTest(overflow=overflow):
                selected = ConversationState.model_validate(
                    state.model_copy(
                        update={
                            "entries": entries
                            + (ConversationEntry(text="z" * (length + int(overflow))),),
                        }
                    ).model_dump()
                )
                preview = preview_context(selected)
                self.assertTrue(preview.within_context_budget)
                self.assertEqual(
                    preview.request.bytes, preview.request.max_bytes + int(overflow)
                )
                self.assertEqual(preview.request.within_budget, not overflow)
                self.assertEqual(
                    (
                        preview.request.provider,
                        preview.request.model,
                        preview.request.effort,
                    ),
                    ("fixture", "tool-reviewer-v1", "high"),
                )
                client = CapturingClient()
                saves: list[ConversationState] = []
                chat = ConversationController(selected, cassette, saves.append)
                if overflow:
                    with self.assertRaises(RequestBudgetError) as error:
                        await chat.step(client)
                    self.assertEqual(
                        error.exception.required_bytes, preview.request.bytes
                    )
                    self.assertEqual(
                        error.exception.maximum_bytes, preview.request.max_bytes
                    )
                    self.assertEqual(client.requests, [])
                    self.assertEqual(saves, [])
                    self.assertIs(chat.state, selected)
                else:
                    self.assertTrue(await chat.step(client))
                    self.assertEqual(len(client.requests), 1)
                    self.assertEqual(
                        digest(canonical_bytes(client.requests[0])),
                        preview.request.sha256,
                    )
                    self.assertEqual(chat.state.exchanges_consumed, 6)

    async def test_unavailable_target_is_a_notice_without_dispatch(self) -> None:
        for review in (False, True):
            with self.subTest(review=review):
                chat = controller()
                if review:
                    brief, cassette = demo_inputs()
                    chat.submit_review(
                        ConversationReviewPacket(brief=brief, cassette=cassette)
                    )
                before = chat.state
                queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
                queue.put_nowait("/context")
                queue.put_nowait(None)
                events: list[dict[str, object]] = []
                with patch.object(
                    chat, "step", side_effect=AssertionError("dispatched")
                ):
                    await terminal(chat, queue, events.append)
                notices = [
                    event
                    for event in events
                    if event["type"] == "conversation.unavailable"
                ]
                self.assertEqual(len(notices), 1)
                self.assertIn(
                    "isolated review packet" if review else "No queued",
                    str(notices[0]["text"]),
                )
                self.assertIs(chat.state, before)

    async def test_preview_hash_matches_the_next_dispatched_context(self) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        await chat.step()
        chat.submit(DEMO_PROMPTS[1])
        preview = preview_context(chat.state)
        client = CapturingClient()
        await chat.step(client)
        self.assertEqual(len(client.requests), 1)
        request = client.requests[0]
        self.assertEqual(preview.request.sha256, digest(canonical_bytes(request)))
        self.assertEqual(preview.request.bytes, len(canonical_bytes(request)))
        self.assertGreater(preview.request.bytes, preview.context_bytes)
        context = canonical_bytes(
            RequestContext(system=request.system, turns=request.turns)
        )
        self.assertEqual(
            (preview.context_sha256, preview.context_bytes),
            (digest(context), len(context)),
        )
        self.assertEqual(
            [source.positions for source in preview.selection.turn_sources],
            [(0,), (0,), (1,)],
        )

    async def test_terminal_inspection_does_not_enable_work_or_save(self) -> None:
        chat = controller()
        chat.submit("PRIVATE queued text")
        before = chat.state
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/context")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        with (
            patch.object(chat, "save", side_effect=AssertionError("saved")),
            patch.object(chat, "step", side_effect=AssertionError("dispatched")),
        ):
            await terminal(chat, queue, events.append)
        event = next(
            event for event in events if event["type"] == "conversation.context"
        )
        self.assertEqual(event["revision"], before.revision)
        self.assertNotIn("PRIVATE", json.dumps(event))
        self.assertIs(chat.state, before)

    async def test_tui_preview_toggle_and_revision_invalidation_preserve_draft(
        self,
    ) -> None:
        chat = controller()
        chat.submit("queued question")
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("unsent draft")
                await until(lambda: ui.editor.text == "unsent draft")
                ui.control("/context")
                await until(lambda: "Context preview • message 0" in ui.transcript.text)
                self.assertEqual(ui.editor.text, "unsent draft")
                self.assertEqual(chat.state.exchanges_consumed, 0)
                ui.control("/context")
                await until(lambda: ui.context_preview is None)
                ui.control("/context")
                await until(lambda: ui.context_preview is not None)
                chat.submit("later question")
                ui.refresh()
                self.assertIn("Context preview is stale", ui.transcript.text)
                self.assertNotIn("Context preview • message 0", ui.transcript.text)
                ui.control("/context")
                await until(lambda: "Omitted message 1" in ui.transcript.text)
                self.assertEqual(ui.editor.text, "unsent draft")
                self.assertEqual(chat.state.exchanges_consumed, 0)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)


class ContextPreviewCLITests(TestCase):
    def test_resume_context_is_read_only_for_both_storage_backends(self) -> None:
        for backend, store_type in (
            ("snapshot", ConversationStore),
            ("sqlite", SQLiteConversationStore),
        ):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory)
                cassette = demo_cassette()
                state = ConversationController.fresh(
                    root, cassette, memory_disabled=True
                )
                with store_type(root / "sessions", state.session_id, root) as store:
                    store.save(state)
                    chat = ConversationController(state, cassette, store.save)
                    chat.submit("queued question")
                    before = digest(canonical_bytes(chat.state))
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "resume",
                        state.session_id,
                        "--storage-backend",
                        backend,
                        "--storage",
                        str(root / "sessions"),
                        "-C",
                        str(root),
                        "--json",
                    ],
                    input="/context\n",
                    text=True,
                    capture_output=True,
                    env={**os.environ, "HOME": str(root)},
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                preview = next(
                    event for event in events if event["type"] == "conversation.context"
                )
                self.assertEqual(preview["selection"]["message_index"], 0)
                self.assertEqual(preview["schema_version"], 2)
                self.assertTrue(preview["request"]["within_budget"])
                self.assertEqual(preview["request"]["max_bytes"], 79800)
                with store_type(
                    root / "sessions", state.session_id, root, create=False
                ) as store:
                    saved = store.load()
                    self.assertEqual(digest(canonical_bytes(saved)), before)
                    self.assertEqual(saved.exchanges_consumed, 0)
