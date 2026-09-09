"""Offline expectation matching for private analytical artifacts."""

import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import Field, JsonValue, model_validator

from mos_eisley.analysis.artifacts import (
    AnalysisArtifact,
    load_artifact,
    private_directory,
)
from mos_eisley.analysis.controller import AnalysisRunIdentity
from mos_eisley.analysis.evidence import CellClaim, Scalar
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.store import private_write

Split = Literal["development", "holdout"]
Reason = Literal[
    "missing_observation",
    "recorded_failure",
    "invalid_artifact",
    "artifact_hash_mismatch",
    "question_mismatch",
    "model_mismatch",
    "run_identity_mismatch",
    "semantic_revision_mismatch",
    "status_mismatch",
    "claims_mismatch",
    "run_predates_review",
    "usage_incoherent",
]


def _same(left: object, right: object) -> bool:
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False
    )


def _number(value: Scalar) -> Decimal:
    if type(value) not in (int, float, str) or len(str(value)) > 128:
        raise ValueError("unsupported numeric comparison")
    if (
        re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?", str(value))
        is None
    ):
        raise ValueError("unsupported numeric comparison")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("unsupported numeric comparison") from None
    if not number.is_finite() or abs(number.adjusted()) > 400:
        raise ValueError("numeric comparison exceeds its range")
    return number


class ExpectedCell(Contract):
    tool: Literal["run_metric", "query_parquet", "query_postgres"]
    arguments: Annotated[dict[str, JsonValue], Field(max_length=32)]
    submitted_sql: Annotated[str, Field(min_length=1, max_length=16000)]
    source_metadata: Annotated[dict[str, JsonValue], Field(max_length=16)]
    reviewed_units: Annotated[str, Field(min_length=1, max_length=128)]
    row: Annotated[int, Field(ge=0, le=9999)]
    column: Annotated[str, Field(min_length=1, max_length=256)]
    value: Scalar
    absolute_tolerance: Annotated[
        str, Field(pattern=r"^(0|[1-9][0-9]{0,18})(\.[0-9]{1,18})?$", max_length=38)
    ] = "0"

    @model_validator(mode="after")
    def explicit_source(self) -> "ExpectedCell":
        if self.tool == "run_metric":
            if (
                not {"name", "revision"} <= self.arguments.keys()
                or not {"backend", "source", "units"} <= self.source_metadata.keys()
            ):
                raise ValueError(
                    "metric expectations require definition and source/unit bindings"
                )
            if self.source_metadata["units"] != self.reviewed_units:
                raise ValueError(
                    "reviewed metric units differ from the expected metadata"
                )
        elif (
            "root" if self.tool == "query_parquet" else "source"
        ) not in self.arguments:
            raise ValueError("query expectation requires a source binding")
        if Decimal(self.absolute_tolerance):
            _number(self.value)
        return self


