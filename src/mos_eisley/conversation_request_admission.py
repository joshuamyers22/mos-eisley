"""Text-free records of admitted chat inputs, saved before provider dispatch."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_context import ContextSelection, RequestContext
from mos_eisley.conversation_limits import ContextByteLimit
from mos_eisley.conversation_pressure import (
    ContextPressureAdvisory,
    ContextPressureSnapshot,
)
from mos_eisley.conversation_task_profile import (
    ContextClassification,
    TaskContinuationAdmission,
    TaskProfileAdmission,
)
from mos_eisley.core.budget import Budget
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_fingerprint
from mos_eisley.core.protocol import Effort, ModelRequest


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


class AuthorCompactionAdmission(Contract):
    compaction_id: Digest
    revision: Annotated[int, Field(ge=1, le=3)]
    compacted_through: Annotated[int, Field(ge=0, le=15)]
    source_revision: Annotated[int, Field(ge=0)]
    before_bytes: Annotated[int, Field(ge=1)]
    after_bytes: Annotated[int, Field(ge=1)]
    prior_compaction_sha256: Digest | None = None
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def reduced_context(self) -> Self:
        if self.after_bytes >= self.before_bytes:
            raise ValueError("admitted compaction must reduce context bytes")
        if (self.revision == 1) != (self.prior_compaction_sha256 is None):
            raise ValueError("admitted compaction lineage is incomplete")
        return self


class RequestAdmission(Contract):
    """An admission record is not proof of transmission or provider receipt."""

    schema_version: Literal[1, 2, 3, 4, 5, 6] = 2
    source_revision: Annotated[int, Field(ge=0)]
    message_count: Annotated[int, Field(ge=1, le=16)]
    exchange_index: Annotated[int, Field(ge=0, le=15)]
    selection: ContextSelection
    context_sha256: Digest
    context_bytes: Annotated[int, Field(ge=1)]
    context_max_bytes: ContextByteLimit
    request: RequestBudgetPreview
    memory_selected: bool
    context_classification: ContextClassification | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    task_profile: TaskProfileAdmission | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    task_continuation: TaskContinuationAdmission | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    author_compaction: AuthorCompactionAdmission | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    pressure: ContextPressureSnapshot | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    pressure_advisory: ContextPressureAdvisory | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def admitted_selection(self) -> Self:
        if self.schema_version == 1:
            if (
                self.context_classification is not None
                or self.task_profile is not None
                or self.task_continuation is not None
                or self.author_compaction is not None
                or self.pressure is not None
                or self.pressure_advisory is not None
            ):
                raise ValueError("schema-1 admission cannot contain scoped context")
        elif self.schema_version == 2 and (
            self.task_continuation is not None or self.author_compaction is not None
        ):
            raise ValueError("schema-2 admission cannot contain derived context")
        elif self.schema_version == 3 and (
            self.task_continuation is None or self.author_compaction is not None
        ):
            raise ValueError("schema-3 admission requires only continuation context")
        elif self.schema_version == 4 and self.author_compaction is None:
            raise ValueError("schema-4 admission requires author compaction")
        elif self.schema_version == 5 and self.pressure is None:
            raise ValueError("schema-5 admission requires context pressure")
        elif self.schema_version == 6 and (
            self.pressure is None
            or self.task_continuation is None
            or self.task_profile is None
            or self.task_profile.acquisition is None
        ):
            raise ValueError(
                "schema-6 admission requires acquired continuation profile"
            )
        elif self.context_classification is None:
            raise ValueError("scoped admission requires context classification")
        elif self.memory_selected != bool(self.context_classification.reusable_memory):
            raise ValueError("memory selection does not match its classification")
        if (
            self.task_profile is None
            and self.context_classification is not None
            and (
                self.context_classification.task_instruction_ids
                or self.context_classification.temporary_task_state_ids
            )
        ):
            raise ValueError("task context classification requires a task profile")
        if self.task_profile is not None and self.context_classification is not None:
            classified = (
                self.context_classification.task_instruction_ids
                + self.context_classification.temporary_task_state_ids
            )
            if set(classified) != set(self.task_profile.selected_instruction_ids):
                raise ValueError(
                    "task context classification does not match admitted profile"
                )
        if self.context_classification is not None:
            selected = self.context_classification.checkpoint_selected
            if selected != (self.task_continuation is not None):
                raise ValueError(
                    "checkpoint classification does not match continuation admission"
                )
            if self.task_continuation is not None and (
                self.context_classification.continuation_claim_id
                != self.task_continuation.claim_id
            ):
                raise ValueError("continuation claim differs from classification")
        acquisition = (
            None if self.task_profile is None else self.task_profile.acquisition
        )
        if self.schema_version < 6 and acquisition is not None:
            raise ValueError("legacy admission cannot contain profile acquisition")
        if acquisition is not None:
            continuation = self.task_continuation
            if continuation is None or (
                acquisition.checkpoint_id != continuation.checkpoint_id
                or acquisition.checkpoint_revision != continuation.checkpoint_revision
                or acquisition.checkpoint_sha256 != continuation.checkpoint_sha256
                or acquisition.work_unit != continuation.selected_work_unit
            ):
                raise ValueError(
                    "profile acquisition differs from continuation admission"
                )
        if self.schema_version < 5 and (
            self.pressure is not None or self.pressure_advisory is not None
        ):
            raise ValueError("legacy admission cannot contain context pressure")
        if self.pressure is not None:
            pressure = self.pressure
            if (
                pressure.source_revision != self.source_revision
                or pressure.request_ordinal != self.exchange_index + 1
                or pressure.context_bytes != self.context_bytes
                or pressure.context_max_bytes != self.context_max_bytes
                or pressure.request_bytes != self.request.bytes
                or pressure.request_max_bytes != self.request.max_bytes
            ):
                raise ValueError("pressure snapshot differs from request admission")
            if self.pressure_advisory is not None and (
                self.pressure_advisory.snapshot_sha256 != pressure.sha256
            ):
                raise ValueError("pressure advisory differs from its snapshot")
        if (
            self.context_bytes > self.context_max_bytes
            or not self.request.within_budget
        ):
            raise ValueError("request admission requires both byte budgets to fit")
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
        compacted = set(selection.compacted_positions)
        if self.author_compaction is None:
            if selection.compaction_id is not None or compacted:
                raise ValueError("selection names an unadmitted author compaction")
        elif (
            selection.compaction_id != self.author_compaction.compaction_id
            or selection.compacted_positions
            != tuple(range(self.author_compaction.compacted_through + 1))
            or self.author_compaction.compacted_through >= target
        ):
            raise ValueError("selection differs from its admitted author compaction")
        omitted = [item.position for item in selection.omitted]
        if (
            omitted != sorted(set(omitted))
            or selected & set(omitted)
            or selected & compacted
            or compacted & set(omitted)
            or selected | compacted | set(omitted) != set(range(self.message_count))
            or any(
                (item.reason == "after_target") != (item.position > target)
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
    context_classification: ContextClassification,
    task_profile: TaskProfileAdmission | None = None,
    task_continuation: TaskContinuationAdmission | None = None,
    author_compaction: AuthorCompactionAdmission | None = None,
    pressure: ContextPressureSnapshot | None = None,
    pressure_advisory: ContextPressureAdvisory | None = None,
) -> RequestAdmission:
    context = canonical_fingerprint(
        RequestContext(system=request.system, turns=request.turns)
    )
    return RequestAdmission(
        schema_version=(
            6
            if task_profile is not None and task_profile.acquisition is not None
            else 5
            if pressure is not None
            else 4
            if author_compaction is not None
            else 3
            if task_continuation is not None
            else 2
        ),
        source_revision=source_revision,
        message_count=message_count,
        exchange_index=exchange_index,
        selection=selection,
        context_sha256=context.sha256,
        context_bytes=context.bytes,
        context_max_bytes=context_max_bytes,
        request=describe_request(request, budget),
        memory_selected=memory_selected,
        context_classification=context_classification,
        task_profile=task_profile,
        task_continuation=task_continuation,
        author_compaction=author_compaction,
        pressure=pressure,
        pressure_advisory=pressure_advisory,
    )
