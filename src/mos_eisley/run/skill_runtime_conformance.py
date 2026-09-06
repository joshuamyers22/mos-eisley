"""Authenticated operator attestation for one published OpenAI runtime exchange."""

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
from mos_eisley.run.skill_runtime_response import (
    PublishedSkillRuntimeResult,
    SkillRuntimeResponsePublication,
    SkillRuntimeResponseStore,
)

_DOMAIN = b"mos-eisley/skill-runtime-openai-conformance/v1\x00"
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


class TrustedSkillRuntimeConformanceObserver(Contract):
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


class SkillRuntimeConformancePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_conformance_policy"] = (
        "skill_runtime_conformance_policy"
    )
    policy_id: Identifier
    response_store_policy_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_observation_age_seconds: Annotated[int, Field(gt=0, le=2_592_000)]
    observers: Annotated[
        tuple[TrustedSkillRuntimeConformanceObserver, ...],
        Field(min_length=1, max_length=20),
    ]
    allowed_sdk_versions: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=20)
    ]
    provider: Literal["openai"] = "openai"
    endpoint_origin: Literal["https://api.openai.com"] = "https://api.openai.com"
    api_family: Literal["responses"] = "responses"
    credential_mode: Literal["api_key"] = "api_key"
    official_sdk_required: Literal[True] = True
    zero_automatic_retries_required: Literal[True] = True
    provider_storage_disabled_required: Literal[True] = True
    truncation_disabled_required: Literal[True] = True
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("runtime conformance policy window must be positive")
        identities = tuple(item.observer_id for item in self.observers)
        keys = tuple(item.public_key_sha256 for item in self.observers)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "runtime conformance observers need sorted unique identities and keys"
            )
        if tuple(sorted(set(self.allowed_sdk_versions))) != self.allowed_sdk_versions:
            raise ValueError("allowed SDK versions must be unique and sorted")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeConformanceObservation(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_conformance_observation"] = (
        "skill_runtime_conformance_observation"
    )
    conformance_policy_sha256: Digest
    response_store_policy_sha256: Digest
    publication_id: Digest
    publication_sha256: Digest
    result_sha256: Digest
    transaction_id: Digest
    provider_request_id: Annotated[str, Field(min_length=1, max_length=1000)]
    model: Identifier
    effort: Effort
    observed_at: UtcTimestamp
    sdk_package: Literal["openai"] = "openai"
    sdk_version: Identifier
    transport_evidence_sha256: Digest
    provider: Literal["openai"] = "openai"
    endpoint_origin: Literal["https://api.openai.com"] = "https://api.openai.com"
    api_family: Literal["responses"] = "responses"
    credential_mode: Literal["api_key"] = "api_key"
    credentialed_exchange_attested: Literal[True] = True
    bounded_http_client_attested: Literal[True] = True
    automatic_retries: Literal[0] = 0
    provider_storage_requested: Literal[False] = False
    truncation_disabled: Literal[True] = True
    raw_response_exported: Literal[False] = False
    provider_credential_persisted: Literal[False] = False
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
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


class SkillRuntimeConformanceSignature(Contract):
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


