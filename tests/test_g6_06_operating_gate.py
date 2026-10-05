"""Synthetic G606-04 operating-gate packet and fault denials."""

from __future__ import annotations

import io
import stat
from contextlib import redirect_stdout
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.core.models import digest
from mos_eisley.run.routing_host_drills import HostDrillEvidenceIndex, HostDrillProtocol
from mos_eisley.run.witnessed_admission import CohortManifest, TaskSessionBinding
from tests import test_routing_host_drills as host_fixture
from tools.g6_06_operating_gate import (
    CLAIM_ALLOWED_FAULTS,
    COHORT_FAULTS,
    FULL_EXPOSURE_FAULTS,
    NO_ASSIGNMENT_FAULTS,
    ONE_ENTRY_FAULTS,
    REQUIRED_CASES,
    STOP_FAULTS,
    CaseSourceReview,
    CohortDrillEvidenceIndex,
    CohortDrillProtocol,
    CohortFaultObservation,
    CohortFaultOracle,
    FrozenOperatingGateAnchor,
    OperatingGateAssessment,
    OperatingGateReviewPacket,
    OperatingLimits,
    case_observations_digest,
    main,
    validate_operating_gate,
)


def _sha(label: str) -> str:
    return digest(label.encode())


@dataclass(frozen=True)
class Fixture:
    anchor: FrozenOperatingGateAnchor
    manifest: CohortManifest
    host_protocol: HostDrillProtocol
    host_evidence: HostDrillEvidenceIndex
    cohort_protocol: CohortDrillProtocol
    cohort_evidence: CohortDrillEvidenceIndex
    reviews: OperatingGateReviewPacket
    now: datetime


