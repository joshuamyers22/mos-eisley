"""One-use offline reviewer candidate gate for a signed real initial child."""

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
from mos_eisley.reviewer_creator_metadata import (
    SignedG4CreatorMetadataRecord,
    verify_creator_metadata_record,
    verify_creator_metadata_record_signature,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
    verify_implementation_binding_record,
)
from mos_eisley.reviewer_initial_child import G4InitialChildDispatchReceipt
from mos_eisley.reviewer_initial_coding_broker import G4ProductionInitialChildReceipt
from mos_eisley.reviewer_initial_integration import (
    SignedG4InitialIntegrationRecord,
    verify_initial_integration_record,
)
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    SignedG4ChildAssignment,
    SignedG4CreatorApproval,
    SignedG4ReviewerCustody,
    SourceRevision,
    _git,
    _git_text,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import (
    ContainerImageId,
    ImmutableReviewerTestExecutionReceipt,
    KnownControlValidationRecord,
    ReviewerTestExecutionRequest,
    build_isolated_reviewer_test_job,
    execute_isolated_reviewer_tests_in_trusted_host,
    validate_known_controls,
    verify_execution_receipt,
)
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.spend_ledger import SpendLedger

_DOMAIN = b"mos-eisley/g4-initial-candidate-approval/v1\x00"
_METADATA_DOMAIN = b"mos-eisley/g4-metadata-candidate-approval/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("initial candidate requires explicit UTC")
    return value


class G4InitialCandidateApproval(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_candidate_approval"] = "g4_initial_candidate_approval"
    approval_id: Identifier
    policy_sha256: Digest
    signed_integration_sha256: Digest
    binding_record_sha256: Digest
    known_control_record_sha256: Digest
    request_sha256: Digest
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
        return _utc(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("initial candidate window is invalid")
        return self


class G4MetadataCandidateApproval(G4InitialCandidateApproval):
    signed_metadata_record_sha256: Digest


class SignedG4InitialCandidateApproval(Contract):
    approval: G4MetadataCandidateApproval | G4InitialCandidateApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_initial_candidate_approval(
    approval: G4InitialCandidateApproval, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4InitialCandidateApproval:
    return SignedG4InitialCandidateApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(
                    (
                        _METADATA_DOMAIN
                        if isinstance(approval, G4MetadataCandidateApproval)
                        else _DOMAIN
                    )
                    + canonical_bytes(approval)
                )
            ).decode("ascii"),
        ),
    )


