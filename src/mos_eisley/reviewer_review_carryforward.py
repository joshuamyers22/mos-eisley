"""Replayable review subject for a signed carry-forward correction and final suites.

The compatibility view feeds existing one-signer critic and judge contracts. It is
constructed only after verifying the complete carry-forward chain and final receipt.
Its hash names this new lineage, rather than claiming a new historical E2 record.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from mos_eisley.core.models import Brief, Contract, Digest, canonical_bytes, digest
from mos_eisley.reviewer_final_suites import G4FinalWholeSuiteReceipt
from mos_eisley.reviewer_final_suites_carryforward import (
    G4CarryForwardFinalInputs,
    verify_carryforward_final_suite_receipt,
)
from mos_eisley.reviewer_independent_review import (
    REVIEW_DIFF_BYTES,
    REVIEW_PLAN_BYTES,
    G4ReviewSubject,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ProvenanceTrustPolicy,
    SignedG4CreatorApproval,
    SourceRevision,
    _git,
)
from mos_eisley.reviewer_single_operator_review import (
    G4SingleOperatorCriticObservation,
    G4SingleOperatorJudgeObservation,
    G4SingleOperatorReviewRecord,
    SignedG4SingleOperatorReviewAuthority,
    SignedG4SingleOperatorReviewDecision,
    assess_single_operator_review,
)
from mos_eisley.run.files import read_bounded


class G4CarryForwardReviewLineageRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_carryforward_review_lineage_record"] = (
        "g4_carryforward_review_lineage_record"
    )
    historical_provenance_sha256: Digest
    signed_integration_sha256: Digest
    renewed_policy_sha256: Digest
    integrated_binding_sha256: Digest
    candidate_receipt_sha256: Digest
    final_suite_receipt_sha256: Digest
    base_revision: SourceRevision
    source_revision: SourceRevision

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


@dataclass(frozen=True)
class _GitProvenanceView:
    base_revision: str
    source_revision: str


@dataclass(frozen=True)
class _GitRecordView:
    provenance: _GitProvenanceView


@dataclass(frozen=True)
class G4CarryForwardReviewContext:
    """Verified compatibility view for existing single-operator review code."""

    policy: G4ProvenanceTrustPolicy
    creator_approval: SignedG4CreatorApproval
    git_provenance: _GitRecordView
    lineage: G4CarryForwardReviewLineageRecord

    @property
    def record_sha256(self) -> str:
        return self.lineage.record_sha256


@dataclass(frozen=True)
class G4CarryForwardReviewBundle:
    subject: G4ReviewSubject
    context: G4CarryForwardReviewContext


def build_carryforward_review_subject(
    final_receipt: G4FinalWholeSuiteReceipt,
    inputs: G4CarryForwardFinalInputs,
    approved_plan_path: Path,
) -> G4CarryForwardReviewBundle:
    """Reconstruct the exact plan, complete diff and replayed post-suite lineage."""
    verify_carryforward_final_suite_receipt(final_receipt, inputs)
    if not final_receipt.final_suites_passed:
        raise ValueError("carry-forward review requires two passing final suites")
    chain = inputs.candidate_inputs
    root = chain.integrated_root.resolve(strict=True)
    plan_path = approved_plan_path.resolve(strict=True)
    if plan_path.is_relative_to(root) or plan_path.is_relative_to(
        chain.original_root.resolve(strict=True)
    ):
        raise ValueError("approved review plan must remain outside target Git")
    plan = read_bounded(approved_plan_path, REVIEW_PLAN_BYTES)
    creator = chain.historical_provenance.creator_approval
    if digest(plan) != creator.approval.approved_plan_sha256:
        raise ValueError("review plan differs from signed creator approval")
    original = chain.historical_provenance.git_provenance.provenance
    integrated = chain.signed_integration.record
    base = original.base_revision
    source = integrated.integrated_revision
    patch = _git(
        chain.git_executable,
        root,
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            base,
            source,
            "--",
        ],
        limit=REVIEW_DIFF_BYTES,
    )
    try:
        plan_text = plan.decode("utf-8")
        patch_text = patch.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("review plan and complete Git diff must be UTF-8") from None
    if not plan_text or not patch_text:
        raise ValueError("review needs a nonempty plan and complete Git diff")
    lineage = G4CarryForwardReviewLineageRecord(
        historical_provenance_sha256=chain.historical_provenance.record_sha256,
        signed_integration_sha256=digest(canonical_bytes(chain.signed_integration)),
        renewed_policy_sha256=chain.renewed_policy.policy_sha256,
        integrated_binding_sha256=chain.binding.binding_record_sha256,
        candidate_receipt_sha256=inputs.candidate.receipt_sha256,
        final_suite_receipt_sha256=final_receipt.receipt_sha256,
        base_revision=base,
        source_revision=source,
    )
    constraints = json.dumps(
        {
            "creator_package_sha256": inputs.creator_package.frozen_package_sha256,
            "final_suite_receipt_sha256": final_receipt.receipt_sha256,
            "reviewer_package_sha256": chain.package.frozen_package_sha256,
            "source_revision": source,
            "carryforward_lineage_sha256": lineage.record_sha256,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    subject = G4ReviewSubject(
        provenance_sha256=lineage.record_sha256,
        final_suite_receipt_sha256=final_receipt.receipt_sha256,
        base_revision=base,
        source_revision=source,
        final_suite_started_at=final_receipt.started_at,
        approved_plan_sha256=digest(plan),
        full_diff_sha256=digest(patch),
        brief=Brief(spec=plan_text, diff=patch_text, constraints=constraints),
    )
    context = G4CarryForwardReviewContext(
        policy=chain.renewed_policy,
        creator_approval=creator,
        git_provenance=_GitRecordView(_GitProvenanceView(base, source)),
        lineage=lineage,
    )
    return G4CarryForwardReviewBundle(subject=subject, context=context)


def assess_carryforward_single_operator_review(
    final_receipt: G4FinalWholeSuiteReceipt,
    inputs: G4CarryForwardFinalInputs,
    approved_plan_path: Path,
    authority: SignedG4SingleOperatorReviewAuthority,
    critics: tuple[G4SingleOperatorCriticObservation, ...],
    judge: G4SingleOperatorJudgeObservation,
    decision: SignedG4SingleOperatorReviewDecision,
) -> G4SingleOperatorReviewRecord:
    """Adjudicate only after rebuilding the exact current carry-forward subject."""
    bundle = build_carryforward_review_subject(
        final_receipt, inputs, approved_plan_path
    )
    # The existing assessor reads only the immutable policy, creator approval,
    # base/source identities and record hash exposed by this verified view.
    context = cast(AuthenticatedG4ProvenanceRecord, bundle.context)
    return assess_single_operator_review(
        bundle.subject, context, authority, critics, judge, decision
    )


def verify_carryforward_single_operator_review_record(
    record: G4SingleOperatorReviewRecord,
    final_receipt: G4FinalWholeSuiteReceipt,
    inputs: G4CarryForwardFinalInputs,
    approved_plan_path: Path,
) -> None:
    replay = assess_carryforward_single_operator_review(
        final_receipt,
        inputs,
        approved_plan_path,
        record.authority,
        record.critics,
        record.judge,
        record.decision,
    )
    if replay != record:
        raise ValueError("carry-forward review record differs from current evidence")
