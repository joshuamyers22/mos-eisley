"""Bounded, advisory-only context pressure measurements for recorded sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_state import RuntimeConversationState
from mos_eisley.core.budget import Budget
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.protocol import (
    ModelRequest,
    ReasoningBlock,
    ToolResultBlock,
)
from mos_eisley.task_state import (
    ContextInputBreakdown,
    CumulativeContextMetrics,
    PartialTotal,
)
from mos_eisley.task_state_acquisition import RuntimeTaskState


def _serialized_string_bytes(value: str) -> int:
    """Count a string's bytes as embedded in canonical JSON, excluding quotes."""
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return len(encoded) - 2


class ContextPressurePolicy(Contract):
    """Trusted, versioned evaluation settings; thresholds grant no authority."""

    schema_version: Literal[1] = 1
    context_advisory_basis_points: Annotated[int, Field(ge=3000, le=4000)] = 3500
    substantial_tool_call_threshold: Annotated[int, Field(ge=20, le=30)] = 25
    denominator_rule: Literal["usable_model_input_bytes_v1"] = (
        "usable_model_input_bytes_v1"
    )
    substantial_call_rule: Literal["completed_noninspection_tool_calls_v1"] = (
        "completed_noninspection_tool_calls_v1"
    )
    token_estimate_rule: Literal["ceil_utf8_bytes_div_4_v1"] = (
        "ceil_utf8_bytes_div_4_v1"
    )
    max_advisory_events: Annotated[int, Field(ge=1, le=32)] = 16


class CurrentContextPressure(Contract):
    request_sha256: Digest
    categories: ContextInputBreakdown
    request_bytes: Annotated[int, Field(ge=1)]
    request_capacity_bytes: Annotated[int, Field(ge=1)]
    request_available_bytes: Annotated[int, Field(ge=0)]
    request_overflow_bytes: Annotated[int, Field(ge=0)]
    request_usage_basis_points: Annotated[int, Field(ge=0)]
    local_input_token_estimate: Annotated[int, Field(ge=1)]
    provider_input_tokens: None = None
    context_bytes: Annotated[int, Field(ge=1)]
    context_capacity_bytes: Annotated[int, Field(ge=1)]
    context_available_bytes: Annotated[int, Field(ge=0)]
    context_overflow_bytes: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def exact_capacity(self) -> Self:
        if self.categories.total_bytes != self.request_bytes:
            raise ValueError("pressure categories do not match request bytes")
        if self.request_available_bytes != max(
            0, self.request_capacity_bytes - self.request_bytes
        ) or self.request_overflow_bytes != max(
            0, self.request_bytes - self.request_capacity_bytes
        ):
            raise ValueError("request pressure capacity is inconsistent")
        if self.context_available_bytes != max(
            0, self.context_capacity_bytes - self.context_bytes
        ) or self.context_overflow_bytes != max(
            0, self.context_bytes - self.context_capacity_bytes
        ):
            raise ValueError("context pressure capacity is inconsistent")
        if self.request_usage_basis_points != (
            self.request_bytes * 10_000 // self.request_capacity_bytes
        ):
            raise ValueError("request pressure denominator is inconsistent")
        if self.local_input_token_estimate != (self.request_bytes + 3) // 4:
            raise ValueError("local token estimate is inconsistent")
        return self


class PressureAdvisory(Contract):
    code: Literal[
        "context_usage_threshold",
        "substantial_tool_call_threshold",
        "hard_input_limit",
    ]
    observed: Annotated[int, Field(ge=0)]
    threshold: Annotated[int, Field(ge=0)]
    unit: Literal["basis_points", "calls", "bytes"]
    assessment: Literal[
        "assess",
        "consider_author_compaction",
        "offer_fresh_continuation",
        "honor_hard_admission_limit",
    ]
    automatic_action: Literal[False] = False
    grants_authority: Literal[False] = False


