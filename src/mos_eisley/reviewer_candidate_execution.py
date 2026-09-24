"""Exact, one-use admission and offline dispatch of G4 candidate reviewer tests."""

from __future__ import annotations

import base64
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    SourceRevision,
    record_trusted_git_provenance,
    verify_authenticated_provenance,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import (
    ContainerImageId,
    ImmutableReviewerTestExecutionReceipt,
    KnownControlValidationRecord,
    ReviewerTestExecutionRequest,
    execute_isolated_reviewer_tests_in_trusted_host,
    verify_execution_receipt,
)
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.isolation import OfflineContainer

CANDIDATE_ARTIFACT_BYTES = 2_000_000
_CANDIDATE_DOMAIN = b"mos-eisley/g4-candidate-execution-approval/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("G4 candidate timestamps require explicit UTC")
    return value


class G4CandidateExecutionApproval(Contract):
    """A creator's separate authorization for one exact offline candidate run."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_candidate_execution_approval"] = "g4_candidate_execution_approval"
    approval_id: Identifier
    policy_sha256: Digest
    authenticated_provenance_sha256: Digest
    known_control_record_sha256: Digest
    request_sha256: Digest
    repository_id: Identifier
    source_revision: SourceRevision
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
    def bounded_window(self) -> Self:
        if not self.issued_at < self.expires_at:
            raise ValueError("candidate approval window must be positive")
        if self.expires_at - self.issued_at > timedelta(hours=24):
            raise ValueError("candidate approval window exceeds 24 hours")
        return self


class SignedG4CandidateExecutionApproval(Contract):
    approval: G4CandidateExecutionApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_candidate_execution_approval(
    approval: G4CandidateExecutionApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4CandidateExecutionApproval:
    """Signing primitive for an external enrolled creator; no CLI accepts a key."""
    return SignedG4CandidateExecutionApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_CANDIDATE_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


class G4CandidateAdmissionRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_candidate_execution_admission"] = (
        "g4_candidate_execution_admission"
    )
    approval: SignedG4CandidateExecutionApproval
    request: ReviewerTestExecutionRequest
    authenticated_provenance_sha256: Digest
    known_control_record_sha256: Digest
    binding_record_sha256: Digest
    frozen_reviewer_test_package_sha256: Digest
    git_provenance_sha256: Digest
    admitted_at: datetime
    candidate_execution_admitted: Literal[True] = True
    candidate_execution_completed: Literal[False] = False
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("admitted_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def exact_identity(self) -> Self:
        if (
            self.approval.approval.request_sha256 != self.request.request_sha256
            or self.approval.approval.authenticated_provenance_sha256
            != self.authenticated_provenance_sha256
            or self.approval.approval.known_control_record_sha256
            != self.known_control_record_sha256
            or self.request.binding_record_sha256 != self.binding_record_sha256
            or self.approval.approval.container_image_id
            != self.request.container_image_id
            or self.request.role != "candidate"
        ):
            raise ValueError("candidate admission identities differ")
        if len(canonical_bytes(self)) > CANDIDATE_ARTIFACT_BYTES:
            raise ValueError("candidate admission exceeds 2 MB")
        return self

    @property
    def admission_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4CandidateDispatchReceipt(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_candidate_execution_dispatch_receipt"] = (
        "g4_candidate_execution_dispatch_receipt"
    )
    admission: G4CandidateAdmissionRecord
    dispatch_claim_sha256: Digest
    execution: ImmutableReviewerTestExecutionReceipt
    git_reverified_after_execution: Literal[True] = True
    candidate_tests_passed: bool
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        if (
            self.dispatch_claim_sha256 != self.admission.admission_sha256
            or self.execution.request != self.admission.request
            or self.execution.binding_record_sha256
            != self.admission.binding_record_sha256
            or self.execution.frozen_reviewer_test_package_sha256
            != self.admission.frozen_reviewer_test_package_sha256
            or self.candidate_tests_passed != self.execution.role_expectation_satisfied
        ):
            raise ValueError("candidate dispatch receipt differs from admission")
        if len(canonical_bytes(self)) > CANDIDATE_ARTIFACT_BYTES:
            raise ValueError("candidate dispatch receipt exceeds 2 MB")
        return self

    @property
    def receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _verify_approval(
    approval: SignedG4CandidateExecutionApproval,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    request: ReviewerTestExecutionRequest,
    now: datetime,
) -> None:
    policy = provenance.policy
    payload = approval.approval
    verify_provenance_signature(
        payload, approval.signature, policy, "creator", _CANDIDATE_DOMAIN
    )
    if not (
        policy.valid_from
        <= payload.issued_at
        <= now
        <= payload.expires_at
        <= policy.valid_until
    ):
        raise ValueError("candidate approval is outside its valid window")
    if payload.issued_at < provenance.child_result.result.issued_at:
        raise ValueError("candidate approval predates child result")
    source = provenance.git_provenance.provenance
    if (
        payload.policy_sha256 != policy.policy_sha256
        or payload.authenticated_provenance_sha256 != provenance.record_sha256
        or payload.known_control_record_sha256 != controls.control_record_sha256
        or payload.request_sha256 != request.request_sha256
        or payload.repository_id != source.repository_id
        or payload.source_revision != source.source_revision
        or payload.container_image_id != request.container_image_id
        or request.role != "candidate"
        or request.container_image_id != controls.container_image_id
    ):
        raise ValueError("candidate approval does not bind exact current inputs")


def _check_locations(
    repository_root: Path,
    implementation_root: Path,
    reviewer_package_path: Path,
    *state_paths: Path,
) -> None:
    root = repository_root.resolve()
    implementation = implementation_root.resolve()
    if not implementation.is_relative_to(root):
        raise ValueError("candidate implementation root must be inside repository")
    if any(
        path.resolve().is_relative_to(root)
        for path in (reviewer_package_path, *state_paths)
    ):
        raise ValueError("candidate artifacts and state must remain outside Git")


def admit_candidate_execution(
    *,
    approval: SignedG4CandidateExecutionApproval,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    request: ReviewerTestExecutionRequest,
    binding: ImmutableImplementationBindingRecord,
    package: FrozenReviewerTestPackage,
    reviewer_package_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    now: datetime | None = None,
) -> G4CandidateAdmissionRecord:
    """Replay all prior gates and current Git before granting one exact run."""
    _check_locations(repository_root, implementation_root, reviewer_package_path)
    admitted_at = _utc(now if now is not None else datetime.now(UTC))
    verify_authenticated_provenance(
        provenance, package=package, binding=binding, controls=controls
    )
    _verify_approval(approval, provenance, controls, request, admitted_at)
    if request.binding_record_sha256 != binding.binding_record_sha256:
        raise ValueError("candidate request differs from exact implementation binding")
    expected = provenance.git_provenance.provenance
    replayed = record_trusted_git_provenance(
        repository_id=expected.repository_id,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        binding=binding,
        reviewer_package_path=reviewer_package_path,
        assignment=provenance.child_assignment,
        result=provenance.child_result,
    )
    if replayed != expected:
        raise ValueError("current Git differs from authenticated candidate provenance")
    return G4CandidateAdmissionRecord(
        approval=approval,
        request=request,
        authenticated_provenance_sha256=provenance.record_sha256,
        known_control_record_sha256=controls.control_record_sha256,
        binding_record_sha256=binding.binding_record_sha256,
        frozen_reviewer_test_package_sha256=package.frozen_package_sha256,
        git_provenance_sha256=expected.provenance_sha256,
        admitted_at=admitted_at,
    )


def _consume_once(root: Path, admission: G4CandidateAdmissionRecord) -> None:
    """Exclusively spend an approval in one trusted, private controller-owned store."""
    directory_fd = _open_dispatch_store(root)
    try:
        name = f"{admission.approval.artifact_sha256}.claim"
        fd = os.open(
            name,
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


def _open_dispatch_store(root: Path) -> int:
    info = root.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("candidate dispatch store must be owner-owned mode 0700")
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    opened = os.fstat(directory_fd)
    if opened.st_dev != info.st_dev or opened.st_ino != info.st_ino:
        os.close(directory_fd)
        raise ValueError("candidate dispatch store changed during open")
    return directory_fd


def _verify_dispatch_claim(root: Path, admission: G4CandidateAdmissionRecord) -> None:
    directory_fd = _open_dispatch_store(root)
    try:
        name = f"{admission.approval.artifact_sha256}.claim"
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise ValueError("candidate dispatch claim is not private")
            actual = stream.read(CANDIDATE_ARTIFACT_BYTES + 1)
        if actual != canonical_bytes(admission):
            raise ValueError("candidate dispatch claim differs from admission")
    finally:
        os.close(directory_fd)


def dispatch_candidate_execution(
    admission: G4CandidateAdmissionRecord,
    *,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    binding: ImmutableImplementationBindingRecord,
    package: FrozenReviewerTestPackage,
    reviewer_package_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    container: OfflineContainer,
    dispatch_store: Path,
    now: datetime | None = None,
) -> G4CandidateDispatchReceipt:
    """Re-admit, spend once, execute in the immutable container, and recheck Git."""
    _check_locations(
        repository_root,
        implementation_root,
        reviewer_package_path,
        dispatch_store,
        container.lifecycle_root,
    )
    fresh = admit_candidate_execution(
        approval=admission.approval,
        provenance=provenance,
        controls=controls,
        request=admission.request,
        binding=binding,
        package=package,
        reviewer_package_path=reviewer_package_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        now=now,
    )
    if (
        admission.authenticated_provenance_sha256
        != fresh.authenticated_provenance_sha256
        or admission.known_control_record_sha256 != fresh.known_control_record_sha256
        or admission.binding_record_sha256 != fresh.binding_record_sha256
        or admission.frozen_reviewer_test_package_sha256
        != fresh.frozen_reviewer_test_package_sha256
        or admission.git_provenance_sha256 != fresh.git_provenance_sha256
        or admission.admitted_at > fresh.admitted_at
        or admission.admitted_at < admission.approval.approval.issued_at
    ):
        raise ValueError("candidate admission is stale or inconsistent")
    if container.image_id != admission.request.container_image_id:
        raise ValueError("candidate container differs from approved image")
    _consume_once(dispatch_store, admission)
    execution = execute_isolated_reviewer_tests_in_trusted_host(
        admission.request,
        binding,
        reviewer_package_path,
        implementation_root,
        container,
    )
    verify_execution_receipt(
        execution,
        admission.request,
        binding,
        reviewer_package_path,
        implementation_root,
    )
    replayed = record_trusted_git_provenance(
        repository_id=provenance.git_provenance.provenance.repository_id,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        binding=binding,
        reviewer_package_path=reviewer_package_path,
        assignment=provenance.child_assignment,
        result=provenance.child_result,
    )
    if replayed != provenance.git_provenance.provenance:
        raise ValueError("candidate Git provenance changed during execution")
    return G4CandidateDispatchReceipt(
        admission=admission,
        dispatch_claim_sha256=admission.admission_sha256,
        execution=execution,
        candidate_tests_passed=execution.role_expectation_satisfied,
    )


def verify_candidate_dispatch_receipt(
    receipt: G4CandidateDispatchReceipt,
    *,
    dispatch_store: Path,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    binding: ImmutableImplementationBindingRecord,
    package: FrozenReviewerTestPackage,
    reviewer_package_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
) -> None:
    """Replay current inputs without requiring approval to remain unexpired."""
    verify_authenticated_provenance(
        provenance, package=package, binding=binding, controls=controls
    )
    _verify_approval(
        receipt.admission.approval,
        provenance,
        controls,
        receipt.admission.request,
        receipt.admission.admitted_at,
    )
    _verify_dispatch_claim(dispatch_store, receipt.admission)
    if (
        receipt.admission.binding_record_sha256 != binding.binding_record_sha256
        or receipt.admission.frozen_reviewer_test_package_sha256
        != package.frozen_package_sha256
        or receipt.admission.git_provenance_sha256
        != provenance.git_provenance.provenance.provenance_sha256
    ):
        raise ValueError("candidate dispatch receipt names stale inputs")
    verify_execution_receipt(
        receipt.execution,
        receipt.admission.request,
        binding,
        reviewer_package_path,
        implementation_root,
    )
    replayed = record_trusted_git_provenance(
        repository_id=provenance.git_provenance.provenance.repository_id,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        binding=binding,
        reviewer_package_path=reviewer_package_path,
        assignment=provenance.child_assignment,
        result=provenance.child_result,
    )
    if replayed != provenance.git_provenance.provenance:
        raise ValueError("current Git differs from candidate dispatch receipt")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def decode_candidate_artifact[T: Contract](payload: bytes, model: type[T]) -> T:
    if len(payload) > CANDIDATE_ARTIFACT_BYTES:
        raise ValueError("G4 candidate artifact exceeds 2 MB")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        value = model.model_validate_json(payload)
        if payload != canonical_bytes(value):
            raise ValueError("G4 candidate artifact must be canonical")
        return value
    except (ValueError, RecursionError):
        raise ValueError("invalid G4 candidate artifact") from None
