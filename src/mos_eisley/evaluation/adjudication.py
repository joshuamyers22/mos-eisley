"""Provenance-bound adjudication and observation compilation."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import (
    Brief,
    Contract,
    Critique,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.evaluation.execution import (
    BlindingMap,
    ExecutionBatch,
    RawResultSet,
)
from mos_eisley.evaluation.models import (
    EvaluationDataset,
    ExpectedFinding,
    Observation,
    ObservationSet,
    SweepPlan,
)


class AdjudicatorProvenance(Contract):
    adjudicator_id: Identifier
    method: Literal["fixture", "human"]
    rubric_sha256: Digest
    completed_at: Annotated[
        str,
        Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),
    ]

    @field_validator("completed_at")
    @classmethod
    def valid_utc_timestamp(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as error:
            raise ValueError("completion time must be a valid UTC timestamp") from error
        return value


class Judgment(Contract):
    sample_id: Digest
    detected_finding_ids: Annotated[tuple[Identifier, ...], Field(max_length=50)] = ()
    false_positive_count: Annotated[int, Field(ge=0, le=1000)] = 0

    @model_validator(mode="after")
    def unique_detections(self) -> Self:
        if len(self.detected_finding_ids) != len(set(self.detected_finding_ids)):
            raise ValueError("judgment detections must be unique")
        return self


class GradingItem(Contract):
    sample_id: Digest
    brief: Brief
    expected_findings: Annotated[tuple[ExpectedFinding, ...], Field(max_length=50)]
    critique: Critique


class GradingBatch(Contract):
    schema_version: Literal[1] = 1
    dataset_sha256: Digest
    mapping_sha256: Digest
    raw_results_sha256: Digest
    items: Annotated[tuple[GradingItem, ...], Field(max_length=50_000)]

    @model_validator(mode="after")
    def unique_items(self) -> Self:
        sample_ids = tuple(item.sample_id for item in self.items)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("grading items must have unique sample ids")
        return self

    @property
    def grading_batch_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AdjudicationSet(Contract):
    schema_version: Literal[1] = 1
    grading_batch_sha256: Digest
    adjudicator: AdjudicatorProvenance
    judgments: Annotated[tuple[Judgment, ...], Field(max_length=50_000)]

    @model_validator(mode="after")
    def unique_judgments(self) -> Self:
        sample_ids = tuple(judgment.sample_id for judgment in self.judgments)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("adjudication sample ids must be unique")
        return self

    @property
    def adjudication_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _validate_execution_chain(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
) -> None:
    plan.validate_dataset(dataset)
    if batch.plan_sha256 != plan.plan_sha256:
        raise ValueError("execution batch does not match the sweep plan")
    if (
        mapping.plan_sha256 != plan.plan_sha256
        or mapping.dataset_sha256 != dataset.dataset_sha256
        or mapping.batch_sha256 != batch.batch_sha256
    ):
        raise ValueError("blinding map does not match its source artifacts")
    if raw_results.batch_sha256 != batch.batch_sha256:
        raise ValueError("raw results do not match the execution batch")


def _validate_batch_mapping(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    batch: ExecutionBatch,
    mapping: BlindingMap,
) -> None:
    cases = {case.id: case for case in dataset.cases}
    expected_assignments = {
        assignment.key
        for assignment in plan.assignments
        if assignment.split == mapping.split
    }
    entries = {entry.sample_id: entry for entry in mapping.entries}
    if {entry.assignment_key for entry in mapping.entries} != expected_assignments:
        raise ValueError("blinding map does not exactly cover its split")
    if set(entries) != {request.sample_id for request in batch.requests}:
        raise ValueError("blinding map does not exactly cover the execution batch")
    for request in batch.requests:
        entry = entries[request.sample_id]
        if (
            entry.request_sha256 != request.request_sha256
            or entry.candidate_id != request.route.candidate_id
            or request.brief != cases[entry.case_id].brief
        ):
            raise ValueError("blinded request does not match its private mapping")


def _validate_raw_results(batch: ExecutionBatch, raw_results: RawResultSet) -> None:
    requests = {request.sample_id: request for request in batch.requests}
    results = {result.sample_id: result for result in raw_results.results}
    if set(results) != set(requests):
        raise ValueError("raw results do not exactly cover the execution batch")
    for sample_id, result in results.items():
        request = requests[sample_id]
        if (
            result.request_sha256 != request.request_sha256
            or result.candidate_id != request.route.candidate_id
        ):
            raise ValueError("raw result does not match its blinded request")


def make_grading_batch(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
) -> GradingBatch:
    """Create a route-blind packet containing only material needed for grading."""
    _validate_execution_chain(dataset, plan, batch, mapping, raw_results)
    _validate_batch_mapping(dataset, plan, batch, mapping)
    _validate_raw_results(batch, raw_results)
    cases = {case.id: case for case in dataset.cases}
    entries = {entry.sample_id: entry for entry in mapping.entries}
    return GradingBatch(
        dataset_sha256=dataset.dataset_sha256,
        mapping_sha256=mapping.mapping_sha256,
        raw_results_sha256=raw_results.raw_results_sha256,
        items=tuple(
            GradingItem(
                sample_id=result.sample_id,
                brief=cases[entries[result.sample_id].case_id].brief,
                expected_findings=cases[
                    entries[result.sample_id].case_id
                ].expected_findings,
                critique=result.critique,
            )
            for result in raw_results.results
            if result.status == "completed" and result.critique is not None
        ),
    )


def compile_observations(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
    grading_batch: GradingBatch,
    adjudication: AdjudicationSet,
) -> ObservationSet:
    """Join labels only after execution and retain the complete provenance chain."""
    expected_grading_batch = make_grading_batch(
        dataset, plan, batch, mapping, raw_results
    )
    if grading_batch != expected_grading_batch:
        raise ValueError("grading batch does not match its source artifacts")
    if adjudication.grading_batch_sha256 != grading_batch.grading_batch_sha256:
        raise ValueError("adjudication does not match the grading batch")
    cases = {case.id: case for case in dataset.cases}
    entries = {entry.sample_id: entry for entry in mapping.entries}
    judgments = {judgment.sample_id: judgment for judgment in adjudication.judgments}
    completed_ids = {
        result.sample_id
        for result in raw_results.results
        if result.status == "completed"
    }
    if set(judgments) != completed_ids:
        raise ValueError("adjudication must exactly cover completed raw results")

    observations: list[Observation] = []
    for result in raw_results.results:
        entry = entries[result.sample_id]
        if result.status == "error":
            observations.append(
                Observation(
                    case_id=entry.case_id,
                    candidate_id=entry.candidate_id,
                    repetition=entry.repetition,
                    status="error",
                    latency_ms=result.latency_ms,
                    cost_microusd=result.cost_microusd,
                    adjudication=adjudication.adjudicator.method,
                    error=result.error,
                )
            )
            continue
        judgment = judgments[result.sample_id]
        expected_ids = {
            finding.id for finding in cases[entry.case_id].expected_findings
        }
        if not set(judgment.detected_finding_ids) <= expected_ids:
            raise ValueError("judgment contains an unknown expected finding id")
        finding_count = len(result.critique.findings) if result.critique else 0
        if judgment.detected_finding_ids and finding_count == 0:
            raise ValueError("empty critique cannot support detected findings")
        if judgment.false_positive_count > finding_count:
            raise ValueError("false-positive count exceeds the critique findings")
        observations.append(
            Observation(
                case_id=entry.case_id,
                candidate_id=entry.candidate_id,
                repetition=entry.repetition,
                status="completed",
                detected_finding_ids=judgment.detected_finding_ids,
                false_positive_count=judgment.false_positive_count,
                latency_ms=result.latency_ms,
                cost_microusd=result.cost_microusd,
                adjudication=adjudication.adjudicator.method,
            )
        )
    return ObservationSet(
        plan_sha256=plan.plan_sha256,
        raw_results_sha256=raw_results.raw_results_sha256,
        adjudication_sha256=adjudication.adjudication_sha256,
        observations=tuple(observations),
    )
