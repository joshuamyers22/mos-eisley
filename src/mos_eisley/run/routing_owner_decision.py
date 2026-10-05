"""Signed G6-05 owner-decision contract for offline R2 binding checks."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest

_OWNER_DECISION_DOMAIN = b"mos-eisley/g605-owner-decision/v1\0"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("owner-decision time must use explicit UTC")
    return value


def _decode(value: str, size: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("owner-decision key or signature is not base64") from None
    if len(decoded) != size or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("owner-decision key or signature is not canonical")
    return decoded


class FrozenG605OwnerDecisionAnchor(Contract):
    """Expected G6-05 inputs supplied outside the signed decision record."""

    schema_version: Literal[1] = 1
    qualification_packet_sha256: Digest
    qualification_evidence_sha256: Digest
    source_handoff_sha256: Digest
    decision_readiness_sha256: Digest
    technical_review_sha256: Digest
    g5_claim_sha256: Digest
    owner_trust_sha256: Digest
    valid_until: datetime

    @field_validator("valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class G605OwnerDecisionTrust(Contract):
    schema_version: Literal[1] = 1
    owner_id: Identifier
    signer_id: Identifier
    public_key_base64: str
    valid_from: datetime
    valid_until: datetime

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_trust(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("owner-decision trust window is invalid")
        _decode(self.public_key_base64, 32)
        return self


class G605OwnerDecision(Contract):
    schema_version: Literal[1] = 1
    status: Literal["go", "no_go"]
    qualification_packet_sha256: Digest
    qualification_evidence_sha256: Digest
    source_handoff_sha256: Digest
    decision_readiness_sha256: Digest
    technical_review_sha256: Digest
    g5_claim_sha256: Digest
    owner_id: Identifier
    cohort_id: Identifier
    signer_id: Identifier
    candidate_policy_sha256: Digest
    selected_candidate_id: Digest
    fallback_candidate_ids: Annotated[tuple[Digest, ...], Field(max_length=256)] = ()
    broker_build_sha256: Digest
    target_host_id: Identifier
    witness_epoch_id: Digest
    approved_task_types: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=64)
    ]
    approved_stages: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=64)
    ]
    max_assignments: Annotated[int, Field(gt=0, le=256)]
    max_concurrent: Annotated[int, Field(gt=0, le=256)]
    task_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    session_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    cohort_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    request_maximum_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    max_stop_latency_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    issued_at: datetime
    valid_until: datetime

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def canonical_envelope(self) -> Self:
        if (
            self.valid_until <= self.issued_at
            or self.fallback_candidate_ids
            != tuple(sorted(set(self.fallback_candidate_ids)))
            or self.selected_candidate_id in self.fallback_candidate_ids
            or self.approved_task_types != tuple(sorted(set(self.approved_task_types)))
            or self.approved_stages != tuple(sorted(set(self.approved_stages)))
            or self.max_concurrent > self.max_assignments
            or self.request_maximum_microusd
            > min(
                self.task_ceiling_microusd,
                self.session_ceiling_microusd,
                self.cohort_ceiling_microusd,
            )
        ):
            raise ValueError("owner-decision envelope is inconsistent")
        return self


class SignedG605OwnerDecision(Contract):
    decision: G605OwnerDecision
    signature_base64: str

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64)
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G605OwnerDecisionAssessment(Contract):
    schema_version: Literal[1] = 1
    signed_decision_sha256: Digest
    go_reference_reviewable: bool
    reasons: tuple[Identifier, ...]
    g5_qualified: Literal[False] = False
    qualification_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def sign_synthetic_g605_owner_decision(
    decision: G605OwnerDecision, private_key: bytes
) -> SignedG605OwnerDecision:
    """Fixture helper; real owner key custody and authorization are external."""
    signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(
        _OWNER_DECISION_DOMAIN + canonical_bytes(decision)
    )
    return SignedG605OwnerDecision(
        decision=decision,
        signature_base64=base64.b64encode(signature).decode("ascii"),
    )


def validate_offline_g605_owner_decision(
    *,
    signed: SignedG605OwnerDecision,
    trust: G605OwnerDecisionTrust,
    anchor: FrozenG605OwnerDecisionAnchor,
    now: datetime,
) -> G605OwnerDecisionAssessment:
    """Verify signed bytes and frozen references without granting a real go."""
    _utc(now)
    decision = signed.decision
    reasons: set[str] = set()
    if decision.status != "go":
        reasons.add("owner_no_go")
    if (
        decision.qualification_packet_sha256 != anchor.qualification_packet_sha256
        or decision.qualification_evidence_sha256
        != anchor.qualification_evidence_sha256
        or decision.source_handoff_sha256 != anchor.source_handoff_sha256
        or decision.decision_readiness_sha256 != anchor.decision_readiness_sha256
        or decision.technical_review_sha256 != anchor.technical_review_sha256
        or decision.g5_claim_sha256 != anchor.g5_claim_sha256
        or digest(canonical_bytes(trust)) != anchor.owner_trust_sha256
    ):
        reasons.add("owner_decision_binding_mismatch")
    if decision.owner_id != trust.owner_id or decision.signer_id != trust.signer_id:
        reasons.add("owner_signer_mismatch")
    if (
        not trust.valid_from <= decision.issued_at
        or not decision.issued_at <= now < decision.valid_until
        or now >= trust.valid_until
        or now >= anchor.valid_until
        or decision.valid_until > trust.valid_until
        or decision.valid_until > anchor.valid_until
    ):
        reasons.add("owner_decision_stale")
    try:
        Ed25519PublicKey.from_public_bytes(_decode(trust.public_key_base64, 32)).verify(
            _decode(signed.signature_base64, 64),
            _OWNER_DECISION_DOMAIN + canonical_bytes(decision),
        )
    except (InvalidSignature, ValueError):
        reasons.add("owner_signature_invalid")
    return G605OwnerDecisionAssessment(
        signed_decision_sha256=signed.decision_sha256,
        go_reference_reviewable=not reasons,
        reasons=tuple(sorted(reasons)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a signed G6-05 owner-decision reference offline"
    )
    parser.add_argument("signed_decision", type=Path)
    parser.add_argument("owner_trust", type=Path)
    parser.add_argument("frozen_anchor", type=Path)
    parser.add_argument("--now", required=True, help="Explicit ISO-8601 UTC time")
    args = parser.parse_args()
    for path in (args.signed_decision, args.owner_trust, args.frozen_anchor):
        if path.stat().st_size > 2_000_000:
            parser.error("owner-decision JSON exceeds the 2 MB metadata limit")
    result = validate_offline_g605_owner_decision(
        signed=SignedG605OwnerDecision.model_validate_json(
            args.signed_decision.read_bytes()
        ),
        trust=G605OwnerDecisionTrust.model_validate_json(args.owner_trust.read_bytes()),
        anchor=FrozenG605OwnerDecisionAnchor.model_validate_json(
            args.frozen_anchor.read_bytes()
        ),
        now=datetime.fromisoformat(args.now),
    )
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0 if result.go_reference_reviewable else 1


if __name__ == "__main__":
    raise SystemExit(main())
