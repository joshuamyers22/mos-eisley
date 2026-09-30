"""One-use contained correction dispatch for a signed initial-child task."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import os
import stat
import time
from datetime import UTC, datetime
from pathlib import Path

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_correction import G4CorrectionReviewPolicy
from mos_eisley.reviewer_correction_dispatch import (
    _DOMAIN,
    _PROPOSAL_DOMAIN,
    MAX_JOB_BYTES,
    CorrectionChildGenerator,
    G4CorrectionChildDispatchReceipt,
    G4CorrectionChildExecution,
    G4CorrectionChildJob,
    G4CorrectionChildOffer,
    SignedG4CorrectionChildDispatchApproval,
    _read_repository_file,
    _source_file,
    _utc,
    creator_test_bundle_sha256,
    validate_correction_child_job,
)
from mos_eisley.reviewer_implementation_binding import snapshot_implementation_files
from mos_eisley.reviewer_initial_candidate import (
    G4InitialCandidateInputs,
    G4InitialCandidateReceipt,
)
from mos_eisley.reviewer_initial_correction import (
    G4InitialCorrectionCycleAdmission,
    verify_initial_correction_cycle_admission,
)
from mos_eisley.reviewer_provenance import verify_provenance_signature
from mos_eisley.run.isolation import OfflineContainer


def _claim_name(admission: G4InitialCorrectionCycleAdmission) -> str:
    grant = admission.approval.approval
    return (
        f"{digest(f'{grant.task_id}\x00{grant.cycle}'.encode())}.correction-child-claim"
    )


def _claim(
    store: Path,
    approval: SignedG4CorrectionChildDispatchApproval,
    admission: G4InitialCorrectionCycleAdmission,
) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _claim_name(admission),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(approval))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_claim(
    store: Path,
    approval: SignedG4CorrectionChildDispatchApproval,
    admission: G4InitialCorrectionCycleAdmission,
) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _claim_name(admission), os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd
        )
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise ValueError("initial correction child claim is not private")
            actual = stream.read(MAX_JOB_BYTES + 1)
        if actual != canonical_bytes(approval):
            raise ValueError("initial correction child claim differs from approval")
    finally:
        os.close(fd)


def preview_initial_correction_child_offer(
    *,
    admission: G4InitialCorrectionCycleAdmission,
    approval: SignedG4CorrectionChildDispatchApproval,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    child_dispatch_store: Path,
    approved_plan: str,
    brief: str,
    acceptance_criteria: str,
    container: OfflineContainer,
    now: datetime | None = None,
) -> G4CorrectionChildOffer:
    """Replay the initial chain and freeze exact source/test bytes without a claim."""
    current = _utc(now if now is not None else datetime.now(UTC))
    root = first_inputs.original_root.resolve()
    integrated = first_inputs.integrated_root.resolve()
    for path in (
        first_inputs.package_path,
        correction_store,
        child_dispatch_store,
        container.lifecycle_root,
    ):
        resolved = path.resolve()
        if resolved.is_relative_to(root) or resolved.is_relative_to(integrated):
            raise ValueError("initial correction child state must remain outside Git")
    fd = open_private_dispatch_store(child_dispatch_store)
    os.close(fd)
    verify_initial_correction_cycle_admission(
        admission,
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        review_policy=review_policy,
        correction_store=correction_store,
    )
    grant = admission.approval.approval
    order = approval.approval
    assignment = first_inputs.assignment.assignment
    if (
        order.admission_sha256 != admission.admission_sha256
        or order.source_revision != admission.source_revision
        or order.source_revision != grant.source_revision
        or order.child_signer_id != grant.child_signer_id
        or approved_plan != first_inputs.approved_plan
        or digest(approved_plan.encode("utf-8")) != grant.approved_plan_sha256
        or not set(order.owned_paths) <= set(grant.owned_paths)
        or set(order.owned_paths) & set(assignment.creator_test_paths)
        or order.brief_sha256 != digest(brief.encode("utf-8"))
        or order.acceptance_criteria_sha256
        != digest(acceptance_criteria.encode("utf-8"))
        or order.creator_test_suite_sha256 != grant.creator_test_suite_sha256
        or container.image_id != order.container_image_id
        or order.container_image_id != first.request.container_image_id
        or order.container_image_id != reproduction.request.container_image_id
        or not admission.admitted_at <= order.issued_at <= current < order.expires_at
        or order.expires_at > grant.expires_at
        or current >= grant.task_budget.deadline
    ):
        raise ValueError("initial correction child dispatch differs from cycle")
    verify_provenance_signature(
        order, approval.signature, first_inputs.policy, "creator", _DOMAIN
    )
    sources = snapshot_implementation_files(
        first_inputs.binding.payload.manifest, integrated
    )
    if not set(order.owned_paths) <= set(sources):
        raise ValueError("initial correction child paths must be bound source files")
    if len(assignment.creator_test_paths) > 64:
        raise ValueError("initial correction child creator-test view exceeds limit")
    creator_tests = tuple(
        _source_file(path, _read_repository_file(integrated, path))
        for path in assignment.creator_test_paths
    )
    if creator_test_bundle_sha256(creator_tests) != order.creator_test_bundle_sha256:
        raise ValueError("initial correction creator tests differ from signed order")
    return G4CorrectionChildOffer(
        dispatch_approval_sha256=approval.artifact_sha256,
        correction_admission_sha256=admission.admission_sha256,
        source_revision=order.source_revision,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        source_files=tuple(
            _source_file(path, sources[path]) for path in order.owned_paths
        ),
        creator_test_files=creator_tests,
        max_input_tokens=grant.max_input_tokens,
        max_output_tokens=grant.max_output_tokens,
        max_tool_calls=grant.max_tool_calls,
        max_seconds=grant.max_seconds,
        max_microusd=grant.max_microusd,
    )


async def dispatch_initial_correction_child(
    *,
    admission: G4InitialCorrectionCycleAdmission,
    approval: SignedG4CorrectionChildDispatchApproval,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    child_dispatch_store: Path,
    approved_plan: str,
    brief: str,
    acceptance_criteria: str,
    generator: CorrectionChildGenerator,
    container: OfflineContainer,
    now: datetime | None = None,
) -> G4CorrectionChildDispatchReceipt:
    """Spend one separately signed dispatch and validate one contained proposal."""
    current = _utc(now if now is not None else datetime.now(UTC))
    offer = preview_initial_correction_child_offer(
        admission=admission,
        approval=approval,
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        review_policy=review_policy,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        container=container,
        now=current,
    )
    grant = admission.approval.approval
    order = approval.approval
    _claim(child_dispatch_store, approval, admission)
    duration = min(
        float(grant.max_seconds),
        (order.expires_at - current).total_seconds(),
        (grant.task_budget.deadline - current).total_seconds(),
    )
    started = time.monotonic()
    async with asyncio.timeout(duration):
        signed_proposal = await generator.generate(offer)
    verify_provenance_signature(
        signed_proposal.proposal,
        signed_proposal.signature,
        first_inputs.policy,
        "child",
        _PROPOSAL_DOMAIN,
    )
    if signed_proposal.signature.signer_id != order.child_signer_id:
        raise ValueError("initial correction proposal came from another child")
    job = G4CorrectionChildJob(offer=offer, signed_proposal=signed_proposal)
    expected = validate_correction_child_job(job)
    remaining = duration - (time.monotonic() - started)
    if remaining <= 0:
        raise TimeoutError("initial correction child allowance elapsed")
    output = container.execute(
        ("-m", "mos_eisley.run.reviewer_correction_child"),
        canonical_bytes(job),
        timeout=min(remaining, 60.0),
    )
    if len(output) > 16_384:
        raise ValueError("contained initial correction result exceeds 16 KB")
    actual = G4CorrectionChildExecution.model_validate_json(output)
    if output != canonical_bytes(actual) or actual != expected:
        raise ValueError("contained initial correction result differs from host replay")
    verify_initial_correction_cycle_admission(
        admission,
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        review_policy=review_policy,
        correction_store=correction_store,
    )
    return G4CorrectionChildDispatchReceipt(
        approval=approval,
        correction_admission_sha256=admission.admission_sha256,
        offer=offer,
        signed_proposal=signed_proposal,
        execution=actual,
        dispatched_at=current,
    )


def verify_initial_correction_child_dispatch_receipt(
    receipt: G4CorrectionChildDispatchReceipt,
    *,
    admission: G4InitialCorrectionCycleAdmission,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    child_dispatch_store: Path,
    container: OfflineContainer,
) -> None:
    """Replay a stored dispatch against the current clean task and exact claim."""
    offer = preview_initial_correction_child_offer(
        admission=admission,
        approval=receipt.approval,
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        review_policy=review_policy,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
        approved_plan=receipt.offer.approved_plan,
        brief=receipt.offer.brief,
        acceptance_criteria=receipt.offer.acceptance_criteria,
        container=container,
        now=receipt.dispatched_at,
    )
    _verify_claim(child_dispatch_store, receipt.approval, admission)
    if (
        offer != receipt.offer
        or receipt.correction_admission_sha256 != admission.admission_sha256
    ):
        raise ValueError("initial correction receipt names another offer")
    verify_provenance_signature(
        receipt.signed_proposal.proposal,
        receipt.signed_proposal.signature,
        first_inputs.policy,
        "child",
        _PROPOSAL_DOMAIN,
    )
    if (
        receipt.signed_proposal.signature.signer_id
        != receipt.approval.approval.child_signer_id
    ):
        raise ValueError("initial correction receipt has another child signer")
    if (
        validate_correction_child_job(
            G4CorrectionChildJob(offer=offer, signed_proposal=receipt.signed_proposal)
        )
        != receipt.execution
    ):
        raise ValueError("initial correction receipt execution differs")
