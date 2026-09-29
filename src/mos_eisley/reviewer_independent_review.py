"""Offline, authenticated G4 implementation-review evidence gate.

No provider, signing-key, write, or release capability is exposed here. Signatures
are supplied by separately enrolled external actors after reviewing the subject.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
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

from mos_eisley.core.models import (
    Brief,
    Contract,
    CriticRequest,
    CriticResult,
    CriticSpec,
    Digest,
    Identifier,
    JudgeDecision,
    JudgeRequest,
    ReviewPolicy,
    Verdict,
    canonical_bytes,
    digest,
)
from mos_eisley.review.citations import citation_bound_request, validate_evidence
from mos_eisley.review.pipeline import critic_quorum_met, judge_findings, judge_verdict
from mos_eisley.reviewer_candidate_execution import G4CandidateDispatchReceipt
from mos_eisley.reviewer_final_suites import (
    G4FinalWholeSuiteReceipt,
    verify_final_whole_suite_receipt,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    G4ProvenanceSigner,
    SourceRevision,
    _decode_base64,
    _git,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import KnownControlValidationRecord
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.files import read_bounded

REVIEW_RECORD_BYTES = 2_000_000
REVIEW_PLAN_BYTES = 128_000
REVIEW_DIFF_BYTES = 256_000
_AUTHORITY_DOMAIN = b"mos-eisley/g4-independent-review-authority/v1\x00"
_CRITIC_DOMAIN = b"mos-eisley/g4-independent-critic/v1\x00"
_JUDGE_DOMAIN = b"mos-eisley/g4-independent-judge/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("G4 review timestamps require explicit UTC")
    return value


class G4ReviewSubject(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_implementation_review_subject"] = (
        "g4_implementation_review_subject"
    )
    provenance_sha256: Digest
    final_suite_receipt_sha256: Digest
    base_revision: SourceRevision
    source_revision: SourceRevision
    final_suite_started_at: datetime
    approved_plan_sha256: Digest
    full_diff_sha256: Digest
    brief: Brief
    final_suites_passed: Literal[True] = True

    @field_validator("final_suite_started_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @property
    def subject_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4ReviewCriticAuthority(Contract):
    critic: CriticSpec
    signer: G4ProvenanceSigner


class G4IndependentReviewAuthority(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_independent_review_authority"] = "g4_independent_review_authority"
    authority_id: Identifier
    provenance_policy_sha256: Digest
    subject_sha256: Digest
    review_policy: ReviewPolicy
    critics: Annotated[
        tuple[G4ReviewCriticAuthority, ...], Field(min_length=2, max_length=8)
    ]
    judge: G4ProvenanceSigner
    issued_at: datetime
    expires_at: datetime
    provider_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("G4 review authority window is invalid")
        ids = tuple(item.critic.id for item in self.critics)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("G4 review critics must have unique sorted IDs")
        if self.review_policy.min_critics < 2 or self.review_policy.min_providers < 2:
            raise ValueError(
                "G4 review requires two critics from two provider families"
            )
        if (
            len({item.critic.provider for item in self.critics})
            < self.review_policy.min_providers
        ):
            raise ValueError("G4 review roster cannot satisfy provider quorum")
        if len(self.critics) < self.review_policy.min_critics:
            raise ValueError("G4 review roster cannot satisfy critic quorum")
        return self


class SignedG4IndependentReviewAuthority(Contract):
    authority: G4IndependentReviewAuthority
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4CriticAssessment(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_critic_assessment"] = "g4_critic_assessment"
    authority_sha256: Digest
    subject_sha256: Digest
    result: CriticResult
    assessed_at: datetime
    full_subject_review_claimed: bool
    acceptance_authorized: Literal[False] = False

    @field_validator("assessed_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def honest_status(self) -> Self:
        if self.full_subject_review_claimed != (self.result.status == "completed"):
            raise ValueError("G4 critic review claim differs from completion status")
        return self


class SignedG4CriticAssessment(Contract):
    assessment: G4CriticAssessment
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4JudgeAssessment(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_judge_assessment"] = "g4_judge_assessment"
    authority_sha256: Digest
    subject_sha256: Digest
    critic_artifact_sha256s: Annotated[
        tuple[Digest, ...], Field(min_length=2, max_length=8)
    ]
    decision: JudgeDecision
    assessed_at: datetime
    acceptance_authorized: Literal[False] = False

    @field_validator("assessed_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)


class SignedG4JudgeAssessment(Contract):
    assessment: G4JudgeAssessment
    signature: G4ArtifactSignature


class G4IndependentReviewRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_independent_review_record"] = "g4_independent_review_record"
    subject: G4ReviewSubject
    authority: SignedG4IndependentReviewAuthority
    critics: Annotated[
        tuple[SignedG4CriticAssessment, ...], Field(min_length=2, max_length=8)
    ]
    judge: SignedG4JudgeAssessment
    verdict: Verdict
    independent_review_evidence_passed: bool
    independent_human_review_proven: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            self.authority.authority.subject_sha256 != self.subject.subject_sha256
            or self.verdict.brief_id != self.subject.brief.brief_id
            or self.independent_review_evidence_passed
            != (self.verdict.decision == "accept")
            or len(canonical_bytes(self)) > REVIEW_RECORD_BYTES
        ):
            raise ValueError("G4 review record has inconsistent subject or verdict")
        return self

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _signature(
    value: Contract, signer_id: str, key: Ed25519PrivateKey, domain: bytes
) -> G4ArtifactSignature:
    return G4ArtifactSignature(
        signer_id=signer_id,
        public_key_sha256=digest(key.public_key().public_bytes_raw()),
        signature_base64=base64.b64encode(
            key.sign(domain + canonical_bytes(value))
        ).decode("ascii"),
    )


def sign_review_authority(
    authority: G4IndependentReviewAuthority, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4IndependentReviewAuthority:
    """External creator-custody primitive; verification CLI accepts no key."""
    return SignedG4IndependentReviewAuthority(
        authority=authority,
        signature=_signature(authority, signer_id, key, _AUTHORITY_DOMAIN),
    )


def sign_critic_assessment(
    assessment: G4CriticAssessment, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4CriticAssessment:
    return SignedG4CriticAssessment(
        assessment=assessment,
        signature=_signature(assessment, signer_id, key, _CRITIC_DOMAIN),
    )


def sign_judge_assessment(
    assessment: G4JudgeAssessment, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4JudgeAssessment:
    return SignedG4JudgeAssessment(
        assessment=assessment,
        signature=_signature(assessment, signer_id, key, _JUDGE_DOMAIN),
    )


def _verify_external_signature(
    value: Contract,
    signature: G4ArtifactSignature,
    signer: G4ProvenanceSigner,
    domain: bytes,
) -> None:
    if (
        signature.signer_id != signer.signer_id
        or signature.public_key_sha256 != signer.public_key_sha256
    ):
        raise ValueError("G4 review signer is not enrolled for this role")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(signer.public_key_base64, 32, "review public key")
        ).verify(
            _decode_base64(signature.signature_base64, 64, "review signature"),
            domain + canonical_bytes(value),
        )
    except InvalidSignature:
        raise ValueError("G4 review signature is invalid") from None


def build_review_subject(
    *,
    final_receipt: G4FinalWholeSuiteReceipt,
    candidate: G4CandidateDispatchReceipt,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    reviewer_binding: ImmutableImplementationBindingRecord,
    creator_package: FrozenReviewerTestPackage,
    reviewer_package: FrozenReviewerTestPackage,
    creator_package_path: Path,
    reviewer_package_path: Path,
    approved_plan_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    candidate_dispatch_store: Path,
    final_dispatch_store: Path,
) -> G4ReviewSubject:
    """Reconstruct the only admissible review subject from current exact inputs."""
    verify_final_whole_suite_receipt(
        final_receipt,
        candidate=candidate,
        provenance=provenance,
        controls=controls,
        reviewer_binding=reviewer_binding,
        creator_package=creator_package,
        reviewer_package=reviewer_package,
        creator_package_path=creator_package_path,
        reviewer_package_path=reviewer_package_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        candidate_dispatch_store=candidate_dispatch_store,
        final_dispatch_store=final_dispatch_store,
    )
    if not final_receipt.final_suites_passed:
        raise ValueError("G4 independent review requires both passing final suites")
    root = repository_root.resolve()
    plan_path = approved_plan_path.resolve()
    if plan_path.is_relative_to(root):
        raise ValueError("approved review plan must remain outside Git")
    plan = read_bounded(approved_plan_path, REVIEW_PLAN_BYTES)
    approval = provenance.creator_approval.approval
    if digest(plan) != approval.approved_plan_sha256:
        raise ValueError("G4 review plan differs from the creator-approved bytes")
    git_record = provenance.git_provenance.provenance
    patch = _git(
        git_executable,
        root,
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            git_record.base_revision,
            git_record.source_revision,
            "--",
        ],
        limit=REVIEW_DIFF_BYTES,
    )
    try:
        plan_text = plan.decode("utf-8")
        patch_text = patch.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("G4 review plan and full diff must be UTF-8") from None
    if not plan_text or not patch_text:
        raise ValueError("G4 review needs a nonempty plan and full Git diff")
    constraints = json.dumps(
        {
            "creator_package_sha256": creator_package.frozen_package_sha256,
            "final_suite_receipt_sha256": final_receipt.receipt_sha256,
            "reviewer_package_sha256": reviewer_package.frozen_package_sha256,
            "source_revision": git_record.source_revision,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return G4ReviewSubject(
        provenance_sha256=provenance.record_sha256,
        final_suite_receipt_sha256=final_receipt.receipt_sha256,
        base_revision=git_record.base_revision,
        source_revision=git_record.source_revision,
        final_suite_started_at=final_receipt.started_at,
        approved_plan_sha256=digest(plan),
        full_diff_sha256=digest(patch),
        brief=Brief(spec=plan_text, diff=patch_text, constraints=constraints),
    )


def assess_independent_review(
    subject: G4ReviewSubject,
    provenance: AuthenticatedG4ProvenanceRecord,
    authority: SignedG4IndependentReviewAuthority,
    critics: tuple[SignedG4CriticAssessment, ...],
    judge: SignedG4JudgeAssessment,
) -> G4IndependentReviewRecord:
    """Verify signatures, exact roles, citations, quorum and deterministic verdict."""
    grant = authority.authority
    verify_provenance_signature(
        grant, authority.signature, provenance.policy, "creator", _AUTHORITY_DOMAIN
    )
    if (
        grant.provenance_policy_sha256 != provenance.policy.policy_sha256
        or grant.subject_sha256 != subject.subject_sha256
        or subject.provenance_sha256 != provenance.record_sha256
        or subject.base_revision != provenance.git_provenance.provenance.base_revision
        or subject.source_revision
        != provenance.git_provenance.provenance.source_revision
        or subject.approved_plan_sha256
        != provenance.creator_approval.approval.approved_plan_sha256
        or not provenance.policy.valid_from
        <= grant.issued_at
        < grant.expires_at
        <= provenance.policy.valid_until
        or grant.issued_at < provenance.creator_approval.approval.issued_at
        or grant.issued_at < subject.final_suite_started_at
        or len(critics) != len(grant.critics)
    ):
        raise ValueError("G4 review authority differs from current lineage or roster")
    excluded = (
        provenance.policy.creators
        + provenance.policy.reviewers
        + provenance.policy.vcs_brokers
        + provenance.policy.children
    )
    all_signers = tuple(item.signer for item in grant.critics) + (grant.judge,)
    ids = tuple(item.signer_id for item in all_signers)
    keys = tuple(item.public_key_sha256 for item in all_signers)
    if (
        len(ids) != len(set(ids))
        or len(keys) != len(set(keys))
        or any(
            item.signer_id in ids or item.public_key_sha256 in keys for item in excluded
        )
    ):
        raise ValueError(
            "G4 review signers must differ from each other and implementation roles"
        )
    if any(
        len(canonical_bytes(citation_bound_request(subject.brief, item.critic.persona)))
        > grant.review_policy.max_request_bytes
        for item in grant.critics
    ):
        raise ValueError("G4 review request exceeds its approved byte budget")
    results: list[CriticResult] = []
    request_cache: dict[str, CriticRequest] = {}
    for signed, enrolled in zip(critics, grant.critics, strict=True):
        item = signed.assessment
        _verify_external_signature(
            item, signed.signature, enrolled.signer, _CRITIC_DOMAIN
        )
        if (
            item.authority_sha256 != authority.artifact_sha256
            or item.subject_sha256 != subject.subject_sha256
            or item.result.critic != enrolled.critic
            or not grant.issued_at <= item.assessed_at < grant.expires_at
        ):
            raise ValueError("G4 critic assessment differs from its exact authority")
        if item.result.status == "completed":
            assert item.result.critique is not None
            request = request_cache.setdefault(
                enrolled.critic.persona,
                citation_bound_request(subject.brief, enrolled.critic.persona),
            )
            validate_evidence(request, item.result.critique.findings)
        results.append(item.result)
    if not critic_quorum_met(tuple(results), grant.review_policy):
        raise ValueError("G4 independent critic quorum was not met")
    judge_request = JudgeRequest(
        brief=subject.brief, findings=judge_findings(tuple(results))
    )
    if len(canonical_bytes(judge_request)) > grant.review_policy.max_request_bytes:
        raise ValueError("G4 judge request exceeds its approved byte budget")
    decision = judge.assessment
    _verify_external_signature(decision, judge.signature, grant.judge, _JUDGE_DOMAIN)
    if (
        decision.authority_sha256 != authority.artifact_sha256
        or decision.subject_sha256 != subject.subject_sha256
        or decision.critic_artifact_sha256s
        != tuple(item.artifact_sha256 for item in critics)
        or not max(item.assessment.assessed_at for item in critics)
        <= decision.assessed_at
        < grant.expires_at
    ):
        raise ValueError("G4 judge assessment differs from the exact critic evidence")
    verdict = judge_verdict(judge_request, decision.decision)
    return G4IndependentReviewRecord(
        subject=subject,
        authority=authority,
        critics=critics,
        judge=judge,
        verdict=verdict,
        independent_review_evidence_passed=verdict.decision == "accept",
    )


def verify_independent_review_record(
    record: G4IndependentReviewRecord,
    *,
    final_receipt: G4FinalWholeSuiteReceipt,
    candidate: G4CandidateDispatchReceipt,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    reviewer_binding: ImmutableImplementationBindingRecord,
    creator_package: FrozenReviewerTestPackage,
    reviewer_package: FrozenReviewerTestPackage,
    creator_package_path: Path,
    reviewer_package_path: Path,
    approved_plan_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    candidate_dispatch_store: Path,
    final_dispatch_store: Path,
) -> None:
    subject = build_review_subject(
        final_receipt=final_receipt,
        candidate=candidate,
        provenance=provenance,
        controls=controls,
        reviewer_binding=reviewer_binding,
        creator_package=creator_package,
        reviewer_package=reviewer_package,
        creator_package_path=creator_package_path,
        reviewer_package_path=reviewer_package_path,
        approved_plan_path=approved_plan_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        candidate_dispatch_store=candidate_dispatch_store,
        final_dispatch_store=final_dispatch_store,
    )
    if record.subject != subject or record != assess_independent_review(
        subject, provenance, record.authority, record.critics, record.judge
    ):
        raise ValueError("G4 independent review record differs from current evidence")


def decode_review_artifact[T: Contract](payload: bytes, model: type[T]) -> T:
    if len(payload) > REVIEW_RECORD_BYTES:
        raise ValueError("G4 review artifact exceeds 2 MB")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        value = model.model_validate_json(payload)
        if canonical_bytes(value) != payload:
            raise ValueError("G4 review artifact must be canonical")
        return value
    except (ValueError, RecursionError):
        raise ValueError("invalid G4 review artifact") from None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result
