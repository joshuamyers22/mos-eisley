"""Read-only checks against explicitly selected owner-private guidance policy."""

import argparse
import json
from pathlib import Path

from mos_eisley.project_guidance_policy import GuidancePolicyCheckStore


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    command.add_argument("--policy", type=Path, required=True)
    command.add_argument("--expected-policy-sha256", required=True)
    command.add_argument(
        "--guidance-storage", type=Path, default=Path.home() / ".mos-eisley-guidance"
    )
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    receipt = GuidancePolicyCheckStore(args.guidance_storage).check_policy(
        args.workspace, args.policy, args.expected_policy_sha256
    )
    print(
        json.dumps(
            {"type": "guidance.policy_check", **receipt},
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return 0 if receipt["guidance_selection_allowed"] else 3
