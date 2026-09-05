"""Composition root for offline review and verified replay."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from mos_eisley.core.models import Brief, ReviewPolicy
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.recorded import Cassette, RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import index_run, load_run, save_run

EXIT_CODES = {"accept": 0, "revise": 1, "reject": 1, "infrastructure_error": 2}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="mos-eisley",
        description=(
            "Mos Eisley: recorded adversarial review foundation (no live models)."
        ),
    )
    command.add_argument("--version", action="version", version="mos-eisley 0.1.0")
    subcommands = command.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("demo", "Run the synthetic recorded example"),
        ("review", "Review an explicit brief using a request-bound cassette"),
    ):
        sub = subcommands.add_parser(name, help=help_text)
        sub.add_argument("--output", type=Path, default=Path(".mos-eisley/runs"))
        sub.add_argument(
            "--json", action="store_true", help="Print NDJSON result events"
        )
        if name == "review":
            sub.add_argument(
                "--brief",
                type=Path,
                required=True,
                help="Brief JSON; no implicit repository reads",
            )
            sub.add_argument("--cassette", type=Path, required=True)
    replay = subcommands.add_parser(
        "replay", help="Verify artifacts and replay recorded responses"
    )
    replay.add_argument("run", type=Path)
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "replay":
            brief, cassette, policy, expected = load_run(cast(Path, args.run))
            actual = asyncio.run(
                review(
                    brief,
                    tuple(r.critic for r in cassette.critics),
                    RecordedReviewer(cassette),
                    policy,
                )
            )
            if actual != expected:
                raise ValueError("recorded replay differs from stored result")
            print(
                json.dumps(
                    {
                        "type": "replay.verified",
                        "brief_id": brief.brief_id,
                        "decision": actual.verdict.decision,
                    }
                )
            )
            return 0
        if args.command == "demo":
            brief, cassette = demo_inputs()
        else:
            brief = Brief.model_validate_json(read_bounded(cast(Path, args.brief)))
            cassette = Cassette.model_validate_json(
                read_bounded(cast(Path, args.cassette), 16_000_000)
            )
        if brief.brief_id != cassette.brief_id:
            raise ValueError("cassette does not match the supplied brief")
        policy = ReviewPolicy()
        result = asyncio.run(
            review(
                brief,
                tuple(r.critic for r in cassette.critics),
                RecordedReviewer(cassette),
                policy,
            )
        )
        root = cast(Path, args.output)
        path = save_run(root, brief, cassette, policy, result)
        try:
            index_run(root, path, result)
        except (OSError, sqlite3.Error):
            print(
                "Index unavailable; complete run artifacts were preserved.",
                file=sys.stderr,
            )
        if args.json:
            print(
                json.dumps({"type": "run.saved", "mode": "recorded", "path": str(path)})
            )
            print(
                json.dumps(
                    {"type": "verdict", **result.verdict.model_dump(mode="json")}
                )
            )
        else:
            print(
                f"Recorded review: {result.verdict.decision} "
                f"({len(result.verdict.findings)} findings)"
            )
            print(f"Artifacts: {path}")
        return EXIT_CODES[result.verdict.decision]
    except ValidationError:
        # Pydantic diagnostics include raw rejected values; do not echo inputs.
        print("mos-eisley: invalid input schema", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(
            f"mos-eisley: {type(error).__name__}: input or artifact validation failed",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
