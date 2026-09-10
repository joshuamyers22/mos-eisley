"""Authenticated observer attestation for one brokered OpenAI evaluation probe."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import Effort, Usage
from mos_eisley.evaluation.execution import EvaluationRequest, ExecutionBatch
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.broker_audit import (
    AssignmentAuthorization,
    inspect_broker_recovery,
)
from mos_eisley.run.brokered_evaluation import BrokeredEvaluationArtifact
from mos_eisley.run.evaluation_broker import make_assignment_authorization
from mos_eisley.run.openai_conformance import build_openai_conformance_payload
from mos_eisley.run.spend_ledger import SpendLedger

_DOMAIN = b"mos-eisley/brokered-openai-evaluation-conformance/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class TrustedEvaluationConformanceObserver(Contract):
    observer_id: Identifier
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32, "public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32, "public key"))


class EvaluationConformancePolicy(Contract):
    """Pre-registered scope for one exact blinded credentialed probe."""

    schema_version: Literal[1] = 1
    mode: Literal["brokered_evaluation_conformance_policy"] = (
        "brokered_evaluation_conformance_policy"
    )
    policy_id: Identifier
    plan_sha256: Digest
    batch_sha256: Digest
    sample_id: Digest
    candidate_id: Digest
    evaluation_request_sha256: Digest
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_observation_age_seconds: Annotated[int, Field(gt=0, le=2_592_000)]
    observers: Annotated[
        tuple[TrustedEvaluationConformanceObserver, ...],
        Field(min_length=1, max_length=20),
    ]
    allowed_sdk_versions: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=20)
    ]
    provider: Literal["openai"] = "openai"
    endpoint_origin: Literal["https://api.openai.com"] = "https://api.openai.com"
    api_family: Literal["responses"] = "responses"
    credential_mode: Literal["api_key"] = "api_key"
    command: Literal["openai-conformance"] = "openai-conformance"
    official_sdk_required: Literal[True] = True
    bounded_http_client_required: Literal[True] = True
    isolated_broker_required: Literal[True] = True
    zero_automatic_retries_required: Literal[True] = True
    provider_storage_disabled_required: Literal[True] = True
    truncation_disabled_required: Literal[True] = True
    batch_conversion_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("evaluation conformance policy window must be positive")
        identities = tuple(item.observer_id for item in self.observers)
        keys = tuple(item.public_key_sha256 for item in self.observers)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "evaluation conformance observers need sorted unique identities "
                "and keys"
            )
        if tuple(sorted(set(self.allowed_sdk_versions))) != self.allowed_sdk_versions:
            raise ValueError("allowed SDK versions must be unique and sorted")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class EvaluationConformanceObservation(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["brokered_evaluation_conformance_observation"] = (
        "brokered_evaluation_conformance_observation"
    )
    conformance_policy_sha256: Digest
    plan_sha256: Digest
    batch_sha256: Digest
    sample_id: Digest
    candidate_id: Digest
    evaluation_request_sha256: Digest
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    artifact_sha256: Digest
    authorization_sha256: Digest
    outcome_sha256: Digest
    provider_response_sha256: Digest
    provider_request_id: Annotated[str, Field(min_length=1, max_length=1000)]
    model: Identifier
    effort: Effort
    usage: Usage
    latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]
    cost_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    observed_at: UtcTimestamp
    sdk_package: Literal["openai"] = "openai"
    sdk_version: Identifier
    transport_evidence_sha256: Digest
    provider: Literal["openai"] = "openai"
    endpoint_origin: Literal["https://api.openai.com"] = "https://api.openai.com"
    api_family: Literal["responses"] = "responses"
    credential_mode: Literal["api_key"] = "api_key"
    command: Literal["openai-conformance"] = "openai-conformance"
    credentialed_exchange_attested: Literal[True] = True
    data_transfer_authorized_attested: Literal[True] = True
    official_sdk_attested: Literal[True] = True
    bounded_http_client_attested: Literal[True] = True
    isolated_broker_attested: Literal[True] = True
    automatic_retries: Literal[0] = 0
    provider_storage_requested: Literal[False] = False
    truncation_disabled: Literal[True] = True
    raw_response_exported: Literal[False] = False
    provider_credential_persisted: Literal[False] = False
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
    complete_batch_conformance_proven: Literal[False] = False
    batch_conversion_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    quality_claimed: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("observed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @property
    def observation_sha256(self) -> str:
        return digest(canonical_bytes(self))


class EvaluationConformanceSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    observation_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedEvaluationConformanceObservation(Contract):
    schema_version: Literal[1] = 1
    observation: EvaluationConformanceObservation
    signature: EvaluationConformanceSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.observation_sha256 != self.observation.observation_sha256:
            raise ValueError("signature does not identify this conformance observation")
        return self

    @property
    def signed_observation_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedEvaluationConformance(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_brokered_evaluation_conformance"] = (
        "authenticated_brokered_evaluation_conformance"
    )
    conformance_policy_sha256: Digest
    plan_sha256: Digest
    batch_sha256: Digest
    sample_id: Digest
    candidate_id: Digest
    evaluation_request_sha256: Digest
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    artifact_sha256: Digest
    signer_id: Identifier
    signed_observation: SignedEvaluationConformanceObservation
    authenticated_at: UtcTimestamp
    credentialed_exchange_attested: Literal[True] = True
    local_batch_and_artifact_reverified: Literal[True] = True
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
    complete_batch_conformance_proven: Literal[False] = False
    batch_conversion_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    quality_claimed: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("authenticated_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_signed_observation(self) -> Self:
        observation = self.signed_observation.observation
        if (
            self.conformance_policy_sha256 != observation.conformance_policy_sha256
            or self.plan_sha256 != observation.plan_sha256
            or self.batch_sha256 != observation.batch_sha256
            or self.sample_id != observation.sample_id
            or self.candidate_id != observation.candidate_id
            or self.evaluation_request_sha256 != observation.evaluation_request_sha256
            or self.provider_request_sha256 != observation.provider_request_sha256
            or self.spend_policy_sha256 != observation.spend_policy_sha256
            or self.ledger_id != observation.ledger_id
            or self.ledger_entry_id != observation.ledger_entry_id
            or self.artifact_sha256 != observation.artifact_sha256
            or self.signer_id != self.signed_observation.signature.signer_id
            or self.authenticated_at < observation.observed_at
        ):
            raise ValueError(
                "authenticated evaluation conformance does not match observation"
            )
        return self

    @property
    def authenticated_conformance_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_evaluation_conformance_observer(
    observer_id: str, public_key: bytes
) -> TrustedEvaluationConformanceObserver:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedEvaluationConformanceObserver(
        observer_id=observer_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _assignment(batch: ExecutionBatch, sample_id: str) -> EvaluationRequest:
    matches = [item for item in batch.requests if item.sample_id == sample_id]
    if len(matches) != 1:
        raise ValueError("evaluation conformance requires one exact assignment")
    return matches[0]


def _sources_match(
    observation: EvaluationConformanceObservation,
    batch: ExecutionBatch,
    artifact: BrokeredEvaluationArtifact,
    expected: AssignmentAuthorization,
) -> bool:
    request = _assignment(batch, observation.sample_id)
    authorization = artifact.authorization
    return (
        authorization == expected
        and observation.plan_sha256 == batch.plan_sha256 == authorization.plan_sha256
        and observation.batch_sha256 == batch.batch_sha256 == authorization.batch_sha256
        and observation.sample_id == authorization.sample_id == request.sample_id
        and observation.candidate_id
        == authorization.candidate_id
        == request.route.candidate_id
        and observation.evaluation_request_sha256
        == authorization.evaluation_request_sha256
        == request.request_sha256
        and observation.provider_request_sha256 == authorization.provider_request_sha256
        and observation.spend_policy_sha256 == authorization.spend_policy_sha256
        and observation.ledger_id == authorization.ledger_id
        and observation.ledger_entry_id == authorization.ledger_entry_id
        and observation.artifact_sha256 == artifact.artifact_sha256
        and observation.authorization_sha256 == artifact.authorization_sha256
        and observation.outcome_sha256 == artifact.outcome_sha256
        and observation.provider_response_sha256 == artifact.provider_response_sha256
        and observation.provider_request_id == artifact.provider_request_id
        and observation.model == request.route.model
        and observation.effort == request.route.effort
        and observation.usage == artifact.usage
        and observation.latency_ms == artifact.latency_ms
        and observation.cost_microusd == artifact.cost_microusd
        and request.route.provider == "openai"
        and artifact.status == "completed"
        and artifact.outcome_status == "response_received"
        and artifact.ledger_status == "settled"
        and artifact.error is None
    )


def _verify_local_provenance(
    artifact: BrokeredEvaluationArtifact,
    expected: AssignmentAuthorization,
    audit_directory: Path,
    ledger: SpendLedger,
) -> None:
    state = inspect_broker_recovery(audit_directory, expected, ledger)
    entry = ledger.entry_status(expected.ledger_entry_id)
    if (
        artifact.authorization != expected
        or artifact.authorization_sha256 != state.authorization_sha256
        or state.phase != "finished"
        or state.outcome_status != "response_received"
        or state.outcome_sha256 != artifact.outcome_sha256
        or state.response_sha256 != artifact.provider_response_sha256
        or state.latency_ms != artifact.latency_ms
        or state.error is not None
        or state.ledger_status != "settled"
        or entry is None
        or entry.status != "settled"
        or entry.charged_microusd != artifact.cost_microusd
    ):
        raise ValueError("evaluation conformance local provenance mismatch")


def _policy_matches_authorization(
    policy: EvaluationConformancePolicy,
    authorization: AssignmentAuthorization,
) -> bool:
    return (
        policy.plan_sha256 == authorization.plan_sha256
        and policy.batch_sha256 == authorization.batch_sha256
        and policy.sample_id == authorization.sample_id
        and policy.candidate_id == authorization.candidate_id
        and policy.evaluation_request_sha256 == authorization.evaluation_request_sha256
        and policy.provider_request_sha256 == authorization.provider_request_sha256
        and policy.spend_policy_sha256 == authorization.spend_policy_sha256
        and policy.ledger_id == authorization.ledger_id
        and policy.ledger_entry_id == authorization.ledger_entry_id
    )


def prepare_evaluation_conformance_policy(
    batch: ExecutionBatch,
    sample_id: str,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    audit_directory: Path,
    policy_id: str,
    valid_from: datetime,
    valid_until: datetime,
    max_observation_age_seconds: int,
    observers: tuple[TrustedEvaluationConformanceObserver, ...],
    allowed_sdk_versions: tuple[str, ...],
) -> EvaluationConformancePolicy:
    """Pre-register one exact no-send conformance ceremony."""

    batch = ExecutionBatch.model_validate_json(canonical_bytes(batch))
    spend_policy = SpendPolicy.model_validate_json(canonical_bytes(spend_policy))
    valid_from = _require_utc(valid_from)
    valid_until = _require_utc(valid_until)
    if audit_directory.exists() or not audit_directory.parent.is_dir():
        raise ValueError("conformance policy requires a fresh audit path")
    if ledger.snapshot().blocked:
        raise ValueError("conformance policy requires an unblocked ledger")
    if not (
        spend_policy.valid_from <= valid_from
        and valid_until <= spend_policy.valid_until
    ):
        raise ValueError("conformance policy exceeds spending-policy validity")
    payload = build_openai_conformance_payload(batch, sample_id, spend_policy)
    authorization = make_assignment_authorization(
        batch,
        sample_id,
        payload,
        spend_policy,
        ledger,
        digest(str(audit_directory.resolve()).encode()),
    )
    if ledger.entry_status(authorization.ledger_entry_id) is not None:
        raise ValueError("conformance policy ledger entry already exists")
    return EvaluationConformancePolicy(
        policy_id=policy_id,
        plan_sha256=authorization.plan_sha256,
        batch_sha256=authorization.batch_sha256,
        sample_id=authorization.sample_id,
        candidate_id=authorization.candidate_id,
        evaluation_request_sha256=authorization.evaluation_request_sha256,
        provider_request_sha256=authorization.provider_request_sha256,
        spend_policy_sha256=authorization.spend_policy_sha256,
        ledger_id=authorization.ledger_id,
        ledger_entry_id=authorization.ledger_entry_id,
        valid_from=valid_from,
        valid_until=valid_until,
        max_observation_age_seconds=max_observation_age_seconds,
        observers=observers,
        allowed_sdk_versions=allowed_sdk_versions,
    )


def validate_evaluation_conformance_preflight(
    batch: ExecutionBatch,
    sample_id: str,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    audit_directory: Path,
    policy: EvaluationConformancePolicy,
    sdk_version: str,
    now: datetime,
) -> AssignmentAuthorization:
    """Fail before credential access unless one run matches its prepared policy."""

    current = _require_utc(now)
    batch = ExecutionBatch.model_validate_json(canonical_bytes(batch))
    spend_policy = SpendPolicy.model_validate_json(canonical_bytes(spend_policy))
    policy = EvaluationConformancePolicy.model_validate_json(canonical_bytes(policy))
    if audit_directory.exists() or not audit_directory.parent.is_dir():
        raise ValueError("conformance preflight requires a fresh audit path")
    if ledger.snapshot().blocked:
        raise ValueError("conformance preflight requires an unblocked ledger")
    payload = build_openai_conformance_payload(batch, sample_id, spend_policy)
    authorization = make_assignment_authorization(
        batch,
        sample_id,
        payload,
        spend_policy,
        ledger,
        digest(str(audit_directory.resolve()).encode()),
    )
    if (
        not _policy_matches_authorization(policy, authorization)
        or not (
            spend_policy.valid_from <= policy.valid_from
            and policy.valid_until <= spend_policy.valid_until
        )
        or not policy.valid_from <= current <= policy.valid_until
        or not spend_policy.valid_from <= current < spend_policy.valid_until
        or sdk_version not in policy.allowed_sdk_versions
        or ledger.entry_status(authorization.ledger_entry_id) is not None
    ):
        raise ValueError("conformance run does not match its prepared policy")
    return authorization


def make_evaluation_conformance_observation(
    batch: ExecutionBatch,
    artifact: BrokeredEvaluationArtifact,
    expected: AssignmentAuthorization,
    audit_directory: Path,
    ledger: SpendLedger,
    policy: EvaluationConformancePolicy,
    observed_at: datetime,
    sdk_version: str,
    transport_evidence_sha256: str,
) -> EvaluationConformanceObservation:
    """Create signable metadata after, never in place of, a credentialed probe."""

    batch = ExecutionBatch.model_validate_json(canonical_bytes(batch))
    artifact = BrokeredEvaluationArtifact.model_validate_json(canonical_bytes(artifact))
    expected = AssignmentAuthorization.model_validate_json(canonical_bytes(expected))
    policy = EvaluationConformancePolicy.model_validate_json(canonical_bytes(policy))
    request = _assignment(batch, policy.sample_id)
    if (
        artifact.usage is None
        or artifact.usage.unit != "tokens"
        or artifact.latency_ms is None
    ):
        raise ValueError("evaluation conformance requires a completed artifact")
    if artifact.cost_microusd is None or artifact.provider_response_sha256 is None:
        raise ValueError("evaluation conformance requires a completed artifact")
    if artifact.provider_request_id is None:
        raise ValueError("evaluation conformance requires a provider request identity")
    _verify_local_provenance(artifact, expected, audit_directory, ledger)
    observation = EvaluationConformanceObservation(
        conformance_policy_sha256=policy.policy_sha256,
        plan_sha256=batch.plan_sha256,
        batch_sha256=batch.batch_sha256,
        sample_id=request.sample_id,
        candidate_id=request.route.candidate_id,
        evaluation_request_sha256=request.request_sha256,
        provider_request_sha256=expected.provider_request_sha256,
        spend_policy_sha256=expected.spend_policy_sha256,
        ledger_id=expected.ledger_id,
        ledger_entry_id=expected.ledger_entry_id,
        artifact_sha256=artifact.artifact_sha256,
        authorization_sha256=artifact.authorization_sha256,
        outcome_sha256=artifact.outcome_sha256,
        provider_response_sha256=artifact.provider_response_sha256,
        provider_request_id=artifact.provider_request_id,
        model=request.route.model,
        effort=request.route.effort,
        usage=artifact.usage,
        latency_ms=artifact.latency_ms,
        cost_microusd=artifact.cost_microusd,
        observed_at=_require_utc(observed_at),
        sdk_version=sdk_version,
        transport_evidence_sha256=transport_evidence_sha256,
    )
    if (
        policy.plan_sha256 != batch.plan_sha256
        or policy.batch_sha256 != batch.batch_sha256
        or policy.candidate_id != request.route.candidate_id
        or policy.evaluation_request_sha256 != request.request_sha256
        or policy.provider_request_sha256 != expected.provider_request_sha256
        or policy.spend_policy_sha256 != expected.spend_policy_sha256
        or policy.ledger_id != expected.ledger_id
        or policy.ledger_entry_id != expected.ledger_entry_id
        or not policy.valid_from <= observation.observed_at <= policy.valid_until
        or observation.sdk_version not in policy.allowed_sdk_versions
        or not _sources_match(observation, batch, artifact, expected)
    ):
        raise ValueError("evaluation conformance observation source mismatch")
    return observation


def sign_evaluation_conformance_observation(
    observation: EvaluationConformanceObservation,
    signer_id: str,
    private_key: bytes,
) -> SignedEvaluationConformanceObservation:
    """Sign canonical observation bytes; callers retain private-key custody."""

    observation = EvaluationConformanceObservation.model_validate_json(
        canonical_bytes(observation)
    )
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(observation))
        public_key = key.public_key().public_bytes_raw()
    except (TypeError, ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedEvaluationConformanceObservation(
        observation=observation,
        signature=EvaluationConformanceSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            observation_sha256=observation.observation_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def authenticate_evaluation_conformance(
    signed: SignedEvaluationConformanceObservation,
    policy: EvaluationConformancePolicy,
    batch: ExecutionBatch,
    artifact: BrokeredEvaluationArtifact,
    expected: AssignmentAuthorization,
    audit_directory: Path,
    ledger: SpendLedger,
    now: datetime,
) -> AuthenticatedEvaluationConformance:
    """Verify signature, freshness, policy, and exact local artifact lineage."""

    current = _require_utc(now)
    signed = SignedEvaluationConformanceObservation.model_validate_json(
        canonical_bytes(signed)
    )
    policy = EvaluationConformancePolicy.model_validate_json(canonical_bytes(policy))
    batch = ExecutionBatch.model_validate_json(canonical_bytes(batch))
    artifact = BrokeredEvaluationArtifact.model_validate_json(canonical_bytes(artifact))
    expected = AssignmentAuthorization.model_validate_json(canonical_bytes(expected))
    _verify_local_provenance(artifact, expected, audit_directory, ledger)
    observation = signed.observation
    if (
        observation.conformance_policy_sha256 != policy.policy_sha256
        or observation.plan_sha256 != policy.plan_sha256
        or observation.batch_sha256 != policy.batch_sha256
        or observation.sample_id != policy.sample_id
        or observation.candidate_id != policy.candidate_id
        or observation.evaluation_request_sha256 != policy.evaluation_request_sha256
        or observation.provider_request_sha256 != policy.provider_request_sha256
        or observation.spend_policy_sha256 != policy.spend_policy_sha256
        or observation.ledger_id != policy.ledger_id
        or observation.ledger_entry_id != policy.ledger_entry_id
        or observation.sdk_version not in policy.allowed_sdk_versions
        or not policy.valid_from
        <= observation.observed_at
        <= current
        <= policy.valid_until
        or (current - observation.observed_at).total_seconds()
        > policy.max_observation_age_seconds
        or not _sources_match(observation, batch, artifact, expected)
    ):
        raise ValueError("evaluation conformance observation does not match policy")
    matches = [
        item
        for item in policy.observers
        if item.observer_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("evaluation conformance observer is not trusted")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("evaluation conformance signature key differs from policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(observation),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError(
            "evaluation conformance signature verification failed"
        ) from None
    return AuthenticatedEvaluationConformance(
        conformance_policy_sha256=policy.policy_sha256,
        plan_sha256=batch.plan_sha256,
        batch_sha256=batch.batch_sha256,
        sample_id=observation.sample_id,
        candidate_id=observation.candidate_id,
        evaluation_request_sha256=observation.evaluation_request_sha256,
        provider_request_sha256=observation.provider_request_sha256,
        spend_policy_sha256=observation.spend_policy_sha256,
        ledger_id=observation.ledger_id,
        ledger_entry_id=observation.ledger_entry_id,
        artifact_sha256=artifact.artifact_sha256,
        signer_id=trusted.observer_id,
        signed_observation=signed,
        authenticated_at=current,
    )