class ContextPressureReport(Contract):
    """Content-free status projection; it does not mutate or authorize work."""

    schema_version: Literal[1] = 1
    source_revision: Annotated[int, Field(ge=0)]
    policy: ContextPressurePolicy
    role: Literal["author"] = "author"
    milestone_state: Literal["queued", "active", "terminal", "unavailable"] = (
        "unavailable"
    )
    boundary: Literal["checkpoint", "session_start"]
    boundary_sha256: Digest
    current: CurrentContextPressure | None = None
    baseline: CumulativeContextMetrics | None = None
    admitted_growth_request_count: Annotated[int, Field(ge=0)]
    admitted_growth_input_bytes: Annotated[int, Field(ge=0)]
    projected_growth_input_bytes: Annotated[int, Field(ge=0)]
    provider_input: PartialTotal
    provider_output: PartialTotal
    cached_input: PartialTotal
    repeated_reads: Annotated[int, Field(ge=0)]
    substantial_tool_calls: Annotated[int, Field(ge=0)]
    compactions: Annotated[int, Field(ge=0)]
    status: Literal["normal", "advisory", "hard_limit"]
    advisories: Annotated[tuple[PressureAdvisory, ...], Field(max_length=3)] = ()
    critic_metrics_included: Literal[False] = False
    critic_compaction_allowed: Literal[False] = False
    automatic_delegation: Literal[False] = False
    automatic_action: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def consistent_report(self) -> Self:
        projected = self.admitted_growth_input_bytes + (
            0 if self.current is None else self.current.request_bytes
        )
        if self.projected_growth_input_bytes != projected:
            raise ValueError("projected pressure growth is inconsistent")
        expected_status = (
            "hard_limit"
            if any(item.code == "hard_input_limit" for item in self.advisories)
            else "advisory"
            if self.advisories
            else "normal"
        )
        if self.status != expected_status:
            raise ValueError("pressure status does not match its advisories")
        if len({item.code for item in self.advisories}) != len(self.advisories):
            raise ValueError("pressure advisory codes must be unique")
        expected_items = (
            self.baseline.admitted_request_count if self.baseline else 0
        ) + self.admitted_growth_request_count
        for total in (self.provider_input, self.provider_output, self.cached_input):
            if total.known_items + total.unknown_items != expected_items:
                raise ValueError("provider totals must account for admitted requests")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))

    def describe(self) -> str:
        lines = [
            f"Context pressure • {self.status} • policy {self.policy.schema_version}",
            f"Boundary: {self.boundary}; {self.admitted_growth_request_count} admitted "
            f"request(s), {self.admitted_growth_input_bytes} serialized input bytes "
            "since that boundary.",
        ]
        if self.current is None:
            lines.append("No queued author request is available for exact measurement.")
        else:
            current = self.current
            lines.extend(
                (
                    f"Upcoming model request: {current.request_bytes}/"
                    f"{current.request_capacity_bytes} bytes; "
                    f"{current.request_available_bytes} available; "
                    f"{current.request_overflow_bytes} overflow.",
                    f"Saved context: {current.context_bytes}/"
                    f"{current.context_capacity_bytes} bytes; "
                    f"{current.context_available_bytes} available; "
                    f"{current.context_overflow_bytes} overflow.",
                    "Local token estimate: "
                    f"{current.local_input_token_estimate} "
                    f"({self.policy.token_estimate_rule}); provider input tokens "
                    "are unavailable before dispatch.",
                    "Upcoming categories: " + _describe_categories(current.categories),
                    f"Projected serialized growth: "
                    f"{self.projected_growth_input_bytes} bytes.",
                )
            )
        if self.baseline is None:
            lines.append("Checkpoint context-metric baseline: unavailable.")
        else:
            lines.append(
                "Checkpoint categories: "
                + _describe_categories(self.baseline.local_input_breakdown)
                + f" across {self.baseline.request_count} request(s)."
            )
        lines.extend(
            (
                "Provider input tokens: " + _describe_partial(self.provider_input),
                "Provider output tokens: " + _describe_partial(self.provider_output),
                "Cached input tokens: " + _describe_partial(self.cached_input),
                f"Signals: {self.substantial_tool_calls} substantial tool call(s), "
                f"{self.repeated_reads} repeated read(s), "
                f"{self.compactions} compaction(s).",
                f"Rules: denominator {self.policy.denominator_rule}; substantial "
                f"calls {self.policy.substantial_call_rule}; advisory at "
                f"{self.policy.context_advisory_basis_points / 100:.2f}% or "
                f"{self.policy.substantial_tool_call_threshold} calls.",
            )
        )
        if self.advisories:
            lines.append(
                "Assessment: "
                + ", ".join(item.assessment for item in self.advisories)
                + "."
            )
        lines.append(
            "Advisory metadata only: no automatic stop, compaction, approval, "
            "delegation, tool, credential, spending, or execution authority. Hard "
            "admission limits remain authoritative; critic/judge context is isolated."
        )
        return "\n".join(lines)


