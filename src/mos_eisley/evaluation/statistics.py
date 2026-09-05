"""Fixed-design group-mean bounds; repetitions never add independent groups."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract
from mos_eisley.evaluation.models import (
    EvalCase,
    Observation,
    Rate,
    StatisticalDesign,
)


class GroupInterval(Contract):
    method: Literal["hoeffding_bonferroni_95_family"] = "hoeffding_bonferroni_95_family"
    groups: Annotated[int, Field(ge=1)]
    estimate: Rate
    lower: Rate
    upper: Rate
    radius: Annotated[float, Field(gt=0)]


class StatisticalAssessment(Contract):
    design: StatisticalDesign
    family_size: Annotated[int, Field(ge=6, le=768)]
    interval_alpha: Annotated[float, Field(gt=0, lt=1)]
    detection: GroupInterval | None = None
    clean_false_positive_runs: GroupInterval | None = None
    completion: GroupInterval | None = None
    sufficient_groups: bool
    issues: tuple[Literal["missing_independence_groups", "too_few_groups"], ...] = ()


def group_interval(values: Sequence[float], family_size: int) -> GroupInterval:
    """Two-sided Hoeffding bounds with Bonferroni allocation over the full family."""
    if not values or not all(
        math.isfinite(value) and 0 <= value <= 1 for value in values
    ):
        raise ValueError("group rates must be nonempty, finite and within [0, 1]")
    if not 6 <= family_size <= 768:
        raise ValueError("confidence family size is outside the supported range")
    radius = math.sqrt(math.log(2 * family_size / 0.05) / (2 * len(values)))
    estimate = math.fsum(values) / len(values)
    return GroupInterval(
        groups=len(values),
        estimate=estimate,
        lower=max(0.0, estimate - radius),
        upper=min(1.0, estimate + radius),
        radius=radius,
    )


def assess_groups(
    cases: dict[str, EvalCase],
    observations: Sequence[Observation],
    design: StatisticalDesign,
    route_count: int,
) -> StatisticalAssessment:
    """Average repetitions per case, cases per group, then independent groups."""
    family_size = route_count * 3 * 2
    if any(case.independence_group is None for case in cases.values()):
        return StatisticalAssessment(
            design=design,
            family_size=family_size,
            interval_alpha=0.05 / family_size,
            sufficient_groups=False,
            issues=("missing_independence_groups",),
        )
    by_case: dict[str, list[Observation]] = defaultdict(list)
    for item in observations:
        by_case[item.case_id].append(item)
    detection: dict[str, list[float]] = defaultdict(list)
    false_positives: dict[str, list[float]] = defaultdict(list)
    completion: dict[str, list[float]] = defaultdict(list)
    for case_id, rows in by_case.items():
        case = cases[case_id]
        group = case.independence_group
        assert group is not None
        completion[group].append(
            sum(item.status == "completed" for item in rows) / len(rows)
        )
        if case.expected_findings:
            detection[group].append(
                sum(len(item.detected_finding_ids) for item in rows)
                / (len(rows) * len(case.expected_findings))
            )
        else:
            # Unavailable reviews cannot establish freedom from false positives.
            false_positives[group].append(
                sum(
                    item.status == "error" or item.false_positive_count > 0
                    for item in rows
                )
                / len(rows)
            )
    intervals = tuple(
        group_interval(
            [math.fsum(values) / len(values) for _, values in sorted(metric.items())],
            family_size,
        )
        for metric in (detection, false_positives, completion)
    )
    sufficient = all(
        interval.groups >= design.min_groups_per_metric for interval in intervals
    )
    return StatisticalAssessment(
        design=design,
        family_size=family_size,
        interval_alpha=0.05 / family_size,
        detection=intervals[0],
        clean_false_positive_runs=intervals[1],
        completion=intervals[2],
        sufficient_groups=sufficient,
        issues=() if sufficient else ("too_few_groups",),
    )
