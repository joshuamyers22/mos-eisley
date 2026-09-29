"""Separately approved final creator/reviewer whole-suite execution for G4.

The result is test evidence only. It does not approve an implementation or grant
provider, repository-write, critic/judge, or release authority.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import fnmatch
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Literal, Self, TypedDict

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import (
    G4CandidateDispatchReceipt,
    open_private_dispatch_store,
    verify_candidate_dispatch_receipt,
)
from mos_eisley.reviewer_correction_dispatch import _read_repository_file
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
    snapshot_implementation_files,
    verify_implementation_binding_record,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    SourceRevision,
    _git,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import (
    ContainerImageId,
    ExecutionImplementationFile,
    ImmutableReviewerTestExecutionReceipt,
    IsolatedReviewerTestObservation,
    KnownControlValidationRecord,
    ReviewerTestExecutionRequest,
    decode_execution_observation,
    execute_isolated_reviewer_tests_in_trusted_host,
    verify_execution_receipt,
)
from mos_eisley.reviewer_test_package import (
    FROZEN_PACKAGE_BYTES,
    FrozenReviewerTestPackage,
    TestCollectionContract,
    decode_frozen_reviewer_test_package,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import MAX_WIRE_BYTES, OfflineContainer

FINAL_SUITE_ARTIFACT_BYTES = 4_000_000
_APPROVAL_DOMAIN = b"mos-eisley/g4-final-whole-suite-approval/v1\x00"


class _PreflightInputs(TypedDict):
    approval: SignedG4FinalWholeSuiteApproval
    candidate: G4CandidateDispatchReceipt
    provenance: AuthenticatedG4ProvenanceRecord
    controls: KnownControlValidationRecord
    creator_request: ReviewerTestExecutionRequest
    reviewer_request: ReviewerTestExecutionRequest
    reviewer_binding: ImmutableImplementationBindingRecord
    creator_package: FrozenReviewerTestPackage
    reviewer_package: FrozenReviewerTestPackage
    creator_package_path: Path
    reviewer_package_path: Path
    repository_root: Path
    implementation_root: Path
    git_executable: Path
    candidate_dispatch_store: Path
    final_dispatch_store: Path
    now: datetime


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("final-suite timestamps require explicit UTC")
    return value


class G4FinalWholeSuiteApproval(Contract):
    """Creator authority for two exact offline runs on one final Git tree."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_final_whole_suite_approval"] = "g4_final_whole_suite_approval"
    suite_id: Identifier
    policy_sha256: Digest
    provenance_sha256: Digest
    candidate_receipt_sha256: Digest
    source_revision: SourceRevision
    creator_test_suite_sha256: Digest
    creator_package_sha256: Digest
    reviewer_package_sha256: Digest
    reviewer_binding_sha256: Digest
    creator_request_sha256: Digest
    reviewer_request_sha256: Digest
    container_image_id: ContainerImageId
    issued_at: datetime
    expires_at: datetime
    final_test_execution_authorized: Literal[True] = True
    repository_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    independent_review_passed: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def bounded_window(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("final-suite approval window is invalid")
        return self


class SignedG4FinalWholeSuiteApproval(Contract):
    approval: G4FinalWholeSuiteApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_final_whole_suite_approval(
    approval: G4FinalWholeSuiteApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4FinalWholeSuiteApproval:
    """External creator-custody primitive; no production CLI accepts a key."""
    return SignedG4FinalWholeSuiteApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_APPROVAL_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


class IsolatedCreatorTestJob(Contract):
    """Direct-import creator tests plus the already authenticated code binding."""

    schema_version: Literal[1] = 1
    kind: Literal["isolated_creator_test_job"] = "isolated_creator_test_job"
    request: ReviewerTestExecutionRequest
    binding: ImmutableImplementationBindingRecord
    creator_package: FrozenReviewerTestPackage
    implementation_files: tuple[ExecutionImplementationFile, ...]

    @model_validator(mode="after")
    def exact_material(self) -> Self:
        expected = tuple(
            item
            for item in self.binding.payload.manifest.files
            if item.kind in {"implementation_source", "implementation_resource"}
        )
        if (
            self.request.binding_record_sha256 != self.binding.binding_record_sha256
            or tuple(item.declaration for item in self.implementation_files) != expected
            or self.request.role != "candidate"
            or len(canonical_bytes(self)) > MAX_WIRE_BYTES
        ):
            raise ValueError("creator-test job differs from bound source or request")
        return self

    @property
    def job_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ImmutableCreatorTestExecutionReceipt(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["immutable_creator_test_execution_receipt"] = (
        "immutable_creator_test_execution_receipt"
    )
    request: ReviewerTestExecutionRequest
    binding_record_sha256: Digest
    creator_package_sha256: Digest
    implementation_tree_sha256: Digest
    collection: TestCollectionContract
    collection_sha256: Digest
    job_sha256: Digest
    observation: IsolatedReviewerTestObservation
    inputs_reverified_after_execution: Literal[True] = True
    collection_contract_satisfied: bool
    role_expectation_satisfied: bool
    repository_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        observed = self.observation
        counts_match = (
            observed.collected_tests == self.collection.expected_collected_tests
            and observed.started_tests == self.collection.expected_collected_tests
            and observed.executed_tests == self.collection.expected_executed_tests
            and observed.skipped_tests == self.collection.expected_skipped_tests
        )
        if (
            self.request.binding_record_sha256 != self.binding_record_sha256
            or self.request.role != "candidate"
            or self.collection_sha256 != digest(canonical_bytes(self.collection))
            or observed.job_sha256 != self.job_sha256
            or self.collection_contract_satisfied != counts_match
            or self.role_expectation_satisfied
            != (counts_match and observed.suite_successful)
            or len(canonical_bytes(self)) > 1_000_000
        ):
            raise ValueError("creator-test execution receipt is inconsistent")
        return self


def build_isolated_creator_test_job(
    request: ReviewerTestExecutionRequest,
    binding: ImmutableImplementationBindingRecord,
    creator_package_path: Path,
    reviewer_package_path: Path,
    implementation_root: Path,
) -> IsolatedCreatorTestJob:
    verify_implementation_binding_record(
        binding, reviewer_package_path, implementation_root
    )
    package = decode_frozen_reviewer_test_package(
        read_bounded(creator_package_path, FROZEN_PACKAGE_BYTES)
    )
    payloads = snapshot_implementation_files(
        binding.payload.manifest, implementation_root
    )
    material = tuple(
        ExecutionImplementationFile(
            declaration=declaration,
            content_base64=base64.b64encode(payloads[declaration.path]).decode("ascii"),
        )
        for declaration in binding.payload.manifest.files
        if declaration.kind in {"implementation_source", "implementation_resource"}
    )
    job = IsolatedCreatorTestJob(
        request=request,
        binding=binding,
        creator_package=package,
        implementation_files=material,
    )
    verify_implementation_binding_record(
        binding, reviewer_package_path, implementation_root
    )
    return job


def execute_isolated_creator_tests_in_trusted_host(
    request: ReviewerTestExecutionRequest,
    binding: ImmutableImplementationBindingRecord,
    creator_package_path: Path,
    reviewer_package_path: Path,
    implementation_root: Path,
    container: OfflineContainer,
) -> ImmutableCreatorTestExecutionReceipt:
    if container.image_id != request.container_image_id:
        raise ValueError("creator-test container differs from approved image")
    job = build_isolated_creator_test_job(
        request,
        binding,
        creator_package_path,
        reviewer_package_path,
        implementation_root,
    )
    response = container.execute(
        ("-m", "mos_eisley.run.creator_test_worker"),
        canonical_bytes(job),
        timeout=float(request.timeout_seconds),
    )
    observation = decode_execution_observation(response)
    if observation.job_sha256 != job.job_sha256:
        raise ValueError("creator worker observed another job")
    current = build_isolated_creator_test_job(
        request,
        binding,
        creator_package_path,
        reviewer_package_path,
        implementation_root,
    )
    if current != job:
        raise ValueError("creator-test inputs changed during execution")
    collection = job.creator_package.payload.manifest.collection
    counts_match = (
        observation.collected_tests == collection.expected_collected_tests
        and observation.started_tests == collection.expected_collected_tests
        and observation.executed_tests == collection.expected_executed_tests
        and observation.skipped_tests == collection.expected_skipped_tests
    )
    return ImmutableCreatorTestExecutionReceipt(
        request=request,
        binding_record_sha256=binding.binding_record_sha256,
        creator_package_sha256=job.creator_package.frozen_package_sha256,
        implementation_tree_sha256=binding.payload.implementation_tree_sha256,
        collection=collection,
        collection_sha256=digest(canonical_bytes(collection)),
        job_sha256=job.job_sha256,
        observation=observation,
        collection_contract_satisfied=counts_match,
        role_expectation_satisfied=counts_match and observation.suite_successful,
    )


def verify_creator_test_execution_receipt(
    receipt: ImmutableCreatorTestExecutionReceipt,
    binding: ImmutableImplementationBindingRecord,
    creator_package_path: Path,
    reviewer_package_path: Path,
    implementation_root: Path,
) -> None:
    job = build_isolated_creator_test_job(
        receipt.request,
        binding,
        creator_package_path,
        reviewer_package_path,
        implementation_root,
    )
    if (
        receipt.binding_record_sha256 != binding.binding_record_sha256
        or receipt.creator_package_sha256 != job.creator_package.frozen_package_sha256
        or receipt.implementation_tree_sha256
        != binding.payload.implementation_tree_sha256
        or receipt.collection != job.creator_package.payload.manifest.collection
        or receipt.job_sha256 != job.job_sha256
    ):
        raise ValueError("creator-test receipt differs from current inputs")


class G4FinalWholeSuiteReceipt(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_final_whole_suite_receipt"] = "g4_final_whole_suite_receipt"
    approval: SignedG4FinalWholeSuiteApproval
    candidate_receipt_sha256: Digest
    source_revision: SourceRevision
    creator_execution: ImmutableCreatorTestExecutionReceipt
    reviewer_execution: ImmutableReviewerTestExecutionReceipt
    started_at: datetime
    inputs_reverified_after_execution: Literal[True] = True
    final_suites_passed: bool
    independent_review_passed: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("started_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        grant = self.approval.approval
        if (
            self.candidate_receipt_sha256 != grant.candidate_receipt_sha256
            or self.source_revision != grant.source_revision
            or self.creator_execution.request.request_sha256
            != grant.creator_request_sha256
            or self.reviewer_execution.request.request_sha256
            != grant.reviewer_request_sha256
            or self.creator_execution.binding_record_sha256
            != grant.reviewer_binding_sha256
            or self.reviewer_execution.binding_record_sha256
            != grant.reviewer_binding_sha256
            or self.creator_execution.creator_package_sha256
            != grant.creator_package_sha256
            or self.reviewer_execution.frozen_reviewer_test_package_sha256
            != grant.reviewer_package_sha256
            or self.final_suites_passed
            != (
                self.creator_execution.role_expectation_satisfied
                and self.reviewer_execution.role_expectation_satisfied
            )
            or not grant.issued_at <= self.started_at < grant.expires_at
            or len(canonical_bytes(self)) > FINAL_SUITE_ARTIFACT_BYTES
        ):
            raise ValueError("final-suite receipt differs from exact approval or runs")
        return self

    @property
    def receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _verify_creator_package(
    package: FrozenReviewerTestPackage,
    provenance: AuthenticatedG4ProvenanceRecord,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
) -> None:
    creator = provenance.creator_approval.approval
    assignment = provenance.child_assignment.assignment
    references = package.payload.manifest.references
    by_kind: dict[str, set[str]] = {}
    for reference in references:
        by_kind.setdefault(reference.kind, set()).add(reference.content_sha256)
    if (
        by_kind.get("approved_plan") != {creator.approved_plan_sha256}
        or by_kind.get("creator_approval")
        != {provenance.creator_approval.artifact_sha256}
        or by_kind.get("rubric") != {creator.rubric_sha256}
        or by_kind.get("interface") != set(creator.public_interface_sha256s)
    ):
        raise ValueError("creator package derivation references differ from approval")
    files = package.payload.files
    test_paths = tuple(
        item.declaration.path for item in files if item.declaration.kind == "test"
    )
    if test_paths != assignment.creator_test_paths:
        raise ValueError("creator package is not the complete protected test inventory")
    pattern = package.payload.manifest.collection.pattern
    if any(
        item.declaration.kind != "test"
        and fnmatch.fnmatchcase(PurePosixPath(item.declaration.path).name, pattern)
        for item in files
    ):
        raise ValueError("creator package hides a collected test as fixture material")
    root = repository_root.resolve()
    implementation = implementation_root.resolve()
    if not implementation.is_relative_to(root):
        raise ValueError("creator test root must remain within the Git repository")
    prefix = implementation.relative_to(root)
    source = provenance.git_provenance.provenance.source_revision
    base = assignment.base_revision
    for item in files:
        path = (prefix / item.declaration.path).as_posix()
        content = item.content
        if (
            _read_repository_file(root, path) != content
            or _git(
                git_executable, root, ["show", f"{base}:{path}"], limit=len(content)
            )
            != content
            or _git(
                git_executable, root, ["show", f"{source}:{path}"], limit=len(content)
            )
            != content
        ):
            raise ValueError("protected creator test changed across Git lineage")


def _preflight(
    *,
    approval: SignedG4FinalWholeSuiteApproval,
    candidate: G4CandidateDispatchReceipt,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    creator_request: ReviewerTestExecutionRequest,
    reviewer_request: ReviewerTestExecutionRequest,
    reviewer_binding: ImmutableImplementationBindingRecord,
    creator_package: FrozenReviewerTestPackage,
    reviewer_package: FrozenReviewerTestPackage,
    creator_package_path: Path,
    reviewer_package_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    candidate_dispatch_store: Path,
    final_dispatch_store: Path,
    now: datetime,
) -> None:
    root = repository_root.resolve()
    if any(
        path.resolve().is_relative_to(root)
        for path in (
            creator_package_path,
            reviewer_package_path,
            candidate_dispatch_store,
            final_dispatch_store,
        )
    ):
        raise ValueError("final-suite artifacts and state must remain outside Git")
    candidate_store = candidate_dispatch_store.resolve()
    final_store = final_dispatch_store.resolve()
    if (
        candidate_store == final_store
        or candidate_store.is_relative_to(final_store)
        or final_store.is_relative_to(candidate_store)
    ):
        raise ValueError("candidate and final-suite claims need separate stores")
    verify_candidate_dispatch_receipt(
        candidate,
        dispatch_store=candidate_dispatch_store,
        provenance=provenance,
        controls=controls,
        binding=reviewer_binding,
        package=reviewer_package,
        reviewer_package_path=reviewer_package_path,
        repository_root=root,
        implementation_root=implementation_root,
        git_executable=git_executable,
    )
    if not candidate.candidate_tests_passed:
        raise ValueError("final suites require a passing admitted candidate run")
    grant = approval.approval
    verify_provenance_signature(
        grant, approval.signature, provenance.policy, "creator", _APPROVAL_DOMAIN
    )
    if not (
        provenance.policy.valid_from
        <= grant.issued_at
        <= now
        < grant.expires_at
        <= provenance.policy.valid_until
    ):
        raise ValueError("final-suite approval is outside its valid window")
    if grant.issued_at < candidate.admission.admitted_at:
        raise ValueError("final-suite approval predates candidate admission")
    if (
        grant.policy_sha256 != provenance.policy.policy_sha256
        or grant.provenance_sha256 != provenance.record_sha256
        or grant.candidate_receipt_sha256 != candidate.receipt_sha256
        or grant.source_revision != provenance.git_provenance.provenance.source_revision
        or grant.creator_test_suite_sha256
        != provenance.creator_approval.approval.creator_test_suite_sha256
        or grant.creator_package_sha256 != creator_package.frozen_package_sha256
        or grant.reviewer_package_sha256 != reviewer_package.frozen_package_sha256
        or grant.reviewer_binding_sha256 != reviewer_binding.binding_record_sha256
        or grant.creator_request_sha256 != creator_request.request_sha256
        or grant.reviewer_request_sha256 != reviewer_request.request_sha256
        or grant.container_image_id != candidate.admission.request.container_image_id
        or creator_request.container_image_id != grant.container_image_id
        or reviewer_request.container_image_id != grant.container_image_id
        or creator_request.binding_record_sha256
        != reviewer_binding.binding_record_sha256
        or reviewer_request.binding_record_sha256
        != reviewer_binding.binding_record_sha256
        or creator_request.role != "candidate"
        or reviewer_request.role != "candidate"
        or creator_request.execution_id == reviewer_request.execution_id
    ):
        raise ValueError("final-suite approval does not bind exact current inputs")
    if reviewer_binding.payload.manifest.source_revision != grant.source_revision:
        raise ValueError("final suites require the exact Git implementation revision")
    if (
        decode_frozen_reviewer_test_package(
            read_bounded(creator_package_path, FROZEN_PACKAGE_BYTES)
        )
        != creator_package
    ):
        raise ValueError("creator package path differs from exact approved package")
    _verify_creator_package(
        creator_package, provenance, root, implementation_root, git_executable
    )


def _verify_reviewer_identities(
    candidate: G4CandidateDispatchReceipt,
    final: ImmutableReviewerTestExecutionReceipt,
) -> None:
    before = candidate.execution.observation
    after = final.observation
    if (
        before.collected_test_ids_sha256 != after.collected_test_ids_sha256
        or before.started_test_ids_sha256 != after.started_test_ids_sha256
        or before.executed_test_ids_sha256 != after.executed_test_ids_sha256
    ):
        raise ValueError("final reviewer suite executed different test identities")


def _claim(
    store: Path, candidate_sha256: str, approval: SignedG4FinalWholeSuiteApproval
) -> None:
    directory_fd = open_private_dispatch_store(store)
    try:
        fd = os.open(
            f"{candidate_sha256}.claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_bytes(approval))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _verify_claim(
    store: Path, candidate_sha256: str, approval: SignedG4FinalWholeSuiteApproval
) -> None:
    directory_fd = open_private_dispatch_store(store)
    try:
        fd = os.open(
            f"{candidate_sha256}.claim",
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size != len(canonical_bytes(approval))
                or stream.read(len(canonical_bytes(approval)) + 1)
                != canonical_bytes(approval)
            ):
                raise ValueError("final-suite claim differs from signed approval")
    finally:
        os.close(directory_fd)


def run_final_whole_suites(
    *,
    approval: SignedG4FinalWholeSuiteApproval,
    candidate: G4CandidateDispatchReceipt,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    creator_request: ReviewerTestExecutionRequest,
    reviewer_request: ReviewerTestExecutionRequest,
    reviewer_binding: ImmutableImplementationBindingRecord,
    creator_package: FrozenReviewerTestPackage,
    reviewer_package: FrozenReviewerTestPackage,
    creator_package_path: Path,
    reviewer_package_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    candidate_dispatch_store: Path,
    final_dispatch_store: Path,
    container: OfflineContainer,
    now: datetime | None = None,
) -> G4FinalWholeSuiteReceipt:
    """Consume one approval and execute both exact suites in the isolated image."""
    started = _utc(now if now is not None else datetime.now(UTC))
    inputs = _PreflightInputs(
        approval=approval,
        candidate=candidate,
        provenance=provenance,
        controls=controls,
        creator_request=creator_request,
        reviewer_request=reviewer_request,
        reviewer_binding=reviewer_binding,
        creator_package=creator_package,
        reviewer_package=reviewer_package,
        creator_package_path=creator_package_path,
        reviewer_package_path=reviewer_package_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        candidate_dispatch_store=candidate_dispatch_store,
        final_dispatch_store=final_dispatch_store,
        now=started,
    )
    _preflight(**inputs)
    if container.image_id != approval.approval.container_image_id:
        raise ValueError("final-suite container differs from approved image")
    _claim(final_dispatch_store, candidate.receipt_sha256, approval)
    creator_execution = execute_isolated_creator_tests_in_trusted_host(
        creator_request,
        reviewer_binding,
        creator_package_path,
        reviewer_package_path,
        implementation_root,
        container,
    )
    reviewer_execution = execute_isolated_reviewer_tests_in_trusted_host(
        reviewer_request,
        reviewer_binding,
        reviewer_package_path,
        implementation_root,
        container,
    )
    _verify_reviewer_identities(candidate, reviewer_execution)
    _preflight(**inputs)
    return G4FinalWholeSuiteReceipt(
        approval=approval,
        candidate_receipt_sha256=candidate.receipt_sha256,
        source_revision=approval.approval.source_revision,
        creator_execution=creator_execution,
        reviewer_execution=reviewer_execution,
        started_at=started,
        final_suites_passed=(
            creator_execution.role_expectation_satisfied
            and reviewer_execution.role_expectation_satisfied
        ),
    )


def verify_final_whole_suite_receipt(
    receipt: G4FinalWholeSuiteReceipt,
    *,
    candidate: G4CandidateDispatchReceipt,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    reviewer_binding: ImmutableImplementationBindingRecord,
    creator_package: FrozenReviewerTestPackage,
    reviewer_package: FrozenReviewerTestPackage,
    creator_package_path: Path,
    reviewer_package_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    candidate_dispatch_store: Path,
    final_dispatch_store: Path,
) -> None:
    _preflight(
        approval=receipt.approval,
        candidate=candidate,
        provenance=provenance,
        controls=controls,
        creator_request=receipt.creator_execution.request,
        reviewer_request=receipt.reviewer_execution.request,
        reviewer_binding=reviewer_binding,
        creator_package=creator_package,
        reviewer_package=reviewer_package,
        creator_package_path=creator_package_path,
        reviewer_package_path=reviewer_package_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        candidate_dispatch_store=candidate_dispatch_store,
        final_dispatch_store=final_dispatch_store,
        now=receipt.started_at,
    )
    _verify_claim(final_dispatch_store, candidate.receipt_sha256, receipt.approval)
    verify_creator_test_execution_receipt(
        receipt.creator_execution,
        reviewer_binding,
        creator_package_path,
        reviewer_package_path,
        implementation_root,
    )
    verify_execution_receipt(
        receipt.reviewer_execution,
        receipt.reviewer_execution.request,
        reviewer_binding,
        reviewer_package_path,
        implementation_root,
    )
    _verify_reviewer_identities(candidate, receipt.reviewer_execution)


def decode_final_suite_artifact[T: Contract](payload: bytes, model: type[T]) -> T:
    if len(payload) > FINAL_SUITE_ARTIFACT_BYTES:
        raise ValueError("final-suite artifact exceeds 4 MB")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        value = model.model_validate_json(payload)
        if payload != canonical_bytes(value):
            raise ValueError("final-suite artifact must be canonical")
        return value
    except (ValueError, RecursionError):
        raise ValueError("invalid final-suite artifact") from None


def decode_creator_job(payload: bytes) -> IsolatedCreatorTestJob:
    if len(payload) > MAX_WIRE_BYTES:
        raise ValueError("creator-test job exceeds the wire limit")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        job = IsolatedCreatorTestJob.model_validate_json(payload)
        if canonical_bytes(job) != payload:
            raise ValueError("creator-test job must be canonical")
        return job
    except (ValueError, RecursionError):
        raise ValueError("invalid creator-test job") from None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result