def _describe_categories(categories: ContextInputBreakdown) -> str:
    return (
        "; ".join(
            (
                f"system {categories.system_instruction_bytes}",
                f"tools {categories.tool_schema_bytes}",
                f"guidance {categories.project_guidance_bytes}",
                f"memory {categories.selected_memory_bytes}",
                f"checkpoint {categories.checkpoint_bytes}",
                f"conversation {categories.conversation_bytes}",
                f"reasoning {categories.retained_reasoning_bytes}",
                f"tool output {categories.tool_output_bytes}",
                f"other {categories.other_bytes}",
            )
        )
        + " bytes"
    )


def _describe_partial(total: PartialTotal) -> str:
    return (
        f"{total.value} known across {total.known_items} request(s); "
        f"unavailable for {total.unknown_items} request(s)."
    )


def measure_current_context(
    request: ModelRequest,
    budget: Budget,
    *,
    context_bytes: int,
    context_capacity_bytes: int,
    project_guidance: str = "",
    selected_memory: str = "",
    checkpoint: str = "",
) -> CurrentContextPressure:
    """Split one exact serialized request into non-overlapping byte categories."""
    system_total = _serialized_string_bytes(request.system)
    guidance_bytes = _serialized_string_bytes(project_guidance)
    memory_bytes = _serialized_string_bytes(selected_memory)
    checkpoint_bytes = _serialized_string_bytes(checkpoint)
    selected_system_bytes = guidance_bytes + memory_bytes + checkpoint_bytes
    if selected_system_bytes > system_total:
        raise ValueError("selected context segments exceed the request system input")

    tool_schema_bytes = sum(len(canonical_bytes(item)) for item in request.tools)
    conversation_bytes = 0
    reasoning_bytes = 0
    tool_output_bytes = 0
    for turn in request.turns:
        for block in turn.blocks:
            block_bytes = len(canonical_bytes(block))
            if isinstance(block, ReasoningBlock):
                reasoning_bytes += block_bytes
            elif isinstance(block, ToolResultBlock):
                tool_output_bytes += block_bytes
            else:
                conversation_bytes += block_bytes

    request_bytes = len(canonical_bytes(request))
    measured = (
        system_total
        + tool_schema_bytes
        + conversation_bytes
        + reasoning_bytes
        + tool_output_bytes
    )
    if measured > request_bytes:
        raise ValueError("context category measurement exceeds serialized request")
    categories = ContextInputBreakdown(
        system_instruction_bytes=system_total - selected_system_bytes,
        tool_schema_bytes=tool_schema_bytes,
        project_guidance_bytes=guidance_bytes,
        selected_memory_bytes=memory_bytes,
        checkpoint_bytes=checkpoint_bytes,
        conversation_bytes=conversation_bytes,
        retained_reasoning_bytes=reasoning_bytes,
        tool_output_bytes=tool_output_bytes,
        other_bytes=request_bytes - measured,
    )
    return CurrentContextPressure(
        request_sha256=digest(canonical_bytes(request)),
        categories=categories,
        request_bytes=request_bytes,
        request_capacity_bytes=budget.usable_input,
        request_available_bytes=max(0, budget.usable_input - request_bytes),
        request_overflow_bytes=max(0, request_bytes - budget.usable_input),
        request_usage_basis_points=request_bytes * 10_000 // budget.usable_input,
        local_input_token_estimate=(request_bytes + 3) // 4,
        context_bytes=context_bytes,
        context_capacity_bytes=context_capacity_bytes,
        context_available_bytes=max(0, context_capacity_bytes - context_bytes),
        context_overflow_bytes=max(0, context_bytes - context_capacity_bytes),
    )


