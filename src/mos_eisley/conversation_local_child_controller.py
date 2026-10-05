"""Bounded local child admission and reports in the existing session header."""

import asyncio
import math
import os
from collections.abc import Callable
from contextlib import suppress
from typing import Literal
from uuid import uuid4

from mos_eisley.conversation_agents import (
    AgentInspectionScope,
    AgentInspectionSnapshot,
    AgentOperationalRecord,
    AgentReportReference,
    ImplementationAssignment,
    ImplementationReport,
)
from mos_eisley.conversation_goal import DurableGoal, GoalJob, exhausted
from mos_eisley.conversation_goal_controller import StateT
from mos_eisley.conversation_local_child import (
    LocalChildAuthorization,
    LocalChildExecution,
    LocalChildExecutor,
    LocalChildJob,
    LocalChildRecord,
    child_system,
)
from mos_eisley.conversation_schedule import LocalWakeupEvent
from mos_eisley.conversation_schedule_controller import ConversationScheduleController
from mos_eisley.conversation_state import (
    RuntimeConversationState,
    validate_runtime_state,
)
from mos_eisley.core.agent import AgentConfig, check_request_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.task_state import ResourceLedger

ChildAuthorizer = Callable[
    [ImplementationAssignment, AgentInspectionScope], LocalChildAuthorization
]


