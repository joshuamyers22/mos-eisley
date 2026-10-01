"""Creator approval of exact plan/test bytes after authenticated judge replay."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import field_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.review.pipeline import judge_verdict
from mos_eisley.reviewer_plan_test_judge import (
    PlanTestCriticAuditInput,
    SignedG4PlanTestJudgeLiveGrant,
    verified_plan_test_judge_request,
    verify_plan_test_judge_audit,
)
from mos_eisley.reviewer_plan_test_review import (
    G4PlanTestReviewPacket,
    SignedG4PlanTestReviewAuthority,
    verify_plan_test_authority,
)
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    verify_provenance_signature,
)
from mos_eisley.run.spend_ledger import SpendLedger

DOMAIN = b"mos-eisley/g4-creator-plan-test-approval/v1\x00"


class G4CreatorPlanTestApproval(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_creator_pre_delegation_plan_test_approval"] = (
        "g4_creator_pre_delegation_plan_test_approval"
    )
    approval_id: Identifier
    packet_sha256: Digest
    provenance_policy_sha256: Digest
    review_authority_sha256: Digest
    judge_grant_sha256: Digest
    judge_observation_sha256: Digest
    verdict_sha256: Digest
    retained_finding_ids: tuple[Digest, ...]
    issued_at: datetime
    human_reviewer: Literal["joshua-myers"] = "joshua-myers"
    sole_human_review_risk_accepted: Literal[True] = True
    retained_findings_acknowledged: Literal[True] = True
    plan_and_tests_approved: Literal[True] = True
    coding_delegation_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    spending_authorized: Literal[False] = False
    task_acceptance_authorized: Literal[False] = False

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("creator approval requires UTC")
        return value


class SignedG4CreatorPlanTestApproval(Contract):
    approval: G4CreatorPlanTestApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def prepare_creator_plan_test_approval(
    *,
    approval_id: str,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    judge: SignedG4PlanTestJudgeLiveGrant,
    critics: tuple[PlanTestCriticAuditInput, PlanTestCriticAuditInput],
    spend: SpendPolicy,
    ledger: SpendLedger,
    claims: Path,
    run: Path,
    issued: datetime,
) -> G4CreatorPlanTestApproval:
    verify_plan_test_authority(authority, packet, policy, now=issued)
    observation = verify_plan_test_judge_audit(
        judge,
        packet=packet,
        policy=policy,
        authority=authority,
        critics=critics,
        spend=spend,
        ledger=ledger,
        claims=claims,
        run=run,
    )
    request, _ = verified_plan_test_judge_request(
        packet=packet,
        policy=policy,
        authority=authority,
        ledger=ledger,
        critics=critics,
    )
    verdict = judge_verdict(request, observation.decision)
    if verdict.decision != "accept" or verdict.required_changes:
        raise ValueError("creator approval requires an accepted plan/test review")
    if not observation.observed_at <= issued:
        raise ValueError("creator approval predates judge observation")
    return G4CreatorPlanTestApproval(
        approval_id=approval_id,
        packet_sha256=packet.packet_sha256,
        provenance_policy_sha256=policy.policy_sha256,
        review_authority_sha256=authority.artifact_sha256,
        judge_grant_sha256=judge.artifact_sha256,
        judge_observation_sha256=observation.artifact_sha256,
        verdict_sha256=digest(canonical_bytes(verdict)),
        retained_finding_ids=tuple(item.finding_id for item in verdict.findings),
        issued_at=issued,
    )


def sign_creator_plan_test_approval(
    approval: G4CreatorPlanTestApproval,
    key: Ed25519PrivateKey,
) -> SignedG4CreatorPlanTestApproval:
    return SignedG4CreatorPlanTestApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id="joshua-myers",
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


def verify_creator_plan_test_approval(
    signed: SignedG4CreatorPlanTestApproval,
    *,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    judge: SignedG4PlanTestJudgeLiveGrant,
    critics: tuple[PlanTestCriticAuditInput, PlanTestCriticAuditInput],
    spend: SpendPolicy,
    ledger: SpendLedger,
    claims: Path,
    run: Path,
    now: datetime,
) -> None:
    signer = verify_provenance_signature(
        signed.approval, signed.signature, policy, "creator", DOMAIN
    )
    expected = prepare_creator_plan_test_approval(
        approval_id=signed.approval.approval_id,
        packet=packet,
        policy=policy,
        authority=authority,
        judge=judge,
        critics=critics,
        spend=spend,
        ledger=ledger,
        claims=claims,
        run=run,
        issued=signed.approval.issued_at,
    )
    if (
        signed.approval != expected
        or signer.signer_id != authority.signature.signer_id
        or signer.public_key_sha256 != authority.signature.public_key_sha256
        or not signed.approval.issued_at <= now < policy.valid_until
    ):
        raise ValueError("creator approval differs from exact reviewed packet or owner")
