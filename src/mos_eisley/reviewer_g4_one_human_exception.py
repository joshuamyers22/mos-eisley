"""Exact, owner-signed exception for one G4 implementation-review subject.

This attests a governance choice about an already signed two-provider review.
It does not turn one human into independent human review or authorize acceptance.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    SourceRevision,
    verify_provenance_signature,
)
from mos_eisley.reviewer_single_operator_review import G4SingleOperatorReviewRecord

_EXCEPTION_DOMAIN = b"mos-eisley/g4-one-human-formal-review-exception/v1\x00"


class G4OneHumanFormalReviewException(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_one_human_formal_review_exception"] = (
        "g4_one_human_formal_review_exception"
    )
    integrated_revision: SourceRevision
    subject_sha256: Digest
    review_record_sha256: Digest
    amendment_document_sha256: Digest
    owner_signer_id: Identifier
    issued_at: datetime
    existing_review_explicitly_accepted: Literal[True] = True
    one_human_operator: Literal[True] = True
    provider_diverse_model_review_required: Literal[True] = True
    independent_human_review_proven: Literal[False] = False
    original_independent_review_gate_passed: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("G4 exception timestamp requires UTC")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.owner_signer_id:
            raise ValueError("G4 exception requires an accountable owner")
        return self


class SignedG4OneHumanFormalReviewException(Contract):
    exception: G4OneHumanFormalReviewException
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_one_human_formal_review_exception(
    exception: G4OneHumanFormalReviewException,
    key: Ed25519PrivateKey,
) -> SignedG4OneHumanFormalReviewException:
    return SignedG4OneHumanFormalReviewException(
        exception=exception,
        signature=G4ArtifactSignature(
            signer_id=exception.owner_signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_EXCEPTION_DOMAIN + canonical_bytes(exception))
            ).decode("ascii"),
        ),
    )


def verify_one_human_formal_review_exception(
    signed: SignedG4OneHumanFormalReviewException,
    record: G4SingleOperatorReviewRecord,
    policy: G4ProvenanceTrustPolicy,
    *,
    amendment_document_sha256: Digest,
) -> None:
    """Check the exact review, scope, chronology, and enrolled owner signature.

    The caller must separately replay the final suites and private provider audits.
    """
    item = signed.exception
    creator = verify_provenance_signature(
        item, signed.signature, policy, "creator", _EXCEPTION_DOMAIN
    )
    review = record.decision.decision
    providers = {critic.result.critic.provider for critic in record.critics}
    if (
        policy.operator_mode != "single_operator"
        or creator.signer_id != item.owner_signer_id
        or record.authority.signature.signer_id != item.owner_signer_id
        or record.decision.signature.signer_id != item.owner_signer_id
        or record.authority.signature.public_key_sha256
        != signed.signature.public_key_sha256
        or record.decision.signature.public_key_sha256
        != signed.signature.public_key_sha256
        or item.integrated_revision != record.subject.source_revision
        or item.subject_sha256 != record.subject.subject_sha256
        or item.review_record_sha256 != record.record_sha256
        or item.amendment_document_sha256 != amendment_document_sha256
        or not record.single_operator_review_evidence_passed
        or record.independent_review_evidence_passed
        or record.independent_human_review_proven
        or record.acceptance_authorized
        or review.verdict.decision != "accept"
        or providers != {"anthropic", "openai"}
        or len(record.critics) != 2
        or any(critic.result.status != "completed" for critic in record.critics)
        or record.judge.provider != "openai"
        or not review.decided_at <= item.issued_at < policy.valid_until
        or item.issued_at < policy.valid_from
    ):
        raise ValueError("G4 one-human exception differs from exact accepted review")
