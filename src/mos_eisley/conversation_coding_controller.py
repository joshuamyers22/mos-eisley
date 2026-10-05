"""Creator-approved, one-level recorded coding and separately approved integration."""

import asyncio
import math
import os
from collections.abc import Callable
from contextlib import suppress
from threading import Event
from typing import Protocol
from uuid import uuid4

from mos_eisley.coding_child import (
    CodeSnapshot,
    CodingBrief,
    CodingHandoff,
    CodingIntegrationApproval,
    CodingPatch,
    CodingRetention,
    CodingReview,
)
from mos_eisley.conversation_agents import AgentInspectionScope, ImplementationReport
from mos_eisley.conversation_goal import DurableGoal, GoalJob, exhausted
from mos_eisley.conversation_goal_controller import StateT
from mos_eisley.conversation_local_child import (
    LocalChildAuthorization,
    LocalChildExecution,
    LocalChildRecord,
)
from mos_eisley.conversation_local_child_controller import (
    ConversationLocalChildController,
)
from mos_eisley.core.agent import check_request_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.coding_child import (
    CodingExecution,
    CodingExecutor,
    CodingJob,
    coding_config,
)
from mos_eisley.task_state import ResourceLedger


class CodingBroker(Protocol):
    def run_operation[T](
        self, operation: Callable[[], T], wall_seconds: int, cancelled: Event
    ) -> T: ...
    def stage(self, brief: CodingBrief, patch: CodingPatch) -> str: ...
    def integrate(
        self, brief: CodingBrief, patch: CodingPatch, expected_diff_sha: str
    ) -> str: ...
    def integrated_snapshot(
        self, brief: CodingBrief, patch: CodingPatch, commit: str
    ) -> CodeSnapshot: ...
    def close(self) -> None: ...


CodingAuthorizer = Callable[
    [CodingBrief, AgentInspectionScope], LocalChildAuthorization
]
CodingReviewer = Callable[[CodingBrief, CodingPatch | None], CodingReview]
IntegrationAuthorizer = Callable[
    [LocalChildRecord, CodingReview], CodingIntegrationApproval
]


