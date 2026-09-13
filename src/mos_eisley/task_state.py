"""Versioned offline contracts for bounded work, evidence, and context accounting."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, Text, canonical_bytes
from mos_eisley.core.models import digest as sha256_digest

ShortText = Annotated[str, Field(min_length=1, max_length=2000)]
PathText = Annotated[str, Field(min_length=1, max_length=4096)]
NonNegative = Annotated[int, Field(ge=0)]
PositiveRevision = Annotated[int, Field(ge=1)]


class OwnerProjectScope(Contract):
    owner_uid: NonNegative
    project_id: Identifier
    workspace_sha256: Digest


class ClauseReference(Contract):
    clause_id: Identifier
    revision: PositiveRevision
    plan_sha256: Digest
    text_sha256: Digest


class ClauseRecord(Contract):
    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    clause_id: Identifier
    revision: PositiveRevision
    plan_sha256: Digest
    source_location: ShortText
    text: Text
    text_sha256: Digest
    status: Literal["active", "superseded"] = "active"
    supersedes_revision: PositiveRevision | None = None

    @model_validator(mode="after")
    def valid_clause(self) -> Self:
        if sha256_digest(self.text.encode("utf-8")) != self.text_sha256:
            raise ValueError("clause text does not match its digest")
        if (
            self.supersedes_revision is not None
            and self.supersedes_revision >= self.revision
        ):
            raise ValueError("a clause may supersede only an earlier revision")
        return self

    @property
    def reference(self) -> ClauseReference:
        return ClauseReference(
            clause_id=self.clause_id,
            revision=self.revision,
            plan_sha256=self.plan_sha256,
            text_sha256=self.text_sha256,
        )


class DecisionReference(Contract):
    decision_id: Identifier
    revision: PositiveRevision


class DecisionRecord(Contract):
    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    decision_id: Identifier
    revision: PositiveRevision
    status: Literal["active", "superseded"] = "active"
    statement: Text
    rationale: Text
    source_sha256: Digest
    authority: Literal["user", "trusted_policy", "accepted_requirement"]
    authorized_by: Identifier
    supersedes: DecisionReference | None = None

    @model_validator(mode="after")
    def valid_supersession(self) -> Self:
        if self.supersedes is not None and (
            self.supersedes.decision_id != self.decision_id
            or self.supersedes.revision >= self.revision
        ):
            raise ValueError("decision supersession must name an earlier revision")
        return self

    @property
    def reference(self) -> DecisionReference:
        return DecisionReference(decision_id=self.decision_id, revision=self.revision)


class ArtifactReference(Contract):
    artifact_id: Identifier
    sha256: Digest
    bytes: NonNegative
    media_type: Annotated[str, Field(min_length=1, max_length=200)]
    availability: Literal["available", "missing", "unknown"]
    freshness: Literal["current", "stale", "unknown"]


class OmittedRange(Contract):
    stream: Literal["stdout", "stderr", "combined", "file"]
    start: NonNegative
    end: Annotated[int, Field(gt=0)]
    units: Literal["bytes"] = "bytes"
    reason: ShortText

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError("omitted range end must follow its start")
        return self


class BoundedEvidenceView(Contract):
    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    operation_id: Identifier
    workspace_revision: ShortText
    source_stream: Literal["stdout", "stderr", "combined", "file"]
    exit_status: Annotated[int | None, Field(ge=0, le=255)] = None
    stdout_sha256: Digest | None = None
    stderr_sha256: Digest | None = None
    original_bytes: NonNegative
    visible_bytes: NonNegative
    original_lines: NonNegative
    visible_lines: NonNegative
    encoding: Literal["utf-8"] = "utf-8"
    content: Annotated[str, Field(max_length=256_000)]
    full_artifact: ArtifactReference
    reduction_policy: Identifier
    reduction_version: PositiveRevision
    omissions: tuple[OmittedRange, ...] = ()
    complete: bool

    @model_validator(mode="after")
    def disclosed_reduction(self) -> Self:
        if len(self.content.encode("utf-8")) != self.visible_bytes:
            raise ValueError("bounded evidence content does not match its byte count")
        if len(self.content.splitlines()) != self.visible_lines:
            raise ValueError("bounded evidence content does not match its line count")
        if self.original_bytes != self.full_artifact.bytes:
            raise ValueError("bounded evidence size differs from its full artifact")
        if (
            self.visible_bytes > self.original_bytes
            or self.visible_lines > self.original_lines
        ):
            raise ValueError("bounded evidence cannot exceed its original")
        reduced = self.visible_bytes != self.original_bytes
        if reduced != bool(self.omissions):
            raise ValueError(
                "every bounded-view reduction must disclose omitted ranges"
            )
        previous_end = 0
        for omission in self.omissions:
            if (
                omission.stream != self.source_stream
                or omission.start < previous_end
                or omission.end > self.original_bytes
            ):
                raise ValueError("bounded-view omissions must be ordered source ranges")
            previous_end = omission.end
        if sum(item.end - item.start for item in self.omissions) != (
            self.original_bytes - self.visible_bytes
        ):
            raise ValueError("bounded-view omissions do not account for removed bytes")
        source_digest = {
            "stdout": self.stdout_sha256,
            "stderr": self.stderr_sha256,
            "combined": self.full_artifact.sha256,
            "file": self.full_artifact.sha256,
        }[self.source_stream]
        if source_digest != self.full_artifact.sha256:
            raise ValueError("bounded evidence stream digest differs from its artifact")
        if self.complete and (
            reduced
            or self.full_artifact.availability != "available"
            or self.full_artifact.freshness != "current"
        ):
            raise ValueError("a lossy or unavailable evidence view cannot be complete")
        if (
            not self.complete
            and not self.omissions
            and self.full_artifact.availability == "available"
        ):
            raise ValueError(
                "an incomplete view must disclose loss or artifact unavailability"
            )
        return self


def verify_bounded_evidence(view: BoundedEvidenceView, payload: bytes) -> None:
    """Reproduce one UTF-8 bounded view from its exact retained artifact."""
    if len(payload) != view.full_artifact.bytes or sha256_digest(payload) != (
        view.full_artifact.sha256
    ):
        raise ValueError("bounded evidence artifact does not match its reference")
    try:
        decoded_payload = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("bounded evidence artifact is not valid UTF-8") from None
    if len(decoded_payload.splitlines()) != view.original_lines:
        raise ValueError("bounded evidence original line count does not reproduce")
    visible = bytearray()
    position = 0
    for omission in view.omissions:
        visible.extend(payload[position : omission.start])
        position = omission.end
    visible.extend(payload[position:])
    try:
        reproduced = bytes(visible).decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("bounded evidence reduction splits UTF-8 content") from None
    if reproduced != view.content:
        raise ValueError("bounded evidence content does not reproduce")


class InputReference(Contract):
    input_id: Identifier
    sha256: Digest
    required: bool = True
    availability: Literal["available", "missing", "unknown"]
    freshness: Literal["current", "stale", "unknown"]


class EvidenceRequirement(Contract):
    requirement_id: Identifier
    description: ShortText
    verification_required: bool = True


class EvidenceReference(Contract):
    evidence_id: Identifier
    artifact: ArtifactReference
    kind: Literal["verification", "review", "artifact", "other"]
    verification_status: Literal["passed", "failed", "not_run", "stale", "unknown"]
    satisfies: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=64)]
    view: BoundedEvidenceView | None = None

    @model_validator(mode="after")
    def valid_evidence(self) -> Self:
        if len(set(self.satisfies)) != len(self.satisfies):
            raise ValueError("evidence requirement bindings must be unique")
        if self.view is not None and self.view.full_artifact != self.artifact:
            raise ValueError("bounded evidence must bind the same full artifact")
        return self


class ResourceCeiling(Contract):
    input_bytes: NonNegative
    output_bytes: NonNegative
    cost_microusd: NonNegative
    attempts: NonNegative
    correction_cycles: NonNegative
    review_rounds: NonNegative


class ResourceLedger(Contract):
    input_bytes: NonNegative = 0
    output_bytes: NonNegative = 0
    cost_microusd: NonNegative = 0
    attempts: NonNegative = 0
    correction_cycles: NonNegative = 0
    review_rounds: NonNegative = 0
    uncertain_effects: NonNegative = 0

    def exceeds(self, ceiling: ResourceCeiling) -> bool:
        return any(
            used > allowed
            for used, allowed in (
                (self.input_bytes, ceiling.input_bytes),
                (self.output_bytes, ceiling.output_bytes),
                (self.cost_microusd, ceiling.cost_microusd),
                (self.attempts, ceiling.attempts),
                (self.correction_cycles, ceiling.correction_cycles),
                (self.review_rounds, ceiling.review_rounds),
            )
        )


TerminalStatus = Literal["completed", "blocked", "cancelled"]


class OutcomeReference(Contract):
    outcome_id: Identifier
    revision: PositiveRevision


class OutcomeRecord(Contract):
    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    outcome_id: Identifier
    revision: PositiveRevision
    work_unit_id: Identifier
    work_unit_revision: PositiveRevision
    status: TerminalStatus
    summary: Text
    reason: ShortText
    evidence_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=64)]
    untested_claims: Annotated[tuple[ShortText, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def unique_evidence(self) -> Self:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("outcome evidence references must be unique")
        return self

    @property
    def reference(self) -> OutcomeReference:
        return OutcomeReference(outcome_id=self.outcome_id, revision=self.revision)


class WorkUnitReference(Contract):
    work_unit_id: Identifier
    revision: PositiveRevision


class WorkUnitRecord(Contract):
    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    work_unit_id: Identifier
    revision: PositiveRevision
    parent: WorkUnitReference | None = None
    dependencies: Annotated[tuple[WorkUnitReference, ...], Field(max_length=32)] = ()
    objective: Text
    component_scope: Annotated[
        tuple[ShortText, ...], Field(min_length=1, max_length=32)
    ]
    interfaces: Annotated[tuple[Identifier, ...], Field(max_length=32)] = ()
    applicable_clauses: Annotated[
        tuple[ClauseReference, ...], Field(max_length=64)
    ] = ()
    origin_direction_sha256: Digest
    policy_sha256: Digest
    authorization_refs: Annotated[tuple[Digest, ...], Field(max_length=16)] = ()
    required_inputs: Annotated[tuple[InputReference, ...], Field(max_length=64)] = ()
    evidence_requirements: Annotated[
        tuple[EvidenceRequirement, ...], Field(max_length=64)
    ] = ()
    evidence: Annotated[tuple[EvidenceReference, ...], Field(max_length=64)] = ()
    stopping_condition: Text
    resource_ceiling: ResourceCeiling
    ledger: ResourceLedger = ResourceLedger()
    status: Literal["queued", "active", "completed", "blocked", "cancelled"]
    terminal_reason: ShortText | None = None
    outcome: OutcomeRecord | None = None
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def valid_work_unit(self) -> Self:
        for identities, label in (
            (
                tuple((item.work_unit_id, item.revision) for item in self.dependencies),
                "dependency",
            ),
            (self.interfaces, "interface"),
            (
                tuple(
                    (item.clause_id, item.revision) for item in self.applicable_clauses
                ),
                "clause",
            ),
            (tuple(item.input_id for item in self.required_inputs), "input"),
            (
                tuple(item.requirement_id for item in self.evidence_requirements),
                "evidence requirement",
            ),
            (tuple(item.evidence_id for item in self.evidence), "evidence"),
        ):
            if len(set(identities)) != len(identities):
                raise ValueError(f"work-unit {label} entries must be unique")
        if self.parent is not None and self.parent.work_unit_id == self.work_unit_id:
            raise ValueError("a work unit cannot parent itself")
        if any(item.work_unit_id == self.work_unit_id for item in self.dependencies):
            raise ValueError("a work unit cannot depend on itself")
        if self.ledger.exceeds(self.resource_ceiling):
            raise ValueError("work-unit resource use exceeds its ceiling")

        requirements = {
            item.requirement_id: item for item in self.evidence_requirements
        }
        for evidence in self.evidence:
            if evidence.view is not None and evidence.view.scope != self.scope:
                raise ValueError("work-unit evidence crosses an owner or project scope")
            if not set(evidence.satisfies) <= set(requirements):
                raise ValueError("evidence binds an unknown requirement")

        terminal = self.status in ("completed", "blocked", "cancelled")
        if terminal and (self.terminal_reason is None or self.outcome is None):
            raise ValueError(
                "terminal work units require exactly one reason and outcome"
            )
        if not terminal and (
            self.terminal_reason is not None or self.outcome is not None
        ):
            raise ValueError("nonterminal work units cannot carry a terminal outcome")
        if self.outcome is not None and (
            self.outcome.scope != self.scope
            or self.outcome.work_unit_id != self.work_unit_id
            or self.outcome.work_unit_revision != self.revision
            or self.outcome.status != self.status
            or self.outcome.reason != self.terminal_reason
            or set(self.outcome.evidence_ids)
            != {item.evidence_id for item in self.evidence}
        ):
            raise ValueError("work-unit outcome does not bind its terminal state")

        if self.status in ("active", "completed"):
            unavailable = [
                item.input_id
                for item in self.required_inputs
                if item.required
                and (item.availability != "available" or item.freshness != "current")
            ]
            if unavailable:
                raise ValueError("active work unit is missing a required current input")
        if self.status == "completed":
            satisfied: dict[str, list[EvidenceReference]] = {
                requirement_id: [] for requirement_id in requirements
            }
            for evidence in self.evidence:
                for requirement_id in evidence.satisfies:
                    satisfied[requirement_id].append(evidence)
            for requirement_id, requirement in requirements.items():
                valid = [
                    item
                    for item in satisfied[requirement_id]
                    if item.artifact.availability == "available"
                    and item.artifact.freshness == "current"
                    and (
                        not requirement.verification_required
                        or (
                            item.kind == "verification"
                            and item.verification_status == "passed"
                        )
                    )
                ]
                if not valid:
                    raise ValueError(
                        "completed work unit lacks current evidence for "
                        f"{requirement_id}"
                    )
        return self

    @property
    def reference(self) -> WorkUnitReference:
        return WorkUnitReference(work_unit_id=self.work_unit_id, revision=self.revision)


class WorkspaceState(Contract):
    repository_sha256: Digest
    branch: ShortText
    revision: ShortText
    tree_sha256: Digest
    dirty_state_sha256: Digest

    @property
    def sha256(self) -> str:
        return sha256_digest(canonical_bytes(self))


class VerificationRecord(Contract):
    verification_id: Identifier
    command: Annotated[str, Field(min_length=1, max_length=4000)]
    status: Literal["passed", "failed", "not_run", "stale", "unknown"]
    bound_workspace_sha256: Digest
    bound_input_sha256: Digest
    result: ArtifactReference | None = None

    @model_validator(mode="after")
    def passed_has_current_result(self) -> Self:
        if self.status == "passed" and (
            self.result is None
            or self.result.availability != "available"
            or self.result.freshness != "current"
        ):
            raise ValueError("a passed verification requires a current result artifact")
        return self


class CheckpointOmission(Contract):
    kind: Literal["work_unit", "decision", "outcome", "verification", "other"]
    record_id: Identifier
    reason: ShortText


class CheckpointView(Contract):
    summary: Annotated[str, Field(min_length=1, max_length=16_000)]
    included_record_ids: Annotated[tuple[Identifier, ...], Field(max_length=128)] = ()
    omissions: Annotated[tuple[CheckpointOmission, ...], Field(max_length=128)] = ()
    complete: bool

    @model_validator(mode="after")
    def disclosed_loss(self) -> Self:
        if len(set(self.included_record_ids)) != len(self.included_record_ids):
            raise ValueError("checkpoint included records must be unique")
        omitted = {(item.kind, item.record_id) for item in self.omissions}
        if len(omitted) != len(self.omissions):
            raise ValueError("checkpoint omissions must be unique")
        if self.complete and self.omissions:
            raise ValueError("a checkpoint with disclosed omissions is not complete")
        if not self.complete and not self.omissions:
            raise ValueError("an incomplete checkpoint must disclose its omissions")
        return self


class PartialTotal(Contract):
    value: NonNegative
    known_items: NonNegative
    unknown_items: NonNegative
    unit: Literal["tokens", "micro_usd", "milliseconds"]

    @model_validator(mode="after")
    def truthful_value(self) -> Self:
        if self.known_items == 0 and self.value != 0:
            raise ValueError("a partial total without observations must be zero")
        return self

    @property
    def complete(self) -> bool:
        return self.unknown_items == 0


class ContextInputBreakdown(Contract):
    system_instruction_bytes: NonNegative = 0
    tool_schema_bytes: NonNegative = 0
    project_guidance_bytes: NonNegative = 0
    selected_memory_bytes: NonNegative = 0
    checkpoint_bytes: NonNegative = 0
    conversation_bytes: NonNegative = 0
    retained_reasoning_bytes: NonNegative = 0
    tool_output_bytes: NonNegative = 0
    other_bytes: NonNegative = 0

    @property
    def total_bytes(self) -> int:
        return sum(
            (
                self.system_instruction_bytes,
                self.tool_schema_bytes,
                self.project_guidance_bytes,
                self.selected_memory_bytes,
                self.checkpoint_bytes,
                self.conversation_bytes,
                self.retained_reasoning_bytes,
                self.tool_output_bytes,
                self.other_bytes,
            )
        )


RequestPurpose = Literal[
    "author",
    "child",
    "review",
    "compaction",
    "handoff",
    "retry",
    "abandoned",
]


class RequestContextMetric(Contract):
    schema_version: Literal[1] = 1
    request_id: Identifier
    ordinal: PositiveRevision
    purpose: RequestPurpose
    local_input_bytes: Annotated[int, Field(ge=1)]
    local_input_breakdown: ContextInputBreakdown
    handoff_revalidation_input_bytes: NonNegative = 0
    admitted: bool
    provider_usage: Literal["unavailable", "estimated", "confirmed"] = "unavailable"
    provider_input_tokens: NonNegative | None = None
    cached_input_tokens: NonNegative | None = None
    provider_output_tokens: NonNegative | None = None
    cost_microusd: NonNegative | None = None
    latency_milliseconds: NonNegative | None = None
    original_tool_output_bytes: NonNegative = 0
    visible_tool_output_bytes: NonNegative = 0
    repeated_reads: NonNegative = 0
    substantial_tool_calls: NonNegative = 0
    compactions: NonNegative = 0

    @model_validator(mode="after")
    def valid_measurement(self) -> Self:
        if self.local_input_breakdown.total_bytes != self.local_input_bytes:
            raise ValueError("local input categories do not match the request total")
        if self.handoff_revalidation_input_bytes > self.local_input_bytes:
            raise ValueError("handoff revalidation input exceeds the request total")
        provider_values = (
            self.provider_input_tokens,
            self.cached_input_tokens,
            self.provider_output_tokens,
            self.cost_microusd,
            self.latency_milliseconds,
        )
        if not self.admitted and self.provider_usage != "unavailable":
            raise ValueError("an unadmitted request cannot claim provider usage")
        if self.provider_usage == "unavailable" and any(
            value is not None for value in provider_values[:4]
        ):
            raise ValueError(
                "unavailable provider usage cannot carry token or cost values"
            )
        if self.provider_usage != "unavailable" and (
            self.provider_input_tokens is None or self.provider_output_tokens is None
        ):
            raise ValueError("observed provider usage requires input and output tokens")
        if not self.admitted and any(value is not None for value in provider_values):
            raise ValueError("an unadmitted request cannot claim provider observations")
        if (
            self.cached_input_tokens is not None
            and self.provider_input_tokens is not None
            and self.cached_input_tokens > self.provider_input_tokens
        ):
            raise ValueError("cached input cannot exceed provider input")
        if self.visible_tool_output_bytes > self.original_tool_output_bytes:
            raise ValueError("visible tool output cannot exceed original output")
        return self


class CumulativeContextMetrics(Contract):
    schema_version: Literal[1] = 1
    request_count: NonNegative
    admitted_request_count: NonNegative
    confirmed_usage_request_count: NonNegative
    estimated_usage_request_count: NonNegative
    unknown_usage_request_count: NonNegative
    local_input_bytes: NonNegative
    local_input_breakdown: ContextInputBreakdown
    handoff_revalidation_input_bytes: NonNegative
    provider_input: PartialTotal
    cached_input: PartialTotal
    provider_output: PartialTotal
    cost: PartialTotal
    latency: PartialTotal
    original_tool_output_bytes: NonNegative
    visible_tool_output_bytes: NonNegative
    repeated_reads: NonNegative
    substantial_tool_calls: NonNegative
    compactions: NonNegative

    @model_validator(mode="after")
    def consistent_counts(self) -> Self:
        if self.local_input_breakdown.total_bytes != self.local_input_bytes:
            raise ValueError("cumulative input categories do not match the total")
        if self.handoff_revalidation_input_bytes > self.local_input_bytes:
            raise ValueError("cumulative handoff input exceeds the total")
        if self.admitted_request_count > self.request_count:
            raise ValueError("admitted request count exceeds total requests")
        if self.admitted_request_count != (
            self.confirmed_usage_request_count
            + self.estimated_usage_request_count
            + self.unknown_usage_request_count
        ):
            raise ValueError("provider usage status must account for admitted requests")
        for total in (
            self.provider_input,
            self.cached_input,
            self.provider_output,
            self.cost,
            self.latency,
        ):
            if total.known_items + total.unknown_items != self.admitted_request_count:
                raise ValueError(
                    "partial totals must account for every admitted request"
                )
        if self.visible_tool_output_bytes > self.original_tool_output_bytes:
            raise ValueError("visible tool-output total exceeds original total")
        return self

    @property
    def sha256(self) -> str:
        return sha256_digest(canonical_bytes(self))


def accumulate_context_metrics(
    requests: Sequence[RequestContextMetric],
) -> CumulativeContextMetrics:
    if len({item.request_id for item in requests}) != len(requests):
        raise ValueError("context metric request IDs must be unique")
    if tuple(item.ordinal for item in requests) != tuple(range(1, len(requests) + 1)):
        raise ValueError("context metric ordinals must be contiguous")
    admitted = tuple(item for item in requests if item.admitted)

    def input_category(field: str) -> int:
        return sum(getattr(item.local_input_breakdown, field) for item in requests)

    def partial(
        field: str, unit: Literal["tokens", "micro_usd", "milliseconds"]
    ) -> PartialTotal:
        values = tuple(getattr(item, field) for item in admitted)
        known = tuple(value for value in values if value is not None)
        return PartialTotal(
            value=sum(known),
            known_items=len(known),
            unknown_items=len(values) - len(known),
            unit=unit,
        )

    return CumulativeContextMetrics(
        request_count=len(requests),
        admitted_request_count=len(admitted),
        confirmed_usage_request_count=sum(
            item.provider_usage == "confirmed" for item in admitted
        ),
        estimated_usage_request_count=sum(
            item.provider_usage == "estimated" for item in admitted
        ),
        unknown_usage_request_count=sum(
            item.provider_usage == "unavailable" for item in admitted
        ),
        local_input_bytes=sum(item.local_input_bytes for item in requests),
        local_input_breakdown=ContextInputBreakdown(
            system_instruction_bytes=input_category("system_instruction_bytes"),
            tool_schema_bytes=input_category("tool_schema_bytes"),
            project_guidance_bytes=input_category("project_guidance_bytes"),
            selected_memory_bytes=input_category("selected_memory_bytes"),
            checkpoint_bytes=input_category("checkpoint_bytes"),
            conversation_bytes=input_category("conversation_bytes"),
            retained_reasoning_bytes=input_category("retained_reasoning_bytes"),
            tool_output_bytes=input_category("tool_output_bytes"),
            other_bytes=input_category("other_bytes"),
        ),
        handoff_revalidation_input_bytes=sum(
            item.handoff_revalidation_input_bytes for item in requests
        ),
        provider_input=partial("provider_input_tokens", "tokens"),
        cached_input=partial("cached_input_tokens", "tokens"),
        provider_output=partial("provider_output_tokens", "tokens"),
        cost=partial("cost_microusd", "micro_usd"),
        latency=partial("latency_milliseconds", "milliseconds"),
        original_tool_output_bytes=sum(
            item.original_tool_output_bytes for item in requests
        ),
        visible_tool_output_bytes=sum(
            item.visible_tool_output_bytes for item in requests
        ),
        repeated_reads=sum(item.repeated_reads for item in requests),
        substantial_tool_calls=sum(item.substantial_tool_calls for item in requests),
        compactions=sum(item.compactions for item in requests),
    )


class MilestoneCheckpoint(Contract):
    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    checkpoint_id: Identifier
    revision: PositiveRevision
    previous_checkpoint_sha256: Digest | None = None
    objective: Text
    current_work_unit: WorkUnitReference
    workspace: WorkspaceState
    main_files: Annotated[tuple[PathText, ...], Field(max_length=64)] = ()
    active_decisions: Annotated[
        tuple[DecisionReference, ...], Field(max_length=64)
    ] = ()
    completed_outcomes: Annotated[
        tuple[OutcomeReference, ...], Field(max_length=64)
    ] = ()
    verifications: Annotated[tuple[VerificationRecord, ...], Field(max_length=64)] = ()
    untested_claims: Annotated[tuple[ShortText, ...], Field(max_length=32)] = ()
    blockers: Annotated[tuple[ShortText, ...], Field(max_length=32)] = ()
    next_actions: Annotated[
        tuple[WorkUnitReference, ...], Field(min_length=1, max_length=3)
    ]
    outstanding_work: Annotated[
        tuple[WorkUnitReference, ...], Field(min_length=1, max_length=128)
    ]
    view: CheckpointView
    context_metrics: CumulativeContextMetrics
    task_ledger: ResourceLedger
    lineage_sha256: Digest

    @model_validator(mode="after")
    def valid_checkpoint(self) -> Self:
        for values, label in (
            (self.main_files, "main file"),
            (self.active_decisions, "decision"),
            (self.completed_outcomes, "outcome"),
            (self.verifications, "verification"),
            (self.next_actions, "next action"),
            (self.outstanding_work, "outstanding work"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"checkpoint {label} entries must be unique")
        if len({item.work_unit_id for item in self.next_actions}) != len(
            self.next_actions
        ) or len({item.work_unit_id for item in self.outstanding_work}) != len(
            self.outstanding_work
        ):
            raise ValueError("checkpoint work-unit identities must be unique")
        outstanding = {item.work_unit_id for item in self.outstanding_work}
        next_ids = {item.work_unit_id for item in self.next_actions}
        if not set(self.next_actions) <= set(self.outstanding_work):
            raise ValueError("checkpoint next actions must remain in outstanding work")
        disclosed = {
            item.record_id for item in self.view.omissions if item.kind == "work_unit"
        }
        if outstanding - next_ids != disclosed:
            raise ValueError(
                "checkpoint must disclose every omitted outstanding work unit"
            )
        if not next_ids <= set(self.view.included_record_ids):
            raise ValueError("checkpoint view must include every short next action")
        if any(
            item.status == "passed"
            and item.bound_workspace_sha256 != self.workspace.sha256
            for item in self.verifications
        ):
            raise ValueError("checkpoint carries a stale passing verification")
        return self

    @property
    def sha256(self) -> str:
        return sha256_digest(canonical_bytes(self))


class ContinuationSelection(Contract):
    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    checkpoint_id: Identifier
    checkpoint_revision: PositiveRevision
    checkpoint_sha256: Digest
    selected_work_unit: WorkUnitReference
    workspace: WorkspaceState
    required_inputs: Annotated[tuple[InputReference, ...], Field(max_length=64)] = ()
    context_baseline: CumulativeContextMetrics
    ledger_baseline: ResourceLedger
    grants_authority: Literal[False] = False


def validate_continuation(
    checkpoint: MilestoneCheckpoint,
    work_unit: WorkUnitRecord,
    selection: ContinuationSelection,
) -> None:
    if selection.scope != checkpoint.scope or work_unit.scope != checkpoint.scope:
        raise ValueError("continuation crosses an owner or project boundary")
    if (
        selection.checkpoint_id != checkpoint.checkpoint_id
        or selection.checkpoint_revision != checkpoint.revision
        or selection.checkpoint_sha256 != checkpoint.sha256
    ):
        raise ValueError("continuation names a stale checkpoint revision")
    if selection.selected_work_unit != work_unit.reference or not any(
        item == work_unit.reference for item in checkpoint.outstanding_work
    ):
        raise ValueError("continuation work unit is not outstanding at this checkpoint")
    if work_unit.status not in ("queued", "active"):
        raise ValueError("continuation cannot select a terminal work unit")
    if selection.workspace != checkpoint.workspace:
        raise ValueError("continuation workspace state is stale")
    if selection.context_baseline != checkpoint.context_metrics:
        raise ValueError("continuation cannot reset cumulative context metrics")
    if selection.ledger_baseline != checkpoint.task_ledger:
        raise ValueError("continuation cannot reset or replace the task ledger")
    expected_inputs = {item.input_id: item for item in work_unit.required_inputs}
    supplied_inputs = {item.input_id: item for item in selection.required_inputs}
    if len(supplied_inputs) != len(selection.required_inputs):
        raise ValueError("continuation input IDs must be unique")
    if set(supplied_inputs) != set(expected_inputs):
        raise ValueError("continuation input inventory differs from the work unit")
    for input_id, expected in expected_inputs.items():
        supplied = supplied_inputs.get(input_id)
        if supplied != expected or (
            expected.required
            and (
                expected.availability != "available" or expected.freshness != "current"
            )
        ):
            raise ValueError("continuation is missing a required current input")
