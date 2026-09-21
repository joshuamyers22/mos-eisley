"""Read-only, text-free provenance for the next queued chat context."""

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.conversation import (
    conversation_base_system,
    conversation_config,
    prepare_conversation_request,
)
from mos_eisley.conversation_compaction import compaction_system
from mos_eisley.conversation_context import (
    ContextSelection,
    RequestContext,
    describe_selection,
    project_context,
)
from mos_eisley.conversation_limits import ContextByteLimit
from mos_eisley.conversation_memory import memory_system
from mos_eisley.conversation_pressure import (
    ContextPressureAdvisory,
    ContextPressureBoundary,
    ContextPressureBreakdown,
    ContextPressurePolicy,
    ContextPressureSnapshot,
    ProviderTokenPressure,
    assess_context_pressure,
    build_pressure_snapshot,
    describe_pressure,
    implicit_pressure_boundary,
    pressure_activity_totals,
    provider_token_pressure,
)
from mos_eisley.conversation_request_admission import (
    RequestBudgetPreview as RequestBudgetPreview,
)
from mos_eisley.conversation_request_admission import describe_request
from mos_eisley.conversation_state import RuntimeConversationState, SessionID
from mos_eisley.core.models import (
    Contract,
    Digest,
    canonical_bytes,
    canonical_fingerprint,
)


class ContextPreviewUnavailable(ValueError):
    """A safe notice when there is no queued chat target."""


class ContextPreview(Contract):
    schema_version: Literal[2, 3, 4] = 2
    session_id: SessionID
    revision: Annotated[int, Field(ge=0)]
    selection: ContextSelection
    context_sha256: Digest
    context_bytes: Annotated[int, Field(ge=1)]
    context_max_bytes: ContextByteLimit
    within_context_budget: bool
    request: RequestBudgetPreview
    memory_selected: bool
    active_work: bool
    compaction_before_bytes: Annotated[int | None, Field(ge=1)] = Field(
        default=None, exclude_if=lambda value: value is None
    )
    compaction_after_bytes: Annotated[int | None, Field(ge=1)] = Field(
        default=None, exclude_if=lambda value: value is None
    )
    pressure: ContextPressureSnapshot | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    pressure_advisory: ContextPressureAdvisory | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    def describe(self) -> str:
        lines = [
            f"Context preview • message {self.selection.message_index} "
            f"• revision {self.revision}",
            f"Context: {self.context_bytes}/{self.context_max_bytes} bytes "
            + (
                "(fits saved context budget)."
                if self.within_context_budget
                else "(over saved context budget)."
            ),
            f"Model request: {self.request.bytes}/{self.request.max_bytes} "
            "canonical bytes "
            + (
                "(fits request budget)."
                if self.request.within_budget
                else "(over request budget)."
            ),
            f"Route: {self.request.provider}/{self.request.model}; "
            f"effort {self.request.effort}.",
            f"Reserved: {self.request.output_reserve_bytes} output bytes; "
            f"{self.request.headroom_bytes} headroom bytes.",
            f"Selection policy: {self.selection.policy_version}; "
            + (
                "saved memory selected."
                if self.memory_selected
                else "no saved memory selected."
            ),
        ]
        lines.extend(describe_selection(self.selection))
        if self.compaction_before_bytes is not None:
            lines.append(
                f"Visible author compaction: {self.compaction_before_bytes} source "
                f"bytes → {self.compaction_after_bytes} model-visible bytes; "
                "originals retained."
            )
        if self.pressure is not None:
            lines.extend(describe_pressure(self.pressure, self.pressure_advisory))
        if self.active_work:
            lines.append("Active work may change this selection before dispatch.")
        lines.append(
            "Read-only preview of saved context; no work started. "
            "Memory, provider limits and recording availability "
            "are rechecked at dispatch."
        )
        return "\n".join(lines)


def _latest_pressure(
    state: RuntimeConversationState,
) -> tuple[ContextPressureSnapshot | None, ContextPressureAdvisory | None]:
    return next(
        (
            (
                entry.request_admission.pressure,
                entry.request_admission.pressure_advisory,
            )
            for entry in reversed(state.entries)
            if entry.request_admission is not None
            and entry.request_admission.pressure is not None
        ),
        (None, None),
    )


