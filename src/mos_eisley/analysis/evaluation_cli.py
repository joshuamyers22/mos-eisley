"""Offline analytical grading and explicit synthetic demonstration commands."""

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
    evaluate,
    public_plan,
    write_private_json,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.files import read_bounded


def run_command(args: argparse.Namespace) -> int:
    try:
        if args.command == "analysis-eval-demo":
            from mos_eisley.analysis.evaluation_demo import run_demo

            path, report = asyncio.run(run_demo(cast(Path, args.result_root)))
            print(
                json.dumps(
                    {
                        "type": "analysis.evaluation.demo",
                        "path": str(path),
                        "arms": [arm.model_dump(mode="json") for arm in report.arms],
                    }
                )
            )
            return 0
        suite = EvaluationSuite.model_validate_json(
            read_bounded(cast(Path, args.suite))
        )
        output = cast(Path, args.output)
        if args.command == "analysis-eval-plan":
            plan = public_plan(suite, cast(Split, args.split))
            write_private_json(output, plan)
            print(
                json.dumps(
                    {
                        "type": "analysis.evaluation.planned",
                        "path": str(output),
                        "suite_sha256": digest(canonical_bytes(suite)),
                    }
                )
            )
            return 0
        inputs = EvaluationInputs.model_validate_json(
            read_bounded(cast(Path, args.inputs))
        )
        report = evaluate(suite, inputs)
        write_private_json(output, report)
        print(
            json.dumps(
                {
                    "type": "analysis.evaluation.scored",
                    "path": str(output),
                    "arms": [arm.model_dump(mode="json") for arm in report.arms],
                }
            )
        )
        return 0 if all(case.outcome == "match" for case in report.cases) else 1
    except Exception:
        print('{"type":"analysis.evaluation.failed"}', file=sys.stderr)
        return 2
