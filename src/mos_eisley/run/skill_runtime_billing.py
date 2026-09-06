"""Authenticated aggregate billing evidence for one published runtime exchange."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import Effort
from mos_eisley.run.skill_runtime_conformance import (
    AuthenticatedSkillRuntimeConformance,
    SkillRuntimeConformancePolicy,
    authenticate_skill_runtime_conformance,
)
from mos_eisley.run.skill_runtime_response import (
    PublishedSkillRuntimeResult,
    SkillRuntimeResponsePublication,
    SkillRuntimeResponseStore,
)

_DOMAIN = b"mos-eisley/skill-runtime-billing-evidence/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]
Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]
Tokens = Annotated[int, Field(ge=0)]


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


class TrustedSkillRuntimeBillingAuditor(Contract):
    auditor_id: Identifier
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32, "public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32, "public key"))


class SkillRuntimeBillingPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_billing_policy"] = "skill_runtime_billing_policy"
    policy_id: Identifier
    response_store_policy_sha256: Digest
    conformance_policy_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_evidence_age_seconds: Annotated[int, Field(gt=0, le=2_592_000)]
    auditors: Annotated[
        tuple[TrustedSkillRuntimeBillingAuditor, ...],
        Field(min_length=1, max_length=20),
    ]
    provider: Literal["openai"] = "openai"
    usage_endpoint: Literal["GET /organization/usage/completions"] = (
        "GET /organization/usage/completions"
    )
    costs_endpoint: Literal["GET /organization/costs"] = "GET /organization/costs"
    usage_bucket_width: Literal["1m"] = "1m"
    costs_bucket_width: Literal["1d"] = "1d"
    usage_grouped_by_project: Literal[True] = True
    usage_grouped_by_api_key: Literal[True] = True
    usage_grouped_by_model: Literal[True] = True
    usage_grouped_by_service_tier: Literal[True] = True
    costs_grouped_by_project: Literal[True] = True
    costs_grouped_by_api_key: Literal[True] = True
    costs_grouped_by_line_item: Literal[True] = True
    complete_pagination_required: Literal[True] = True
    exclusive_one_request_scope_required: Literal[True] = True
    exact_cost_match_required: Literal[True] = True
    ledger_mutation_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("runtime billing policy window must be positive")
        identities = tuple(item.auditor_id for item in self.auditors)
        keys = tuple(item.public_key_sha256 for item in self.auditors)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "runtime billing auditors need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeBillingObservation(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_billing_observation"] = (
        "skill_runtime_billing_observation"
    )
    billing_policy_sha256: Digest
    conformance_policy_sha256: Digest
    authenticated_conformance_sha256: Digest
    response_store_policy_sha256: Digest
    publication_id: Digest
    publication_sha256: Digest
    result_sha256: Digest
    transaction_id: Digest
    outcome_sha256: Digest
    spend_ledger_id: Digest
    ledger_entry_id: Digest
    provider_request_id: Annotated[str, Field(min_length=1, max_length=1000)]
    model: Identifier
    effort: Effort
    local_input_tokens: Tokens
    local_output_tokens: Tokens
    local_charged_microusd: Money
    external_input_tokens: Tokens
    external_output_tokens: Tokens
    external_cost_microusd: Money
    usage_bucket_start: UtcTimestamp
    usage_bucket_end: UtcTimestamp
    costs_bucket_start: UtcTimestamp
    costs_bucket_end: UtcTimestamp
    project_id_sha256: Digest
    api_key_id_sha256: Digest
    usage_evidence_sha256: Digest
    costs_evidence_sha256: Digest
    evidence_retrieved_at: UtcTimestamp
    provider: Literal["openai"] = "openai"
    service_tier: Literal["default"] = "default"
    usage_bucket_width: Literal["1m"] = "1m"
    costs_bucket_width: Literal["1d"] = "1d"
    external_scope_request_count: Literal[1] = 1
    official_admin_api_evidence_attested: Literal[True] = True
    complete_pagination_attested: Literal[True] = True
    exclusive_one_request_scope_attested: Literal[True] = True
    usage_aggregate_matches_local: Literal[True] = True
    cost_aggregate_matches_local: Literal[True] = True
    provider_request_id_present_in_billing_evidence: Literal[False] = False
    exact_request_cost_attribution_proven: Literal[False] = False
    provider_authorship_proven: Literal[False] = False
    invoice_finality_proven: Literal[False] = False
    raw_billing_evidence_included: Literal[False] = False
    provider_credential_included: Literal[False] = False
    ledger_mutation_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    provider_retry_authorized: Literal[False] = False
    quality_claimed: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator(
        "usage_bucket_start",
        "usage_bucket_end",
        "costs_bucket_start",
        "costs_bucket_end",
        "evidence_retrieved_at",
    )
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def coherent_aggregate_evidence(self) -> Self:
        if self.usage_bucket_end - self.usage_bucket_start != timedelta(minutes=1):
            raise ValueError(
                "runtime billing usage bucket must span exactly one minute"
            )
        if (
            self.usage_bucket_start.second != 0
            or self.usage_bucket_start.microsecond != 0
        ):
            raise ValueError("runtime billing usage bucket must align to a UTC minute")
        if self.costs_bucket_end - self.costs_bucket_start != timedelta(days=1):
            raise ValueError("runtime billing costs bucket must span exactly one day")
        if self.costs_bucket_start.time() != datetime.min.time():
            raise ValueError("runtime billing costs bucket must align to a UTC day")
        if self.evidence_retrieved_at < max(
            self.usage_bucket_end, self.costs_bucket_end
        ):
            raise ValueError("runtime billing evidence predates a completed bucket")
        if (
            self.local_input_tokens != self.external_input_tokens
            or self.local_output_tokens != self.external_output_tokens
            or self.local_charged_microusd != self.external_cost_microusd
        ):
            raise ValueError(
                "runtime billing aggregate does not exactly match local data"
            )
        return self

    @property
    def observation_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeBillingSignature(Contract):
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


class SignedSkillRuntimeBillingObservation(Contract):
    schema_version: Literal[1] = 1
    observation: SkillRuntimeBillingObservation
    signature: SkillRuntimeBillingSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.observation_sha256 != self.observation.observation_sha256:
            raise ValueError("signature does not identify this billing observation")
        return self

    @property
    def signed_observation_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedSkillRuntimeBillingEvidence(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_skill_runtime_billing_evidence"] = (
        "authenticated_skill_runtime_billing_evidence"
    )
    billing_policy_sha256: Digest
    conformance_policy_sha256: Digest
    authenticated_conformance_sha256: Digest
    response_store_policy_sha256: Digest
    publication_id: Digest
    publication_sha256: Digest
    result_sha256: Digest
    signer_id: Identifier
    signed_observation: SignedSkillRuntimeBillingObservation
    authenticated_at: UtcTimestamp
    conformance_reauthenticated: Literal[True] = True
    local_publication_reverified: Literal[True] = True
    billing_evidence_authenticated: Literal[True] = True
    exclusive_aggregate_billing_reconciled: Literal[True] = True
    exact_request_cost_attribution_proven: Literal[False] = False
    provider_authorship_proven: Literal[False] = False
    invoice_finality_proven: Literal[False] = False
    ledger_mutation_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    provider_retry_authorized: Literal[False] = False
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
            self.billing_policy_sha256 != observation.billing_policy_sha256
            or self.conformance_policy_sha256 != observation.conformance_policy_sha256
            or self.authenticated_conformance_sha256
            != observation.authenticated_conformance_sha256
            or self.response_store_policy_sha256
            != observation.response_store_policy_sha256
            or self.publication_id != observation.publication_id
            or self.publication_sha256 != observation.publication_sha256
            or self.result_sha256 != observation.result_sha256
            or self.signer_id != self.signed_observation.signature.signer_id
            or self.authenticated_at < observation.evidence_retrieved_at
        ):
            raise ValueError(
                "authenticated runtime billing evidence does not match source"
            )
        return self

    @property
    def authenticated_billing_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_skill_runtime_billing_auditor(
    auditor_id: str, public_key: bytes
) -> TrustedSkillRuntimeBillingAuditor:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedSkillRuntimeBillingAuditor(
        auditor_id=auditor_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _reauthenticate_conformance(
    source: AuthenticatedSkillRuntimeConformance,
    policy: SkillRuntimeConformancePolicy,
    response_store: SkillRuntimeResponseStore,
) -> None:
    verified = authenticate_skill_runtime_conformance(
        source.signed_observation,
        policy,
        response_store,
        source.authenticated_at,
    )
    if verified != source:
        raise ValueError("runtime billing conformance source is not authentic")


def _sources_match(
    observation: SkillRuntimeBillingObservation,
    conformance: AuthenticatedSkillRuntimeConformance,
    publication: SkillRuntimeResponsePublication,
    result: PublishedSkillRuntimeResult,
) -> bool:
    return (
        observation.authenticated_conformance_sha256
        == conformance.authenticated_conformance_sha256
        and observation.conformance_policy_sha256
        == conformance.conformance_policy_sha256
        and observation.response_store_policy_sha256
        == conformance.response_store_policy_sha256
        == publication.response_store_policy_sha256
        == result.response_store_policy_sha256
        and observation.publication_id
        == conformance.publication_id
        == publication.publication_id
        == result.publication_id
        and observation.publication_sha256
        == conformance.publication_sha256
        == publication.publication_sha256
        and observation.result_sha256
        == conformance.result_sha256
        == publication.result_sha256
        == result.result_sha256
        and observation.transaction_id
        == publication.transaction_id
        == result.transaction_id
        and observation.outcome_sha256
        == publication.outcome_sha256
        == result.outcome_sha256
        and observation.spend_ledger_id == result.spend_ledger_id
        and observation.ledger_entry_id == result.ledger_entry_id
        and observation.provider_request_id == result.provider_request_id
        and observation.model == result.model
        and observation.effort == result.effort
        and observation.local_input_tokens == result.usage.input
        and observation.local_output_tokens == result.usage.output
        and observation.local_charged_microusd == result.charged_microusd
        and observation.usage_bucket_start
        <= publication.committed_at
        < observation.usage_bucket_end
        and observation.costs_bucket_start
        <= publication.committed_at
        < observation.costs_bucket_end
        and observation.evidence_retrieved_at >= conformance.authenticated_at
    )


def make_skill_runtime_billing_observation(
    conformance: AuthenticatedSkillRuntimeConformance,
    conformance_policy: SkillRuntimeConformancePolicy,
    response_store: SkillRuntimeResponseStore,
    policy: SkillRuntimeBillingPolicy,
    *,
    external_input_tokens: int,
    external_output_tokens: int,
    external_cost_microusd: int,
    usage_bucket_start: datetime,
    usage_bucket_end: datetime,
    costs_bucket_start: datetime,
    costs_bucket_end: datetime,
    project_id_sha256: str,
    api_key_id_sha256: str,
    usage_evidence_sha256: str,
    costs_evidence_sha256: str,
    evidence_retrieved_at: datetime,
) -> SkillRuntimeBillingObservation:
    """Create signable metadata for separately retained aggregate billing evidence."""

    _reauthenticate_conformance(conformance, conformance_policy, response_store)
    publication, result = response_store.load(conformance.publication_id)
    observation = SkillRuntimeBillingObservation(
        billing_policy_sha256=policy.policy_sha256,
        conformance_policy_sha256=conformance_policy.policy_sha256,
        authenticated_conformance_sha256=(conformance.authenticated_conformance_sha256),
        response_store_policy_sha256=response_store.policy.policy_sha256,
        publication_id=publication.publication_id,
        publication_sha256=publication.publication_sha256,
        result_sha256=result.result_sha256,
        transaction_id=result.transaction_id,
        outcome_sha256=result.outcome_sha256,
        spend_ledger_id=result.spend_ledger_id,
        ledger_entry_id=result.ledger_entry_id,
        provider_request_id=result.provider_request_id,
        model=result.model,
        effort=result.effort,
        local_input_tokens=result.usage.input,
        local_output_tokens=result.usage.output,
        local_charged_microusd=result.charged_microusd,
        external_input_tokens=external_input_tokens,
        external_output_tokens=external_output_tokens,
        external_cost_microusd=external_cost_microusd,
        usage_bucket_start=_require_utc(usage_bucket_start),
        usage_bucket_end=_require_utc(usage_bucket_end),
        costs_bucket_start=_require_utc(costs_bucket_start),
        costs_bucket_end=_require_utc(costs_bucket_end),
        project_id_sha256=project_id_sha256,
        api_key_id_sha256=api_key_id_sha256,
        usage_evidence_sha256=usage_evidence_sha256,
        costs_evidence_sha256=costs_evidence_sha256,
        evidence_retrieved_at=_require_utc(evidence_retrieved_at),
    )
    if (
        policy.response_store_policy_sha256 != response_store.policy.policy_sha256
        or policy.conformance_policy_sha256 != conformance_policy.policy_sha256
        or not policy.valid_from
        <= observation.evidence_retrieved_at
        <= policy.valid_until
        or not _sources_match(observation, conformance, publication, result)
    ):
        raise ValueError("runtime billing observation source mismatch")
    return observation


def sign_skill_runtime_billing_observation(
    observation: SkillRuntimeBillingObservation,
    signer_id: str,
    private_key: bytes,
) -> SignedSkillRuntimeBillingObservation:
    """Sign canonical observation bytes; callers retain private-key custody."""

    observation = SkillRuntimeBillingObservation.model_validate_json(
        canonical_bytes(observation)
    )
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(observation))
        public_key = key.public_key().public_bytes_raw()
    except (TypeError, ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedSkillRuntimeBillingObservation(
        observation=observation,
        signature=SkillRuntimeBillingSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            observation_sha256=observation.observation_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def authenticate_skill_runtime_billing_evidence(
    signed: SignedSkillRuntimeBillingObservation,
    policy: SkillRuntimeBillingPolicy,
    conformance: AuthenticatedSkillRuntimeConformance,
    conformance_policy: SkillRuntimeConformancePolicy,
    response_store: SkillRuntimeResponseStore,
    now: datetime,
) -> AuthenticatedSkillRuntimeBillingEvidence:
    """Verify aggregate evidence signature, freshness, separation, and lineage."""

    current = _require_utc(now)
    signed = SignedSkillRuntimeBillingObservation.model_validate_json(
        canonical_bytes(signed)
    )
    policy = SkillRuntimeBillingPolicy.model_validate_json(canonical_bytes(policy))
    observation = signed.observation
    if (
        policy.response_store_policy_sha256 != response_store.policy.policy_sha256
        or policy.conformance_policy_sha256 != conformance_policy.policy_sha256
        or observation.billing_policy_sha256 != policy.policy_sha256
        or observation.conformance_policy_sha256 != policy.conformance_policy_sha256
        or not policy.valid_from
        <= observation.evidence_retrieved_at
        <= current
        <= policy.valid_until
        or (current - observation.evidence_retrieved_at).total_seconds()
        > policy.max_evidence_age_seconds
    ):
        raise ValueError("runtime billing observation does not match policy")
    matches = [
        item
        for item in policy.auditors
        if item.auditor_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("runtime billing auditor is not trusted")
    trusted = matches[0]
    conformance_ids = {item.observer_id for item in conformance_policy.observers}
    conformance_keys = {item.public_key_sha256 for item in conformance_policy.observers}
    if (
        trusted.auditor_id in conformance_ids
        or trusted.public_key_sha256 in conformance_keys
    ):
        raise ValueError("runtime billing auditor must be independent of conformance")
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("runtime billing signature key differs from policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(observation),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("runtime billing signature verification failed") from None
    _reauthenticate_conformance(conformance, conformance_policy, response_store)
    publication, result = response_store.load(observation.publication_id)
    if not _sources_match(observation, conformance, publication, result):
        raise ValueError("runtime billing publication provenance mismatch")
    return AuthenticatedSkillRuntimeBillingEvidence(
        billing_policy_sha256=policy.policy_sha256,
        conformance_policy_sha256=conformance_policy.policy_sha256,
        authenticated_conformance_sha256=(conformance.authenticated_conformance_sha256),
        response_store_policy_sha256=response_store.policy.policy_sha256,
        publication_id=publication.publication_id,
        publication_sha256=publication.publication_sha256,
        result_sha256=result.result_sha256,
        signer_id=trusted.auditor_id,
        signed_observation=signed,
        authenticated_at=current,
    )
