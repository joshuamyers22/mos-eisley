"""Compare a fresh G6-06 offline index with a separately frozen baseline."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.store import private_write
from tools.g6_06_full_offline import FullOfflineResultIndex


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def suite_manifest_sha256(index: FullOfflineResultIndex) -> str:
    """Hash ordered suite identities, case identities and expected counts."""
    return digest(
        canonical_bytes(
            SuiteManifest(
                suites=tuple(
                    SuiteExpectation(
                        suite_id=item.suite_id,
                        case_ids_sha256=item.case_ids_sha256,
                        expected_case_count=item.expected_case_count,
                    )
                    for item in index.suites
                )
            )
        )
    )


class SuiteExpectation(Contract):
    suite_id: Identifier
    case_ids_sha256: Digest
    expected_case_count: int


class SuiteManifest(Contract):
    schema_version: Literal[1] = 1
    suites: tuple[SuiteExpectation, ...]


class FrozenReproductionAnchor(Contract):
    """Out-of-band baseline metadata retained before the replay starts."""

    schema_version: Literal[1] = 1
    baseline_index_sha256: Digest
    bound_source_set_sha256: Digest
    suite_manifest_sha256: Digest
    pyproject_sha256: Digest
    uv_lock_sha256: Digest
    runner_sha256: Digest
    broker_build_sha256: Digest
    protocol_sha256: Digest
    command_sha256: Digest
    baseline_producer_id: Identifier
    baseline_host_id: Identifier
    expected_reproducer_id: Identifier
    expected_replay_host_id: Identifier
    frozen_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def ordered_window(self) -> FrozenReproductionAnchor:
        if not (_utc(self.frozen_at) and _utc(self.expires_at)):
            raise ValueError("anchor times must have UTC offsets")
        if self.frozen_at >= self.expires_at:
            raise ValueError("anchor window is empty")
        return self


class ReproductionRecord(Contract):
    """Reproducer-supplied metadata; identities and host claims are unauthenticated."""

    schema_version: Literal[1] = 1
    baseline_index_sha256: Digest
    replay_index_sha256: Digest
    bound_source_set_sha256: Digest
    suite_manifest_sha256: Digest
    broker_build_sha256: Digest
    protocol_sha256: Digest
    command_sha256: Digest
    reproducer_id: Identifier
    host_id: Identifier
    reproduced_at: datetime


class ReproductionAssessment(Contract):
    schema_version: Literal[1] = 1
    status: Literal["metadata_match", "blocked"]
    reasons: tuple[str, ...]
    anchor_sha256: Digest
    record_sha256: Digest
    baseline_index_sha256: Digest
    replay_index_sha256: Digest
    source_file_count: int
    suite_count: int
    case_count: int
    independent_reproduced: Literal[False] = False
    target_build_verified: Literal[False] = False
    cohort_release_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False
    assessment_authorized: Literal[False] = False


def validate_reproduction_handoff(
    *,
    anchor: FrozenReproductionAnchor,
    record: ReproductionRecord,
    baseline: FullOfflineResultIndex,
    replay: FullOfflineResultIndex,
    now: datetime,
) -> ReproductionAssessment:
    """Fail closed on any index, digest, suite, source, time or identity mismatch."""
    reasons: set[str] = set()
    if not _utc(now) or not _utc(record.reproduced_at):
        reasons.add("time_invalid")
    for label, index in (("baseline", baseline), ("replay", replay)):
        try:
            FullOfflineResultIndex.model_validate_json(index.model_dump_json())
        except ValidationError:
            reasons.add(f"{label}_index_invalid")
        if not _utc(index.generated_at):
            reasons.add(f"{label}_time_invalid")
        if index.status != "synthetic_pass" or not index.source_stable:
            reasons.add(f"{label}_not_passing")

    baseline_sha = digest(canonical_bytes(baseline))
    replay_sha = digest(canonical_bytes(replay))
    if (
        baseline_sha != anchor.baseline_index_sha256
        or baseline_sha != record.baseline_index_sha256
    ):
        reasons.add("baseline_digest_mismatch")
    if replay_sha != record.replay_index_sha256 or replay_sha == baseline_sha:
        reasons.add("replay_digest_mismatch")
    if (
        baseline.bound_source_set_sha256 != anchor.bound_source_set_sha256
        or replay.bound_source_set_sha256 != anchor.bound_source_set_sha256
        or record.bound_source_set_sha256 != anchor.bound_source_set_sha256
        or baseline.source_files != replay.source_files
    ):
        reasons.add("source_mismatch")
    baseline_suite_sha = suite_manifest_sha256(baseline)
    replay_suite_sha = suite_manifest_sha256(replay)
    if (
        baseline_suite_sha != anchor.suite_manifest_sha256
        or replay_suite_sha != anchor.suite_manifest_sha256
        or record.suite_manifest_sha256 != anchor.suite_manifest_sha256
        or baseline.suites != replay.suites
    ):
        reasons.add("suite_mismatch")
    source_map = {item.relative_path: item.sha256 for item in baseline.source_files}
    for relative, expected, reason in (
        ("pyproject.toml", anchor.pyproject_sha256, "pyproject_mismatch"),
        ("uv.lock", anchor.uv_lock_sha256, "lock_mismatch"),
        ("tools/g6_06_full_offline.py", anchor.runner_sha256, "runner_mismatch"),
    ):
        if source_map.get(relative) != expected:
            reasons.add(reason)
    for name in ("broker_build_sha256", "protocol_sha256", "command_sha256"):
        if getattr(anchor, name) != getattr(record, name):
            reasons.add(name.removesuffix("_sha256") + "_mismatch")
    if (
        record.reproducer_id != anchor.expected_reproducer_id
        or record.reproducer_id == anchor.baseline_producer_id
    ):
        reasons.add("reproducer_mismatch")
    if (
        record.host_id != anchor.expected_replay_host_id
        or record.host_id == anchor.baseline_host_id
    ):
        reasons.add("host_mismatch")
    if not reasons.intersection(
        {"time_invalid", "baseline_time_invalid", "replay_time_invalid"}
    ) and not (
        baseline.generated_at
        <= anchor.frozen_at
        < replay.generated_at
        <= record.reproduced_at
        <= now
        < anchor.expires_at
    ):
        reasons.add("window_mismatch")
    return ReproductionAssessment(
        status="blocked" if reasons else "metadata_match",
        reasons=tuple(sorted(reasons)),
        anchor_sha256=digest(canonical_bytes(anchor)),
        record_sha256=digest(canonical_bytes(record)),
        baseline_index_sha256=baseline_sha,
        replay_index_sha256=replay_sha,
        source_file_count=len(replay.source_files),
        suite_count=len(replay.suites),
        case_count=sum(item.ran_count for item in replay.suites),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("anchor", type=Path)
    parser.add_argument("baseline_index", type=Path)
    parser.add_argument("replay_index", type=Path)
    parser.add_argument("record", type=Path)
    parser.add_argument("output", type=Path, help="new private assessment JSON path")
    args = parser.parse_args(argv)
    try:
        anchor = FrozenReproductionAnchor.model_validate_json(args.anchor.read_bytes())
        baseline = FullOfflineResultIndex.model_validate_json(
            args.baseline_index.read_bytes()
        )
        replay = FullOfflineResultIndex.model_validate_json(
            args.replay_index.read_bytes()
        )
        record = ReproductionRecord.model_validate_json(args.record.read_bytes())
    except (OSError, ValidationError, ValueError):
        print("blocked: invalid input")
        return 1
    assessment = validate_reproduction_handoff(
        anchor=anchor,
        baseline=baseline,
        replay=replay,
        record=record,
        now=datetime.now(UTC),
    )
    private_write(args.output, (assessment.model_dump_json(indent=2) + "\n").encode())
    print(f"{assessment.status}: {len(assessment.reasons)} mismatch categories")
    return 0 if assessment.status == "metadata_match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