class ExpectedOutcome(Contract):
    arm_id: Identifier
    status: Literal["answer", "clarify", "unavailable"]
    claim_order: Literal["ordered", "unordered"] = "ordered"
    cells: Annotated[tuple[ExpectedCell, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def status_shape(self) -> "ExpectedOutcome":
        if (self.status == "answer") != bool(self.cells):
            raise ValueError("only answers carry expected cells")
        return self


class EvaluationArm(Contract):
    id: Identifier
    provider: Literal["fixture", "openai"]
    model: Identifier
    run_identity: AnalysisRunIdentity
    semantic_revision: Digest


class EvaluationCase(Contract):
    id: Identifier
    family: Identifier
    split: Split
    question: Annotated[str, Field(min_length=1, max_length=8000)]
    fixture_sha256: Digest
    expectations: Annotated[
        tuple[ExpectedOutcome, ...], Field(min_length=1, max_length=8)
    ]


class EvaluationSuite(Contract):
    schema_version: Literal[1] = 1
    id: Identifier
    reviewer: Identifier
    reviewed_at: datetime
    arms: Annotated[tuple[EvaluationArm, ...], Field(min_length=1, max_length=8)]
    cases: Annotated[tuple[EvaluationCase, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def complete_design(self) -> "EvaluationSuite":
        if self.reviewed_at.tzinfo is None:
            raise ValueError("review time must include a timezone")
        arms = {arm.id for arm in self.arms}
        if len(arms) != len(self.arms) or len({case.id for case in self.cases}) != len(
            self.cases
        ):
            raise ValueError("evaluation identities must be unique")
        families: dict[str, Split] = {}
        questions: set[str] = set()
        for case in self.cases:
            ids = [expected.arm_id for expected in case.expectations]
            if len(ids) != len(set(ids)) or set(ids) != arms:
                raise ValueError("every case requires exactly one expectation per arm")
            if case.family in families and families[case.family] != case.split:
                raise ValueError("development and holdout families must be disjoint")
            if case.question in questions:
                raise ValueError("duplicate questions can leak across evaluation cases")
            questions.add(case.question)
            families[case.family] = case.split
        if len(canonical_bytes(self)) > 2_000_000:
            raise ValueError("evaluation suite exceeds byte limit")
        return self


class Observation(Contract):
    case_id: Identifier
    arm_id: Identifier
    artifact_path: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    artifact_sha256: Digest | None = None
    failure: (
        Literal[
            "timeout", "provider_error", "tool_error", "validation_error", "cancelled"
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def one_outcome(self) -> "Observation":
        artifact = self.artifact_path is not None and self.artifact_sha256 is not None
        if (self.artifact_path is None) != (
            self.artifact_sha256 is None
        ) or artifact == (self.failure is not None):
            raise ValueError(
                "observation requires one pinned artifact or recorded failure"
            )
        if (
            self.artifact_path is not None
            and not Path(self.artifact_path).is_absolute()
        ):
            raise ValueError("artifact paths must be absolute")
        return self


class EvaluationInputs(Contract):
    schema_version: Literal[1] = 1
    suite_sha256: Digest
    split: Split
    observations: Annotated[tuple[Observation, ...], Field(max_length=1024)] = ()


class CaseScore(Contract):
    case_id: Identifier
    arm_id: Identifier
    outcome: Literal["match", "mismatch", "missing", "failure", "invalid"]
    reasons: tuple[Reason, ...]
    artifact_sha256: Digest | None = None
    elapsed_ms: int | None = None
    usage: dict[str, int] | None = None
    retained_microusd: int | None = None


class ArmScore(Contract):
    arm_id: Identifier
    planned_cases: int
    matched_cases: int
    mismatched_cases: int
    missing_cases: int
    failed_cases: int
    invalid_cases: int
    reported_usage: dict[str, int]
    usage_unknown_cases: int
    reported_retained_microusd: int
    spending_unknown_cases: int
    measured_elapsed_ms: int
    latency_unknown_cases: int


class EvaluationReport(Contract):
    schema_version: Literal[1] = 1
    suite_sha256: Digest
    inputs_sha256: Digest
    split: Split
    cases: tuple[CaseScore, ...]
    arms: tuple[ArmScore, ...]
    observations_complete: bool
    source_truth_verified: Literal[False] = False
    fixture_snapshot_verified: Literal[False] = False
    controlled_comparison_verified: Literal[False] = False
    explanation_quality_assessed: Literal[False] = False
    promotion_ready: Literal[False] = False


def public_plan(suite: EvaluationSuite, split: Split) -> dict[str, JsonValue]:
    """Export questions and identities without expected answers or SQL."""
    suite = EvaluationSuite.model_validate_json(suite.model_dump_json())
    cases = [case for case in suite.cases if case.split == split]
    if not cases:
        raise ValueError("selected split has no cases")
    return {
        "schema_version": 1,
        "suite_sha256": digest(canonical_bytes(suite)),
        "split": split,
        "cases": [
            {
                "id": case.id,
                "family": case.family,
                "question": case.question,
                "fixture_sha256": case.fixture_sha256,
            }
            for case in cases
        ],
        "arms": [arm.model_dump(mode="json") for arm in suite.arms],
    }


def _cell_matches(
    expected: ExpectedCell, claim: CellClaim, artifact: AnalysisArtifact
) -> bool:
    if (claim.row, claim.column) != (expected.row, expected.column) or type(
        claim.value
    ) is not type(expected.value):
        return False
    query = next(
        (
            item
            for item in artifact.result.sql_trail
            if item.result_id == claim.result_id
        ),
        None,
    )
    if (
        query is None
        or not query.complete
        or query.tool != expected.tool
        or query.submitted_sql != expected.submitted_sql
        or not _same(query.arguments, expected.arguments)
        or any(
            key not in query.source_reported_metadata
            or not _same(query.source_reported_metadata[key], value)
            for key, value in expected.source_metadata.items()
        )
    ):
        return False
    tolerance = Decimal(expected.absolute_tolerance)
    if not tolerance:
        return _same(claim.value, expected.value)
    try:
        with localcontext() as context:
            context.prec = 1024
            return abs(_number(claim.value) - _number(expected.value)) <= tolerance
    except ValueError:
        return False


def _claims_match(expected: ExpectedOutcome, artifact: AnalysisArtifact) -> bool:
    actual = artifact.result.answer.claims
    if len(actual) != len(expected.cells):
        return False
    if expected.claim_order == "ordered":
        return all(
            _cell_matches(cell, claim, artifact)
            for cell, claim in zip(expected.cells, actual, strict=True)
        )
    # Perfect bipartite matching preserves multiplicity with overlapping tolerances.
    owners: dict[int, int] = {}

    def assign(index: int, seen: set[int]) -> bool:
        for candidate, claim in enumerate(actual):
            if candidate in seen or not _cell_matches(
                expected.cells[index], claim, artifact
            ):
                continue
            seen.add(candidate)
            if candidate not in owners or assign(owners[candidate], seen):
                owners[candidate] = index
                return True
        return False

    return all(assign(index, set()) for index in range(len(expected.cells)))


def _score_case(
    suite: EvaluationSuite,
    case: EvaluationCase,
    arm: EvaluationArm,
    observation: Observation | None,
) -> CaseScore:
    if observation is None:
        return CaseScore(
            case_id=case.id,
            arm_id=arm.id,
            outcome="missing",
            reasons=("missing_observation",),
        )
    if observation.failure is not None:
        return CaseScore(
            case_id=case.id,
            arm_id=arm.id,
            outcome="failure",
            reasons=("recorded_failure",),
        )
    try:
        manifest, artifact = load_artifact(Path(cast(str, observation.artifact_path)))
    except Exception:
        return CaseScore(
            case_id=case.id,
            arm_id=arm.id,
            outcome="invalid",
            reasons=("invalid_artifact",),
        )
    if manifest.payload_sha256 != observation.artifact_sha256:
        return CaseScore(
            case_id=case.id,
            arm_id=arm.id,
            outcome="invalid",
            reasons=("artifact_hash_mismatch",),
        )
    result = artifact.result
    reasons: list[Reason] = []
    if result.question != case.question:
        reasons.append("question_mismatch")
    if (result.provider, result.model) != (arm.provider, arm.model):
        reasons.append("model_mismatch")
    if result.run_identity != arm.run_identity:
        reasons.append("run_identity_mismatch")
    if result.semantic_revision != arm.semantic_revision:
        reasons.append("semantic_revision_mismatch")
    if result.started_at < suite.reviewed_at:
        reasons.append("run_predates_review")
    expected = next(item for item in case.expectations if item.arm_id == arm.id)
    if result.answer.status != expected.status:
        reasons.append("status_mismatch")
    elif not _claims_match(expected, artifact):
        reasons.append("claims_mismatch")
    usage: Counter[str] = Counter()
    for item in result.provider_usage:
        if (
            item.cache_read + item.cache_write > item.input
            or item.reasoning > item.output
        ):
            reasons.append("usage_incoherent")
            break
        for name in ("input", "output", "reasoning", "cache_read", "cache_write"):
            usage[f"{item.unit}.{name}"] += getattr(item, name)
    else:
        return CaseScore(
            case_id=case.id,
            arm_id=arm.id,
            outcome="mismatch" if reasons else "match",
            reasons=tuple(reasons),
            artifact_sha256=manifest.payload_sha256,
            elapsed_ms=int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            ),
            usage=dict(usage),
            retained_microusd=(
                artifact.spend_receipt.retained_microusd
                if artifact.spend_receipt
                else 0
                if result.provider == "fixture"
                else None
            ),
        )
    return CaseScore(
        case_id=case.id,
        arm_id=arm.id,
        outcome="invalid",
        reasons=tuple(reasons),
        artifact_sha256=manifest.payload_sha256,
    )


def evaluate(suite: EvaluationSuite, inputs: EvaluationInputs) -> EvaluationReport:
    suite = EvaluationSuite.model_validate_json(suite.model_dump_json())
    inputs = EvaluationInputs.model_validate_json(inputs.model_dump_json())
    suite_hash = digest(canonical_bytes(suite))
    if suite_hash != inputs.suite_sha256:
        raise ValueError("evaluation labels differ from the frozen suite digest")
    cases = [case for case in suite.cases if case.split == inputs.split]
    if not cases:
        raise ValueError("selected split has no cases")
    expected = {(case.id, arm.id) for case in cases for arm in suite.arms}
    observations = {(item.case_id, item.arm_id): item for item in inputs.observations}
    if (
        len(observations) != len(inputs.observations)
        or not observations.keys() <= expected
    ):
        raise ValueError("duplicate or unexpected evaluation observations")
    hashes = [
        item.artifact_sha256
        for item in inputs.observations
        if item.artifact_sha256 is not None
    ]
    if len(set(hashes)) != len(hashes):
        raise ValueError("one captured artifact cannot fill multiple assignments")
    scores = tuple(
        _score_case(suite, case, arm, observations.get((case.id, arm.id)))
        for case in cases
        for arm in suite.arms
    )
    aggregates: list[ArmScore] = []
    for arm in suite.arms:
        rows = [row for row in scores if row.arm_id == arm.id]
        counts = Counter(row.outcome for row in rows)
        usage: Counter[str] = Counter()
        for row in rows:
            usage.update(row.usage or {})
        aggregates.append(
            ArmScore(
                arm_id=arm.id,
                planned_cases=len(rows),
                matched_cases=counts["match"],
                mismatched_cases=counts["mismatch"],
                missing_cases=counts["missing"],
                failed_cases=counts["failure"],
                invalid_cases=counts["invalid"],
                reported_usage=dict(usage),
                usage_unknown_cases=sum(row.usage is None for row in rows),
                reported_retained_microusd=sum(
                    row.retained_microusd or 0 for row in rows
                ),
                spending_unknown_cases=sum(
                    row.retained_microusd is None for row in rows
                ),
                measured_elapsed_ms=sum(row.elapsed_ms or 0 for row in rows),
                latency_unknown_cases=sum(row.elapsed_ms is None for row in rows),
            )
        )
    return EvaluationReport(
        suite_sha256=suite_hash,
        inputs_sha256=digest(canonical_bytes(inputs)),
        split=inputs.split,
        cases=scores,
        arms=tuple(aggregates),
        observations_complete=all(score.outcome != "missing" for score in scores),
    )


def write_private_json(path: Path, value: Contract | dict[str, JsonValue]) -> None:
    private_directory(path.parent)
    payload = (
        canonical_bytes(value)
        if isinstance(value, Contract)
        else json.dumps(value, sort_keys=True, allow_nan=False).encode()
    )
    if len(payload) > 2_000_000:
        raise ValueError("evaluation output exceeds its byte limit")
    private_write(path, payload)
