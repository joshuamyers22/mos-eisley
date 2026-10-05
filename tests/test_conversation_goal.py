"""Goal admission, completion guards, restart and bounded semantic evaluation."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase

from test_conversation import WaitingClient
from test_conversation_checkpoint_closure import scoped_bundle
from test_conversation_context import CapturingClient

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_goal import (
    DurableGoal,
    GoalDefinition,
    GoalEvidence,
    GoalFailure,
    GoalJob,
    GoalTestReceipt,
    decide,
    guard_goal_checkpoint,
)
from mos_eisley.conversation_goal_evaluation import (
    GoalEvaluationInput,
    GoalSemanticVerdict,
)
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_state import ConversationState
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.conversation_transcript import read_sqlite_transcript
from mos_eisley.task_state import ArtifactReference, ResourceLedger

WS, INPUTS, RECEIPT = digest(b"workspace"), digest(b"tests"), digest(b"receipt")


def active(chat: ConversationController) -> DurableGoal:
    goal = chat.current_goal
    assert goal is not None
    return goal


def definition() -> GoalDefinition:
    return GoalDefinition(
        objective="Ship the cache",
        success_criteria=("Correct bounded cache",),
        remaining_work=("Implement cache", "Verify cache"),
        verification_requirements=("cache-tests",),
    )


def proof(goal: DurableGoal, *, semantic: str = "passed") -> GoalEvidence:
    return GoalEvidence.model_validate_json(
        __import__("json").dumps(
            {
                "goal_id": goal.goal_id,
                "definition_sha256": goal.definition.sha256,
                "workspace_sha256": WS,
                "inputs_sha256": INPUTS,
                "receipt_ids": [RECEIPT],
                "completed_work": list(goal.definition.remaining_work),
                "passed_verifications": list(goal.definition.verification_requirements),
                "executed_tests": 2,
                "independent_review": "accept",
                "semantic": semantic,
                "complete_view": True,
            }
        )
    )


class GoalTests(IsolatedAsyncioTestCase):
    def chat(self, root: Path | None = None) -> ConversationController:
        cassette = AgentCassette(exchanges=(demo_cassette().exchanges[0],) * 16)
        return ConversationController(
            ConversationController.fresh(root or Path.cwd(), cassette),
            cassette,
            lambda _: None,
            goal_clock=lambda: 100.0,
        )

    async def test_only_explicit_creation_activates_goal(self) -> None:
        chat = self.chat()
        chat.submit("What is next?")
        await chat.step(CapturingClient())
        self.assertIsNone(chat.current_goal)
        chat.create_goal(definition())
        self.assertEqual(chat.state.exchanges_consumed, 1)
        self.assertEqual(len(chat.state.entries), 1)
        self.assertEqual(
            active(chat).definition.success_criteria, ("Correct bounded cache",)
        )

    async def test_author_end_turn_is_not_completion_and_preview_matches(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        chat.submit("I have completed everything")
        preview = preview_context(chat.state)
        client = CapturingClient()
        await chat.step(client)
        current = chat.current_goal
        assert current is not None
        self.assertEqual(current.status, "working")
        self.assertEqual(current.no_progress, 1)
        self.assertEqual(current.ledger.attempts, 1)
        self.assertGreater(current.ledger.input_bytes, 0)
        self.assertEqual(current.reservations, ())
        self.assertIn("Explicit durable objective", client.requests[0].system)
        self.assertIn("Implement cache", current.decisions[-1].missing)
        self.assertEqual(chat.state.entries[0].goal_id, goal.goal_id)
        admission = chat.state.entries[0].request_admission
        assert admission is not None
        self.assertEqual(preview.request.sha256, admission.request.sha256)

    async def test_revision_bound_proof_is_required_for_completion(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        evidence = proof(goal)
        for bad in (
            None,
            evidence.model_copy(update={"workspace_sha256": digest(b"stale")}),
            evidence.model_copy(update={"inputs_sha256": digest(b"old-tests")}),
            evidence.model_copy(update={"definition_sha256": digest(b"old-goal")}),
            evidence.model_copy(update={"receipt_ids": ()}),
            evidence.model_copy(update={"complete_view": False}),
            evidence.model_copy(update={"executed_tests": 0}),
            evidence.model_copy(update={"independent_review": "reject"}),
            evidence.model_copy(update={"passed_verifications": ()}),
            evidence.model_copy(update={"completed_work": ()}),
        ):
            self.assertNotEqual(
                decide(
                    goal, 100, bad, workspace_sha256=WS, inputs_sha256=INPUTS
                ).status,
                "completed",
            )
        current = decide(goal, 100, evidence, workspace_sha256=WS, inputs_sha256=INPUTS)
        self.assertEqual(current.status, "completed")
        self.assertEqual(current.decisions[-1].receipt_ids, (RECEIPT,))

    async def test_stall_and_explicit_resume_preserve_counters_and_budgets(
        self,
    ) -> None:
        chat = self.chat()
        chat.create_goal(definition())
        for _ in range(3):
            chat.submit("Still working, tools ran")
            await chat.step(CapturingClient())
        current = chat.current_goal
        assert current is not None
        self.assertEqual(current.status, "stalled")
        ledger, counter = current.ledger, current.no_progress
        chat.goal_control("resume")
        self.assertEqual(active(chat).ledger, ledger)
        self.assertEqual(active(chat).no_progress, counter)
        chat.submit("Try a different approach")
        await chat.step(CapturingClient())
        self.assertEqual(active(chat).status, "stalled")
        self.assertEqual(active(chat).no_progress, 4)

    async def test_pause_during_work_keeps_goal_paused_after_late_answer(self) -> None:
        chat = self.chat()
        chat.create_goal(definition())
        chat.submit("Work")
        waiting = WaitingClient()
        task = asyncio.create_task(chat.step(waiting))
        await asyncio.wait_for(waiting.started.wait(), 2)
        self.assertEqual(active(chat).ledger.attempts, 1)
        chat.goal_control("pause")
        waiting.release.set()
        await task
        self.assertEqual(active(chat).status, "paused")
        self.assertEqual(active(chat).ledger.attempts, 1)
        self.assertEqual(active(chat).reservations, ())

    async def test_pause_skips_goal_queue_but_allows_direct_question(self) -> None:
        chat = self.chat()
        chat.create_goal(definition())
        chat.submit("Queued work")
        chat.goal_control("pause")
        chat.submit("What does caching mean?")
        await chat.step(CapturingClient())
        self.assertEqual(chat.state.entries[0].status, "queued")
        self.assertEqual(chat.state.entries[1].status, "completed")
        self.assertIsNone(chat.state.entries[1].goal_id)
        self.assertFalse(await chat.step(CapturingClient()))

    async def test_edit_invalidates_proof_and_old_queue_without_reset(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        chat.submit("Old work")
        chat.check_goal()
        new = definition().model_copy(
            update={
                "objective": "Ship revised cache",
                "remaining_work": ("New obligation",),
            }
        )
        chat.edit_goal(new, expected_revision=1)
        self.assertEqual(active(chat).status, "paused")
        self.assertIn("New obligation", active(chat).describe(100))
        self.assertIsNone(active(chat).current_decision)
        self.assertEqual(len(active(chat).decisions), 1)
        chat.goal_control("resume")
        self.assertFalse(chat.can_dispatch(chat.state.entries[0]))
        self.assertNotEqual(active(chat).definition.sha256, goal.definition.sha256)
        with self.assertRaisesRegex(ValueError, "revision changed"):
            chat.edit_goal(new, expected_revision=1)

    async def test_clear_preserves_private_history_and_cumulative_limits(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        chat.submit("Work")
        await chat.step(CapturingClient())
        old_ledger = active(chat).ledger
        chat.goal_control("clear")
        self.assertIsNone(chat.current_goal)
        self.assertEqual(chat.state.goals[0].goal_id, goal.goal_id)
        second = chat.create_goal(definition())
        self.assertEqual(second.ledger, old_ledger)
        self.assertEqual(second.started_at, goal.started_at)

    async def test_budget_exhaustion_never_becomes_completion(self) -> None:
        chat = self.chat()
        d = definition()
        d = d.model_copy(
            update={"ceiling": d.ceiling.model_copy(update={"attempts": 1})}
        )
        chat.create_goal(d)
        chat.submit("Work")
        await chat.step(CapturingClient())
        self.assertEqual(active(chat).status, "budget_exhausted")
        with self.assertRaisesRegex(ValueError, "exhausted"):
            chat.goal_control("resume")
        self.assertEqual(active(chat).ledger.attempts, 1)

    async def test_wall_time_is_not_reset_by_pause_or_resume(self) -> None:
        chat = self.chat()
        chat.create_goal(definition().model_copy(update={"max_seconds": 10}))
        chat.goal_control("pause")
        chat.goal_clock = lambda: 111.0
        with self.assertRaisesRegex(ValueError, "exhausted"):
            chat.goal_control("resume")
        self.assertEqual(active(chat).started_at, 100.0)

    async def test_failure_retains_exposure_and_cannot_repeat_uncertain_request(
        self,
    ) -> None:
        chat = self.chat()
        chat.create_goal(definition())
        chat.submit("Work")
        task = asyncio.create_task(chat.step(WaitingClient()))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(active(chat).status, "blocked")
        self.assertEqual(active(chat).ledger.uncertain_effects, 1)
        self.assertEqual(active(chat).ledger.attempts, 1)
        with self.assertRaisesRegex(ValueError, "reconciliation"):
            chat.goal_control("resume")
        self.assertFalse(chat.can_dispatch(chat.state.entries[0]))

    async def test_json_sqlite_restart_and_history_keep_goal_identity(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in (ConversationStore, SQLiteConversationStore):
                chat = self.chat(root)
                with kind(root / kind.__name__, chat.state.session_id, root) as store:
                    store.save(chat.state)
                    chat.save = store.save
                    goal = chat.create_goal(definition())
                    chat.submit("Work")
                    await chat.step(CapturingClient())
                    restored = store.load()
                    self.assertEqual(restored.goals, chat.state.goals)
                    self.assertEqual(
                        restored.entries[0].goal_definition_sha256,
                        goal.definition.sha256,
                    )
                    if isinstance(store, SQLiteConversationStore):
                        working = store.load_working()
                        self.assertEqual(working.goals, chat.state.goals)
                        page = read_sqlite_transcript(
                            root / kind.__name__, chat.state.session_id, root
                        )
                        self.assertEqual(page.entries[0].content.goal_id, goal.goal_id)

    async def test_legacy_snapshot_and_wrong_owner_fail_closed(self) -> None:
        chat = self.chat()
        before = canonical_bytes(chat.state)
        self.assertNotIn(b"goals", before)
        self.assertEqual(
            canonical_bytes(ConversationState.model_validate_json(before)), before
        )
        chat.create_goal(definition())
        goal = chat.current_goal
        assert goal is not None
        bad = chat.state.model_copy(
            update={
                "goals": (goal.model_copy(update={"owner_uid": goal.owner_uid + 1}),)
            }
        )
        with self.assertRaises(ValueError):
            ConversationState.model_validate_json(bad.model_dump_json())

    async def test_required_vs_optional_jobs_and_terminal_goals(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        evidence = proof(goal)
        for required, expected in ((True, "waiting"), (False, "completed")):
            candidate = goal.model_copy(
                update={"jobs": (GoalJob(operation_id="test-job", required=required),)}
            )
            assessed = decide(
                candidate, 100, evidence, workspace_sha256=WS, inputs_sha256=INPUTS
            )
            self.assertEqual(assessed.status, expected)
        for status in ("paused", "cancelled"):
            candidate = goal.model_copy(update={"status": status})
            self.assertEqual(
                decide(
                    candidate, 100, evidence, workspace_sha256=WS, inputs_sha256=INPUTS
                ).status,
                status,
            )

    async def test_separate_semantic_evaluator_is_bounded_and_charged(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        observations: list[GoalEvaluationInput] = []

        def observe(_goal: DurableGoal) -> GoalEvidence:
            return proof(_goal, semantic="unavailable")

        async def evaluator(request: GoalEvaluationInput) -> GoalSemanticVerdict:
            observations.append(request)
            return GoalSemanticVerdict(
                definition_sha256=request.definition_sha256,
                evidence_sha256=request.evidence_sha256,
                decision="passed",
                reason="Criteria verified.",
            )

        chat.observe_goal_evidence = observe
        chat.observe_goal_inputs = lambda: (WS, INPUTS)
        chat.goal_evaluator = evaluator
        result = await chat.evaluate_goal()
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.ledger.attempts, 1)
        self.assertEqual(len(observations), 1)
        self.assertIsNone(result.evaluating_sha256)
        self.assertEqual(result.goal_id, goal.goal_id)

    async def test_false_evaluator_claim_cannot_waive_missing_mechanical_evidence(
        self,
    ) -> None:
        chat = self.chat()
        chat.create_goal(definition())
        calls: list[GoalEvaluationInput] = []

        def observe(goal: DurableGoal) -> GoalEvidence:
            return proof(goal, semantic="unavailable").model_copy(
                update={"executed_tests": 0}
            )

        async def evaluator(request: GoalEvaluationInput) -> GoalSemanticVerdict:
            calls.append(request)
            return GoalSemanticVerdict(
                definition_sha256=request.definition_sha256,
                evidence_sha256=request.evidence_sha256,
                decision="passed",
                reason="False completion.",
            )

        chat.observe_goal_evidence = observe
        chat.observe_goal_inputs = lambda: (WS, INPUTS)
        chat.goal_evaluator = evaluator
        result = await chat.evaluate_goal()
        self.assertNotEqual(result.status, "completed")
        self.assertEqual(calls, [])
        self.assertEqual(result.ledger.attempts, 0)

    async def test_evaluator_timeout_and_late_completion_do_not_reopen_pause(
        self,
    ) -> None:
        for pause in (False, True):
            chat = self.chat()
            chat.create_goal(definition())

            def observe(goal: DurableGoal) -> GoalEvidence:
                return proof(goal, semantic="unavailable")

            started, release = asyncio.Event(), asyncio.Event()

            async def evaluator(
                request: GoalEvaluationInput,
                started: asyncio.Event = started,
                release: asyncio.Event = release,
            ) -> GoalSemanticVerdict:
                started.set()
                await release.wait()
                return GoalSemanticVerdict(
                    definition_sha256=request.definition_sha256,
                    evidence_sha256=request.evidence_sha256,
                    decision="passed",
                    reason="Late verdict.",
                )

            chat.observe_goal_evidence = observe
            chat.observe_goal_inputs = lambda: (WS, INPUTS)
            chat.goal_evaluator = evaluator
            chat.goal_evaluator_timeout = 0.05
            task = asyncio.create_task(chat.evaluate_goal())
            await asyncio.wait_for(started.wait(), 2)
            if pause:
                chat.goal_control("pause")
                release.set()
            result = await task
            self.assertEqual(result.status, "paused" if pause else "blocked")
            self.assertEqual(result.ledger.attempts, 1)
            if not pause:
                self.assertEqual(result.ledger.uncertain_effects, 1)
                with self.assertRaises(ValueError):
                    chat.goal_control("resume")

    async def test_cli_controls_do_not_dispatch_and_pasted_goal_is_literal(
        self,
    ) -> None:
        chat = self.chat()
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        for line in ("/goal new Ship cache", "/goal pause", "/goal status", None):
            queue.put_nowait(line)
        events: list[dict[str, object]] = []
        await terminal(chat, queue, events.append)
        self.assertEqual(chat.state.exchanges_consumed, 0)
        self.assertEqual(active(chat).status, "paused")
        self.assertTrue(any(e["type"] == "conversation.goal" for e in events))
        chat = self.chat()
        queue = asyncio.Queue()
        accepted = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/goal new Ship cache", True, accepted))
        queue.put_nowait(None)
        await terminal(chat, queue, lambda _: None)
        self.assertTrue(accepted.result())
        self.assertIsNone(chat.current_goal)
        self.assertEqual(chat.state.entries[0].text, "/goal new Ship cache")

    async def test_recorded_goal_replay_has_exact_budgeted_prompt(self) -> None:
        source = self.chat()
        source.create_goal(definition())
        source.submit("Investigate cache")
        client = CapturingClient()
        await source.step(client)
        cassette = AgentCassette(
            exchanges=(
                AgentExchange(
                    request_sha256=digest(canonical_bytes(client.requests[0])),
                    response=source.cassette.exchanges[0].response,
                ),
            )
        )
        state = ConversationController.fresh(Path.cwd(), cassette).model_copy(
            update={
                "goals": (
                    source.state.goals[0].model_copy(
                        update={
                            "ledger": ResourceLedger(),
                            "no_progress": 0,
                            "decisions": (),
                            "completed_work": (),
                        }
                    ),
                ),
                "active_goal_id": source.state.active_goal_id,
            }
        )
        chat = ConversationController(
            state, cassette, lambda _: None, goal_clock=lambda: 100.0
        )
        chat.submit("Investigate cache")
        self.assertTrue(await chat.step())
        self.assertNotEqual(active(chat).status, "completed")

    async def test_required_results_are_revision_bound_and_duplicates_are_idempotent(
        self,
    ) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        chat.register_goal_job(
            GoalJob(operation_id="build"), expected_definition=goal.definition.sha256
        )
        self.assertEqual(active(chat).status, "waiting")
        report = (
            active(chat)
            .jobs[0]
            .model_copy(update={"state": "passed", "result_sha256": RECEIPT})
        )
        chat.report_goal_job(
            goal.goal_id, report, expected_definition=goal.definition.sha256
        )
        self.assertEqual(active(chat).status, "working")
        revision = chat.state.revision
        chat.report_goal_job(
            goal.goal_id, report, expected_definition=goal.definition.sha256
        )
        self.assertEqual(chat.state.revision, revision)
        with self.assertRaisesRegex(ValueError, "committed result"):
            chat.report_goal_job(
                goal.goal_id,
                report.model_copy(update={"result_sha256": digest(b"other")}),
                expected_definition=goal.definition.sha256,
            )
        with self.assertRaisesRegex(ValueError, "obsolete"):
            chat.report_goal_job(
                goal.goal_id, report, expected_definition=digest(b"old")
            )

    async def test_late_job_result_does_not_resume_pause_or_cancel(self) -> None:
        for action in ("pause", "cancel", "clear"):
            chat = self.chat()
            goal = chat.create_goal(definition())
            chat.register_goal_job(
                GoalJob(operation_id="build"),
                expected_definition=goal.definition.sha256,
            )
            report = (
                active(chat)
                .jobs[0]
                .model_copy(update={"state": "passed", "result_sha256": RECEIPT})
            )
            chat.goal_control(action)
            chat.report_goal_job(
                goal.goal_id, report, expected_definition=goal.definition.sha256
            )
            self.assertEqual(
                chat.state.goals[0].status,
                "cancelled" if action == "cancel" else "paused",
            )
            self.assertEqual(chat.state.exchanges_consumed, 0)

    async def test_lost_background_reports_stop_at_bounded_checkins(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        chat.register_goal_job(
            GoalJob(operation_id="build", checkin_seconds=1, max_checkins=2),
            expected_definition=goal.definition.sha256,
        )
        chat.goal_clock = lambda: 101.0
        self.assertEqual(chat.check_goal().jobs[0].checkins, 1)
        chat.goal_clock = lambda: 103.0
        current = chat.check_goal()
        self.assertEqual(current.status, "blocked")
        self.assertEqual(current.jobs[0].state, "stuck")
        self.assertEqual(current.jobs[0].checkins, 2)
        self.assertEqual(current.ledger.attempts, 0)
        self.assertIn("build", current.decisions[-1].missing[-1])

    async def test_uncertain_reconciliation_preserves_usage_without_resuming(
        self,
    ) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        chat.submit("Work")
        task = asyncio.create_task(chat.step(WaitingClient()))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        ledger = active(chat).ledger
        chat.reconcile_goal_operation(
            "message-0",
            expected_definition=goal.definition.sha256,
            receipt_sha256=RECEIPT,
            observed_ledger=ledger,
        )
        current = active(chat)
        self.assertEqual(current.status, "blocked")
        self.assertEqual(current.ledger.uncertain_effects, 0)
        self.assertEqual(current.ledger.attempts, ledger.attempts)
        self.assertEqual(current.ledger.input_bytes, ledger.input_bytes)
        revision = chat.state.revision
        chat.reconcile_goal_operation(
            "message-0",
            expected_definition=goal.definition.sha256,
            receipt_sha256=RECEIPT,
            observed_ledger=ledger,
        )
        self.assertEqual(chat.state.revision, revision)
        chat.goal_control("resume")
        self.assertEqual(active(chat).ledger.attempts, 1)

    async def test_classified_failures_retain_goal_and_do_not_automatically_retry(
        self,
    ) -> None:
        for category in (
            "transient",
            "usage_exhausted",
            "authentication",
            "configuration",
            "uncertain_effects",
        ):
            chat = self.chat()
            goal = chat.create_goal(definition())
            failure = GoalFailure.model_validate_json(
                __import__("json").dumps(
                    {
                        "category": category,
                        "reason": "Provider action required.",
                        "operation_id": "request-1",
                        "receipt_sha256": RECEIPT,
                        "retryable": category == "transient",
                        "max_retries": 1,
                    }
                )
            )
            chat.report_goal_failure(
                failure, expected_definition=goal.definition.sha256
            )
            self.assertEqual(
                active(chat).status,
                "budget_exhausted" if category == "usage_exhausted" else "blocked",
            )
            revision = chat.state.revision
            chat.report_goal_failure(
                failure, expected_definition=goal.definition.sha256
            )
            self.assertEqual(chat.state.revision, revision)
            self.assertEqual(chat.state.exchanges_consumed, 0)
            self.assertEqual(
                active(chat).failures[0].reason, "Provider action required."
            )

    async def test_empty_or_stale_test_receipt_cannot_close_goal_work_unit(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = self.chat(root)
            d = definition().model_copy(
                update={"verification_requirements": ("focused-tests",)}
            )
            goal = chat.create_goal(d)
            bundle, _scope, _payload = scoped_bundle(root)
            verification = bundle.checkpoint.verifications[0]
            for count, stale, expected in (
                (0, False, False),
                (1, True, False),
                (1, False, True),
            ):
                receipt = GoalTestReceipt(
                    operation_id="tests",
                    executed_tests=count,
                    failed_tests=0,
                    workspace_sha256=verification.bound_workspace_sha256,
                    inputs_sha256=digest(b"stale")
                    if stale
                    else verification.bound_input_sha256,
                )
                payload = canonical_bytes(receipt)
                ref = ArtifactReference(
                    artifact_id="goal-tests",
                    sha256=digest(payload),
                    bytes=len(payload),
                    media_type="application/json",
                    availability="available",
                    freshness="current",
                )
                current = bundle.model_copy(
                    update={
                        "checkpoint": bundle.checkpoint.model_copy(
                            update={
                                "verifications": (
                                    verification.model_copy(update={"result": ref}),
                                )
                            }
                        )
                    }
                )
                if expected:
                    guard_goal_checkpoint(goal, current, {digest(payload): payload})
                else:
                    with self.assertRaises(ValueError):
                        guard_goal_checkpoint(goal, current, {digest(payload): payload})

    async def test_malformed_evaluator_and_changed_inputs_leave_completion_unproven(
        self,
    ) -> None:
        for malformed in (False, True):
            chat = self.chat()
            chat.create_goal(definition())

            def observe(goal: DurableGoal) -> GoalEvidence:
                return proof(goal, semantic="unavailable")

            chat.observe_goal_evidence = observe
            chat.observe_goal_inputs = lambda: (WS, INPUTS)

            async def evaluator(
                request: GoalEvaluationInput,
                malformed: bool = malformed,
                chat: ConversationController = chat,
            ) -> GoalSemanticVerdict:
                if malformed:
                    return cast(GoalSemanticVerdict, {"decision": "passed"})
                chat.observe_goal_inputs = lambda: (
                    digest(b"changed workspace"),
                    INPUTS,
                )
                return GoalSemanticVerdict(
                    definition_sha256=request.definition_sha256,
                    evidence_sha256=request.evidence_sha256,
                    decision="passed",
                    reason="Must not waive freshness.",
                )

            chat.goal_evaluator = evaluator
            current = await chat.evaluate_goal()
            self.assertNotEqual(current.status, "completed")
            self.assertEqual(current.ledger.attempts, 1)

    async def test_semantic_verdicts_for_unchanged_evidence_are_reused(self) -> None:
        chat = self.chat()
        chat.create_goal(definition())

        def observe(goal: DurableGoal) -> GoalEvidence:
            return proof(goal, semantic="unavailable")

        calls: list[GoalEvaluationInput] = []

        async def evaluator(request: GoalEvaluationInput) -> GoalSemanticVerdict:
            calls.append(request)
            return GoalSemanticVerdict(
                definition_sha256=request.definition_sha256,
                evidence_sha256=request.evidence_sha256,
                decision="failed",
                reason="Criterion still unproven.",
            )

        chat.observe_goal_evidence = observe
        chat.observe_goal_inputs = lambda: (WS, INPUTS)
        chat.goal_evaluator = evaluator
        await chat.evaluate_goal()
        await chat.evaluate_goal()
        self.assertEqual(len(calls), 1)
        self.assertEqual(active(chat).ledger.attempts, 1)

    async def test_goal_control_rejection_preserves_typed_draft_acknowledgement(
        self,
    ) -> None:
        chat = self.chat()
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        accepted = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/goal create {}", False, accepted))
        queue.put_nowait(None)
        await terminal(chat, queue, lambda _: None)
        self.assertFalse(accepted.result())
        self.assertIsNone(chat.current_goal)
        self.assertEqual(chat.state.entries, ())

    async def test_storage_failure_is_fatal_and_does_not_claim_goal_creation(
        self,
    ) -> None:
        chat = self.chat()

        def fail(_state: ConversationState) -> None:
            raise ValueError("storage changed")

        chat.save = fail
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        accepted = asyncio.get_running_loop().create_future()
        queue.put_nowait(
            ConversationSubmission("/goal new Ship cache", False, accepted)
        )
        with self.assertRaisesRegex(ValueError, "storage changed"):
            await terminal(chat, queue, lambda _: None)
        self.assertTrue(accepted.cancelled())
        self.assertIsNone(chat.current_goal)

    async def test_cancellation_resistant_evaluator_cannot_be_reconciled_while_running(
        self,
    ) -> None:
        chat = self.chat()
        chat.create_goal(definition())
        chat.observe_goal_evidence = lambda goal: proof(goal, semantic="unavailable")
        chat.observe_goal_inputs = lambda: (WS, INPUTS)
        release = asyncio.Event()
        finished = asyncio.Event()

        async def evaluator(request: GoalEvaluationInput) -> GoalSemanticVerdict:
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            finished.set()
            return GoalSemanticVerdict(
                definition_sha256=request.definition_sha256,
                evidence_sha256=request.evidence_sha256,
                decision="passed",
                reason="Late completion cannot replace the timeout.",
            )

        chat.goal_evaluator = evaluator
        chat.goal_evaluator_timeout = 0.01
        result = await asyncio.wait_for(chat.evaluate_goal(), 1)
        self.assertEqual(result.status, "blocked")
        assert result.evaluating_sha256 is not None
        try:
            with self.assertRaisesRegex(ValueError, "active operation"):
                chat.reconcile_goal_operation(
                    "evaluate-" + result.evaluating_sha256[:16],
                    expected_definition=result.definition.sha256,
                    receipt_sha256=digest(b"reconciled"),
                    observed_ledger=ResourceLedger(),
                )
            with self.assertRaisesRegex(ValueError, "safe turn"):
                chat.check_goal()
        finally:
            release.set()
            await asyncio.wait_for(finished.wait(), 1)
            await asyncio.sleep(0)
        self.assertEqual(active(chat), result)

    async def test_evaluator_runtime_failure_retains_reserved_exposure(self) -> None:
        chat = self.chat()
        chat.create_goal(definition())
        chat.observe_goal_evidence = lambda goal: proof(goal, semantic="unavailable")
        chat.observe_goal_inputs = lambda: (WS, INPUTS)

        async def evaluator(_request: GoalEvaluationInput) -> GoalSemanticVerdict:
            raise RuntimeError("Adapter lost its connection.")

        chat.goal_evaluator = evaluator
        result = await chat.evaluate_goal()
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.ledger.uncertain_effects, 1)
        self.assertGreater(result.ledger.output_bytes, 0)
        self.assertIsNotNone(result.evaluating_sha256)
        self.assertIn("reserved", result.describe(chat.goal_clock()))

    async def test_unchanged_receipts_do_not_manufacture_progress(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        evidence = proof(goal, semantic="failed").model_copy(
            update={"failure_cause": "same failure"}
        )
        for _ in range(4):
            goal = decide(
                goal, 100, evidence, workspace_sha256=WS, inputs_sha256=INPUTS
            )
        self.assertEqual(goal.status, "stalled")
        self.assertEqual(goal.no_progress, 3)
        self.assertEqual(goal.repeated_failures, 4)
        changed = evidence.model_copy(update={"failure_cause": "different failure"})
        goal = decide(goal, 100, changed, workspace_sha256=WS, inputs_sha256=INPUTS)
        self.assertEqual(goal.repeated_failures, 1)
        self.assertEqual(goal.status, "stalled")

    async def test_job_reports_preserve_checkin_accounting(self) -> None:
        chat = self.chat()
        goal = chat.create_goal(definition())
        chat.register_goal_job(
            GoalJob(operation_id="tests"), expected_definition=goal.definition.sha256
        )
        chat.goal_clock = lambda: 160.0
        checked = chat.check_goal()
        self.assertEqual(checked.jobs[0].checkins, 1)
        report = checked.jobs[0].model_copy(
            update={"checkins": 0, "next_checkin_at": 0}
        )
        chat.report_goal_job(
            goal.goal_id, report, expected_definition=goal.definition.sha256
        )
        self.assertEqual(active(chat).jobs[0].checkins, 1)
        self.assertEqual(
            active(chat).jobs[0].next_checkin_at, checked.jobs[0].next_checkin_at
        )

    async def test_task_scoped_goals_require_and_retain_aggregate_usage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = self.chat(root)
            _, scope, _ = scoped_bundle(root)
            chat.task_scope = scope
            with self.assertRaisesRegex(ValueError, "aggregate ledger"):
                chat.create_goal(definition())
            chat.observe_goal_inputs = lambda: (WS, INPUTS)
            chat.observe_goal_evidence = lambda goal: proof(goal).model_copy(
                update={"task_ledger": ResourceLedger(attempts=5, input_bytes=1234)}
            )
            created = chat.create_goal(definition())
            self.assertEqual(created.ledger.attempts, 5)
            self.assertEqual(created.ledger.input_bytes, 1234)
            chat.goal_control("clear")
            again = chat.create_goal(definition())
            self.assertEqual(again.ledger, created.ledger)
            self.assertEqual(again.started_at, created.started_at)

    async def test_tui_and_plain_history_show_same_goal_details(self) -> None:
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        from mos_eisley.conversation_goal_commands import goal_command
        from mos_eisley.conversation_tui import ConversationTUI

        chat = self.chat()
        goal = chat.create_goal(definition())
        chat.check_goal()
        chat.goal_control("clear")
        events: list[dict[str, object]] = []
        goal_command(chat, "/goal history", events.append)
        event = events[-1]
        self.assertIn(goal.goal_id, str(event["text"]))
        self.assertIn("Attempts", str(event["text"]))
        self.assertIn("Remaining", str(event["text"]))
        with create_pipe_input() as pipe:
            ui = ConversationTUI(chat, input=pipe, output=DummyOutput())
            ui.emit(event)
            self.assertEqual(ui.context_preview, (chat.state.revision, event["text"]))
            self.assertIn(goal.definition.objective, ui.transcript.text)

    async def test_restart_preserves_running_author_and_evaluator_uncertainty(
        self,
    ) -> None:
        for evaluator_inflight in (False, True):
            chat = self.chat()
            chat.create_goal(definition())
            release = asyncio.Event()
            started = asyncio.Event()

            async def evaluator(
                request: GoalEvaluationInput,
                started: asyncio.Event = started,
                release: asyncio.Event = release,
            ) -> GoalSemanticVerdict:
                started.set()
                await release.wait()
                return GoalSemanticVerdict(
                    definition_sha256=request.definition_sha256,
                    evidence_sha256=request.evidence_sha256,
                    decision="passed",
                    reason="Only the original process may observe this response.",
                )

            if evaluator_inflight:
                chat.observe_goal_evidence = lambda goal: proof(
                    goal, semantic="unavailable"
                )
                chat.observe_goal_inputs = lambda: (WS, INPUTS)
                chat.goal_evaluator = evaluator
                task = asyncio.create_task(chat.evaluate_goal())
                await asyncio.wait_for(started.wait(), 2)
            else:
                waiting = WaitingClient()
                chat.submit("Work")
                task = asyncio.create_task(chat.step(waiting))
                await asyncio.wait_for(waiting.started.wait(), 2)
            saved = ConversationState.model_validate_json(chat.state.model_dump_json())
            recovered = ConversationController(
                saved, chat.cassette, lambda _: None, goal_clock=lambda: 100.0
            )
            goal = active(recovered)
            self.assertEqual(goal.status, "blocked")
            self.assertEqual(goal.ledger.uncertain_effects, 1)
            self.assertEqual(goal.ledger.attempts, 1)
            with self.assertRaises(ValueError):
                recovered.goal_control("resume")
            twice = ConversationController(
                recovered.state, chat.cassette, lambda _: None, goal_clock=lambda: 100.0
            )
            self.assertEqual(active(twice).ledger, goal.ledger)
            recovered.goal_control("clear")
            with self.assertRaisesRegex(ValueError, "in-flight"):
                recovered.create_goal(definition())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_clear_and_replacement_cannot_enlarge_task_budget(self) -> None:
        chat = self.chat()
        limited = definition().model_copy(
            update={"ceiling": definition().ceiling.model_copy(update={"attempts": 1})}
        )
        chat.create_goal(limited)
        chat.submit("One attempt")
        await chat.step(CapturingClient())
        chat.goal_control("clear")
        with self.assertRaisesRegex(ValueError, "enlarge retained"):
            chat.create_goal(definition())
        replacement = chat.create_goal(limited)
        self.assertEqual(replacement.status, "budget_exhausted")
        self.assertEqual(replacement.ledger.attempts, 1)

    async def test_reused_test_operation_cannot_inflate_work_unit_test_count(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = self.chat(root)
            goal = chat.create_goal(
                definition().model_copy(
                    update={
                        "verification_requirements": ("first", "second"),
                        "minimum_tests": 2,
                    }
                )
            )
            bundle, _scope, _payload = scoped_bundle(root)
            verification = bundle.checkpoint.verifications[0]
            payload = canonical_bytes(
                GoalTestReceipt(
                    operation_id="single-test-run",
                    executed_tests=1,
                    failed_tests=0,
                    workspace_sha256=verification.bound_workspace_sha256,
                    inputs_sha256=verification.bound_input_sha256,
                )
            )
            ref = ArtifactReference(
                artifact_id="tests",
                sha256=digest(payload),
                bytes=len(payload),
                media_type="application/json",
                availability="available",
                freshness="current",
            )
            checkpoint = bundle.checkpoint.model_copy(
                update={
                    "verifications": tuple(
                        verification.model_copy(
                            update={"verification_id": name, "result": ref}
                        )
                        for name in ("first", "second")
                    )
                }
            )
            with self.assertRaisesRegex(ValueError, "nonempty executed-test"):
                guard_goal_checkpoint(
                    goal,
                    bundle.model_copy(update={"checkpoint": checkpoint}),
                    {digest(payload): payload},
                )
