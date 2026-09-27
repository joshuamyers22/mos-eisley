"""One-use offline candidate run for a signed post-deadline G4 integration.

The historical custody chain remains under its original policy. A fresh creator
signature under the renewed same-roster policy authorizes only the integrated
revision's exact reviewer-test request. Every admission replays the full signed
integration chain and the current read-only Git reconstruction.
"""

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
from mos_eisley.reviewer_candidate_execution import (
    G4CandidateDispatchReceipt,
    _check_locations,
    open_private_dispatch_store,
)
from mos_eisley.reviewer_correction import G4CorrectionCycleAdmission
from mos_eisley.reviewer_correction_dispatch import G4CorrectionChildDispatchReceipt
from mos_eisley.reviewer_correction_integration import (
    SignedG4CorrectionIntegrationRecord,
    verify_correction_integration_record,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
    verify_implementation_binding_record,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    SourceRevision,
    record_trusted_git_provenance,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import (
    ContainerImageId,
    ImmutableReviewerTestExecutionReceipt,
    KnownControlValidationRecord,
    ReviewerTestExecutionRequest,
    build_isolated_reviewer_test_job,
    execute_isolated_reviewer_tests_in_trusted_host,
    verify_execution_receipt,
)
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.isolation import OfflineContainer

_DOMAIN = b"mos-eisley/g4-carryforward-candidate-approval/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("carry-forward candidate timestamps require UTC")
    return value


class G4CarryForwardCandidateApproval(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_carryforward_candidate_approval"] = (
        "g4_carryforward_candidate_approval"
    )
    approval_id: Identifier
    historical_provenance_sha256: Digest
    signed_integration_sha256: Digest
    renewed_policy_sha256: Digest
    binding_record_sha256: Digest
    known_control_record_sha256: Digest
    request_sha256: Digest
    repository_id: Identifier
    integrated_revision: SourceRevision
    container_image_id: ContainerImageId
    issued_at: datetime
    expires_at: datetime
    candidate_execution_authorized: Literal[True] = True
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("carry-forward candidate window is invalid")
        return self


class SignedG4CarryForwardCandidateApproval(Contract):
    approval: G4CarryForwardCandidateApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_carryforward_candidate_approval(
    approval: G4CarryForwardCandidateApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4CarryForwardCandidateApproval:
    return SignedG4CarryForwardCandidateApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


class G4CarryForwardCandidateAdmission(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_carryforward_candidate_admission"] = (
        "g4_carryforward_candidate_admission"
    )
    approval: SignedG4CarryForwardCandidateApproval
    request: ReviewerTestExecutionRequest
    integrated_git_provenance_sha256: Digest
    admitted_at: datetime
    candidate_execution_admitted: Literal[True] = True
    candidate_execution_completed: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("admitted_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @property
    def admission_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4CarryForwardCandidateReceipt(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_carryforward_candidate_receipt"] = (
        "g4_carryforward_candidate_receipt"
    )
    admission: G4CarryForwardCandidateAdmission
    dispatch_claim_sha256: Digest
    execution: ImmutableReviewerTestExecutionReceipt
    git_reverified_after_execution: Literal[True] = True
    candidate_tests_passed: bool
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        if (
            self.dispatch_claim_sha256 != self.admission.admission_sha256
            or self.execution.request != self.admission.request
            or self.execution.binding_record_sha256
            != self.admission.approval.approval.binding_record_sha256
            or self.candidate_tests_passed != self.execution.role_expectation_satisfied
        ):
            raise ValueError("carry-forward candidate receipt differs from admission")
        if len(canonical_bytes(self)) > 2_000_000:
            raise ValueError("carry-forward candidate receipt exceeds 2 MB")
        return self

    @property
    def receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


@dataclass(frozen=True)
class G4CarryForwardCandidateInputs:
    """Private controller inputs needed to replay the complete historical chain."""

    admission: G4CorrectionCycleAdmission
    child_receipt: G4CorrectionChildDispatchReceipt
    failed_candidate: G4CandidateDispatchReceipt
    historical_provenance: AuthenticatedG4ProvenanceRecord
    historical_binding: ImmutableImplementationBindingRecord
    signed_integration: SignedG4CorrectionIntegrationRecord
    renewed_policy: G4ProvenanceTrustPolicy
    binding: ImmutableImplementationBindingRecord
    controls: KnownControlValidationRecord
    package: FrozenReviewerTestPackage
    package_path: Path
    original_root: Path
    integrated_root: Path
    git_executable: Path
    candidate_store: Path
    correction_store: Path
    child_dispatch_store: Path
    integration_store: Path


def _replay(inputs: G4CarryForwardCandidateInputs) -> str:
    old = inputs.historical_provenance
    integrated = inputs.signed_integration.record
    if (
        integrated.schema_version != 2
        or inputs.renewed_policy.policy_sha256
        != integrated.approval.approval.renewed_policy_sha256
        or inputs.integrated_root.resolve(strict=True)
        != (inputs.integration_store / integrated.worktree_name).resolve(strict=True)
        or inputs.integrated_root.resolve().is_relative_to(
            inputs.original_root.resolve()
        )
    ):
        raise ValueError(
            "candidate source differs from signed carry-forward integration"
        )
    verify_correction_integration_record(
        inputs.signed_integration,
        admission=inputs.admission,
        receipt=inputs.child_receipt,
        first=inputs.failed_candidate,
        provenance=old,
        controls=inputs.controls,
        binding=inputs.historical_binding,
        package=inputs.package,
        reviewer_package_path=inputs.package_path,
        repository_root=inputs.original_root,
        implementation_root=inputs.original_root,
        git_executable=inputs.git_executable,
        candidate_dispatch_store=inputs.candidate_store,
        correction_store=inputs.correction_store,
        child_dispatch_store=inputs.child_dispatch_store,
        integration_store=inputs.integration_store,
        renewed_policy=inputs.renewed_policy,
    )
    verify_implementation_binding_record(
        inputs.binding, inputs.package_path, inputs.integrated_root
    )
    if (
        inputs.binding.payload.manifest.source_revision
        != integrated.integrated_revision
        or inputs.binding.payload.frozen_reviewer_test_package_sha256
        != inputs.package.frozen_package_sha256
        or inputs.binding.payload.adapter_sha256 != inputs.controls.adapter_sha256
    ):
        raise ValueError("candidate binding differs from integrated revision")
    current = record_trusted_git_provenance(
        repository_id=old.git_provenance.provenance.repository_id,
        repository_root=inputs.integrated_root,
        implementation_root=inputs.integrated_root,
        git_executable=inputs.git_executable,
        binding=inputs.binding,
        reviewer_package_path=inputs.package_path,
        assignment=old.child_assignment,
        result=old.child_result,
    )
    if (
        current.source_revision != integrated.integrated_revision
        or current.source_tree_id != integrated.integrated_tree_id
        or current.binding_record_sha256 != inputs.binding.binding_record_sha256
    ):
        raise ValueError("candidate Git provenance differs from signed integration")
    return current.provenance_sha256


def admit_carryforward_candidate(
    approval: SignedG4CarryForwardCandidateApproval,
    request: ReviewerTestExecutionRequest,
    inputs: G4CarryForwardCandidateInputs,
    *,
    now: datetime | None = None,
) -> G4CarryForwardCandidateAdmission:
    current = _utc(now if now is not None else datetime.now(UTC))
    _check_locations(
        inputs.integrated_root,
        inputs.integrated_root,
        inputs.package_path,
        inputs.candidate_store,
        inputs.integration_store,
        inputs.correction_store,
        inputs.child_dispatch_store,
    )
    git_sha256 = _replay(inputs)
    policy = inputs.renewed_policy
    signed = approval.approval
    verify_provenance_signature(signed, approval.signature, policy, "creator", _DOMAIN)
    old = inputs.historical_provenance
    integrated = inputs.signed_integration.record
    if (
        not policy.valid_from
        <= signed.issued_at
        <= current
        < signed.expires_at
        <= policy.valid_until
        or signed.issued_at < integrated.integrated_at
        or signed.historical_provenance_sha256 != old.record_sha256
        or signed.signed_integration_sha256
        != digest(canonical_bytes(inputs.signed_integration))
        or signed.renewed_policy_sha256 != policy.policy_sha256
        or signed.binding_record_sha256 != inputs.binding.binding_record_sha256
        or signed.known_control_record_sha256 != inputs.controls.control_record_sha256
        or signed.request_sha256 != request.request_sha256
        or signed.repository_id != old.git_provenance.provenance.repository_id
        or signed.integrated_revision != integrated.integrated_revision
        or signed.container_image_id != request.container_image_id
        or request.container_image_id != inputs.controls.container_image_id
        or request.binding_record_sha256 != inputs.binding.binding_record_sha256
        or request.role != "candidate"
    ):
        raise ValueError("carry-forward candidate approval differs from exact inputs")
    build_isolated_reviewer_test_job(
        request, inputs.binding, inputs.package_path, inputs.integrated_root
    )
    directory_fd = open_private_dispatch_store(inputs.candidate_store)
    os.close(directory_fd)
    return G4CarryForwardCandidateAdmission(
        approval=approval,
        request=request,
        integrated_git_provenance_sha256=git_sha256,
        admitted_at=current,
    )


def _claim(store: Path, admission: G4CarryForwardCandidateAdmission) -> None:
    directory_fd = open_private_dispatch_store(store)
    try:
        fd = os.open(
            f"{admission.approval.artifact_sha256}.claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_bytes(admission))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _verify_claim(store: Path, admission: G4CarryForwardCandidateAdmission) -> None:
    directory_fd = open_private_dispatch_store(store)
    try:
        fd = os.open(
            f"{admission.approval.artifact_sha256}.claim",
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or stream.read(2_000_001) != canonical_bytes(admission)
            ):
                raise ValueError("carry-forward candidate claim differs from admission")
    finally:
        os.close(directory_fd)


def dispatch_carryforward_candidate(
    admission: G4CarryForwardCandidateAdmission,
    inputs: G4CarryForwardCandidateInputs,
    container: OfflineContainer,
    *,
    now: datetime | None = None,
) -> G4CarryForwardCandidateReceipt:
    _check_locations(
        inputs.integrated_root,
        inputs.integrated_root,
        inputs.package_path,
        inputs.candidate_store,
        container.lifecycle_root,
    )
    fresh = admit_carryforward_candidate(
        admission.approval, admission.request, inputs, now=now
    )
    if (
        admission.integrated_git_provenance_sha256
        != fresh.integrated_git_provenance_sha256
        or admission.admitted_at > fresh.admitted_at
        or admission.admitted_at < admission.approval.approval.issued_at
        or container.image_id != admission.request.container_image_id
        or container.lifecycle_root.resolve().is_relative_to(
            inputs.integrated_root.resolve()
        )
        or inputs.candidate_store.resolve().is_relative_to(
            inputs.integrated_root.resolve()
        )
        or container.lifecycle_root.resolve() == inputs.candidate_store.resolve()
    ):
        raise ValueError("carry-forward candidate admission is stale")
    _claim(inputs.candidate_store, admission)
    execution = execute_isolated_reviewer_tests_in_trusted_host(
        admission.request,
        inputs.binding,
        inputs.package_path,
        inputs.integrated_root,
        container,
    )
    verify_execution_receipt(
        execution,
        admission.request,
        inputs.binding,
        inputs.package_path,
        inputs.integrated_root,
    )
    if _replay(inputs) != admission.integrated_git_provenance_sha256:
        raise ValueError("carry-forward candidate Git changed during execution")
    return G4CarryForwardCandidateReceipt(
        admission=admission,
        dispatch_claim_sha256=admission.admission_sha256,
        execution=execution,
        candidate_tests_passed=execution.role_expectation_satisfied,
    )


def verify_carryforward_candidate_receipt(
    receipt: G4CarryForwardCandidateReceipt,
    inputs: G4CarryForwardCandidateInputs,
) -> None:
    replay = admit_carryforward_candidate(
        receipt.admission.approval,
        receipt.admission.request,
        inputs,
        now=receipt.admission.admitted_at,
    )
    if (
        replay.integrated_git_provenance_sha256
        != receipt.admission.integrated_git_provenance_sha256
    ):
        raise ValueError("carry-forward candidate Git differs from receipt")
    _verify_claim(inputs.candidate_store, receipt.admission)
    verify_execution_receipt(
        receipt.execution,
        receipt.admission.request,
        inputs.binding,
        inputs.package_path,
        inputs.integrated_root,
    )