class G4InitialCandidateReceipt(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_candidate_receipt"] = "g4_initial_candidate_receipt"
    approval: SignedG4InitialCandidateApproval
    request: ReviewerTestExecutionRequest
    execution: ImmutableReviewerTestExecutionReceipt
    ran_at: datetime
    candidate_tests_passed: bool
    original_source_unchanged: Literal[True] = True
    integrated_source_unchanged: Literal[True] = True
    final_suite_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("ran_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        if (
            self.approval.approval.request_sha256 != self.request.request_sha256
            or self.execution.request != self.request
            or self.candidate_tests_passed != self.execution.role_expectation_satisfied
            or len(canonical_bytes(self)) > 2_000_000
        ):
            raise ValueError("initial candidate receipt differs from execution")
        return self

    @property
    def receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


@dataclass(frozen=True)
class G4InitialCandidateInputs:
    policy: G4ProvenanceTrustPolicy
    creator: SignedG4CreatorApproval
    custody: SignedG4ReviewerCustody
    assignment: SignedG4ChildAssignment
    package: FrozenReviewerTestPackage
    package_path: Path
    dispatch: G4InitialChildDispatchReceipt
    production: G4ProductionInitialChildReceipt
    signed_integration: SignedG4InitialIntegrationRecord
    binding: ImmutableImplementationBindingRecord
    controls: KnownControlValidationRecord
    good_binding: ImmutableImplementationBindingRecord
    bad_binding: ImmutableImplementationBindingRecord
    original_root: Path
    integrated_root: Path
    good_root: Path
    bad_root: Path
    git_executable: Path
    container: OfflineContainer
    ledger: SpendLedger
    dispatch_store: Path
    production_store: Path
    integration_store: Path
    candidate_store: Path
    approved_plan: str
    brief: str
    acceptance_criteria: str
    signed_metadata: SignedG4CreatorMetadataRecord | None = None
    metadata_store: Path | None = None
    initial_container: OfflineContainer | None = None


def replay_initial_candidate_inputs(inputs: G4InitialCandidateInputs) -> None:
    """Replay paid child, VCS record, binding, controls and current clean Git."""
    integrated = inputs.signed_integration.record
    original = inputs.original_root.resolve(strict=True)
    root = inputs.integrated_root.resolve(strict=True)
    store = inputs.candidate_store.resolve(strict=True)
    fd = open_private_dispatch_store(store)
    os.close(fd)
    parent = (inputs.integration_store / integrated.worktree_name).resolve(strict=True)
    expected_root = parent
    revision = integrated.integrated_revision
    if inputs.signed_metadata is not None:
        if inputs.metadata_store is None:
            raise ValueError("metadata candidate lacks its amendment store")
        verify_creator_metadata_record_signature(inputs.signed_metadata, inputs.policy)
        verify_creator_metadata_record(
            inputs.signed_metadata.record,
            policy=inputs.policy,
            creator=inputs.creator,
            custody=inputs.custody,
            vcs=inputs.signed_integration,
            parent_root=parent,
            store=inputs.metadata_store,
            git=inputs.git_executable,
        )
        expected_root = (
            inputs.metadata_store / inputs.signed_metadata.record.worktree_name
        ).resolve(strict=True)
        revision = inputs.signed_metadata.record.revision
    elif inputs.metadata_store is not None:
        raise ValueError("metadata store requires signed metadata evidence")
    if (
        root != expected_root
        or root == original
        or any(
            path.resolve().is_relative_to(root)
            for path in (
                inputs.package_path,
                inputs.candidate_store,
                inputs.dispatch_store,
                inputs.production_store,
                inputs.integration_store,
                *(
                    (inputs.metadata_store,)
                    if inputs.metadata_store is not None
                    else ()
                ),
            )
        )
    ):
        raise ValueError("initial candidate state overlaps integrated Git")
    verify_initial_integration_record(
        inputs.signed_integration,
        dispatch=inputs.dispatch,
        production=inputs.production,
        policy=inputs.policy,
        creator=inputs.creator,
        custody=inputs.custody,
        assignment=inputs.assignment,
        package=inputs.package,
        repository_root=original,
        git_executable=inputs.git_executable,
        approved_plan=inputs.approved_plan,
        brief=inputs.brief,
        acceptance_criteria=inputs.acceptance_criteria,
        container=inputs.initial_container or inputs.container,
        dispatch_store=inputs.dispatch_store,
        production_store=inputs.production_store,
        ledger=inputs.ledger,
        integration_store=inputs.integration_store,
    )
    verify_implementation_binding_record(inputs.binding, inputs.package_path, root)
    if (
        inputs.binding.payload.manifest.source_revision != revision
        or inputs.binding.payload.frozen_reviewer_test_package_sha256
        != inputs.package.frozen_package_sha256
        or inputs.binding.payload.adapter_sha256 != inputs.controls.adapter_sha256
        or inputs.controls.container_image_id != inputs.container.image_id
        or _git_text(inputs.git_executable, root, ["rev-parse", "HEAD"]) != revision
        or _git(
            inputs.git_executable,
            root,
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        )
    ):
        raise ValueError("initial candidate binding, controls or Git changed")
    if inputs.package_path.read_bytes() != canonical_bytes(inputs.package):
        raise ValueError("initial candidate reviewer package changed")
    good = inputs.controls.known_good
    bad = inputs.controls.known_bad
    for receipt, binding, control_root in (
        (good, inputs.good_binding, inputs.good_root),
        (bad, inputs.bad_binding, inputs.bad_root),
    ):
        verify_execution_receipt(
            receipt, receipt.request, binding, inputs.package_path, control_root
        )
    if validate_known_controls(good, bad) != inputs.controls:
        raise ValueError("initial candidate known controls differ")


def preflight_initial_candidate(
    approval: SignedG4InitialCandidateApproval,
    request: ReviewerTestExecutionRequest,
    inputs: G4InitialCandidateInputs,
    *,
    now: datetime | None = None,
) -> None:
    current = _utc(now if now is not None else datetime.now(UTC))
    replay_initial_candidate_inputs(inputs)
    grant = approval.approval
    metadata = getattr(inputs, "signed_metadata", None)
    revision = inputs.signed_integration.record.integrated_revision
    if metadata is not None:
        revision = metadata.record.revision
        if (
            not isinstance(grant, G4MetadataCandidateApproval)
            or grant.signed_metadata_record_sha256 != metadata.artifact_sha256
            or grant.issued_at < metadata.record.amended_at
        ):
            raise ValueError("metadata candidate grant differs from signed amendment")
    elif isinstance(grant, G4MetadataCandidateApproval):
        raise ValueError("metadata candidate grant lacks signed amendment")
    verify_provenance_signature(
        grant,
        approval.signature,
        inputs.policy,
        "creator",
        _METADATA_DOMAIN if isinstance(grant, G4MetadataCandidateApproval) else _DOMAIN,
    )
    integrated = inputs.signed_integration.record
    if (
        not inputs.policy.valid_from
        <= grant.issued_at
        <= current
        < grant.expires_at
        <= inputs.policy.valid_until
        or grant.issued_at < integrated.integrated_at
        or grant.policy_sha256 != inputs.policy.policy_sha256
        or grant.signed_integration_sha256
        != digest(canonical_bytes(inputs.signed_integration))
        or grant.binding_record_sha256 != inputs.binding.binding_record_sha256
        or grant.known_control_record_sha256 != inputs.controls.control_record_sha256
        or grant.request_sha256 != request.request_sha256
        or grant.integrated_revision != revision
        or grant.container_image_id != inputs.container.image_id
        or request.container_image_id != inputs.container.image_id
        or request.binding_record_sha256 != inputs.binding.binding_record_sha256
        or request.role != "candidate"
    ):
        raise ValueError("initial candidate grant differs from exact inputs")
    build_isolated_reviewer_test_job(
        request, inputs.binding, inputs.package_path, inputs.integrated_root
    )


def _claim(store: Path, approval: SignedG4InitialCandidateApproval) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            approval.artifact_sha256 + ".claim",
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


def _verify_claim(store: Path, approval: SignedG4InitialCandidateApproval) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            approval.artifact_sha256 + ".claim", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd
        )
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or stream.read(16_385) != canonical_bytes(approval)
            ):
                raise ValueError("initial candidate claim differs or is not private")
    finally:
        os.close(fd)