class ConversationLocalChildController(ConversationScheduleController[StateT]):
    local_child_authorizer: ChildAuthorizer | None
    local_child_executor: LocalChildExecutor | None
    _cancel_local_child: Callable[[], bool] | None
    _local_child_task: asyncio.Task[object] | None

    async def stop_local_child(self) -> None:
        """Session shutdown owns and awaits the exact running child cleanup."""
        task = self._local_child_task
        if task is None:
            return
        if task is asyncio.current_task():
            raise ValueError("A child cannot own its parent terminal shutdown.")
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def goal_control(
        self, action: Literal["pause", "resume", "cancel", "clear"]
    ) -> None:
        super().goal_control(action)
        if action in {"pause", "cancel", "clear"} and self._cancel_local_child:
            self._cancel_local_child()

    def child_scope(self) -> AgentInspectionScope:
        return AgentInspectionScope(
            owner_uid=self.state.owner_uid,
            parent_session_id=self.state.session_id,
            workspace_sha256=digest(self.state.workspace.encode()),
        )

    def child_authorization(
        self, assignment: ImplementationAssignment
    ) -> LocalChildAuthorization:
        if (
            self.local_child_authorizer is None
            or self.local_child_executor is None
            or self.state.owner_uid != os.getuid()
            or assignment.workspace != self.state.workspace
            or self.task_scope is not None
        ):
            raise ValueError(
                "Local children require qualified read-only host adapters."
            )
        scope = self.child_scope()
        approved = self.local_child_authorizer(assignment, scope)
        approved = LocalChildAuthorization.model_validate_json(
            approved.model_dump_json()
        )
        now = self.goal_clock()
        if (
            not math.isfinite(now)
            or now < 0
            or approved.mode != "recorded_read_only"
            or approved.scope != scope
            or approved.assignment_sha256 != assignment.sha256
            or approved.expires_at <= now
            or self.observe_branch_workspace(self.state.workspace)
            != approved.workspace_observation_sha256
        ):
            raise ValueError(
                "Child approval is stale or crosses owner/workspace scope."
            )
        return approved

    def record_authorization(self, record: LocalChildRecord) -> LocalChildAuthorization:
        return self.child_authorization(record.assignment)

    def _commit_children(
        self, children: tuple[LocalChildRecord, ...], goals: tuple[DurableGoal, ...]
    ) -> None:
        self._commit(
            validate_runtime_state(
                self.state.model_copy(
                    update={
                        "local_children": children,
                        "goals": goals,
                        "revision": self.state.revision + 1,
                    }
                )
            )
        )

    async def run_local_child(
        self,
        assignment: ImplementationAssignment,
        cassette: AgentCassette,
        *,
        expected_revision: int,
    ) -> ImplementationReport:
        """An explicit host call, never an automatic model-selected delegation."""
        from mos_eisley.conversation import prepare_conversation_request

        assignment = ImplementationAssignment.model_validate_json(
            assignment.model_dump_json()
        )
        goal = self.current_goal
        if (
            self.state.revision != expected_revision
            or goal is None
            or goal.status != "working"
            or assignment.parent_task_id != goal.goal_id
            or self._busy
            or self._side_busy
            or goal.reservations
            or goal.evaluating_sha256
            or len(self.state.local_children) >= 4
            or any(c.state != "completed" for c in self.state.local_children)
        ):
            raise ValueError("Child admission needs a safe working-goal boundary.")
        approval = self.child_authorization(assignment)
        job = LocalChildJob(
            assignment=assignment,
            config=AgentConfig(
                provider=assignment.provider,
                model=assignment.model,
                effort=assignment.effort,
                system=child_system(assignment),
                initial_turns=(
                    Turn(role="user", blocks=(TextBlock(text=assignment.objective),)),
                ),
                max_iterations=1,
                max_tool_calls=0,
                request_timeout_seconds=5,
            ),
            cassette=cassette,
        )
        request, budget = prepare_conversation_request(job.config)
        reserved = ResourceLedger(
            input_bytes=check_request_budget(request, budget),
            output_bytes=budget.output_reserve,
            attempts=1,
        )
        if (
            job.cassette.exchanges[0].request_sha256 != digest(canonical_bytes(request))
            or any(
                getattr(reserved, field) > getattr(assignment.allowance, field)
                for field in type(assignment.allowance).model_fields
            )
            or any(
                getattr(assignment.allowance, field)
                > getattr(goal.definition.ceiling, field)
                for field in type(assignment.allowance).model_fields
            )
            or exhausted(
                goal,
                self.goal_clock(),
                input_bytes=reserved.input_bytes,
                output_bytes=reserved.output_bytes,
                attempts=1,
            )
        ):
            raise ValueError("Child request exceeds its exact recording or allowance.")
        # Branch allowances also bound local children; do not silently bypass them.
        if self.state.branch_budget is not None:
            raise ValueError("Local children in forks require separate qualification.")
        assert self.local_child_executor is not None
        executor = self.local_child_executor
        child_id = "child-" + uuid4().hex
        record = LocalChildRecord(
            child_id=child_id,
            authorization=approval,
            assignment=assignment,
            goal_definition_sha256=goal.definition.sha256,
            request_sha256=digest(canonical_bytes(request)),
            cassette_sha256=digest(canonical_bytes(job.cassette)),
            image_id=executor.image_id,
            reserved=reserved,
        )
        updated_goal = goal.model_copy(
            update={
                "ledger": goal.ledger.model_copy(
                    update={
                        field: getattr(goal.ledger, field) + getattr(reserved, field)
                        for field in ResourceLedger.model_fields
                    }
                ),
                "jobs": (
                    *goal.jobs,
                    GoalJob(
                        operation_id=child_id,
                        definition_sha256=goal.definition.sha256,
                        checkin_seconds=10,
                        next_checkin_at=self.goal_clock() + 10,
                    ),
                ),
            }
        )
        self._commit_children(
            (*self.state.local_children, record),
            tuple(updated_goal if g == goal else g for g in self.state.goals),
        )
        task = asyncio.current_task()
        assert task is not None
        self._cancel_local_child = task.cancel
        self._local_child_task = task
        try:
            # Approval/workspace can change during the durable running commit.
            if (
                self.child_authorization(assignment) != approval
                or self.current_goal is None
                or self.current_goal.status != "working"
            ):
                raise ValueError("Child approval changed before execution.")
            async with asyncio.timeout(10):
                execution = await executor.execute(job)
            execution = LocalChildExecution.model_validate_json(
                execution.model_dump_json()
            )
            if execution.image_id != record.image_id:
                raise ValueError("Child execution returned another image identity.")
            usage = execution.result.usage
            if (
                usage.unit != "bytes"
                or usage.requests != 1
                or usage.tools
                or usage.largest_request != reserved.input_bytes
                or usage.billed_input > reserved.input_bytes
                or usage.billed_output > reserved.output_bytes
                or len(execution.events) != 2
                or execution.events[0].payload_sha256 != record.request_sha256
            ):
                raise ValueError(
                    "Child result has inconsistent usage or request evidence."
                )
            latest_goal = next(
                (g for g in self.state.goals if g.goal_id == self.state.active_goal_id),
                None,
            )
            if (
                self.child_authorization(assignment) != approval
                or latest_goal is None
                or latest_goal.goal_id != goal.goal_id
                or latest_goal.definition.sha256 != record.goal_definition_sha256
            ):
                raise ValueError("Child task/approval changed before result commit.")
            report = ImplementationReport(
                scope=record.authorization.scope,
                child_id=child_id,
                report_id=child_id + "-report",
                assignment_sha256=assignment.sha256,
                summary=execution.result.final_text,
                evidence=(
                    "Recorded read-only execution; image " + record.image_id,
                    "Execution receipt " + digest(canonical_bytes(execution)),
                ),
                complete=True,
            )
            record = record.model_copy(
                update={
                    "state": "completed",
                    "execution_sha256": digest(canonical_bytes(execution)),
                    "usage": ResourceLedger(
                        input_bytes=usage.billed_input,
                        output_bytes=usage.billed_output,
                        attempts=1,
                    ),
                    "report": report,
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
            self._cancel_local_child = None
            self._local_child_task = None

    def _finish_child(self, record: LocalChildRecord) -> None:
        goals: list[DurableGoal] = []
        for goal in self.state.goals:
            if goal.goal_id != record.assignment.parent_task_id:
                goals.append(goal)
                continue
            unknown = record.state != "completed"
            goals.append(
                goal.model_copy(
                    update={
                        "status": "paused"
                        if unknown and goal.status in {"working", "waiting"}
                        else goal.status,
                        "ledger": goal.ledger.model_copy(
                            update={
                                "uncertain_effects": goal.ledger.uncertain_effects
                                + int(unknown)
                            }
                        ),
                        "jobs": tuple(
                            j.model_copy(
                                update={
                                    "state": "uncertain" if unknown else "passed",
                                    "result_sha256": record.execution_sha256,
                                }
                            )
                            if j.operation_id == record.child_id
                            else j
                            for j in goal.jobs
                        ),
                    }
                )
            )
        self._commit_children(
            tuple(
                record if c.child_id == record.child_id else c
                for c in self.state.local_children
            ),
            tuple(goals),
        )

    def recover_local_children(self) -> None:
        for record in self.state.local_children:
            if record.state == "running":
                self._finish_child(record.model_copy(update={"state": "uncertain"}))

    def local_child_event(self, schedule_id: str, child_id: str) -> LocalWakeupEvent:
        """Only a current committed local result can become omitted event metadata."""
        spec = self._schedule_record(schedule_id).state.spec
        child = next(
            (c for c in self.state.local_children if c.child_id == child_id), None
        )
        if (
            child is None
            or child.state != "completed"
            or child.report is None
            or child_id not in spec.local_sources
            or spec.binding.task_id != child.assignment.task_id
            or spec.binding.goal_id != child.assignment.parent_task_id
            or spec.binding.goal_definition_sha256 != child.goal_definition_sha256
            or self.record_authorization(child) != child.authorization
        ):
            raise ValueError("Wakeup requires a current authorized committed child.")
        payload = canonical_bytes(child.report)
        return LocalWakeupEvent(
            source_id=child_id,
            event_id="result-" + digest(payload)[:32],
            sequence=1,
            binding=spec.binding,
            payload_sha256=digest(payload),
            payload_bytes=len(payload),
            kind="local_child",
        )

    def validate_local_child_event(self, event: LocalWakeupEvent) -> None:
        if event.kind != "local_child":
            raise ValueError("Only committed local child results are connected.")
        for record in self.state.schedules:
            if (
                record.state.spec.binding == event.binding
                and event.source_id in record.state.spec.local_sources
            ):
                expected = self.local_child_event(
                    record.state.spec.schedule_id, event.source_id
                )
                if expected == event:
                    return
        raise ValueError("Event differs from the exact committed child receipt.")


class RetainedLocalChildSource[ChildStateT: RuntimeConversationState]:
    """Inspection reads the controller's committed header, not another registry."""

    def __init__(self, controller: ConversationLocalChildController[ChildStateT]):
        self.controller = controller

    def snapshot(self, scope: AgentInspectionScope) -> AgentInspectionSnapshot:
        chat = self.controller
        if scope != chat.child_scope() or scope.owner_uid != os.getuid():
            raise ValueError("Child inspection scope differs.")
        rows: list[AgentOperationalRecord] = []
        for record in chat.state.local_children:
            current = False
            with suppress(OSError, ValueError):
                goal = chat.current_goal
                current = (
                    chat.record_authorization(record) == record.authorization
                    and goal is not None
                    and goal.goal_id == record.assignment.parent_task_id
                    and goal.definition.sha256 == record.goal_definition_sha256
                )
            rows.append(
                AgentOperationalRecord(
                    child_id=record.child_id,
                    scope=scope,
                    role="implementation",
                    state="unknown" if record.state == "uncertain" else record.state,
                    assignment=record.assignment,
                    assignment_current=current,
                    usage=record.usage,
                    verification=(
                        "passed"
                        if record.coding.handoff.verification.passed
                        else "failed"
                    )
                    if record.coding is not None and record.coding.handoff is not None
                    else "not_run",
                    report=None
                    if record.report is None
                    else AgentReportReference(
                        report_id=record.report.report_id,
                        assignment_sha256=record.assignment.sha256,
                        sha256=digest(canonical_bytes(record.report)),
                        availability="available",
                    ),
                )
            )
        return AgentInspectionSnapshot(
            scope=scope, revision=chat.state.revision, children=tuple(rows)
        )

    def report(
        self,
        scope: AgentInspectionScope,
        child_id: str,
        reference: AgentReportReference,
        *,
        expected_revision: int,
    ) -> ImplementationReport:
        if (
            self.controller.state.revision != expected_revision
            or scope != self.controller.child_scope()
        ):
            raise ValueError("Child report revision/scope changed.")
        record = next(
            c for c in self.controller.state.local_children if c.child_id == child_id
        )
        if record.report is None or record.report_sha256 != reference.sha256:
            raise ValueError("Child report reference differs.")
        return record.report
