"""Admit a reproduced failed initial candidate to one bounded correction cycle.

This bridge does not convert paid initial-child evidence into legacy Git-child
provenance. Its admission type grants no dispatch authority by itself.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_correction import (
    _CYCLE_DOMAIN,
    MAX_RECORD_BYTES,
    G4CorrectionReviewPolicy,
    SignedG4CorrectionCycleApproval,
    SignedG4CorrectionTriage,
    _assignment_reservations,
    _claim_name,
    _reserve,
    _utc,
    _verify_triage_signature,
)
from mos_eisley.reviewer_initial_candidate import (
    G4InitialCandidateInputs,
    G4InitialCandidateReceipt,
    verify_initial_candidate_receipt,
)
from mos_eisley.reviewer_provenance import SourceRevision, verify_provenance_signature


class G4InitialCorrectionCycleAdmission(Contract):
    """A claimed review decision, not correction-child or repository authority."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_correction_cycle_admission"] = (
        "g4_initial_correction_cycle_admission"
    )
    triage: SignedG4CorrectionTriage
    approval: SignedG4CorrectionCycleApproval
    candidate_receipt_sha256: Digest
    reproduction_receipt_sha256: Digest
    signed_integration_sha256: Digest
    binding_record_sha256: Digest
    known_control_record_sha256: Digest
    frozen_reviewer_test_package_sha256: Digest
    source_revision: SourceRevision
    admitted_at: datetime
    cycle_claimed: Literal[True] = True
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    final_suite_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("admitted_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def exact_links(self) -> Self:
        decision = self.triage.triage
        grant = self.approval.approval
        if (
            decision.task_id != grant.task_id
            or decision.cycle != 1
            or grant.cycle != 1
            or grant.previous_completion_sha256 is not None
            or grant.triage_artifact_sha256 != self.triage.artifact_sha256
            or decision.candidate_receipt_sha256 != self.candidate_receipt_sha256
            or decision.reproduction_receipt_sha256 != self.reproduction_receipt_sha256
            or grant.source_revision != self.source_revision
            or grant.frozen_reviewer_test_package_sha256
            != self.frozen_reviewer_test_package_sha256
            or len(canonical_bytes(self)) > MAX_RECORD_BYTES
        ):
            raise ValueError("initial correction admission identities differ")
        return self

    @property
    def admission_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _matching_failed_pair(
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
) -> tuple[str, ...]:
    left = first.execution
    right = reproduction.execution
    a = left.observation
    b = right.observation
    if (
        first.candidate_tests_passed
        or reproduction.candidate_tests_passed
        or first.ran_at >= reproduction.ran_at
        or first.approval.artifact_sha256 == reproduction.approval.artifact_sha256
        or first.request.execution_id == reproduction.request.execution_id
        or first_inputs.candidate_store.resolve()
        == reproduction_inputs.candidate_store.resolve()
    ):
        raise ValueError("initial correction needs distinct ordered failed executions")
    if (
        first_inputs.policy != reproduction_inputs.policy
        or first_inputs.creator != reproduction_inputs.creator
        or first_inputs.custody != reproduction_inputs.custody
        or first_inputs.assignment != reproduction_inputs.assignment
        or first_inputs.signed_integration != reproduction_inputs.signed_integration
        or first_inputs.binding != reproduction_inputs.binding
        or first_inputs.controls != reproduction_inputs.controls
        or first_inputs.package != reproduction_inputs.package
        or first_inputs.integrated_root.resolve()
        != reproduction_inputs.integrated_root.resolve()
        or left.binding_record_sha256 != right.binding_record_sha256
        or left.frozen_reviewer_test_package_sha256
        != right.frozen_reviewer_test_package_sha256
        or left.implementation_tree_sha256 != right.implementation_tree_sha256
        or left.adapter_sha256 != right.adapter_sha256
        or left.collection_sha256 != right.collection_sha256
        or first.request.container_image_id != reproduction.request.container_image_id
    ):
        raise ValueError("initial correction reproduction changed source or tests")
    if (
        not left.collection_contract_satisfied
        or not right.collection_contract_satisfied
        or a.schema_version != 2
        or b.schema_version != 2
        or a.failures < 1
        or b.failures < 1
        or a.errors
        or b.errors
        or a.unexpected_successes
        or b.unexpected_successes
        or tuple(sorted(a.failed_test_ids)) != tuple(sorted(b.failed_test_ids))
        or a.collected_test_ids_sha256 != b.collected_test_ids_sha256
        or a.executed_test_ids_sha256 != b.executed_test_ids_sha256
    ):
        raise ValueError("initial correction needs matching assertion failures")
    return tuple(sorted(a.failed_test_ids))


def _write_initial_claim(
    store: Path, admission: G4InitialCorrectionCycleAdmission
) -> None:
    fd = open_private_dispatch_store(store)
    try:
        name = _claim_name(
            admission.approval.approval.task_id, admission.approval.approval.cycle
        )
        claim_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(admission))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def _evaluate_initial_correction_cycle(
    *,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    triage: SignedG4CorrectionTriage,
    approval: SignedG4CorrectionCycleApproval,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    now: datetime | None = None,
) -> G4InitialCorrectionCycleAdmission:
    """Replay exact evidence and construct a cycle-one decision without a write."""
    current = _utc(now if now is not None else datetime.now(UTC))
    root = first_inputs.original_root.resolve()
    integrated = first_inputs.integrated_root.resolve()
    if any(
        correction_store.resolve().is_relative_to(path) for path in (root, integrated)
    ):
        raise ValueError("initial correction state must remain outside Git")
    verify_initial_candidate_receipt(first, first_inputs)
    verify_initial_candidate_receipt(reproduction, reproduction_inputs)
    failed_ids = _matching_failed_pair(
        first, reproduction, first_inputs, reproduction_inputs
    )
    policy = first_inputs.policy
    decision = triage.triage
    grant = approval.approval
    original = first_inputs.creator.approval
    assignment = first_inputs.assignment.assignment
    integration = first_inputs.signed_integration.record
    budget = grant.task_budget
    if (
        review_policy.provenance_policy_sha256 != policy.policy_sha256
        or review_policy.operator_mode != policy.operator_mode
        or not review_policy.valid_from
        <= decision.issued_at
        <= current
        <= review_policy.valid_until
        or decision.issued_at < reproduction.ran_at
        or decision.candidate_receipt_sha256 != first.receipt_sha256
        or decision.reproduction_receipt_sha256 != reproduction.receipt_sha256
        or tuple(item.failed_test_id for item in decision.findings) != failed_ids
        or any(
            item.disposition != "implementation_defect" for item in decision.findings
        )
    ):
        raise ValueError("initial correction triage does not cover reproduced defects")
    if review_policy.operator_mode == "separated":
        human_keys = {
            item.public_key_sha256
            for item in policy.creators + policy.reviewers + policy.vcs_brokers
        }
        if any(item.public_key_sha256 in human_keys for item in review_policy.judges):
            raise ValueError("separated correction judge shares a custody key")
    child_keys = {item.public_key_sha256 for item in policy.children}
    if any(item.public_key_sha256 in child_keys for item in review_policy.judges):
        raise ValueError("correction judge shares a coding-child key")
    _verify_triage_signature(triage, review_policy)
    verify_provenance_signature(
        grant, approval.signature, policy, "creator", _CYCLE_DOMAIN
    )
    if (
        grant.task_id != decision.task_id
        or grant.cycle != 1
        or grant.previous_completion_sha256 is not None
        or grant.provenance_policy_sha256 != policy.policy_sha256
        or grant.triage_artifact_sha256 != triage.artifact_sha256
        or grant.source_revision != integration.integrated_revision
        or grant.approved_plan_sha256 != original.approved_plan_sha256
        or grant.creator_test_suite_sha256 != original.creator_test_suite_sha256
        or grant.frozen_reviewer_test_package_sha256
        != first_inputs.package.frozen_package_sha256
        or grant.child_signer_id != assignment.child_signer_id
        or not set(grant.owned_paths) <= set(assignment.owned_paths)
        or set(grant.owned_paths) & set(assignment.creator_test_paths)
        or grant.max_input_tokens > assignment.max_input_tokens
        or grant.max_output_tokens > assignment.max_output_tokens
        or grant.max_tool_calls > assignment.max_tool_calls
        or grant.max_seconds > assignment.max_seconds
        or grant.max_microusd > assignment.max_microusd
        or budget.initial_assignment_sha256 != first_inputs.assignment.artifact_sha256
        or grant.reserved_before != _assignment_reservations(assignment)
        or current > budget.deadline
        or grant.expires_at > budget.deadline
        or not decision.issued_at
        <= grant.issued_at
        <= current
        <= grant.expires_at
        <= policy.valid_until
    ):
        raise ValueError("initial correction approval exceeds source, scope or budget")
    after = _reserve(grant.reserved_before, grant)
    ceiling = budget.ceiling
    if any(
        used > limit
        for used, limit in (
            (after.input_tokens, ceiling.input_tokens),
            (after.output_tokens, ceiling.output_tokens),
            (after.tool_calls, ceiling.tool_calls),
            (after.seconds, ceiling.seconds),
            (after.microusd, ceiling.microusd),
        )
    ):
        raise ValueError("initial correction exceeds aggregate task allowance")
    admission = G4InitialCorrectionCycleAdmission(
        triage=triage,
        approval=approval,
        candidate_receipt_sha256=first.receipt_sha256,
        reproduction_receipt_sha256=reproduction.receipt_sha256,
        signed_integration_sha256=digest(
            canonical_bytes(first_inputs.signed_integration)
        ),
        binding_record_sha256=first_inputs.binding.binding_record_sha256,
        known_control_record_sha256=first_inputs.controls.control_record_sha256,
        frozen_reviewer_test_package_sha256=first_inputs.package.frozen_package_sha256,
        source_revision=integration.integrated_revision,
        admitted_at=current,
    )
    return admission


