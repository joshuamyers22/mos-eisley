"""Offline owner-attested G4 review assembly and exact evidence replay."""

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
    build_review_subject,
    decode_review_artifact,
)
from mos_eisley.reviewer_single_operator_review import (
    G4SingleOperatorCriticObservation,
    G4SingleOperatorJudgeObservation,
    G4SingleOperatorReviewRecord,
    SignedG4SingleOperatorReviewAuthority,
    SignedG4SingleOperatorReviewDecision,
    assess_single_operator_review,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    reviewer_final_suites_cli.add_arguments(command, "g4-verify-final-whole-suites")
    command.add_argument("--approved-plan", type=Path, required=True)
    if name == "g4-assemble-single-operator-review":
        command.add_argument("--authority", type=Path, required=True)
        command.add_argument("--critic", type=Path, action="append", required=True)
        command.add_argument("--judge", type=Path, required=True)
        command.add_argument("--decision", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    else:
        command.add_argument("--review-record", type=Path, required=True)


def run_command(args: argparse.Namespace) -> int:
    reviewer_final_suites_cli._check_paths(args)
    assembling = args.command == "g4-assemble-single-operator-review"
    critic_paths = cast(list[Path], getattr(args, "critic", None) or [])
    if assembling and not 2 <= len(critic_paths) <= 8:
        raise ValueError("G4 one-signer review needs two to eight critic observations")
    root = cast(Path, args.repository_root).resolve()
    artifacts = [cast(Path, args.approved_plan)]
    for name in ("authority", "judge", "decision", "output", "review_record"):
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
    subject = build_review_subject(
        final_receipt=final_receipt,
        approved_plan_path=cast(Path, args.approved_plan),
        **common,
    )
    if assembling:
        authority = decode_review_artifact(
            read_bounded(cast(Path, args.authority), REVIEW_RECORD_BYTES),
            SignedG4SingleOperatorReviewAuthority,
        )
        critics = tuple(
            decode_review_artifact(
                read_bounded(path, REVIEW_RECORD_BYTES),
                G4SingleOperatorCriticObservation,
            )
            for path in critic_paths
        )
        judge = decode_review_artifact(
            read_bounded(cast(Path, args.judge), REVIEW_RECORD_BYTES),
            G4SingleOperatorJudgeObservation,
        )
        decision = decode_review_artifact(
            read_bounded(cast(Path, args.decision), REVIEW_RECORD_BYTES),
            SignedG4SingleOperatorReviewDecision,
        )
        record = assess_single_operator_review(
            subject, common["provenance"], authority, critics, judge, decision
        )
        path = cast(Path, args.output)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_write(path, canonical_bytes(record))
        event = "g4.single_operator_review.assembled"
    else:
        path = cast(Path, args.review_record)
        record = decode_review_artifact(
            read_bounded(path, REVIEW_RECORD_BYTES), G4SingleOperatorReviewRecord
        )
        if record.subject != subject or record != assess_single_operator_review(
            subject,
            common["provenance"],
            record.authority,
            record.critics,
            record.judge,
            record.decision,
        ):
            raise ValueError(
                "G4 one-signer review record differs from current evidence"
            )
        event = "g4.single_operator_review.verified"
    print(
        json.dumps(
            {
                "event": event,
                "path": str(path),
                "record_sha256": record.record_sha256,
                "decision": record.decision.decision.verdict.decision,
                "single_operator_review_evidence_passed": (
                    record.single_operator_review_evidence_passed
                ),
                "independent_review_evidence_passed": False,
                "acceptance_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0 if record.single_operator_review_evidence_passed else 1