class SignedSkillRuntimeConformanceObservation(Contract):
    schema_version: Literal[1] = 1
    observation: SkillRuntimeConformanceObservation
    signature: SkillRuntimeConformanceSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.observation_sha256 != self.observation.observation_sha256:
            raise ValueError("signature does not identify this conformance observation")
        return self

    @property
    def signed_observation_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedSkillRuntimeConformance(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_skill_runtime_conformance"] = (
        "authenticated_skill_runtime_conformance"
    )
    conformance_policy_sha256: Digest
    response_store_policy_sha256: Digest
    publication_id: Digest
    publication_sha256: Digest
    result_sha256: Digest
    signer_id: Identifier
    signed_observation: SignedSkillRuntimeConformanceObservation
    authenticated_at: UtcTimestamp
    credentialed_exchange_attested: Literal[True] = True
    local_publication_reverified: Literal[True] = True
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
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
            or self.response_store_policy_sha256
            != observation.response_store_policy_sha256
            or self.publication_id != observation.publication_id
            or self.publication_sha256 != observation.publication_sha256
            or self.result_sha256 != observation.result_sha256
            or self.signer_id != self.signed_observation.signature.signer_id
            or self.authenticated_at < observation.observed_at
        ):
            raise ValueError(
                "authenticated runtime conformance does not match observation"
            )
        return self

    @property
    def authenticated_conformance_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_skill_runtime_conformance_observer(
    observer_id: str, public_key: bytes
) -> TrustedSkillRuntimeConformanceObserver:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedSkillRuntimeConformanceObserver(
        observer_id=observer_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _sources_match(
    observation: SkillRuntimeConformanceObservation,
    publication: SkillRuntimeResponsePublication,
    result: PublishedSkillRuntimeResult,
) -> bool:
    return (
        observation.response_store_policy_sha256
        == publication.response_store_policy_sha256
        == result.response_store_policy_sha256
        and observation.publication_id
        == publication.publication_id
        == result.publication_id
        and observation.publication_sha256 == publication.publication_sha256
        and observation.result_sha256
        == publication.result_sha256
        == result.result_sha256
        and observation.transaction_id
        == publication.transaction_id
        == result.transaction_id
        and observation.provider_request_id == result.provider_request_id
        and observation.model == result.model
        and observation.effort == result.effort
        and observation.observed_at >= publication.committed_at
    )


def make_skill_runtime_conformance_observation(
    publication: SkillRuntimeResponsePublication,
    result: PublishedSkillRuntimeResult,
    policy: SkillRuntimeConformancePolicy,
    observed_at: datetime,
    sdk_version: str,
    transport_evidence_sha256: str,
) -> SkillRuntimeConformanceObservation:
    """Create signable metadata after, never in place of, a credentialed exchange."""

    observation = SkillRuntimeConformanceObservation(
        conformance_policy_sha256=policy.policy_sha256,
        response_store_policy_sha256=result.response_store_policy_sha256,
        publication_id=publication.publication_id,
        publication_sha256=publication.publication_sha256,
        result_sha256=result.result_sha256,
        transaction_id=result.transaction_id,
        provider_request_id=result.provider_request_id,
        model=result.model,
        effort=result.effort,
        observed_at=_require_utc(observed_at),
        sdk_version=sdk_version,
        transport_evidence_sha256=transport_evidence_sha256,
    )
    if (
        policy.response_store_policy_sha256 != publication.response_store_policy_sha256
        or not policy.valid_from <= observation.observed_at <= policy.valid_until
        or observation.sdk_version not in policy.allowed_sdk_versions
        or not _sources_match(observation, publication, result)
    ):
        raise ValueError("runtime conformance observation source mismatch")
    return observation


def sign_skill_runtime_conformance_observation(
    observation: SkillRuntimeConformanceObservation,
    signer_id: str,
    private_key: bytes,
) -> SignedSkillRuntimeConformanceObservation:
    """Sign canonical observation bytes; callers retain private-key custody."""

    observation = SkillRuntimeConformanceObservation.model_validate_json(
        canonical_bytes(observation)
    )
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(observation))
        public_key = key.public_key().public_bytes_raw()
    except (TypeError, ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedSkillRuntimeConformanceObservation(
        observation=observation,
        signature=SkillRuntimeConformanceSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            observation_sha256=observation.observation_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def authenticate_skill_runtime_conformance(
    signed: SignedSkillRuntimeConformanceObservation,
    policy: SkillRuntimeConformancePolicy,
    response_store: SkillRuntimeResponseStore,
    now: datetime,
) -> AuthenticatedSkillRuntimeConformance:
    """Verify signature, freshness, policy, and exact local publication lineage."""

    current = _require_utc(now)
    signed = SignedSkillRuntimeConformanceObservation.model_validate_json(
        canonical_bytes(signed)
    )
    policy = SkillRuntimeConformancePolicy.model_validate_json(canonical_bytes(policy))
    observation = signed.observation
    if (
        policy.response_store_policy_sha256 != response_store.policy.policy_sha256
        or observation.conformance_policy_sha256 != policy.policy_sha256
        or observation.response_store_policy_sha256
        != policy.response_store_policy_sha256
        or observation.sdk_version not in policy.allowed_sdk_versions
        or not policy.valid_from
        <= observation.observed_at
        <= current
        <= policy.valid_until
        or (current - observation.observed_at).total_seconds()
        > policy.max_observation_age_seconds
    ):
        raise ValueError("runtime conformance observation does not match policy")
    matches = [
        item
        for item in policy.observers
        if item.observer_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("runtime conformance observer is not trusted")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("runtime conformance signature key differs from policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(observation),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("runtime conformance signature verification failed") from None
    publication, result = response_store.load(observation.publication_id)
    if not _sources_match(observation, publication, result):
        raise ValueError("runtime conformance publication provenance mismatch")
    return AuthenticatedSkillRuntimeConformance(
        conformance_policy_sha256=policy.policy_sha256,
        response_store_policy_sha256=policy.response_store_policy_sha256,
        publication_id=publication.publication_id,
        publication_sha256=publication.publication_sha256,
        result_sha256=result.result_sha256,
        signer_id=trusted.observer_id,
        signed_observation=signed,
        authenticated_at=current,
    )
