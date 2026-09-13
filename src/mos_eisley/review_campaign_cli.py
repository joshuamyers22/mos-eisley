"""Offline campaign preview, explicit sealing and fresh evidence review."""

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
    decode_campaign_bundle,
    decode_campaign_submission,
    review_campaign_evidence,
    seal_review_campaign,
    validate_campaign_preflight,
)


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    if name in {"review-campaign-preview", "review-campaign-seal"}:
        command.add_argument("--bundle", type=Path, required=True)
    if name == "review-campaign-preview":
        command.add_argument("--show", action="store_true")
    elif name == "review-campaign-seal":
        command.add_argument("--expected-bundle-sha256", required=True)
        command.add_argument("--destination", type=Path, required=True)
    else:
        command.add_argument("--campaign-dir", type=Path, required=True)
        command.add_argument("--expected-seal-sha256", required=True)
        command.add_argument("--evidence", type=Path, required=True)
        command.add_argument("--expected-evidence-sha256", required=True)


def run_command(args: argparse.Namespace) -> int:
    try:
        return _run(args)
    except sqlite3.Error:
        raise ValueError("selected campaign ledger is unavailable") from None


def _run(args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    if args.command == "review-campaign-review":
        raw = read_bounded(cast(Path, args.evidence), CAMPAIGN_BYTES)
        if digest(raw) != args.expected_evidence_sha256:
            raise ValueError("campaign evidence submission changed before review")
        result = review_campaign_evidence(
            cast(Path, args.campaign_dir),
            cast(str, args.expected_seal_sha256),
            decode_campaign_submission(raw),
            now=now,
        )
        print(
            json.dumps(
                {
                    "type": "review.campaign.acceptance",
                    **result.model_dump(mode="json"),
                },
                ensure_ascii=True,
            )
        )
        return 0 if result.status == "accepted" else 1
    bundle = decode_campaign_bundle(
        read_bounded(cast(Path, args.bundle), CAMPAIGN_BYTES)
    )
    if args.command == "review-campaign-seal":
        seal = seal_review_campaign(
            bundle,
            cast(Path, args.destination),
            expected_bundle_sha256=cast(str, args.expected_bundle_sha256),
            now=now,
        )
        print(
            json.dumps(
                {
                    "type": "review.campaign.seal",
                    "seal_sha256": digest(canonical_bytes(seal)),
                    **seal.model_dump(mode="json"),
                },
                ensure_ascii=True,
            )
        )
        return 0
    validate_campaign_preflight(bundle, now)
    preview: dict[str, object] = {
        "type": "review.campaign.preview",
        "bundle_sha256": digest(canonical_bytes(bundle)),
        "policy_sha256": digest(canonical_bytes(bundle.policy)),
        "attempts": 3,
        "total_planned_microusd": sum(
            item.preview.envelope.total_reserved_microusd for item in bundle.attempts
        ),
        "runtime": bundle.policy.runtime.model_dump(mode="json"),
        "review_policy": bundle.policy.review_policy.model_dump(mode="json"),
        "provider_dispatch_authorized": False,
        "live_review_activation_authorized": False,
    }
    if args.show:
        preview["bundle"] = bundle.model_dump(mode="json")
    print(json.dumps(preview, ensure_ascii=True))
    return 0
