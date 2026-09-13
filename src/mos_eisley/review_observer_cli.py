"""Read-only evidence projection for independent review, without signing keys."""

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.files import read_bounded
from mos_eisley.run.review_campaign import CAMPAIGN_BYTES, write_campaign_export
from mos_eisley.run.review_campaign_observation import (
    decode_probe_completion,
    preview_campaign_observation,
)


def add_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--campaign-dir", type=Path, required=True)
    command.add_argument("--expected-seal-sha256", required=True)
    command.add_argument("--completion", type=Path, required=True)
    command.add_argument("--expected-completion-sha256", required=True)
    command.add_argument(
        "--lifecycle-directory", type=Path, action="append", required=True
    )
    command.add_argument("--output", type=Path)
    command.add_argument("--show", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    try:
        return _run(args)
    except sqlite3.Error:
        raise ValueError("selected campaign ledger is unavailable") from None


def _run(args: argparse.Namespace) -> int:
    raw = read_bounded(cast(Path, args.completion), CAMPAIGN_BYTES)
    if digest(raw) != args.expected_completion_sha256:
        raise ValueError("campaign completion changed before observer review")
    directory = cast(Path, args.campaign_dir)
    seal_sha = cast(str, args.expected_seal_sha256)
    preview = preview_campaign_observation(
        directory,
        seal_sha,
        decode_probe_completion(raw),
        lifecycle_directories=tuple(cast(list[Path], args.lifecycle_directory)),
        now=datetime.now(UTC),
    )
    if args.output is not None:
        write_campaign_export(
            directory, seal_sha, cast(Path, args.output), canonical_bytes(preview)
        )
    report = preview.model_dump(mode="json", exclude={"unsigned_observation"})
    report.update(
        {
            "type": "review.campaign.observation.preview",
            "completion_file_sha256": digest(raw),
            "observation_sha256": preview.observation_sha256,
        }
    )
    if args.show:
        report["unsigned_observation"] = preview.unsigned_observation.model_dump(
            mode="json"
        )
    print(json.dumps(report, ensure_ascii=True))
    return 0
