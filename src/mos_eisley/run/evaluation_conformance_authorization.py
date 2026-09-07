"""Independent signed authority for one exact OpenAI conformance attempt."""

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
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.evaluation_conformance import EvaluationConformancePolicy

_DOMAIN = b"mos-eisley/evaluation-conformance-authorization/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


class TrustedEvaluationConformanceAuthority(Contract):
    authority_id: Identifier
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32, "public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32, "public key"))


class EvaluationConformanceAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["evaluation_conformance_authority_policy"] = (
        "evaluation_conformance_authority_policy"
    )
    policy_id: Identifier
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_authorization_lifetime_seconds: Annotated[int, Field(gt=0, le=3600)]
    authorities: Annotated[
        tuple[TrustedEvaluationConformanceAuthority, ...],
        Field(min_length=1, max_length=20),
    ]
    provider: Literal["openai"] = "openai"
    command: Literal["openai-conformance"] = "openai-conformance"
    independent_signature_required: Literal[True] = True
    exact_policy_binding_required: Literal[True] = True
    explicit_local_consent_also_required: Literal[True] = True
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("conformance authority policy window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "conformance authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class EvaluationConformanceAuthorization(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["evaluation_conformance_authorization"] = (
        "evaluation_conformance_authorization"
    )
    authority_policy_sha256: Digest
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
    max_cost_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    provider: Literal["openai"] = "openai"
    command: Literal["openai-conformance"] = "openai-conformance"
    credential_mode: Literal["api_key"] = "api_key"
    currency: Literal["USD"] = "USD"
    one_exact_attempt_authorized: Literal[True] = True
    blinded_data_transfer_authorized: Literal[True] = True
    credential_access_authorized: Literal[True] = True
    spend_authorized: Literal[True] = True
    unblinded_data_transfer_authorized: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    batch_conversion_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def positive_window(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("conformance authorization window must be positive")
        return self

    @property
    def authorization_sha256(self) -> str:
        return digest(canonical_bytes(self))


class EvaluationConformanceAuthorizationSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    authorization_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedEvaluationConformanceAuthorization(Contract):
    schema_version: Literal[1] = 1
    authorization: EvaluationConformanceAuthorization
    signature: EvaluationConformanceAuthorizationSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if (
            self.signature.authorization_sha256
            != self.authorization.authorization_sha256
        ):
            raise ValueError(
                "signature does not identify this conformance authorization"
            )
        return self

    @property
    def signed_authorization_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_evaluation_conformance_authority(
    authority_id: str, public_key: bytes
) -> TrustedEvaluationConformanceAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedEvaluationConformanceAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _validate_authority_separation(
    policy: EvaluationConformanceAuthorityPolicy,
    conformance_policy: EvaluationConformancePolicy,
) -> None:
    observer_ids = {item.observer_id for item in conformance_policy.observers}
    observer_keys = {item.public_key_sha256 for item in conformance_policy.observers}
    if any(
        item.authority_id in observer_ids or item.public_key_sha256 in observer_keys
        for item in policy.authorities
    ):
        raise ValueError("conformance authority must be independent of observers")


def make_evaluation_conformance_authorization(
    conformance_policy: EvaluationConformancePolicy,
    spend_policy: SpendPolicy,
    authority_policy: EvaluationConformanceAuthorityPolicy,
    issued_at: datetime,
    valid_until: datetime,
) -> EvaluationConformanceAuthorization:
    """Derive exact signable authority without reading a credential or sending."""

    conformance_policy = EvaluationConformancePolicy.model_validate_json(
        canonical_bytes(conformance_policy)
    )
    spend_policy = SpendPolicy.model_validate_json(canonical_bytes(spend_policy))
    authority_policy = EvaluationConformanceAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    _validate_authority_separation(authority_policy, conformance_policy)
    if conformance_policy.spend_policy_sha256 != spend_policy.policy_sha256 or not (
        spend_policy.valid_from <= conformance_policy.valid_from
        and conformance_policy.valid_until <= spend_policy.valid_until
    ):
        raise ValueError("conformance authorization spending provenance mismatch")
    if not (
        authority_policy.valid_from <= issued
        and conformance_policy.valid_from <= issued
        and issued < expires
        and expires <= authority_policy.valid_until
        and expires <= conformance_policy.valid_until
        and (expires - issued).total_seconds()
        <= authority_policy.max_authorization_lifetime_seconds
    ):
        raise ValueError("conformance authorization window exceeds policy")
    return EvaluationConformanceAuthorization(
        authority_policy_sha256=authority_policy.policy_sha256,
        conformance_policy_sha256=conformance_policy.policy_sha256,
        plan_sha256=conformance_policy.plan_sha256,
        batch_sha256=conformance_policy.batch_sha256,
        sample_id=conformance_policy.sample_id,
        candidate_id=conformance_policy.candidate_id,
        evaluation_request_sha256=conformance_policy.evaluation_request_sha256,
        provider_request_sha256=conformance_policy.provider_request_sha256,
        spend_policy_sha256=conformance_policy.spend_policy_sha256,
        ledger_id=conformance_policy.ledger_id,
        ledger_entry_id=conformance_policy.ledger_entry_id,
        max_cost_microusd=spend_policy.max_cost_microusd,
        issued_at=issued,
        valid_until=expires,
    )


def sign_evaluation_conformance_authorization(
    authorization: EvaluationConformanceAuthorization,
    signer_id: str,
    private_key: bytes,
) -> SignedEvaluationConformanceAuthorization:
    """Sign exact authority; command-line paths never accept private keys."""

    if len(private_key) != 32:
        raise ValueError("Ed25519 private key must contain 32 bytes")
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(authorization))
    except (ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedEvaluationConformanceAuthorization(
        authorization=authorization,
        signature=EvaluationConformanceAuthorizationSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            authorization_sha256=authorization.authorization_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def verify_evaluation_conformance_authorization(
    signed: SignedEvaluationConformanceAuthorization,
    authority_policy: EvaluationConformanceAuthorityPolicy,
    conformance_policy: EvaluationConformancePolicy,
    spend_policy: SpendPolicy,
    now: datetime,
) -> EvaluationConformanceAuthorization:
    """Authenticate current exact transfer/spend authority before credential access."""

    current = _require_utc(now)
    signed = SignedEvaluationConformanceAuthorization.model_validate_json(
        canonical_bytes(signed)
    )
    authority_policy = EvaluationConformanceAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    matches = [
        item
        for item in authority_policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if (
        len(matches) != 1
        or matches[0].public_key_sha256 != signed.signature.public_key_sha256
        or signed.authorization.authority_policy_sha256
        != authority_policy.policy_sha256
    ):
        raise ValueError("conformance authorization signer is not enrolled")
    signer = matches[0]
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(signer.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(signed.authorization),
        )
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("conformance authorization signature is invalid") from None
    expected = make_evaluation_conformance_authorization(
        conformance_policy,
        spend_policy,
        authority_policy,
        signed.authorization.issued_at,
        signed.authorization.valid_until,
    )
    if (
        signed.authorization != expected
        or not authority_policy.valid_from <= current <= authority_policy.valid_until
        or not conformance_policy.valid_from
        <= current
        <= conformance_policy.valid_until
        or not signed.authorization.issued_at
        <= current
        <= signed.authorization.valid_until
    ):
        raise ValueError("conformance authorization does not match current policy")
    return signed.authorization
