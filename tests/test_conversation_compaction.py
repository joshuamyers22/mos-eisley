"""Visible author compaction remains reconstructable across storage boundaries."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from test_conversation_context import CapturingClient

from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationState,
)
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_compaction import (
    AuthorCompactionDraft,
    CompactionBudgetError,
    CompactionMaterialDraft,
)
from mos_eisley.conversation_context import ContextBudgetError
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_state import validate_runtime_state
from mos_eisley.core.agent import AgentUsage
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore

USAGE = AgentUsage(
    requests=1,
    tools=0,
    billed_input=100,
    billed_output=100,
    largest_request=100,
)


def recording(count: int = 1) -> AgentCassette:
    cassette = demo_cassette()
    return AgentCassette(exchanges=cassette.exchanges * max(1, (count + 1) // 2))


def completed_state(root: Path, count: int = 1) -> ConversationState:
    cassette = recording(count)
    fresh = ConversationController.fresh(root, cassette)
    return ConversationState.model_validate(
        {
            **fresh.model_dump(mode="python"),
            "revision": 1,
            "exchanges_consumed": count,
            "entries": tuple(
                ConversationEntry(
                    text=f"exact user instruction {position}",
                    status="completed",
                    answer=f"answer {position}: " + "x" * 6000,
                    usage=USAGE,
                )
                for position in range(count)
            ),
        }
    )


def draft(
    through: int, summary: str = "The prior exchange established the task."
) -> AuthorCompactionDraft:
    return AuthorCompactionDraft(
        compacted_through=through,
        summary=summary,
        compactor="fixture-author",
        model="fixture-v1",
        policy="author-compaction-v1",
    )


class AuthorCompactionTests(TestCase):
    def test_visible_compaction_replaces_raw_answer_and_records_admission(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            controller = ConversationController(
                completed_state(root), cassette, lambda _: None
            )
            proposed = draft(0).model_copy(
                update={
                    "material": (
                        CompactionMaterialDraft(
                            kind="objective",
                            statement="Continue the exact user objective.",
                            source_position=0,
                            source_role="user",
                            source_excerpt="exact user instruction 0",
                            state="active",
                        ),
                        CompactionMaterialDraft(
                            kind="unresolved_question",
                            statement="The answer still needs verification.",
                            source_position=0,
                            source_role="assistant",
                            source_excerpt="answer 0:",
                            state="unresolved",
                        ),
                    )
                }
            )
            compacted = controller.compact_author(proposed)
            boundary = controller.state.context_pressure_boundary
            assert boundary is not None
            self.assertEqual(boundary.kind, "compaction")
            self.assertEqual(boundary.compaction_count, 1)
            self.assertLess(compacted.after_bytes, compacted.before_bytes)
            self.assertFalse(compacted.grants_authority)
            self.assertTrue(
                all(not item.grants_authority for item in compacted.view.material)
            )
            self.assertEqual(
                compacted.view.retained_user_instructions[0].text,
                "exact user instruction 0",
            )
            controller.submit("continue from the compacted work")
            preview = preview_context(controller.state)
            self.assertEqual(preview.schema_version, 4)
            self.assertEqual(preview.selection.compacted_positions, (0,))
            self.assertIn("originals retained", preview.describe())
            client = CapturingClient()
            asyncio.run(controller.step(client))
            request = client.requests[0]
            self.assertIn("exact user instruction 0", request.system)
            self.assertIn("The prior exchange established the task.", request.system)
            self.assertIn("UNTRUSTED DERIVATIVE", request.system)
            self.assertNotIn("x" * 100, request.system)
            self.assertEqual(len(request.turns), 1)
            admission = controller.state.entries[1].request_admission
            assert admission is not None
            assert admission.author_compaction is not None
            self.assertEqual(admission.schema_version, 5)
            self.assertEqual(
                admission.author_compaction.compaction_id, compacted.compaction_id
            )
            self.assertEqual(admission.selection.compacted_positions, (0,))
            self.assertEqual(admission.selection.omitted, ())

    def test_reconstruction_rejects_mutated_or_missing_originals(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            controller = ConversationController(
                completed_state(root), demo_cassette(), lambda _: None
            )
            controller.compact_author(draft(0))
            entry = controller.state.entries[0]
            mutated = controller.state.model_copy(
                update={
                    "entries": (
                        entry.model_copy(
                            update={"answer": "different retained answer"}
                        ),
                    )
                }
            )
            with self.assertRaisesRegex(ValueError, "reconstructed"):
                validate_runtime_state(mutated)
            missing = controller.state.model_copy(update={"entries": ()})
            with self.assertRaisesRegex(ValueError, "lineage"):
                validate_runtime_state(missing)

    def test_cancelled_instruction_is_retained_but_not_reactivated(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = completed_state(root)
            state = validate_runtime_state(
                state.model_copy(
                    update={
                        "revision": 2,
                        "entries": state.entries
                        + (ConversationEntry(text="cancel this", status="cancelled"),),
                    }
                )
            )
            controller = ConversationController(state, demo_cassette(), lambda _: None)
            compacted = controller.compact_author(draft(1))
            instructions = compacted.view.retained_user_instructions
            self.assertEqual(compacted.view.active_user_instruction_position, 0)
            self.assertEqual(
                tuple(item.supersession_state for item in instructions),
                ("current", "cancelled"),
            )

    def test_three_revision_cap_and_advancing_lineage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            controller = ConversationController(
                completed_state(root, 4), recording(4), lambda _: None
            )
            first = controller.compact_author(draft(0))
            second = controller.compact_author(draft(1))
            third = controller.compact_author(draft(2))
            self.assertEqual(second.prior_compaction_sha256, first.compaction_id)
            self.assertEqual(third.prior_compaction_sha256, second.compaction_id)
            with self.assertRaisesRegex(ValueError, "capped at three"):
                controller.compact_author(draft(3))
            self.assertEqual(
                controller.state.author_compactions, (first, second, third)
            )

    def test_failed_compaction_or_save_leaves_precompaction_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            controller = ConversationController(
                completed_state(root), demo_cassette(), lambda _: None
            )
            before = controller.state
            with self.assertRaisesRegex(ValueError, "reduce"):
                controller.compact_author(draft(0, summary="y" * 7000))
            self.assertIs(controller.state, before)
            with (
                patch.object(controller, "save", side_effect=OSError("disk full")),
                self.assertRaisesRegex(OSError, "disk full"),
            ):
                controller.compact_author(draft(0))
            self.assertIs(controller.state, before)

    def test_oversized_derivative_is_rejected_before_commit(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = completed_state(root, 5)
            state = validate_runtime_state(
                state.model_copy(
                    update={
                        "entries": tuple(
                            entry.model_copy(update={"text": "u" * 7000})
                            for entry in state.entries
                        )
                    }
                )
            )
            controller = ConversationController(state, recording(5), lambda _: None)
            before = controller.state
            with self.assertRaises(CompactionBudgetError) as caught:
                controller.compact_author(draft(4))
            self.assertGreater(caught.exception.required_bytes, 32_000)
            self.assertIs(controller.state, before)

    def test_compaction_round_trips_through_both_private_stores(self) -> None:
        for backend in (ConversationStore, SQLiteConversationStore):
            with (
                self.subTest(backend=backend.__name__),
                TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                cassette = demo_cassette()
                state = completed_state(root)
                with backend(root / "sessions", state.session_id, root) as store:
                    initial = validate_runtime_state(
                        state.model_copy(
                            update={
                                "revision": 0,
                                "exchanges_consumed": 0,
                                "entries": (),
                            }
                        )
                    )
                    store.save(initial)
                    store.save(state)
                    controller = ConversationController(state, cassette, store.save)
                    compacted = controller.compact_author(draft(0))
                    restored = store.load()
                    self.assertEqual(restored.author_compactions[-1], compacted)
                    validate_runtime_state(restored)

    def test_post_compaction_overflow_stops_before_attempt_consumption(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            controller = ConversationController(
                completed_state(root), demo_cassette(), lambda _: None
            )
            controller.compact_author(draft(0))
            controller.resize_context(4000)
            controller.submit("z" * 3000)
            before = controller.state
            client = CapturingClient()
            with self.assertRaises(ContextBudgetError):
                asyncio.run(controller.step(client))
            self.assertIs(controller.state, before)
            self.assertEqual(controller.state.exchanges_consumed, 1)
            self.assertEqual(client.requests, [])
            self.assertIsNone(controller.state.entries[1].request_admission)
