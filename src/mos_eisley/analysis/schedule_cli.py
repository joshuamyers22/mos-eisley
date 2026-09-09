"""Offline comparison commands and an explicit synthetic MCP demonstration."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import cast

from mos_eisley.analysis.evaluation import (
    EvaluationInputs,
    EvaluationSuite,
    Split,
    write_private_json,
)
from mos_eisley.analysis.schedule import (
    ComparisonSchedule,
    assess_schedule,
    make_schedule,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.files import read_bounded


def run_command(args: argparse.Namespace) -> int:
    try:
        if args.command == "analysis-comparison-demo":
            from mos_eisley.analysis.comparison_demo import run_demo

            path, report = asyncio.run(run_demo(cast(Path, args.result_root)))
            print(
                json.dumps(
                    {
                        "type": "analysis.comparison.demo",
                        "path": str(path),
                        "schedule_sha256": report.schedule_sha256,
                        "recorded_order_matches": report.recorded_order_matches,
                        "arms": [
                            arm.model_dump(mode="json")
                            for arm in report.evaluation.arms
                        ],
                    }
                )
            )
            return (
                0
                if report.recorded_order_matches
                and all(case.outcome == "match" for case in report.evaluation.cases)
                else 1
            )
        suite = EvaluationSuite.model_validate_json(
            read_bounded(cast(Path, args.suite))
        )
        output = cast(Path, args.output)
        if args.command == "analysis-eval-schedule":
            schedule = make_schedule(
                suite, cast(Split, args.split), cast(str, args.seed)
            )
            write_private_json(output, schedule)
            print(
                json.dumps(
                    {
                        "type": "analysis.schedule.created",
                        "path": str(output),
                        "schedule_sha256": digest(canonical_bytes(schedule)),
                        "assignments": len(schedule.assignments),
                    }
                )
            )
            return 0
        schedule = ComparisonSchedule.model_validate_json(
            read_bounded(cast(Path, args.schedule))
        )
        if digest(canonical_bytes(schedule)) != args.schedule_sha256:
            raise ValueError("schedule differs from the independently retained digest")
        inputs = EvaluationInputs.model_validate_json(
            read_bounded(cast(Path, args.inputs))
        )
        report = assess_schedule(suite, schedule, inputs)
        write_private_json(output, report)
        print(
            json.dumps(
                {
                    "type": "analysis.schedule.assessed",
                    "path": str(output),
                    "recorded_order_matches": report.recorded_order_matches,
                    "timing_unknown_assignments": report.timing_unknown_assignments,
                    "arms": [
                        arm.model_dump(mode="json") for arm in report.evaluation.arms
                    ],
                }
            )
        )
        return (
            0
            if report.recorded_order_matches
            and all(case.outcome == "match" for case in report.evaluation.cases)
            else 1
        )
    except Exception:
        print('{"type":"analysis.schedule.failed"}', file=sys.stderr)
        return 2
