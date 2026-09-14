"""Text-free records of admitted chat inputs, saved before provider dispatch."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_context import ContextSelection, RequestContext
from mos_eisley.conversation_limits import ContextByteLimit
from mos_eisley.core.budget import Budget
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_fingerprint
from mos_eisley.core.protocol import Effort, ModelRequest
from mos_eisley.task_profile import TaskProfileAdmission
from mos_eisley.task_state_acquisition import TaskStateAdmission


class RequestBudgetPreview(Contract):
    provider: Identifier
    model: Identifier
    effort: Effort
    sha256: Digest
    bytes: Annotated[int, Field(ge=1)]
    max_bytes: Annotated[int, Field(ge=1)]
    within_budget: bool
    output_reserve_bytes: Annotated[int, Field(ge=1)]
    headroom_bytes: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def consistent_fit(self) -> Self:
        if self.within_budget != (self.bytes <= self.max_bytes):
            raise ValueError("request fit does not match its byte counts")
        return self


def describe_request(request: ModelRequest, budget: Budget) -> RequestBudgetPreview:
    fingerprint = canonical_fingerprint(request)
    return RequestBudgetPreview(
        provider=request.provider,
        model=request.model,
        effort=request.effort,
        sha256=fingerprint.sha256,
        bytes=fingerprint.bytes,
        max_bytes=budget.usable_input,
        within_budget=fingerprint.bytes <= budget.usable_input,
        output_reserve_bytes=budget.output_reserve,
        headroom_bytes=budget.headroom,
    )


class RequestAdmission(Contract):
    """An admission record is not proof of transmission or provider receipt."""

    schema_version: Literal[1] = 1
    source_revision: Annotated[int, Field(ge=0)]
    message_count: Annotated[int, Field(ge=1, le=16)]
    exchange_index: Annotated[int, Field(ge=0, le=15)]
    selection: ContextSelection
    context_sha256: Digest
    context_bytes: Annotated[int, Field(ge=1)]
    context_max_bytes: ContextByteLimit
    request: RequestBudgetPreview
    memory_selected: bool
    task_profile: TaskProfileAdmission | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    task_state: TaskStateAdmission | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def admitted_selection(self) -> Self:
        if (
            self.context_bytes > self.context_max_bytes
            or not self.request.within_budget
        ):
            raise ValueError("request admission requires both byte budgets to fit")
        if self.task_profile is not None and (
            self.task_profile.request_sha256 != self.request.sha256
            or self.memory_selected
            != (self.task_profile.reusable_memory_context_sha256 is not None)
        ):
            raise ValueError("task profile does not bind this admitted request context")
        if self.task_state is not None and (
            self.task_state.request_sha256 != self.request.sha256
        ):
            raise ValueError("task state does not bind this admitted request")
        expected_task_state = (
            None if self.task_state is None else self.task_state.context_sha256
        )
        if self.task_profile is not None and (
            self.task_profile.temporary_task_state_sha256 != expected_task_state
            or (
                self.task_state is not None
                and self.task_profile.manifest.work_unit
                != self.task_state.current_work_unit
            )
        ):
            raise ValueError("task profile and task state select different work")
        selection = self.selection
        sources = selection.turn_sources
        target = selection.message_index
        if target >= self.message_count or len(sources) % 2 != 1:
            raise ValueError("invalid admission target or turn count")
        completed: list[int] = []
        for turn, source in enumerate(sources):
            if (
                source.role != ("user" if turn % 2 == 0 else "assistant")
                or tuple(sorted(set(source.positions))) != source.positions
                or source.positions[-1] > target
            ):
                raise ValueError("invalid admission turn sources")
            if source.role == "assistant":
                compacted_derivative = selection.policy_version == 2 and turn == 1
                if compacted_derivative:
                    if source.positions != sources[0].positions:
                        raise ValueError("invalid admitted compaction provenance")
                else:
                    if (
                        len(source.positions) != 1
                        or source.positions[-1] >= target
                        or sources[turn - 1].positions[-1] != source.positions[0]
                    ):
                        raise ValueError("invalid admission completed exchange")
                    completed.append(source.positions[0])
        if completed != sorted(set(completed)) or sources[-1].positions[-1] != target:
            raise ValueError("invalid admission exchange order")
        selected = {position for source in sources for position in source.positions}
        omitted = [item.position for item in selection.omitted]

        def expected_omission(position: int) -> str:
            if position > target:
                return "after_target"
            if (
                selection.policy_version == 2
                and selection.compacted_through is not None
                and position <= selection.compacted_through
            ):
                return "replaced_by_author_compaction"
            return "no_completed_answer_or_required_link"

        if (
            omitted != sorted(set(omitted))
            or selected & set(omitted)
            or selected | set(omitted) != set(range(self.message_count))
            or any(
                item.reason != expected_omission(item.position)
                for item in selection.omitted
            )
        ):
            raise ValueError("admission must account for every existing message")
        return self


def record_admission(
    *,
    source_revision: int,
    message_count: int,
    exchange_index: int,
    selection: ContextSelection,
    context_max_bytes: int,
    request: ModelRequest,
    budget: Budget,
    memory_selected: bool,
    task_profile: TaskProfileAdmission | None = None,
    task_state: TaskStateAdmission | None = None,
) -> RequestAdmission:
    context = canonical_fingerprint(
        RequestContext(system=request.system, turns=request.turns)
    )
    return RequestAdmission(
        source_revision=source_revision,
        message_count=message_count,
        exchange_index=exchange_index,
        selection=selection,
        context_sha256=context.sha256,
        context_bytes=context.bytes,
        context_max_bytes=context_max_bytes,
        request=describe_request(request, budget),
        memory_selected=memory_selected,
        task_profile=task_profile,
        task_state=task_state,
    )
