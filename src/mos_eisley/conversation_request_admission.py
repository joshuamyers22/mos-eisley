"""Text-free records of admitted chat inputs, saved before provider dispatch."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_context import ContextSelection, RequestContext
from mos_eisley.conversation_limits import ContextByteLimit
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

    @model_validator(mode="after")
    def admitted_selection(self) -> Self:
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
        omitted = [item.position for item in selection.omitted]
        if (
            omitted != sorted(set(omitted))
            or selected & set(omitted)
            or selected | set(omitted) != set(range(self.message_count))
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
    )
