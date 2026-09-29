"""Final offline suites for a signed integrated correction and carry-forward candidate.

This route reuses the final-suite receipt schema, but replays the distinct
carry-forward admission instead of treating it as a historical candidate.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mos_eisley.reviewer_candidate_carryforward import (
    G4CarryForwardCandidateInputs,
    G4CarryForwardCandidateReceipt,
    verify_carryforward_candidate_receipt,
)
from mos_eisley.reviewer_correction_dispatch import _read_repository_file
from mos_eisley.reviewer_final_suites import (
    _APPROVAL_DOMAIN,
    G4FinalWholeSuiteReceipt,
    SignedG4FinalWholeSuiteApproval,
    _claim,
    _verify_claim,
    _verify_creator_package,
    build_isolated_creator_test_job,
    execute_isolated_creator_tests_in_trusted_host,
    verify_creator_test_execution_receipt,
)
from mos_eisley.reviewer_provenance import _git, verify_provenance_signature
from mos_eisley.reviewer_test_execution import (
    ImmutableReviewerTestExecutionReceipt,
    ReviewerTestExecutionRequest,
    build_isolated_reviewer_test_job,
    execute_isolated_reviewer_tests_in_trusted_host,
    verify_execution_receipt,
)
from mos_eisley.reviewer_test_package import (
    FROZEN_PACKAGE_BYTES,
    FrozenReviewerTestPackage,
    decode_frozen_reviewer_test_package,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer


@dataclass(frozen=True)
class G4CarryForwardFinalInputs:
    candidate: G4CarryForwardCandidateReceipt
    candidate_inputs: G4CarryForwardCandidateInputs
    creator_package: FrozenReviewerTestPackage
    creator_package_path: Path
    creator_request: ReviewerTestExecutionRequest
    reviewer_request: ReviewerTestExecutionRequest
    final_store: Path


def _reviewer_identities(
    candidate: G4CarryForwardCandidateReceipt,
    execution: ImmutableReviewerTestExecutionReceipt,
) -> None:
    before = candidate.execution.observation
    after = execution.observation
    if (
        before.collected_test_ids_sha256 != after.collected_test_ids_sha256
        or before.started_test_ids_sha256 != after.started_test_ids_sha256
        or before.executed_test_ids_sha256 != after.executed_test_ids_sha256
    ):
        raise ValueError("final reviewer suite executed different test identities")


def preflight_carryforward_final_suites(
    approval: SignedG4FinalWholeSuiteApproval,
    inputs: G4CarryForwardFinalInputs,
    *,
    now: datetime | None = None,
) -> None:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ValueError("final-suite preflight requires explicit UTC")
    candidate = inputs.candidate
    chain = inputs.candidate_inputs
    root = chain.integrated_root.resolve(strict=True)
    for path in (
        inputs.creator_package_path,
        chain.package_path,
        inputs.final_store,
    ):
        if path.resolve().is_relative_to(root):
            raise ValueError("final-suite packages and claims must stay outside Git")
    final_store = inputs.final_store.resolve()
    candidate_store = chain.candidate_store.resolve()
    if (
        final_store == candidate_store
        or final_store.is_relative_to(candidate_store)
        or candidate_store.is_relative_to(final_store)
    ):
        raise ValueError("candidate and final-suite claims need separate stores")
    verify_carryforward_candidate_receipt(candidate, chain)
    if not candidate.candidate_tests_passed:
        raise ValueError("final suites require a passing carry-forward candidate")
    policy = chain.renewed_policy
    grant = approval.approval
    verify_provenance_signature(
        grant, approval.signature, policy, "creator", _APPROVAL_DOMAIN
    )
    if not (
        policy.valid_from
        <= grant.issued_at
        <= current
        < grant.expires_at
        <= policy.valid_until
        and grant.issued_at >= candidate.admission.admitted_at
    ):
        raise ValueError("final-suite authority is outside its policy/candidate window")
    integrated = chain.signed_integration.record
    creator_suite = (
        chain.historical_provenance.creator_approval.approval.creator_test_suite_sha256
    )
    if (
        not grant.suite_id.startswith("g4-q2-real-child-final-")
        or grant.policy_sha256 != policy.policy_sha256
        or grant.provenance_sha256 != chain.historical_provenance.record_sha256
        or grant.candidate_receipt_sha256 != candidate.receipt_sha256
        or grant.source_revision != integrated.integrated_revision
        or grant.creator_test_suite_sha256 != creator_suite
        or grant.creator_package_sha256 != inputs.creator_package.frozen_package_sha256
        or grant.reviewer_package_sha256 != chain.package.frozen_package_sha256
        or grant.reviewer_binding_sha256 != chain.binding.binding_record_sha256
        or grant.creator_request_sha256 != inputs.creator_request.request_sha256
        or grant.reviewer_request_sha256 != inputs.reviewer_request.request_sha256
        or grant.container_image_id != candidate.admission.request.container_image_id
        or inputs.creator_request.container_image_id != grant.container_image_id
        or inputs.reviewer_request.container_image_id != grant.container_image_id
        or inputs.creator_request.binding_record_sha256
        != chain.binding.binding_record_sha256
        or inputs.reviewer_request.binding_record_sha256
        != chain.binding.binding_record_sha256
        or inputs.creator_request.role != "candidate"
        or inputs.reviewer_request.role != "candidate"
        or inputs.creator_request.execution_id == inputs.reviewer_request.execution_id
    ):
        raise ValueError("final-suite approval differs from exact integrated inputs")
    if (
        decode_frozen_reviewer_test_package(
            read_bounded(inputs.creator_package_path, FROZEN_PACKAGE_BYTES)
        )
        != inputs.creator_package
    ):
        raise ValueError("protected creator package file changed")
    _verify_creator_package(
        inputs.creator_package,
        chain.historical_provenance,
        chain.original_root,
        chain.original_root,
        chain.git_executable,
    )
    for item in inputs.creator_package.payload.files:
        path = item.declaration.path
        content = item.content
        if (
            _read_repository_file(root, path) != content
            or _git(
                chain.git_executable,
                root,
                ["show", f"{grant.source_revision}:{path}"],
                limit=len(content),
            )
            != content
        ):
            raise ValueError("protected creator tests changed in integrated Git")
    build_isolated_creator_test_job(
        inputs.creator_request,
        chain.binding,
        inputs.creator_package_path,
        chain.package_path,
        root,
    )
    build_isolated_reviewer_test_job(
        inputs.reviewer_request, chain.binding, chain.package_path, root
    )


def run_carryforward_final_suites(
    approval: SignedG4FinalWholeSuiteApproval,
    inputs: G4CarryForwardFinalInputs,
    container: OfflineContainer,
    *,
    now: datetime | None = None,
) -> G4FinalWholeSuiteReceipt:
    started = now if now is not None else datetime.now(UTC)
    preflight_carryforward_final_suites(approval, inputs, now=started)
    if container.image_id != approval.approval.container_image_id:
        raise ValueError("final-suite container differs from approved image")
    if container.lifecycle_root.resolve().is_relative_to(
        inputs.candidate_inputs.integrated_root.resolve()
    ):
        raise ValueError("final-suite container state must stay outside Git")
    chain = inputs.candidate_inputs
    _claim(inputs.final_store, inputs.candidate.receipt_sha256, approval)
    creator = execute_isolated_creator_tests_in_trusted_host(
        inputs.creator_request,
        chain.binding,
        inputs.creator_package_path,
        chain.package_path,
        chain.integrated_root,
        container,
    )
    reviewer = execute_isolated_reviewer_tests_in_trusted_host(
        inputs.reviewer_request,
        chain.binding,
        chain.package_path,
        chain.integrated_root,
        container,
    )
    _reviewer_identities(inputs.candidate, reviewer)
    preflight_carryforward_final_suites(approval, inputs, now=started)
    return G4FinalWholeSuiteReceipt(
        approval=approval,
        candidate_receipt_sha256=inputs.candidate.receipt_sha256,
        source_revision=approval.approval.source_revision,
        creator_execution=creator,
        reviewer_execution=reviewer,
        started_at=started,
        final_suites_passed=(
            creator.role_expectation_satisfied and reviewer.role_expectation_satisfied
        ),
    )


def verify_carryforward_final_suite_receipt(
    receipt: G4FinalWholeSuiteReceipt,
    inputs: G4CarryForwardFinalInputs,
) -> None:
    if (
        receipt.creator_execution.request != inputs.creator_request
        or receipt.reviewer_execution.request != inputs.reviewer_request
    ):
        raise ValueError("final-suite receipt differs from frozen requests")
    preflight_carryforward_final_suites(
        receipt.approval, inputs, now=receipt.started_at
    )
    _verify_claim(inputs.final_store, inputs.candidate.receipt_sha256, receipt.approval)
    chain = inputs.candidate_inputs
    verify_creator_test_execution_receipt(
        receipt.creator_execution,
        chain.binding,
        inputs.creator_package_path,
        chain.package_path,
        chain.integrated_root,
    )
    verify_execution_receipt(
        receipt.reviewer_execution,
        inputs.reviewer_request,
        chain.binding,
        chain.package_path,
        chain.integrated_root,
    )
    _reviewer_identities(inputs.candidate, receipt.reviewer_execution)