def run_initial_candidate(
    approval: SignedG4InitialCandidateApproval,
    request: ReviewerTestExecutionRequest,
    inputs: G4InitialCandidateInputs,
    *,
    now: datetime | None = None,
) -> G4InitialCandidateReceipt:
    started = _utc(now if now is not None else datetime.now(UTC))
    preflight_initial_candidate(approval, request, inputs, now=started)
    _claim(inputs.candidate_store, approval)
    execution = execute_isolated_reviewer_tests_in_trusted_host(
        request,
        inputs.binding,
        inputs.package_path,
        inputs.integrated_root,
        inputs.container,
    )
    verify_execution_receipt(
        execution,
        request,
        inputs.binding,
        inputs.package_path,
        inputs.integrated_root,
    )
    replay_initial_candidate_inputs(inputs)
    return G4InitialCandidateReceipt(
        approval=approval,
        request=request,
        execution=execution,
        ran_at=started,
        candidate_tests_passed=execution.role_expectation_satisfied,
    )


def verify_initial_candidate_receipt(
    receipt: G4InitialCandidateReceipt, inputs: G4InitialCandidateInputs
) -> None:
    preflight_initial_candidate(
        receipt.approval, receipt.request, inputs, now=receipt.ran_at
    )
    _verify_claim(inputs.candidate_store, receipt.approval)
    verify_execution_receipt(
        receipt.execution,
        receipt.request,
        inputs.binding,
        inputs.package_path,
        inputs.integrated_root,
    )
    if receipt.candidate_tests_passed != receipt.execution.role_expectation_satisfied:
        raise ValueError("initial candidate result differs from reviewer execution")
