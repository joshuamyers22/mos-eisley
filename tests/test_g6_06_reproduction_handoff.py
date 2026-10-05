"""Synthetic checks for the G606-03 metadata-only reproduction handoff."""

from __future__ import annotations

import io
import stat
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.core.models import canonical_bytes, digest
from tools.g6_06_full_offline import (
    PROJECT_ROOT,
    SUITES,
    bound_source_files,
    make_index,
)
from tools.g6_06_r0_offline import R0SuiteResult
from tools.g6_06_reproduction_handoff import (
    FrozenReproductionAnchor,
    ReproductionRecord,
    main,
    suite_manifest_sha256,
    validate_reproduction_handoff,
)


def _fixture():  # type: ignore[no-untyped-def]
    files = bound_source_files(PROJECT_ROOT)
    suites = tuple(
        R0SuiteResult(
            suite_id=suite_id,
            case_ids_sha256=digest(suite_id.encode()),
            expected_case_count=1,
            ran_count=1,
            failure_count=0,
            error_count=0,
            skipped_count=0,
            expected_failure_count=0,
            unexpected_success_count=0,
            status="synthetic_pass",
        )
        for suite_id, _ in SUITES
    )
    starting = make_index(files=files, results=suites, source_stable=True)
    t0 = datetime(2026, 9, 27, 12, tzinfo=UTC)
    baseline = starting.model_copy(update={"generated_at": t0})
    replay = starting.model_copy(update={"generated_at": t0 + timedelta(minutes=2)})
    paths = {item.relative_path: item.sha256 for item in files}
    anchor = FrozenReproductionAnchor(
        baseline_index_sha256=digest(canonical_bytes(baseline)),
        bound_source_set_sha256=baseline.bound_source_set_sha256,
        suite_manifest_sha256=suite_manifest_sha256(baseline),
        pyproject_sha256=paths["pyproject.toml"],
        uv_lock_sha256=paths["uv.lock"],
        runner_sha256=paths["tools/g6_06_full_offline.py"],
        broker_build_sha256=digest(b"synthetic-build"),
        protocol_sha256=digest(b"synthetic-protocol"),
        command_sha256=digest(b"synthetic-command"),
        baseline_producer_id="producer-a",
        baseline_host_id="producer-host",
        expected_reproducer_id="reviewer-b",
        expected_replay_host_id="synthetic-host",
        frozen_at=t0 + timedelta(minutes=1),
        expires_at=t0 + timedelta(hours=1),
    )
    record = ReproductionRecord(
        baseline_index_sha256=anchor.baseline_index_sha256,
        replay_index_sha256=digest(canonical_bytes(replay)),
        bound_source_set_sha256=anchor.bound_source_set_sha256,
        suite_manifest_sha256=anchor.suite_manifest_sha256,
        broker_build_sha256=anchor.broker_build_sha256,
        protocol_sha256=anchor.protocol_sha256,
        command_sha256=anchor.command_sha256,
        reproducer_id="reviewer-b",
        host_id="synthetic-host",
        reproduced_at=t0 + timedelta(minutes=3),
    )
    return anchor, record, baseline, replay, t0 + timedelta(minutes=4)


