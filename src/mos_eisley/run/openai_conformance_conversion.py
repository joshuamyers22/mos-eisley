"""Convert a reviewed OpenAI conformance gate into a score-inert run artifact."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Self, cast

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    Critique,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import Effort, Usage
from mos_eisley.evaluation.execution import (
    EvaluationRequest,
    ExecutionBatch,
    RawResultSet,
)
from mos_eisley.evaluation.models import MAX_ASSIGNMENTS
from mos_eisley.run.brokered_evaluation import BrokeredEvaluationArtifact
from mos_eisley.run.evaluation_conformance import AuthenticatedEvaluationConformance

_DENIED_GATE_CLAIMS = (
    "provider_authorship_proven",
    "billing_reconciled",
    "quality_claimed",
    "complete_batch_conformance_proven",
    "batch_conversion_authorized",
    "calibration_conversion_performed",
    "grading_authorized",
    "scoring_authorized",
    "promotion_authorized",
    "routing_activation_authorized",
    "additional_provider_request_authorized",
)


class OpenAIConformanceProfileRequirement(Contract):
    model: Identifier
    effort: Effort
    positions: Annotated[tuple[Identifier, ...], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def unique_positions(self) -> Self:
        if len(set(self.positions)) != 3:
            raise ValueError("conversion profile positions must be unique")
        return self

    @property
    def profile(self) -> str:
        return f"{self.model}/{self.effort}"


class OpenAIConformanceConversionPolicy(Contract):
    """Reviewed commitment to one exact, already-complete offline gate report."""

    schema_version: Literal[1] = 1
    mode: Literal["openai_conformance_calibration_conversion_policy"] = (
        "openai_conformance_calibration_conversion_policy"
    )
    policy_id: Identifier
    plan_sha256: Digest
    batch_sha256: Digest
    gate_report_sha256: Digest
    profiles: Annotated[
        tuple[OpenAIConformanceProfileRequirement, ...],
        Field(min_length=6, max_length=6),
    ]
    required_successes_per_profile: Literal[3] = 3
    required_qualifying_successes: Literal[18] = 18
    provider: Literal["openai"] = "openai"
    command: Literal["eval-convert-openai-conformance"] = (
        "eval-convert-openai-conformance"
    )
    exact_gate_report_binding_required: Literal[True] = True
    exact_qualifying_source_set_required: Literal[True] = True
    offline_only: Literal[True] = True
    credential_access_authorized: Literal[False] = False
    provider_request_authorized: Literal[False] = False
    complete_batch_conversion_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def canonical_profiles(self) -> Self:
        identities = tuple(item.profile for item in self.profiles)
        positions = tuple(
            position for item in self.profiles for position in item.positions
        )
        if identities != tuple(sorted(set(identities))):
            raise ValueError("conversion profiles must be sorted and unique")
        if len(positions) != 18 or len(set(positions)) != 18:
            raise ValueError("conversion policy requires 18 unique positions")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class _GateSuccess(Contract):
    artifact_sha256: Digest
    authenticated_at: str
    authenticated_conformance_sha256: Digest
    authorization_sha256: Digest
    cost_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]
    ledger_entry_id: Digest
    ledger_id: Digest
    outcome_sha256: Digest
    position: Identifier
    profile: Annotated[str, Field(min_length=3, max_length=200)]
    provider_request_id: Annotated[str, Field(min_length=1, max_length=1000)]
    provider_response_sha256: Digest
    qualifying: bool
    receipt_path: Annotated[str, Field(min_length=1, max_length=4096)]
    sample_id: Digest
    signed_observation_sha256: Digest


class ConvertedOpenAIConformanceResult(Contract):
    position: Identifier
    sample_id: Digest
    candidate_id: Digest
    evaluation_request_sha256: Digest
    model: Identifier
    effort: Effort
    critique: Critique
    usage: Usage
    latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]
    cost_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    authenticated_conformance_sha256: Digest
    signed_observation_sha256: Digest
    artifact_sha256: Digest
    authorization_sha256: Digest
    outcome_sha256: Digest
    provider_response_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
    quality_claimed: Literal[False] = False


class OpenAIConformanceCalibrationSeed(Contract):
    """Partial empirical input that remains incompatible with scoreable results."""

    schema_version: Literal[1] = 1
    mode: Literal["openai_conformance_partial_calibration_seed"] = (
        "openai_conformance_partial_calibration_seed"
    )
    conversion_policy_sha256: Digest
    gate_report_sha256: Digest
    plan_sha256: Digest
    batch_sha256: Digest
    execution_batch_assignments: Annotated[int, Field(ge=18, le=MAX_ASSIGNMENTS)]
    converted_assignments: Literal[18] = 18
    results: Annotated[
        tuple[ConvertedOpenAIConformanceResult, ...],
        Field(min_length=18, max_length=18),
    ]
    conversion_performed: Literal[True] = True
    partial_calibration_input_issued: Literal[True] = True
    exact_qualifying_source_set_verified: Literal[True] = True
    complete_batch_coverage_verified: Literal[False] = False
    live_raw_result_set_issued: Literal[False] = False
    credential_accessed_during_conversion: Literal[False] = False
    provider_request_sent_during_conversion: Literal[False] = False
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
    quality_claimed: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False
    additional_provider_request_authorized: Literal[False] = False

    @model_validator(mode="after")
    def unique_partial_results(self) -> Self:
        identities = (
            tuple(item.position for item in self.results),
            tuple(item.sample_id for item in self.results),
            tuple(item.authenticated_conformance_sha256 for item in self.results),
            tuple(item.signed_observation_sha256 for item in self.results),
            tuple(item.artifact_sha256 for item in self.results),
            tuple(item.authorization_sha256 for item in self.results),
            tuple(item.outcome_sha256 for item in self.results),
            tuple(item.provider_response_sha256 for item in self.results),
            tuple(item.ledger_entry_id for item in self.results),
        )
        if any(len(values) != len(set(values)) for values in identities):
            raise ValueError("converted conformance result identities must be unique")
        if self.execution_batch_assignments <= self.converted_assignments:
            raise ValueError("conformance seed must remain partial batch coverage")
        return self

    @property
    def calibration_seed_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("gate report contains a duplicate JSON key")
        value[key] = item
    return value


def _load_gate_report(payload: bytes) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("gate report must be unique-key UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("gate report must be a JSON object")
    canonical = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if canonical != payload:
        raise ValueError("gate report must use canonical sorted compact JSON")
    return cast(dict[str, Any], value)


def _gate_successes(
    report: dict[str, Any], policy: OpenAIConformanceConversionPolicy
) -> tuple[_GateSuccess, ...]:
    required_true = {
        "exact_attempt_coverage_verified": True,
        "failure_sources_reverified": True,
        "no_credential_accessed_during_compilation": True,
        "no_provider_request_sent_during_compilation": True,
    }
    required_values: dict[str, object] = {
        "schema_version": 1,
        "mode": "openai_live_conformance_gate_report",
        "outcome": "pass",
        "plan_sha256": policy.plan_sha256,
        "batch_sha256": policy.batch_sha256,
        "profile_count": 6,
        "required_success_positions": 18,
        "verified_success_positions": 18,
        "required_execution_positions": 23,
        "verified_execution_positions": 23,
        "required_failure_boundaries": 5,
        "verified_failure_boundaries": 5,
        "all_authenticated_successes_reverified": 20,
        "historical_authenticated_successes_excluded": 2,
        **required_true,
    }
    if any(
        type(report.get(key)) is not type(expected) or report.get(key) != expected
        for key, expected in required_values.items()
    ):
        raise ValueError("gate report does not satisfy the reviewed aggregate gate")
    if any(report.get(key) is not False for key in _DENIED_GATE_CLAIMS):
        raise ValueError("gate report grants an authority forbidden to conversion")
    raw_successes = report.get("successes")
    if not isinstance(raw_successes, list):
        raise ValueError("gate report must retain all 20 authenticated successes")
    typed_successes = cast(list[Any], raw_successes)
    if len(typed_successes) != 20:
        raise ValueError("gate report must retain all 20 authenticated successes")
    successes = tuple(_GateSuccess.model_validate(item) for item in typed_successes)
    qualifying = tuple(item for item in successes if item.qualifying)
    excluded = tuple(item for item in successes if not item.qualifying)
    if len(qualifying) != 18 or len(excluded) != 2:
        raise ValueError("gate report qualifying-success disposition is invalid")
    required_profiles = {item.profile: item.positions for item in policy.profiles}
    observed_profiles: dict[str, list[str]] = {}
    for item in qualifying:
        observed_profiles.setdefault(item.profile, []).append(item.position)
    if {
        profile: tuple(positions)
        for profile, positions in sorted(observed_profiles.items())
    } != required_profiles:
        raise ValueError("gate report does not match required profile positions")
    matrix = report.get("profile_matrix")
    if not isinstance(matrix, dict):
        raise ValueError("gate report profile matrix is incomplete")
    typed_matrix = cast(dict[str, Any], matrix)
    if set(typed_matrix) != set(required_profiles):
        raise ValueError("gate report profile matrix is incomplete")
    for profile, positions in required_profiles.items():
        entry = typed_matrix.get(profile)
        if not isinstance(entry, dict) or entry != {
            "positions": list(positions),
            "required_consecutive_successes": 3,
            "verified_qualifying_successes": 3,
        }:
            raise ValueError("gate report profile matrix differs from policy")
    return qualifying


def _validate_source(
    request: EvaluationRequest,
    success: _GateSuccess,
    receipt: AuthenticatedEvaluationConformance,
    artifact: BrokeredEvaluationArtifact,
) -> ConvertedOpenAIConformanceResult:
    # Attribute access stays explicit so every converted field remains bound to all
    # three independently retained representations.
    route = request.route
    request_sample_id = request.sample_id
    request_sha256 = request.request_sha256
    observation = receipt.signed_observation.observation
    if (
        request_sample_id != success.sample_id
        or request_sample_id != receipt.sample_id
        or request_sample_id != artifact.authorization.sample_id
        or request_sha256 != receipt.evaluation_request_sha256
        or request_sha256 != artifact.authorization.evaluation_request_sha256
        or route.candidate_id != receipt.candidate_id
        or route.candidate_id != artifact.authorization.candidate_id
        or route.provider != "openai"
        or route.model != observation.model
        or route.effort != observation.effort
        or success.profile != f"{route.model}/{route.effort}"
        or receipt.authenticated_conformance_sha256
        != success.authenticated_conformance_sha256
        or receipt.signed_observation.signed_observation_sha256
        != success.signed_observation_sha256
        or receipt.artifact_sha256 != success.artifact_sha256
        or artifact.artifact_sha256 != success.artifact_sha256
        or artifact.authorization_sha256 != success.authorization_sha256
        or artifact.outcome_sha256 != success.outcome_sha256
        or artifact.provider_response_sha256 != success.provider_response_sha256
        or artifact.provider_request_id != success.provider_request_id
        or artifact.authorization.ledger_id != success.ledger_id
        or artifact.authorization.ledger_entry_id != success.ledger_entry_id
        or artifact.latency_ms != success.latency_ms
        or artifact.cost_microusd != success.cost_microusd
        or receipt.ledger_id != success.ledger_id
        or receipt.ledger_entry_id != success.ledger_entry_id
        or receipt.plan_sha256 != artifact.authorization.plan_sha256
        or receipt.batch_sha256 != artifact.authorization.batch_sha256
        or receipt.provider_request_sha256
        != artifact.authorization.provider_request_sha256
        or artifact.status != "completed"
        or artifact.outcome_status != "response_received"
        or artifact.ledger_status != "settled"
        or artifact.critique is None
        or artifact.usage is None
        or artifact.latency_ms is None
        or artifact.cost_microusd is None
    ):
        raise ValueError("qualifying conformance source lineage mismatch")
    return ConvertedOpenAIConformanceResult(
        position=success.position,
        sample_id=request_sample_id,
        candidate_id=route.candidate_id,
        evaluation_request_sha256=request_sha256,
        model=route.model,
        effort=route.effort,
        critique=artifact.critique,
        usage=artifact.usage,
        latency_ms=artifact.latency_ms,
        cost_microusd=artifact.cost_microusd,
        authenticated_conformance_sha256=success.authenticated_conformance_sha256,
        signed_observation_sha256=success.signed_observation_sha256,
        artifact_sha256=success.artifact_sha256,
        authorization_sha256=success.authorization_sha256,
        outcome_sha256=success.outcome_sha256,
        provider_response_sha256=success.provider_response_sha256,
        ledger_id=success.ledger_id,
        ledger_entry_id=success.ledger_entry_id,
    )


def convert_openai_conformance_to_calibration_seed(
    batch: ExecutionBatch,
    gate_report: bytes,
    policy: OpenAIConformanceConversionPolicy,
    receipts: tuple[AuthenticatedEvaluationConformance, ...],
    artifacts: tuple[BrokeredEvaluationArtifact, ...],
) -> OpenAIConformanceCalibrationSeed:
    """Project only aggregate-approved successes into a non-scoreable seed."""

    batch = ExecutionBatch.model_validate_json(canonical_bytes(batch))
    policy = OpenAIConformanceConversionPolicy.model_validate_json(
        canonical_bytes(policy)
    )
    if digest(gate_report) != policy.gate_report_sha256:
        raise ValueError("gate report does not match the conversion policy")
    if (
        batch.plan_sha256 != policy.plan_sha256
        or batch.batch_sha256 != policy.batch_sha256
    ):
        raise ValueError("execution batch does not match the conversion policy")
    if len(batch.requests) <= policy.required_qualifying_successes:
        raise ValueError("conversion requires a partial subset of a larger batch")
    successes = _gate_successes(_load_gate_report(gate_report), policy)
    validated_receipts = tuple(
        AuthenticatedEvaluationConformance.model_validate_json(canonical_bytes(item))
        for item in receipts
    )
    validated_artifacts = tuple(
        BrokeredEvaluationArtifact.model_validate_json(canonical_bytes(item))
        for item in artifacts
    )
    by_receipt = {item.sample_id: item for item in validated_receipts}
    by_artifact = {item.authorization.sample_id: item for item in validated_artifacts}
    qualifying_samples = {item.sample_id for item in successes}
    if (
        len(validated_receipts) != 18
        or len(validated_artifacts) != 18
        or set(by_receipt) != qualifying_samples
        or set(by_artifact) != qualifying_samples
    ):
        raise ValueError("conversion inputs must exactly cover qualifying successes")
    requests = {item.sample_id: item for item in batch.requests}
    if not qualifying_samples <= set(requests):
        raise ValueError("qualifying success is absent from the execution batch")
    success_by_sample = {item.sample_id: item for item in successes}
    results = tuple(
        _validate_source(
            request,
            success_by_sample[request.sample_id],
            by_receipt[request.sample_id],
            by_artifact[request.sample_id],
        )
        for request in batch.requests
        if request.sample_id in qualifying_samples
    )
    seed = OpenAIConformanceCalibrationSeed(
        conversion_policy_sha256=policy.policy_sha256,
        gate_report_sha256=policy.gate_report_sha256,
        plan_sha256=batch.plan_sha256,
        batch_sha256=batch.batch_sha256,
        execution_batch_assignments=len(batch.requests),
        results=results,
    )
    # Preserve an executable assertion that this distinct schema never silently
    # becomes the legacy gradeable result contract.
    try:
        RawResultSet.model_validate_json(canonical_bytes(seed))
    except ValueError:
        return seed
    raise ValueError("partial calibration seed unexpectedly parsed as raw results")
