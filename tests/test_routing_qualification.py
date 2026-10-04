"""Synthetic G6-05 packet checks; no G5 stores or live transport are used."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.skills import PromptAsset
from mos_eisley.evaluation.models import RouteCandidate
from mos_eisley.run.routing_decision_readiness import (
    DecisionDisposition,
    G605DecisionReadinessPacket,
    SourceInspectionOutcome,
    required_decisions,
    signed_reviews_sha256,
    validate_g605_decision_readiness,
)
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
    drill_case_sha256,
    validate_joined_inert_host_drill_index,
)
from mos_eisley.run.routing_qualification import (
    ExactRouteMetadata,
    OfflineQualificationEvidence,
    OfflineQualificationPacket,
    OfflineQualificationReviewDecision,
    OfflineQualificationReviewTrust,
    QualificationAuthority,
    QualificationCandidate,
    QualificationDrillSummary,
    QualificationEvidenceRecord,
    QualificationPrerequisite,
    QualificationReviewer,
    QualificationRouteObservation,
    QualificationRuntime,
    QualificationScope,
    QualificationVerification,
    QualificationWitness,
    QualifiedRoute,
    SignedOfflineQualificationReview,
    sign_synthetic_qualification_review,
    validate_offline_qualification_packet,
)
from mos_eisley.run.routing_source_handoff import (
    G605SourceEvidenceHandoff,
    SourceEvidenceReference,
    required_source_references,
    validate_g605_source_handoff,
)


def sha(label: str) -> str:
    return digest(label.encode())


class RoutingQualificationTests(TestCase):
    now_override: datetime | None = None

    def setUp(self) -> None:
        self.now = self.now_override or datetime(2026, 9, 26, 12, tzinfo=UTC)
        self.route = RouteCandidate(
            backend="fixture",
            provider="fixture",
            model="exact",
            effort="high",
            client_version="fixture/1",
            registry_sha256=sha("registry"),
            prompt=PromptAsset(mode="inline", instructions="Synthetic fixture."),
        )
        self.packet = OfflineQualificationPacket(
            frozen_at=self.now - timedelta(days=1),
            decision_deadline=self.now + timedelta(hours=1),
            prerequisites=(
                QualificationPrerequisite(
                    milestone="G2", required=True, applicability_basis_sha256=sha("g2")
                ),
                QualificationPrerequisite(
                    milestone="G3", required=False, applicability_basis_sha256=sha("g3")
                ),
                QualificationPrerequisite(
                    milestone="G4", required=False, applicability_basis_sha256=sha("g4")
                ),
            ),
            scope=QualificationScope(
                owner_id="owner",
                cohort_id="cohort",
                task_enrollment_sha256=sha("tasks"),
                task_types=("review",),
                stages=("stage0",),
                valid_from=self.now - timedelta(days=1),
                valid_until=self.now + timedelta(days=1),
                max_tasks=10,
                task_ceiling_microusd=1000,
                session_ceiling_microusd=2000,
                cohort_ceiling_microusd=5000,
                request_maximum_microusd=500,
                unavailable_action="fail_closed",
            ),
            candidate=QualificationCandidate(
                candidate_policy_sha256=sha("policy"),
                sealed_study_sha256=sha("study"),
                plan_sha256=sha("plan"),
                feature_partition_sha256=sha("features"),
                g5_claim_sha256=sha("g5-claim"),
                g5_holdout_report_sha256=sha("g5-report"),
                g5_use_claim_sha256=sha("g5-use"),
                g5_population_id="fixture-population",
                g5_estimand_id="fixture-estimand",
                routes=(
                    QualifiedRoute(
                        identity=ExactRouteMetadata.from_candidate(
                            self.route, sha("capabilities")
                        ),
                        purpose="selected",
                        pricing_basis="fixture-basis",
                        max_normalized_cost_microusd=1000,
                    ),
                ),
            ),
            authority=QualificationAuthority(
                promotion_authority_policy_sha256=sha("promotion-roots"),
                promotion_receipt_sha256=sha("promotion"),
                activation_authority_policy_sha256=sha("activation-roots"),
                activation_policy_sha256=sha("activation"),
                activation_eligibility_sha256=sha("eligibility"),
                control_anchor_policy_sha256=sha("anchor"),
                latest_control_entry_sha256=sha("control"),
                preflight_sha256=sha("preflight"),
                promotion_signer_id="promotion-signer",
                activation_signer_id="activation-signer",
                readiness_signer_id="readiness-signer",
                control_signer_id="control-signer",
            ),
            witness=QualificationWitness(
                enrollment_sha256=sha("enrollment"),
                budget_policy_sha256=sha("budget"),
                epoch_id=sha("epoch"),
                checkpoint_id="checkpoint",
                operator_id="witness-operator",
                deployment_id="deployment",
                persistence_design_sha256=sha("persistence"),
                recovery_runbook_sha256=sha("recovery"),
            ),
            runtime=QualificationRuntime(
                broker_build_sha256=sha("broker-build"),
                target_host_id="host",
                broker_os_identity="broker-os",
                worker_os_identity="worker-os",
                credential_custodian_id="credential-custodian",
                monitor_id="monitor",
                audit_sink_id="audit",
                clock_source_id="clock",
                witness_network_policy_sha256=sha("network"),
                stop_runbook_sha256=sha("stop"),
                alert_contact_id="on-call",
            ),
            verification=QualificationVerification(
                test_protocol_sha256=sha("protocol"),
                severity_rubric_sha256=sha("rubric"),
                retention_policy_sha256=sha("retention"),
                max_stop_latency_ms=1000,
                max_alert_latency_ms=2000,
                max_route_evidence_age_seconds=3600,
                max_workers=4,
                max_crash_cases=20,
                max_synthetic_admissions=50,
            ),
        )
        required = [
            "G2",
            "G6-01",
            "G6-02",
            "G6-03",
            "G6-04",
            "Q1",
            "Q2",
            "Q3",
            "Q4",
            "Q5",
            "Q6",
            *(f"O{number:02d}" for number in range(1, 11)),
        ]
        self.drill_protocol = self.joined_protocol()
        self.drill_index = self.joined_evidence(self.drill_protocol).model_copy(
            update={"assembled_at": self.now - timedelta(minutes=7)}
        )
        self.evidence = OfflineQualificationEvidence(
            packet_sha256=self.packet.packet_sha256,
            drill_protocol_sha256=self.drill_protocol.protocol_sha256,
            drill_index_sha256=self.drill_index.evidence_sha256,
            assembled_at=self.now - timedelta(minutes=5),
            records=tuple(
                QualificationEvidenceRecord(
                    evidence_id=key,
                    status="pass",
                    source_sha256=(
                        self.drill_index.evidence_sha256
                        if key == "Q6"
                        else drill_case_sha256(self.drill_index, key)
                        if key.startswith("O")
                        else sha(key)
                    ),
                    producer_id="operator",
                    checker_id=(
                        self.drill_protocol.independent_checker_id
                        if key == "Q6" or key.startswith("O")
                        else "independent-checker"
                    ),
                    collected_at=(
                        self.now - timedelta(minutes=6)
                        if key == "Q6" or key.startswith("O")
                        else self.now - timedelta(hours=2)
                    ),
                    valid_until=self.now + timedelta(hours=1),
                )
                for key in sorted(required)
            ),
            route_observations=(
                QualificationRouteObservation(
                    identity=ExactRouteMetadata.from_candidate(
                        self.route, sha("capabilities")
                    ),
                    pricing_basis="fixture-basis",
                    normalized_cost_microusd=500,
                    catalog_status="available",
                    catalog_evidence_sha256=sha("catalog"),
                    pricing_evidence_sha256=sha("pricing"),
                    conformance_status="passed",
                    conformance_evidence_sha256=sha("conformance"),
                    drift_status="passed",
                    drift_evidence_sha256=sha("drift"),
                    observed_at=self.now - timedelta(minutes=10),
                    valid_until=self.now + timedelta(minutes=10),
                    source_revision="fixture-v1",
                    method_sha256=sha("observation-method"),
                    producer_id="route-operator",
                    checker_id="route-checker",
                ),
            ),
            drill_summary=QualificationDrillSummary(
                workers_used=2,
                crash_cases_run=6,
                synthetic_admissions=20,
                measured_max_stop_latency_ms=500,
                measured_max_alert_latency_ms=900,
            ),
        )
        self.keys = {
            role: Ed25519PrivateKey.generate()
            for role in ("operations", "owner", "security", "statistical")
        }
        self.trust = OfflineQualificationReviewTrust(
            reviewers=tuple(
                QualificationReviewer(
                    role=role,  # type: ignore[arg-type]
                    reviewer_id=f"{role}-reviewer",
                    public_key_base64=base64.b64encode(
                        self.keys[role].public_key().public_bytes_raw()
                    ).decode("ascii"),
                )
                for role in ("operations", "owner", "security", "statistical")
            )
        )

    def reviews(
        self,
        *,
        evidence: OfflineQualificationEvidence | None = None,
        decision: str = "accept",
    ) -> tuple[SignedOfflineQualificationReview, ...]:
        current = evidence or self.evidence
        return tuple(
            sign_synthetic_qualification_review(
                OfflineQualificationReviewDecision(
                    role=reviewer.role,
                    reviewer_id=reviewer.reviewer_id,
                    packet_sha256=self.packet.packet_sha256,
                    evidence_sha256=current.evidence_sha256,
                    decision=decision,  # type: ignore[arg-type]
                    reviewed_at=self.now - timedelta(minutes=2),
                    valid_until=self.now + timedelta(minutes=40),
                ),
                self.keys[reviewer.role].private_bytes_raw(),
            )
            for reviewer in self.trust.reviewers
        )

    def assess(
        self,
        *,
        packet: OfflineQualificationPacket | None = None,
        evidence: OfflineQualificationEvidence | None = None,
        reviews: tuple[SignedOfflineQualificationReview, ...] | None = None,
        drill_protocol: HostDrillProtocol | None = None,
        drill_index: HostDrillEvidenceIndex | None = None,
        now: datetime | None = None,
    ) -> tuple[bool, tuple[str, ...]]:
        result = validate_offline_qualification_packet(
            packet=packet or self.packet,
            evidence=evidence or self.evidence,
            reviews=reviews if reviews is not None else self.reviews(),
            trust=self.trust,
            drill_protocol=drill_protocol or self.drill_protocol,
            drill_index=drill_index or self.drill_index,
            now=now or self.now,
        )
        self.assertFalse(result.qualification_authorized)
        self.assertFalse(result.dispatch_authorized)
        return result.reviewable, result.reasons

    def rebind_drill(
        self, index: HostDrillEvidenceIndex
    ) -> OfflineQualificationEvidence:
        records = tuple(
            record.model_copy(
                update={
                    "source_sha256": (
                        index.evidence_sha256
                        if record.evidence_id == "Q6"
                        else drill_case_sha256(index, record.evidence_id)
                    )
                }
            )
            if record.evidence_id == "Q6" or record.evidence_id.startswith("O")
            else record
            for record in self.evidence.records
        )
        return self.evidence.model_copy(
            update={
                "drill_protocol_sha256": index.protocol_sha256,
                "drill_index_sha256": index.evidence_sha256,
                "records": records,
                "drill_summary": QualificationDrillSummary(
                    workers_used=index.workers_used,
                    crash_cases_run=index.crash_cases_run,
                    synthetic_admissions=index.synthetic_admissions,
                    measured_max_stop_latency_ms=index.measured_max_stop_latency_ms,
                    measured_max_alert_latency_ms=index.measured_max_alert_latency_ms,
                ),
            }
        )

    def test_complete_synthetic_packet_is_only_reviewable(self) -> None:
        self.assertEqual(self.assess(), (True, ()))
        self.assertNotIn(b"Synthetic fixture.", canonical_bytes(self.packet))
        self.assertNotIn(b"Synthetic fixture.", canonical_bytes(self.evidence))

    def test_packet_mutation_invalidates_evidence_and_reviews(self) -> None:
        changed = self.packet.model_copy(
            update={
                "witness": self.packet.witness.model_copy(
                    update={"checkpoint_id": "other-checkpoint"}
                )
            }
        )
        ready, reasons = self.assess(packet=changed)
        self.assertFalse(ready)
        self.assertIn("packet_digest_mismatch", reasons)
        self.assertIn("review_binding_invalid", reasons)

    def test_prerequisite_applicability_change_needs_new_packet_and_evidence(
        self,
    ) -> None:
        changed = self.packet.prerequisites[0].model_copy(update={"required": False})
        packet = self.packet.model_copy(
            update={"prerequisites": (changed, *self.packet.prerequisites[1:])}
        )
        ready, reasons = self.assess(packet=packet)
        self.assertFalse(ready)
        self.assertIn("packet_digest_mismatch", reasons)
        self.assertIn("evidence_coverage_invalid", reasons)

    def test_missing_unavailable_and_stale_gate_evidence(self) -> None:
        missing = self.evidence.model_copy(
            update={"records": self.evidence.records[1:]}
        )
        self.assertIn("evidence_coverage_invalid", self.assess(evidence=missing)[1])
        changed = self.evidence.records[0].model_copy(update={"status": "unavailable"})
        unavailable = self.evidence.model_copy(
            update={"records": (changed, *self.evidence.records[1:])}
        )
        self.assertIn("evidence_not_passed", self.assess(evidence=unavailable)[1])
        expired = self.evidence.records[0].model_copy(
            update={"valid_until": self.now - timedelta(minutes=1)}
        )
        stale = self.evidence.model_copy(
            update={"records": (expired, *self.evidence.records[1:])}
        )
        self.assertIn("evidence_stale", self.assess(evidence=stale)[1])

    def test_route_is_exact_current_and_within_price(self) -> None:
        observation = self.evidence.route_observations[0]
        cases = (
            ("catalog_status", "unavailable", "route_ineligible"),
            ("normalized_cost_microusd", 1001, "route_ineligible"),
            ("pricing_basis", "other-basis", "route_ineligible"),
            ("valid_until", self.now, "route_stale"),
        )
        for field, value, expected in cases:
            with self.subTest(field=field):
                changed = observation.model_copy(update={field: value})
                evidence = self.evidence.model_copy(
                    update={"route_observations": (changed,)}
                )
                self.assertIn(expected, self.assess(evidence=evidence)[1])
        empty = self.evidence.model_copy(update={"route_observations": ()})
        self.assertIn("route_coverage_invalid", self.assess(evidence=empty)[1])
        old_but_unexpired = observation.model_copy(
            update={"observed_at": self.now - timedelta(hours=2)}
        )
        evidence = self.evidence.model_copy(
            update={"route_observations": (old_but_unexpired,)}
        )
        self.assertIn("route_stale", self.assess(evidence=evidence)[1])
        other_route = self.route.model_copy(update={"model": "nearby"})
        other_observation = observation.model_copy(
            update={
                "identity": ExactRouteMetadata.from_candidate(
                    other_route, sha("capabilities")
                )
            }
        )
        evidence = self.evidence.model_copy(
            update={"route_observations": (other_observation,)}
        )
        self.assertIn("route_coverage_invalid", self.assess(evidence=evidence)[1])

    def test_drill_measurements_cannot_exceed_frozen_limits(self) -> None:
        changed = self.evidence.drill_summary.model_copy(
            update={"measured_max_stop_latency_ms": 1001}
        )
        evidence = self.evidence.model_copy(update={"drill_summary": changed})
        self.assertIn("drill_limit_exceeded", self.assess(evidence=evidence)[1])
        changed = self.evidence.drill_summary.model_copy(update={"workers_used": 5})
        evidence = self.evidence.model_copy(update={"drill_summary": changed})
        self.assertIn("drill_limit_exceeded", self.assess(evidence=evidence)[1])

    def test_missing_rejected_expired_and_tampered_reviews(self) -> None:
        signed = self.reviews()
        self.assertIn("review_coverage_invalid", self.assess(reviews=signed[1:])[1])
        rejected = self.reviews(decision="reject")
        self.assertIn("review_rejected", self.assess(reviews=rejected)[1])
        old = signed[0].model_copy(
            update={
                "review": signed[0].review.model_copy(
                    update={"valid_until": self.now - timedelta(seconds=1)}
                )
            }
        )
        self.assertIn("review_stale", self.assess(reviews=(old, *signed[1:]))[1])
        self.assertIn(
            "review_signature_invalid", self.assess(reviews=(old, *signed[1:]))[1]
        )
        tampered = signed[0].model_copy(
            update={"signature_base64": signed[1].signature_base64}
        )
        self.assertIn(
            "review_signature_invalid", self.assess(reviews=(tampered, *signed[1:]))[1]
        )

    def test_changed_evidence_requires_new_review(self) -> None:
        changed = self.evidence.records[0].model_copy(
            update={"source_sha256": sha("new")}
        )
        evidence = self.evidence.model_copy(
            update={"records": (changed, *self.evidence.records[1:])}
        )
        self.assertIn("review_binding_invalid", self.assess(evidence=evidence)[1])
        self.assertEqual(
            self.assess(evidence=evidence, reviews=self.reviews(evidence=evidence)),
            (True, ()),
        )

    def test_qualification_drill_digests_are_required_and_exact(self) -> None:
        payload = self.evidence.model_dump(mode="json")
        for field in ("drill_protocol_sha256", "drill_index_sha256"):
            with self.subTest(missing=field):
                incomplete = payload.copy()
                incomplete.pop(field)
                with self.assertRaises(ValidationError):
                    OfflineQualificationEvidence.model_validate(incomplete)
            with self.subTest(changed=field):
                changed = self.evidence.model_copy(update={field: sha(field)})
                _, reasons = self.assess(
                    evidence=changed, reviews=self.reviews(evidence=changed)
                )
                self.assertIn("drill_digest_mismatch", reasons)

    def test_q6_and_every_o_record_bind_the_exact_drill_index(self) -> None:
        for evidence_id in ("Q6", *(f"O{number:02d}" for number in range(1, 11))):
            with self.subTest(evidence_id=evidence_id):
                records = tuple(
                    record.model_copy(update={"source_sha256": sha("substitute")})
                    if record.evidence_id == evidence_id
                    else record
                    for record in self.evidence.records
                )
                changed = self.evidence.model_copy(update={"records": records})
                _, reasons = self.assess(
                    evidence=changed, reviews=self.reviews(evidence=changed)
                )
                self.assertIn("drill_record_mismatch", reasons)

    def test_drill_summary_roles_and_collection_time_must_match(self) -> None:
        changed_summary = self.evidence.drill_summary.model_copy(
            update={"crash_cases_run": 7}
        )
        changed = self.evidence.model_copy(update={"drill_summary": changed_summary})
        self.assertIn(
            "drill_summary_mismatch",
            self.assess(evidence=changed, reviews=self.reviews(evidence=changed))[1],
        )
        for update, reason in (
            ({"checker_id": "other-checker"}, "drill_record_role_mismatch"),
            (
                {"collected_at": self.drill_index.assembled_at - timedelta(seconds=1)},
                "drill_record_time_invalid",
            ),
        ):
            with self.subTest(reason=reason):
                records = tuple(
                    item.model_copy(update=update)
                    if item.evidence_id == "O01"
                    else item
                    for item in self.evidence.records
                )
                changed = self.evidence.model_copy(update={"records": records})
                _, reasons = self.assess(
                    evidence=changed, reviews=self.reviews(evidence=changed)
                )
                self.assertIn(reason, reasons)

    def test_failed_drill_index_denies_even_when_evidence_is_resigned(self) -> None:
        incomplete = self.drill_index.model_copy(
            update={"observations": self.drill_index.observations[:-1]}
        )
        evidence = self.rebind_drill(incomplete)
        self.assertIn(
            "drill_index_invalid",
            self.assess(
                evidence=evidence,
                reviews=self.reviews(evidence=evidence),
                drill_index=incomplete,
            )[1],
        )

    def test_changed_drill_index_needs_new_qualification_reviews(self) -> None:
        changed_index = self.drill_index.model_copy(update={"workers_used": 3})
        evidence = self.rebind_drill(changed_index)
        self.assertIn(
            "review_binding_invalid",
            self.assess(evidence=evidence, drill_index=changed_index)[1],
        )
        self.assertEqual(
            self.assess(
                evidence=evidence,
                reviews=self.reviews(evidence=evidence),
                drill_index=changed_index,
            ),
            (True, ()),
        )

    def test_scope_and_packet_expire(self) -> None:
        ready, reasons = self.assess(now=self.now + timedelta(hours=2))
        self.assertFalse(ready)
        self.assertIn("packet_stale", reasons)
        self.assertIn("evidence_stale", reasons)

    def test_schema_rejects_unfrozen_or_unsafe_shapes(self) -> None:
        with self.assertRaises(ValidationError):
            QualificationScope.model_validate(
                self.packet.scope.model_dump() | {"request_maximum_microusd": 10_000}
            )
        with self.assertRaises(ValidationError):
            OfflineQualificationPacket.model_validate(
                self.packet.model_dump() | {"unrecognized_permission": True}
            )
        with self.assertRaises(ValidationError):
            OfflineQualificationPacket.model_validate(
                self.packet.model_dump()
                | {"prerequisites": self.packet.prerequisites[:2]}
            )
        with self.assertRaises(ValidationError):
            QualificationRuntime.model_validate(
                self.packet.runtime.model_dump() | {"worker_os_identity": "broker-os"}
            )
        with self.assertRaises(ValidationError):
            OfflineQualificationReviewTrust.model_validate(
                self.trust.model_dump() | {"reviewers": (self.trust.reviewers[0],) * 4}
            )

    def joined_protocol(self) -> HostDrillProtocol:
        return HostDrillProtocol(
            qualification_packet_sha256=self.packet.packet_sha256,
            broker_build_sha256=self.packet.runtime.broker_build_sha256,
            target_host_id=self.packet.runtime.target_host_id,
            witness_deployment_id=self.packet.witness.deployment_id,
            test_protocol_sha256=self.packet.verification.test_protocol_sha256,
            operator_id="operator",
            independent_checker_id="checker",
            frozen_at=self.now - timedelta(hours=2),
            valid_until=self.now + timedelta(minutes=30),
            max_workers=4,
            max_crash_cases=20,
            max_synthetic_admissions=50,
            max_stop_latency_ms=1000,
            max_alert_latency_ms=2000,
            request_maximum_microusd=self.packet.scope.request_maximum_microusd,
            oracles=tuple(
                HostDrillOracle(
                    case_id=case,  # type: ignore[arg-type]
                    fault_id=fault,
                    expected_status=status,  # type: ignore[arg-type]
                    expected_state_sha256=sha(f"oracle:{case}:{fault}"),
                    max_claims=1 if (case, fault) in REQUIRED_CLAIM_FAULTS else 0,
                    max_intents=1 if (case, fault) in REQUIRED_INTENT_FAULTS else 0,
                    max_transport_entries=1 if status == "one_entry" else 0,
                    min_retained_exposure_microusd=(
                        self.packet.scope.request_maximum_microusd
                        if (case, fault) in REQUIRED_FULL_EXPOSURE_FAULTS
                        else 0
                    ),
                )
                for case, faults in REQUIRED_FAULTS.items()
                for fault in faults
                for status in (REQUIRED_STATUSES[(case, fault)],)
            ),
        )

    def joined_evidence(self, protocol: HostDrillProtocol) -> HostDrillEvidenceIndex:
        return HostDrillEvidenceIndex(
            protocol_sha256=protocol.protocol_sha256,
            qualification_packet_sha256=protocol.qualification_packet_sha256,
            broker_build_sha256=protocol.broker_build_sha256,
            target_host_id=protocol.target_host_id,
            witness_deployment_id=protocol.witness_deployment_id,
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
                    producer_id=protocol.operator_id,
                    checker_id=protocol.independent_checker_id,
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
                    protocol.oracles, key=lambda item: (item.case_id, item.fault_id)
                )
            ),
        )

    def test_joined_drill_accepts_exact_or_narrower_packet_bounds(self) -> None:
        protocol = self.joined_protocol()
        for current in (
            protocol,
            protocol.model_copy(update={"max_workers": 3, "max_crash_cases": 10}),
        ):
            with self.subTest(workers=current.max_workers):
                result = validate_joined_inert_host_drill_index(
                    packet=self.packet,
                    protocol=current,
                    evidence=self.joined_evidence(current),
                    now=self.now,
                )
                self.assertTrue(result.packet_checked)
                self.assertTrue(result.reviewable)
                self.assertEqual(result.reasons, ())
                self.assertFalse(result.target_host_verified)
                self.assertFalse(result.qualification_authorized)
                self.assertFalse(result.dispatch_authorized)
        incomplete = self.joined_evidence(protocol)
        incomplete = incomplete.model_copy(
            update={"observations": incomplete.observations[:-1]}
        )
        result = validate_joined_inert_host_drill_index(
            packet=self.packet,
            protocol=protocol,
            evidence=incomplete,
            now=self.now,
        )
        self.assertIn("coverage_invalid", result.reasons)

    def test_joined_drill_denies_each_packet_identity_mismatch(self) -> None:
        original = self.joined_protocol()
        for field in (
            "qualification_packet_sha256",
            "broker_build_sha256",
            "target_host_id",
            "witness_deployment_id",
            "test_protocol_sha256",
            "request_maximum_microusd",
        ):
            with self.subTest(field=field):
                value = (
                    501
                    if field == "request_maximum_microusd"
                    else "other-host"
                    if field == "target_host_id"
                    else "other-witness"
                    if field == "witness_deployment_id"
                    else sha(field)
                )
                protocol = original.model_copy(update={field: value})
                result = validate_joined_inert_host_drill_index(
                    packet=self.packet,
                    protocol=protocol,
                    evidence=self.joined_evidence(protocol),
                    now=self.now,
                )
                self.assertFalse(result.reviewable)
                self.assertIn("qualification_packet_binding_mismatch", result.reasons)
                self.assertNotIn("binding_mismatch", result.reasons)

    def test_joined_drill_denies_each_raised_ceiling(self) -> None:
        original = self.joined_protocol()
        for field, value in (
            ("max_workers", 5),
            ("max_crash_cases", 21),
            ("max_synthetic_admissions", 51),
            ("max_stop_latency_ms", 1001),
            ("max_alert_latency_ms", 2001),
        ):
            with self.subTest(field=field):
                protocol = original.model_copy(update={field: value})
                result = validate_joined_inert_host_drill_index(
                    packet=self.packet,
                    protocol=protocol,
                    evidence=self.joined_evidence(protocol),
                    now=self.now,
                )
                self.assertFalse(result.reviewable)
                self.assertIn("qualification_packet_limit_exceeded", result.reasons)
                self.assertNotIn("limit_exceeded", result.reasons)

    def test_joined_drill_denies_extended_or_stale_window(self) -> None:
        original = self.joined_protocol()
        for changes in (
            {"frozen_at": self.packet.frozen_at - timedelta(seconds=1)},
            {"valid_until": self.packet.decision_deadline + timedelta(seconds=1)},
        ):
            protocol = original.model_copy(update=changes)
            result = validate_joined_inert_host_drill_index(
                packet=self.packet,
                protocol=protocol,
                evidence=self.joined_evidence(protocol),
                now=self.now,
            )
            self.assertIn("qualification_packet_window_invalid", result.reasons)
        result = validate_joined_inert_host_drill_index(
            packet=self.packet,
            protocol=original,
            evidence=self.joined_evidence(original),
            now=self.packet.decision_deadline,
        )
        self.assertIn("qualification_packet_window_invalid", result.reasons)

    def test_joined_drill_cli_denies_packet_mismatch(self) -> None:
        protocol = self.joined_protocol()
        evidence = self.joined_evidence(protocol)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            protocol_path = root / "protocol.json"
            evidence_path = root / "evidence.json"
            packet_path.write_text(self.packet.model_dump_json())
            protocol_path.write_text(protocol.model_dump_json())
            evidence_path.write_text(evidence.model_dump_json())
            command = [
                sys.executable,
                "-m",
                "mos_eisley.run.routing_host_drills",
                str(protocol_path),
                str(evidence_path),
                "--qualification-packet",
                str(packet_path),
                "--now",
                self.now.isoformat(),
            ]
            passed = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertTrue(json.loads(passed.stdout)["packet_checked"])
            self.assertTrue(json.loads(passed.stdout)["reviewable"])
            changed = self.packet.model_copy(
                update={
                    "runtime": self.packet.runtime.model_copy(
                        update={"target_host_id": "other-host"}
                    )
                }
            )
            packet_path.write_text(changed.model_dump_json())
            denied = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(denied.returncode, 1, denied.stderr)
            self.assertIn(
                "qualification_packet_binding_mismatch",
                json.loads(denied.stdout)["reasons"],
            )

    def source_handoff(self) -> G605SourceEvidenceHandoff:
        inspection_sha256 = sha("inspection-protocol")
        roster_sha256 = sha("reviewer-roster")
        required = required_source_references(
            packet=self.packet,
            evidence=self.evidence,
            drill_protocol=self.drill_protocol,
            drill_index=self.drill_index,
            inspection_protocol_sha256=inspection_sha256,
            reviewer_roster_sha256=roster_sha256,
        )
        references = tuple(
            SourceEvidenceReference(
                **requirement.model_dump(),
                custody_domain_id="isolated-review-custody",
                custodian_id="custodian",
                locator_id=f"loc-{number}",
                producer_id="producer",
                checker_id=f"{requirement.checker_role}-checker",
                status="available",
                captured_at=self.now - timedelta(minutes=4),
                valid_until=self.now + timedelta(minutes=20),
            )
            for number, requirement in enumerate(required)
        )
        return G605SourceEvidenceHandoff(
            packet_sha256=self.packet.packet_sha256,
            qualification_evidence_sha256=self.evidence.evidence_sha256,
            drill_protocol_sha256=self.drill_protocol.protocol_sha256,
            drill_index_sha256=self.drill_index.evidence_sha256,
            inspection_protocol_sha256=inspection_sha256,
            reviewer_roster_sha256=roster_sha256,
            assembled_at=self.now - timedelta(minutes=3),
            references=references,
        )

    def source_assessment(
        self,
        handoff: G605SourceEvidenceHandoff,
        *,
        packet: OfflineQualificationPacket | None = None,
        evidence: OfflineQualificationEvidence | None = None,
        now: datetime | None = None,
    ) -> tuple[bool, tuple[str, ...]]:
        result = validate_g605_source_handoff(
            handoff=handoff,
            packet=packet or self.packet,
            evidence=evidence or self.evidence,
            drill_protocol=self.drill_protocol,
            drill_index=self.drill_index,
            expected_inspection_protocol_sha256=sha("inspection-protocol"),
            expected_reviewer_roster_sha256=sha("reviewer-roster"),
            now=now or self.now,
        )
        self.assertFalse(result.source_authenticated)
        self.assertFalse(result.target_host_verified)
        self.assertFalse(result.qualification_authorized)
        self.assertFalse(result.dispatch_authorized)
        return result.handoff_ready, result.reasons

    def test_source_handoff_complete_inventory_is_only_ready_for_inspection(
        self,
    ) -> None:
        handoff = self.source_handoff()
        self.assertEqual(self.source_assessment(handoff), (True, ()))
        self.assertGreater(len(handoff.references), 70)
        self.assertNotIn(b"Synthetic fixture.", canonical_bytes(handoff))
        self.assertTrue(any(ref.source_id == "q.Q1" for ref in handoff.references))
        self.assertTrue(
            any(ref.source_id.startswith("f.O10.") for ref in handoff.references)
        )

    def test_source_handoff_denies_missing_extra_and_rebound_source(self) -> None:
        handoff = self.source_handoff()
        missing = handoff.model_copy(update={"references": handoff.references[1:]})
        self.assertIn("source_coverage_invalid", self.source_assessment(missing)[1])
        changed = handoff.references[0].model_copy(
            update={"source_sha256": sha("other-source")}
        )
        rebound = handoff.model_copy(
            update={"references": (changed, *handoff.references[1:])}
        )
        self.assertIn("source_binding_mismatch", self.source_assessment(rebound)[1])
        extra = SourceEvidenceReference.model_validate(
            {**handoff.references[-1].model_dump(), "source_id": "z.extra"}
        )
        with_extra = handoff.model_copy(
            update={"references": (*handoff.references, extra)}
        )
        self.assertIn("source_coverage_invalid", self.source_assessment(with_extra)[1])

    def test_source_handoff_denies_unavailable_stale_and_disputed(self) -> None:
        handoff = self.source_handoff()
        for update, reason in (
            ({"status": "unavailable"}, "source_unavailable"),
            ({"status": "disputed"}, "source_unavailable"),
            ({"valid_until": self.now - timedelta(seconds=1)}, "source_stale"),
        ):
            altered = handoff.references[0].model_copy(update=update)
            candidate = handoff.model_copy(
                update={"references": (altered, *handoff.references[1:])}
            )
            self.assertIn(reason, self.source_assessment(candidate)[1])

    def test_source_handoff_denies_wrong_access_method_or_checker_role(self) -> None:
        handoff = self.source_handoff()
        for update in (
            {"access_mode": "owner_isolated"},
            {"check_method": "independent_source_read"},
            {"checker_role": "security"},
        ):
            audited = next(ref for ref in handoff.references if ref.source_id == "q.Q1")
            changed = audited.model_copy(update=update)
            references = tuple(
                changed if ref.source_id == "q.Q1" else ref
                for ref in handoff.references
            )
            altered = handoff.model_copy(update={"references": references})
            self.assertIn("source_binding_mismatch", self.source_assessment(altered)[1])

    def test_source_handoff_denies_wrong_packet_and_expired_window(self) -> None:
        handoff = self.source_handoff()
        changed_packet = self.packet.model_copy(
            update={
                "runtime": self.packet.runtime.model_copy(
                    update={"target_host_id": "other-host"}
                )
            }
        )
        self.assertIn(
            "handoff_binding_mismatch",
            self.source_assessment(handoff, packet=changed_packet)[1],
        )
        self.assertIn(
            "handoff_window_invalid",
            self.source_assessment(handoff, now=self.packet.decision_deadline)[1],
        )
        changed_roster = handoff.model_copy(
            update={"reviewer_roster_sha256": sha("different-roster")}
        )
        self.assertIn(
            "handoff_binding_mismatch", self.source_assessment(changed_roster)[1]
        )

    def test_source_handoff_denies_incomplete_qualification_and_route(self) -> None:
        handoff = self.source_handoff()
        incomplete = self.evidence.model_copy(
            update={"records": self.evidence.records[1:]}
        )
        self.assertIn(
            "qualification_coverage_invalid",
            self.source_assessment(handoff, evidence=incomplete)[1],
        )
        wrong_route = self.evidence.route_observations[0].model_copy(
            update={"normalized_cost_microusd": 5000}
        )
        altered = self.evidence.model_copy(
            update={"route_observations": (wrong_route,)}
        )
        self.assertIn(
            "route_observation_invalid",
            self.source_assessment(handoff, evidence=altered)[1],
        )
        changed_q6 = next(
            item for item in self.evidence.records if item.evidence_id == "Q6"
        ).model_copy(update={"source_sha256": sha("other-drill")})
        changed_records = tuple(
            changed_q6 if item.evidence_id == "Q6" else item
            for item in self.evidence.records
        )
        altered = self.evidence.model_copy(update={"records": changed_records})
        self.assertIn(
            "drill_record_mismatch",
            self.source_assessment(handoff, evidence=altered)[1],
        )

    def test_source_handoff_rejects_same_checker_and_embedded_content(self) -> None:
        reference = self.source_handoff().references[0]
        with self.assertRaises(ValidationError):
            SourceEvidenceReference.model_validate(
                {**reference.model_dump(), "checker_id": reference.custodian_id}
            )
        with self.assertRaises(ValidationError):
            SourceEvidenceReference.model_validate(
                {**reference.model_dump(), "prompt_text": "forbidden content"}
            )

    def test_source_handoff_cli_has_bounded_metadata_result(self) -> None:
        handoff = self.source_handoff()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("packet", self.packet),
                ("qualification", self.evidence),
                ("protocol", self.drill_protocol),
                ("index", self.drill_index),
                ("handoff", handoff),
            ):
                (root / f"{name}.json").write_text(value.model_dump_json())
            command = [
                sys.executable,
                "-m",
                "mos_eisley.run.routing_source_handoff",
                *(
                    str(root / f"{name}.json")
                    for name in (
                        "packet",
                        "qualification",
                        "protocol",
                        "index",
                        "handoff",
                    )
                ),
                "--now",
                self.now.isoformat(),
                "--inspection-protocol-sha256",
                handoff.inspection_protocol_sha256,
                "--reviewer-roster-sha256",
                handoff.reviewer_roster_sha256,
            ]
            passed = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            payload = json.loads(passed.stdout)
            self.assertTrue(payload["handoff_ready"])
            self.assertFalse(payload["source_authenticated"])
            self.assertNotIn("references", payload)
            wrong_approval = subprocess.run(
                [*command[:-1], sha("unapproved-roster")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(wrong_approval.returncode, 1, wrong_approval.stderr)
            self.assertIn(
                "handoff_binding_mismatch",
                json.loads(wrong_approval.stdout)["reasons"],
            )
            denied = handoff.model_copy(update={"references": handoff.references[1:]})
            (root / "handoff.json").write_text(denied.model_dump_json())
            failed = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(failed.returncode, 1, failed.stderr)
            self.assertIn(
                "source_coverage_invalid", json.loads(failed.stdout)["reasons"]
            )

    def decision_readiness(
        self, handoff: G605SourceEvidenceHandoff
    ) -> G605DecisionReadinessPacket:
        technical_sha256 = sha("technical-review-freeze")
        inspections = tuple(
            SourceInspectionOutcome(
                source_id=reference.source_id,
                source_sha256=reference.source_sha256,
                inspection_record_sha256=sha(f"inspection:{reference.source_id}"),
                checker_id=reference.checker_id,
                status="accept",
                inspected_at=self.now - timedelta(minutes=2, seconds=30),
                valid_until=self.now + timedelta(minutes=20),
            )
            for reference in handoff.references
        )
        roster = {item.role: item.reviewer_id for item in self.trust.reviewers}
        dispositions = tuple(
            DecisionDisposition(
                **requirement.model_dump(),
                decision_record_sha256=sha(f"decision:{requirement.decision_id}"),
                reviewer_id=roster[requirement.reviewer_role],
                producer_id="operator",
                status="accept",
                recorded_at=self.now - timedelta(minutes=2, seconds=20),
                valid_until=self.now + timedelta(minutes=20),
            )
            for requirement in required_decisions(
                packet=self.packet,
                evidence=self.evidence,
                drill_index=self.drill_index,
                handoff=handoff,
                technical_review_sha256=technical_sha256,
            )
        )
        return G605DecisionReadinessPacket(
            qualification_packet_sha256=self.packet.packet_sha256,
            qualification_evidence_sha256=self.evidence.evidence_sha256,
            drill_protocol_sha256=self.drill_protocol.protocol_sha256,
            drill_index_sha256=self.drill_index.evidence_sha256,
            source_handoff_sha256=handoff.handoff_sha256,
            review_trust_sha256=digest(canonical_bytes(self.trust)),
            signed_reviews_sha256=signed_reviews_sha256(self.reviews()),
            technical_review_sha256=technical_sha256,
            assembled_at=self.now - timedelta(minutes=1),
            valid_until=self.now + timedelta(minutes=20),
            source_inspections=inspections,
            dispositions=dispositions,
        )

    def decision_assessment(
        self,
        readiness: G605DecisionReadinessPacket,
        handoff: G605SourceEvidenceHandoff,
        *,
        packet: OfflineQualificationPacket | None = None,
        reviews: tuple[SignedOfflineQualificationReview, ...] | None = None,
        now: datetime | None = None,
    ) -> tuple[bool, tuple[str, ...]]:
        result = validate_g605_decision_readiness(
            readiness=readiness,
            packet=packet or self.packet,
            evidence=self.evidence,
            drill_protocol=self.drill_protocol,
            drill_index=self.drill_index,
            handoff=handoff,
            trust=self.trust,
            reviews=reviews if reviews is not None else self.reviews(),
            expected_inspection_protocol_sha256=sha("inspection-protocol"),
            expected_reviewer_roster_sha256=sha("reviewer-roster"),
            expected_review_trust_sha256=digest(canonical_bytes(self.trust)),
            expected_technical_review_sha256=sha("technical-review-freeze"),
            now=now or self.now,
        )
        self.assertFalse(result.source_authenticated)
        self.assertFalse(result.target_host_verified)
        self.assertFalse(result.g5_qualified)
        self.assertFalse(result.qualification_authorized)
        self.assertFalse(result.dispatch_authorized)
        return result.ready_for_owner_decision, result.reasons

    def test_decision_readiness_complete_synthetic_queue_has_no_authority(self) -> None:
        handoff = self.source_handoff()
        readiness = self.decision_readiness(handoff)
        self.assertEqual(self.decision_assessment(readiness, handoff), (True, ()))
        self.assertGreater(len(readiness.source_inspections), 70)
        self.assertNotIn(b"Synthetic fixture.", canonical_bytes(readiness))

    def test_decision_readiness_denies_inspection_gaps_and_failure(self) -> None:
        handoff = self.source_handoff()
        original = self.decision_readiness(handoff)
        incomplete = original.model_copy(
            update={"source_inspections": original.source_inspections[1:]}
        )
        self.assertIn(
            "inspection_coverage_invalid",
            self.decision_assessment(incomplete, handoff)[1],
        )
        for update, reason in (
            ({"status": "reject"}, "inspection_not_accepted"),
            ({"status": "unavailable"}, "inspection_not_accepted"),
            ({"source_sha256": sha("rebound")}, "inspection_binding_mismatch"),
            ({"checker_id": "other-checker"}, "inspection_binding_mismatch"),
            (
                {"valid_until": self.now - timedelta(seconds=1)},
                "inspection_window_invalid",
            ),
        ):
            changed = original.source_inspections[0].model_copy(update=update)
            candidate = original.model_copy(
                update={
                    "source_inspections": (changed, *original.source_inspections[1:])
                }
            )
            self.assertIn(reason, self.decision_assessment(candidate, handoff)[1])

    def test_decision_readiness_denies_disposition_gaps_and_rejection(self) -> None:
        handoff = self.source_handoff()
        original = self.decision_readiness(handoff)
        incomplete = original.model_copy(
            update={"dispositions": original.dispositions[1:]}
        )
        self.assertIn(
            "decision_coverage_invalid",
            self.decision_assessment(incomplete, handoff)[1],
        )
        for update, reason in (
            ({"status": "reject"}, "decision_not_accepted"),
            ({"subject_sha256": sha("wrong")}, "decision_binding_mismatch"),
            ({"reviewer_id": "wrong-reviewer"}, "decision_binding_mismatch"),
            (
                {"recorded_at": self.now + timedelta(seconds=1)},
                "decision_window_invalid",
            ),
        ):
            changed = original.dispositions[0].model_copy(update=update)
            candidate = original.model_copy(
                update={"dispositions": (changed, *original.dispositions[1:])}
            )
            self.assertIn(reason, self.decision_assessment(candidate, handoff)[1])

    def test_decision_readiness_denies_early_source_disposition_and_q7_review(
        self,
    ) -> None:
        handoff = self.source_handoff()
        original = self.decision_readiness(handoff)
        dispositions = tuple(
            item.model_copy(
                update={"recorded_at": self.now - timedelta(minutes=2, seconds=40)}
            )
            if item.decision_id == "G605-05"
            else item
            for item in original.dispositions
        )
        altered = original.model_copy(update={"dispositions": dispositions})
        self.assertIn(
            "source_disposition_early", self.decision_assessment(altered, handoff)[1]
        )
        late_decision = original.dispositions[0].model_copy(
            update={"recorded_at": self.now - timedelta(minutes=1, seconds=30)}
        )
        altered = original.model_copy(
            update={"dispositions": (late_decision, *original.dispositions[1:])}
        )
        self.assertIn(
            "q7_review_order_invalid", self.decision_assessment(altered, handoff)[1]
        )

    def test_decision_readiness_denies_changed_freeze_open_finding_and_expiry(
        self,
    ) -> None:
        handoff = self.source_handoff()
        original = self.decision_readiness(handoff)
        changed = original.model_copy(
            update={"technical_review_sha256": sha("unapproved-review")}
        )
        self.assertIn(
            "readiness_binding_mismatch", self.decision_assessment(changed, handoff)[1]
        )
        open_finding = original.model_copy(update={"unresolved_findings": ("G605-05",)})
        self.assertIn(
            "unresolved_findings", self.decision_assessment(open_finding, handoff)[1]
        )
        self.assertIn(
            "readiness_window_invalid",
            self.decision_assessment(original, handoff, now=original.valid_until)[1],
        )

    def test_decision_readiness_rejects_go_state_and_embedded_source(self) -> None:
        handoff = self.source_handoff()
        original = self.decision_readiness(handoff)
        with self.assertRaises(ValidationError):
            G605DecisionReadinessPacket.model_validate(
                {**original.model_dump(), "decision_state": "go"}
            )
        with self.assertRaises(ValidationError):
            SourceInspectionOutcome.model_validate(
                {
                    **original.source_inspections[0].model_dump(),
                    "source_text": "forbidden",
                }
            )

    def test_decision_readiness_denies_rejected_q7_review(self) -> None:
        handoff = self.source_handoff()
        readiness = self.decision_readiness(handoff)
        rejected = self.reviews(decision="reject")
        self.assertIn(
            "qualification_metadata_invalid",
            self.decision_assessment(readiness, handoff, reviews=rejected)[1],
        )

    def test_decision_readiness_denies_rebound_handoff_and_packet(self) -> None:
        handoff = self.source_handoff()
        readiness = self.decision_readiness(handoff)
        incomplete_handoff = handoff.model_copy(
            update={"references": handoff.references[1:]}
        )
        self.assertIn(
            "source_handoff_invalid",
            self.decision_assessment(readiness, incomplete_handoff)[1],
        )
        changed_packet = self.packet.model_copy(
            update={
                "runtime": self.packet.runtime.model_copy(
                    update={"target_host_id": "changed-host"}
                )
            }
        )
        reasons = self.decision_assessment(readiness, handoff, packet=changed_packet)[1]
        self.assertIn("qualification_metadata_invalid", reasons)
        self.assertIn("readiness_binding_mismatch", reasons)

    def test_decision_readiness_cli_reports_only_bounded_metadata(self) -> None:
        handoff = self.source_handoff()
        readiness = self.decision_readiness(handoff)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            objects = (
                ("packet", self.packet),
                ("evidence", self.evidence),
                ("protocol", self.drill_protocol),
                ("index", self.drill_index),
                ("handoff", handoff),
                ("trust", self.trust),
                ("readiness", readiness),
            )
            for name, value in objects:
                (root / f"{name}.json").write_text(value.model_dump_json())
            (root / "reviews.json").write_text(
                json.dumps([item.model_dump(mode="json") for item in self.reviews()])
            )
            command = [
                sys.executable,
                "-m",
                "mos_eisley.run.routing_decision_readiness",
                *(
                    str(root / f"{name}.json")
                    for name in (
                        "packet",
                        "evidence",
                        "protocol",
                        "index",
                        "handoff",
                        "trust",
                        "reviews",
                        "readiness",
                    )
                ),
                "--inspection-protocol-sha256",
                handoff.inspection_protocol_sha256,
                "--reviewer-roster-sha256",
                handoff.reviewer_roster_sha256,
                "--review-trust-sha256",
                readiness.review_trust_sha256,
                "--technical-review-sha256",
                readiness.technical_review_sha256,
                "--now",
                self.now.isoformat(),
            ]
            passed = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            payload = json.loads(passed.stdout)
            self.assertTrue(payload["ready_for_owner_decision"])
            self.assertFalse(payload["qualification_authorized"])
            self.assertNotIn("source_inspections", payload)
            denied = subprocess.run(
                [*command[:-3], sha("wrong-review"), *command[-2:]],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(denied.returncode, 1, denied.stderr)
            self.assertIn(
                "readiness_binding_mismatch", json.loads(denied.stdout)["reasons"]
            )