def _combined_partial(
    baseline: PartialTotal | None,
    state: RuntimeConversationState,
    field_name: Literal["billed_input", "billed_output"],
) -> PartialTotal:
    value = 0 if baseline is None else baseline.value
    known = 0 if baseline is None else baseline.known_items
    unknown = 0 if baseline is None else baseline.unknown_items
    for entry in state.entries:
        if entry.request_admission is None:
            continue
        if entry.usage is not None and entry.usage.unit == "tokens":
            value += getattr(entry.usage, field_name)
            known += 1
        else:
            unknown += 1
    return PartialTotal(
        value=value, known_items=known, unknown_items=unknown, unit="tokens"
    )


def _cached_partial(
    baseline: PartialTotal | None, state: RuntimeConversationState
) -> PartialTotal:
    return PartialTotal(
        value=0 if baseline is None else baseline.value,
        known_items=0 if baseline is None else baseline.known_items,
        unknown_items=(0 if baseline is None else baseline.unknown_items)
        + sum(entry.request_admission is not None for entry in state.entries),
        unit="tokens",
    )


def context_pressure_report(
    state: RuntimeConversationState,
    *,
    current: CurrentContextPressure | None = None,
    task_state: RuntimeTaskState | None = None,
    policy: ContextPressurePolicy | None = None,
) -> ContextPressureReport:
    policy = policy or ContextPressurePolicy()
    if task_state is not None:
        task_state = RuntimeTaskState.model_validate(task_state.model_dump())
    baseline = None if task_state is None else task_state.checkpoint.context_metrics
    admitted_entries = tuple(
        entry for entry in state.entries if entry.request_admission is not None
    )
    admissions = tuple(
        entry.request_admission
        for entry in admitted_entries
        if entry.request_admission is not None
    )
    admitted_bytes = sum(admission.request.bytes for admission in admissions)
    baseline_calls = 0 if baseline is None else baseline.substantial_tool_calls
    session_calls = sum(
        entry.usage.tools for entry in admitted_entries if entry.usage is not None
    )
    substantial_calls = baseline_calls + session_calls
    repeated_reads = 0 if baseline is None else baseline.repeated_reads
    compactions = (0 if baseline is None else baseline.compactions) + len(
        state.author_compactions
    )
    milestone_state: Literal["queued", "active", "terminal", "unavailable"] = (
        "unavailable"
    )
    if task_state is not None:
        work_status = task_state.current_work_unit.status
        if work_status == "queued":
            milestone_state = "queued"
        elif work_status == "active":
            milestone_state = "active"
        else:
            milestone_state = "terminal"

    advisories: list[PressureAdvisory] = []
    hard_overflow = False
    if current is not None:
        hard_overflow = (
            current.request_overflow_bytes > 0 or current.context_overflow_bytes > 0
        )
    if hard_overflow:
        assert current is not None
        advisories.append(
            PressureAdvisory(
                code="hard_input_limit",
                observed=max(
                    current.request_overflow_bytes, current.context_overflow_bytes
                ),
                threshold=0,
                unit="bytes",
                assessment="honor_hard_admission_limit",
            )
        )
    elif current is not None and current.request_usage_basis_points >= (
        policy.context_advisory_basis_points
    ):
        assessment: Literal[
            "assess", "consider_author_compaction", "offer_fresh_continuation"
        ] = (
            "offer_fresh_continuation"
            if milestone_state == "terminal"
            else "consider_author_compaction"
            if milestone_state in {"queued", "active"}
            else "assess"
        )
        advisories.append(
            PressureAdvisory(
                code="context_usage_threshold",
                observed=current.request_usage_basis_points,
                threshold=policy.context_advisory_basis_points,
                unit="basis_points",
                assessment=assessment,
            )
        )
    if substantial_calls >= policy.substantial_tool_call_threshold:
        advisories.append(
            PressureAdvisory(
                code="substantial_tool_call_threshold",
                observed=substantial_calls,
                threshold=policy.substantial_tool_call_threshold,
                unit="calls",
                assessment="assess",
            )
        )

    return ContextPressureReport(
        source_revision=state.revision,
        policy=policy,
        milestone_state=milestone_state,
        boundary="checkpoint" if task_state is not None else "session_start",
        boundary_sha256=(
            task_state.checkpoint.sha256
            if task_state is not None
            else digest(state.session_id.encode("ascii"))
        ),
        current=current,
        baseline=baseline,
        admitted_growth_request_count=len(admissions),
        admitted_growth_input_bytes=admitted_bytes,
        projected_growth_input_bytes=admitted_bytes
        + (0 if current is None else current.request_bytes),
        provider_input=_combined_partial(
            None if baseline is None else baseline.provider_input,
            state,
            "billed_input",
        ),
        provider_output=_combined_partial(
            None if baseline is None else baseline.provider_output,
            state,
            "billed_output",
        ),
        cached_input=_cached_partial(
            None if baseline is None else baseline.cached_input, state
        ),
        repeated_reads=repeated_reads,
        substantial_tool_calls=substantial_calls,
        compactions=compactions,
        status=(
            "hard_limit" if hard_overflow else "advisory" if advisories else "normal"
        ),
        advisories=tuple(advisories),
    )


