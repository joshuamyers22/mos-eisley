"""Strict, content-addressed contracts for blinded route evaluations."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Brief,
    Contract,
    Digest,
    Identifier,
    Text,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import Effort

Split = Literal["calibration", "holdout"]
FailureKind = Literal[
    "provider_error", "timeout", "invalid_output", "budget_exceeded", "unavailable"
]
Rate = Annotated[float, Field(ge=0.0, le=1.0)]
MAX_ASSIGNMENTS = 50_000


class ExpectedFinding(Contract):
    id: Identifier
    category: Literal[
        "correctness", "spec_violation", "security", "performance", "preference"
    ]
    description: Text


class EvalCase(Contract):
    id: Identifier
    split: Split
    brief: Brief
    expected_findings: Annotated[tuple[ExpectedFinding, ...], Field(max_length=50)] = ()
    risk_tags: Annotated[tuple[Identifier, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def unique_labels(self) -> Self:
        finding_ids = tuple(finding.id for finding in self.expected_findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("expected finding ids must be unique within a case")
        if len(self.risk_tags) != len(set(self.risk_tags)):
            raise ValueError("risk tags must be unique")
        return self


class EvaluationDataset(Contract):
    schema_version: Literal[1] = 1
    id: Identifier
    cases: Annotated[tuple[EvalCase, ...], Field(min_length=2, max_length=5000)]

    @model_validator(mode="after")
    def valid_dataset(self) -> Self:
        case_ids = tuple(case.id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case ids must be unique")
        if {case.split for case in self.cases} != {"calibration", "holdout"}:
            raise ValueError("dataset must contain calibration and holdout cases")
        return self

    @property
    def dataset_sha256(self) -> str:
        return digest(canonical_bytes(self))


class RouteCandidate(Contract):
    backend: Identifier
    provider: Identifier
    model: Identifier
    effort: Effort
    client_version: Annotated[str, Field(min_length=1, max_length=200)]
    registry_sha256: Digest

    @property
    def candidate_id(self) -> str:
        return digest(canonical_bytes(self))


class CandidateGrid(Contract):
    schema_version: Literal[1] = 1
    routes: Annotated[tuple[RouteCandidate, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def unique_routes(self) -> Self:
        ids = tuple(route.candidate_id for route in self.routes)
        if len(ids) != len(set(ids)):
            raise ValueError("candidate routes must be unique")
        return self


class EvaluationGate(Contract):
    schema_version: Literal[1] = 1
    confidence_level: Literal["95%"] = "95%"
    min_detection_lower_bound: Rate
    max_false_positive_upper_bound: Rate
    min_completion_lower_bound: Rate
    max_mean_cost_microusd: (
        Annotated[int, Field(ge=0, le=1_000_000_000_000_000)] | None
    ) = None
    max_p95_latency_ms: Annotated[int, Field(gt=0, le=86_400_000)] | None = None


class Assignment(Contract):
    case_id: Identifier
    split: Split
    candidate_id: Digest
    repetition: Annotated[int, Field(ge=0, lt=100)]

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.case_id, self.candidate_id, self.repetition)


class SweepPlan(Contract):
    schema_version: Literal[1] = 1
    dataset_sha256: Digest
    routes: Annotated[tuple[RouteCandidate, ...], Field(min_length=1, max_length=128)]
    repetitions: Annotated[int, Field(ge=1, le=100)]
    randomization_seed: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
    gate: EvaluationGate
    assignments: Annotated[
        tuple[Assignment, ...], Field(min_length=1, max_length=MAX_ASSIGNMENTS)
    ]

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        route_ids = tuple(route.candidate_id for route in self.routes)
        route_id_set = set(route_ids)
        if len(route_ids) != len(route_id_set):
            raise ValueError("plan routes must be unique")
        keys = tuple(assignment.key for assignment in self.assignments)
        if len(keys) != len(set(keys)):
            raise ValueError("plan assignments must be unique")
        if any(
            assignment.candidate_id not in route_id_set
            for assignment in self.assignments
        ):
            raise ValueError("assignment references an unknown route")
        if any(
            assignment.repetition >= self.repetitions for assignment in self.assignments
        ):
            raise ValueError("assignment repetition exceeds plan")
        return self

    @property
    def plan_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def validate_dataset(self, dataset: EvaluationDataset) -> None:
        """Verify full matrix coverage before any dataset-dependent operation."""
        if self.dataset_sha256 != dataset.dataset_sha256:
            raise ValueError("plan does not match the evaluation dataset")
        count = len(dataset.cases) * len(self.routes) * self.repetitions
        if count > MAX_ASSIGNMENTS:
            raise ValueError("evaluation matrix exceeds the assignment limit")
        expected = {
            (case.id, case.split, route.candidate_id, repetition)
            for case in dataset.cases
            for route in self.routes
            for repetition in range(self.repetitions)
        }
        actual = {
            (item.case_id, item.split, item.candidate_id, item.repetition)
            for item in self.assignments
        }
        if actual != expected:
            raise ValueError("plan does not contain the complete evaluation matrix")


class Observation(Contract):
    case_id: Identifier
    candidate_id: Digest
    repetition: Annotated[int, Field(ge=0, lt=100)]
    status: Literal["completed", "error"]
    detected_finding_ids: Annotated[tuple[Identifier, ...], Field(max_length=50)] = ()
    false_positive_count: Annotated[int, Field(ge=0, le=1000)] = 0
    latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]
    cost_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000_000)] | None = None
    adjudication: Literal["fixture", "human"]
    error: FailureKind | None = None

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        if len(self.detected_finding_ids) != len(set(self.detected_finding_ids)):
            raise ValueError("detected finding ids must be unique")
        if self.status == "completed" and self.error is not None:
            raise ValueError("completed observation cannot declare an error")
        if self.status == "error" and (
            self.error is None
            or self.detected_finding_ids
            or self.false_positive_count != 0
        ):
            raise ValueError("error observation cannot declare findings")
        return self

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.case_id, self.candidate_id, self.repetition)


class ObservationSet(Contract):
    schema_version: Literal[1] = 1
    plan_sha256: Digest
    raw_results_sha256: Digest
    adjudication_sha256: Digest
    observations: Annotated[tuple[Observation, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_observations(self) -> Self:
        keys = tuple(observation.key for observation in self.observations)
        if len(keys) != len(set(keys)):
            raise ValueError("observations must have unique assignment keys")
        return self

    @property
    def observations_sha256(self) -> str:
        return digest(canonical_bytes(self))
