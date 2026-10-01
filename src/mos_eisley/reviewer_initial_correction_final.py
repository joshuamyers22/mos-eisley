"""Exact whole-suite authority for a passing initial correction candidate."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from mos_eisley.core.models import Contract, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_correction_dispatch import _read_repository_file
from mos_eisley.reviewer_final_suites import (
    _APPROVAL_DOMAIN,
    FINAL_SUITE_ARTIFACT_BYTES,
    G4FinalWholeSuiteApproval,
    G4FinalWholeSuiteReceipt,
    SignedG4FinalWholeSuiteApproval,
    _claim,
    _verify_claim,
    build_isolated_creator_test_job,
    execute_isolated_creator_tests_in_trusted_host,
    verify_creator_test_execution_receipt,
)
from mos_eisley.reviewer_initial_correction_candidate import (
    G4InitialCorrectionCandidateInputs,
    G4InitialCorrectionCandidateReceipt,
    verify_initial_correction_candidate_receipt,
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
class G4InitialCorrectionFinalInputs:
    candidate: G4InitialCorrectionCandidateReceipt
    chain: G4InitialCorrectionCandidateInputs
    creator_package: FrozenReviewerTestPackage
    creator_package_path: Path
    creator_request: ReviewerTestExecutionRequest
    reviewer_request: ReviewerTestExecutionRequest
    final_store: Path


def initial_correction_final_approval(
    inputs: G4InitialCorrectionFinalInputs, issued_at: datetime
) -> G4FinalWholeSuiteApproval:
    """Construct exact bounded authority; construction itself grants nothing."""
    context = inputs.chain
    chain = context.first_inputs
    cycle = context.admission.approval.approval
    return G4FinalWholeSuiteApproval(
        suite_id="g4-q4-ic-final-"
        + digest(str(inputs.final_store.resolve(strict=True)).encode()),
        policy_sha256=chain.policy.policy_sha256,
        provenance_sha256=digest(canonical_bytes(context.signed_integration)),
        candidate_receipt_sha256=inputs.candidate.receipt_sha256,
        source_revision=context.signed_integration.record.integrated_revision,
        creator_test_suite_sha256=chain.creator.approval.creator_test_suite_sha256,
        creator_package_sha256=inputs.creator_package.frozen_package_sha256,
        reviewer_package_sha256=chain.package.frozen_package_sha256,
        reviewer_binding_sha256=context.binding.binding_record_sha256,
        creator_request_sha256=inputs.creator_request.request_sha256,
        reviewer_request_sha256=inputs.reviewer_request.request_sha256,
        container_image_id=chain.container.image_id,
        issued_at=issued_at,
        expires_at=min(
            issued_at + timedelta(hours=2),
            chain.policy.valid_until,
            cycle.expires_at,
            cycle.task_budget.deadline,
        ),
    )


def _verify_creator_package(inputs: G4InitialCorrectionFinalInputs) -> None:
    context = inputs.chain
    chain = context.first_inputs
    package = inputs.creator_package
    root = context.candidate_root.resolve(strict=True)
    references: dict[str, set[str]] = {}
    for reference in package.payload.manifest.references:
        references.setdefault(reference.kind, set()).add(reference.content_sha256)
    creator = chain.creator.approval
    if (
        references.get("approved_plan") != {creator.approved_plan_sha256}
        or references.get("creator_approval") != {chain.creator.artifact_sha256}
        or references.get("rubric") != {creator.rubric_sha256}
        or references.get("interface") != set(creator.public_interface_sha256s)
        or tuple(item.declaration.path for item in package.payload.files)
        != chain.assignment.assignment.creator_test_paths
        or any(item.declaration.kind != "test" for item in package.payload.files)
    ):
        raise ValueError("final creator package differs from protected inventory")
    for item in package.payload.files:
        if _read_repository_file(root, item.declaration.path) != item.content:
            raise ValueError("protected creator test bytes changed")
        for revision in (
            chain.assignment.assignment.base_revision,
            chain.signed_integration.record.integrated_revision,
            context.signed_integration.record.integrated_revision,
        ):
            if (
                _git(
                    chain.git_executable,
                    root,
                    ["show", f"{revision}:{item.declaration.path}"],
                    limit=len(item.content),
                )
                != item.content
            ):
                raise ValueError(
                    "protected creator tests changed across correction Git"
                )


def _verify_creator_collection(package: FrozenReviewerTestPackage) -> None:
    """Check discovery importability without importing or executing task tests."""
    collection = package.payload.manifest.collection
    directory = PurePosixPath(collection.start_directory)
    top = PurePosixPath(collection.top_level_directory)
    paths = {item.declaration.path for item in package.payload.files}
    while directory != top:
        if (directory / "__init__.py").as_posix() not in paths:
            raise ValueError(
                "creator discovery requires an initializer outside its frozen inventory"
            )
        directory = directory.parent


def replay_initial_correction_final_inputs(
    inputs: G4InitialCorrectionFinalInputs,
) -> None:
    """Verify final subjects and build both jobs without executing either suite."""
    context = inputs.chain
    chain = context.first_inputs
    verify_initial_correction_candidate_receipt(inputs.candidate, context)
    if not inputs.candidate.candidate_tests_passed:
        raise ValueError("final suites require a passing correction candidate")
    fd = open_private_dispatch_store(inputs.final_store)
    os.close(fd)
    store = inputs.final_store.resolve(strict=True)
    for other in (
        context.candidate_root,
        chain.original_root,
        chain.integrated_root,
        context.candidate_store,
        chain.candidate_store,
        context.reproduction_inputs.candidate_store,
        context.correction_store,
        context.child_dispatch_store,
        context.production_store,
        context.integration_store,
    ):
        root = other.resolve(strict=True)
        if store.is_relative_to(root) or root.is_relative_to(store):
            raise ValueError("final whole-suite claims overlap prior state")
    root = context.candidate_root.resolve(strict=True)
    for path in (chain.package_path, inputs.creator_package_path):
        if path.resolve().is_relative_to(root):
            raise ValueError("final whole-suite packages overlap corrected Git")
    if (
        decode_frozen_reviewer_test_package(
            read_bounded(inputs.creator_package_path, FROZEN_PACKAGE_BYTES)
        )
        != inputs.creator_package
    ):
        raise ValueError("final creator package file changed")
    _verify_creator_package(inputs)
    _verify_creator_collection(inputs.creator_package)
    if (
        inputs.creator_request.role != "candidate"
        or inputs.reviewer_request.role != "candidate"
        or inputs.creator_request.execution_id == inputs.reviewer_request.execution_id
        or inputs.reviewer_request.execution_id == inputs.candidate.request.execution_id
        or inputs.creator_request.execution_id == inputs.candidate.request.execution_id
        or any(
            request.binding_record_sha256 != context.binding.binding_record_sha256
            or request.container_image_id != chain.container.image_id
            for request in (inputs.creator_request, inputs.reviewer_request)
        )
    ):
        raise ValueError(
            "final whole-suite requests are not distinct exact offline runs"
        )
    build_isolated_creator_test_job(
        inputs.creator_request,
        context.binding,
        inputs.creator_package_path,
        chain.package_path,
        root,
    )
    build_isolated_reviewer_test_job(
        inputs.reviewer_request, context.binding, chain.package_path, root
    )


def preflight_initial_correction_final(
    signed: SignedG4FinalWholeSuiteApproval,
    inputs: G4InitialCorrectionFinalInputs,
    *,
    now: datetime | None = None,
) -> None:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ValueError("final whole-suite preflight requires explicit UTC")
    replay_initial_correction_final_inputs(inputs)
    chain = inputs.chain.first_inputs
    grant = signed.approval
    verify_provenance_signature(
        grant, signed.signature, chain.policy, "creator", _APPROVAL_DOMAIN
    )
    if (
        grant != initial_correction_final_approval(inputs, grant.issued_at)
        or not chain.policy.valid_from <= grant.issued_at <= current < grant.expires_at
        or grant.issued_at < inputs.candidate.ran_at
    ):
        raise ValueError(
            "final whole-suite authority differs from exact correction inputs"
        )


def _reviewer_identities(
    candidate: G4InitialCorrectionCandidateReceipt,
    execution: ImmutableReviewerTestExecutionReceipt,
) -> None:
    before = candidate.execution.observation
    after = execution.observation
    if (
        before.collected_test_ids_sha256 != after.collected_test_ids_sha256
        or before.started_test_ids_sha256 != after.started_test_ids_sha256
        or before.executed_test_ids_sha256 != after.executed_test_ids_sha256
    ):
        raise ValueError(
            "final correction reviewer suite executed different test identities"
        )


def _save_stage(store: Path, name: str, receipt: Contract) -> None:
    fd = open_private_dispatch_store(store)
    try:
        output_fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
        )
        with os.fdopen(output_fd, "wb") as stream:
            stream.write(canonical_bytes(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_stage(store: Path, name: str, receipt: Contract) -> None:
    fd = open_private_dispatch_store(store)
    try:
        input_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        with os.fdopen(input_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or stream.read(FINAL_SUITE_ARTIFACT_BYTES + 1)
                != canonical_bytes(receipt)
            ):
                raise ValueError(
                    "retained final suite execution differs or is not private"
                )
    finally:
        os.close(fd)


def run_initial_correction_final(
    signed: SignedG4FinalWholeSuiteApproval,
    inputs: G4InitialCorrectionFinalInputs,
) -> G4FinalWholeSuiteReceipt:
    """Consume one grant and execute both exact offline jobs separately."""
    preflight_initial_correction_final(signed, inputs)
    started = datetime.now(UTC)
    required_seconds = (
        inputs.creator_request.timeout_seconds + inputs.reviewer_request.timeout_seconds
    )
    if not signed.approval.issued_at <= started or (
        started + timedelta(seconds=required_seconds) >= signed.approval.expires_at
    ):
        raise ValueError("final suite grant lacks remaining execution time")
    _claim(inputs.final_store, inputs.candidate.receipt_sha256, signed)
    context = inputs.chain
    chain = context.first_inputs
    creator = execute_isolated_creator_tests_in_trusted_host(
        inputs.creator_request,
        context.binding,
        inputs.creator_package_path,
        chain.package_path,
        context.candidate_root,
        chain.container,
    )
    verify_creator_test_execution_receipt(
        creator,
        context.binding,
        inputs.creator_package_path,
        chain.package_path,
        context.candidate_root,
    )
    _save_stage(
        inputs.final_store, inputs.candidate.receipt_sha256 + ".creator.json", creator
    )
    if (
        datetime.now(UTC) + timedelta(seconds=inputs.reviewer_request.timeout_seconds)
        >= signed.approval.expires_at
    ):
        raise ValueError("final suite grant expired before reviewer execution")
    reviewer = execute_isolated_reviewer_tests_in_trusted_host(
        inputs.reviewer_request,
        context.binding,
        chain.package_path,
        context.candidate_root,
        chain.container,
    )
    verify_execution_receipt(
        reviewer,
        inputs.reviewer_request,
        context.binding,
        chain.package_path,
        context.candidate_root,
    )
    _save_stage(
        inputs.final_store, inputs.candidate.receipt_sha256 + ".reviewer.json", reviewer
    )
    _reviewer_identities(inputs.candidate, reviewer)
    preflight_initial_correction_final(signed, inputs, now=started)
    return G4FinalWholeSuiteReceipt(
        approval=signed,
        candidate_receipt_sha256=inputs.candidate.receipt_sha256,
        source_revision=signed.approval.source_revision,
        creator_execution=creator,
        reviewer_execution=reviewer,
        started_at=started,
        final_suites_passed=(
            creator.role_expectation_satisfied and reviewer.role_expectation_satisfied
        ),
    )


def verify_initial_correction_final_receipt(
    receipt: G4FinalWholeSuiteReceipt,
    inputs: G4InitialCorrectionFinalInputs,
) -> None:
    """Replay the exact private claim, both measured receipts and unchanged Git."""
    if (
        receipt.creator_execution.request != inputs.creator_request
        or receipt.reviewer_execution.request != inputs.reviewer_request
    ):
        raise ValueError("final suite receipt differs from frozen execution requests")
    preflight_initial_correction_final(receipt.approval, inputs, now=receipt.started_at)
    _verify_claim(inputs.final_store, inputs.candidate.receipt_sha256, receipt.approval)
    _verify_stage(
        inputs.final_store,
        inputs.candidate.receipt_sha256 + ".creator.json",
        receipt.creator_execution,
    )
    _verify_stage(
        inputs.final_store,
        inputs.candidate.receipt_sha256 + ".reviewer.json",
        receipt.reviewer_execution,
    )
    context = inputs.chain
    chain = context.first_inputs
    verify_creator_test_execution_receipt(
        receipt.creator_execution,
        context.binding,
        inputs.creator_package_path,
        chain.package_path,
        context.candidate_root,
    )
    verify_execution_receipt(
        receipt.reviewer_execution,
        inputs.reviewer_request,
        context.binding,
        chain.package_path,
        context.candidate_root,
    )
    _reviewer_identities(inputs.candidate, receipt.reviewer_execution)