def admit_initial_correction_cycle(
    *,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    triage: SignedG4CorrectionTriage,
    approval: SignedG4CorrectionCycleApproval,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    now: datetime | None = None,
) -> G4InitialCorrectionCycleAdmission:
    """Replay both signed initial receipts, adjudicate, and claim cycle one once."""
    admission = _evaluate_initial_correction_cycle(
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        triage=triage,
        approval=approval,
        review_policy=review_policy,
        correction_store=correction_store,
        now=now,
    )
    _write_initial_claim(correction_store, admission)
    return admission


def verify_initial_correction_cycle_claim(
    store: Path, admission: G4InitialCorrectionCycleAdmission
) -> None:
    """Verify the owner-private durable claim for this exact admission."""
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _claim_name(
                admission.approval.approval.task_id,
                admission.approval.approval.cycle,
            ),
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise ValueError("initial correction claim is not private")
            actual = stream.read(MAX_RECORD_BYTES + 1)
        if actual != canonical_bytes(admission):
            raise ValueError("initial correction claim differs from admission")
    finally:
        os.close(fd)


def verify_initial_correction_cycle_admission(
    admission: G4InitialCorrectionCycleAdmission,
    *,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
) -> None:
    """Replay the signed historical decision, current Git and its one-use claim."""
    expected = _evaluate_initial_correction_cycle(
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        triage=admission.triage,
        approval=admission.approval,
        review_policy=review_policy,
        correction_store=correction_store,
        now=admission.admitted_at,
    )
    if expected != admission:
        raise ValueError("initial correction admission differs from replay")
    verify_initial_correction_cycle_claim(correction_store, admission)
