"""Explicit private assembly of freshly verified campaign evidence; no key access."""

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.files import read_bounded
from mos_eisley.run.review_campaign import (
    CAMPAIGN_BYTES,
    decode_campaign_submission,
    write_campaign_export,
)
from mos_eisley.run.review_campaign_observation import (
    decode_observation_preview,
    decode_probe_completion,
)
from mos_eisley.run.review_campaign_submission import (
    append_campaign_observation,
    decode_signed_observation,
)


def add_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--campaign-dir", type=Path, required=True)
    command.add_argument("--expected-seal-sha256", required=True)
    for name in ("completion", "preview", "signed-observation"):
        command.add_argument(f"--{name}", type=Path, required=True)
        command.add_argument(f"--expected-{name}-sha256", required=True)
    command.add_argument("--previous-evidence", type=Path)
    command.add_argument("--expected-previous-evidence-sha256")
    command.add_argument(
        "--lifecycle-directory", type=Path, action="append", required=True
    )
    command.add_argument("--output", type=Path, required=True)


def _pinned(path: Path, expected: str) -> bytes:
    raw = read_bounded(path, CAMPAIGN_BYTES)
    if digest(raw) != expected:
        raise ValueError("campaign evidence input changed before assembly")
    return raw


def run_command(args: argparse.Namespace) -> int:
    try:
        return _run(args)
    except sqlite3.Error:
        raise ValueError("selected campaign ledger is unavailable") from None


def _run(args: argparse.Namespace) -> int:
    if (args.previous_evidence is None) != (
        args.expected_previous_evidence_sha256 is None
    ):
        raise ValueError(
            "previous campaign evidence requires its independent file hash"
        )
    completion_raw = _pinned(
        cast(Path, args.completion), cast(str, args.expected_completion_sha256)
    )
    preview_raw = _pinned(
        cast(Path, args.preview), cast(str, args.expected_preview_sha256)
    )
    signed_raw = _pinned(
        cast(Path, args.signed_observation),
        cast(str, args.expected_signed_observation_sha256),
    )
    previous = (
        None
        if args.previous_evidence is None
        else decode_campaign_submission(
            _pinned(
                cast(Path, args.previous_evidence),
                cast(str, args.expected_previous_evidence_sha256),
            )
        )
    )
    completion = decode_probe_completion(completion_raw)
    directory, seal_sha = (
        cast(Path, args.campaign_dir),
        cast(str, args.expected_seal_sha256),
    )
    appended = append_campaign_observation(
        directory,
        seal_sha,
        completion,
        decode_observation_preview(preview_raw),
        decode_signed_observation(signed_raw),
        lifecycle_directories=tuple(cast(list[Path], args.lifecycle_directory)),
        previous=previous,
        now=datetime.now(UTC),
    )
    raw = canonical_bytes(appended.submission)
    write_campaign_export(directory, seal_sha, cast(Path, args.output), raw)
    print(
        json.dumps(
            {
                "type": "review.campaign.evidence.append",
                "seal_sha256": seal_sha,
                "submission_sha256": digest(raw),
                "appended_attempt_index": completion.attempt_index,
                **appended.review.model_dump(mode="json"),
            },
            ensure_ascii=True,
        )
    )
    return 0
