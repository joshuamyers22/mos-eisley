"""Review combined requirement and advisory conflicts without changing policy."""

import argparse
import json
from pathlib import Path

from mos_eisley.project_guidance_precedence_store import ProjectAssessmentStore


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument("action", choices=("show", "effective", "set", "clear"))
    command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    command.add_argument("--input", type=Path)
    command.add_argument("--snapshot-sha256")
    command.add_argument(
        "--guidance-storage", type=Path, default=Path.home() / ".mos-eisley-guidance"
    )
    command.add_argument("--apply", action="store_true")
    command.add_argument("--expected-sha256")
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    store = ProjectAssessmentStore(args.guidance_storage)
    if args.action in {"show", "effective"}:
        if args.input is not None or args.apply or args.expected_sha256 is not None:
            raise ValueError("Read-only inspection does not accept mutation options.")
        receipt = store.show_assessment(
            args.workspace,
            snapshot_sha256=args.snapshot_sha256,
            effective=args.action == "effective",
        )
    else:
        if (args.action == "set") != (
            args.input is not None
        ) or args.snapshot_sha256 is not None:
            raise ValueError(
                "set requires --input; clear accepts no input or snapshot."
            )
        if args.apply != (args.expected_sha256 is not None):
            raise ValueError("Use --apply and --expected-sha256 together.")
        receipt = store.change_assessment(
            args.workspace, args.input, expected_sha256=args.expected_sha256
        )
    print(
        json.dumps(
            {"type": "guidance.assessment", **receipt},
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return 0
