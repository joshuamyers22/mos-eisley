"""Exact pre-delegation plan/test packets and non-dispatch owner authority."""

from __future__ import annotations

import base64
import difflib
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import (
    Brief,
    Contract,
    CriticRequest,
    CriticSpec,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.review.citations import citation_bound_request
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    SourceRevision,
    verify_provenance_signature,
)

AUTHORITY_DOMAIN = b"mos-eisley/g4-plan-test-review-authority/v1\x00"


class CreatorTestSource(Contract):
    path: Annotated[str, Field(pattern=r"^tests/test_[a-z0-9_]+\.py$")]
    content: Annotated[str, Field(min_length=1, max_length=64_000)]


class G4PlanTestReviewPacket(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_pre_delegation_plan_test_packet"] = (
        "g4_pre_delegation_plan_test_packet"
    )
    task_id: Identifier
    base_revision: SourceRevision
    plan: Annotated[str, Field(min_length=1, max_length=64_000)]
    creator_tests: Annotated[
        tuple[CreatorTestSource, ...], Field(min_length=1, max_length=8)
    ]
    coding_delegation_occurred: Literal[False] = False

    @model_validator(mode="after")
    def unique_ordered_tests(self) -> Self:
        paths = tuple(item.path for item in self.creator_tests)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("creator test paths must be unique and ordered")
        return self

    @property
    def packet_sha256(self) -> str:
        return digest(canonical_bytes(self))


def plan_test_brief(packet: G4PlanTestReviewPacket) -> Brief:
    """Present every creator-test byte as an addition, without implementation."""
    diff = "".join(
        "".join(
            difflib.unified_diff(
                [],
                item.content.splitlines(keepends=True),
                fromfile="/dev/null",
                tofile=f"b/{item.path}",
            )
        )
        for item in packet.creator_tests
    )
    return Brief(
        spec=packet.plan,
        diff=diff,
        constraints=(
            "Review stage: creator plan and executable tests BEFORE coding delegation. "
            "The diff presents exact creator-test source as new-file additions; "
            "it is not an implementation patch. Assess the stated contract, test "
            "correctness, coverage, contradictory expectations and bounded task scope. "
            "No child implementation exists beyond a deliberately unimplemented stub. "
            "Do not demand passing implementation tests before coding. Report actual "
            "defects or requirement gaps, retaining exact citation evidence. "
            "This review is separate from final implementation review and acceptance."
        ),
    )


class G4PlanTestReviewAuthority(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_pre_delegation_plan_test_review_authority"] = (
        "g4_pre_delegation_plan_test_review_authority"
    )
    authority_id: Identifier
    provenance_policy_sha256: Digest
    packet_sha256: Digest
    critics: Annotated[tuple[CriticSpec, ...], Field(min_length=2, max_length=2)]
    critic_request_sha256s: tuple[Digest, Digest]
    judge_provider: Literal["openai"] = "openai"
    judge_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    proposed_review_ceiling_microusd: Literal[250_000] = 250_000
    issued_at: datetime
    expires_at: datetime
    human_reviewer: Literal["joshua-myers"] = "joshua-myers"
    sole_human_review_risk_accepted: Literal[True] = True
    plan_and_tests_approved: Literal[False] = False
    coding_delegation_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    spending_authorized: Literal[False] = False
    task_acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("plan/test review times require explicit UTC")
        return value

    @model_validator(mode="after")
    def roster_and_window(self) -> Self:
        if tuple((item.id, item.provider, item.model) for item in self.critics) != (
            ("anthropic-critic", "anthropic", "claude-sonnet-5"),
            ("openai-critic", "openai", "gpt-5.6-luna"),
        ) or not self.issued_at < self.expires_at <= self.issued_at + timedelta(
            hours=24
        ):
            raise ValueError("plan/test roster or authority window is invalid")
        return self


class SignedG4PlanTestReviewAuthority(Contract):
    authority: G4PlanTestReviewAuthority
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def plan_test_requests(
    packet: G4PlanTestReviewPacket, critics: tuple[CriticSpec, ...]
) -> tuple[CriticRequest, ...]:
    brief = plan_test_brief(packet)
    return tuple(citation_bound_request(brief, spec.persona) for spec in critics)


def sign_plan_test_authority(
    authority: G4PlanTestReviewAuthority, key: Ed25519PrivateKey
) -> SignedG4PlanTestReviewAuthority:
    return SignedG4PlanTestReviewAuthority(
        authority=authority,
        signature=G4ArtifactSignature(
            signer_id="joshua-myers",
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(AUTHORITY_DOMAIN + canonical_bytes(authority))
            ).decode("ascii"),
        ),
    )


def verify_plan_test_authority(
    signed: SignedG4PlanTestReviewAuthority,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    *,
    now: datetime,
) -> None:
    authority = signed.authority
    signer = verify_provenance_signature(
        authority, signed.signature, policy, "creator", AUTHORITY_DOMAIN
    )
    requests = plan_test_requests(packet, authority.critics)
    if (
        signer.signer_id != authority.human_reviewer
        or policy.operator_mode != "single_operator"
        or authority.provenance_policy_sha256 != policy.policy_sha256
        or authority.packet_sha256 != packet.packet_sha256
        or authority.critic_request_sha256s
        != tuple(digest(canonical_bytes(item)) for item in requests)
        or not policy.valid_from
        <= authority.issued_at
        <= now
        < authority.expires_at
        <= policy.valid_until
        or any(len(canonical_bytes(item)) > 512_000 for item in requests)
    ):
        raise ValueError("plan/test authority differs from exact frozen evidence")