class ConversationCodingController(ConversationLocalChildController[StateT]):
    coding_authorizer: CodingAuthorizer | None
    coding_reviewer: CodingReviewer | None
    coding_executor: CodingExecutor | None
    coding_broker: CodingBroker | None
    coding_integration_authorizer: IntegrationAuthorizer | None

    async def _run_coding_vcs[T](
        self, operation: Callable[[], T], wall_seconds: int
    ) -> T:
        assert self.coding_broker is not None
        cancelled = Event()
        future = asyncio.create_task(
            asyncio.to_thread(
                self.coding_broker.run_operation, operation, wall_seconds, cancelled
            )
        )
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled.set()
            # Exact cleanup completes before parent cancellation is acknowledged.
            while not future.done():
                try:
                    await asyncio.shield(future)
                except asyncio.CancelledError:
                    cancelled.set()
                except Exception:
                    break
            with suppress(Exception, asyncio.CancelledError):
                future.result()
            raise

    def _commit_children(
        self, children: tuple[LocalChildRecord, ...], goals: tuple[DurableGoal, ...]
    ) -> None:
        updated_goals: list[DurableGoal] = []
        for goal in goals:
            jobs = list(goal.jobs)
            for child in children:
                coding = child.coding
                if coding is None or child.assignment.parent_task_id != goal.goal_id:
                    continue
                operation_id = child.child_id + "-integration"
                existing = next(
                    (j for j in jobs if j.operation_id == operation_id), None
                )
                job = existing or GoalJob(
                    operation_id=operation_id,
                    definition_sha256=child.goal_definition_sha256,
                    checkin_seconds=30,
                    next_checkin_at=self.goal_clock() + 30,
                )
                state = (
                    "stuck"
                    if existing is not None and existing.state == "stuck"
                    else "running"
                )
                receipt = None
                if (
                    child.state in {"cancelled", "uncertain"}
                    or coding.integration_state == "uncertain"
                ):
                    state = "uncertain"
                elif coding.integration_state == "integrated":
                    state = "passed"
                    receipt = digest(canonical_bytes(coding))
                elif (
                    coding.handoff is not None
                    and not coding.handoff.verification.passed
                ):
                    state = "failed"
                job = job.model_copy(update={"state": state, "result_sha256": receipt})
                jobs = [j for j in jobs if j.operation_id != operation_id]
                jobs.append(job)
            updated_goals.append(goal.model_copy(update={"jobs": tuple(jobs)}))
        super()._commit_children(children, tuple(updated_goals))

    def coding_authorization(
        self, brief: CodingBrief, review: CodingReview
    ) -> LocalChildAuthorization:
        review.require(brief)
        if (
            self.coding_authorizer is None
            or self.coding_executor is None
            or self.coding_broker is None
            or self.coding_reviewer is None
            or self.task_scope is not None
            or self.state.branch_budget is not None
            or self.state.owner_uid != os.getuid()
            or brief.assignment.workspace != self.state.workspace
        ):
            raise ValueError(
                "Coding requires complete local host adapters and owner scope."
            )
        approval = self.coding_authorizer(brief, self.child_scope())
        approval = LocalChildAuthorization.model_validate_json(
            approval.model_dump_json()
        )
        now = self.goal_clock()
        if (
            not math.isfinite(now)
            or now < 0
            or approval.expires_at <= now
            or approval.scope != self.child_scope()
            or approval.assignment_sha256 != brief.assignment.sha256
            or approval.mode != "recorded_coding"
            or approval.brief_sha256 != brief.sha256
            or approval.review_sha256 != digest(canonical_bytes(review))
            or approval.workspace_observation_sha256
            != self.observe_branch_workspace(self.state.workspace)
        ):
            raise ValueError(
                "Coding approval differs from the current reviewed assignment."
            )
        return approval

    def record_authorization(self, record: LocalChildRecord) -> LocalChildAuthorization:
        if record.coding is None:
            return super().record_authorization(record)
        return self.coding_authorization(record.coding.brief, record.coding.plan_review)

    def _coding_record(self, child_id: str) -> LocalChildRecord:
        record = next(
            (r for r in self.state.local_children if r.child_id == child_id), None
        )
        if record is None or record.coding is None:
            raise ValueError(
                "Coding child is outside this owner-scoped retained workflow."
            )
        return record

    def _update_coding_record(self, record: LocalChildRecord) -> None:
        self._commit_children(
            tuple(
                record if r.child_id == record.child_id else r
                for r in self.state.local_children
            ),
            self.state.goals,
        )

    async def run_coding_child(
        self, brief: CodingBrief, cassette: AgentCassette, *, expected_revision: int
    ) -> ImplementationReport:
        from mos_eisley.conversation import prepare_conversation_request

        brief = CodingBrief.model_validate_json(brief.model_dump_json())
        goal = self.current_goal
        if (
            self.state.revision != expected_revision
            or goal is None
            or goal.status != "working"
            or brief.assignment.parent_task_id != goal.goal_id
            or self.schedule_boundary_busy
            or self._local_child_task is not None
            or goal.reservations
            or goal.evaluating_sha256
            or len(self.state.local_children) >= 4
            or any(
                c.state != "completed"
                or (
                    c.coding is not None
                    and c.coding.integration_state in {"integrating", "uncertain"}
                )
                for c in self.state.local_children
            )
        ):
            raise ValueError(
                "Coding admission requires a safe current working-goal boundary."
            )
        if self.coding_reviewer is None:
            raise ValueError("Trusted plan/test review must precede creator approval.")
        review = self.coding_reviewer(brief, None)
        review = CodingReview.model_validate_json(review.model_dump_json())
        approval = self.coding_authorization(brief, review)
        job = CodingJob(brief=brief, cassette=cassette)
        request, budget = prepare_conversation_request(coding_config(brief))
        reserved = ResourceLedger(
            input_bytes=check_request_budget(request, budget),
            output_bytes=budget.output_reserve,
            attempts=1,
        )
        if (
            cassette.exchanges[0].request_sha256 != digest(canonical_bytes(request))
            or any(
                getattr(reserved, f) > getattr(brief.assignment.allowance, f)
                or getattr(brief.assignment.allowance, f)
                > getattr(goal.definition.ceiling, f)
                for f in type(brief.assignment.allowance).model_fields
            )
            or exhausted(
                goal,
                self.goal_clock(),
                input_bytes=reserved.input_bytes,
                output_bytes=reserved.output_bytes,
                attempts=1,
            )
        ):
            raise ValueError(
                "Coding recording or cumulative allowance does not fit the parent goal."
            )
        assert self.coding_executor is not None and self.coding_broker is not None
        executor = self.coding_executor
        record = LocalChildRecord(
            child_id="coding-" + uuid4().hex,
            authorization=approval,
            assignment=brief.assignment,
            goal_definition_sha256=goal.definition.sha256,
            request_sha256=digest(canonical_bytes(request)),
            cassette_sha256=digest(canonical_bytes(cassette)),
            image_id=executor.image_id,
            reserved=reserved,
            coding=CodingRetention(brief=brief, plan_review=review),
        )
        updated = goal.model_copy(
            update={
                "ledger": goal.ledger.model_copy(
                    update={
                        f: getattr(goal.ledger, f) + getattr(reserved, f)
                        for f in ResourceLedger.model_fields
                    }
                ),
                "jobs": (
                    *goal.jobs,
                    GoalJob(
                        operation_id=record.child_id,
                        definition_sha256=goal.definition.sha256,
                        checkin_seconds=30,
                        next_checkin_at=self.goal_clock() + 30,
                    ),
                ),
            }
        )
        self._commit_children(
            (*self.state.local_children, record),
            tuple(updated if g == goal else g for g in self.state.goals),
        )
        task = asyncio.current_task()
        assert task is not None
        self._local_child_task = task
        self._cancel_local_child = task.cancel
        self._busy = True
        try:
            self._require_current(record)
            if self.coding_authorization(brief, review) != approval:
                raise ValueError("Coding approval changed before dispatch.")
            async with asyncio.timeout(brief.wall_seconds + 5):
                result = await executor.execute(job)
            result = CodingExecution.model_validate_json(result.model_dump_json())
            execution = LocalChildExecution.model_validate_json(
                result.execution.model_dump_json()
            )
            usage = execution.result.usage
            snapshot = result.patch.apply(brief)
            if (
                execution.image_id != record.image_id
                or execution.events[0].payload_sha256 != record.request_sha256
                or CodingPatch.model_validate_json(execution.result.final_text)
                != result.patch
                or usage.unit != "bytes"
                or usage.requests != 1
                or usage.tools
                or usage.largest_request != reserved.input_bytes
                or usage.billed_input > reserved.input_bytes
                or usage.billed_output > reserved.output_bytes
                or result.verification.snapshot_sha256 != snapshot.sha256
                or result.verification.tests_sha256 != brief.assignment.tests_sha256
            ):
                raise ValueError(
                    "Coding execution differs from its patch, request or resources."
                )
            self._require_current(record)
            broker = self.coding_broker
            diff = await self._run_coding_vcs(
                lambda: broker.stage(brief, result.patch), brief.wall_seconds
            )
            self._require_current(record)
            handoff = CodingHandoff(
                patch=result.patch, verification=result.verification, diff=diff
            )
            report = ImplementationReport(
                scope=approval.scope,
                child_id=record.child_id,
                report_id=record.child_id + "-report",
                assignment_sha256=brief.assignment.sha256,
                summary=result.patch.summary,
                evidence=(
                    "Patch " + result.patch.sha256,
                    "Protected tests " + brief.assignment.tests_sha256,
                    "Verification " + digest(canonical_bytes(result.verification)),
                ),
                unresolved=()
                if result.verification.passed
                else ("Creator tests failed; integration is blocked.",),
                complete=True,
            )
            record = record.model_copy(
                update={
                    "state": "completed",
                    "report": report,
                    "execution_sha256": digest(canonical_bytes(result)),
                    "usage": ResourceLedger(
                        input_bytes=usage.billed_input,
                        output_bytes=usage.billed_output,
                        attempts=1,
                    ),
                    "coding": record.coding.model_copy(update={"handoff": handoff})
                    if record.coding
                    else None,
                }
            )
            self._finish_child(record)
            return report
        except BaseException as error:
            if not self.persistence_broken:
                self._finish_child(
                    record.model_copy(
                        update={
                            "state": "cancelled"
                            if isinstance(error, asyncio.CancelledError)
                            else "uncertain",
                            "report": None,
                            "execution_sha256": None,
                            "usage": None,
                        }
                    )
                )
            raise
        finally:
            self._busy = False
            self._local_child_task = None
            self._cancel_local_child = None

    def _require_current(
        self, record: LocalChildRecord, *, allow_waiting: bool = False
    ) -> None:
        goal = self.current_goal
        if (
            self.record_authorization(record) != record.authorization
            or goal is None
            or goal.status
            not in ({"working", "waiting"} if allow_waiting else {"working"})
            or goal.goal_id != record.assignment.parent_task_id
            or goal.definition.sha256 != record.goal_definition_sha256
            or exhausted(goal, self.goal_clock())
        ):
            raise ValueError("Coding goal, source tree or creator approval changed.")

    async def integrate_coding_child(
        self, child_id: str, *, expected_revision: int
    ) -> str:
        record = self._coding_record(child_id)
        coding = record.coding
        assert coding is not None
        if (
            expected_revision != self.state.revision
            or record.state != "completed"
            or coding.handoff is None
            or not coding.handoff.verification.passed
            or coding.integration_state != "pending"
            or self._local_child_task is not None
            or self.schedule_boundary_busy
            or self.coding_reviewer is None
            or self.coding_integration_authorizer is None
        ):
            raise ValueError("Integration needs a passing patch and creator approval.")
        self._require_current(record, allow_waiting=True)
        goal = self.current_goal
        assert goal is not None
        if any(
            j.required and j.state in {"stuck", "failed", "uncertain"}
            for j in goal.jobs
        ):
            raise ValueError("Resolve blocked required work before coding integration.")
        review = self.coding_reviewer(coding.brief, coding.handoff.patch)
        review = CodingReview.model_validate_json(review.model_dump_json())
        review.require(coding.brief, coding.handoff.patch)
        handoff = coding.handoff
        approval = self.coding_integration_authorizer(record, review)
        approval = CodingIntegrationApproval.model_validate_json(
            approval.model_dump_json()
        )

        def require_integration() -> None:
            now = self.goal_clock()
            if (
                not math.isfinite(now)
                or now < 0
                or approval.expires_at <= now
                or approval.owner_uid != self.state.owner_uid
                or approval.parent_session_id != self.state.session_id
                or approval.child_id != child_id
                or approval.handoff_sha256 != digest(canonical_bytes(handoff))
                or approval.review_sha256 != digest(canonical_bytes(review))
                or self.coding_integration_authorizer is None
                or self.coding_integration_authorizer(record, review) != approval
            ):
                raise ValueError(
                    "Integration approval is stale or differs from the reviewed patch."
                )

        require_integration()
        assert self.coding_executor is not None and self.coding_broker is not None
        goal = self.current_goal
        assert goal is not None
        # Integration/test work is another conservatively charged task attempt.
        if exhausted(goal, self.goal_clock(), attempts=1):
            raise ValueError("Integration exceeds the aggregate task budget.")
        pending = coding.model_copy(
            update={"final_review": review, "integration_state": "integrating"}
        )
        record = record.model_copy(update={"coding": pending})
        updated_goal = goal.model_copy(
            update={
                "ledger": goal.ledger.model_copy(
                    update={"attempts": goal.ledger.attempts + 1}
                )
            }
        )
        self._commit_children(
            tuple(
                record if r.child_id == child_id else r
                for r in self.state.local_children
            ),
            tuple(updated_goal if g == goal else g for g in self.state.goals),
        )
        task = asyncio.current_task()
        assert task is not None
        self._local_child_task = task
        self._cancel_local_child = task.cancel
        self._busy = True
        try:
            snapshot = coding.handoff.patch.apply(coding.brief)
            async with asyncio.timeout(coding.brief.wall_seconds + 5):
                verified = await self.coding_executor.verify(coding.brief, snapshot)
            if (
                not verified.passed
                or verified.snapshot_sha256 != snapshot.sha256
                or verified.tests_sha256 != coding.brief.assignment.tests_sha256
            ):
                raise ValueError("Final full creator tests failed or changed.")
            self._require_current(record, allow_waiting=True)
            require_integration()
            broker = self.coding_broker
            commit = await self._run_coding_vcs(
                lambda: broker.integrate(
                    coding.brief, handoff.patch, digest(handoff.diff.encode())
                ),
                coding.brief.wall_seconds,
            )
            pending = pending.model_copy(update={"applied_commit": commit})
            record = record.model_copy(update={"coding": pending})
            self._update_coding_record(record)
            # Recheck actual integrated sources in a fresh isolated verifier.
            async with asyncio.timeout(coding.brief.wall_seconds + 5):
                integrated = await self._run_coding_vcs(
                    lambda: broker.integrated_snapshot(
                        coding.brief, handoff.patch, commit
                    ),
                    coding.brief.wall_seconds,
                )
                if integrated != snapshot:
                    raise ValueError(
                        "Integrated source differs from the reviewed patch."
                    )
                final = await self.coding_executor.verify(coding.brief, integrated)
            if (
                not final.passed
                or final.snapshot_sha256 != snapshot.sha256
                or final.tests_sha256 != coding.brief.assignment.tests_sha256
            ):
                raise ValueError(
                    "Post-integration verification failed; integration is uncertain."
                )
            record = record.model_copy(
                update={
                    "coding": pending.model_copy(
                        update={
                            "integration_state": "integrated",
                            "integrated_commit": commit,
                            "final_verification": final,
                        }
                    )
                }
            )
            self._update_coding_record(record)
            return commit
        except BaseException:
            if not self.persistence_broken:
                self._mark_integration_uncertain(record)
            raise
        finally:
            self._busy = False
            self._local_child_task = None
            self._cancel_local_child = None

    def _mark_integration_uncertain(self, record: LocalChildRecord) -> None:
        assert record.coding is not None
        changed = record.model_copy(
            update={
                "coding": record.coding.model_copy(
                    update={"integration_state": "uncertain"}
                )
            }
        )
        goals = tuple(
            g.model_copy(
                update={
                    "status": "paused"
                    if g.status in {"working", "waiting"}
                    else g.status,
                    "ledger": g.ledger.model_copy(
                        update={"uncertain_effects": g.ledger.uncertain_effects + 1}
                    ),
                }
            )
            if g.goal_id == record.assignment.parent_task_id
            else g
            for g in self.state.goals
        )
        self._commit_children(
            tuple(
                changed if r.child_id == record.child_id else r
                for r in self.state.local_children
            ),
            goals,
        )

    def recover_local_children(self) -> None:
        super().recover_local_children()
        for record in self.state.local_children:
            if (
                record.coding is not None
                and record.coding.integration_state == "integrating"
            ):
                self._mark_integration_uncertain(record)
