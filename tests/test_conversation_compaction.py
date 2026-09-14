"""Validated author compaction is reconstructable, bounded and fail closed."""

import asyncio
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_compaction import (
    AuthorCompactionDraft,
    AuthorCompactionOmission,
    AuthorCompactionSummary,
    AuthorCompactionSummaryItem,
)
from mos_eisley.conversation_context import ContextBudgetError, project_context
from mos_eisley.conversation_context_pressure import context_pressure_report
from mos_eisley.conversation_state import ConversationEntry, ConversationState
from mos_eisley.core.agent import AgentUsage
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.task_state import WorkspaceState
from mos_eisley.task_state_continuation import WorkspaceInspection


@dataclass
class FixedInspector:
    inspections: list[WorkspaceInspection]
    calls: int = 0

    def inspect(
        self, workspace: Path, relevant_files: Sequence[str]
    ) -> WorkspaceInspection:
        inspection = self.inspections[min(self.calls, len(self.inspections) - 1)]
        self.calls += 1
        return inspection


class CompletingClient:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        response = demo_cassette().exchanges[1].response
        assert response is not None
        return response


def inspection(seed: bytes = b"same") -> WorkspaceInspection:
    sha = digest(seed)
    return WorkspaceInspection(
        workspace=WorkspaceState(
            repository_sha256=sha,
            branch="main",
            revision=sha,
            tree_sha256=sha,
            dirty_state_sha256=sha,
        )
    )


def usage() -> AgentUsage:
    return AgentUsage(
        requests=1,
        tools=0,
        billed_input=1,
        billed_output=1,
        largest_request=1,
    )


def draft(
    state: ConversationState, *, summary_text: str = "Keep the contract."
) -> AuthorCompactionDraft:
    return AuthorCompactionDraft(
        expected_source_revision=state.revision,
        expected_message_count=len(state.entries),
        retained_user_positions=(0,),
        summary=AuthorCompactionSummary(
            items=(
                AuthorCompactionSummaryItem(
                    category="objective",
                    text=summary_text,
                    source_role="user",
                    source_positions=(0,),
                ),
                AuthorCompactionSummaryItem(
                    category="current_work",
                    text=summary_text,
                    source_role="assistant",
                    source_positions=(0,),
                ),
            )
        ),
        omissions=(),
        compactor="fixture-compactor",
        model="fixture-model",
    )


def compactable_state(
    *, context_max_bytes: int | None = None, workspace: Path | None = None
) -> ConversationState:
    cassette = demo_cassette()
    fresh = ConversationController.fresh(
        workspace or Path.cwd(), cassette, context_max_bytes=context_max_bytes
    )
    return ConversationState.model_validate(
        fresh.model_copy(
            update={
                "revision": 2,
                "exchanges_consumed": 1,
                "entries": (
                    ConversationEntry(
                        text="preserve exactly: " + "x" * 1200,
                        status="completed",
                        answer="old detail " + "y" * 7000,
                        usage=usage(),
                    ),
                    ConversationEntry(text="continue now"),
                ),
            }
        ).model_dump()
    )


