"""Inspect proposed launch conformance with current guidance and fresh evidence."""

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import cast

from mos_eisley import review_launch_cli
from mos_eisley.core.models import digest
from mos_eisley.run.files import read_bounded
from mos_eisley.run.review_campaign import CAMPAIGN_BYTES, decode_campaign_submission
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_launch import (
    CONFIGURATION_BYTES,
    decode_launch_configuration,
)
from mos_eisley.run.review_launch_conformance import check_review_launch_conformance


def add_arguments(command: argparse.ArgumentParser) -> None:
    review_launch_cli.add_arguments(command)
    command.add_argument("--expected-config-sha256", required=True)
    command.add_argument("--campaign-dir", type=Path, required=True)
    command.add_argument("--expected-seal-sha256", required=True)
    command.add_argument("--evidence", type=Path, required=True)
    command.add_argument("--expected-evidence-sha256", required=True)
    command.add_argument("--image-id", required=True)


def run_command(args: argparse.Namespace) -> int:
    try:
        return _run(args)
    except sqlite3.Error:
        raise ValueError("selected conformance ledger is unavailable") from None


def _run(args: argparse.Namespace) -> int:
    config_raw = read_bounded(cast(Path, args.config), CONFIGURATION_BYTES)
    evidence_raw = read_bounded(cast(Path, args.evidence), CAMPAIGN_BYTES)
    if (
        digest(config_raw) != args.expected_config_sha256
        or digest(evidence_raw) != args.expected_evidence_sha256
    ):
        raise ValueError("selected launch conformance input changed")
    configuration = decode_launch_configuration(config_raw)
    submission = decode_campaign_submission(evidence_raw)
    runtime = ReviewConformanceRuntime(
        sdk_version=version("openai"), image_id=cast(str, args.image_id)
    )
    preview = review_launch_cli.prepare_from_arguments(args, configuration)
    result = check_review_launch_conformance(
        configuration,
        preview,
        cast(Path, args.campaign_dir),
        cast(str, args.expected_seal_sha256),
        submission,
        runtime=runtime,
        now=datetime.now(UTC),
    )
    print(
        json.dumps(
            {
                "type": "review.launch.conformance.check",
                **result.model_dump(mode="json"),
            },
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return 0 if result.conformance.status == "accepted" else 1
