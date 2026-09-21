"""Explicit configuration preview; no live launch or credential access."""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import cast

from mos_eisley.project_guidance_review import (
    REVIEW_GUIDANCE_BYTES,
    decode_prepared_review,
)
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore
from mos_eisley.run.files import read_bounded
from mos_eisley.run.review_launch import (
    CONFIGURATION_BYTES,
    ReviewLaunchConfiguration,
    ReviewLaunchPreview,
    decode_launch_configuration,
    prepare_review_launch_preview,
)
from mos_eisley.run.spend_ledger import SpendLedger


def add_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--config", type=Path, required=True)
    command.add_argument("-C", "--workspace", type=Path, required=True)
    command.add_argument("--guidance-storage", type=Path, required=True)
    command.add_argument("--prepared", type=Path, required=True)
    command.add_argument("--expected-prepared-sha256", required=True)
    command.add_argument("--guidance-policy", type=Path, required=True)
    command.add_argument("--expected-guidance-policy-sha256", required=True)
    command.add_argument("--spend-ledger", type=Path, required=True)
    command.add_argument("--review-dir", type=Path, required=True)
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    configuration = decode_launch_configuration(
        read_bounded(cast(Path, args.config), CONFIGURATION_BYTES)
    )
    preview = prepare_from_arguments(args, configuration)
    print(
        json.dumps(
            {"type": "review.launch.preview", **preview.model_dump(mode="json")},
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return 0


def prepare_from_arguments(
    args: argparse.Namespace, configuration: ReviewLaunchConfiguration
) -> ReviewLaunchPreview:
    prepared = decode_prepared_review(
        read_bounded(cast(Path, args.prepared), REVIEW_GUIDANCE_BYTES)
    )
    try:
        preview = prepare_review_launch_preview(
            configuration,
            prepared=prepared,
            expected_prepared_sha256=cast(str, args.expected_prepared_sha256),
            workspace=cast(Path, args.workspace),
            guidance_store=RoleContextAdmissionStore(cast(Path, args.guidance_storage)),
            guidance_policy_path=cast(Path, args.guidance_policy),
            expected_guidance_policy_sha256=cast(
                str, args.expected_guidance_policy_sha256
            ),
            ledger=SpendLedger(cast(Path, args.spend_ledger)),
            review_directory=cast(Path, args.review_dir),
        )
    except sqlite3.Error:
        raise ValueError("selected spending ledger is unavailable") from None
    return preview
