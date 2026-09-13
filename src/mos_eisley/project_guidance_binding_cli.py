"""Explicit review and application of private project guidance bindings."""

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley.project_guidance_binding import BindingAction, GuidanceBindingStore


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument("action", choices=("show", "attach", "update", "detach"))
    command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    command.add_argument("--template-id")
    command.add_argument("--descriptor", type=Path)
    command.add_argument("--markdown", type=Path)
    command.add_argument("--snapshot-sha256")
    command.add_argument(
        "--guidance-storage", type=Path, default=Path.home() / ".mos-eisley-guidance"
    )
    command.add_argument("--apply", action="store_true")
    command.add_argument("--expected-sha256")
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    store = GuidanceBindingStore(args.guidance_storage)
    if args.action == "show":
        if any(
            (
                args.template_id is not None,
                args.descriptor is not None,
                args.markdown is not None,
                args.apply,
                args.expected_sha256 is not None,
            )
        ):
            raise ValueError(
                "show accepts workspace, storage, snapshot digest and output format."
            )
        receipt = store.show(args.workspace, snapshot_sha256=args.snapshot_sha256)
    else:
        if args.snapshot_sha256 is not None or args.template_id is None:
            raise ValueError(
                "Mutations require --template-id; snapshot selection is for show."
            )
        if args.apply != (args.expected_sha256 is not None):
            raise ValueError("Use --apply and --expected-sha256 together.")
        receipt = store.change(
            args.workspace,
            cast(BindingAction, args.action),
            args.template_id,
            descriptor_path=args.descriptor,
            markdown_path=args.markdown,
            expected_sha256=args.expected_sha256,
        )
    # Full review data is escaped even in pretty output; source text is not markup.
    print(
        json.dumps(
            {"type": "guidance.binding", **receipt},
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return 0
