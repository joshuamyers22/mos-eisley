"""Synthetic G6-05 target-host drill index checks; no host or provider access."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.core.models import digest
from mos_eisley.run.routing_host_drills import (
    REQUIRED_CHECKPOINT_ADVANCE_FAULTS,
    REQUIRED_CLAIM_FAULTS,
    REQUIRED_FAULTS,
    REQUIRED_FULL_EXPOSURE_FAULTS,
    REQUIRED_INTENT_FAULTS,
    REQUIRED_STATUSES,
    HostDrillEvidenceIndex,
    HostDrillObservation,
    HostDrillOracle,
    HostDrillProtocol,
    validate_inert_host_drill_index,
)


def sha(label: str) -> str:
    return digest(label.encode())


class HostDrillIndexTests(TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 27, 12, tzinfo=UTC)
        self.protocol = HostDrillProtocol(
            qualification_packet_sha256=sha("qualification"),
            broker_build_sha256=sha("build"),
            target_host_id="fixture-host",
            witness_deployment_id="fixture-witness",
            test_protocol_sha256=sha("test-protocol"),
            operator_id="operator",
            independent_checker_id="checker",
            frozen_at=self.now - timedelta(hours=2),
            valid_until=self.now + timedelta(hours=2),
            max_workers=4,
            max_crash_cases=20,
            max_synthetic_admissions=60,
            max_stop_latency_ms=1000,
            max_alert_latency_ms=2000,
            request_maximum_microusd=500,
            oracles=tuple(
                HostDrillOracle(
                    case_id=case,  # type: ignore[arg-type]
                    fault_id=fault,
                    expected_status=status,  # type: ignore[arg-type]
                    expected_state_sha256=sha(f"oracle:{case}:{fault}"),
                    max_claims=1
                    if (case, fault) in REQUIRED_CLAIM_FAULTS
                    else 0,
                    max_intents=1
                    if (case, fault) in REQUIRED_INTENT_FAULTS
                    else 0,
                    max_transport_entries=1 if status == "one_entry" else 0,
                    min_retained_exposure_microusd=500
                    if (case, fault) in REQUIRED_FULL_EXPOSURE_FAULTS
                    else 0,
                )
                for case, faults in REQUIRED_FAULTS.items()
                for fault in faults
                for status in (REQUIRED_STATUSES.get((case, fault), "deny"),)
            ),
        )
        self.evidence = HostDrillEvidenceIndex(
            protocol_sha256=self.protocol.protocol_sha256,
            qualification_packet_sha256=self.protocol.qualification_packet_sha256,
            broker_build_sha256=self.protocol.broker_build_sha256,
            target_host_id=self.protocol.target_host_id,
            witness_deployment_id=self.protocol.witness_deployment_id,
            assembled_at=self.now - timedelta(minutes=1),
            workers_used=2,
            crash_cases_run=6,
            synthetic_admissions=20,
            measured_max_stop_latency_ms=500,
            measured_max_alert_latency_ms=900,
            observations=tuple(
                HostDrillObservation(
                    case_id=oracle.case_id,
                    fault_id=oracle.fault_id,
                    status="pass",
                    observed_status=oracle.expected_status,
                    expected_state_sha256=oracle.expected_state_sha256,
                    source_sha256=sha(f"source:{oracle.case_id}:{oracle.fault_id}"),
                    producer_id="operator",
                    checker_id="checker",
                    observed_at=self.now - timedelta(minutes=10),
                    checkpoint_generation_before=1,
                    checkpoint_generation_after=2
                    if oracle.expected_status == "stop_acknowledged"
                    or (oracle.case_id, oracle.fault_id)
                    in REQUIRED_CHECKPOINT_ADVANCE_FAULTS
                    else 1,
                    claim_count=1
                    if (oracle.case_id, oracle.fault_id) in REQUIRED_CLAIM_FAULTS
                    else 0,
                    intent_count=1
                    if (oracle.case_id, oracle.fault_id) in REQUIRED_INTENT_FAULTS
                    else 0,
                    transport_entries_for_attempt=1
                    if oracle.expected_status == "one_entry"
                    else 0,
                    retained_exposure_microusd=oracle.min_retained_exposure_microusd,
                    audit_event_count=1,
                    alert_event_count=1,
                )
                for oracle in sorted(
                    self.protocol.oracles,
                    key=lambda item: (item.case_id, item.fault_id),
                )
            ),
        )

    def assess(
        self, evidence: HostDrillEvidenceIndex | None = None
    ) -> tuple[bool, tuple[str, ...]]:
        result = validate_inert_host_drill_index(
            protocol=self.protocol, evidence=evidence or self.evidence, now=self.now
        )
        self.assertFalse(result.target_host_verified)
        self.assertFalse(result.qualification_authorized)
        self.assertFalse(result.dispatch_authorized)
        return result.reviewable, result.reasons

    def test_full_synthetic_index_is_only_reviewable(self) -> None:
        self.assertEqual(self.assess(), (True, ()))
        self.assertEqual(len(self.evidence.observations), len(self.protocol.oracles))

    def test_missing_fault_cannot_be_called_complete(self) -> None:
        changed = self.evidence.model_copy(
            update={"observations": self.evidence.observations[1:]}
        )
        self.assertIn("coverage_invalid", self.assess(changed)[1])

    def test_unacknowledged_stop_and_underreported_timeout_exposure_fail(self) -> None:
        rows = list(self.evidence.observations)
        stop = next(
            i
            for i, row in enumerate(rows)
            if (row.case_id, row.fault_id) == ("O10", "operator_stop")
        )
        timeout = next(
            i
            for i, row in enumerate(rows)
            if (row.case_id, row.fault_id) == ("O08", "timeout")
        )
        rows[stop] = rows[stop].model_copy(update={"checkpoint_generation_after": 1})
        rows[timeout] = rows[timeout].model_copy(
            update={"retained_exposure_microusd": 0}
        )
        self.assertIn(
            "state_invariant_failed",
            self.assess(self.evidence.model_copy(update={"observations": tuple(rows)}))[
                1
            ],
        )

    def test_protocol_cannot_weaken_fault_specific_minimums(self) -> None:
        cases = (
            ("O03", "before_journal", {"max_claims": 1}),
            ("O03", "after_receipt", {"max_claims": 0}),
            ("O03", "after_intent", {"max_intents": 0}),
            ("O08", "invalid_price", {"min_retained_exposure_microusd": 0}),
        )
        for case_id, fault_id, update in cases:
            with self.subTest(case_id=case_id, fault_id=fault_id):
                oracles = tuple(
                    oracle.model_copy(update=update)
                    if (oracle.case_id, oracle.fault_id) == (case_id, fault_id)
                    else oracle
                    for oracle in self.protocol.oracles
                )
                with self.assertRaisesRegex(ValidationError, "minimum was weakened"):
                    HostDrillProtocol.model_validate(
                        self.protocol.model_copy(
                            update={"oracles": oracles}
                        ).model_dump()
                    )

    def test_fault_state_cannot_erase_claim_intent_checkpoint_or_exposure(
        self,
    ) -> None:
        cases = (
            ("O03", "before_journal", {"claim_count": 1}),
            ("O03", "after_journal", {"checkpoint_generation_after": 2}),
            ("O03", "after_checkpoint", {"checkpoint_generation_after": 1}),
            ("O03", "after_receipt", {"claim_count": 0}),
            ("O03", "after_intent", {"intent_count": 0}),
            ("O08", "invalid_price", {"retained_exposure_microusd": 0}),
            ("O08", "timeout", {"retained_exposure_microusd": 0}),
        )
        for case_id, fault_id, update in cases:
            with self.subTest(case_id=case_id, fault_id=fault_id):
                observations = tuple(
                    item.model_copy(update=update)
                    if (item.case_id, item.fault_id) == (case_id, fault_id)
                    else item
                    for item in self.evidence.observations
                )
                evidence = self.evidence.model_copy(
                    update={"observations": observations}
                )
                self.assertIn("state_invariant_failed", self.assess(evidence)[1])

    def test_full_exposure_faults_all_reject_zero_retention(self) -> None:
        for case_id, fault_id in REQUIRED_FULL_EXPOSURE_FAULTS:
            with self.subTest(case_id=case_id, fault_id=fault_id):
                observations = tuple(
                    item.model_copy(update={"retained_exposure_microusd": 0})
                    if (item.case_id, item.fault_id) == (case_id, fault_id)
                    else item
                    for item in self.evidence.observations
                )
                evidence = self.evidence.model_copy(
                    update={"observations": observations}
                )
                self.assertIn("state_invariant_failed", self.assess(evidence)[1])

    def test_changed_build_roles_and_deadline_fail(self) -> None:
        changed = self.evidence.model_copy(
            update={
                "broker_build_sha256": sha("different-build"),
                "measured_max_stop_latency_ms": 1001,
                "assembled_at": self.now + timedelta(minutes=1),
            }
        )
        self.assertEqual(
            set(self.assess(changed)[1]),
            {"binding_mismatch", "limit_exceeded", "window_invalid"},
        )

    def test_favorable_subset_or_oracle_substitution_fails(self) -> None:
        rows = list(self.evidence.observations)
        rows[0] = rows[0].model_copy(update={"expected_state_sha256": sha("changed")})
        rows[1] = rows[1].model_copy(update={"status": "unavailable"})
        self.assertIn(
            "oracle_not_met",
            self.assess(self.evidence.model_copy(update={"observations": tuple(rows)}))[
                1
            ],
        )

    def test_protocol_rejects_missing_fault_and_rewritten_positive_oracle(self) -> None:
        with self.assertRaises(ValidationError):
            self.protocol.model_copy(
                update={"oracles": self.protocol.oracles[:-1]}
            ).model_validate(
                self.protocol.model_copy(
                    update={"oracles": self.protocol.oracles[:-1]}
                ).model_dump()
            )
        first = self.protocol.oracles[0]
        altered = first.model_copy(update={"expected_status": "deny"})
        with self.assertRaises(ValidationError):
            HostDrillProtocol.model_validate(
                self.protocol.model_copy(
                    update={"oracles": (altered, *self.protocol.oracles[1:])}
                ).model_dump()
            )

    def test_cli_checks_bound_index_without_source_content(self) -> None:
        with TemporaryDirectory() as directory:
            protocol_path = Path(directory) / "protocol.json"
            evidence_path = Path(directory) / "evidence.json"
            protocol_path.write_text(self.protocol.model_dump_json())
            evidence_path.write_text(self.evidence.model_dump_json())
            command = [
                sys.executable,
                "-m",
                "mos_eisley.run.routing_host_drills",
                str(protocol_path),
                str(evidence_path),
                "--now",
                self.now.isoformat(),
            ]
            passed = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertTrue(json.loads(passed.stdout)["reviewable"])
            evidence_path.write_text(
                self.evidence.model_copy(
                    update={"observations": self.evidence.observations[:-1]}
                ).model_dump_json()
            )
            denied = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(denied.returncode, 1, denied.stderr)
            self.assertIn("coverage_invalid", json.loads(denied.stdout)["reasons"])

    def test_index_rejects_unbounded_private_content(self) -> None:
        payload = self.evidence.model_dump(mode="json")
        payload["observations"][0]["prompt"] = "private content"
        with self.assertRaises(ValidationError):
            HostDrillEvidenceIndex.model_validate(payload)

    def test_empty_summary_cannot_stand_in_for_executed_drills(self) -> None:
        payload = self.evidence.model_dump(mode="json")
        payload["workers_used"] = 0
        payload["crash_cases_run"] = 0
        payload["synthetic_admissions"] = 0
        with self.assertRaises(ValidationError):
            HostDrillEvidenceIndex.model_validate(payload)