def _fixture() -> Fixture:
    host = host_fixture.HostDrillIndexTests(
        "test_full_synthetic_index_is_only_reviewable"
    )
    host.setUp()
    now = host.now
    manifest = CohortManifest(
        owner_id="owner",
        cohort_id="cohort",
        witness_epoch_id=_sha("epoch"),
        witness_enrollment_sha256=_sha("enrollment"),
        budget_policy_sha256=_sha("budget"),
        candidate_policy_sha256=_sha("policy"),
        promotion_receipt_sha256=_sha("promotion"),
        broker_build_sha256=host.protocol.broker_build_sha256,
        target_host_id=host.protocol.target_host_id,
        tasks=(TaskSessionBinding(task_id="task", session_id="session"),),
        stages=("stage",),
        max_assignments=1,
        max_concurrent=1,
        valid_from=now - timedelta(hours=3),
        valid_until=now + timedelta(hours=3),
    )
    limits = OperatingLimits(
        max_assignments=1,
        max_concurrent=1,
        task_ceiling_microusd=1000,
        session_ceiling_microusd=1000,
        cohort_ceiling_microusd=3000,
        request_maximum_microusd=500,
        warning_exposure_microusd=1000,
        hard_stop_exposure_microusd=2000,
        observation_cadence_ms=100,
        queue_capacity=10,
        retention_seconds=86400,
        max_stop_latency_ms=1000,
        max_alert_latency_ms=2000,
    )
    protocol = CohortDrillProtocol(
        manifest_sha256=manifest.manifest_sha256,
        qualification_packet_sha256=host.protocol.qualification_packet_sha256,
        g6_05_go_sha256=_sha("go"),
        broker_build_sha256=manifest.broker_build_sha256,
        target_host_id=manifest.target_host_id,
        witness_epoch_id=manifest.witness_epoch_id,
        host_protocol_sha256=host.protocol.protocol_sha256,
        host_evidence_sha256=host.evidence.evidence_sha256,
        test_protocol_sha256=_sha("c-protocol"),
        operator_id="operator",
        checker_id="checker",
        frozen_at=now - timedelta(seconds=50),
        valid_until=now + timedelta(hours=1),
        max_workers=4,
        max_crash_cases=20,
        max_synthetic_admissions=60,
        limits=limits,
        oracles=tuple(
            CohortFaultOracle(
                case_id=case,
                fault_id=fault,
                expected_status="one_entry" if key in ONE_ENTRY_FAULTS else "deny",  # type: ignore[arg-type]
                expected_state_sha256=_sha(f"state:{case}:{fault}"),
                max_assignments_created=0 if key in NO_ASSIGNMENT_FAULTS else 1,
                max_claims_created=1 if key in CLAIM_ALLOWED_FAULTS else 0,
                max_intents_created=1 if key in ONE_ENTRY_FAULTS else 0,
                max_transport_entries=1 if key in ONE_ENTRY_FAULTS else 0,
                min_retained_exposure_microusd=500
                if key in FULL_EXPOSURE_FAULTS
                else 0,
            )
            for case, faults in COHORT_FAULTS.items()
            for fault in faults
            for key in ((case, fault),)
        ),
    )
    evidence = CohortDrillEvidenceIndex(
        protocol_sha256=protocol.protocol_sha256,
        manifest_sha256=manifest.manifest_sha256,
        broker_build_sha256=manifest.broker_build_sha256,
        target_host_id=manifest.target_host_id,
        witness_epoch_id=manifest.witness_epoch_id,
        assembled_at=now - timedelta(seconds=20),
        workers_used=2,
        crash_cases_run=6,
        synthetic_admissions=20,
        measured_max_stop_latency_ms=500,
        measured_max_alert_latency_ms=900,
        observations=tuple(
            CohortFaultObservation(
                case_id=oracle.case_id,
                fault_id=oracle.fault_id,
                status="pass",
                observed_status=oracle.expected_status,
                expected_state_sha256=oracle.expected_state_sha256,
                source_sha256=_sha(f"source:{oracle.case_id}:{oracle.fault_id}"),
                producer_id="operator",
                checker_id="checker",
                observed_at=now - timedelta(seconds=30),
                assignments_created=1
                if key in CLAIM_ALLOWED_FAULTS or key == ("C03", "killed_assignment")
                else 0,
                claims_created=1 if key in CLAIM_ALLOWED_FAULTS else 0,
                intents_created=1 if key in ONE_ENTRY_FAULTS else 0,
                transport_entries=1 if key in ONE_ENTRY_FAULTS else 0,
                retained_exposure_microusd=oracle.min_retained_exposure_microusd,
                checkpoint_generation_before=1,
                checkpoint_generation_after=2 if key in STOP_FAULTS else 1,
            )
            for oracle in sorted(
                protocol.oracles, key=lambda item: (item.case_id, item.fault_id)
            )
            for key in ((oracle.case_id, oracle.fault_id),)
        ),
    )
    anchor = FrozenOperatingGateAnchor(
        manifest_sha256=manifest.manifest_sha256,
        qualification_packet_sha256=host.protocol.qualification_packet_sha256,
        g6_05_go_sha256=protocol.g6_05_go_sha256,
        g5_claim_sha256=_sha("g5"),
        g6_01_04_review_sha256=_sha("g6-reviews"),
        broker_build_sha256=manifest.broker_build_sha256,
        target_host_id=manifest.target_host_id,
        witness_epoch_id=manifest.witness_epoch_id,
        witness_deployment_id=host.protocol.witness_deployment_id,
        expected_reviewer_id="reviewer",
        host_protocol_sha256=host.protocol.protocol_sha256,
        host_evidence_sha256=host.evidence.evidence_sha256,
        cohort_protocol_sha256=protocol.protocol_sha256,
        frozen_at=now - timedelta(seconds=45),
        valid_until=now + timedelta(hours=1),
    )
    reviews = OperatingGateReviewPacket(
        manifest_sha256=manifest.manifest_sha256,
        broker_build_sha256=manifest.broker_build_sha256,
        host_evidence_sha256=host.evidence.evidence_sha256,
        cohort_evidence_sha256=evidence.evidence_sha256,
        g5_claim_sha256=anchor.g5_claim_sha256,
        g6_01_04_review_sha256=anchor.g6_01_04_review_sha256,
        g6_05_go_sha256=anchor.g6_05_go_sha256,
        reviews=tuple(
            CaseSourceReview(
                case_id=case,
                decision="accept",
                case_observations_sha256=case_observations_digest(
                    tuple(
                        item
                        for item in (
                            host.evidence.observations
                            if case.startswith("O")
                            else evidence.observations
                        )
                        if item.case_id == case
                    )
                ),
                reviewer_id="reviewer",
                reviewed_at=now - timedelta(seconds=10),
                valid_until=now + timedelta(hours=1),
            )
            for case in REQUIRED_CASES
        ),
    )
    return Fixture(
        anchor,
        manifest,
        host.protocol,
        host.evidence,
        protocol,
        evidence,
        reviews,
        now,
    )


def _assess(values: Fixture) -> OperatingGateAssessment:
    return validate_operating_gate(
        anchor=values.anchor,
        manifest=values.manifest,
        host_protocol=values.host_protocol,
        host_evidence=values.host_evidence,
        cohort_protocol=values.cohort_protocol,
        cohort_evidence=values.cohort_evidence,
        reviews=values.reviews,
        now=values.now,
    )