class ReproductionHandoffTests(TestCase):
    def test_exact_replay_is_only_a_metadata_match(self) -> None:
        anchor, record, baseline, replay, now = _fixture()
        result = validate_reproduction_handoff(
            anchor=anchor, record=record, baseline=baseline, replay=replay, now=now
        )
        self.assertEqual(result.status, "metadata_match")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.anchor_sha256, digest(canonical_bytes(anchor)))
        self.assertEqual(result.record_sha256, digest(canonical_bytes(record)))
        self.assertEqual(result.source_file_count, len(baseline.source_files))
        self.assertEqual(result.case_count, len(SUITES))
        self.assertFalse(result.independent_reproduced)
        self.assertFalse(result.target_build_verified)
        self.assertFalse(result.cohort_release_authorized)
        self.assertFalse(result.dispatch_authorized)
        self.assertFalse(result.assessment_authorized)

    def test_changed_source_and_locked_inputs_block(self) -> None:
        anchor, record, baseline, replay, now = _fixture()
        files = list(replay.source_files)
        files[0] = files[0].model_copy(update={"sha256": digest(b"changed")})
        changed = replay.model_copy(update={"source_files": tuple(files)})
        result = validate_reproduction_handoff(
            anchor=anchor, record=record, baseline=baseline, replay=changed, now=now
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("replay_index_invalid", result.reasons)
        self.assertIn("source_mismatch", result.reasons)
        self.assertIn(
            "lock_mismatch",
            validate_reproduction_handoff(
                anchor=anchor.model_copy(update={"uv_lock_sha256": digest(b"wrong")}),
                record=record,
                baseline=baseline,
                replay=replay,
                now=now,
            ).reasons,
        )
        self.assertIn(
            "runner_mismatch",
            validate_reproduction_handoff(
                anchor=anchor.model_copy(update={"runner_sha256": digest(b"wrong")}),
                record=record,
                baseline=baseline,
                replay=replay,
                now=now,
            ).reasons,
        )

    def test_changed_case_identity_count_and_missing_suite_block(self) -> None:
        anchor, record, baseline, replay, now = _fixture()
        for change in (
            {"case_ids_sha256": digest(b"other-case")},
            {"expected_case_count": 2, "ran_count": 2},
        ):
            suites = list(replay.suites)
            suites[0] = suites[0].model_copy(update=change)
            changed = replay.model_copy(update={"suites": tuple(suites)})
            result = validate_reproduction_handoff(
                anchor=anchor, record=record, baseline=baseline, replay=changed, now=now
            )
            self.assertIn("suite_mismatch", result.reasons)
        missing = replay.model_copy(update={"suites": replay.suites[:-1]})
        result = validate_reproduction_handoff(
            anchor=anchor, record=record, baseline=baseline, replay=missing, now=now
        )
        self.assertIn("replay_index_invalid", result.reasons)

    def test_build_protocol_command_and_identity_claims_block(self) -> None:
        anchor, record, baseline, replay, now = _fixture()
        for field in ("broker_build_sha256", "protocol_sha256", "command_sha256"):
            changed = record.model_copy(update={field: digest(b"changed")})
            result = validate_reproduction_handoff(
                anchor=anchor, record=changed, baseline=baseline, replay=replay, now=now
            )
            self.assertEqual(result.status, "blocked")
        changed = record.model_copy(
            update={"reproducer_id": anchor.baseline_producer_id}
        )
        result = validate_reproduction_handoff(
            anchor=anchor, record=changed, baseline=baseline, replay=replay, now=now
        )
        self.assertIn("reproducer_mismatch", result.reasons)
        changed = record.model_copy(update={"host_id": anchor.baseline_host_id})
        result = validate_reproduction_handoff(
            anchor=anchor, record=changed, baseline=baseline, replay=replay, now=now
        )
        self.assertIn("host_mismatch", result.reasons)

    def test_stale_and_reused_replay_block(self) -> None:
        anchor, record, baseline, replay, now = _fixture()
        for changed_record, changed_replay, changed_now in (
            (record, baseline, now),
            (
                record,
                replay.model_copy(update={"generated_at": baseline.generated_at}),
                now,
            ),
            (record, replay, anchor.expires_at),
            (
                record.model_copy(update={"reproduced_at": anchor.frozen_at}),
                replay,
                now,
            ),
        ):
            result = validate_reproduction_handoff(
                anchor=anchor,
                record=changed_record,
                baseline=baseline,
                replay=changed_replay,
                now=changed_now,
            )
            self.assertEqual(result.status, "blocked")

    def test_cli_writes_private_metadata_only_assessment(self) -> None:
        anchor, record, baseline, replay, now = _fixture()
        # Keep the synthetic fixture window current for this CLI-only test.
        shift = datetime.now(UTC) - now
        baseline = baseline.model_copy(
            update={"generated_at": baseline.generated_at + shift}
        )
        replay = replay.model_copy(update={"generated_at": replay.generated_at + shift})
        anchor = anchor.model_copy(
            update={
                "baseline_index_sha256": digest(canonical_bytes(baseline)),
                "frozen_at": anchor.frozen_at + shift,
                "expires_at": anchor.expires_at + shift,
            }
        )
        record = record.model_copy(
            update={
                "baseline_index_sha256": anchor.baseline_index_sha256,
                "replay_index_sha256": digest(canonical_bytes(replay)),
                "reproduced_at": record.reproduced_at + shift,
            }
        )
        with TemporaryDirectory() as directory:
            paths = [
                Path(directory) / f"{name}.json"
                for name in ("anchor", "baseline", "replay", "record", "assessment")
            ]
            for path, value in zip(
                paths[:4], (anchor, baseline, replay, record), strict=True
            ):
                path.write_text(value.model_dump_json())
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main([str(path) for path in paths]), 0)
            self.assertIn("metadata_match", output.getvalue())
            self.assertEqual(stat.S_IMODE(paths[-1].stat().st_mode), 0o600)
            contents = paths[-1].read_text()
            self.assertNotIn("synthetic-host", contents)
            self.assertNotIn("reviewer-b", contents)
            with redirect_stdout(io.StringIO()), self.assertRaises(FileExistsError):
                main([str(path) for path in paths])
