"""Separate final creator/reviewer suites for a signed real initial child."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_correction_dispatch import _read_repository_file
from mos_eisley.reviewer_final_suites import (
    _APPROVAL_DOMAIN,
    G4FinalWholeSuiteReceipt,
    SignedG4FinalWholeSuiteApproval,
    _claim,
    _verify_claim,
    build_isolated_creator_test_job,
    execute_isolated_creator_tests_in_trusted_host,
    verify_creator_test_execution_receipt,
)
from mos_eisley.reviewer_initial_candidate import (
    G4InitialCandidateInputs,
    G4InitialCandidateReceipt,
    verify_initial_candidate_receipt,
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


@dataclass(frozen=True)
class G4InitialFinalInputs:
    candidate: G4InitialCandidateReceipt
    chain: G4InitialCandidateInputs
    creator_package: FrozenReviewerTestPackage
    creator_package_path: Path
    creator_request: ReviewerTestExecutionRequest
    reviewer_request: ReviewerTestExecutionRequest
    final_store: Path


def _reviewer_identities(
    candidate: G4InitialCandidateReceipt,
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


def _verify_creator_package(inputs: G4InitialFinalInputs) -> None:
    chain = inputs.chain
    package = inputs.creator_package
    root = chain.integrated_root.resolve(strict=True)
    base = chain.assignment.assignment.base_revision
    integrated = chain.signed_integration.record.integrated_revision
    creator = chain.creator.approval
    references: dict[str, set[str]] = {}
    for reference in package.payload.manifest.references:
        references.setdefault(reference.kind, set()).add(reference.content_sha256)
    if (
        references.get("approved_plan") != {creator.approved_plan_sha256}
        or references.get("creator_approval") != {chain.creator.artifact_sha256}
        or references.get("rubric") != {creator.rubric_sha256}
        or references.get("interface") != set(creator.public_interface_sha256s)
        or tuple(item.declaration.path for item in package.payload.files)
        != chain.assignment.assignment.creator_test_paths
        or any(item.declaration.kind != "test" for item in package.payload.files)
    ):
        raise ValueError("creator package is not the signed protected test inventory")
    for item in package.payload.files:
        path = item.declaration.path
        content = item.content
        if (
            _read_repository_file(root, path) != content
            or _git(
                chain.git_executable,
                root,
                ["show", f"{base}:{path}"],
                limit=len(content),
            )
            != content
            or _git(
                chain.git_executable,
                root,
                ["show", f"{integrated}:{path}"],
                limit=len(content),
            )
            != content
        ):
            raise ValueError("protected creator tests changed across initial-child Git")


def preflight_initial_final(
    approval: SignedG4FinalWholeSuiteApproval,
    inputs: G4InitialFinalInputs,
    *,
    now: datetime | None = None,
) -> None:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ValueError("final-suite preflight requires explicit UTC")
    chain = inputs.chain
    grant = approval.approval
    root = chain.integrated_root.resolve(strict=True)
    for path in (inputs.creator_package_path, chain.package_path, inputs.final_store):
        if path.resolve().is_relative_to(root):
            raise ValueError("final-suite package or claim overlaps integrated Git")
    final_store = inputs.final_store.resolve()
    candidate_store = chain.candidate_store.resolve()
    if (
        final_store == candidate_store
        or final_store.is_relative_to(candidate_store)
        or candidate_store.is_relative_to(final_store)
    ):
        raise ValueError("candidate and final-suite claims need separate stores")
    verify_initial_candidate_receipt(inputs.candidate, chain)
    if not inputs.candidate.candidate_tests_passed:
        raise ValueError("final suites require a passing initial-child candidate")
    verify_provenance_signature(
        grant, approval.signature, chain.policy, "creator", _APPROVAL_DOMAIN
    )
    if not (
        chain.policy.valid_from
        <= grant.issued_at
        <= current
        < grant.expires_at
        <= chain.policy.valid_until
        and grant.issued_at >= inputs.candidate.ran_at
    ):
        raise ValueError("final-suite authority outside candidate or policy window")
    integrated = chain.signed_integration.record.integrated_revision
    if (
        not grant.suite_id.startswith("g4-q3-real-initial-final-")
        or grant.policy_sha256 != chain.policy.policy_sha256
        or grant.provenance_sha256
        != digest(canonical_bytes(chain.signed_integration))
        or grant.candidate_receipt_sha256 != inputs.candidate.receipt_sha256
        or grant.source_revision != integrated
        or grant.creator_test_suite_sha256
        != chain.creator.approval.creator_test_suite_sha256
        or grant.creator_package_sha256
        != inputs.creator_package.frozen_package_sha256
        or grant.reviewer_package_sha256 != chain.package.frozen_package_sha256
        or grant.reviewer_binding_sha256 != chain.binding.binding_record_sha256
        or grant.creator_request_sha256 != inputs.creator_request.request_sha256
        or grant.reviewer_request_sha256 != inputs.reviewer_request.request_sha256
        or grant.container_image_id != chain.container.image_id
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
        raise ValueError("final-suite approval differs from exact initial-child inputs")
    if (
        decode_frozen_reviewer_test_package(
            read_bounded(inputs.creator_package_path, FROZEN_PACKAGE_BYTES)
        )
        != inputs.creator_package
    ):
        raise ValueError("protected creator package file changed")
    _verify_creator_package(inputs)
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


def run_initial_final(
    approval: SignedG4FinalWholeSuiteApproval,
    inputs: G4InitialFinalInputs,
    *,
    now: datetime | None = None,
) -> G4FinalWholeSuiteReceipt:
    started = now if now is not None else datetime.now(UTC)
    preflight_initial_final(approval, inputs, now=started)
    chain = inputs.chain
    _claim(inputs.final_store, inputs.candidate.receipt_sha256, approval)
    creator = execute_isolated_creator_tests_in_trusted_host(
        inputs.creator_request,
        chain.binding,
        inputs.creator_package_path,
        chain.package_path,
        chain.integrated_root,
        chain.container,
    )
    reviewer = execute_isolated_reviewer_tests_in_trusted_host(
        inputs.reviewer_request,
        chain.binding,
        chain.package_path,
        chain.integrated_root,
        chain.container,
    )
    _reviewer_identities(inputs.candidate, reviewer)
    preflight_initial_final(approval, inputs, now=started)
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


def verify_initial_final_receipt(
    receipt: G4FinalWholeSuiteReceipt, inputs: G4InitialFinalInputs
) -> None:
    if (
        receipt.creator_execution.request != inputs.creator_request
        or receipt.reviewer_execution.request != inputs.reviewer_request
    ):
        raise ValueError("final-suite receipt differs from frozen requests")
    preflight_initial_final(receipt.approval, inputs, now=receipt.started_at)
    _verify_claim(
        inputs.final_store, inputs.candidate.receipt_sha256, receipt.approval
    )
    chain = inputs.chain
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