class AuthorCompactionTests(TestCase):
    def controller(
        self,
        state: ConversationState,
        inspector: FixedInspector,
        save: Mock | None = None,
    ) -> ConversationController:
        save = save or Mock()
        save.return_value = None
        return ConversationController(
            state,
            demo_cassette(),
            save,
            compaction_workspace_inspector=inspector,
        )

    def test_compaction_reconstructs_source_and_projects_untrusted_derivative(
        self,
    ) -> None:
        state = compactable_state()
        before = project_context(state.entries, 1)
        save = Mock()
        controller = self.controller(state, FixedInspector([inspection()]), save)
        compaction = controller.compact_author_context(draft(state))

        self.assertEqual(compaction.source.turns, before.turns[:-1])
        retained = compaction.retained_user_turn.blocks[0]
        derivative = compaction.derivative_turn.blocks[0]
        self.assertIsInstance(retained, TextBlock)
        self.assertIsInstance(derivative, TextBlock)
        assert isinstance(retained, TextBlock)
        assert isinstance(derivative, TextBlock)
        self.assertEqual(retained.text, state.entries[0].text)
        self.assertIn("UNTRUSTED AUTHOR COMPACTION", derivative.text)
        self.assertFalse(compaction.manifest.grants_authority)
        self.assertFalse(compaction.manifest.critic_eligible)
        self.assertLess(
            compaction.manifest.after_bytes, compaction.manifest.before_bytes
        )
        projected = project_context(controller.state.entries, 1, compaction)
        self.assertEqual(projected.selection.policy_version, 2)
        self.assertEqual(projected.selection.compaction_sha256, compaction.sha256)
        current = projected.turns[-1].blocks[0]
        self.assertIsInstance(current, TextBlock)
        assert isinstance(current, TextBlock)
        self.assertEqual(current.text, "continue now")
        self.assertEqual(controller.state.exchanges_consumed, 1)
        self.assertEqual(controller.state.entries[1].status, "queued")
        save.assert_called_once()

    def test_stale_incomplete_and_newest_instruction_drafts_fail_without_save(
        self,
    ) -> None:
        state = compactable_state()
        for invalid in (
            draft(state).model_copy(update={"expected_source_revision": 1}),
            draft(state).model_copy(update={"retained_user_positions": (1,)}),
            draft(state).model_copy(
                update={
                    "retained_user_positions": (),
                    "omissions": (
                        AuthorCompactionOmission(
                            start_position=0,
                            end_position=0,
                            category="other",
                            reason="drop all",
                        ),
                    ),
                }
            ),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                save = Mock()
                self.controller(
                    state, FixedInspector([inspection()]), save
                ).compact_author_context(invalid)
                save.assert_not_called()

    def test_workspace_change_and_context_overflow_restore_prior_state(self) -> None:
        state = compactable_state()
        save = Mock()
        controller = self.controller(
            state, FixedInspector([inspection(), inspection(b"changed")]), save
        )
        with self.assertRaisesRegex(ValueError, "workspace changed"):
            controller.compact_author_context(draft(state))
        self.assertEqual(controller.state, state)
        save.assert_not_called()

        limited = compactable_state(context_max_bytes=4000)
        controller = self.controller(limited, FixedInspector([inspection()]), save)
        with self.assertRaises(ContextBudgetError):
            controller.compact_author_context(
                draft(limited, summary_text="summary " + "z" * 3000)
            )
        self.assertEqual(controller.state, limited)
        save.assert_not_called()

    def test_tamper_and_freshness_fail_closed_and_pressure_counts_compaction(
        self,
    ) -> None:
        state = compactable_state()
        controller = self.controller(state, FixedInspector([inspection()]))
        compaction = controller.compact_author_context(draft(state))
        self.assertEqual(context_pressure_report(controller.state).compactions, 1)

        tampered = compaction.model_copy(
            update={
                "manifest": compaction.manifest.model_copy(
                    update={"source_sha256": "0" * 64}
                )
            }
        )
        with self.assertRaises(ValueError):
            ConversationState.model_validate(
                controller.state.model_copy(
                    update={"author_compactions": (tampered,)}
                ).model_dump()
            )

        stale = self.controller(
            controller.state, FixedInspector([inspection(b"changed")])
        )
        with self.assertRaisesRegex(ValueError, "compaction is stale"):
            stale.validate_author_compaction_freshness()
        self.assertGreater(len(canonical_bytes(compaction.source)), 0)

    def test_sqlite_round_trip_keeps_exact_source_in_private_header_artifact(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = compactable_state(workspace=root)
            state = ConversationState.model_validate(
                state.model_copy(update={"revision": 0}).model_dump()
            )
            with SQLiteConversationStore(root, state.session_id, root) as store:
                store.save(state)
                controller = ConversationController(
                    state,
                    demo_cassette(),
                    store.save,
                    compaction_workspace_inspector=FixedInspector([inspection()]),
                )
                compaction = controller.compact_author_context(draft(state))
                self.assertEqual(store.load(), controller.state)
            with sqlite3.connect(root / DATABASE) as database:
                header = database.execute("SELECT header FROM sessions").fetchone()[0]
                artifacts = tuple(
                    row[0] for row in database.execute("SELECT payload FROM artifacts")
                )
            canary = compaction.source.messages[0].answer.encode()
            self.assertNotIn(canary, header)
            self.assertTrue(any(canary in payload for payload in artifacts))


class TerminalCompactionTests(IsolatedAsyncioTestCase):
    async def test_dispatch_admission_binds_versioned_compaction_selection(
        self,
    ) -> None:
        state = compactable_state()
        inspector = FixedInspector([inspection()])
        controller = ConversationController(
            state,
            demo_cassette(),
            lambda updated: None,
            compaction_workspace_inspector=inspector,
        )
        compaction = controller.compact_author_context(draft(state))
        client = CompletingClient()

        self.assertTrue(await controller.step(client))

        admission = controller.state.entries[-1].request_admission
        assert admission is not None
        self.assertEqual(admission.selection.policy_version, 2)
        self.assertEqual(admission.selection.compaction_sha256, compaction.sha256)
        self.assertEqual(controller.state.entries[-1].status, "completed")
        self.assertEqual(len(client.requests), 1)

    async def test_explicit_command_emits_content_free_receipt_and_pauses(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = compactable_state(workspace=root)
            controller = ConversationController(
                state,
                demo_cassette(),
                lambda updated: None,
                compaction_workspace_inspector=FixedInspector([inspection()]),
            )
            proposal = root / "compact.json"
            proposal.write_bytes(canonical_bytes(draft(state)))
            queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
            queue.put_nowait(f"/compact {proposal}")
            queue.put_nowait(None)
            events: list[dict[str, object]] = []

            await terminal(controller, queue, events.append)

            receipt = next(
                event for event in events if event["type"] == "conversation.compacted"
            )
            encoded = str(receipt)
            self.assertNotIn("old detail", encoded)
            self.assertNotIn("preserve exactly", encoded)
            self.assertEqual(receipt["count"], 1)
            self.assertEqual(controller.state.entries[-1].status, "queued")
            self.assertEqual(controller.state.exchanges_consumed, 1)
