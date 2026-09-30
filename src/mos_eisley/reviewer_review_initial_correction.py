"""Exact review subject and prospective one-human amendment for a connected run."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import field_validator

from mos_eisley.core.models import Brief, Contract, Digest, canonical_bytes, digest
from mos_eisley.review.citations import citation_bound_request
from mos_eisley.reviewer_final_suites import G4FinalWholeSuiteReceipt
from mos_eisley.reviewer_independent_review import (
    REVIEW_DIFF_BYTES,
    REVIEW_PLAN_BYTES,
    G4ReviewSubject,
)
from mos_eisley.reviewer_initial_correction_final import (
    G4InitialCorrectionFinalInputs,
    verify_initial_correction_final_receipt,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    SignedG4CreatorApproval,
    SourceRevision,
    _git,
    verify_provenance_signature,
)
from mos_eisley.reviewer_review_initial import (
    _GitProvenanceView,
    _GitRecordView,
)
from mos_eisley.reviewer_single_operator_review import (
    _AUTHORITY_DOMAIN,
    G4SingleOperatorCriticObservation,
    G4SingleOperatorJudgeObservation,
    G4SingleOperatorReviewRecord,
    SignedG4SingleOperatorReviewAuthority,
    SignedG4SingleOperatorReviewDecision,
    assess_single_operator_review,
)
from mos_eisley.run.files import read_bounded

_AMENDMENT_DOMAIN = b"mos-eisley/g4-connected-prospective-review-amendment/v1\x00"


class G4InitialCorrectionReviewLineage(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_correction_review_lineage"] = (
        "g4_initial_correction_review_lineage"
    )
    signed_creator_sha256: Digest
    initial_dispatch_sha256: Digest
    initial_production_sha256: Digest
    initial_integration_sha256: Digest
    first_failure_sha256: Digest
    reproduced_failure_sha256: Digest
    correction_admission_sha256: Digest
    correction_dispatch_sha256: Digest
    correction_production_sha256: Digest
    correction_integration_sha256: Digest
    candidate_receipt_sha256: Digest
    final_suite_receipt_sha256: Digest
    policy_sha256: Digest
    integrated_binding_sha256: Digest
    base_revision: SourceRevision
    source_revision: SourceRevision

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


@dataclass(frozen=True)
class G4InitialCorrectionReviewContext:
    policy: G4ProvenanceTrustPolicy
    creator_approval: SignedG4CreatorApproval
    git_provenance: _GitRecordView
    lineage: G4InitialCorrectionReviewLineage

    @property
    def record_sha256(self) -> str:
        return self.lineage.record_sha256


@dataclass(frozen=True)
class G4InitialCorrectionReviewBundle:
    subject: G4ReviewSubject
    context: G4InitialCorrectionReviewContext


def build_initial_correction_review_subject(
    final: G4FinalWholeSuiteReceipt,
    inputs: G4InitialCorrectionFinalInputs,
    approved_plan_path: Path,
    *,
    review_amendment_document_path: Path | None = None,
) -> G4InitialCorrectionReviewBundle:
    """Replay evidence before exposing its exact plan, diff and signed decisions."""
    verify_initial_correction_final_receipt(final, inputs)
    if not final.final_suites_passed:
        raise ValueError("connected review requires both passing final suites")
    correction = inputs.chain
    initial = correction.first_inputs
    root = correction.candidate_root.resolve(strict=True)
    plan_path = approved_plan_path.resolve(strict=True)
    if any(
        plan_path.is_relative_to(path.resolve(strict=True))
        for path in (root, initial.original_root, initial.integrated_root)
    ):
        raise ValueError("connected review plan must remain outside task Git")
    plan = read_bounded(plan_path, REVIEW_PLAN_BYTES)
    if digest(plan) != initial.creator.approval.approved_plan_sha256:
        raise ValueError("connected review plan differs from signed creator plan")
    base = initial.assignment.assignment.base_revision
    source = correction.signed_integration.record.integrated_revision
    patch = _git(
        initial.git_executable,
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
        spec, diff = plan.decode("utf-8"), patch.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("connected plan and full patch must be UTF-8") from None
    if not spec or not diff:
        raise ValueError("connected review requires nonempty plan and full patch")
    lineage = G4InitialCorrectionReviewLineage(
        signed_creator_sha256=initial.creator.artifact_sha256,
        initial_dispatch_sha256=initial.dispatch.receipt_sha256,
        initial_production_sha256=initial.production.receipt_sha256,
        initial_integration_sha256=digest(canonical_bytes(initial.signed_integration)),
        first_failure_sha256=correction.first.receipt_sha256,
        reproduced_failure_sha256=correction.reproduction.receipt_sha256,
        correction_admission_sha256=correction.admission.admission_sha256,
        correction_dispatch_sha256=digest(canonical_bytes(correction.dispatch)),
        correction_production_sha256=correction.production.receipt_sha256,
        correction_integration_sha256=digest(
            canonical_bytes(correction.signed_integration)
        ),
        candidate_receipt_sha256=inputs.candidate.receipt_sha256,
        final_suite_receipt_sha256=final.receipt_sha256,
        policy_sha256=initial.policy.policy_sha256,
        integrated_binding_sha256=correction.binding.binding_record_sha256,
        base_revision=base,
        source_revision=source,
    )
    # Include signed decisions in full; bulky dispatch/source and measured receipts
    # are represented by verified hashes and exact observations, not raw responses.
    artifacts: tuple[tuple[str, Contract], ...] = (
        ("provenance_policy", initial.policy),
        ("creator_approval", initial.creator),
        ("reviewer_custody", initial.custody),
        ("initial_assignment", initial.assignment),
        ("initial_integration", initial.signed_integration),
        ("correction_triage", correction.admission.triage),
        ("correction_cycle_authority", correction.admission.approval),
        ("correction_integration", correction.signed_integration),
        ("corrected_candidate_authority", inputs.candidate.approval),
        ("final_suite_authority", final.approval),
    )
    if review_amendment_document_path is not None:
        artifacts += (
            ("first_failed_candidate_authority", correction.first.approval),
            ("reproduced_failed_candidate_authority", correction.reproduction.approval),
        )
    lines = [
        "Connected initial-child-to-correction qualification evidence, version 1.",
        "The full signed chain, private claims, provider audits/spend, Git and "
        "frozen tests were replayed before constructing this subject. Signed "
        "decisions appear below in canonical JSON; larger execution records "
        "are identified by verified hashes and their measured observations. "
        "Test source and raw provider responses are excluded. This review's "
        "critic, judge and creator decisions occur later and are pending. "
        "Scope: this distinct task's connected run; no full G4 milestone, "
        "representative quality, G3 study, savings or independent human claim.",
    ]
    for name, artifact in artifacts:
        payload = canonical_bytes(artifact)
        lines.extend((f"[{name}] sha256={digest(payload)}", payload.decode()))
    if review_amendment_document_path is not None:
        amendment_document = read_bounded(
            review_amendment_document_path, REVIEW_PLAN_BYTES
        )
        try:
            document_text = amendment_document.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("review amendment document must be UTF-8") from None
        if not document_text:
            raise ValueError("review amendment document must be nonempty")
        lines.extend(
            (
                "[prospective_formal_review_document] sha256="
                + digest(amendment_document),
                document_text,
                "This document states the proposed exact review governance. "
                "The owner must sign the prospective amendment and exact new "
                "subject/roster after freezing and before critic calls. "
                "That signature and live grants are checked by the controller. "
                "This current review assesses the completed implementation and "
                "its prerequisite evidence; its own later verdict, the judge "
                "decision, quality applicability and creator acceptance are "
                "not asserted complete and are not prerequisites of themselves.",
            )
        )
    summary = {
        "lineage": lineage.model_dump(mode="json"),
        "controls_validated": initial.controls.controls_validated,
        "creator_package_sha256": inputs.creator_package.frozen_package_sha256,
        "reviewer_package_sha256": initial.package.frozen_package_sha256,
        "initial_failure": correction.first.execution.observation.model_dump(
            mode="json"
        ),
        "reproduced_failure": correction.reproduction.execution.observation.model_dump(
            mode="json"
        ),
        "corrected_candidate": inputs.candidate.execution.observation.model_dump(
            mode="json"
        ),
        "creator_final": final.creator_execution.observation.model_dump(mode="json"),
        "reviewer_final": final.reviewer_execution.observation.model_dump(mode="json"),
    }
    lines.extend(
        (
            "[verified_lineage_and_observations]",
            json.dumps(summary, sort_keys=True, separators=(",", ":")),
        )
    )
    constraints = "\n".join(lines)
    if len(constraints) > 32_000:
        raise ValueError("connected review evidence exceeds brief bound")
    subject = G4ReviewSubject(
        provenance_sha256=lineage.record_sha256,
        final_suite_receipt_sha256=final.receipt_sha256,
        base_revision=base,
        source_revision=source,
        final_suite_started_at=final.started_at,
        approved_plan_sha256=digest(plan),
        full_diff_sha256=digest(patch),
        brief=Brief(spec=spec, diff=diff, constraints=constraints),
    )
    return G4InitialCorrectionReviewBundle(
        subject,
        G4InitialCorrectionReviewContext(
            initial.policy,
            initial.creator,
            _GitRecordView(_GitProvenanceView(base, source)),
            lineage,
        ),
    )


class G4ConnectedProspectiveReviewAmendment(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_connected_prospective_review_amendment"] = (
        "g4_connected_prospective_review_amendment"
    )
    integrated_revision: SourceRevision
    subject_sha256: Digest
    review_authority_sha256: Digest
    policy_sha256: Digest
    amendment_document_sha256: Digest
    issued_at: datetime
    one_human_operator: Literal[True] = True
    single_operator_self_review_risk_accepted: Literal[True] = True
    provider_diverse_model_review_required: Literal[True] = True
    independent_human_review_proven: Literal[False] = False
    original_independent_review_gate_passed: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("prospective amendment requires UTC")
        return value


class SignedG4ConnectedProspectiveReviewAmendment(Contract):
    amendment: G4ConnectedProspectiveReviewAmendment
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_connected_review_amendment(
    body: G4ConnectedProspectiveReviewAmendment,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4ConnectedProspectiveReviewAmendment:
    return SignedG4ConnectedProspectiveReviewAmendment(
        amendment=body,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_AMENDMENT_DOMAIN + canonical_bytes(body))
            ).decode(),
        ),
    )


def verify_connected_review_amendment(
    signed: SignedG4ConnectedProspectiveReviewAmendment,
    authority: SignedG4SingleOperatorReviewAuthority,
    bundle: G4InitialCorrectionReviewBundle,
    amendment_document_sha256: Digest,
) -> None:
    """Verify exact prospective scope; callers replay bundle and later live audits."""
    policy, item, grant = bundle.context.policy, signed.amendment, authority.authority
    owner = verify_provenance_signature(
        item, signed.signature, policy, "creator", _AMENDMENT_DOMAIN
    )
    reviewer = verify_provenance_signature(
        grant, authority.signature, policy, "creator", _AUTHORITY_DOMAIN
    )
    requests = tuple(
        citation_bound_request(bundle.subject.brief, critic.persona)
        for critic in grant.critics
    )
    if (
        owner != reviewer
        or policy.operator_mode != "single_operator"
        or item.integrated_revision != bundle.subject.source_revision
        or item.subject_sha256 != bundle.subject.subject_sha256
        or item.review_authority_sha256 != authority.artifact_sha256
        or item.policy_sha256 != policy.policy_sha256
        or item.amendment_document_sha256 != amendment_document_sha256
        or grant.subject_sha256 != bundle.subject.subject_sha256
        or grant.provenance_policy_sha256 != policy.policy_sha256
        or grant.critic_request_sha256s
        != tuple(digest(canonical_bytes(request)) for request in requests)
        or any(
            len(canonical_bytes(request)) > grant.review_policy.max_request_bytes
            for request in requests
        )
        or tuple(critic.provider for critic in grant.critics) != ("anthropic", "openai")
        or grant.judge_provider != "openai"
        or grant.review_policy.min_critics != 2
        or grant.review_policy.min_providers != 2
        or not policy.valid_from
        <= grant.issued_at
        <= item.issued_at
        < grant.expires_at
        <= policy.valid_until
        or grant.issued_at < bundle.subject.final_suite_started_at
    ):
        raise ValueError("connected prospective amendment differs from exact review")


def assess_initial_correction_single_operator_review(
    final: G4FinalWholeSuiteReceipt,
    inputs: G4InitialCorrectionFinalInputs,
    approved_plan_path: Path,
    amendment_document_path: Path,
    amendment: SignedG4ConnectedProspectiveReviewAmendment,
    authority: SignedG4SingleOperatorReviewAuthority,
    critics: tuple[G4SingleOperatorCriticObservation, ...],
    judge: G4SingleOperatorJudgeObservation,
    decision: SignedG4SingleOperatorReviewDecision,
) -> G4SingleOperatorReviewRecord:
    """Replay the connected subject and amendment before content adjudication.

    Live provider audits and spend must additionally replay before formal gate
    completion. This record alone retains provider-operation and acceptance false.
    """
    bundle = build_initial_correction_review_subject(
        final,
        inputs,
        approved_plan_path,
        review_amendment_document_path=amendment_document_path,
    )
    document = read_bounded(amendment_document_path, REVIEW_PLAN_BYTES)
    verify_connected_review_amendment(amendment, authority, bundle, digest(document))
    if not critics or any(
        critic.observed_at < amendment.amendment.issued_at for critic in critics
    ):
        raise ValueError("connected review observations predate prospective amendment")
    context = cast(AuthenticatedG4ProvenanceRecord, bundle.context)
    return assess_single_operator_review(
        bundle.subject, context, authority, critics, judge, decision
    )


def verify_initial_correction_single_operator_review_record(
    record: G4SingleOperatorReviewRecord,
    final: G4FinalWholeSuiteReceipt,
    inputs: G4InitialCorrectionFinalInputs,
    approved_plan_path: Path,
    amendment_document_path: Path,
    amendment: SignedG4ConnectedProspectiveReviewAmendment,
) -> None:
    replay = assess_initial_correction_single_operator_review(
        final,
        inputs,
        approved_plan_path,
        amendment_document_path,
        amendment,
        record.authority,
        record.critics,
        record.judge,
        record.decision,
    )
    if replay != record:
        raise ValueError("connected review record differs from current evidence")
