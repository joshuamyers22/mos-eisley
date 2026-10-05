"""Explicit forks, transient side context, private persistence and shared budgets."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_conversation import WaitingClient
from test_conversation_context import CapturingClient
from test_conversation_goal import definition

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_branch_commands import BranchCommands
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_state import ConversationState, WorkingConversationState
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.task_state import ResourceCeiling


class BranchTests(IsolatedAsyncioTestCase):
    def chat(self, root: Path) -> ConversationController:
        cassette = AgentCassette(exchanges=(demo_cassette().exchanges[0],) * 16)
        return ConversationController(
            ConversationController.fresh(root, cassette), cassette, lambda _: None
        )

    async def history(self, chat: ConversationController) -> None:
        chat.submit("Selected source")
        await chat.step(CapturingClient())
        chat.submit("Omitted private source")
        await chat.step(CapturingClient())

    async def test_fork_copies_only_selected_context_and_no_executable_state(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = self.chat(root)
            await self.history(chat)
            children: list[ConversationState] = []
            chat.publish_fork = children.append
            before_entries = chat.state.entries
            fork = chat.create_fork(
                (0,), boundary=1, expected_revision=chat.state.revision
            )
            self.assertEqual(chat.state.entries, before_entries)
            self.assertEqual(children, [fork])
            self.assertIsNone(fork.memory)
            self.assertIsNone(fork.task_checkpoint)
            self.assertIsNone(fork.task_continuation)
            self.assertEqual(fork.entries, ())
            self.assertEqual(fork.exchanges_consumed, chat.state.exchanges_consumed)
            self.assertNotIn(b"Omitted private source", canonical_bytes(fork))
            self.assertEqual(chat.state.forks[-1].state, "published")
            child = ConversationController(fork, chat.cassette, lambda _: None)
            child.submit("Explore the branch")
            preview = preview_context(child.state)
            client = CapturingClient()
            await child.step(client)
            self.assertIn("Selected source", client.requests[0].system)
            self.assertNotIn("Omitted private source", client.requests[0].system)
            admission = child.state.entries[0].request_admission
            assert admission is not None
            self.assertEqual(preview.request.sha256, admission.request.sha256)
            child.submit("Allowance cannot reset")
            self.assertFalse(await child.step(CapturingClient()))

    async def test_fork_goal_obligations_and_disjoint_allowance_survive_resume(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = self.chat(root)
            goal = chat.create_goal(definition())
            chat.submit("Work")
            await chat.step(CapturingClient())
            children: list[ConversationState] = []
            chat.publish_fork = children.append
            before = chat.current_goal
            assert before is not None
            fork = chat.create_fork(
                (0,), boundary=0, expected_revision=chat.state.revision
            )
            parent_goal = chat.current_goal
            assert parent_goal is not None
            self.assertEqual(parent_goal.ledger.attempts, before.ledger.attempts + 1)
            self.assertEqual(fork.goals[0].goal_id, goal.goal_id)
            self.assertEqual(
                fork.goals[0].definition.remaining_work, goal.definition.remaining_work
            )
            self.assertEqual(fork.goals[0].ledger, before.ledger)
            self.assertEqual(fork.goals[0].status, "paused")
            child = ConversationController(fork, chat.cassette, lambda _: None)
            child.goal_control("resume")
            child.submit("One allowed turn")
            await child.step(CapturingClient())
            child.goal_control("clear")
            child.create_goal(definition())
            child.submit("No fresh fork budget")
            self.assertFalse(await child.step(CapturingClient()))

    async def test_stale_cross_owner_invalid_and_pending_boundary_rejected(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)
            chat.publish_fork = lambda _: None
            for selected, boundary, revision in (
                ((0,), 1, chat.state.revision - 1),
                ((1, 0), 1, chat.state.revision),
                ((0, 0), 1, chat.state.revision),
                ((1,), 0, chat.state.revision),
                ((2,), 2, chat.state.revision),
                ((-1,), 0, chat.state.revision),
            ):
                with self.assertRaises(ValueError):
                    chat.create_fork(
                        selected, boundary=boundary, expected_revision=revision
                    )
            chat.state = chat.state.model_copy(update={"owner_uid": os.getuid() + 1})
            with self.assertRaisesRegex(ValueError, "owner"):
                chat.create_fork(
                    (0,), boundary=0, expected_revision=chat.state.revision
                )

    async def test_parent_reservation_precedes_failed_fork_publication(self) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)

            def fail(_state: ConversationState) -> None:
                assert chat.state.branch_budget is not None
                self.assertEqual(chat.state.branch_budget.ledger.attempts, 3)
                raise OSError("Publish failed after reservation")

            chat.publish_fork = fail
            with self.assertRaises(OSError):
                chat.create_fork(
                    (0,), boundary=0, expected_revision=chat.state.revision
                )
            self.assertEqual(chat.state.forks[-1].state, "uncertain")
            assert chat.state.branch_budget is not None
            self.assertEqual(chat.state.branch_budget.ledger.attempts, 3)

    async def test_repeated_forks_cannot_reuse_parent_budget(self) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)
            chat.publish_fork = lambda _: None
            allowance = ResourceCeiling(
                input_bytes=1000,
                output_bytes=1000,
                attempts=8,
                cost_microusd=0,
                correction_cycles=0,
                review_rounds=0,
            )
            chat.create_fork(
                (0,),
                boundary=0,
                expected_revision=chat.state.revision,
                allowance=allowance,
            )
            revision = chat.state.revision
            with self.assertRaisesRegex(ValueError, "allowance"):
                chat.create_fork(
                    (0,), boundary=0, expected_revision=revision, allowance=allowance
                )
            self.assertEqual(chat.state.revision, revision)
            self.assertEqual(len(chat.state.forks), 1)

    async def test_workspace_changes_stop_fork_until_explicit_revalidation(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)
            chat.publish_fork = lambda _: None
            fork = chat.create_fork(
                (0,), boundary=0, expected_revision=chat.state.revision
            )
            child = ConversationController(
                fork,
                chat.cassette,
                lambda _: None,
                branch_workspace_observer=lambda _: digest(b"changed"),
            )
            child.submit("Explore")
            with self.assertRaisesRegex(ValueError, "revalidate"):
                await child.step(CapturingClient())
            self.assertEqual(child.state.exchanges_consumed, fork.exchanges_consumed)
            child.revalidate_fork()
            await child.step(CapturingClient())

    async def test_side_is_transient_and_enters_main_only_when_attached(self) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)
            before = chat.state.entries
            side = await chat.ask_side(
                "Explain the detail",
                (0,),
                expected_revision=chat.state.revision,
                client=CapturingClient(),
            )
            self.assertEqual(chat.state.entries, before)
            stored = canonical_bytes(chat.state)
            self.assertNotIn(b"Explain the detail", stored)
            self.assertNotIn(side.answer.encode(), canonical_bytes(chat.state.sides[0]))
            chat.submit("Separate main question")
            client = CapturingClient()
            await chat.step(client)
            self.assertNotIn(
                side.receipt.side_id, canonical_bytes(client.requests[0]).decode()
            )
            chat.attach_side(side.receipt.side_id)
            self.assertIn(side.answer, chat.state.entries[-1].text)
            self.assertIn(side.receipt.context_sha256, chat.state.entries[-1].text)
            self.assertEqual(
                chat.state.sides[0].attached_position, len(chat.state.entries) - 1
            )
            with self.assertRaises(ValueError):
                chat.attach_side(side.receipt.side_id)

    async def test_side_context_is_selected_read_only_and_excludes_memory(self) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)
            client = CapturingClient()
            await chat.ask_side(
                "Question", (0,), expected_revision=chat.state.revision, client=client
            )
            request = client.requests[0]
            self.assertEqual(request.tools, ())
            self.assertIn("Selected source", request.system)
            self.assertNotIn("Omitted private source", request.system)
            self.assertEqual(len(request.turns), 1)
            self.assertIn("Side question", request.system)

    async def test_side_does_not_interrupt_active_author_or_queued_steering(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            chat.submit("Active author")
            waiting = WaitingClient()
            author = asyncio.create_task(chat.step(waiting))
            await asyncio.wait_for(waiting.started.wait(), 2)
            try:
                side = await chat.ask_side(
                    "Concurrent read-only question",
                    (),
                    expected_revision=chat.state.revision,
                    client=CapturingClient(),
                )
                self.assertEqual(chat.state.entries[0].status, "running")
                chat.submit("Steering retained")
                self.assertEqual(chat.state.entries[1].status, "queued")
                self.assertEqual(chat.state.exchanges_consumed, 2)
                self.assertEqual(side.receipt.state, "completed")
            finally:
                waiting.release.set()
                await author
            self.assertEqual(chat.state.entries[0].status, "completed")
            self.assertEqual(chat.state.entries[1].text, "Steering retained")
            assert chat.state.branch_budget is not None
            self.assertEqual(chat.state.branch_budget.pending, ())

    async def test_cancelled_side_preserves_exposure_and_main_task(self) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            chat.submit("Unstarted main")
            waiting = WaitingClient()
            side = asyncio.create_task(
                chat.ask_side(
                    "Wait", (), expected_revision=chat.state.revision, client=waiting
                )
            )
            await asyncio.wait_for(waiting.started.wait(), 2)
            side.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await side
            self.assertEqual(chat.state.entries[0].status, "queued")
            self.assertEqual(chat.state.sides[0].state, "cancelled")
            assert chat.state.branch_budget is not None
            self.assertEqual(chat.state.branch_budget.ledger.uncertain_effects, 1)
            with self.assertRaises(ValueError):
                await chat.ask_side(
                    "No retry",
                    (),
                    expected_revision=chat.state.revision,
                    client=CapturingClient(),
                )

    async def test_side_restart_discards_content_and_retains_uncertainty_once(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            waiting = WaitingClient()
            side = asyncio.create_task(
                chat.ask_side(
                    "Lost question",
                    (),
                    expected_revision=chat.state.revision,
                    client=waiting,
                )
            )
            await asyncio.wait_for(waiting.started.wait(), 2)
            saved = ConversationState.model_validate_json(chat.state.model_dump_json())
            recovered = ConversationController(saved, chat.cassette, lambda _: None)
            assert recovered.state.branch_budget is not None
            self.assertEqual(recovered.state.branch_budget.ledger.uncertain_effects, 1)
            twice = ConversationController(
                recovered.state, chat.cassette, lambda _: None
            )
            self.assertEqual(twice.state.branch_budget, recovered.state.branch_budget)
            with self.assertRaises(ValueError):
                twice.attach_side(saved.sides[0].side_id)
            side.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await side

    async def test_goal_pause_and_side_usage_survive_without_false_progress(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            chat.create_goal(definition())
            chat.goal_control("pause")
            await chat.ask_side(
                "Clarify",
                (),
                expected_revision=chat.state.revision,
                client=CapturingClient(),
            )
            goal = chat.current_goal
            assert goal is not None
            self.assertEqual(goal.status, "paused")
            self.assertEqual(goal.ledger.attempts, 1)
            self.assertEqual(goal.no_progress, 0)
            self.assertEqual(goal.progress_ids, ())

    async def test_json_sqlite_keep_provenance_but_not_unattached_side_content(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in (ConversationStore, SQLiteConversationStore):
                chat = self.chat(root)
                with kind(root / kind.__name__, chat.state.session_id, root) as store:
                    store.save(chat.state)
                    chat.save = store.save
                    side = await chat.ask_side(
                        "Transient secret question",
                        (),
                        expected_revision=chat.state.revision,
                        client=CapturingClient(),
                    )
                    loaded = store.load()
                    self.assertEqual(loaded.sides, chat.state.sides)
                    self.assertNotIn(
                        b"Transient secret question", canonical_bytes(loaded)
                    )
                    resumed = ConversationController(loaded, chat.cassette, store.save)
                    with self.assertRaises(ValueError):
                        resumed.attach_side(side.receipt.side_id)

    async def test_typed_rejection_preserves_ack_and_pasted_command_is_literal(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(ConversationSubmission("/fork 99", False, accepted))
            queue.put_nowait(None)
            await terminal(chat, queue, lambda _: None)
            self.assertFalse(accepted.result())
            self.assertEqual(chat.state.entries, ())
            chat = self.chat(Path(directory))
            queue = asyncio.Queue()
            literal_ack = asyncio.get_running_loop().create_future()
            queue.put_nowait(
                ConversationSubmission("/side - literal text", True, literal_ack)
            )
            queue.put_nowait(None)
            await terminal(chat, queue, lambda _: None)
            self.assertTrue(literal_ack.result())
            self.assertEqual(chat.state.sides, ())
            self.assertEqual(chat.state.entries[0].text, "/side - literal text")

    async def test_fork_store_error_is_fatal_not_success_ack(self) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)
            chat.publish_fork = lambda _: None

            def fail(_state: ConversationState) -> None:
                raise OSError("Storage lost")

            chat.save = fail
            with self.assertRaises(OSError):
                await BranchCommands(chat, lambda _: None).execute("/fork 0")
            self.assertEqual(chat.state.forks, ())

    async def test_legacy_serialization_has_no_branch_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            payload = canonical_bytes(chat.state)
            self.assertNotIn(b"fork_origin", payload)
            self.assertNotIn(b"branch_budget", payload)
            self.assertEqual(
                canonical_bytes(ConversationState.model_validate_json(payload)), payload
            )

    async def test_archived_sqlite_selection_and_fork_publication_retain_exact_source(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = self.chat(root)
            with SQLiteConversationStore(
                root / "sessions", chat.state.session_id, root
            ) as store:
                store.save(chat.state)
                chat.save = store.save
                await self.history(chat)
                working = store.load_working()
                assert isinstance(working, WorkingConversationState)
                runtime = ConversationController(
                    working,
                    chat.cassette,
                    store.save_working,
                    load_entry=store.load_working_entry,
                )

                def publish(child: ConversationState) -> None:
                    with SQLiteConversationStore(
                        root / "sessions", child.session_id, root
                    ) as child_store:
                        child_store.save(child)

                runtime.publish_fork = publish
                child = runtime.create_fork(
                    (0,), boundary=0, expected_revision=runtime.state.revision
                )
                with SQLiteConversationStore(
                    root / "sessions", child.session_id, root, create=False
                ) as child_store:
                    restored = child_store.load()
                    self.assertEqual(restored.fork_origin, child.fork_origin)
                    self.assertEqual(restored.branch_budget, child.branch_budget)
                    self.assertNotIn(
                        b"Omitted private source", canonical_bytes(restored)
                    )
                self.assertEqual(store.load_working().forks, runtime.state.forks)

    async def test_review_boundary_is_never_selected_into_fork_or_side_context(
        self,
    ) -> None:
        from mos_eisley.conversation_review import ConversationReviewPacket
        from mos_eisley.demo import demo_inputs

        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            brief, recording = demo_inputs()
            chat.submit_review(
                ConversationReviewPacket(brief=brief, cassette=recording)
            )
            await chat.step()
            chat.publish_fork = lambda _: None
            with self.assertRaises(ValueError):
                chat.create_fork(
                    (0,), boundary=0, expected_revision=chat.state.revision
                )
            with self.assertRaises(ValueError):
                await chat.ask_side(
                    "No sealed context",
                    (0,),
                    expected_revision=chat.state.revision,
                    client=CapturingClient(),
                )

    async def test_live_tui_branch_rejection_retains_editor_and_report_preserves_draft(
        self,
    ) -> None:
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        from test_conversation_tui import until

        from mos_eisley.conversation_tui import ConversationTUI

        with TemporaryDirectory() as directory, create_pipe_input() as pipe:
            chat = self.chat(Path(directory))
            ui = ConversationTUI(chat, input=pipe, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                pipe.send_text("/fork 99\r")
                await until(lambda: not ui.sending and "safe boundary" in ui.notice)
                self.assertEqual(ui.editor.text, "/fork 99")
                ui.emit({"type": "conversation.side", "text": "Transient side answer"})
                self.assertEqual(ui.editor.text, "/fork 99")
                self.assertIn("Transient side answer", ui.transcript.text)
            finally:
                pipe.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_terminal_side_command_acknowledges_without_main_submission(
        self,
    ) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            ack = asyncio.get_running_loop().create_future()
            queue.put_nowait(
                ConversationSubmission("/side - A separate question", False, ack)
            )
            queue.put_nowait(None)
            events: list[dict[str, object]] = []
            with patch(
                "mos_eisley.conversation_branch_controller.RecordedAgentClient",
                return_value=CapturingClient(),
            ):
                await terminal(chat, queue, events.append)
            self.assertTrue(ack.result())
            self.assertEqual(chat.state.entries, ())
            self.assertEqual(chat.state.sides[0].state, "completed")
            self.assertTrue(
                any(e["type"] == "conversation.side" and "receipt" in e for e in events)
            )

    async def test_timeout_ignores_late_answer_and_recovery_preserves_all_charges(
        self,
    ) -> None:
        from mos_eisley.core.agent import AgentUsage
        from mos_eisley.core.protocol import ModelRequest, ModelResponse

        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            chat.side_timeout = 0.01
            release, finished = asyncio.Event(), asyncio.Event()

            class ResistantClient:
                async def complete(self, request: ModelRequest) -> ModelResponse:
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        await release.wait()
                    finished.set()
                    return await CapturingClient().complete(request)

            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(
                    chat.ask_side(
                        "Question",
                        (),
                        expected_revision=chat.state.revision,
                        client=ResistantClient(),
                    ),
                    1,
                )
            receipt = chat.state.sides[0]
            budget = chat.state.branch_budget
            assert budget is not None
            usage = AgentUsage(
                requests=1, tools=0, billed_input=0, billed_output=0, largest_request=0
            )

            def reconcile() -> None:
                chat.reconcile_side(
                    receipt.side_id,
                    expected_request_sha256=receipt.request_sha256,
                    receipt_sha256=digest(b"recovery"),
                    usage=usage,
                )

            try:
                with self.assertRaisesRegex(ValueError, "provider operation"):
                    reconcile()
            finally:
                release.set()
                await asyncio.wait_for(finished.wait(), 1)
                await asyncio.sleep(0)
            self.assertEqual(chat.state.sides[0].state, "uncertain")
            self.assertFalse(chat.side_answer_available(receipt.side_id))
            reconcile()
            after = chat.state.branch_budget
            assert after is not None
            self.assertEqual(after.ledger.input_bytes, budget.ledger.input_bytes)
            self.assertEqual(after.ledger.output_bytes, budget.ledger.output_bytes)
            self.assertEqual(after.ledger.attempts, budget.ledger.attempts)
            self.assertEqual(after.ledger.uncertain_effects, 0)
            reconcile()
            self.assertEqual(chat.state.branch_budget, after)

    async def test_goal_activation_retains_previous_side_usage_and_refuses_inflight(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            waiting = WaitingClient()
            task = asyncio.create_task(
                chat.ask_side(
                    "Question",
                    (),
                    expected_revision=chat.state.revision,
                    client=waiting,
                )
            )
            await asyncio.wait_for(waiting.started.wait(), 2)
            try:
                with self.assertRaisesRegex(ValueError, "side operations"):
                    chat.create_goal(definition())
            finally:
                waiting.release.set()
                await task
            goal = chat.create_goal(definition())
            self.assertEqual(goal.ledger.attempts, 1)
            assert chat.state.branch_budget is not None
            self.assertEqual(goal.ledger, chat.state.branch_budget.ledger)

    async def test_fork_goal_evaluator_cannot_exceed_the_allocated_attempt(
        self,
    ) -> None:
        from test_conversation_goal import INPUTS, WS, proof

        from mos_eisley.conversation_goal_evaluation import (
            GoalEvaluationInput,
            GoalSemanticVerdict,
        )

        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            chat.create_goal(definition())
            chat.submit("Parent work")
            await chat.step(CapturingClient())
            chat.publish_fork = lambda _: None
            fork = chat.create_fork(
                (0,), boundary=0, expected_revision=chat.state.revision
            )
            child = ConversationController(fork, chat.cassette, lambda _: None)
            child.goal_control("resume")
            child.observe_goal_inputs = lambda: (WS, INPUTS)
            child.observe_goal_evidence = lambda goal: proof(
                goal, semantic="unavailable"
            )
            calls: list[GoalEvaluationInput] = []

            async def evaluator(request: GoalEvaluationInput) -> GoalSemanticVerdict:
                calls.append(request)
                return GoalSemanticVerdict(
                    definition_sha256=request.definition_sha256,
                    evidence_sha256=request.evidence_sha256,
                    decision="passed",
                    reason="Bounded semantic check",
                )

            child.goal_evaluator = evaluator
            with self.assertRaisesRegex(ValueError, "allowance"):
                await child.evaluate_goal()
            self.assertEqual(calls, [])
            self.assertIsNotNone(child.current_goal)
            goal = child.current_goal
            assert goal is not None
            self.assertIsNone(goal.evaluating_sha256)

    async def test_fork_does_not_clone_implementation_or_review_grants(self) -> None:
        from test_conversation_task_profile import selected_profile

        from mos_eisley.conversation_review import ConversationReviewPacket
        from mos_eisley.conversation_task_profile import ScopedTaskProfile
        from mos_eisley.demo import demo_inputs

        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)
            chat.publish_fork = lambda _: None
            fork = chat.create_fork(
                (0,), boundary=0, expected_revision=chat.state.revision
            )
            child = ConversationController(fork, chat.cassette, lambda _: None)
            brief, recording = demo_inputs()
            with self.assertRaisesRegex(ValueError, "review allowance"):
                child.submit_review(
                    ConversationReviewPacket(brief=brief, cassette=recording)
                )
            profile, scope = selected_profile(Path(directory))
            child.task_scope = scope

            def resolve_profile(_position: int) -> ScopedTaskProfile:
                return profile

            child.resolve_task_profile = resolve_profile
            child.submit("Request a write")
            with self.assertRaisesRegex(ValueError, "task tools"):
                await child.step(CapturingClient())
            self.assertEqual(child.state.entries[0].status, "queued")
            self.assertEqual(child.state.exchanges_consumed, fork.exchanges_consumed)

    async def test_git_checkout_revalidation_detects_actual_working_file_change(
        self,
    ) -> None:
        import subprocess

        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "source.txt").write_text("Before\n")
            chat = self.chat(root)
            await self.history(chat)
            chat.publish_fork = lambda _: None
            fork = chat.create_fork(
                (0,), boundary=0, expected_revision=chat.state.revision
            )
            child = ConversationController(fork, chat.cassette, lambda _: None)
            (root / "source.txt").write_text("After\n")
            child.submit("Read historical context")
            with self.assertRaisesRegex(ValueError, "revalidate"):
                await child.step(CapturingClient())
            child.revalidate_fork()
            await child.step(CapturingClient())

    async def test_refresh_preserves_branch_origin_budget_and_side_receipts(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            await self.history(chat)
            chat.publish_fork = lambda _: None
            fork = chat.create_fork(
                (0,), boundary=0, expected_revision=chat.state.revision
            )
            child = ConversationController(fork, chat.cassette, lambda _: None)
            before = child.state
            child.refresh_memory(None, chat.cassette, disabled=True)
            self.assertEqual(child.state.fork_origin, before.fork_origin)
            self.assertEqual(child.state.branch_budget, before.branch_budget)
            self.assertEqual(child.state.sides, before.sides)
