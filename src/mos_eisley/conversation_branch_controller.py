"""Fork publication and transient side questions under the serialized session owner."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from mos_eisley.conversation_branch import (
    BranchBudget,
    BranchContext,
    BranchReservation,
    ForkOrigin,
    ForkReceipt,
    SelectedMessage,
    SideAnswer,
    SideReceipt,
    branch_system,
    side_attachment,
)
from mos_eisley.conversation_context import admit_context
from mos_eisley.conversation_goal import (
    DurableGoal,
    GoalDefinition,
    exhausted,
    merge_ledger,
)
from mos_eisley.conversation_goal_controller import ConversationGoalController, StateT
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    ConversationEntry,
    ConversationState,
    validate_runtime_state,
)
from mos_eisley.core.agent import (
    AgentResult,
    AgentUsage,
    check_request_budget,
    run_agent,
)
from mos_eisley.core.models import canonical_bytes, canonical_fingerprint, digest
from mos_eisley.core.ports import ModelClient
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.core.registry import fixture_registry
from mos_eisley.providers.agent_recorded import AgentCassette, RecordedAgentClient
from mos_eisley.task_state import ResourceCeiling, ResourceLedger
from mos_eisley.tools.none import NoToolsDispatcher


def observe_branch_workspace(workspace: str) -> str:
    root = Path(workspace)
    info = root.stat(follow_symlinks=False)
    if root.is_symlink() or not root.is_dir() or info.st_uid != os.getuid():
        raise ValueError("Conversation workspace must be owned and stable.")
    value = f"{root.resolve(strict=True)}:{info.st_dev}:{info.st_ino}"
    if (root / ".git").exists():
        from mos_eisley.git_review import GitReviewSelection, freeze_git_scope

        scope = freeze_git_scope(root, GitReviewSelection(kind="uncommitted"))
        value += ":" + digest(canonical_bytes(scope))
    return digest(value.encode())


def reserve(
    budget: BranchBudget, operation: BranchReservation, attempts: int = 1
) -> BranchBudget:
    if budget.ledger.uncertain_effects:
        raise ValueError("Uncertain branch effects require qualified recovery.")
    ledger = budget.ledger.model_copy(
        update={
            "input_bytes": budget.ledger.input_bytes + operation.input_bytes,
            "output_bytes": budget.ledger.output_bytes + operation.output_bytes,
            "attempts": budget.ledger.attempts + attempts,
        }
    )
    if ledger.exceeds(budget.ceiling):
        raise ValueError("Branch operation exceeds its cumulative allowance.")
    return budget.model_copy(
        update={"ledger": ledger, "pending": (*budget.pending, operation)}
    )


def settle(
    budget: BranchBudget, operation_id: str, usage: AgentUsage | None
) -> BranchBudget:
    held = next((r for r in budget.pending if r.operation_id == operation_id), None)
    if held is None:
        raise ValueError("Branch response has no durable reservation.")
    if usage is None or usage.unit != "bytes":
        return budget.model_copy(
            update={
                "ledger": budget.ledger.model_copy(
                    update={
                        "uncertain_effects": budget.ledger.uncertain_effects + 1,
                    }
                )
            }
        )
    ledger = budget.ledger.model_copy(
        update={
            "input_bytes": budget.ledger.input_bytes
            + max(0, usage.billed_input - held.input_bytes),
            "output_bytes": budget.ledger.output_bytes
            - held.output_bytes
            + usage.billed_output,
        }
    )
    return budget.model_copy(
        update={
            "ledger": ledger,
            "pending": tuple(r for r in budget.pending if r != held),
        }
    )


class ConversationBranchController(ConversationGoalController[StateT]):
    cassette: AgentCassette
    load_entry: Callable[[int, ArchivedConversationEntry], ConversationEntry] | None
    publish_fork: Callable[[ConversationState], None] | None
    observe_branch_workspace: Callable[[str], str]
    _side_busy: bool
    side_timeout: float
    _side_provider_task: asyncio.Task[AgentResult] | None
    _side_answers: dict[str, SideAnswer]

    def _branch_save(self, **updates: object) -> None:
        self._commit(
            validate_runtime_state(
                self.state.model_copy(
                    update={
                        **updates,
                        "revision": self.state.revision + 1,
                    }
                )
            )
        )

    def can_dispatch(
        self, entry: ConversationEntry | ArchivedConversationEntry
    ) -> bool:
        budget = self.state.branch_budget
        return super().can_dispatch(entry) and (
            budget is None
            or (
                not budget.ledger.uncertain_effects
                and budget.ledger.attempts < budget.ceiling.attempts
                and not budget.ledger.exceeds(budget.ceiling)
            )
        )

    def _save_goals(self, goals: tuple[DurableGoal, ...], active: str | None) -> None:
        # Goal evaluator reservations share the branch allowance atomically.
        budget = self.state.branch_budget
        if budget is None:
            super()._save_goals(goals, active)
            return
        for current in goals:
            old = next(
                (g for g in self.state.goals if g.goal_id == current.goal_id), None
            )
            if old is None:
                continue
            if not old.evaluating_sha256 and current.evaluating_sha256:
                budget = reserve(
                    budget,
                    BranchReservation(
                        operation_id="goal-" + current.evaluating_sha256[:16],
                        input_bytes=current.ledger.input_bytes - old.ledger.input_bytes,
                        output_bytes=current.ledger.output_bytes
                        - old.ledger.output_bytes,
                    ),
                )
            elif old.evaluating_sha256:
                operation_id = "goal-" + old.evaluating_sha256[:16]
                held = next(
                    (r for r in budget.pending if r.operation_id == operation_id), None
                )
                if held is not None and not current.evaluating_sha256:
                    budget = settle(
                        budget,
                        operation_id,
                        AgentUsage(
                            requests=1,
                            tools=0,
                            billed_input=held.input_bytes
                            + max(
                                0, current.ledger.input_bytes - old.ledger.input_bytes
                            ),
                            billed_output=held.output_bytes
                            + current.ledger.output_bytes
                            - old.ledger.output_bytes,
                            largest_request=held.input_bytes,
                        ),
                    )
                    if current.ledger.uncertain_effects < old.ledger.uncertain_effects:
                        budget = budget.model_copy(
                            update={
                                "ledger": budget.ledger.model_copy(
                                    update={
                                        "uncertain_effects": max(
                                            0, budget.ledger.uncertain_effects - 1
                                        )
                                    }
                                )
                            }
                        )
                elif (
                    held is not None
                    and current.ledger.uncertain_effects > old.ledger.uncertain_effects
                ):
                    budget = settle(budget, operation_id, None)
            for recovered in old.reservations:
                if recovered not in current.reservations:
                    operation_id = f"author-{recovered.message_position}"
                    held = next(
                        (r for r in budget.pending if r.operation_id == operation_id),
                        None,
                    )
                    if held is not None:
                        budget = settle(
                            budget,
                            operation_id,
                            AgentUsage(
                                requests=1,
                                tools=0,
                                billed_input=held.input_bytes,
                                billed_output=held.output_bytes,
                                largest_request=held.input_bytes,
                            ),
                        )
                        budget = budget.model_copy(
                            update={
                                "ledger": budget.ledger.model_copy(
                                    update={
                                        "uncertain_effects": max(
                                            0, budget.ledger.uncertain_effects - 1
                                        )
                                    }
                                )
                            }
                        )
        self._branch_save(goals=goals, active_goal_id=active, branch_budget=budget)

    def _goal_initial_ledger(self) -> ResourceLedger:
        if self.state.branch_budget is None:
            return super()._goal_initial_ledger()
        ledger = self.state.branch_budget.ledger
        if self.state.fork_origin is not None:
            baseline = self.state.fork_origin.task_ledger_baseline
            ledger = ResourceLedger(
                **{
                    field: getattr(ledger, field) + getattr(baseline, field)
                    for field in ResourceLedger.model_fields
                }
            )
        return ledger

    def create_goal(self, definition: GoalDefinition) -> DurableGoal:
        if self._side_busy or (
            self.state.branch_budget is not None
            and self.state.branch_budget.ledger.uncertain_effects
        ):
            raise ValueError(
                "Finish or reconcile side operations before creating a goal."
            )
        return super().create_goal(definition)

    def _branch_budget(self) -> BranchBudget:
        if self.state.branch_budget is not None:
            return self.state.branch_budget
        if any(g.evaluating_sha256 for g in self.state.goals):
            raise ValueError(
                "Finish the goal evaluator before activating fork/side accounting."
            )
        ledger = ResourceLedger(attempts=self.state.exchanges_consumed)
        pending: list[BranchReservation] = []
        for position, entry in enumerate(self.state.entries):
            admission = entry.request_admission
            if admission is None:
                continue
            amount = admission.request
            ledger = ledger.model_copy(
                update={
                    "input_bytes": ledger.input_bytes + amount.bytes,
                    "output_bytes": ledger.output_bytes
                    + (
                        entry.usage.billed_output
                        if entry.usage is not None and entry.usage.unit == "bytes"
                        else amount.output_reserve_bytes
                    ),
                }
            )
            if entry.status == "running":
                pending.append(
                    BranchReservation(
                        operation_id=f"author-{position}",
                        input_bytes=amount.bytes,
                        output_bytes=amount.output_reserve_bytes,
                    )
                )
            elif entry.status != "completed":
                ledger = ledger.model_copy(
                    update={"uncertain_effects": ledger.uncertain_effects + 1}
                )
        for goal in self.state.goals:
            ledger = merge_ledger(ledger, goal.ledger)
        return BranchBudget(
            ceiling=ResourceCeiling(
                input_bytes=1_000_000,
                output_bytes=64_000,
                attempts=16,
                cost_microusd=0,
                correction_cycles=8,
                review_rounds=8,
            ),
            ledger=ledger,
            pending=tuple(pending),
        )

    def _branch_transitions(
        self, entries: tuple[ConversationEntry | ArchivedConversationEntry, ...]
    ) -> BranchBudget | None:
        budget = self.state.branch_budget
        if budget is None:
            return None
        for position, entry in enumerate(entries):
            if position >= len(self.state.entries) or entry.is_review:
                continue
            previous = self.state.entries[position]
            if previous.status == "queued" and entry.status == "running":
                assert entry.request_admission is not None
                request = entry.request_admission.request
                budget = reserve(
                    budget,
                    BranchReservation(
                        operation_id=f"author-{position}",
                        input_bytes=request.bytes,
                        output_bytes=request.output_reserve_bytes,
                    ),
                )
            elif previous.status == "running" and entry.status in {
                "completed",
                "failed",
                "cancelled",
                "interrupted",
            }:
                budget = settle(
                    budget,
                    f"author-{position}",
                    entry.usage if entry.status == "completed" else None,
                )
        return budget

    def select_branch_context(
        self,
        positions: tuple[int, ...],
        *,
        boundary: int | None,
        expected_revision: int,
    ) -> BranchContext:
        if (
            self.state.owner_uid != os.getuid()
            or self.state.revision != expected_revision
        ):
            raise ValueError("Conversation owner or source revision changed.")
        if positions != tuple(sorted(set(positions))) or len(positions) > 4:
            raise ValueError("Select at most four unique ordered message positions.")
        if boundary is not None and (
            boundary < 0
            or boundary >= len(self.state.entries)
            or self.state.entries[boundary].status != "completed"
            or self.state.entries[boundary].is_review
        ):
            raise ValueError("Select a completed author boundary.")
        selected: list[SelectedMessage] = []
        for position in positions:
            if boundary is None or position < 0 or position > boundary:
                raise ValueError("Context selection exceeds its boundary.")
            entry = self.state.entries[position]
            if entry.status != "completed" or entry.is_review:
                raise ValueError(
                    "Select completed author messages, never review packets."
                )
            if isinstance(entry, ArchivedConversationEntry):
                if self.load_entry is None:
                    raise ValueError(
                        "Selected archived context requires its verified store."
                    )
                entry = self.load_entry(position, entry)
            assert entry.answer is not None
            selected.append(
                SelectedMessage(
                    position=position,
                    record_sha256=digest(canonical_bytes(entry)),
                    text=entry.text,
                    answer=entry.answer,
                    artifacts=entry.diff_attachments,
                )
            )
        return BranchContext(
            parent_session_id=self.state.session_id,
            source_revision=expected_revision,
            boundary=boundary,
            owner_uid=self.state.owner_uid,
            workspace=self.state.workspace,
            workspace_sha256=self.observe_branch_workspace(self.state.workspace),
            messages=tuple(selected),
        )

    def create_fork(
        self,
        positions: tuple[int, ...],
        *,
        boundary: int,
        expected_revision: int,
        allowance: ResourceCeiling | None = None,
    ) -> ConversationState:
        if self._busy or self._side_busy or self.publish_fork is None:
            raise ValueError(
                "Fork publication requires a safe boundary and owner-scoped store."
            )
        if self.task_scope is not None:
            raise ValueError(
                "Task-controller forks require qualified lifecycle integration."
            )
        if len(self.state.forks) >= 8 or any(
            g.reservations or g.evaluating_sha256 or g.ledger.uncertain_effects
            for g in self.state.goals
        ):
            raise ValueError(
                "Fork capacity or unresolved task operations prevent branching."
            )
        context = self.select_branch_context(
            positions, boundary=boundary, expected_revision=expected_revision
        )
        allowance = allowance or ResourceCeiling(
            input_bytes=32000,
            output_bytes=12000,
            attempts=1,
            cost_microusd=0,
            correction_cycles=0,
            review_rounds=0,
        )
        allowance = ResourceCeiling.model_validate_json(allowance.model_dump_json())
        if (
            allowance.attempts < 1
            or allowance.cost_microusd
            or allowance.correction_cycles
            or allowance.review_rounds
        ):
            raise ValueError(
                "Recorded forks require a positive, zero-cost author allowance."
            )
        if self.state.exchanges_consumed + allowance.attempts > len(
            self.cassette.exchanges
        ):
            raise ValueError("Recording cannot cover the allocated branch attempts.")
        branch_id, child_id = uuid4().hex, uuid4().hex
        operation = BranchReservation(
            operation_id=branch_id,
            input_bytes=allowance.input_bytes,
            output_bytes=allowance.output_bytes,
        )
        budget = reserve(self._branch_budget(), operation, allowance.attempts)
        goals = self._charge_branch_goals(operation, allowance.attempts)
        child = ConversationState(
            session_id=child_id,
            owner_uid=self.state.owner_uid,
            workspace=self.state.workspace,
            cassette_sha256=self.state.cassette_sha256,
            exchanges_consumed=self.state.exchanges_consumed,
            retained_cassette=self.cassette,
            builtin_recording=self.state.builtin_recording,
            interaction_mode=self.state.interaction_mode,
            memory_disabled=True,
            context_max_bytes=self.state.context_max_bytes,
            snapshot_max_bytes=self.state.snapshot_max_bytes,
            fork_origin=ForkOrigin(
                branch_id=branch_id,
                context=context,
                exchange_offset=self.state.exchanges_consumed,
                task_ledger_baseline=self._goal_initial_ledger()
                if self.state.fork_origin is not None
                else self._branch_budget().ledger,
            ),
            branch_budget=BranchBudget(ceiling=allowance, ledger=ResourceLedger()),
            goals=tuple(
                g.model_copy(
                    update={
                        "status": "paused"
                        if g.status
                        not in {"completed", "cancelled", "budget_exhausted"}
                        else g.status,
                        "evidence": None,
                        "semantic_evidence_sha256": None,
                    }
                )
                for g in self.state.goals
            ),
            active_goal_id=self.state.active_goal_id,
        )
        receipt = ForkReceipt(
            branch_id=branch_id,
            child_session_id=child_id,
            context_sha256=context.sha256,
            source_revision=expected_revision,
            allowance=allowance,
        )
        if context.workspace_sha256 != self.observe_branch_workspace(
            self.state.workspace
        ):
            raise ValueError("Workspace changed before fork publication.")
        # Reserve permanently in the parent before the child can become executable.
        budget = budget.model_copy(
            update={
                "pending": tuple(
                    r for r in budget.pending if r.operation_id != branch_id
                )
            }
        )
        self._branch_save(
            branch_budget=budget, goals=goals, forks=(*self.state.forks, receipt)
        )
        try:
            self.publish_fork(child)
        except BaseException:
            self._branch_save(
                forks=tuple(
                    f.model_copy(update={"state": "uncertain"})
                    if f.branch_id == branch_id
                    else f
                    for f in self.state.forks
                )
            )
            raise
        self._branch_save(
            forks=tuple(
                f.model_copy(update={"state": "published"})
                if f.branch_id == branch_id
                else f
                for f in self.state.forks
            )
        )
        return child

    def _charge_branch_goals(
        self, operation: BranchReservation, attempts: int = 1
    ) -> tuple[DurableGoal, ...]:
        for goal in self.state.goals:
            if exhausted(
                goal,
                self.goal_clock(),
                input_bytes=operation.input_bytes,
                output_bytes=operation.output_bytes,
                attempts=attempts,
            ):
                raise ValueError("Side/fork allocation exceeds retained task budgets.")
        return tuple(
            g.model_copy(
                update={
                    "ledger": g.ledger.model_copy(
                        update={
                            "input_bytes": g.ledger.input_bytes + operation.input_bytes,
                            "output_bytes": g.ledger.output_bytes
                            + operation.output_bytes,
                            "attempts": g.ledger.attempts + attempts,
                        }
                    )
                }
            )
            for g in self.state.goals
        )

    async def ask_side(
        self,
        question: str,
        positions: tuple[int, ...],
        *,
        expected_revision: int,
        client: ModelClient | None = None,
    ) -> SideAnswer:
        from mos_eisley.conversation import (
            conversation_config,
            prepare_conversation_request,
        )

        if (
            self._side_busy
            or len(self.state.sides) >= 16
            or not question.strip()
            or len(question) > 8000
        ):
            raise ValueError("Side question is empty, excessive or already running.")
        if self.task_scope is not None:
            raise ValueError(
                "Task-controller side calls require qualified aggregate admission."
            )
        context = self.select_branch_context(
            positions,
            boundary=max(positions) if positions else None,
            expected_revision=expected_revision,
        )
        config = conversation_config(
            (Turn(role="user", blocks=(TextBlock(text=question),)),),
            None,
            task_system=branch_system(context)
            + "\nSide question: answer read-only; no tools, task steering, "
            "implementation or independent review. The answer is transient "
            "until explicitly attached.",
        )
        admit_context(
            config.system, config.initial_turns, self.state.context_byte_limit
        )
        request, model_budget = prepare_conversation_request(config)
        size = check_request_budget(request, model_budget)
        consumed = self.state.exchanges_consumed
        if consumed >= len(self.cassette.exchanges):
            raise ValueError("Recording has no remaining side-call exchange.")
        side_id = uuid4().hex
        operation = BranchReservation(
            operation_id=side_id,
            input_bytes=size,
            output_bytes=model_budget.output_reserve,
        )
        budget = reserve(self._branch_budget(), operation)
        goals = self._charge_branch_goals(operation)
        receipt = SideReceipt(
            exchange_index=consumed,
            source_session_id=self.state.session_id,
            owner_uid=self.state.owner_uid,
            workspace_sha256=context.workspace_sha256,
            side_id=side_id,
            context_sha256=context.sha256,
            source_revision=expected_revision,
            positions=positions,
            question_sha256=digest(question.encode()),
            request_sha256=canonical_fingerprint(request).sha256,
        )
        self._branch_save(
            branch_budget=budget,
            goals=goals,
            sides=(*self.state.sides, receipt),
            exchanges_consumed=consumed + 1,
        )
        self._side_busy = True
        try:
            recorded = RecordedAgentClient(
                AgentCassette(exchanges=(self.cassette.exchanges[consumed],))
            )
            provider = asyncio.create_task(
                run_agent(
                    config, fixture_registry(), client or recorded, NoToolsDispatcher()
                )
            )
            self._side_provider_task = provider

            def consume(done: asyncio.Task[AgentResult]) -> None:
                if not done.cancelled():
                    done.exception()

            provider.add_done_callback(consume)
            try:
                done, _ = await asyncio.wait((provider,), timeout=self.side_timeout)
                if not done:
                    provider.cancel()
                    raise TimeoutError(
                        "Side question deadline exceeded; exposure remains reserved."
                    )
                result = provider.result()
            except asyncio.CancelledError:
                provider.cancel()
                raise
        except BaseException as error:
            budget = settle(self._branch_budget(), side_id, None)
            goals = tuple(
                g.model_copy(
                    update={
                        "ledger": g.ledger.model_copy(
                            update={"uncertain_effects": g.ledger.uncertain_effects + 1}
                        )
                    }
                )
                for g in self.state.goals
            )
            self._branch_save(
                branch_budget=budget,
                goals=goals,
                sides=tuple(
                    s.model_copy(
                        update={
                            "state": "cancelled"
                            if isinstance(error, asyncio.CancelledError)
                            else "uncertain"
                        }
                    )
                    if s.side_id == side_id
                    else s
                    for s in self.state.sides
                ),
            )
            raise
        finally:
            self._side_busy = False
        budget = settle(self._branch_budget(), side_id, result.usage)
        goals = tuple(
            g.model_copy(
                update={
                    "ledger": g.ledger.model_copy(
                        update={
                            "input_bytes": g.ledger.input_bytes
                            + max(0, result.usage.billed_input - operation.input_bytes),
                            "output_bytes": g.ledger.output_bytes
                            - operation.output_bytes
                            + result.usage.billed_output,
                        }
                    )
                }
            )
            for g in self.state.goals
        )
        receipt = receipt.model_copy(
            update={
                "state": "completed",
                "answer_sha256": digest(result.final_text.encode()),
                "usage": result.usage,
            }
        )
        self._branch_save(
            branch_budget=budget,
            goals=goals,
            sides=tuple(
                receipt if s.side_id == side_id else s for s in self.state.sides
            ),
        )
        answer = SideAnswer(
            receipt=receipt, question=question, answer=result.final_text
        )
        self._side_answers[side_id] = answer
        return answer

    def reconcile_side(
        self,
        side_id: str,
        *,
        expected_request_sha256: str,
        receipt_sha256: str,
        usage: AgentUsage,
    ) -> None:
        """Trusted recorded-call reconciliation; no retry or answer restoration."""
        from pydantic import TypeAdapter

        from mos_eisley.core.models import Digest

        if self._side_busy or (
            self._side_provider_task is not None and not self._side_provider_task.done()
        ):
            raise ValueError("Reconciliation requires the provider operation to end.")
        receipt = next((s for s in self.state.sides if s.side_id == side_id), None)
        if receipt is None or receipt.request_sha256 != expected_request_sha256:
            raise ValueError("Reconciliation names another request.")
        recovery = TypeAdapter[str](Digest).validate_python(receipt_sha256)
        if receipt.recovery_receipt_sha256 is not None:
            if receipt.recovery_receipt_sha256 != recovery:
                raise ValueError("A recovery receipt cannot be replaced.")
            return
        if receipt.state not in {"cancelled", "uncertain"}:
            raise ValueError("Only uncertain side operations require reconciliation.")
        usage = AgentUsage.model_validate_json(usage.model_dump_json())
        if usage.unit != "bytes":
            raise ValueError("Recorded side reconciliation requires byte usage.")
        budget = self._branch_budget()
        held = next((r for r in budget.pending if r.operation_id == side_id), None)
        if held is None:
            raise ValueError("Side operation has no retained exposure.")
        charged = usage.model_copy(
            update={
                "billed_input": max(usage.billed_input, held.input_bytes),
                "billed_output": max(usage.billed_output, held.output_bytes),
            }
        )
        budget = settle(budget, side_id, charged)
        budget = budget.model_copy(
            update={
                "ledger": budget.ledger.model_copy(
                    update={
                        "uncertain_effects": max(0, budget.ledger.uncertain_effects - 1)
                    }
                )
            }
        )
        goals = tuple(
            g.model_copy(
                update={
                    "ledger": g.ledger.model_copy(
                        update={
                            "uncertain_effects": max(0, g.ledger.uncertain_effects - 1),
                            "input_bytes": g.ledger.input_bytes
                            + charged.billed_input
                            - held.input_bytes,
                            "output_bytes": g.ledger.output_bytes
                            + charged.billed_output
                            - held.output_bytes,
                        }
                    )
                }
            )
            for g in self.state.goals
        )
        self._branch_save(
            branch_budget=budget,
            goals=goals,
            sides=tuple(
                s.model_copy(
                    update={
                        "state": "reconciled",
                        "recovery_receipt_sha256": recovery,
                        "usage": charged,
                    }
                )
                if s.side_id == side_id
                else s
                for s in self.state.sides
            ),
        )

    def side_answer_available(self, side_id: str) -> bool:
        return side_id in self._side_answers

    def discard_side(self, side_id: str) -> None:
        if self._side_answers.pop(side_id, None) is None:
            raise ValueError("Side answer is unavailable.")

    def attach_side(self, side_id: str) -> None:
        answer = self._side_answers.get(side_id)
        receipt = next((s for s in self.state.sides if s.side_id == side_id), None)
        if (
            answer is None
            or receipt is None
            or receipt.state != "completed"
            or receipt.attached_position is not None
        ):
            raise ValueError(
                "Side answer is unavailable or attached; "
                "transient answers do not survive restart."
            )
        text = "Consider this explicitly attached side answer." + side_attachment(
            answer
        )
        # Admission must succeed before attachment metadata changes.
        self.submit(text)
        self._branch_save(
            sides=tuple(
                s.model_copy(update={"attached_position": len(self.state.entries) - 1})
                if s.side_id == side_id
                else s
                for s in self.state.sides
            )
        )
        self._side_answers.pop(side_id, None)

    def submit(self, text: str) -> None:
        raise NotImplementedError

    def revalidate_fork(self) -> None:
        if self.state.fork_origin is None or self._busy or self._side_busy:
            raise ValueError("Revalidation requires a saved fork and a safe boundary.")
        observed = self.observe_branch_workspace(self.state.workspace)
        self._branch_save(
            fork_origin=self.state.fork_origin.model_copy(
                update={"admitted_workspace_sha256": observed},
            )
        )

    def recover_branches(self) -> None:
        running = tuple(s for s in self.state.sides if s.state == "running")
        reserved = tuple(f for f in self.state.forks if f.state == "reserved")
        if running:
            budget = self._branch_budget()
            for receipt in running:
                budget = settle(budget, receipt.side_id, None)
            self._branch_save(
                branch_budget=budget,
                sides=tuple(
                    s.model_copy(update={"state": "uncertain"})
                    if s.state == "running"
                    else s
                    for s in self.state.sides
                ),
                goals=tuple(
                    g.model_copy(
                        update={
                            "ledger": g.ledger.model_copy(
                                update={
                                    "uncertain_effects": g.ledger.uncertain_effects
                                    + len(running)
                                }
                            )
                        }
                    )
                    for g in self.state.goals
                ),
            )
        if reserved:
            self._branch_save(
                forks=tuple(
                    f.model_copy(update={"state": "uncertain"})
                    if f.state == "reserved"
                    else f
                    for f in self.state.forks
                )
            )
