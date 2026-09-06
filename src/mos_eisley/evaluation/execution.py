"""Label-blind evaluation requests and request-bound recorded execution."""

from __future__ import annotations

import hashlib
import hmac
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Brief,
    Contract,
    Critique,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.evaluation.models import (
    MAX_ASSIGNMENTS,
    EvaluationDataset,
    FailureKind,
    RouteCandidate,
    Split,
    SweepPlan,
)


class EvaluationRequest(Contract):
    """The complete object visible to an evaluation backend."""

    schema_version: Literal[2] = 2
    sample_id: Digest
    route: RouteCandidate
    brief: Brief

    @property
    def request_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ExecutionBatch(Contract):
    schema_version: Literal[2] = 2
    plan_sha256: Digest
    requests: Annotated[
        tuple[EvaluationRequest, ...], Field(min_length=1, max_length=MAX_ASSIGNMENTS)
    ]

    @model_validator(mode="after")
    def unique_samples(self) -> Self:
        sample_ids = tuple(request.sample_id for request in self.requests)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("execution sample ids must be unique")
        return self

    @property
    def batch_sha256(self) -> str:
        return digest(canonical_bytes(self))


class BlindingEntry(Contract):
    sample_id: Digest
    case_id: Identifier
    candidate_id: Digest
    repetition: Annotated[int, Field(ge=0, lt=100)]
    request_sha256: Digest

    @property
    def assignment_key(self) -> tuple[str, str, int]:
        return (self.case_id, self.candidate_id, self.repetition)


class BlindingMap(Contract):
    schema_version: Literal[1] = 1
    plan_sha256: Digest
    dataset_sha256: Digest
    batch_sha256: Digest
    split: Split
    nonce_sha256: Digest
    entries: Annotated[
        tuple[BlindingEntry, ...], Field(min_length=1, max_length=MAX_ASSIGNMENTS)
    ]

    @model_validator(mode="after")
    def unique_entries(self) -> Self:
        samples = tuple(entry.sample_id for entry in self.entries)
        assignments = tuple(entry.assignment_key for entry in self.entries)
        if len(samples) != len(set(samples)):
            raise ValueError("blinding map sample ids must be unique")
        if len(assignments) != len(set(assignments)):
            raise ValueError("blinding map assignments must be unique")
        return self

    @property
    def mapping_sha256(self) -> str:
        return digest(canonical_bytes(self))


class RecordedExchange(Contract):
    request_sha256: Digest
    response: Critique | None = None
    error: FailureKind | None = None
    latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]
    cost_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000_000)] | None = None

    @model_validator(mode="after")
    def exactly_one_outcome(self) -> Self:
        if (self.response is None) == (self.error is None):
            raise ValueError("recorded exchange requires exactly one outcome")
        return self


class EvaluationCassette(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["recorded_evaluation"] = "recorded_evaluation"
    batch_sha256: Digest
    exchanges: Annotated[
        tuple[RecordedExchange, ...], Field(min_length=1, max_length=MAX_ASSIGNMENTS)
    ]

    @model_validator(mode="after")
    def unique_requests(self) -> Self:
        request_ids = tuple(exchange.request_sha256 for exchange in self.exchanges)
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("evaluation cassette requests must be unique")
        return self

    @property
    def cassette_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ExecutorProvenance(Contract):
    mode: Literal["recorded_fixture"] = "recorded_fixture"
    implementation: Identifier
    version: Annotated[str, Field(min_length=1, max_length=200)]
    cassette_sha256: Digest


class RawResult(Contract):
    sample_id: Digest
    candidate_id: Digest
    request_sha256: Digest
    status: Literal["completed", "error"]
    critique: Critique | None = None
    error: FailureKind | None = None
    latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]
    cost_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000_000)] | None = None

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if self.status == "completed" and (
            self.critique is None or self.error is not None
        ):
            raise ValueError("completed raw result requires a critique")
        if self.status == "error" and (self.critique is not None or self.error is None):
            raise ValueError("error raw result requires an error")
        return self


