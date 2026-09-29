"""Offline G4 independent-review assembly and full evidence replay CLI."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley import reviewer_final_suites_cli
from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_final_suites import (
    FINAL_SUITE_ARTIFACT_BYTES,
    G4FinalWholeSuiteReceipt,
    decode_final_suite_artifact,
)
from mos_eisley.reviewer_independent_review import (
    REVIEW_RECORD_BYTES,
    G4IndependentReviewRecord,
    SignedG4CriticAssessment,
    SignedG4IndependentReviewAuthority,
    SignedG4JudgeAssessment,
    assess_independent_review,
    build_review_subject,
    decode_review_artifact,
    verify_independent_review_record,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    reviewer_final_suites_cli.add_arguments(command, "g4-verify-final-whole-suites")
    command.add_argument("--approved-plan", type=Path, required=True)
    if name == "g4-assemble-independent-review":
        command.add_argument("--authority", type=Path, required=True)
        command.add_argument("--critic", type=Path, action="append", required=True)
        command.add_argument("--judge", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    else:
        command.add_argument("--review-record", type=Path, required=True)


def run_command(args: argparse.Namespace) -> int:
    reviewer_final_suites_cli._check_paths(args)
    critic_paths = cast(list[Path], getattr(args, "critic", None) or [])
    if (
        args.command == "g4-assemble-independent-review"
        and not 2 <= len(critic_paths) <= 8
    ):
        raise ValueError("G4 review needs between two and eight critic artifacts")
    root = cast(Path, args.repository_root).resolve()
    artifacts = [cast(Path, args.approved_plan)]
    for name in ("authority", "judge", "output", "review_record"):
        value = getattr(args, name, None)
        if value is not None:
            artifacts.append(cast(Path, value))
    artifacts.extend(critic_paths)
    resolved = tuple(path.resolve() for path in artifacts)
    if len(resolved) != len(set(resolved)) or any(
        path.is_relative_to(root) for path in resolved
    ):
        raise ValueError("G4 review artifacts must be distinct and outside Git")
    common = reviewer_final_suites_cli._common(args)
    final_receipt = decode_final_suite_artifact(
        read_bounded(cast(Path, args.receipt), FINAL_SUITE_ARTIFACT_BYTES),
        G4FinalWholeSuiteReceipt,
    )
    if args.command == "g4-assemble-independent-review":
        subject = build_review_subject(
            final_receipt=final_receipt,
            approved_plan_path=cast(Path, args.approved_plan),
            **common,
        )
        authority = decode_review_artifact(
            read_bounded(cast(Path, args.authority), REVIEW_RECORD_BYTES),
            SignedG4IndependentReviewAuthority,
        )
        critics = tuple(
            decode_review_artifact(
                read_bounded(path, REVIEW_RECORD_BYTES), SignedG4CriticAssessment
            )
            for path in critic_paths
        )
        judge = decode_review_artifact(
            read_bounded(cast(Path, args.judge), REVIEW_RECORD_BYTES),
            SignedG4JudgeAssessment,
        )
        record = assess_independent_review(
            subject, common["provenance"], authority, critics, judge
        )
        output = cast(Path, args.output)
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_write(output, canonical_bytes(record))
        event = "g4.independent_review.assembled"
        path = output
    else:
        record = decode_review_artifact(
            read_bounded(cast(Path, args.review_record), REVIEW_RECORD_BYTES),
            G4IndependentReviewRecord,
        )
        verify_independent_review_record(
            record,
            final_receipt=final_receipt,
            approved_plan_path=cast(Path, args.approved_plan),
            **common,
        )
        event = "g4.independent_review.verified"
        path = cast(Path, args.review_record)
    print(
        json.dumps(
            {
                "event": event,
                "path": str(path),
                "record_sha256": record.record_sha256,
                "decision": record.verdict.decision,
                "independent_review_evidence_passed": (
                    record.independent_review_evidence_passed
                ),
                "acceptance_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0 if record.independent_review_evidence_passed else 1
