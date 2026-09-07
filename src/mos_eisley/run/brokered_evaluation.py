"""Turn a validated broker response into non-scoreable evaluation conformance."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, model_validator

from mos_eisley.core.models import Contract, Critique, Digest, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ReasoningBlock, TextBlock, Usage
from mos_eisley.evaluation.execution import ExecutionBatch
from mos_eisley.evaluation.models import MAX_ASSIGNMENTS
from mos_eisley.providers.openai_responses import response_from_payload
from mos_eisley.run.broker_audit import (
    AssignmentAuthorization,
    inspect_broker_recovery,
)
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.spend_ledger import SpendLedger

BrokerFailureKind = Literal["provider_error", "timeout", "cancelled"]


class BrokeredEvaluationArtifact(Contract):
    schema_version: Literal[1, 2] = 2
    mode: Literal["broker_conformance"] = "broker_conformance"
    authorization: AssignmentAuthorization
    authorization_sha256: Digest
    outcome_sha256: Digest
    status: Literal["completed", "error"] = "completed"
    outcome_status: Literal["response_received", "failed", "cancelled"] = (
        "response_received"
    )
    ledger_status: Literal["absent", "held", "settled", "uncertain", "violation"] = (
        "settled"
    )
    provider_response_sha256: Digest | None = None
    provider_request_id: Annotated[str, Field(min_length=1, max_length=1000)] | None = (
        None
    )
    usage: Usage | None = None
    latency_ms: Annotated[int, Field(ge=0, le=86_400_000)] | None = None
    cost_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)] | None = None
    critique: Critique | None = None
    error: BrokerFailureKind | None = None
    retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    promotion_eligible: Literal[False] = False
    live_result_eligible: Literal[False] = False

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if self.authorization_sha256 != digest(canonical_bytes(self.authorization)):
            raise ValueError("brokered artifact authorization hash mismatch")
        completed = self.status == "completed"
        if self.schema_version == 1 and not completed:
            raise ValueError("legacy brokered artifacts cannot encode failures")
        if completed and (
            self.outcome_status != "response_received"
            or self.ledger_status != "settled"
            or self.provider_response_sha256 is None
            or self.provider_request_id is None
            or self.usage is None
            or self.latency_ms is None
            or self.cost_microusd is None
            or self.critique is None
            or self.error is not None
        ):
            raise ValueError("completed brokered artifact is incomplete")
        if not completed and (
            self.outcome_status == "response_received"
            or self.ledger_status == "settled"
            or self.provider_response_sha256 is not None
            or self.provider_request_id is not None
            or self.usage is not None
            or self.latency_ms is None
            or self.critique is not None
            or self.error not in ("provider_error", "timeout", "cancelled")
            or (self.ledger_status == "absent") != (self.cost_microusd is None)
        ):
            raise ValueError("failed brokered artifact is inconsistent")
        if self.outcome_status == "cancelled" and self.error != "cancelled":
            raise ValueError("cancelled brokered artifact classification is invalid")
        if self.outcome_status == "failed" and self.error == "cancelled":
            raise ValueError("failed brokered artifact cannot claim cancellation")
        return self

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class BrokeredEvaluationResultSet(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["brokered_evaluation_result_set"] = "brokered_evaluation_result_set"
    plan_sha256: Digest
    batch_sha256: Digest
    artifacts: Annotated[
        tuple[BrokeredEvaluationArtifact, ...],
        Field(min_length=1, max_length=MAX_ASSIGNMENTS),
    ]
    exact_batch_coverage_verified: Literal[True] = True
    failures_preserved: Literal[True] = True
    credentialed_conformance_proven: Literal[False] = False
    live_raw_result_set_issued: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def consistent_artifacts(self) -> Self:
        authorizations = tuple(item.authorization for item in self.artifacts)
        if any(
            item.plan_sha256 != self.plan_sha256
            or item.batch_sha256 != self.batch_sha256
            for item in authorizations
        ):
            raise ValueError("brokered result-set lineage mismatch")
        sample_ids = tuple(item.sample_id for item in authorizations)
        authorization_ids = tuple(item.authorization_sha256 for item in self.artifacts)
        artifact_ids = tuple(item.artifact_sha256 for item in self.artifacts)
        outcome_ids = tuple(item.outcome_sha256 for item in self.artifacts)
        ledger_entries = tuple(item.ledger_entry_id for item in authorizations)
        if (
            len(sample_ids) != len(set(sample_ids))
            or len(authorization_ids) != len(set(authorization_ids))
            or len(artifact_ids) != len(set(artifact_ids))
            or len(outcome_ids) != len(set(outcome_ids))
            or len(ledger_entries) != len(set(ledger_entries))
            or len({item.ledger_id for item in authorizations}) != 1
        ):
            raise ValueError("brokered result-set artifacts are not unique")
        provider_ids = tuple(
            item.provider_request_id
            for item in self.artifacts
            if item.provider_request_id is not None
        )
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("brokered result-set provider requests are not unique")
        response_ids = tuple(
            item.provider_response_sha256
            for item in self.artifacts
            if item.provider_response_sha256 is not None
        )
        if len(response_ids) != len(set(response_ids)):
            raise ValueError("brokered result-set responses are not unique")
        return self

    @property
    def result_set_sha256(self) -> str:
        return digest(canonical_bytes(self))


def compile_brokered_evaluation(
    reply: BrokerReply,
    expected: AssignmentAuthorization,
    audit_directory: Path,
    ledger: SpendLedger,
) -> BrokeredEvaluationArtifact:
    """Validate audit, spend, OpenAI shape and strict critique before provenance."""
    state = inspect_broker_recovery(audit_directory, expected, ledger)
    response_hash = digest(canonical_bytes(reply))
    if (
        state.phase != "finished"
        or state.outcome_status != "response_received"
        or state.outcome_sha256 is None
        or state.response_sha256 != response_hash
        or state.ledger_status != "settled"
        or state.latency_ms is None
    ):
        raise ValueError("brokered evaluation provenance is incomplete")
    entry = ledger.entry_status(expected.ledger_entry_id)
    if entry is None or entry.status != "settled":
        raise ValueError("brokered evaluation spending is incomplete")
    try:
        response = response_from_payload(reply.response)
        if response.stop_reason != "end_turn" or any(
            not isinstance(block, (TextBlock, ReasoningBlock))
            for block in response.turn.blocks
        ):
            raise ValueError("response did not complete with text")
        text = "".join(
            block.text for block in response.turn.blocks if isinstance(block, TextBlock)
        )
        critique = Critique.model_validate_json(text)
        if response.provider_request_id is None:
            raise ValueError("provider request identity is absent")
    except (ProviderError, ValidationError, ValueError):
        raise ValueError("brokered critique validation failed") from None
    return BrokeredEvaluationArtifact(
        authorization=expected,
        authorization_sha256=state.authorization_sha256,
        outcome_sha256=state.outcome_sha256,
        status="completed",
        outcome_status="response_received",
        ledger_status="settled",
        provider_response_sha256=response_hash,
        provider_request_id=response.provider_request_id,
        usage=response.usage,
        latency_ms=state.latency_ms,
        cost_microusd=entry.charged_microusd,
        critique=critique,
    )


def compile_brokered_evaluation_failure(
    expected: AssignmentAuthorization,
    audit_directory: Path,
    ledger: SpendLedger,
) -> BrokeredEvaluationArtifact:
    """Preserve one terminal broker failure without inventing response evidence."""

    state = inspect_broker_recovery(audit_directory, expected, ledger)
    if (
        state.phase != "finished"
        or state.outcome_status not in ("failed", "cancelled")
        or state.outcome_sha256 is None
        or state.response_sha256 is not None
        or state.latency_ms is None
        or state.error not in ("provider_error", "timeout", "cancelled")
    ):
        raise ValueError("brokered evaluation failure provenance is incomplete")
    entry = ledger.entry_status(expected.ledger_entry_id)
    if state.ledger_status == "absent":
        if entry is not None:
            raise ValueError("brokered evaluation failure ledger is inconsistent")
        cost_microusd = None
    else:
        if entry is None or entry.status != state.ledger_status:
            raise ValueError("brokered evaluation failure ledger is inconsistent")
        if entry.status == "settled":
            raise ValueError("failed brokered evaluation cannot have settled spend")
        cost_microusd = entry.charged_microusd
    return BrokeredEvaluationArtifact(
        authorization=expected,
        authorization_sha256=state.authorization_sha256,
        outcome_sha256=state.outcome_sha256,
        status="error",
        outcome_status=state.outcome_status,
        ledger_status=state.ledger_status,
        latency_ms=state.latency_ms,
        cost_microusd=cost_microusd,
        error=state.error,
    )


def compile_brokered_evaluation_result_set(
    batch: ExecutionBatch,
    artifacts: tuple[BrokeredEvaluationArtifact, ...],
) -> BrokeredEvaluationResultSet:
    """Require exact batch coverage while retaining a deliberately inert schema."""

    if not artifacts:
        raise ValueError("brokered result set requires artifacts")
    validated = tuple(
        BrokeredEvaluationArtifact.model_validate_json(canonical_bytes(item))
        for item in artifacts
    )
    by_sample = {item.authorization.sample_id: item for item in validated}
    expected_samples = {request.sample_id for request in batch.requests}
    if len(by_sample) != len(validated) or set(by_sample) != expected_samples:
        raise ValueError("brokered artifacts do not exactly cover the batch")
    ordered: list[BrokeredEvaluationArtifact] = []
    for request in batch.requests:
        artifact = by_sample[request.sample_id]
        authorization = artifact.authorization
        if (
            authorization.plan_sha256 != batch.plan_sha256
            or authorization.batch_sha256 != batch.batch_sha256
            or authorization.candidate_id != request.route.candidate_id
            or authorization.evaluation_request_sha256 != request.request_sha256
        ):
            raise ValueError("brokered artifact differs from its evaluation request")
        ordered.append(artifact)
    return BrokeredEvaluationResultSet(
        plan_sha256=batch.plan_sha256,
        batch_sha256=batch.batch_sha256,
        artifacts=tuple(ordered),
    )
