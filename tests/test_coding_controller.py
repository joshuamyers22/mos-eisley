"""Explicit creator plan/test review, coding handoff and integration lifecycle."""

import asyncio
import subprocess
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import IsolatedAsyncioTestCase

from test_coding_vcs import good_patch, make_brief

from mos_eisley.coding_child import (
    CodeSnapshot,
    CodingBrief,
    CodingIntegrationApproval,
    CodingPatch,
    CodingReview,
    CodingVerification,
)
from mos_eisley.conversation import ConversationController, prepare_conversation_request
from mos_eisley.conversation_agents import AgentInspectionScope
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_goal import GoalDefinition
from mos_eisley.conversation_local_child import (
    LocalChildAuthorization,
    LocalChildRecord,
)
from mos_eisley.conversation_state import ConversationState
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn, Usage
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.coding_child import (
    CodingExecution,
    CodingJob,
    coding_config,
    replay_coding,
)
from mos_eisley.run.coding_child_worker import verify_snapshot
from mos_eisley.run.coding_vcs import CodingVCS
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore

IMAGE = "sha256:" + "1" * 64


def cassette_for(brief: CodingBrief, patch: CodingPatch) -> AgentCassette:
    request, _ = prepare_conversation_request(coding_config(brief))
    text = canonical_bytes(patch).decode()
    response = demo_cassette().exchanges[0].response
    assert response is not None
    response = response.model_copy(
        update={
            "turn": Turn(role="assistant", blocks=(TextBlock(text=text),)),
            "usage": Usage(
                input=len(canonical_bytes(request)),
                output=len(text.encode()),
                unit="bytes",
            ),
        }
    )
    return AgentCassette(
        exchanges=(
            AgentExchange(
                request_sha256=digest(canonical_bytes(request)), response=response
            ),
        )
    )


def review_for(brief: CodingBrief, patch: CodingPatch | None) -> CodingReview:
    return CodingReview(
        brief_sha256=brief.sha256,
        plan_sha256=brief.assignment.plan_sha256,
        tests_sha256=brief.assignment.tests_sha256,
        phase="plan_tests" if patch is None else "final",
        patch_sha256=None if patch is None else patch.sha256,
        critic_sha256=digest(b"Fixture independent critic"),
        judge_sha256=digest(b"Fixture independent judge"),
        decision="accept",
    )


class FixtureCodingExecutor:
    image_id = IMAGE

    def __init__(self) -> None:
        self.calls = 0
        self.verifications = 0
        self.started = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.fail = False
        self.fail_final = False

    async def execute(self, job: CodingJob) -> CodingExecution:
        self.calls += 1
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.fail:
            raise OSError("Lost worker acknowledgement")
        execution = await replay_coding(job, self.image_id)
        patch = CodingPatch.model_validate_json(execution.result.final_text)
        verification = await verify_snapshot(job.brief, patch.apply(job.brief))
        return CodingExecution(
            execution=execution, patch=patch, verification=verification
        )

    async def verify(
        self, brief: CodingBrief, snapshot: CodeSnapshot
    ) -> CodingVerification:
        self.verifications += 1
        verification = await verify_snapshot(brief, snapshot)
        return (
            verification.model_copy(update={"passed": False})
            if self.fail_final and self.verifications == 2
            else verification
        )


class HeldCodingBroker(CodingVCS):
    def __init__(self, git: Path, workspace: Path, staging_root: Path):
        super().__init__(git, workspace, staging_root)
        self.hold = False
        self.started = Event()
        self.cleaned = Event()

    def run_operation[T](
        self, operation: Callable[[], T], wall_seconds: int, cancelled: Event
    ) -> T:
        if self.hold:
            self.started.set()
            if not cancelled.wait(wall_seconds):
                raise TimeoutError("Held broker operation timed out.")
            self.cleaned.set()
            raise InterruptedError("Exact broker cleanup completed.")
        return super().run_operation(operation, wall_seconds, cancelled)


class CodingControllerTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        (self.repo / "adder.py").write_text("def add(a,b):\n    return 0\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_adder.py").write_text(
            "import unittest\nfrom adder import add\n"
            "class Tests(unittest.TestCase):\n    def test_add(self):\n"
            "        self.assertEqual(add(2,3),5)\n"
            "        self.assertEqual(add(-4,1),-3)\n"
        )
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Creator tests first",
        )
        self.broker = CodingVCS(Path("/usr/bin/git"), self.repo, self.root / "staging")
        self.executor = FixtureCodingExecutor()
        self.approved = True
        self.integration_approved = True
        self.reject_review = False
        self.events: list[str] = []
        self.saved: list[ConversationState] = []
        self.chat = self.new_chat(save=self.saved.append)
        self.saved.append(self.chat.state)
        self.chat.create_goal(
            GoalDefinition(
                objective="Implement addition",
                success_criteria=("Positive and negative tests pass",),
                remaining_work=("Delegate and integrate addition",),
            )
        )
        commit, snapshot = self.broker.snapshot(("adder.py", "tests/test_adder.py"))
        self.brief = make_brief(
            self.repo, self.root / "staging/child", commit, snapshot
        )
        goal = self.chat.current_goal
        assert goal is not None
        self.brief = self.brief.model_copy(
            update={
                "assignment": self.brief.assignment.model_copy(
                    update={"parent_task_id": goal.goal_id}
                )
            }
        )

    async def asyncTearDown(self) -> None:
        await self.chat.stop_local_child()
        self.broker.close()
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return (
            subprocess.check_output(["git", "-C", str(self.repo), *args])
            .decode()
            .strip()
        )

    def new_chat(
        self,
        state: ConversationState | None = None,
        save: Callable[[ConversationState], None] = lambda _: None,
    ) -> ConversationController[ConversationState]:
        cassette = demo_cassette()
        return ConversationController(
            state or ConversationController.fresh(self.repo, cassette),
            cassette,
            save,
            goal_clock=lambda: 100.0,
            coding_authorizer=self.authorize,
            coding_reviewer=self.review,
            coding_executor=self.executor,
            coding_broker=self.broker,
            coding_integration_authorizer=self.authorize_integration,
        )

    def review(self, brief: CodingBrief, patch: CodingPatch | None) -> CodingReview:
        self.events.append("plan_review" if patch is None else "final_review")
        return (
            review_for(brief, patch).model_copy(update={"decision": "reject"})
            if self.reject_review
            else review_for(brief, patch)
        )

    def authorize(
        self, brief: CodingBrief, scope: AgentInspectionScope
    ) -> LocalChildAuthorization:
        self.events.append("creator_approval")
        if not self.approved:
            raise ValueError("Creator revoked the exact assignment")
        return LocalChildAuthorization(
            scope=scope,
            assignment_sha256=brief.assignment.sha256,
            workspace_observation_sha256=self.chat.observe_branch_workspace(
                str(self.repo)
            ),
            expires_at=500.0,
            mode="recorded_coding",
            brief_sha256=brief.sha256,
            review_sha256=digest(canonical_bytes(review_for(brief, None))),
        )

    def authorize_integration(
        self, record: LocalChildRecord, review: CodingReview
    ) -> CodingIntegrationApproval:
        self.events.append("integration_approval")
        if not self.integration_approved:
            raise ValueError("Creator has not approved integration")
        assert record.coding is not None and record.coding.handoff is not None
        return CodingIntegrationApproval(
            owner_uid=self.chat.state.owner_uid,
            parent_session_id=self.chat.state.session_id,
            child_id=record.child_id,
            handoff_sha256=digest(canonical_bytes(record.coding.handoff)),
            review_sha256=digest(canonical_bytes(review)),
            expires_at=500.0,
        )

    async def run_child(self, patch: CodingPatch | None = None):
        return await self.chat.run_coding_child(
            self.brief,
            cassette_for(self.brief, patch or good_patch(self.brief)),
            expected_revision=self.chat.state.revision,
        )

    async def test_plan_review_precedes_approval_reservation_precedes_dispatch(
        self,
    ) -> None:
        self.executor.release = asyncio.Event()
        task = asyncio.create_task(self.run_child())
        await self.executor.started.wait()
        self.assertEqual(self.events[:2], ["plan_review", "creator_approval"])
        self.assertEqual(self.chat.state.local_children[0].state, "running")
        assert self.chat.current_goal is not None
        self.assertEqual(self.chat.current_goal.ledger.attempts, 1)
        with self.assertRaises(ValueError):
            await self.run_child()
        self.executor.release.set()
        report = await task
        self.assertFalse(report.integration_approved)
        self.assertIn("return 0", (self.repo / "adder.py").read_text())
        view = self.chat.inspect_agents(report.child_id)
        self.assertEqual(view.report_status, "available")
        self.assertEqual(view.snapshot.children[0].verification, "passed")

    async def test_creator_approved_integration_and_fresh_final_tests(self) -> None:
        report = await self.run_child()
        commit = await self.chat.integrate_coding_child(
            report.child_id, expected_revision=self.chat.state.revision
        )
        self.assertEqual(self.git("rev-parse", "HEAD"), commit)
        self.assertEqual(self.executor.verifications, 2)
        record = self.chat.state.local_children[0]
        assert record.coding is not None and self.chat.current_goal is not None
        self.assertEqual(record.coding.integration_state, "integrated")
        self.assertEqual(self.chat.current_goal.ledger.attempts, 2)
        self.assertEqual(self.chat.current_goal.ledger.uncertain_effects, 0)
        with self.assertRaises(ValueError):
            await self.chat.integrate_coding_child(
                report.child_id, expected_revision=self.chat.state.revision
            )

    async def test_rejected_review_or_creator_approval_dispatches_nothing(self) -> None:
        self.reject_review = True
        with self.assertRaises(ValueError):
            await self.run_child()
        self.reject_review = False
        self.approved = False
        with self.assertRaises(ValueError):
            await self.run_child()
        self.assertEqual(self.executor.calls, 0)
        self.assertEqual(self.chat.state.local_children, ())

    async def test_protected_tests_and_stale_plan_rejected_before_dispatch(
        self,
    ) -> None:
        for brief in (
            self.brief.model_copy(update={"owned_paths": ("tests/test_adder.py",)}),
            self.brief.model_copy(update={"plan": "changed"}),
            self.brief.model_copy(update={"depth": 2}),
        ):
            with self.assertRaises(ValueError):
                await self.chat.run_coding_child(
                    brief,
                    cassette_for(self.brief, good_patch(self.brief)),
                    expected_revision=self.chat.state.revision,
                )
        self.assertEqual(self.executor.calls, 0)

    async def test_failed_tests_cannot_integrate(self) -> None:
        patch = good_patch(self.brief)
        change = patch.changes[0]
        patch = patch.model_copy(
            update={
                "changes": (
                    change.model_copy(
                        update={
                            "file": change.file.model_copy(
                                update={"content": "def add(a,b):\n    return a-b\n"}
                            )
                        }
                    ),
                )
            }
        )
        report = await self.run_child(patch)
        with self.assertRaises(ValueError):
            await self.chat.integrate_coding_child(
                report.child_id, expected_revision=self.chat.state.revision
            )
        self.assertIn("return 0", (self.repo / "adder.py").read_text())

    async def test_revoked_integration_approval_does_not_modify_parent(self) -> None:
        report = await self.run_child()
        self.integration_approved = False
        with self.assertRaises(ValueError):
            await self.chat.integrate_coding_child(
                report.child_id, expected_revision=self.chat.state.revision
            )
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)
        assert self.chat.state.local_children[0].coding is not None
        self.assertEqual(
            self.chat.state.local_children[0].coding.integration_state, "pending"
        )

    async def test_cancel_preserves_parent_terminal_state_and_uncertainty_once(
        self,
    ) -> None:
        self.executor.release = asyncio.Event()
        task = asyncio.create_task(self.run_child())
        await self.executor.started.wait()
        self.chat.goal_control("cancel")
        with self.assertRaises(asyncio.CancelledError):
            await task
        assert self.chat.current_goal is not None
        self.assertEqual(self.chat.current_goal.status, "cancelled")
        self.assertEqual(self.chat.current_goal.ledger.uncertain_effects, 1)
        resumed = self.new_chat(self.chat.state)
        assert resumed.current_goal is not None
        self.assertEqual(resumed.current_goal.ledger.uncertain_effects, 1)
        self.assertEqual(self.executor.calls, 1)

    async def test_running_restart_retains_charges_and_never_replays(self) -> None:
        self.executor.release = asyncio.Event()
        task = asyncio.create_task(self.run_child())
        await self.executor.started.wait()
        snapshot = self.chat.state
        await self.chat.stop_local_child()
        with self.assertRaises(asyncio.CancelledError):
            await task
        resumed = self.new_chat(snapshot)
        assert resumed.current_goal is not None
        self.assertEqual(resumed.current_goal.status, "paused")
        self.assertEqual(resumed.current_goal.ledger.attempts, 1)
        self.assertEqual(resumed.current_goal.ledger.uncertain_effects, 1)
        self.assertEqual(self.executor.calls, 1)

    async def test_store_failure_before_dispatch_issues_no_execution(self) -> None:
        def broken(_: ConversationState) -> None:
            raise OSError("Store failed")

        chat = self.new_chat(self.chat.state, broken)
        with self.assertRaises(OSError):
            await chat.run_coding_child(
                self.brief,
                cassette_for(self.brief, good_patch(self.brief)),
                expected_revision=chat.state.revision,
            )
        self.assertEqual(self.executor.calls, 0)

    async def test_final_verification_failure_retains_uncertain_integrated_tree(
        self,
    ) -> None:
        report = await self.run_child()
        self.executor.fail_final = True
        with self.assertRaises(ValueError):
            await self.chat.integrate_coding_child(
                report.child_id, expected_revision=self.chat.state.revision
            )
        assert (
            self.chat.current_goal is not None
            and self.chat.state.local_children[0].coding is not None
        )
        self.assertEqual(self.chat.current_goal.status, "paused")
        self.assertEqual(self.chat.current_goal.ledger.uncertain_effects, 1)
        self.assertEqual(
            self.chat.state.local_children[0].coding.integration_state, "uncertain"
        )
        self.assertIn("return a + b", (self.repo / "adder.py").read_text())
        self.new_chat(self.chat.state)
        self.assertEqual(self.chat.current_goal.ledger.uncertain_effects, 1)

    async def test_both_stores_retain_coding_without_executor_or_replay(self) -> None:
        await self.run_child()
        for backend in (ConversationStore, SQLiteConversationStore):
            with backend(
                self.root / backend.__name__, self.chat.state.session_id, self.repo
            ) as store:
                for state in self.saved:
                    store.save(state)
                loaded = store.load()
                resumed = ConversationController(
                    loaded, demo_cassette(), store.save, goal_clock=lambda: 100.0
                )
                self.assertEqual(
                    resumed.state.local_children[0].coding,
                    self.chat.state.local_children[0].coding,
                )
                self.assertEqual(
                    resumed.inspect_agents(
                        self.chat.state.local_children[0].child_id
                    ).report_status,
                    "stale",
                )
        self.assertEqual(self.executor.calls, 1)

    async def test_pending_or_failed_handoff_has_required_unpassed_integration_job(
        self,
    ) -> None:
        await self.run_child()
        assert self.chat.current_goal is not None
        job = next(
            j
            for j in self.chat.current_goal.jobs
            if j.operation_id.endswith("-integration")
        )
        self.assertTrue(job.required)
        self.assertEqual(job.state, "running")
        self.assertIsNone(job.result_sha256)

    async def test_integrating_restart_retains_uncertainty_once(self) -> None:
        await self.run_child()
        record = self.chat.state.local_children[0]
        assert record.coding is not None and record.coding.handoff is not None
        coding = record.coding.model_copy(
            update={
                "integration_state": "integrating",
                "final_review": review_for(self.brief, record.coding.handoff.patch),
            }
        )
        running = self.chat.state.model_copy(
            update={"local_children": (record.model_copy(update={"coding": coding}),)}
        )
        resumed = self.new_chat(running)
        assert resumed.current_goal is not None
        self.assertEqual(resumed.current_goal.status, "paused")
        self.assertEqual(resumed.current_goal.ledger.uncertain_effects, 1)
        twice = self.new_chat(resumed.state)
        assert twice.current_goal is not None
        self.assertEqual(twice.current_goal.ledger.uncertain_effects, 1)
        self.assertEqual(self.executor.calls, 1)

    async def test_stage_cancellation_awaits_exact_vcs_cleanup(self) -> None:
        held = HeldCodingBroker(Path("/usr/bin/git"), self.repo, self.root / "staging")
        held.hold = True
        self.chat.coding_broker = held
        task = asyncio.create_task(self.run_child())
        self.assertTrue(await asyncio.to_thread(held.started.wait, 5))
        self.chat.goal_control("cancel")
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(held.cleaned.is_set())
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)
        assert self.chat.current_goal is not None
        self.assertEqual(self.chat.current_goal.status, "cancelled")
        self.assertEqual(self.chat.current_goal.ledger.uncertain_effects, 1)
        held.close()

    async def test_expired_or_too_small_allowance_dispatches_nothing(self) -> None:
        tiny = self.brief.model_copy(
            update={
                "assignment": self.brief.assignment.model_copy(
                    update={
                        "allowance": self.brief.assignment.allowance.model_copy(
                            update={"input_bytes": 1}
                        )
                    }
                )
            }
        )
        with self.assertRaises(ValueError):
            await self.chat.run_coding_child(
                tiny,
                cassette_for(tiny, good_patch(tiny)),
                expected_revision=self.chat.state.revision,
            )
        self.chat.goal_clock = lambda: 1000.0
        with self.assertRaises(ValueError):
            await self.run_child()
        self.assertEqual(self.executor.calls, 0)
        self.assertEqual(self.chat.state.local_children, ())

    async def test_waiting_goal_can_integrate_its_current_reviewed_child(self) -> None:
        report = await self.run_child()
        self.chat.check_goal()
        assert self.chat.current_goal is not None
        self.assertEqual(self.chat.current_goal.status, "waiting")
        commit = await self.chat.integrate_coding_child(
            report.child_id, expected_revision=self.chat.state.revision
        )
        self.assertEqual(self.git("rev-parse", "HEAD"), commit)

    async def test_pending_integration_watchdog_retains_stuck_state(self) -> None:
        report = await self.run_child()
        self.chat.check_goal()
        for now in (140.0, 230.0, 500.0):
            self.chat.goal_clock = lambda now=now: now
            self.chat.check_goal()
        assert self.chat.current_goal is not None
        job = next(
            j
            for j in self.chat.current_goal.jobs
            if j.operation_id.endswith("-integration")
        )
        self.assertEqual(job.state, "stuck")
        with self.assertRaises(ValueError):
            await self.chat.integrate_coding_child(
                report.child_id, expected_revision=self.chat.state.revision
            )
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)

    async def test_queued_user_input_keeps_priority_over_coding_admission(self) -> None:
        self.chat.submit("Check the plan before implementation.")
        with self.assertRaises(ValueError):
            await self.run_child()
        self.assertEqual(self.executor.calls, 0)
        self.assertEqual(self.chat.state.local_children, ())
