"""Bounded isolated execution and immutable count evidence for G4 reviewer tests."""

from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_implementation_binding import (
    BINDING_RECORD_BYTES,
    ImmutableImplementationBindingRecord,
    ImplementationFileDeclaration,
    decode_implementation_binding_record,
    snapshot_implementation_files,
    verify_implementation_binding_record,
)
from mos_eisley.reviewer_test_package import (
    FROZEN_PACKAGE_BYTES,
    FrozenReviewerTestPackage,
    TestCollectionContract,
    decode_frozen_reviewer_test_package,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import MAX_WIRE_BYTES, OfflineContainer

EXECUTION_REQUEST_BYTES = 64_000
EXECUTION_RECEIPT_BYTES = 1_000_000
CONTROL_RECORD_BYTES = 2_000_000
MAX_TEST_OUTPUT_BYTES = 65_536
MAX_TEST_ID_BYTES = 1_000_000

ExecutionRole = Literal["candidate", "known_good", "known_bad"]
ContainerImageId = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
EncodedImplementationFile = Annotated[str, Field(min_length=4, max_length=2_666_668)]
Count = Annotated[int, Field(ge=0, le=10_000)]


class ReviewerTestExecutionRequest(Contract):
    """Explicit request for one bounded run; no later authority is implied."""

    schema_version: Literal[1] = 1
    kind: Literal["reviewer_test_execution_request"] = "reviewer_test_execution_request"
    execution_id: Identifier
    binding_record_sha256: Digest
    container_image_id: ContainerImageId
    role: ExecutionRole
    timeout_seconds: Annotated[int, Field(ge=5, le=60)] = 30
    test_execution_requested: Literal[True] = True
    repository_write_authorized: Literal[False] = False
    vcs_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded_request(self) -> Self:
        if len(canonical_bytes(self)) > EXECUTION_REQUEST_BYTES:
            raise ValueError("reviewer-test execution request exceeds 64 KB")
        return self

    @property
    def request_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ExecutionImplementationFile(Contract):
    declaration: ImplementationFileDeclaration
    content_base64: EncodedImplementationFile

    @model_validator(mode="after")
    def exact_content(self) -> Self:
        if self.declaration.kind not in {
            "implementation_source",
            "implementation_resource",
        }:
            raise ValueError("execution material may contain only source-root files")
        try:
            payload = base64.b64decode(self.content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("execution material must use canonical base64") from None
        if base64.b64encode(payload).decode("ascii") != self.content_base64:
            raise ValueError("execution material must use canonical base64")
        if (
            len(payload) != self.declaration.bytes
            or digest(payload) != self.declaration.content_sha256
        ):
            raise ValueError("execution material differs from its declaration")
        return self

    @property
    def content(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class IsolatedReviewerTestJob(Contract):
    """Self-contained stdin payload for the immutable no-mount worker."""

    schema_version: Literal[1] = 1
    kind: Literal["isolated_reviewer_test_job"] = "isolated_reviewer_test_job"
    request: ReviewerTestExecutionRequest
    binding: ImmutableImplementationBindingRecord
    reviewer_package: FrozenReviewerTestPackage
    implementation_files: Annotated[
        tuple[ExecutionImplementationFile, ...], Field(min_length=1, max_length=2048)
    ]

    @model_validator(mode="after")
    def exact_bound_material(self) -> Self:
        if self.request.binding_record_sha256 != self.binding.binding_record_sha256:
            raise ValueError("execution request names a different binding record")
        if self.reviewer_package.frozen_package_sha256 != (
            self.binding.payload.frozen_reviewer_test_package_sha256
        ):
            raise ValueError(
                "execution package differs from the implementation binding"
            )
        expected = tuple(
            item
            for item in self.binding.payload.manifest.files
            if item.kind in {"implementation_source", "implementation_resource"}
        )
        actual = tuple(item.declaration for item in self.implementation_files)
        if actual != expected:
            raise ValueError("execution material differs from the bound source roots")
        if len(canonical_bytes(self)) > MAX_WIRE_BYTES:
            raise ValueError("isolated reviewer-test job exceeds the 16 MB wire limit")
        return self

    @property
    def job_sha256(self) -> str:
        return digest(canonical_bytes(self))


class IsolatedReviewerTestObservation(Contract):
    """Bounded worker observation; the host binds it to current inputs."""

    schema_version: Literal[1] = 1
    kind: Literal["isolated_reviewer_test_observation"] = (
        "isolated_reviewer_test_observation"
    )
    job_sha256: Digest
    collected_tests: Count
    started_tests: Count
    executed_tests: Count
    skipped_tests: Count
    failures: Count
    errors: Count
    expected_failures: Count
    unexpected_successes: Count
    collected_test_ids_sha256: Digest
    started_test_ids_sha256: Digest
    executed_test_ids_sha256: Digest
    output_bytes: Annotated[int, Field(ge=0, le=MAX_TEST_OUTPUT_BYTES)]
    suite_successful: bool

    @model_validator(mode="after")
    def coherent_observation(self) -> Self:
        if self.executed_tests + self.skipped_tests != self.started_tests:
            raise ValueError(
                "executed and skipped observations must equal started tests"
            )
        classified = (
            self.failures
            + self.errors
            + self.expected_failures
            + self.unexpected_successes
        )
        if classified > self.executed_tests:
            raise ValueError("test outcomes exceed executed tests")
        expected_success = not (
            self.failures or self.errors or self.unexpected_successes
        )
        if self.suite_successful != expected_success:
            raise ValueError("suite success differs from observed outcomes")
        return self


class ImmutableReviewerTestExecutionReceipt(Contract):
    """Exact execution/count evidence; never correction or acceptance authority."""

    schema_version: Literal[1] = 1
    kind: Literal["immutable_reviewer_test_execution_receipt"] = (
        "immutable_reviewer_test_execution_receipt"
    )
    request: ReviewerTestExecutionRequest
    request_sha256: Digest
    binding_record_sha256: Digest
    frozen_reviewer_test_package_sha256: Digest
    reviewer_test_payload_sha256: Digest
    implementation_tree_sha256: Digest
    adapter_sha256: Digest
    collection: TestCollectionContract
    collection_sha256: Digest
    job_sha256: Digest
    observation: IsolatedReviewerTestObservation
    inputs_reverified_after_execution: Literal[True] = True
    collection_contract_satisfied: bool
    role_expectation_satisfied: bool
    test_execution_completed: Literal[True] = True
    repository_write_authorized: Literal[False] = False
    vcs_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_receipt(self) -> Self:
        if self.request_sha256 != self.request.request_sha256:
            raise ValueError("execution request digest is invalid")
        if self.binding_record_sha256 != self.request.binding_record_sha256:
            raise ValueError("receipt binding differs from the request")
        if self.collection_sha256 != digest(canonical_bytes(self.collection)):
            raise ValueError("collection contract digest is invalid")
        if self.observation.job_sha256 != self.job_sha256:
            raise ValueError("worker observation names a different job")
        observed = self.observation
        counts_match = (
            observed.collected_tests == self.collection.expected_collected_tests
            and observed.started_tests == self.collection.expected_collected_tests
            and observed.executed_tests == self.collection.expected_executed_tests
            and observed.skipped_tests == self.collection.expected_skipped_tests
        )
        if self.collection_contract_satisfied != counts_match:
            raise ValueError("collection-contract result differs from observed counts")
        if self.request.role == "known_bad":
            role_match = (
                counts_match
                and not observed.suite_successful
                and observed.failures > 0
                and observed.errors == 0
                and observed.unexpected_successes == 0
            )
        else:
            role_match = counts_match and observed.suite_successful
        if self.role_expectation_satisfied != role_match:
            raise ValueError("role expectation differs from observed outcomes")
        if len(canonical_bytes(self)) > EXECUTION_RECEIPT_BYTES:
            raise ValueError("reviewer-test execution receipt exceeds 1 MB")
        return self

    @property
    def receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


class KnownControlValidationRecord(Contract):
    """Paired sensitivity/specificity evidence with no candidate authority."""

    schema_version: Literal[1] = 1
    kind: Literal["reviewer_test_known_control_validation"] = (
        "reviewer_test_known_control_validation"
    )
    known_good: ImmutableReviewerTestExecutionReceipt
    known_bad: ImmutableReviewerTestExecutionReceipt
    frozen_reviewer_test_package_sha256: Digest
    adapter_sha256: Digest
    container_image_id: ContainerImageId
    collection_sha256: Digest
    controls_validated: Literal[True] = True
    candidate_execution_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_controls(self) -> Self:
        good = self.known_good
        bad = self.known_bad
        if good.request.role != "known_good" or bad.request.role != "known_bad":
            raise ValueError("control receipts require known-good and known-bad roles")
        if good.request.execution_id == bad.request.execution_id:
            raise ValueError("known controls require distinct execution ids")
        if good.binding_record_sha256 == bad.binding_record_sha256:
            raise ValueError("known controls require distinct implementation bindings")
        if good.implementation_tree_sha256 == bad.implementation_tree_sha256:
            raise ValueError("known controls require distinct implementation trees")
        if not good.role_expectation_satisfied or not bad.role_expectation_satisfied:
            raise ValueError("known-control role expectation failed")
        same_values = (
            good.frozen_reviewer_test_package_sha256,
            good.adapter_sha256,
            good.request.container_image_id,
            good.collection_sha256,
        )
        if same_values != (
            bad.frozen_reviewer_test_package_sha256,
            bad.adapter_sha256,
            bad.request.container_image_id,
            bad.collection_sha256,
        ):
            raise ValueError(
                "known controls must share package, adapter, image and counts"
            )
        if self.frozen_reviewer_test_package_sha256 != same_values[0]:
            raise ValueError("control package identity is invalid")
        if self.adapter_sha256 != same_values[1]:
            raise ValueError("control adapter identity is invalid")
        if self.container_image_id != same_values[2]:
            raise ValueError("control image identity is invalid")
        if self.collection_sha256 != same_values[3]:
            raise ValueError("control collection identity is invalid")
        good_observation = good.observation
        bad_observation = bad.observation
        if (
            good_observation.collected_test_ids_sha256
            != bad_observation.collected_test_ids_sha256
            or good_observation.started_test_ids_sha256
            != bad_observation.started_test_ids_sha256
            or good_observation.executed_test_ids_sha256
            != bad_observation.executed_test_ids_sha256
        ):
            raise ValueError("known controls executed different test identities")
        if len(canonical_bytes(self)) > CONTROL_RECORD_BYTES:
            raise ValueError("known-control validation record exceeds 2 MB")
        return self

    @property
    def control_record_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _decode_contract[T: Contract](payload: bytes, model: type[T], limit: int) -> T:
    if len(payload) > limit:
        raise ValueError("G4 execution artifact exceeds its byte limit")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        value = model.model_validate_json(payload)
        if payload != canonical_bytes(value):
            raise ValueError("G4 execution artifact must be canonical")
        return value
    except (ValueError, RecursionError):
        raise ValueError("invalid G4 execution artifact") from None


def decode_execution_request(payload: bytes) -> ReviewerTestExecutionRequest:
    return _decode_contract(
        payload, ReviewerTestExecutionRequest, EXECUTION_REQUEST_BYTES
    )


def decode_execution_job(payload: bytes) -> IsolatedReviewerTestJob:
    return _decode_contract(payload, IsolatedReviewerTestJob, MAX_WIRE_BYTES)


def decode_execution_observation(payload: bytes) -> IsolatedReviewerTestObservation:
    return _decode_contract(payload, IsolatedReviewerTestObservation, 256_000)


def decode_execution_receipt(
    payload: bytes,
) -> ImmutableReviewerTestExecutionReceipt:
    return _decode_contract(
        payload, ImmutableReviewerTestExecutionReceipt, EXECUTION_RECEIPT_BYTES
    )


def decode_control_record(payload: bytes) -> KnownControlValidationRecord:
    return _decode_contract(payload, KnownControlValidationRecord, CONTROL_RECORD_BYTES)


def build_isolated_reviewer_test_job(
    request: ReviewerTestExecutionRequest,
    binding: ImmutableImplementationBindingRecord,
    reviewer_package_path: Path,
    implementation_root: Path,
) -> IsolatedReviewerTestJob:
    if request.binding_record_sha256 != binding.binding_record_sha256:
        raise ValueError("execution request names a different binding record")
    verify_implementation_binding_record(
        binding, reviewer_package_path, implementation_root
    )
    package_bytes = read_bounded(reviewer_package_path, FROZEN_PACKAGE_BYTES)
    package = decode_frozen_reviewer_test_package(package_bytes)
    if package_bytes != canonical_bytes(package):
        raise ValueError("frozen reviewer-test package must use canonical encoding")
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
    job = IsolatedReviewerTestJob(
        request=request,
        binding=binding,
        reviewer_package=package,
        implementation_files=material,
    )
    verify_implementation_binding_record(
        binding, reviewer_package_path, implementation_root
    )
    return job


def run_isolated_reviewer_tests(
    request: ReviewerTestExecutionRequest,
    binding: ImmutableImplementationBindingRecord,
    reviewer_package_path: Path,
    implementation_root: Path,
    container: OfflineContainer,
) -> ImmutableReviewerTestExecutionReceipt:
    """Execute known controls; candidates require the separate G4 admission gate."""
    if request.role == "candidate":
        raise ValueError("candidate execution requires authenticated G4 admission")
    return execute_isolated_reviewer_tests_in_trusted_host(
        request, binding, reviewer_package_path, implementation_root, container
    )


def execute_isolated_reviewer_tests_in_trusted_host(
    request: ReviewerTestExecutionRequest,
    binding: ImmutableImplementationBindingRecord,
    reviewer_package_path: Path,
    implementation_root: Path,
    container: OfflineContainer,
) -> ImmutableReviewerTestExecutionReceipt:
    """Execute one exact request only through the immutable no-mount container."""
    if container.image_id != request.container_image_id:
        raise ValueError("container image differs from the execution request")
    job = build_isolated_reviewer_test_job(
        request, binding, reviewer_package_path, implementation_root
    )
    response = container.execute(
        ("-m", "mos_eisley.run.reviewer_test_worker"),
        canonical_bytes(job),
        timeout=float(request.timeout_seconds),
    )
    observation = decode_execution_observation(response)
    if observation.job_sha256 != job.job_sha256:
        raise ValueError("isolated worker observed a different execution job")
    current = build_isolated_reviewer_test_job(
        request, binding, reviewer_package_path, implementation_root
    )
    if current != job:
        raise ValueError("execution inputs changed during isolated execution")
    collection = job.reviewer_package.payload.manifest.collection
    observed = observation
    counts_match = (
        observed.collected_tests == collection.expected_collected_tests
        and observed.started_tests == collection.expected_collected_tests
        and observed.executed_tests == collection.expected_executed_tests
        and observed.skipped_tests == collection.expected_skipped_tests
    )
    if request.role == "known_bad":
        role_match = (
            counts_match
            and not observed.suite_successful
            and observed.failures > 0
            and observed.errors == 0
            and observed.unexpected_successes == 0
        )
    else:
        role_match = counts_match and observed.suite_successful
    return ImmutableReviewerTestExecutionReceipt(
        request=request,
        request_sha256=request.request_sha256,
        binding_record_sha256=binding.binding_record_sha256,
        frozen_reviewer_test_package_sha256=(
            binding.payload.frozen_reviewer_test_package_sha256
        ),
        reviewer_test_payload_sha256=binding.payload.reviewer_test_payload_sha256,
        implementation_tree_sha256=binding.payload.implementation_tree_sha256,
        adapter_sha256=binding.payload.adapter_sha256,
        collection=collection,
        collection_sha256=digest(canonical_bytes(collection)),
        job_sha256=job.job_sha256,
        observation=observation,
        collection_contract_satisfied=counts_match,
        role_expectation_satisfied=role_match,
    )


def verify_execution_receipt(
    receipt: ImmutableReviewerTestExecutionReceipt,
    request: ReviewerTestExecutionRequest,
    binding: ImmutableImplementationBindingRecord,
    reviewer_package_path: Path,
    implementation_root: Path,
) -> None:
    if receipt.request != request:
        raise ValueError("execution receipt differs from the current request")
    job = build_isolated_reviewer_test_job(
        request, binding, reviewer_package_path, implementation_root
    )
    if (
        receipt.binding_record_sha256 != binding.binding_record_sha256
        or receipt.job_sha256 != job.job_sha256
        or receipt.frozen_reviewer_test_package_sha256
        != job.reviewer_package.frozen_package_sha256
        or receipt.reviewer_test_payload_sha256 != job.reviewer_package.payload_sha256
        or receipt.implementation_tree_sha256
        != binding.payload.implementation_tree_sha256
        or receipt.adapter_sha256 != binding.payload.adapter_sha256
    ):
        raise ValueError("execution receipt differs from current bound inputs")


def validate_known_controls(
    known_good: ImmutableReviewerTestExecutionReceipt,
    known_bad: ImmutableReviewerTestExecutionReceipt,
) -> KnownControlValidationRecord:
    return KnownControlValidationRecord(
        known_good=known_good,
        known_bad=known_bad,
        frozen_reviewer_test_package_sha256=(
            known_good.frozen_reviewer_test_package_sha256
        ),
        adapter_sha256=known_good.adapter_sha256,
        container_image_id=known_good.request.container_image_id,
        collection_sha256=known_good.collection_sha256,
    )


def load_binding(path: Path) -> ImmutableImplementationBindingRecord:
    return decode_implementation_binding_record(
        read_bounded(path, BINDING_RECORD_BYTES)
    )
