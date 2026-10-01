"""Fresh candidate test authority on a separately signed initial correction."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_coding_broker import G4ProductionCodingChildReceipt
from mos_eisley.reviewer_correction import G4CorrectionReviewPolicy
from mos_eisley.reviewer_correction_dispatch import G4CorrectionChildDispatchReceipt
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
    verify_implementation_binding_record,
)
from mos_eisley.reviewer_initial_candidate import (
    G4InitialCandidateInputs,
    G4InitialCandidateReceipt,
)
from mos_eisley.reviewer_initial_correction import G4InitialCorrectionCycleAdmission
from mos_eisley.reviewer_initial_correction_integration import (
    SignedG4InitialCorrectionIntegrationRecord,
    verify_initial_correction_integration_record,
)
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    SourceRevision,
    _git,
    _git_text,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import (
    ContainerImageId,
    ImmutableReviewerTestExecutionReceipt,
    ReviewerTestExecutionRequest,
    build_isolated_reviewer_test_job,
    execute_isolated_reviewer_tests_in_trusted_host,
    verify_execution_receipt,
)

_DOMAIN = b"mos-eisley/g4-initial-correction-candidate-approval/v1\x00"


class G4InitialCorrectionCandidateApproval(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_correction_candidate_approval"] = (
        "g4_initial_correction_candidate_approval"
    )
    approval_id: Identifier
    policy_sha256: Digest
    admission_sha256: Digest
    signed_integration_sha256: Digest
    binding_record_sha256: Digest
    known_control_record_sha256: Digest
    reviewer_package_sha256: Digest
    request_sha256: Digest
    candidate_store_sha256: Digest
    integrated_revision: SourceRevision
    container_image_id: ContainerImageId
    issued_at: datetime
    expires_at: datetime
    candidate_execution_authorized: Literal[True] = True
    provider_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    final_suite_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("correction candidate authority requires explicit UTC")
        return value

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("correction candidate authority window is invalid")
        return self


class SignedG4InitialCorrectionCandidateApproval(Contract):
    approval: G4InitialCorrectionCandidateApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4InitialCorrectionCandidateReceipt(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_correction_candidate_receipt"] = (
        "g4_initial_correction_candidate_receipt"
    )
    approval: SignedG4InitialCorrectionCandidateApproval
    request: ReviewerTestExecutionRequest
    execution: ImmutableReviewerTestExecutionReceipt
    ran_at: datetime
    candidate_tests_passed: bool
    original_source_unchanged: Literal[True] = True
    initial_integrated_source_unchanged: Literal[True] = True
    corrected_source_unchanged: Literal[True] = True
    final_suite_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("ran_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("correction candidate receipt requires explicit UTC")
        return value

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        if (
            self.approval.approval.request_sha256 != self.request.request_sha256
            or self.execution.request != self.request
            or self.candidate_tests_passed != self.execution.role_expectation_satisfied
            or not self.approval.approval.issued_at
            <= self.ran_at
            < self.approval.approval.expires_at
            or len(canonical_bytes(self)) > 2_000_000
        ):
            raise ValueError(
                "correction candidate receipt differs from exact execution"
            )
        return self

    @property
    def receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_initial_correction_candidate_approval(
    approval: G4InitialCorrectionCandidateApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4InitialCorrectionCandidateApproval:
    return SignedG4InitialCorrectionCandidateApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


@dataclass(frozen=True)
class G4InitialCorrectionCandidateInputs:
    admission: G4InitialCorrectionCycleAdmission
    dispatch: G4CorrectionChildDispatchReceipt
    production: G4ProductionCodingChildReceipt
    first: G4InitialCandidateReceipt
    reproduction: G4InitialCandidateReceipt
    first_inputs: G4InitialCandidateInputs
    reproduction_inputs: G4InitialCandidateInputs
    review_policy: G4CorrectionReviewPolicy
    correction_store: Path
    child_dispatch_store: Path
    production_store: Path
    integration_store: Path
    signed_integration: SignedG4InitialCorrectionIntegrationRecord
    binding: ImmutableImplementationBindingRecord
    candidate_store: Path

    @property
    def candidate_root(self) -> Path:
        return self.integration_store / self.signed_integration.record.worktree_name


def replay_initial_correction_candidate_inputs(
    inputs: G4InitialCorrectionCandidateInputs,
) -> None:
    """Check the full correction chain, frozen adapter and current clean Git."""
    chain = inputs.first_inputs
    verify_initial_correction_integration_record(
        inputs.signed_integration,
        admission=inputs.admission,
        dispatch=inputs.dispatch,
        production=inputs.production,
        first=inputs.first,
        reproduction=inputs.reproduction,
        first_inputs=chain,
        reproduction_inputs=inputs.reproduction_inputs,
        review_policy=inputs.review_policy,
        correction_store=inputs.correction_store,
        child_dispatch_store=inputs.child_dispatch_store,
        production_store=inputs.production_store,
        integration_store=inputs.integration_store,
    )
    root = inputs.candidate_root.resolve(strict=True)
    store = inputs.candidate_store.resolve(strict=True)
    fd = open_private_dispatch_store(inputs.candidate_store)
    os.close(fd)
    for other in (
        chain.original_root,
        chain.integrated_root,
        root,
        chain.candidate_store,
        inputs.reproduction_inputs.candidate_store,
        inputs.correction_store,
        inputs.child_dispatch_store,
        inputs.production_store,
        inputs.integration_store,
    ):
        resolved = other.resolve(strict=True)
        if store.is_relative_to(resolved) or resolved.is_relative_to(store):
            raise ValueError("correction candidate claim store overlaps prior state")
    if chain.package_path.resolve().is_relative_to(root):
        raise ValueError("correction candidate reviewer package overlaps Git")
    verify_implementation_binding_record(inputs.binding, chain.package_path, root)
    old = chain.binding.payload.manifest
    new = inputs.binding.payload.manifest
    record = inputs.signed_integration.record
    if (
        new.source_revision != record.integrated_revision
        or new.adapter != old.adapter
        or new.source_roots != old.source_roots
        or tuple((item.path, item.kind) for item in new.files)
        != tuple((item.path, item.kind) for item in old.files)
        or inputs.binding.payload.adapter_sha256 != chain.controls.adapter_sha256
        or inputs.binding.payload.frozen_reviewer_test_package_sha256
        != chain.package.frozen_package_sha256
        or chain.controls.container_image_id != chain.container.image_id
        or chain.package_path.read_bytes() != canonical_bytes(chain.package)
        or _git_text(chain.git_executable, root, ["rev-parse", "HEAD"])
        != record.integrated_revision
        or _git(
            chain.git_executable,
            root,
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        )
    ):
        raise ValueError("correction candidate binding, package or Git changed")


def preflight_initial_correction_candidate(
    signed: SignedG4InitialCorrectionCandidateApproval,
    request: ReviewerTestExecutionRequest,
    inputs: G4InitialCorrectionCandidateInputs,
    *,
    now: datetime | None = None,
) -> None:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ValueError("correction candidate preflight requires explicit UTC")
    replay_initial_correction_candidate_inputs(inputs)
    chain = inputs.first_inputs
    grant = signed.approval
    record = inputs.signed_integration.record
    cycle = inputs.admission.approval.approval
    verify_provenance_signature(
        grant, signed.signature, chain.policy, "creator", _DOMAIN
    )
    if (
        not chain.policy.valid_from <= grant.issued_at <= current < grant.expires_at
        or grant.expires_at
        > min(chain.policy.valid_until, cycle.expires_at, cycle.task_budget.deadline)
        or grant.issued_at < record.integrated_at
        or grant.policy_sha256 != chain.policy.policy_sha256
        or grant.admission_sha256 != inputs.admission.admission_sha256
        or grant.signed_integration_sha256
        != digest(canonical_bytes(inputs.signed_integration))
        or grant.binding_record_sha256 != inputs.binding.binding_record_sha256
        or grant.known_control_record_sha256 != chain.controls.control_record_sha256
        or grant.reviewer_package_sha256 != chain.package.frozen_package_sha256
        or grant.request_sha256 != request.request_sha256
        or grant.candidate_store_sha256
        != digest(str(inputs.candidate_store.resolve(strict=True)).encode())
        or grant.integrated_revision != record.integrated_revision
        or grant.container_image_id != chain.container.image_id
        or request.container_image_id != chain.container.image_id
        or request.binding_record_sha256 != inputs.binding.binding_record_sha256
        or request.role != "candidate"
    ):
        raise ValueError("correction candidate grant differs from exact signed inputs")
    build_isolated_reviewer_test_job(
        request, inputs.binding, chain.package_path, inputs.candidate_root
    )


def _claim(store: Path, signed: SignedG4InitialCorrectionCandidateApproval) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            signed.artifact_sha256 + ".claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(signed))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_claim(
    store: Path, signed: SignedG4InitialCorrectionCandidateApproval
) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            signed.artifact_sha256 + ".claim", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd
        )
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or stream.read(16_385) != canonical_bytes(signed)
            ):
                raise ValueError("correction candidate claim differs or is not private")
    finally:
        os.close(fd)


def run_initial_correction_candidate(
    signed: SignedG4InitialCorrectionCandidateApproval,
    request: ReviewerTestExecutionRequest,
    inputs: G4InitialCorrectionCandidateInputs,
) -> G4InitialCorrectionCandidateReceipt:
    """Spend one exact grant and execute its frozen reviewer job once offline."""
    preflight_initial_correction_candidate(signed, request, inputs)
    started = datetime.now(UTC)
    if not signed.approval.issued_at <= started or (
        started + timedelta(seconds=request.timeout_seconds)
        >= signed.approval.expires_at
    ):
        raise ValueError("correction candidate grant lacks remaining execution time")
    _claim(inputs.candidate_store, signed)
    chain = inputs.first_inputs
    execution = execute_isolated_reviewer_tests_in_trusted_host(
        request,
        inputs.binding,
        chain.package_path,
        inputs.candidate_root,
        chain.container,
    )
    verify_execution_receipt(
        execution, request, inputs.binding, chain.package_path, inputs.candidate_root
    )
    replay_initial_correction_candidate_inputs(inputs)
    return G4InitialCorrectionCandidateReceipt(
        approval=signed,
        request=request,
        execution=execution,
        ran_at=started,
        candidate_tests_passed=execution.role_expectation_satisfied,
    )


def verify_initial_correction_candidate_receipt(
    receipt: G4InitialCorrectionCandidateReceipt,
    inputs: G4InitialCorrectionCandidateInputs,
) -> None:
    preflight_initial_correction_candidate(
        receipt.approval, receipt.request, inputs, now=receipt.ran_at
    )
    _verify_claim(inputs.candidate_store, receipt.approval)
    verify_execution_receipt(
        receipt.execution,
        receipt.request,
        inputs.binding,
        inputs.first_inputs.package_path,
        inputs.candidate_root,
    )