def preview_context(
    state: RuntimeConversationState,
    policy: ContextPressurePolicy | None = None,
) -> ContextPreview:
    index = next(
        (
            index
            for index, entry in enumerate(state.entries)
            if entry.status == "queued"
        ),
        None,
    )
    if index is None:
        raise ContextPreviewUnavailable("No queued message to preview.")
    if state.entries[index].is_review:
        raise ContextPreviewUnavailable(
            "The next queued message is a review; it uses its isolated review packet "
            "rather than chat history."
        )
    compaction = None if not state.author_compactions else state.author_compactions[-1]
    projected = project_context(state.entries, index, compaction)
    config = conversation_config(
        projected.turns,
        state.memory,
        task_system="" if compaction is None else compaction_system(compaction),
    )
    fingerprint = canonical_fingerprint(
        RequestContext(system=config.system, turns=projected.turns)
    )
    request, budget = prepare_conversation_request(config)
    request_preview = describe_request(request, budget)
    selected_policy = policy or state.context_pressure_policy or ContextPressurePolicy()
    pressure = build_pressure_snapshot(
        policy=selected_policy,
        source_revision=state.revision,
        request_ordinal=state.exchanges_consumed + 1,
        context_bytes=fingerprint.bytes,
        context_max_bytes=state.context_byte_limit,
        request_bytes=request_preview.bytes,
        request_max_bytes=request_preview.max_bytes,
        known_breakdown=ContextPressureBreakdown(
            base_system_bytes=len(
                conversation_base_system(state.memory).encode("utf-8")
            ),
            conversation_bytes=sum(
                len(canonical_bytes(turn)) for turn in projected.turns
            ),
            reusable_memory_bytes=len(memory_system(state.memory).encode("utf-8")),
            compaction_bytes=(
                0
                if compaction is None
                else len(compaction_system(compaction).encode("utf-8"))
            ),
        ),
        entries=state.entries,
        boundary=state.context_pressure_boundary,
        compaction_count=len(state.author_compactions),
    )
    previous, _ = _latest_pressure(state)
    pressure_advisory = assess_context_pressure(pressure, previous)
    return ContextPreview(
        schema_version=4,
        session_id=state.session_id,
        revision=state.revision,
        selection=projected.selection,
        context_sha256=fingerprint.sha256,
        context_bytes=fingerprint.bytes,
        context_max_bytes=state.context_byte_limit,
        within_context_budget=fingerprint.bytes <= state.context_byte_limit,
        request=request_preview,
        memory_selected=state.memory is not None,
        active_work=any(entry.status == "running" for entry in state.entries),
        compaction_before_bytes=(
            None if compaction is None else compaction.before_bytes
        ),
        compaction_after_bytes=(None if compaction is None else compaction.after_bytes),
        pressure=pressure,
        pressure_advisory=pressure_advisory,
    )


class ContextPressureStatus(Contract):
    schema_version: Literal[1] = 1
    session_id: SessionID
    revision: Annotated[int, Field(ge=0)]
    policy: ContextPressurePolicy
    boundary: ContextPressureBoundary
    latest_request: ContextPressureSnapshot | None = None
    advisory: ContextPressureAdvisory | None = None
    tool_calls_since_boundary: Annotated[int, Field(ge=0)]
    substantial_tool_calls_since_boundary: Annotated[int, Field(ge=0)]
    repeated_reads_since_boundary: Annotated[int, Field(ge=0)]
    compaction_count: Annotated[int, Field(ge=0, le=3)]
    tokens: ProviderTokenPressure | None = None
    read_only: Literal[True] = True

    def describe(self) -> str:
        lines = [
            f"Context pressure status • revision {self.revision} • "
            f"policy {self.policy.policy_id}",
            f"Boundary: {self.boundary.kind} at revision "
            f"{self.boundary.conversation_revision}; next message position "
            f"{self.boundary.next_message_position}.",
        ]
        if self.latest_request is None:
            lines.append("No model request has been measured in this session.")
        else:
            current = self.latest_request
            lines.append("Latest measured request:")
            lines.extend(describe_pressure(current, self.advisory))
        lines.append(
            f"Activity since boundary: {self.tool_calls_since_boundary} tool "
            f"call(s), {self.substantial_tool_calls_since_boundary} substantial, "
            f"{self.repeated_reads_since_boundary} repeated read(s); "
            f"{self.compaction_count} compaction(s) total."
        )
        if self.tokens is None:
            lines.append("Provider token counts: unavailable; no request measured.")
        else:
            lines.append(
                "Provider token counts: "
                f"{self.tokens.historical_confirmed_input_tokens} "
                f"confirmed input token(s) across "
                f"{self.tokens.historical_known_requests} request(s); "
                f"{self.tokens.historical_unknown_requests} unavailable."
            )
        lines.append(
            "Read-only advisory metadata; status inspection does not count as a "
            "tool call and grants no authority."
        )
        return "\n".join(lines)


def pressure_status(
    state: RuntimeConversationState,
    policy: ContextPressurePolicy | None = None,
) -> ContextPressureStatus:
    selected_policy = policy or state.context_pressure_policy or ContextPressurePolicy()
    latest, advisory = _latest_pressure(state)
    boundary = state.context_pressure_boundary or implicit_pressure_boundary()
    calls, substantial, repeated = pressure_activity_totals(state.entries, boundary)
    return ContextPressureStatus(
        session_id=state.session_id,
        revision=state.revision,
        policy=selected_policy,
        boundary=boundary,
        latest_request=latest,
        advisory=advisory,
        tool_calls_since_boundary=calls,
        substantial_tool_calls_since_boundary=substantial,
        repeated_reads_since_boundary=repeated,
        compaction_count=len(state.author_compactions),
        tokens=(
            None
            if latest is None
            else provider_token_pressure(state.entries, latest.request_bytes)
        ),
    )
