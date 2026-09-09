"""Frozen, label-free comparison ordering and offline recorded-timing checks."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from mos_eisley.analysis.artifacts import load_artifact
from mos_eisley.analysis.evaluation import (
    EvaluationArm,
    EvaluationInputs,
    EvaluationReport,
    EvaluationSuite,
    Split,
    evaluate,
    public_plan,
)
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest


class ScheduledCase(Contract):
    id: Identifier
    family: Identifier
    question: Annotated[str, Field(min_length=1, max_length=8000)]
    fixture_sha256: Digest


class ComparisonTasks(Contract):
    schema_version: Literal[1] = 1
    suite_sha256: Digest
    split: Split
    cases: Annotated[tuple[ScheduledCase, ...], Field(min_length=1, max_length=128)]
    arms: Annotated[tuple[EvaluationArm, ...], Field(min_length=2, max_length=8)]

    @model_validator(mode="after")
    def unique_tasks(self) -> "ComparisonTasks":
        if len({case.id for case in self.cases}) != len(self.cases) or len(
            {arm.id for arm in self.arms}
        ) != len(self.arms):
            raise ValueError("comparison cases and arms must have unique identities")
        return self


class Assignment(Contract):
    ordinal: Annotated[int, Field(ge=1, le=1024)]
    case_id: Identifier
    arm_id: Identifier


def assignment_order(tasks: ComparisonTasks, seed: str) -> tuple[Assignment, ...]:
    def rank(kind: str, name: str) -> tuple[str, str]:
        return digest(json.dumps([seed, kind, name]).encode()), name

    cases = sorted(tasks.cases, key=lambda case: rank("case", case.id))
    arms = sorted(tasks.arms, key=lambda arm: rank("arm", arm.id))
    assignments: list[Assignment] = []
    for index, case in enumerate(cases):
        offset = index % len(arms)
        for arm in (*arms[offset:], *arms[:offset]):
            assignments.append(
                Assignment(
                    ordinal=len(assignments) + 1,
                    case_id=case.id,
                    arm_id=arm.id,
                )
            )
    return tuple(assignments)


class ComparisonSchedule(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["sha256_case_blocks_rotating_arms_v1"] = (
        "sha256_case_blocks_rotating_arms_v1"
    )
    created_at: datetime
    seed: Digest
    tasks: ComparisonTasks
    assignments: Annotated[tuple[Assignment, ...], Field(min_length=2, max_length=1024)]

    @model_validator(mode="after")
    def frozen_order(self) -> "ComparisonSchedule":
        if self.created_at.tzinfo is None:
            raise ValueError("schedule creation time requires a timezone")
        if self.assignments != assignment_order(self.tasks, self.seed):
            raise ValueError("assignments differ from the derived complete order")
        if len(canonical_bytes(self)) > 2_000_000:
            raise ValueError("comparison schedule exceeds its byte limit")
        return self


def make_schedule(
    suite: EvaluationSuite,
    split: Split,
    seed: str,
    *,
    created_at: datetime | None = None,
) -> ComparisonSchedule:
    suite = EvaluationSuite.model_validate_json(suite.model_dump_json())
    tasks = ComparisonTasks.model_validate_json(json.dumps(public_plan(suite, split)))
    created = created_at if created_at is not None else datetime.now(UTC)
    if created.tzinfo is None or created < suite.reviewed_at:
        raise ValueError("schedule must follow the asserted suite review")
    return ComparisonSchedule(
        created_at=created,
        seed=seed,
        tasks=tasks,
        assignments=assignment_order(tasks, seed),
    )


class RecordedTiming(Contract):
    assignment: Assignment
    started_at: datetime | None = None
    completed_at: datetime | None = None
    reasons: tuple[
        Literal[
            "timing_unavailable",
            "run_predates_schedule",
            "out_of_order",
            "overlap",
        ],
        ...,
    ] = ()


class ComparisonAssessment(Contract):
    schema_version: Literal[1] = 1
    schedule_sha256: Digest
    evaluation: EvaluationReport
    timings: tuple[RecordedTiming, ...]
    recorded_order_matches: bool
    timing_unknown_assignments: int
    execution_authorship_verified: Literal[False] = False
    fixture_snapshot_verified: Literal[False] = False
    controlled_comparison_verified: Literal[False] = False
    promotion_ready: Literal[False] = False


def assess_schedule(
    suite: EvaluationSuite,
    schedule: ComparisonSchedule,
    inputs: EvaluationInputs,
) -> ComparisonAssessment:
    suite = EvaluationSuite.model_validate_json(suite.model_dump_json())
    schedule = ComparisonSchedule.model_validate_json(schedule.model_dump_json())
    inputs = EvaluationInputs.model_validate_json(inputs.model_dump_json())
    expected = make_schedule(
        suite, inputs.split, schedule.seed, created_at=schedule.created_at
    )
    if expected != schedule:
        raise ValueError("schedule differs from the reviewed suite or selected split")
    evaluation = evaluate(suite, inputs)
    observations = {(item.case_id, item.arm_id): item for item in inputs.observations}
    scores = {(item.case_id, item.arm_id): item for item in evaluation.cases}
    timings: list[RecordedTiming] = []
    previous_start: datetime | None = None
    previous_end: datetime | None = None
    for assignment in schedule.assignments:
        key = (assignment.case_id, assignment.arm_id)
        observation = observations.get(key)
        score = scores[key]
        if (
            observation is None
            or observation.artifact_path is None
            or score.outcome
            in {
                "invalid",
                "missing",
                "failure",
            }
        ):
            timings.append(
                RecordedTiming(assignment=assignment, reasons=("timing_unavailable",))
            )
            continue
        try:
            # Recheck the pinned payload when retrieving timestamps after grading.
            manifest, artifact = load_artifact(Path(observation.artifact_path))
            if manifest.payload_sha256 != observation.artifact_sha256:
                raise ValueError("artifact changed after grading")
        except Exception:
            timings.append(
                RecordedTiming(assignment=assignment, reasons=("timing_unavailable",))
            )
            continue
        started, completed = artifact.result.started_at, artifact.result.completed_at
        reasons: list[
            Literal[
                "timing_unavailable", "run_predates_schedule", "out_of_order", "overlap"
            ]
        ] = []
        if started < schedule.created_at:
            reasons.append("run_predates_schedule")
        if previous_start is not None and started < previous_start:
            reasons.append("out_of_order")
        elif previous_end is not None and started < previous_end:
            reasons.append("overlap")
        previous_start = max(previous_start, started) if previous_start else started
        previous_end = max(previous_end, completed) if previous_end else completed
        timings.append(
            RecordedTiming(
                assignment=assignment,
                started_at=started,
                completed_at=completed,
                reasons=tuple(reasons),
            )
        )
    return ComparisonAssessment(
        schedule_sha256=digest(canonical_bytes(schedule)),
        evaluation=evaluation,
        timings=tuple(timings),
        recorded_order_matches=all(not item.reasons for item in timings),
        timing_unknown_assignments=sum(item.started_at is None for item in timings),
    )
