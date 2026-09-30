"""Exact whole-suite authority for a passing initial correction candidate."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_correction_dispatch import _read_repository_file
from mos_eisley.reviewer_final_suites import (
    _APPROVAL_DOMAIN,
    G4FinalWholeSuiteApproval,
    SignedG4FinalWholeSuiteApproval,
    build_isolated_creator_test_job,
)
from mos_eisley.reviewer_initial_correction_candidate import (
    G4InitialCorrectionCandidateInputs,
    G4InitialCorrectionCandidateReceipt,
    verify_initial_correction_candidate_receipt,
)
from mos_eisley.reviewer_provenance import _git, verify_provenance_signature
from mos_eisley.reviewer_test_execution import (
    ReviewerTestExecutionRequest,
    build_isolated_reviewer_test_job,
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
