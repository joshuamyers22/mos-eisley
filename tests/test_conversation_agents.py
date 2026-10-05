"""Owner-scoped child inspection and sealed review projections without dispatch."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_conversation import WaitingClient

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_agent_commands import agent_command
from mos_eisley.conversation_agents import (
    AgentInspectionScope,
    AgentInspectionSnapshot,
    AgentOperationalRecord,
    AgentReportReference,
    ImplementationAssignment,
    ImplementationReport,
)
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_input import (
    ConversationInput,
    ConversationSubmission,
    submission_command,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.task_state import ResourceCeiling, ResourceLedger


class RetainedChildren:
    def __init__(self, scope: AgentInspectionScope):
        self.scope = scope
        assignment = ImplementationAssignment(
            task_id="task-1",
            parent_task_id="parent-task",
            objective="Implement parser",
            provider="fixture",
            model="tool-reviewer-v1",
            effort="high",
            workspace="/workspace",
            worktree="/worktree",
            plan_sha256="a" * 64,
            tests_sha256="b" * 64,
            allowance=ResourceCeiling(
                input_bytes=100,
                output_bytes=100,
                cost_microusd=20,
                attempts=2,
                correction_cycles=1,
                review_rounds=1,
            ),
        )
        self.output = ImplementationReport(
            scope=scope,
            child_id="child-1",
            report_id="report-1",
            assignment_sha256=assignment.sha256,
            summary="Parser patch retained",
            evidence=("Parser tests passed; retained evidence",),
            unresolved=("Creator integration pending",),
            complete=True,
        )
        self.reference = AgentReportReference(
            report_id="report-1",
            assignment_sha256=assignment.sha256,
            sha256=digest(canonical_bytes(self.output)),
            availability="available",
        )
        child = AgentOperationalRecord(
            scope=scope,
            child_id="child-1",
            role="implementation",
            state="completed",
            assignment=assignment,
            assignment_current=True,
            usage=ResourceLedger(
                input_bytes=50, output_bytes=20, cost_microusd=10, attempts=1
            ),
            verification="passed",
            unresolved=("Creator integration pending",),
            report=self.reference,
        )
        review = AgentOperationalRecord(
            scope=scope,
            child_id="review-1",
            role="review",
            state="running",
        )
        self.view = AgentInspectionSnapshot(
            scope=scope, revision=1, children=(child, review)
        )
        self.reads = 0
        self.race = False

    def snapshot(self, scope: AgentInspectionScope) -> AgentInspectionSnapshot:
        assert scope == self.scope
        return self.view

    def report(
        self,
        scope: AgentInspectionScope,
        child_id: str,
        reference: AgentReportReference,
        *,
        expected_revision: int,
    ) -> ImplementationReport:
        assert scope == self.scope and child_id == "child-1"
        assert reference == self.reference and expected_revision == self.view.revision
        self.reads += 1
        if self.race:
            self.view = self.view.model_copy(
                update={"revision": self.view.revision + 1}
            )
        return self.output


class AgentInspectionTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.root = TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        cassette = demo_cassette()
        self.saved: list[object] = []
        self.chat = ConversationController(
            ConversationController.fresh(Path(self.root.name), cassette),
            cassette,
            self.saved.append,
        )
        self.scope = AgentInspectionScope(
            owner_uid=self.chat.state.owner_uid,
            parent_session_id=self.chat.state.session_id,
            workspace_sha256=digest(self.chat.state.workspace.encode()),
        )
        self.source = RetainedChildren(self.scope)
        self.chat.child_inspection = self.source

    def test_authorized_report_and_json_alias_leave_state_and_spend_unchanged(
        self,
    ) -> None:
        before = canonical_bytes(self.chat.state)
        source_before = canonical_bytes(self.source.view)
        events: list[dict[str, object]] = []
        for command in ("/agent child-1", "/subagents child-1 --json"):
            self.assertEqual(
                agent_command(self.chat, command, events.append), "accepted"
            )
        self.assertIn("Parser patch retained", str(events[0]["text"]))
        self.assertEqual(events[0]["inspection"], events[1]["inspection"])
        self.assertIn("microUSD", str(events[0]["text"]))
        self.assertEqual(canonical_bytes(self.chat.state), before)
        self.assertEqual(canonical_bytes(self.source.view), source_before)
        self.assertEqual(self.saved, [])

    def test_review_report_never_reads_evidence(self) -> None:
        view = self.chat.inspect_agents("review-1")
        self.assertEqual(view.report_status, "sealed")
        self.assertIsNone(view.report)
        self.assertEqual(self.source.reads, 0)
        with self.assertRaises(ValueError):
            AgentOperationalRecord.model_validate_json(
                canonical_bytes(
                    self.source.view.children[1].model_copy(
                        update={"unresolved": ("sealed finding",)}
                    )
                )
            )

    def test_cross_owner_parent_workspace_and_duplicate_rows_fail_closed(self) -> None:
        for update in (
            {"owner_uid": self.scope.owner_uid + 1},
            {"parent_session_id": "f" * 32},
            {"workspace_sha256": "f" * 64},
        ):
            foreign = self.scope.model_copy(update=update)
            self.source.view = AgentInspectionSnapshot(scope=foreign, revision=1)
            with self.assertRaises(ValueError):
                self.chat.inspect_agents()
        self.source.view = RetainedChildren(self.scope).view
        child = self.source.view.children[0]
        for children in (
            (child, child),
            (child.model_copy(update={"scope": foreign}),),
        ):
            self.source.view = self.source.view.model_copy(
                update={"children": children}
            )
            with self.assertRaises(ValueError):
                self.chat.inspect_agents()
        self.assertEqual(self.source.reads, 0)

    def test_stale_assignment_and_mismatched_report_binding_do_not_open_report(
        self,
    ) -> None:
        original = self.source.view
        child = original.children[0]
        for stale in (
            child.model_copy(update={"assignment_current": False}),
            child.model_copy(
                update={
                    "report": self.source.reference.model_copy(
                        update={"assignment_sha256": "c" * 64}
                    )
                }
            ),
        ):
            self.source.view = original.model_copy(update={"children": (stale,)})
            self.assertEqual(self.chat.inspect_agents("child-1").report_status, "stale")
        self.assertEqual(self.source.reads, 0)

    def test_failed_cancelled_missing_and_partial_reports(self) -> None:
        original = self.source.view.children[0]
        for state in ("failed", "cancelled", "completed"):
            child = original.model_copy(update={"state": state})
            self.source.view = self.source.view.model_copy(
                update={"children": (child,)}
            )
            self.assertEqual(
                self.chat.inspect_agents("child-1").report_status, "available"
            )
        for reference in (
            None,
            self.source.reference.model_copy(update={"availability": "missing"}),
        ):
            self.source.view = self.source.view.model_copy(
                update={
                    "children": (original.model_copy(update={"report": reference}),)
                }
            )
            self.assertEqual(
                self.chat.inspect_agents("child-1").report_status, "missing"
            )
        self.source.output = self.source.output.model_copy(update={"complete": False})
        self.source.reference = self.source.reference.model_copy(
            update={
                "sha256": digest(canonical_bytes(self.source.output)),
                "availability": "partial",
            }
        )
        self.source.view = self.source.view.model_copy(
            update={
                "children": (
                    original.model_copy(update={"report": self.source.reference}),
                )
            }
        )
        self.assertEqual(self.chat.inspect_agents("child-1").report_status, "partial")

    def test_report_tampering_or_concurrent_resume_fails_before_display(self) -> None:
        original = self.source.output
        for update in (
            {
                "scope": self.scope.model_copy(
                    update={"owner_uid": self.scope.owner_uid + 1}
                )
            },
            {"child_id": "other"},
            {"summary": "tampered"},
            {"assignment_sha256": "d" * 64},
        ):
            self.source.output = original.model_copy(update=update)
            events: list[dict[str, object]] = []
            self.assertEqual(
                agent_command(self.chat, "/agent child-1", events.append), "rejected"
            )
            self.assertNotIn("tampered", str(events))
        self.source.output = original
        self.source.race = True
        with self.assertRaisesRegex(ValueError, "changed"):
            self.chat.inspect_agents("child-1")
        self.assertEqual(self.saved, [])

    def test_unknown_child_mutation_commands_and_unconnected_source_reject(
        self,
    ) -> None:
        events: list[dict[str, object]] = []
        for command in (
            "/agent unknown",
            "/agent child-1 cancel",
            "/subagents child-1 resume",
            "/agent --json --json",
            "/agent\nchild-1",
        ):
            self.assertEqual(
                agent_command(self.chat, command, events.append), "rejected"
            )
        self.chat.child_inspection = None
        self.assertEqual(agent_command(self.chat, "/agent", events.append), "rejected")
        self.assertIn("qualified child controller", str(events[-1]["text"]))
        self.assertEqual(self.saved, [])

    async def test_terminal_typed_and_plain_commands_never_admit_author_turn(
        self,
    ) -> None:
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        ack = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/agent child-1", False, ack))
        queue.put_nowait("/subagents --json")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        before = canonical_bytes(self.chat.state)
        await terminal(self.chat, queue, events.append)
        self.assertTrue(ack.result())
        self.assertEqual(sum(e["type"] == "conversation.agents" for e in events), 2)
        self.assertEqual(canonical_bytes(self.chat.state), before)

    async def test_inspection_during_active_author_preserves_admission_and_usage(
        self,
    ) -> None:
        self.chat.submit("Main work")
        client = WaitingClient()
        task = asyncio.create_task(self.chat.step(client))
        await client.started.wait()
        before = canonical_bytes(self.chat.state)
        try:
            self.chat.inspect_agents("child-1")
            self.assertEqual(canonical_bytes(self.chat.state), before)
            self.assertFalse(task.done())
        finally:
            client.release.set()
            await task

    def test_tui_report_keeps_editor_and_context_out_of_author_history(self) -> None:
        from prompt_toolkit.input import DummyInput
        from prompt_toolkit.output import DummyOutput

        from mos_eisley.conversation_tui import ConversationTUI

        ui = ConversationTUI(self.chat, input=DummyInput(), output=DummyOutput())
        ui.editor.text = "Retained draft"
        agent_command(self.chat, "/agent child-1", ui.emit)
        self.assertEqual(ui.editor.text, "Retained draft")
        self.assertIn("Parser patch retained", ui.transcript.text)
        self.assertEqual(self.chat.state.entries, ())

    def test_submission_alias_is_exact(self) -> None:
        self.assertEqual(submission_command("/agent"), "agent_inspection")
        self.assertEqual(submission_command("/subagents child-1"), "agent_inspection")
        self.assertIsNone(submission_command("/agentish"))

    def test_source_reconnect_after_json_and_sqlite_resume_does_not_write(self) -> None:
        root = Path(self.root.name)
        for kind in (ConversationStore, SQLiteConversationStore):
            with kind(root / kind.__name__, self.chat.state.session_id, root) as store:
                store.save(self.chat.state)
                before = canonical_bytes(store.load())
                resumed = ConversationController(
                    store.load(),
                    self.chat.cassette,
                    store.save,
                    child_inspection=self.source,
                )
                self.assertEqual(
                    resumed.inspect_agents("child-1").report_status, "available"
                )
                self.assertEqual(canonical_bytes(store.load()), before)
                disconnected = ConversationController(
                    store.load(), self.chat.cassette, store.save
                )
                with self.assertRaisesRegex(ValueError, "qualified"):
                    disconnected.inspect_agents()

    def test_oversized_or_sealed_source_projections_fail_closed(self) -> None:
        original = self.source.view
        review = original.children[1].model_copy(
            update={"unresolved": ("sealed secret",)}
        )
        self.source.view = original.model_copy(update={"children": (review,)})
        events: list[dict[str, object]] = []
        self.assertEqual(agent_command(self.chat, "/agent", events.append), "rejected")
        self.assertNotIn("sealed secret", str(events))
        child = original.children[0]
        assignment = child.assignment
        assert assignment is not None
        huge = assignment.model_copy(update={"objective": "x" * 8000})
        children = tuple(
            child.model_copy(update={"child_id": f"child-{i}", "assignment": huge})
            for i in range(32)
        )
        self.source.view = original.model_copy(update={"children": children})
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.chat.inspect_agents()
        self.assertEqual(self.source.reads, 0)

    async def test_rejected_typed_command_preserves_draft_and_paste_is_literal(
        self,
    ) -> None:
        self.chat.child_inspection = None
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        ack = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/agent", False, ack))
        queue.put_nowait(None)
        await terminal(self.chat, queue, lambda _: None)
        self.assertFalse(ack.result())
        self.assertEqual(self.chat.state.entries, ())
        literal = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/agent", True, literal))
        queue.put_nowait(None)
        await terminal(self.chat, queue, lambda _: None)
        self.assertTrue(literal.result())
        self.assertEqual(self.chat.state.entries[0].text, "/agent")