class RawResultSet(Contract):
    schema_version: Literal[1] = 1
    batch_sha256: Digest
    executor: ExecutorProvenance
    results: Annotated[
        tuple[RawResult, ...], Field(min_length=1, max_length=MAX_ASSIGNMENTS)
    ]

    @model_validator(mode="after")
    def unique_results(self) -> Self:
        sample_ids = tuple(result.sample_id for result in self.results)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("raw evaluation results must have unique sample ids")
        return self

    @property
    def raw_results_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _blind_sample_id(nonce: bytes, plan_sha256: str, assignment_key: str) -> str:
    message = f"{plan_sha256}\0{assignment_key}".encode()
    return hmac.new(nonce, message, hashlib.sha256).hexdigest()


def make_execution_batch(
    plan: SweepPlan,
    dataset: EvaluationDataset,
    split: Split,
    nonce: bytes,
) -> tuple[ExecutionBatch, BlindingMap]:
    """Project labeled cases into backend-visible requests and a private join map."""
    if len(nonce) != 32:
        raise ValueError("blinding nonce must contain exactly 32 bytes")
    plan.validate_dataset(dataset)
    cases = {case.id: case for case in dataset.cases}
    routes = {route.candidate_id: route for route in plan.routes}
    requests: list[EvaluationRequest] = []
    partial_entries: list[tuple[str, str, str, int, str]] = []
    for assignment in plan.assignments:
        if assignment.split != split:
            continue
        assignment_key = (
            f"{assignment.case_id}\0{assignment.candidate_id}\0{assignment.repetition}"
        )
        sample_id = _blind_sample_id(nonce, plan.plan_sha256, assignment_key)
        request = EvaluationRequest(
            sample_id=sample_id,
            route=routes[assignment.candidate_id],
            brief=cases[assignment.case_id].brief,
        )
        requests.append(request)
        partial_entries.append(
            (
                sample_id,
                assignment.case_id,
                assignment.candidate_id,
                assignment.repetition,
                request.request_sha256,
            )
        )
    batch = ExecutionBatch(plan_sha256=plan.plan_sha256, requests=tuple(requests))
    mapping = BlindingMap(
        plan_sha256=plan.plan_sha256,
        dataset_sha256=dataset.dataset_sha256,
        batch_sha256=batch.batch_sha256,
        split=split,
        nonce_sha256=digest(nonce),
        entries=tuple(
            BlindingEntry(
                sample_id=sample_id,
                case_id=case_id,
                candidate_id=candidate_id,
                repetition=repetition,
                request_sha256=request_sha256,
            )
            for (
                sample_id,
                case_id,
                candidate_id,
                repetition,
                request_sha256,
            ) in partial_entries
        ),
    )
    return batch, mapping


def run_recorded_evaluation(
    batch: ExecutionBatch,
    cassette: EvaluationCassette,
    implementation: str = "mos-eisley",
    version: str = "0.1.0",
) -> RawResultSet:
    """Execute a label-blind batch against exact request-bound offline fixtures."""
    if cassette.batch_sha256 != batch.batch_sha256:
        raise ValueError("cassette does not match the execution batch")
    exchanges = {exchange.request_sha256: exchange for exchange in cassette.exchanges}
    expected = {request.request_sha256 for request in batch.requests}
    if set(exchanges) != expected:
        raise ValueError("cassette does not exactly cover the execution batch")
    results: list[RawResult] = []
    for request in batch.requests:
        exchange = exchanges[request.request_sha256]
        completed = exchange.response is not None
        results.append(
            RawResult(
                sample_id=request.sample_id,
                candidate_id=request.route.candidate_id,
                request_sha256=request.request_sha256,
                status="completed" if completed else "error",
                critique=exchange.response,
                error=exchange.error,
                latency_ms=exchange.latency_ms,
                cost_microusd=exchange.cost_microusd,
            )
        )
    return RawResultSet(
        batch_sha256=batch.batch_sha256,
        executor=ExecutorProvenance(
            implementation=implementation,
            version=version,
            cassette_sha256=cassette.cassette_sha256,
        ),
        results=tuple(results),
    )
