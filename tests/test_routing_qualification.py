"""Synthetic G6-05 packet checks; no G5 stores or live transport are used."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.skills import PromptAsset
from mos_eisley.evaluation.models import RouteCandidate
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


def sha(label: str) -> str:
    return digest(label.encode())


class RoutingQualificationTests(TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 26, 12, tzinfo=UTC)
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
        self.evidence = OfflineQualificationEvidence(
            packet_sha256=self.packet.packet_sha256,
            assembled_at=self.now - timedelta(minutes=5),
            records=tuple(
                QualificationEvidenceRecord(
                    evidence_id=key,
                    status="pass",
                    source_sha256=sha(key),
                    producer_id="operator",
                    checker_id="independent-checker",
                    collected_at=self.now - timedelta(hours=2),
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
                crash_cases_run=10,
                synthetic_admissions=20,
                measured_max_stop_latency_ms=500,
                measured_max_alert_latency_ms=1000,
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
        now: datetime | None = None,
    ) -> tuple[bool, tuple[str, ...]]:
        result = validate_offline_qualification_packet(
            packet=packet or self.packet,
            evidence=evidence or self.evidence,
            reviews=reviews if reviews is not None else self.reviews(),
            trust=self.trust,
            now=now or self.now,
        )
        self.assertFalse(result.qualification_authorized)
        self.assertFalse(result.dispatch_authorized)
        return result.reviewable, result.reasons

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