class ContextPressureAdvisoryEvent(Contract):
    schema_version: Literal[1] = 1
    sequence: Annotated[int, Field(ge=1, le=32)]
    kind: Literal["pressure_changed", "pressure_cleared"]
    report_sha256: Digest
    status: Literal["normal", "advisory", "hard_limit"]
    advisories: Annotated[tuple[PressureAdvisory, ...], Field(max_length=3)] = ()
    automatic_action: Literal[False] = False
    grants_authority: Literal[False] = False


@dataclass
class ContextPressureMonitor:
    """Ephemeral de-duplication for bounded, non-transcript advisory events."""

    policy: ContextPressurePolicy = field(default_factory=ContextPressurePolicy)
    _last_key: tuple[object, ...] | None = None
    _emitted: int = 0

    def observe(
        self, report: ContextPressureReport
    ) -> ContextPressureAdvisoryEvent | None:
        key: tuple[object, ...] = (
            report.status,
            tuple(item.code for item in report.advisories),
            report.repeated_reads,
            report.compactions,
            None if report.current is None else report.current.request_sha256,
        )
        previous = self._last_key
        self._last_key = key
        if key == previous or (previous is None and not report.advisories):
            return None
        if not report.advisories and (previous is None or previous[0] == "normal"):
            return None
        if self._emitted >= self.policy.max_advisory_events:
            return None
        self._emitted += 1
        return ContextPressureAdvisoryEvent(
            sequence=self._emitted,
            kind=("pressure_cleared" if not report.advisories else "pressure_changed"),
            report_sha256=report.sha256,
            status=report.status,
            advisories=report.advisories,
        )
