"""Durable goal admission, accounting and completion controller for conversations."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Generic, Literal
from uuid import uuid4

from pydantic import TypeAdapter
from typing_extensions import TypeVar

from mos_eisley.conversation_goal import (
    DurableGoal,
    GoalDefinition,
    GoalEvidence,
    GoalFailure,
    GoalJob,
    GoalReservation,
    GoalStatus,
    apply_job_report,
    check_job_deadlines,
    decide,
    exhausted,
    merge_ledger,
)
from mos_eisley.conversation_goal_evaluation import (
    GoalEvaluator,
    GoalSemanticVerdict,
    evaluation_input,
    run_goal_evaluation,
)
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    ConversationEntry,
    ConversationState,
    RuntimeConversationState,
    validate_runtime_state,
)
from mos_eisley.core.models import Digest, canonical_bytes, digest
from mos_eisley.task_state import (
    OwnerProjectScope,
    ResourceCeiling,
    ResourceLedger,
    WorkspaceState,
)

StateT = TypeVar("StateT", bound=RuntimeConversationState, default=ConversationState)


class ConversationGoalController(Generic[StateT]):
    """Ports are supplied by the existing serialized conversation owner."""

    state: StateT
    _busy: bool
    _broken: bool
    task_scope: OwnerProjectScope | None
    validate_memory: Callable[[], None] | None
    observe_task_workspace: Callable[[], WorkspaceState] | None
    goal_clock: Callable[[], float]
    goal_evaluator: GoalEvaluator | None
    goal_evaluator_timeout: float
    _goal_evaluator_task: asyncio.Future[GoalSemanticVerdict] | None
    observe_goal_evidence: Callable[[DurableGoal], GoalEvidence | None] | None
    observe_goal_inputs: Callable[[], tuple[str, str]] | None

    def _commit(self, updated: StateT) -> None:
        raise NotImplementedError("The conversation owner must persist goal state.")

    @property
    def persistence_broken(self) -> bool:
        return self._broken

    @property
    def current_goal(self) -> DurableGoal | None:
        return next(
            (g for g in self.state.goals if g.goal_id == self.state.active_goal_id),
            None,
        )

    def goal_for_entry(
        self, entry: ConversationEntry | ArchivedConversationEntry
    ) -> DurableGoal | None:
        return next((g for g in self.state.goals if g.goal_id == entry.goal_id), None)

    def can_dispatch(
        self, entry: ConversationEntry | ArchivedConversationEntry
    ) -> bool:
        goal = self.goal_for_entry(entry)
        return entry.goal_id is None or (
            goal is not None
            and goal.goal_id == self.state.active_goal_id
            and goal.status == "working"
            and not goal.reservations
            and not goal.ledger.uncertain_effects
            and entry.goal_definition_sha256 == goal.definition.sha256
        )

    def _save_goals(self, goals: tuple[DurableGoal, ...], active: str | None) -> None:
        self._commit(
            validate_runtime_state(
                self.state.model_copy(
                    update={
                        "goals": goals,
                        "active_goal_id": active,
                        "revision": self.state.revision + 1,
                    }
                )
            )
        )

    def _goal_initial_ledger(self) -> ResourceLedger:
        return ResourceLedger()

    def create_goal(self, definition: GoalDefinition) -> DurableGoal:
        definition = GoalDefinition.model_validate_json(definition.model_dump_json())
        if self.current_goal is not None:
            raise ValueError("Clear the selected goal before creating another.")
        if any(g.reservations or g.evaluating_sha256 for g in self.state.goals):
            raise ValueError(
                "Reconcile retained in-flight goal operations before creating another."
            )
        if len(self.state.goals) >= 8:
            raise ValueError(
                "Retained goal capacity reached; start a separately authorized session."
            )
        if any(
            definition.max_seconds > old.definition.max_seconds
            or any(
                getattr(definition.ceiling, key) > getattr(old.definition.ceiling, key)
                for key in ResourceCeiling.model_fields
            )
            for old in self.state.goals
        ):
            raise ValueError("A new goal cannot enlarge retained task ceilings.")
        ledger = self._goal_initial_ledger()
        for old in self.state.goals:
            ledger = merge_ledger(ledger, old.ledger)
        goal = DurableGoal(
            goal_id=uuid4().hex,
            owner_uid=self.state.owner_uid,
            workspace=self.state.workspace,
            revisions=(definition,),
            started_at=min(
                (g.started_at for g in self.state.goals), default=self.goal_clock()
            ),
            ledger=ledger,
        )
        if self.task_scope is not None:
            if self.observe_goal_evidence is None or self.observe_goal_inputs is None:
                raise ValueError(
                    "Task-scoped goals require a qualified aggregate ledger observer."
                )
            observed = self.observe_goal_evidence(goal)
            workspace, inputs = self.observe_goal_inputs()
            if (
                observed is None
                or observed.goal_id != goal.goal_id
                or observed.definition_sha256 != goal.definition.sha256
                or observed.workspace_sha256 != workspace
                or observed.inputs_sha256 != inputs
            ):
                raise ValueError("Task usage is unavailable or bound to stale inputs.")
            ledger = merge_ledger(ledger, observed.task_ledger)
            goal = goal.model_copy(update={"ledger": ledger})
        if ledger.uncertain_effects:
            goal = goal.model_copy(update={"status": "blocked"})
        elif exhausted(goal, self.goal_clock(), attempts=1):
            goal = goal.model_copy(update={"status": "budget_exhausted"})
        self._save_goals((*self.state.goals, goal), goal.goal_id)
        return goal

    def edit_goal(self, definition: GoalDefinition, *, expected_revision: int) -> None:
        goal = self.current_goal
        if goal is None or len(goal.revisions) != expected_revision:
            raise ValueError("Goal revision changed or no goal is selected.")
        if len(goal.revisions) >= 16:
            raise ValueError("Goal revision capacity reached.")
        definition = GoalDefinition.model_validate_json(definition.model_dump_json())
        if (
            any(
                getattr(definition.ceiling, k) > getattr(goal.definition.ceiling, k)
                for k in ResourceCeiling.model_fields
            )
            or definition.max_seconds > goal.definition.max_seconds
        ):
            raise ValueError("Goal edits cannot reset or enlarge cumulative ceilings.")
        if goal.status in {"completed", "cancelled"}:
            raise ValueError("Terminal goals require a new explicit objective.")
        updated = goal.model_copy(
            update={
                "revisions": (*goal.revisions, definition),
                "evidence": None,
                "semantic_evidence_sha256": None,
                "completed_work": (),
                "status": "paused",
                "decisions": (),
            }
        )
        # Retain historical decisions; edited criteria invalidate their applicability.
        updated = updated.model_copy(update={"decisions": goal.decisions})
        self._save_goals(
            tuple(
                updated if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            goal.goal_id,
        )

    def goal_control(
        self, action: Literal["pause", "resume", "cancel", "clear"]
    ) -> None:
        goal = self.current_goal
        if goal is None:
            raise ValueError("No goal is selected.")
        status: GoalStatus = goal.status
        if action == "resume":
            if goal.status in {"completed", "cancelled"}:
                raise ValueError("Completed/cancelled goals cannot resume.")
            if (
                goal.reservations
                or goal.evaluating_sha256
                or goal.ledger.uncertain_effects
            ):
                raise ValueError(
                    "Uncertain or in-flight operations require trusted reconciliation."
                )
            if exhausted(goal, self.goal_clock(), attempts=1):
                raise ValueError(
                    "Goal budgets remain exhausted; resume cannot reset them."
                )
            if self.validate_memory is not None:
                self.validate_memory()
            if self.observe_task_workspace is not None:
                self.observe_task_workspace()
            status = (
                "waiting"
                if any(j.required and j.state != "passed" for j in goal.jobs)
                else "working"
            )
        elif action == "pause":
            if goal.status in {"completed", "cancelled"}:
                raise ValueError("Terminal goals cannot pause.")
            status = "paused"
        elif action == "clear" and goal.status not in {
            "completed",
            "cancelled",
            "budget_exhausted",
        }:
            status = "paused"
        elif action == "cancel":
            if goal.status == "completed":
                raise ValueError("Completed goals remain completed.")
            status = "cancelled"
        updated = goal.model_copy(
            update={
                "status": status,
                "evidence": None if action == "resume" else goal.evidence,
            }
        )
        self._save_goals(
            tuple(
                updated if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            None if action == "clear" else goal.goal_id,
        )

    def _goal_transitions(
        self, entries: tuple[ConversationEntry | ArchivedConversationEntry, ...]
    ) -> tuple[DurableGoal, ...]:
        """Reserve before dispatch; atomically charge and guard turn completion."""
        goals = list(self.state.goals)
        for position, entry in enumerate(entries):
            if entry.goal_id is None or position >= len(self.state.entries):
                continue
            old = self.state.entries[position]
            goal_index = next(
                i for i, g in enumerate(goals) if g.goal_id == entry.goal_id
            )
            goal = goals[goal_index]
            if old.status == "queued" and entry.status == "running":
                assert entry.request_admission is not None
                reservation = GoalReservation(
                    message_position=position,
                    input_bytes=entry.request_admission.request.bytes,
                    output_bytes=entry.request_admission.request.output_reserve_bytes,
                )
                if exhausted(
                    goal,
                    self.goal_clock(),
                    input_bytes=reservation.input_bytes,
                    output_bytes=reservation.output_bytes,
                    attempts=1,
                ):
                    raise ValueError(
                        "Goal request exceeds its remaining cumulative budget."
                    )
                ledger = goal.ledger.model_copy(
                    update={
                        "attempts": goal.ledger.attempts + 1,
                        "input_bytes": goal.ledger.input_bytes
                        + reservation.input_bytes,
                        "output_bytes": goal.ledger.output_bytes
                        + reservation.output_bytes,
                    }
                )
                goals[goal_index] = goal.model_copy(
                    update={
                        "ledger": ledger,
                        "reservations": (*goal.reservations, reservation),
                    }
                )
            elif old.status == "running" and entry.status in {
                "completed",
                "failed",
                "cancelled",
                "interrupted",
            }:
                held = next(
                    (r for r in goal.reservations if r.message_position == position),
                    None,
                )
                if held is None:
                    raise ValueError("Goal dispatch has no durable reservation.")
                if (
                    entry.status == "completed"
                    and entry.usage is not None
                    and entry.usage.unit == "bytes"
                ):
                    ledger = goal.ledger.model_copy(
                        update={
                            "input_bytes": goal.ledger.input_bytes
                            + max(0, entry.usage.billed_input - held.input_bytes),
                            "output_bytes": goal.ledger.output_bytes
                            - held.output_bytes
                            + entry.usage.billed_output,
                        }
                    )
                    goal = goal.model_copy(
                        update={
                            "ledger": ledger,
                            "reservations": tuple(
                                r for r in goal.reservations if r != held
                            ),
                        }
                    )
                else:
                    goal = goal.model_copy(
                        update={
                            "ledger": goal.ledger.model_copy(
                                update={
                                    "uncertain_effects": goal.ledger.uncertain_effects
                                    + 1
                                }
                            ),
                            "last_failure": "Uncertain request failure; "
                            "qualified reconciliation required.",
                        }
                    )
                goals[goal_index] = decide(goal, self.goal_clock(), count_turn=True)
        return tuple(goals)

    def recover_goal_evaluations(self) -> None:
        """A lost evaluator response preserves its durable reservation on restart."""
        goals = tuple(
            goal.model_copy(
                update={
                    "status": "blocked" if goal.status == "waiting" else goal.status,
                    "ledger": goal.ledger.model_copy(update={"uncertain_effects": 1}),
                    "last_failure": "Evaluator interrupted by restart; "
                    "qualified reconciliation required.",
                }
            )
            if goal.evaluating_sha256 and not goal.ledger.uncertain_effects
            else goal
            for goal in self.state.goals
        )
        if goals != self.state.goals:
            self._save_goals(goals, self.state.active_goal_id)

    def check_goal(self) -> DurableGoal:
        goal = self.current_goal
        if goal is None:
            raise ValueError("No goal is selected.")
        if goal.status == "completed":
            return goal
        if self._busy or goal.reservations or goal.evaluating_sha256:
            raise ValueError("Goal completion checks require a safe turn boundary.")
        goal = check_job_deadlines(goal, self.goal_clock())
        evidence = None
        workspace = inputs = None
        if (
            self.observe_goal_evidence is not None
            and self.observe_goal_inputs is not None
        ):
            try:
                before = self.observe_goal_inputs()
                observation = self.observe_goal_evidence(goal)
                evidence = (
                    None
                    if observation is None
                    else GoalEvidence.model_validate_json(observation.model_dump_json())
                )
                if (
                    evidence is not None
                    and goal.evidence is not None
                    and goal.semantic_evidence_sha256
                    == digest(canonical_bytes(evidence))
                ):
                    evidence = evidence.model_copy(
                        update={
                            "semantic": goal.evidence.semantic,
                            "semantic_reason": goal.evidence.semantic_reason,
                            "failure_cause": goal.evidence.failure_cause,
                        }
                    )
                if before == self.observe_goal_inputs():
                    workspace, inputs = before
                    if (
                        evidence is not None
                        and evidence.goal_id == goal.goal_id
                        and evidence.definition_sha256 == goal.definition.sha256
                        and evidence.workspace_sha256 == workspace
                        and evidence.inputs_sha256 == inputs
                    ):
                        goal = goal.model_copy(
                            update={
                                "ledger": merge_ledger(
                                    goal.ledger, evidence.task_ledger
                                )
                            }
                        )
            except (ValueError, OSError, AttributeError):
                goal = goal.model_copy(
                    update={
                        "status": "blocked",
                        "evidence": None,
                        "last_failure": "Completion evidence adapter failed; "
                        "no execution or verification inferred.",
                    }
                )
        updated = decide(
            goal,
            self.goal_clock(),
            evidence,
            workspace_sha256=workspace,
            inputs_sha256=inputs,
            count_turn=False,
        )
        self._save_goals(
            tuple(
                updated if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            goal.goal_id,
        )
        return updated

    def register_goal_job(self, job: GoalJob, *, expected_definition: str) -> None:
        goal = self.current_goal
        if goal is None or goal.definition.sha256 != expected_definition:
            raise ValueError("Job assignment names an obsolete goal revision.")
        if goal.status not in {"working", "waiting"}:
            raise ValueError("Stop states cannot admit required background work.")
        if any(j.operation_id == job.operation_id for j in goal.jobs):
            raise ValueError("Operation is already registered.")
        job = GoalJob.model_validate_json(job.model_dump_json()).model_copy(
            update={
                "next_checkin_at": self.goal_clock() + job.checkin_seconds,
                "definition_sha256": goal.definition.sha256,
                "committed_revision": None,
            }
        )
        updated = goal.model_copy(
            update={
                "jobs": (*goal.jobs, job),
                "status": "waiting" if job.required else goal.status,
            }
        )
        self._save_goals(
            tuple(
                updated if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            self.state.active_goal_id,
        )

    def report_goal_job(
        self, goal_id: str, report: GoalJob, *, expected_definition: str
    ) -> None:
        goal = next((g for g in self.state.goals if g.goal_id == goal_id), None)
        if goal is None or goal.definition.sha256 != expected_definition:
            raise ValueError("Background result belongs to an obsolete goal.")
        report = GoalJob.model_validate_json(report.model_dump_json())
        old = next(
            (j for j in goal.jobs if j.operation_id == report.operation_id), None
        )
        if old is None:
            raise ValueError("Unregistered result operation.")
        if report.committed_revision not in {None, old.committed_revision}:
            raise ValueError("Result commit revision is controller-owned.")
        report = report.model_copy(
            update={
                "committed_revision": (
                    old.committed_revision or self.state.revision + 1
                    if report.state in {"passed", "failed"}
                    and report.result_sha256 is not None
                    else None
                )
            }
        )
        updated = apply_job_report(goal, report, self.goal_clock())
        if updated == goal:
            return
        self._save_goals(
            tuple(
                updated if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            self.state.active_goal_id,
        )

    def report_goal_failure(
        self, failure: GoalFailure, *, expected_definition: str
    ) -> None:
        """Trusted provider/execution adapters classify errors; prose cannot do so."""
        goal = self.current_goal
        if goal is None or goal.definition.sha256 != expected_definition:
            raise ValueError("Failure report names a stale goal revision.")
        failure = GoalFailure.model_validate_json(failure.model_dump_json())
        if any(f.receipt_sha256 == failure.receipt_sha256 for f in goal.failures):
            return
        state: GoalStatus = (
            "budget_exhausted" if failure.category == "usage_exhausted" else "blocked"
        )
        if goal.status in {"paused", "cancelled", "completed"}:
            state = goal.status
        updated = goal.model_copy(
            update={
                "failures": (*goal.failures[-31:], failure),
                "status": state,
                "last_failure": failure.reason,
                "repeated_failures": goal.repeated_failures + 1
                if goal.last_failure == failure.reason
                else 1,
            }
        )
        self._save_goals(
            tuple(
                updated if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            self.state.active_goal_id,
        )

    def reconcile_goal_operation(
        self,
        operation_id: str,
        *,
        expected_definition: str,
        receipt_sha256: str,
        observed_ledger: ResourceLedger,
    ) -> None:
        """A qualified adapter may reconcile one exact uncertain operation.

        This is not a user command or a retry permission. Charges cannot decrease;
        only the corresponding uncertainty marker and in-flight reservation clear.
        """
        goal = self.current_goal
        if self._busy or (
            self._goal_evaluator_task is not None
            and not self._goal_evaluator_task.done()
        ):
            raise ValueError("Reconciliation requires the active operation to end.")
        if goal is None or goal.definition.sha256 != expected_definition:
            raise ValueError("Reconciliation names an obsolete goal revision.")
        receipt = TypeAdapter[str](Digest).validate_python(receipt_sha256)
        if receipt in goal.recovery_receipts:
            return
        if goal.ledger.uncertain_effects == 0:
            raise ValueError(
                "A running operation is not yet an uncertain recovery case."
            )
        pending = next(
            (
                r
                for r in goal.reservations
                if operation_id == f"message-{r.message_position}"
            ),
            None,
        )
        semantic = (
            goal.evaluating_sha256 is not None
            and operation_id == "evaluate-" + goal.evaluating_sha256[:16]
        )
        if pending is None and not semantic:
            raise ValueError("No matching uncertain operation is reserved.")
        observed_ledger = ResourceLedger.model_validate_json(
            observed_ledger.model_dump_json()
        )
        ledger = merge_ledger(goal.ledger, observed_ledger).model_copy(
            update={
                "uncertain_effects": max(
                    0,
                    max(
                        goal.ledger.uncertain_effects, observed_ledger.uncertain_effects
                    )
                    - 1,
                )
            }
        )
        updated = goal.model_copy(
            update={
                "ledger": ledger,
                "reservations": tuple(r for r in goal.reservations if r != pending),
                "evaluating_sha256": None if semantic else goal.evaluating_sha256,
                "recovery_receipts": (*goal.recovery_receipts[-31:], receipt),
            }
        )
        self._save_goals(
            tuple(
                updated if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            self.state.active_goal_id,
        )

    async def evaluate_goal(self) -> DurableGoal:
        goal = self.check_goal()
        if (
            self.goal_evaluator is None
            or goal.evidence is None
            or goal.evidence.semantic != "unavailable"
            or goal.status != "working"
            or any(j.required and j.state != "passed" for j in goal.jobs)
        ):
            return goal
        evidence = goal.evidence
        # Test/build/work-unit and independent-review guards are prerequisites.
        d = goal.definition
        if (
            set(d.remaining_work) - set(evidence.completed_work)
            or set(d.verification_requirements) - set(evidence.passed_verifications)
            or evidence.executed_tests < d.minimum_tests
            or (
                d.independent_review_required
                and evidence.independent_review != "accept"
            )
        ):
            return goal
        request = evaluation_input(goal, evidence)
        # Worst-case escaped JSON reason (2,000 * 6 bytes) plus schema overhead.
        reserve_in, reserve_out = len(canonical_bytes(request)), 13312
        if exhausted(
            goal,
            self.goal_clock(),
            input_bytes=reserve_in,
            output_bytes=reserve_out,
            attempts=1,
        ):
            updated = goal.model_copy(update={"status": "budget_exhausted"})
            self._save_goals(
                tuple(
                    updated if g.goal_id == goal.goal_id else g
                    for g in self.state.goals
                ),
                self.state.active_goal_id,
            )
            return updated
        ledger = goal.ledger.model_copy(
            update={
                "attempts": goal.ledger.attempts + 1,
                "input_bytes": goal.ledger.input_bytes + reserve_in,
                "output_bytes": goal.ledger.output_bytes + reserve_out,
            }
        )
        reserved = goal.model_copy(
            update={
                "ledger": ledger,
                "status": "waiting",
                "evaluating_sha256": digest(canonical_bytes(request)),
            }
        )
        self._save_goals(
            tuple(
                reserved if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            self.state.active_goal_id,
        )

        def observe_task(task: asyncio.Future[GoalSemanticVerdict]) -> None:
            self._goal_evaluator_task = task

        try:
            verdict = await run_goal_evaluation(
                self.goal_evaluator,
                request,
                timeout=self.goal_evaluator_timeout,
                observe_task=observe_task,
            )
        except asyncio.CancelledError:
            current = next(g for g in self.state.goals if g.goal_id == goal.goal_id)
            updated = current.model_copy(
                update={
                    "status": "blocked"
                    if current.status == "waiting"
                    else current.status,
                    "ledger": current.ledger.model_copy(
                        update={
                            "uncertain_effects": current.ledger.uncertain_effects + 1
                        }
                    ),
                    "last_failure": "Semantic evaluation was interrupted; "
                    "its exposure remains reserved.",
                }
            )
            self._save_goals(
                tuple(
                    updated if g.goal_id == goal.goal_id else g
                    for g in self.state.goals
                ),
                self.state.active_goal_id,
            )
            raise
        except (
            Exception
        ):  # Adapter failures retain exposure; persistence runs outside this try.
            current = next(g for g in self.state.goals if g.goal_id == goal.goal_id)
            updated = current.model_copy(
                update={
                    "status": "blocked"
                    if current.status == "waiting"
                    else current.status,
                    "ledger": current.ledger.model_copy(
                        update={
                            "uncertain_effects": current.ledger.uncertain_effects + 1
                        }
                    ),
                    "last_failure": "Semantic evaluator failed or timed out; "
                    "exposure remains reserved.",
                }
            )
            self._save_goals(
                tuple(
                    updated if g.goal_id == goal.goal_id else g
                    for g in self.state.goals
                ),
                self.state.active_goal_id,
            )
            return updated
        current = next(g for g in self.state.goals if g.goal_id == goal.goal_id)
        current = current.model_copy(
            update={
                "evaluating_sha256": None,
                "ledger": current.ledger.model_copy(
                    update={
                        "output_bytes": current.ledger.output_bytes
                        - reserve_out
                        + len(canonical_bytes(verdict))
                    }
                ),
            }
        )
        self._save_goals(
            tuple(
                current if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            self.state.active_goal_id,
        )
        if (
            current.definition.sha256 != request.definition_sha256
            or current.status != "waiting"
            or current.goal_id != self.state.active_goal_id
        ):
            return current  # Late results confer no new continuation authority.
        current = current.model_copy(update={"status": "working"})
        before = (
            None if self.observe_goal_inputs is None else self.observe_goal_inputs()
        )
        evidence = evidence.model_copy(
            update={
                "semantic": "passed" if verdict.decision == "passed" else "failed",
                "semantic_reason": verdict.reason,
                "failure_cause": verdict.reason
                if verdict.decision == "blocked"
                else None,
            }
        )
        updated = decide(
            current,
            self.goal_clock(),
            evidence,
            workspace_sha256=None if before is None else before[0],
            inputs_sha256=None if before is None else before[1],
            count_turn=False,
        )
        updated = updated.model_copy(
            update={"semantic_evidence_sha256": request.evidence_sha256}
        )
        if verdict.decision == "blocked" and updated.status not in {
            "completed",
            "budget_exhausted",
        }:
            updated = updated.model_copy(update={"status": "blocked"})
        self._save_goals(
            tuple(
                updated if g.goal_id == goal.goal_id else g for g in self.state.goals
            ),
            self.state.active_goal_id,
        )
        return updated
