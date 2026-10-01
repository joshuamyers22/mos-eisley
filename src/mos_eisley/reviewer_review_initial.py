"""Replayable review subject for a signed real initial child and final suites."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from mos_eisley.core.models import Brief, Contract, Digest, canonical_bytes, digest
from mos_eisley.reviewer_final_suites import G4FinalWholeSuiteReceipt
from mos_eisley.reviewer_independent_review import (
    REVIEW_DIFF_BYTES,
    REVIEW_PLAN_BYTES,
    G4ReviewSubject,
)
from mos_eisley.reviewer_initial_final import (
    G4InitialFinalInputs,
    verify_initial_final_receipt,
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


class G4InitialReviewLineageRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_review_lineage_record"] = (
        "g4_initial_review_lineage_record"
    )
    signed_creator_sha256: Digest
    signed_child_dispatch_sha256: Digest
    production_child_receipt_sha256: Digest
    signed_integration_sha256: Digest
    policy_sha256: Digest
    integrated_binding_sha256: Digest
    candidate_receipt_sha256: Digest
    final_suite_receipt_sha256: Digest
    base_revision: SourceRevision
    source_revision: SourceRevision

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4MetadataReviewLineageRecord(G4InitialReviewLineageRecord):
    signed_metadata_record_sha256: Digest


@dataclass(frozen=True)
class _GitProvenanceView:
    base_revision: str
    source_revision: str


@dataclass(frozen=True)
class _GitRecordView:
    provenance: _GitProvenanceView


@dataclass(frozen=True)
class G4InitialReviewContext:
    policy: G4ProvenanceTrustPolicy
    creator_approval: SignedG4CreatorApproval
    git_provenance: _GitRecordView
    lineage: G4InitialReviewLineageRecord

    @property
    def record_sha256(self) -> str:
        return self.lineage.record_sha256


@dataclass(frozen=True)
class G4InitialReviewBundle:
    subject: G4ReviewSubject
    context: G4InitialReviewContext


def _verified_evidence_packet(
    final_receipt: G4FinalWholeSuiteReceipt,
    inputs: G4InitialFinalInputs,
    lineage: G4InitialReviewLineageRecord,
) -> str:
    """Expose replay-verified signed lineage to critics within Brief's bound."""
    chain = inputs.chain
    artifacts = (
        ("provenance_policy", chain.policy),
        ("signed_creator_approval", chain.creator),
        ("signed_reviewer_custody", chain.custody),
        ("signed_child_assignment", chain.assignment),
        ("signed_child_dispatch_approval", chain.dispatch.approval),
        ("signed_child_dispatch_receipt", chain.dispatch),
        ("signed_integration_record", chain.signed_integration),
        ("signed_candidate_approval", inputs.candidate.approval),
        ("signed_final_suite_approval", final_receipt.approval),
        *(
            (("signed_creator_metadata_record", chain.signed_metadata),)
            if chain.signed_metadata is not None
            else ()
        ),
    )
    lines = [
        "G4 initial-child qualification evidence, version 2.",
        "All artifacts below were checked against the exact current Git source, "
        "frozen reviewer package, child execution, and passing offline suites "
        "before this review subject was built. JSON is canonical; each digest "
        "identifies the complete adjacent artifact.",
        "Scope: this is a real initial-child path. Prior failed candidates, "
        "adjudication, and correction triage belong to the separate correction "
        "path and are not prerequisites for this initial-child claim. Critic and "
        "judge observations and the creator's review decision follow this "
        "subject; they cannot be evidence inside their own input.",
    ]
    for name, artifact in artifacts:
        payload = canonical_bytes(artifact)
        lines.append(f"[{name}] sha256={digest(payload)}")
        lines.append(payload.decode("utf-8"))
    summary = {
        "initial_lineage_sha256": lineage.record_sha256,
        "source_revision": lineage.source_revision,
        "integrated_binding_sha256": chain.binding.binding_record_sha256,
        "frozen_reviewer_package_sha256": chain.package.frozen_package_sha256,
        "frozen_creator_package_sha256": inputs.creator_package.frozen_package_sha256,
        "known_controls_validated": chain.controls.controls_validated,
        "known_good_expectation_satisfied": (
            chain.controls.known_good.role_expectation_satisfied
        ),
        "known_bad_expectation_satisfied": (
            chain.controls.known_bad.role_expectation_satisfied
        ),
        "candidate_receipt_sha256": inputs.candidate.receipt_sha256,
        "candidate_tests_passed": inputs.candidate.candidate_tests_passed,
        "final_suite_receipt_sha256": final_receipt.receipt_sha256,
        "creator_suite_passed": (
            final_receipt.creator_execution.role_expectation_satisfied
        ),
        "reviewer_suite_passed": (
            final_receipt.reviewer_execution.role_expectation_satisfied
        ),
        "final_suites_passed": final_receipt.final_suites_passed,
        "production_child_receipt_sha256": chain.production.receipt_sha256,
    }
    lines.append("[verified_outcomes_and_bindings]")
    lines.append(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    result = "\n".join(lines)
    if len(result) > 32_000:
        raise ValueError("verified initial review evidence exceeds brief bound")
    return result


def build_initial_review_subject(
    final_receipt: G4FinalWholeSuiteReceipt,
    inputs: G4InitialFinalInputs,
    approved_plan_path: Path,
) -> G4InitialReviewBundle:
    """Rebuild the exact approved plan, full Git diff and signed lineage."""
    verify_initial_final_receipt(final_receipt, inputs)
    if not final_receipt.final_suites_passed:
        raise ValueError("initial review requires two passing final suites")
    chain = inputs.chain
    root = chain.integrated_root.resolve(strict=True)
    plan_path = approved_plan_path.resolve(strict=True)
    if plan_path.is_relative_to(root) or plan_path.is_relative_to(
        chain.original_root.resolve(strict=True)
    ):
        raise ValueError("approved review plan must remain outside target Git")
    plan = read_bounded(approved_plan_path, REVIEW_PLAN_BYTES)
    creator = chain.creator
    if digest(plan) != creator.approval.approved_plan_sha256:
        raise ValueError("review plan differs from signed creator approval")
    base = chain.assignment.assignment.base_revision
    source = chain.signed_integration.record.integrated_revision
    if chain.signed_metadata is not None:
        source = chain.signed_metadata.record.revision
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
    lineage = G4InitialReviewLineageRecord(
        signed_creator_sha256=digest(canonical_bytes(chain.creator)),
        signed_child_dispatch_sha256=chain.dispatch.receipt_sha256,
        production_child_receipt_sha256=chain.production.receipt_sha256,
        signed_integration_sha256=digest(canonical_bytes(chain.signed_integration)),
        policy_sha256=chain.policy.policy_sha256,
        integrated_binding_sha256=chain.binding.binding_record_sha256,
        candidate_receipt_sha256=inputs.candidate.receipt_sha256,
        final_suite_receipt_sha256=final_receipt.receipt_sha256,
        base_revision=base,
        source_revision=source,
    )
    if chain.signed_metadata is not None:
        lineage = G4MetadataReviewLineageRecord.model_validate(
            lineage.model_dump()
            | {"signed_metadata_record_sha256": chain.signed_metadata.artifact_sha256}
        )
    constraints = _verified_evidence_packet(final_receipt, inputs, lineage)
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
    context = G4InitialReviewContext(
        policy=chain.policy,
        creator_approval=creator,
        git_provenance=_GitRecordView(_GitProvenanceView(base, source)),
        lineage=lineage,
    )
    return G4InitialReviewBundle(subject=subject, context=context)


def assess_initial_single_operator_review(
    final_receipt: G4FinalWholeSuiteReceipt,
    inputs: G4InitialFinalInputs,
    approved_plan_path: Path,
    authority: SignedG4SingleOperatorReviewAuthority,
    critics: tuple[G4SingleOperatorCriticObservation, ...],
    judge: G4SingleOperatorJudgeObservation,
    decision: SignedG4SingleOperatorReviewDecision,
) -> G4SingleOperatorReviewRecord:
    bundle = build_initial_review_subject(final_receipt, inputs, approved_plan_path)
    context = cast(AuthenticatedG4ProvenanceRecord, bundle.context)
    return assess_single_operator_review(
        bundle.subject, context, authority, critics, judge, decision
    )


def verify_initial_single_operator_review_record(
    record: G4SingleOperatorReviewRecord,
    final_receipt: G4FinalWholeSuiteReceipt,
    inputs: G4InitialFinalInputs,
    approved_plan_path: Path,
) -> None:
    replay = assess_initial_single_operator_review(
        final_receipt,
        inputs,
        approved_plan_path,
        record.authority,
        record.critics,
        record.judge,
        record.decision,
    )
    if replay != record:
        raise ValueError("initial review record differs from current evidence")
