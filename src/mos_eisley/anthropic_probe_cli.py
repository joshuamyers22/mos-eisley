"""Small CLI entry point for the fixed credentialed Claude probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley.run.anthropic_probe import run_from_paths


def run_command(args: argparse.Namespace) -> int:
    if not cast(bool, args.allow_data_transfer):
        raise ValueError("Anthropic synthetic data transfer was not acknowledged")
    result = run_from_paths(
        policy_path=cast(Path, args.spend_policy),
        ledger_path=cast(Path, args.spend_ledger),
        key_path=cast(Path, args.key_file),
        output_dir=cast(Path, args.output_dir),
    )
    print(
        json.dumps(
            {
                "type": "anthropic.probe.completed",
                "receipt_sha256": result.response_sha256,
                "provider_request_id": result.provider_request_id,
                "settled_microusd": result.settled_microusd,
                "credentialed_exchange_observed": result.credentialed_exchange_observed,
                "review_role_conformance_proven": result.review_role_conformance_proven,
            }
        )
    )
    return 0
