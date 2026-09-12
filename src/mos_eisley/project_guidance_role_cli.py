"""Preview, freeze and inspect explicitly scoped local role-guidance contexts."""

import argparse
import json
from pathlib import Path

from mos_eisley.project_guidance_role_store import RoleGuidanceStore


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument("action", choices=("freeze", "show"))
    command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    command.add_argument("--input", type=Path)
    command.add_argument("--policy", type=Path)
    command.add_argument("--expected-policy-sha256")
    command.add_argument("--snapshot-sha256")
    command.add_argument("--apply", action="store_true")
    command.add_argument("--expected-sha256")
    command.add_argument(
        "--guidance-storage", type=Path, default=Path.home() / ".mos-eisley-guidance"
    )
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    store = RoleGuidanceStore(args.guidance_storage)
    if args.action == "show":
        if (
            args.snapshot_sha256 is None
            or args.input is not None
            or args.policy is not None
            or args.expected_policy_sha256 is not None
            or args.apply
            or args.expected_sha256 is not None
        ):
            raise ValueError(
                "Show requires only a snapshot hash and project/storage selection."
            )
        receipt = store.show_context(args.workspace, args.snapshot_sha256)
    else:
        if (
            args.input is None
            or args.policy is None
            or args.expected_policy_sha256 is None
            or args.snapshot_sha256 is not None
            or args.apply != (args.expected_sha256 is not None)
        ):
            raise ValueError(
                "Freeze requires selection and policy/hash; "
                "apply needs the reviewed hash."
            )
        receipt = store.freeze_context(
            args.workspace,
            args.input,
            args.policy,
            args.expected_policy_sha256,
            expected_sha256=args.expected_sha256,
        )
    print(
        json.dumps(
            {"type": "guidance.role_context", **receipt},
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return 0
