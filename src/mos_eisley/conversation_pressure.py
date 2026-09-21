"""Bounded, advisory-only context pressure for recorded author conversations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.agent import AgentUsage
from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import ToolCallBlock, ToolResultBlock, Turn


class ContextPressurePolicy(Contract):
    """Trusted evaluation policy; thresholds cause advice, never authority."""

    schema_version: Literal[1] = 1
    policy_id: Identifier = "context-pressure-v1"
    denominator: Literal["request_usable_input_bytes"] = "request_usable_input_bytes"
    context_threshold_basis_points: Annotated[int, Field(ge=1000, le=9000)] = 3500
    material_growth_basis_points: Annotated[int, Field(ge=100, le=5000)] = 500
    material_growth_bytes: Annotated[int, Field(ge=1024, le=256_000)] = 4096
    substantial_tool_result_bytes: Annotated[int, Field(ge=256, le=64_000)] = 4096
    substantial_tool_call_threshold: Annotated[int, Field(ge=1, le=128)] = 25
    repeated_read_threshold: Annotated[int, Field(ge=1, le=128)] = 3
    read_tool_ids: Annotated[tuple[Identifier, ...], Field(max_length=64)] = (
        "read_file",
        "read_text",
        "search",
        "search_files",
        "find",
        "grep",
        "list_files",
    )
    substantial_call_rule: Literal["executed_tool_result_utf8_bytes_gte_threshold"] = (
        "executed_tool_result_utf8_bytes_gte_threshold"
    )
    repeated_read_rule: Literal[
        "same_allowlisted_tool_and_canonical_args_after_first_since_boundary"
    ] = "same_allowlisted_tool_and_canonical_args_after_first_since_boundary"
    token_estimate_rule: Literal["ceil_canonical_request_utf8_bytes_div_4"] = (
        "ceil_canonical_request_utf8_bytes_div_4"
    )
    advisory_only: Literal[True] = True
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def unique_read_tools(self) -> Self:
        if len(set(self.read_tool_ids)) != len(self.read_tool_ids):
            raise ValueError("pressure read-tool IDs must be unique")
        return self


class ContextPressureBreakdown(Contract):
    base_system_bytes: Annotated[int, Field(ge=0)] = 0
    conversation_bytes: Annotated[int, Field(ge=0)] = 0
    reusable_memory_bytes: Annotated[int, Field(ge=0)] = 0
    task_profile_bytes: Annotated[int, Field(ge=0)] = 0
    checkpoint_bytes: Annotated[int, Field(ge=0)] = 0
    compaction_bytes: Annotated[int, Field(ge=0)] = 0
    tool_schema_bytes: Annotated[int, Field(ge=0)] = 0
    request_envelope_bytes: Annotated[int, Field(ge=0)] = 0

    @property
    def total_bytes(self) -> int:
        return sum(self.model_dump(mode="python").values())


class ConversationPressureActivity(Contract):
    schema_version: Literal[1] = 1
    tool_calls: Annotated[int, Field(ge=0, le=128)] = 0
    substantial_tool_calls: Annotated[int, Field(ge=0, le=128)] = 0
    read_fingerprints: Annotated[tuple[Digest, ...], Field(max_length=128)] = ()

    @model_validator(mode="after")
    def bounded_counts(self) -> Self:
        if (
            self.substantial_tool_calls > self.tool_calls
            or len(self.read_fingerprints) > self.tool_calls
        ):
            raise ValueError("pressure activity counts exceed executed tool calls")
        return self


class ContextPressureBoundary(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["session_start", "checkpoint", "continuation", "compaction"]
    conversation_revision: Annotated[int, Field(ge=0)]
    next_message_position: Annotated[int, Field(ge=0, le=16)]
    request_bytes: Annotated[int, Field(ge=0)]
    compaction_count: Annotated[int, Field(ge=0, le=3)]


class ProviderTokenPressure(Contract):
    current_status: Literal["unavailable"] = "unavailable"
    current_input_tokens: None = None
    local_estimated_input_tokens: Annotated[int, Field(ge=1)]
    estimate_rule: Literal["ceil_canonical_request_utf8_bytes_div_4"] = (
        "ceil_canonical_request_utf8_bytes_div_4"
    )
    historical_confirmed_input_tokens: Annotated[int, Field(ge=0)]
    historical_known_requests: Annotated[int, Field(ge=0)]
    historical_unknown_requests: Annotated[int, Field(ge=0)]


class ContextPressureSnapshot(Contract):
    schema_version: Literal[1] = 1
    policy: ContextPressurePolicy
    source_revision: Annotated[int, Field(ge=0)]
    request_ordinal: Annotated[int, Field(ge=1, le=16)]
    context_bytes: Annotated[int, Field(ge=1)]
    context_max_bytes: Annotated[int, Field(ge=1)]
    context_available_bytes: Annotated[int, Field(ge=0)]
    context_overage_bytes: Annotated[int, Field(ge=0)]
    request_bytes: Annotated[int, Field(ge=1)]
    request_max_bytes: Annotated[int, Field(ge=1)]
    request_available_bytes: Annotated[int, Field(ge=0)]
    request_overage_bytes: Annotated[int, Field(ge=0)]
    request_usage_basis_points: Annotated[int, Field(ge=0)]
    breakdown: ContextPressureBreakdown
    boundary: ContextPressureBoundary
    growth_since_boundary_bytes: Annotated[int, Field(ge=-2_000_000, le=2_000_000)]
    tool_calls_since_boundary: Annotated[int, Field(ge=0)]
    substantial_tool_calls_since_boundary: Annotated[int, Field(ge=0)]
    repeated_reads_since_boundary: Annotated[int, Field(ge=0)]
    compaction_count: Annotated[int, Field(ge=0, le=3)]
    compactions_since_boundary: Annotated[int, Field(ge=0, le=3)]
    tokens: ProviderTokenPressure
    advisory_only: Literal[True] = True
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_accounting(self) -> Self:
        if self.breakdown.total_bytes != self.request_bytes:
            raise ValueError("pressure categories do not match complete request bytes")
        if self.context_available_bytes != max(
            0, self.context_max_bytes - self.context_bytes
        ) or self.context_overage_bytes != max(
            0, self.context_bytes - self.context_max_bytes
        ):
            raise ValueError("pressure context capacity accounting is inconsistent")
        if self.request_available_bytes != max(
            0, self.request_max_bytes - self.request_bytes
        ) or self.request_overage_bytes != max(
            0, self.request_bytes - self.request_max_bytes
        ):
            raise ValueError("pressure request capacity accounting is inconsistent")
        if self.request_usage_basis_points != (
            self.request_bytes * 10_000 // self.request_max_bytes
        ):
            raise ValueError("pressure denominator differs from its policy")
        if self.growth_since_boundary_bytes != (
            self.request_bytes - self.boundary.request_bytes
        ):
            raise ValueError("pressure growth differs from its boundary")
        if self.compactions_since_boundary != (
            self.compaction_count - self.boundary.compaction_count
        ):
            raise ValueError("pressure compaction delta differs from its boundary")
        if self.compactions_since_boundary < 0:
            raise ValueError("pressure boundary cannot have a future compaction count")
        if self.tokens.local_estimated_input_tokens != (self.request_bytes + 3) // 4:
            raise ValueError("pressure token estimate differs from its stated rule")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


PressureReason = Literal[
    "request_context_threshold_crossed",
    "substantial_tool_threshold_crossed",
    "repeated_read_threshold_crossed",
    "material_request_growth",
    "boundary_changed",
    "compaction_changed",
]


class ContextPressureAdvisory(Contract):
    schema_version: Literal[1] = 1
    event_id: Digest
    snapshot_sha256: Digest
    previous_snapshot_sha256: Digest | None = None
    reasons: Annotated[tuple[PressureReason, ...], Field(min_length=1, max_length=6)]
    recommendation: Literal[
        "assess_context",
        "consider_author_compaction",
        "consider_checkpoint_continuation",
    ]
    automatic_stop: Literal[False] = False
    automatic_compaction: Literal[False] = False
    automatic_delegation: Literal[False] = False
    approval_required: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def reproducible_event(self) -> Self:
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("pressure advisory reasons must be unique")
        expected = pressure_event_id(
            self.snapshot_sha256, self.previous_snapshot_sha256, self.reasons
        )
        if self.event_id != expected:
            raise ValueError("pressure advisory identity does not reproduce")
        return self


class PressureEntry(Protocol):
    @property
    def usage(self) -> AgentUsage | None: ...

    @property
    def pressure_activity(self) -> ConversationPressureActivity | None: ...


class ReadOperationIdentity(Contract):
    tool_id: Identifier
    args: dict[str, JsonValue]


def pressure_event_id(
    snapshot_sha256: str,
    previous_snapshot_sha256: str | None,
    reasons: tuple[PressureReason, ...],
) -> str:
    previous = "none" if previous_snapshot_sha256 is None else previous_snapshot_sha256
    return digest((snapshot_sha256 + previous + "\0".join(reasons)).encode("ascii"))


def measure_pressure_activity(
    turns: Sequence[Turn], policy: ContextPressurePolicy
) -> ConversationPressureActivity:
    calls: dict[str, ToolCallBlock] = {}
    results: list[ToolResultBlock] = []
    for turn in turns:
        for block in turn.blocks:
            if isinstance(block, ToolCallBlock):
                calls[block.id] = block
            elif isinstance(block, ToolResultBlock):
                results.append(block)
    read_tools = set(policy.read_tool_ids)
    reads: list[str] = []
    substantial = 0
    for result in results:
        call = calls.get(result.call_id)
        if call is None:
            raise ValueError("pressure activity result lacks its tool call")
        if len(result.content.encode("utf-8")) >= policy.substantial_tool_result_bytes:
            substantial += 1
        if call.name in read_tools:
            reads.append(
                digest(
                    canonical_bytes(
                        ReadOperationIdentity(tool_id=call.name, args=call.args)
                    )
                )
            )
    return ConversationPressureActivity(
        tool_calls=len(results),
        substantial_tool_calls=substantial,
        read_fingerprints=tuple(reads),
    )


def pressure_activity_totals(
    entries: Sequence[PressureEntry], boundary: ContextPressureBoundary
) -> tuple[int, int, int]:
    activities = tuple(
        item.pressure_activity
        for item in entries[boundary.next_message_position :]
        if item.pressure_activity is not None
    )
    fingerprints = tuple(
        fingerprint for item in activities for fingerprint in item.read_fingerprints
    )
    repeated = sum(count - 1 for count in Counter(fingerprints).values())
    return (
        sum(item.tool_calls for item in activities),
        sum(item.substantial_tool_calls for item in activities),
        repeated,
    )


def provider_token_pressure(
    entries: Sequence[PressureEntry], request_bytes: int
) -> ProviderTokenPressure:
    usages = tuple(item.usage for item in entries if item.usage is not None)
    known = tuple(item for item in usages if item.unit == "tokens")
    return ProviderTokenPressure(
        local_estimated_input_tokens=(request_bytes + 3) // 4,
        historical_confirmed_input_tokens=sum(item.billed_input for item in known),
        historical_known_requests=len(known),
        historical_unknown_requests=len(usages) - len(known),
    )


def make_pressure_boundary(
    *,
    kind: Literal["checkpoint", "continuation", "compaction"],
    conversation_revision: int,
    next_message_position: int,
    latest_request_bytes: int,
    compaction_count: int,
) -> ContextPressureBoundary:
    return ContextPressureBoundary(
        kind=kind,
        conversation_revision=conversation_revision,
        next_message_position=next_message_position,
        request_bytes=latest_request_bytes,
        compaction_count=compaction_count,
    )


def implicit_pressure_boundary() -> ContextPressureBoundary:
    return ContextPressureBoundary(
        kind="session_start",
        conversation_revision=0,
        next_message_position=0,
        request_bytes=0,
        compaction_count=0,
    )


def build_pressure_snapshot(
    *,
    policy: ContextPressurePolicy,
    source_revision: int,
    request_ordinal: int,
    context_bytes: int,
    context_max_bytes: int,
    request_bytes: int,
    request_max_bytes: int,
    known_breakdown: ContextPressureBreakdown,
    entries: Sequence[PressureEntry],
    boundary: ContextPressureBoundary | None,
    compaction_count: int,
) -> ContextPressureSnapshot:
    if known_breakdown.request_envelope_bytes != 0:
        raise ValueError("pressure envelope bytes must be derived locally")
    known = known_breakdown.total_bytes
    if known > request_bytes:
        raise ValueError("pressure categories exceed the complete request")
    breakdown = known_breakdown.model_copy(
        update={"request_envelope_bytes": request_bytes - known}
    )
    selected_boundary = boundary or implicit_pressure_boundary()
    calls, substantial, repeated = pressure_activity_totals(entries, selected_boundary)
    return ContextPressureSnapshot(
        policy=policy,
        source_revision=source_revision,
        request_ordinal=request_ordinal,
        context_bytes=context_bytes,
        context_max_bytes=context_max_bytes,
        context_available_bytes=max(0, context_max_bytes - context_bytes),
        context_overage_bytes=max(0, context_bytes - context_max_bytes),
        request_bytes=request_bytes,
        request_max_bytes=request_max_bytes,
        request_available_bytes=max(0, request_max_bytes - request_bytes),
        request_overage_bytes=max(0, request_bytes - request_max_bytes),
        request_usage_basis_points=request_bytes * 10_000 // request_max_bytes,
        breakdown=breakdown,
        boundary=selected_boundary,
        growth_since_boundary_bytes=request_bytes - selected_boundary.request_bytes,
        tool_calls_since_boundary=calls,
        substantial_tool_calls_since_boundary=substantial,
        repeated_reads_since_boundary=repeated,
        compaction_count=compaction_count,
        compactions_since_boundary=(
            compaction_count - selected_boundary.compaction_count
        ),
        tokens=provider_token_pressure(entries, request_bytes),
    )


def assess_context_pressure(
    current: ContextPressureSnapshot,
    previous: ContextPressureSnapshot | None,
) -> ContextPressureAdvisory | None:
    policy = current.policy
    reasons: list[PressureReason] = []
    previous_usage = 0 if previous is None else previous.request_usage_basis_points
    if (
        previous_usage
        < policy.context_threshold_basis_points
        <= current.request_usage_basis_points
    ):
        reasons.append("request_context_threshold_crossed")
    previous_substantial = (
        0 if previous is None else previous.substantial_tool_calls_since_boundary
    )
    if (
        previous_substantial
        < policy.substantial_tool_call_threshold
        <= current.substantial_tool_calls_since_boundary
    ):
        reasons.append("substantial_tool_threshold_crossed")
    previous_reads = 0 if previous is None else previous.repeated_reads_since_boundary
    if (
        previous_reads
        < policy.repeated_read_threshold
        <= current.repeated_reads_since_boundary
    ):
        reasons.append("repeated_read_threshold_crossed")
    if previous is not None:
        growth = current.request_bytes - previous.request_bytes
        growth_basis_points = abs(
            current.request_usage_basis_points - previous.request_usage_basis_points
        )
        if (
            abs(growth) >= policy.material_growth_bytes
            and growth_basis_points >= policy.material_growth_basis_points
        ):
            reasons.append("material_request_growth")
        if current.boundary != previous.boundary:
            reasons.append("boundary_changed")
        if current.compaction_count != previous.compaction_count:
            reasons.append("compaction_changed")
    if not reasons:
        return None
    ordered = tuple(reasons)
    recommendation: Literal[
        "assess_context",
        "consider_author_compaction",
        "consider_checkpoint_continuation",
    ] = "assess_context"
    if current.boundary.kind == "checkpoint":
        recommendation = "consider_checkpoint_continuation"
    elif (
        current.request_usage_basis_points >= policy.context_threshold_basis_points
        and current.compaction_count < 3
    ):
        recommendation = "consider_author_compaction"
    previous_sha = None if previous is None else previous.sha256
    return ContextPressureAdvisory(
        event_id=pressure_event_id(current.sha256, previous_sha, ordered),
        snapshot_sha256=current.sha256,
        previous_snapshot_sha256=previous_sha,
        reasons=ordered,
        recommendation=recommendation,
    )


def describe_pressure(
    snapshot: ContextPressureSnapshot,
    advisory: ContextPressureAdvisory | None,
) -> list[str]:
    breakdown = snapshot.breakdown
    token = snapshot.tokens
    lines = [
        "Pressure policy: "
        f"{snapshot.policy.policy_id}; denominator "
        f"{snapshot.policy.denominator}; advisory only.",
        f"Complete request pressure: {snapshot.request_bytes}/"
        f"{snapshot.request_max_bytes} bytes "
        f"({snapshot.request_usage_basis_points / 100:.2f}%); "
        f"{snapshot.request_available_bytes} bytes available.",
        f"Saved context capacity: {snapshot.context_bytes}/"
        f"{snapshot.context_max_bytes} bytes; "
        f"{snapshot.context_available_bytes} bytes available.",
        "Request byte categories: "
        f"base {breakdown.base_system_bytes}, "
        f"conversation {breakdown.conversation_bytes}, "
        f"memory {breakdown.reusable_memory_bytes}, "
        f"task profile {breakdown.task_profile_bytes}, "
        f"checkpoint {breakdown.checkpoint_bytes}, "
        f"compaction {breakdown.compaction_bytes}, "
        f"tool schemas {breakdown.tool_schema_bytes}, "
        f"envelope {breakdown.request_envelope_bytes} bytes.",
        f"Growth since {snapshot.boundary.kind} boundary: "
        f"{snapshot.growth_since_boundary_bytes:+d} request bytes.",
        f"Activity since boundary: {snapshot.tool_calls_since_boundary} tool "
        f"call(s), {snapshot.substantial_tool_calls_since_boundary} substantial; "
        f"{snapshot.repeated_reads_since_boundary} repeated read(s); "
        f"{snapshot.compaction_count} compaction(s) total.",
        f"Token estimate: {token.local_estimated_input_tokens} input tokens "
        f"({token.estimate_rule}); current provider count unavailable. Historical "
        f"provider input: {token.historical_confirmed_input_tokens} confirmed "
        f"token(s) across {token.historical_known_requests} request(s), "
        f"{token.historical_unknown_requests} unavailable.",
    ]
    if advisory is not None:
        lines.append(
            "Pressure advisory: "
            + ", ".join(advisory.reasons)
            + f"; recommendation {advisory.recommendation}. No automatic stop, "
            "compaction, delegation or approval request."
        )
    else:
        lines.append("Pressure advisory: no threshold crossing or material change.")
    return lines