class OperatingGateTests(TestCase):
    def test_complete_metadata_is_reviewable_without_authority(self) -> None:
        result = _assess(_fixture())
        self.assertEqual(result.status, "reviewable")
        self.assertEqual(result.reasons, ())
        self.assertEqual((result.host_case_count, result.cohort_case_count), (10, 9))
        self.assertFalse(result.target_host_verified)
        self.assertFalse(result.independent_reviews_authenticated)
        self.assertFalse(result.g6_05_go_verified)
        self.assertFalse(result.cohort_release_authorized)
        self.assertFalse(result.dispatch_authorized)
        self.assertFalse(result.assessment_authorized)

    def test_missing_and_failed_faults_block(self) -> None:
        values = _fixture()
        evidence = values.cohort_evidence
        changed = evidence.model_copy(
            update={"observations": evidence.observations[:-1]}
        )
        self.assertIn(
            "cohort_coverage_invalid",
            _assess(replace(values, cohort_evidence=changed)).reasons,
        )
        values = _fixture()
        evidence = values.host_evidence
        observations = list(evidence.observations)
        observations[0] = observations[0].model_copy(update={"status": "fail"})
        changed = evidence.model_copy(update={"observations": tuple(observations)})
        self.assertIn(
            "host_drills_blocked",
            _assess(replace(values, host_evidence=changed)).reasons,
        )

    def test_changed_manifest_build_and_go_block(self) -> None:
        for field, reason in (
            ("manifest_sha256", "manifest_mismatch"),
            ("broker_build_sha256", "manifest_mismatch"),
            ("g6_05_go_sha256", "cohort_binding_mismatch"),
        ):
            values = _fixture()
            changed = values.anchor.model_copy(update={field: _sha("changed")})
            self.assertIn(reason, _assess(replace(values, anchor=changed)).reasons)

    def test_raised_ceiling_and_fault_state_block(self) -> None:
        values = _fixture()
        protocol = values.cohort_protocol
        limits = protocol.limits.model_copy(update={"max_stop_latency_ms": 1001})
        changed = protocol.model_copy(update={"limits": limits})
        self.assertIn(
            "limit_exceeded",
            _assess(replace(values, cohort_protocol=changed)).reasons,
        )
        values = _fixture()
        evidence = values.cohort_evidence
        observations = list(evidence.observations)
        target = next(
            i
            for i, item in enumerate(observations)
            if item.fault_id == "ambiguous_claim"
        )
        observations[target] = observations[target].model_copy(
            update={"retained_exposure_microusd": 0}
        )
        changed = evidence.model_copy(update={"observations": tuple(observations)})
        self.assertIn(
            "cohort_state_invariant_failed",
            _assess(replace(values, cohort_evidence=changed)).reasons,
        )

    def test_stale_rejected_rebound_and_same_operator_reviews_block(self) -> None:
        for update in (
            {"decision": "reject"},
            {"case_observations_sha256": _sha("wrong")},
            {"reviewer_id": "operator"},
        ):
            values = _fixture()
            reviews = values.reviews
            rows = list(reviews.reviews)
            rows[0] = rows[0].model_copy(update=update)
            changed = reviews.model_copy(update={"reviews": tuple(rows)})
            self.assertIn(
                "case_review_invalid",
                _assess(replace(values, reviews=changed)).reasons,
            )
        values = _fixture()
        self.assertIn(
            "window_invalid",
            _assess(replace(values, now=values.anchor.valid_until)).reasons,
        )

    def test_missing_case_review_is_schema_error(self) -> None:
        values = _fixture()
        with self.assertRaises(ValidationError):
            OperatingGateReviewPacket.model_validate(
                values.reviews.model_copy(
                    update={"reviews": values.reviews.reviews[:-1]}
                ).model_dump()
            )

    def test_late_freeze_and_new_assignment_under_missing_go_block(self) -> None:
        values = _fixture()
        late = values.anchor.model_copy(
            update={"frozen_at": values.cohort_evidence.assembled_at}
        )
        self.assertIn(
            "cohort_window_invalid",
            _assess(replace(values, anchor=late)).reasons,
        )
        observations = list(values.cohort_evidence.observations)
        target = next(
            i
            for i, item in enumerate(observations)
            if item.case_id == "C01" and item.fault_id == "missing_go"
        )
        observations[target] = observations[target].model_copy(
            update={"assignments_created": 1}
        )
        evidence = values.cohort_evidence.model_copy(
            update={"observations": tuple(observations)}
        )
        self.assertIn(
            "cohort_state_invariant_failed",
            _assess(replace(values, cohort_evidence=evidence)).reasons,
        )

    def test_cli_writes_private_bounded_result(self) -> None:
        values = _fixture()
        with TemporaryDirectory() as directory:
            paths = [Path(directory) / f"{i}.json" for i in range(8)]
            inputs = (
                values.anchor,
                values.manifest,
                values.host_protocol,
                values.host_evidence,
                values.cohort_protocol,
                values.cohort_evidence,
                values.reviews,
            )
            for path, value in zip(paths[:7], inputs, strict=True):
                path.write_text(value.model_dump_json())
            with redirect_stdout(io.StringIO()) as output:
                code = main(
                    [*(str(path) for path in paths), "--now", values.now.isoformat()]
                )
            self.assertEqual(code, 0)
            self.assertIn("reviewable", output.getvalue())
            self.assertEqual(stat.S_IMODE(paths[-1].stat().st_mode), 0o600)
            self.assertNotIn("reviewer", paths[-1].read_text())
            self.assertNotIn("operator", paths[-1].read_text())
