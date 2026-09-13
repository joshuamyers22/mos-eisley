"""Explicit reviewed acceptance of project requirements from briefs and ADRs."""

import argparse
import json
from pathlib import Path

from mos_eisley.project_requirement_store import RequirementStore


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument("action", choices=("show", "set", "clear"))
    command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    command.add_argument("--input", type=Path)
    command.add_argument("--source", type=Path, action="append", default=[])
    command.add_argument("--snapshot-sha256")
    command.add_argument(
        "--guidance-storage", type=Path, default=Path.home() / ".mos-eisley-guidance"
    )
    command.add_argument("--apply", action="store_true")
    command.add_argument("--expected-sha256")
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    store = RequirementStore(args.guidance_storage)
    if args.action == "show":
        if (
            args.input is not None
            or args.source
            or args.apply
            or args.expected_sha256 is not None
        ):
            raise ValueError("Read-only inspection does not accept mutation options.")
        receipt = store.show(args.workspace, snapshot_sha256=args.snapshot_sha256)
    else:
        if (args.action == "set") != (
            args.input is not None
        ) or args.snapshot_sha256 is not None:
            raise ValueError(
                "set requires --input; clear accepts no input or snapshot."
            )
        if args.apply != (args.expected_sha256 is not None):
            raise ValueError("Use --apply and --expected-sha256 together.")
        receipt = store.change(
            args.workspace,
            args.input,
            tuple(args.source),
            expected_sha256=args.expected_sha256,
        )
    print(
        json.dumps(
            {"type": "project.requirements", **receipt},
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return 0
