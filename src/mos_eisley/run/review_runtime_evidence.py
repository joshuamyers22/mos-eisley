"""Private host measurements for independent review; never provider attestation."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest
from mos_eisley.providers.openai_responses import request_payload
from mos_eisley.providers.openai_spend import count_payload, spending_request_sha256
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_conformance_authorization import (
    ImageID,
    ReviewConformanceAuthorization,
)
from mos_eisley.run.review_conformance_observation import ReviewObservedExchange
from mos_eisley.run.store import private_write
from mos_eisley.run.watchdog import CleanupLease, CleanupRecord

Operation = Literal["count", "generation"]


class RuntimeOperationStart(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_runtime_operation"] = "review_runtime_operation"
    operation: Operation
    model_request_sha256: Digest
    authorization_sha256: Digest
    payload_sha256: Digest
    started_at: datetime
    sdk_version: Identifier
    image_id: ImageID
    container_id: Digest | None
    cleanup_lease_sha256: Digest | None
    host_record_only: Literal[True] = True

    @model_validator(mode="after")
    def valid_start(self) -> Self:
        if self.started_at.tzinfo is None or self.started_at.utcoffset() != timedelta(
            0
        ):
            raise ValueError("runtime evidence requires UTC timestamps")
        if (self.container_id is None) != (self.cleanup_lease_sha256 is None):
            raise ValueError("runtime evidence requires both cleanup bindings")
        return self


class RuntimeOperationEnd(Contract):
    schema_version: Literal[1] = 1
    start_sha256: Digest
    status: Literal["returned", "failed", "cancelled"]
    finished_at: datetime
    duration_ms: Annotated[int, Field(ge=0)]
    result_sha256: Digest | None = None
    input_tokens: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def valid_end(self) -> Self:
        if self.finished_at.tzinfo is None or self.finished_at.utcoffset() != timedelta(
            0
        ):
            raise ValueError("runtime evidence requires UTC timestamps")
        if (self.status == "returned") != (self.result_sha256 is not None):
            raise ValueError("runtime result must match returned status")
        if self.status != "returned" and self.input_tokens is not None:
            raise ValueError("failed runtime operation cannot claim a token count")
        return self


class RuntimeTransportEvidence(Contract):
    count_start: RuntimeOperationStart
    count_end: RuntimeOperationEnd
    generation_start: RuntimeOperationStart
    generation_end: RuntimeOperationEnd


class RuntimeCleanupEvidence(Contract):
    lease: CleanupLease
    result: CleanupRecord


class RuntimeOperationRecorder:
    """A begin record precedes SDK use; an interrupted record never implies success."""

    def __init__(
        self,
        directory: Path,
        operation: Operation,
        request: ModelRequest,
        authorization: ReviewConformanceAuthorization,
        payload: dict[str, JsonValue],
        container: OfflineContainer,
    ) -> None:
        lease = None
        if container.lifecycle_path is not None:
            lease = CleanupLease.model_validate_json(
                read_bounded(container.lifecycle_path / "lease.json", 4096)
            )
        self.start = RuntimeOperationStart(
            operation=operation,
            model_request_sha256=digest(canonical_bytes(request)),
            authorization_sha256=digest(canonical_bytes(authorization)),
            payload_sha256=spending_request_sha256(payload),
            started_at=datetime.now(UTC),
            sdk_version=authorization.scope.sdk_version,
            image_id=container.image_id,
            container_id=None if lease is None else lease.container_id,
            cleanup_lease_sha256=None
            if lease is None
            else digest(canonical_bytes(lease)),
        )
        self._directory = directory
        self._monotonic = monotonic()
        private_write(
            directory / f"runtime-{operation}-start.json", canonical_bytes(self.start)
        )

    def finish(self, result: int | dict[str, JsonValue] | BaseException) -> None:
        failed = isinstance(result, BaseException)
        if isinstance(result, BaseException):
            result_sha = None
        elif isinstance(result, int):
            if type(result) is not int or result < 0:
                raise ValueError("runtime token count must be a nonnegative integer")
            result_sha = spending_request_sha256({"input_tokens": result})
        else:
            result_sha = spending_request_sha256(result)
        end = RuntimeOperationEnd(
            start_sha256=digest(canonical_bytes(self.start)),
            status="cancelled"
            if isinstance(result, asyncio.CancelledError)
            else "failed"
            if failed
            else "returned",
            finished_at=datetime.now(UTC),
            duration_ms=max(0, int((monotonic() - self._monotonic) * 1000)),
            result_sha256=result_sha,
            input_tokens=result if type(result) is int else None,
        )
        private_write(
            self._directory / f"runtime-{self.start.operation}-end.json",
            canonical_bytes(end),
        )


def collect_review_runtime_exchange(
    directory: Path,
    lifecycle_directory: Path,
    request: ModelRequest,
    authorization: ReviewConformanceAuthorization,
) -> ReviewObservedExchange:
    """Check stopped host records against trusted call/context and cleanup selection.

    The resulting pins cover local evidence only. An independent observer must
    inspect actual runtime before signing any credentialed exchange attestation.
    """
    if directory.is_symlink() or lifecycle_directory.is_symlink():
        raise ValueError("runtime evidence directories must not be symlinks")
    request = ModelRequest.model_validate_json(canonical_bytes(request))
    authorization = ReviewConformanceAuthorization.model_validate_json(
        canonical_bytes(authorization)
    )
    evidence = RuntimeTransportEvidence(
        count_start=RuntimeOperationStart.model_validate_json(
            read_bounded(directory / "runtime-count-start.json", 4096)
        ),
        count_end=RuntimeOperationEnd.model_validate_json(
            read_bounded(directory / "runtime-count-end.json", 4096)
        ),
        generation_start=RuntimeOperationStart.model_validate_json(
            read_bounded(directory / "runtime-generation-start.json", 4096)
        ),
        generation_end=RuntimeOperationEnd.model_validate_json(
            read_bounded(directory / "runtime-generation-end.json", 4096)
        ),
    )
    cleanup = RuntimeCleanupEvidence(
        lease=CleanupLease.model_validate_json(
            read_bounded(lifecycle_directory / "lease.json", 4096)
        ),
        result=CleanupRecord.model_validate_json(
            read_bounded(lifecycle_directory / "result.json", 4096)
        ),
    )
    lease_sha = digest(canonical_bytes(cleanup.lease))
    if (
        cleanup.result.state != "removed"
        or cleanup.result.attempts < 1
        or cleanup.result.lease_sha256 != lease_sha
        or cleanup.result.container_id != cleanup.lease.container_id
    ):
        raise ValueError("runtime worker cleanup is incomplete or mismatched")
    payload = request_payload(request)
    payload["service_tier"] = "default"
    for operation, start, end in (
        ("count", evidence.count_start, evidence.count_end),
        ("generation", evidence.generation_start, evidence.generation_end),
    ):
        expected_payload = count_payload(payload) if operation == "count" else payload
        if (
            start.operation != operation
            or start.model_request_sha256 != digest(canonical_bytes(request))
            or start.authorization_sha256 != digest(canonical_bytes(authorization))
            or start.payload_sha256 != spending_request_sha256(expected_payload)
            or start.sdk_version != authorization.scope.sdk_version
            or start.image_id != authorization.scope.image_id
            or start.container_id != cleanup.lease.container_id
            or start.cleanup_lease_sha256 != lease_sha
            or end.start_sha256 != digest(canonical_bytes(start))
            or end.status != "returned"
            or not authorization.issued_at
            <= start.started_at
            <= end.finished_at
            < authorization.valid_until
            or end.duration_ms > 60_000
        ):
            raise ValueError("runtime operation differs from its approved exchange")
    tokens = evidence.count_end.input_tokens
    if (
        tokens is None
        or evidence.count_end.result_sha256
        != spending_request_sha256({"input_tokens": tokens})
        or evidence.generation_end.input_tokens is not None
    ):
        raise ValueError("runtime evidence token-count result is inconsistent")
    # The broker wraps the exact returned SDK payload; validate that binding without
    # exporting response prose or credentials into the observer-facing record.
    response = BrokerReply.model_validate_json(
        read_bounded(directory / "broker-response.json")
    )
    if (
        spending_request_sha256(response.response)
        != evidence.generation_end.result_sha256
    ):
        raise ValueError("runtime evidence differs from retained provider response")
    return ReviewObservedExchange(
        model_request_sha256=digest(canonical_bytes(request)),
        count_started_at=evidence.count_start.started_at,
        count_finished_at=evidence.count_end.finished_at,
        generation_started_at=evidence.generation_start.started_at,
        generation_finished_at=evidence.generation_end.finished_at,
        transport_evidence_sha256=digest(canonical_bytes(evidence)),
        cleanup_evidence_sha256=digest(canonical_bytes(cleanup)),
    )


def verify_review_runtime_exchange(
    expected: ReviewObservedExchange,
    directory: Path,
    lifecycle_directory: Path,
    request: ModelRequest,
    authorization: ReviewConformanceAuthorization,
) -> None:
    """Recheck an independently pinned observer exchange against local evidence."""
    collected = collect_review_runtime_exchange(
        directory, lifecycle_directory, request, authorization
    )
    if canonical_bytes(collected) != canonical_bytes(expected):
        raise ValueError("runtime evidence differs from the pinned observer exchange")
