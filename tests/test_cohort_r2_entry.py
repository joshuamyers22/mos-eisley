"""G6-06 R2 metadata-only entry packet and synthetic denial rehearsal."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.cohort_entry import (
    FrozenR2EntryAnchor,
    OfflineR2EntryPacket,
    R2GoReference,
    R2ReviewReference,
    task_enrollment_sha256,
    validate_end_to_end_offline_r2_entry,
    validate_joined_offline_r2_entry,
    validate_offline_r2_entry,
)
from mos_eisley.run.routing_owner_decision import (
    FrozenG605OwnerDecisionAnchor,
    G605OwnerDecision,
    G605OwnerDecisionTrust,
    SignedG605OwnerDecision,
    sign_synthetic_g605_owner_decision,
    validate_offline_g605_owner_decision,
)
from mos_eisley.run.routing_qualification import ExactRouteMetadata, QualifiedRoute
from tests import test_cohort_controller as cohort_module
from tests import test_routing_qualification as qualification_module


class CohortR2EntryTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.owner_decision_key = Ed25519PrivateKey.generate()
        self.fixture.go_sha256_factory = self.make_owner_go_sha256
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.now = self.fixture.now
        self.proposed = self.fixture.release("bounded_live", 1)
        self.anchor = FrozenR2EntryAnchor(
            manifest_sha256=self.fixture.manifest.manifest_sha256,
            g6_05_go_sha256=self.fixture.go_sha256,
            g6_05_packet_sha256=self.owner_anchor.qualification_packet_sha256,
            r0_review_sha256=digest(b"r2-synthetic-r0-review"),
            r1_review_sha256=digest(b"r2-synthetic-r1-review"),
            oncall_evidence_sha256=digest(b"r2-synthetic-oncall-evidence"),
            full_request_microusd=100,
            max_route_age_seconds=60,
            valid_until=self.now + timedelta(minutes=1),
        )
        go = R2GoReference(
            decision_sha256=self.fixture.go_sha256,
            packet_sha256=self.anchor.g6_05_packet_sha256,
            status="go",
            owner_id=self.fixture.manifest.owner_id,
            cohort_id=self.fixture.manifest.cohort_id,
            candidate_policy_sha256=self.fixture.manifest.candidate_policy_sha256,
            selected_candidate_id=self.fixture.base.selection.candidate_id,
            broker_build_sha256=self.fixture.manifest.broker_build_sha256,
            target_host_id=self.fixture.manifest.target_host_id,
            witness_epoch_id=self.fixture.manifest.witness_epoch_id,
            issued_at=self.now - timedelta(seconds=10),
            valid_until=self.now + timedelta(minutes=1),
        )
        r0 = R2ReviewReference(
            phase="R0",
            status="accepted",
            evidence_sha256=self.anchor.r0_review_sha256,
            manifest_sha256=self.fixture.manifest.manifest_sha256,
            broker_build_sha256=self.fixture.manifest.broker_build_sha256,
            reviewer_id="independent-r0-reviewer",
            reviewed_at=self.now - timedelta(seconds=10),
            valid_until=self.now + timedelta(minutes=1),
        )
        r1 = r0.model_copy(
            update={
                "phase": "R1",
                "evidence_sha256": self.anchor.r1_review_sha256,
                "reviewer_id": "independent-r1-reviewer",
            }
        )
        self.packet = OfflineR2EntryPacket(
            manifest_sha256=self.fixture.manifest.manifest_sha256,
            signed_release_sha256=digest(canonical_bytes(self.proposed)),
            route_observation_sha256=digest(
                canonical_bytes(self.fixture.route_probe.current)
            ),
            g6_05=go,
            r0=r0,
            r1=r1,
            oncall_ready=True,
            oncall_evidence_sha256=self.anchor.oncall_evidence_sha256,
            proposed_at=self.now,
        )

    def make_owner_go_sha256(self, fixture: cohort_module.CohortControllerTests) -> str:
        now = fixture.now
        budget = fixture.base.budget_policy
        manifest = fixture.manifest
        q = qualification_module.RoutingQualificationTests()
        q.now_override = now
        q.setUp()
        q.route = fixture.base.selection.route
        identity = ExactRouteMetadata.from_candidate(
            q.route, qualification_module.sha("capabilities")
        )
        q.packet = q.packet.model_copy(
            update={
                "scope": q.packet.scope.model_copy(
                    update={
                        "owner_id": manifest.owner_id,
                        "cohort_id": manifest.cohort_id,
                        "task_enrollment_sha256": task_enrollment_sha256(
                            manifest.tasks
                        ),
                        "stages": manifest.stages,
                        "max_tasks": budget.max_tasks,
                        "task_ceiling_microusd": budget.task_ceiling_microusd,
                        "session_ceiling_microusd": budget.session_ceiling_microusd,
                        "cohort_ceiling_microusd": budget.cohort_ceiling_microusd,
                        "request_maximum_microusd": budget.request_maximum_microusd,
                    }
                ),
                "candidate": q.packet.candidate.model_copy(
                    update={
                        "candidate_policy_sha256": manifest.candidate_policy_sha256,
                        "routes": (
                            QualifiedRoute(
                                identity=identity,
                                purpose="selected",
                                pricing_basis="fixture-basis",
                                max_normalized_cost_microusd=100,
                            ),
                        ),
                    }
                ),
                "authority": q.packet.authority.model_copy(
                    update={
                        "promotion_receipt_sha256": manifest.promotion_receipt_sha256,
                        "preflight_sha256": fixture.base.preflight.preflight_sha256,
                    }
                ),
                "witness": q.packet.witness.model_copy(
                    update={
                        "enrollment_sha256": manifest.witness_enrollment_sha256,
                        "budget_policy_sha256": manifest.budget_policy_sha256,
                        "epoch_id": manifest.witness_epoch_id,
                    }
                ),
                "runtime": q.packet.runtime.model_copy(
                    update={
                        "broker_build_sha256": manifest.broker_build_sha256,
                        "target_host_id": manifest.target_host_id,
                    }
                ),
            }
        )
        q.drill_protocol = q.joined_protocol()
        q.drill_index = q.joined_evidence(q.drill_protocol).model_copy(
            update={"assembled_at": now - timedelta(minutes=7)}
        )
        q.evidence = q.rebind_drill(q.drill_index).model_copy(
            update={
                "packet_sha256": q.packet.packet_sha256,
                "route_observations": (
                    q.evidence.route_observations[0].model_copy(
                        update={
                            "identity": identity,
                            "normalized_cost_microusd": 100,
                        }
                    ),
                ),
            }
        )
        self.qualification = q
        self.source_handoff = q.source_handoff()
        self.readiness = q.decision_readiness(self.source_handoff)
        self.owner_trust = G605OwnerDecisionTrust(
            owner_id=manifest.owner_id,
            signer_id="g605-owner",
            public_key_base64=base64.b64encode(
                self.owner_decision_key.public_key().public_bytes_raw()
            ).decode("ascii"),
            valid_from=now - timedelta(minutes=1),
            valid_until=now + timedelta(minutes=5),
        )
        self.owner_anchor = FrozenG605OwnerDecisionAnchor(
            qualification_packet_sha256=q.packet.packet_sha256,
            qualification_evidence_sha256=q.evidence.evidence_sha256,
            source_handoff_sha256=self.source_handoff.handoff_sha256,
            decision_readiness_sha256=self.readiness.readiness_sha256,
            technical_review_sha256=self.readiness.technical_review_sha256,
            g5_claim_sha256=q.packet.candidate.g5_claim_sha256,
            owner_trust_sha256=digest(canonical_bytes(self.owner_trust)),
            valid_until=now + timedelta(minutes=5),
        )
        decision = G605OwnerDecision(
            status="go",
            qualification_packet_sha256=self.owner_anchor.qualification_packet_sha256,
            qualification_evidence_sha256=self.owner_anchor.qualification_evidence_sha256,
            source_handoff_sha256=self.owner_anchor.source_handoff_sha256,
            decision_readiness_sha256=self.owner_anchor.decision_readiness_sha256,
            technical_review_sha256=self.owner_anchor.technical_review_sha256,
            g5_claim_sha256=self.owner_anchor.g5_claim_sha256,
            owner_id=manifest.owner_id,
            cohort_id=manifest.cohort_id,
            signer_id=self.owner_trust.signer_id,
            candidate_policy_sha256=manifest.candidate_policy_sha256,
            selected_candidate_id=fixture.base.selection.candidate_id,
            broker_build_sha256=manifest.broker_build_sha256,
            target_host_id=manifest.target_host_id,
            witness_epoch_id=manifest.witness_epoch_id,
            approved_task_types=("review",),
            approved_stages=manifest.stages,
            max_assignments=manifest.max_assignments,
            max_concurrent=manifest.max_concurrent,
            task_ceiling_microusd=budget.task_ceiling_microusd,
            session_ceiling_microusd=budget.session_ceiling_microusd,
            cohort_ceiling_microusd=budget.cohort_ceiling_microusd,
            request_maximum_microusd=budget.request_maximum_microusd,
            max_stop_latency_ms=1000,
            issued_at=now - timedelta(seconds=10),
            valid_until=now + timedelta(minutes=5),
        )
        self.owner_decision = sign_synthetic_g605_owner_decision(
            decision, self.owner_decision_key.private_bytes_raw()
        )
        return self.owner_decision.decision_sha256

    def validate(self, **changes: object):
        values: dict[str, object] = {
            "packet": self.packet,
            "anchor": self.anchor,
            "signed_release": self.proposed,
            "selection": self.fixture.base.selection,
            "preflight": self.fixture.base.preflight,
            "admission": self.fixture.base.admission,
            "store": self.fixture.base.store,
            "audit": self.fixture.audit,
            "recovery_anchor": self.fixture.recovery_anchor,
            "route_probe": self.fixture.route_probe,
            "monitor": self.fixture.base.monitor,
            "alerts": self.fixture.alerts,
            "now": self.now,
        }
        values.update(changes)
        return validate_offline_r2_entry(**values)  # type: ignore[arg-type]

    def validate_joined(self, **changes: object):
        values: dict[str, object] = {
            "packet": self.packet,
            "anchor": self.anchor,
            "owner_decision": self.owner_decision,
            "owner_trust": self.owner_trust,
            "owner_anchor": self.owner_anchor,
            "signed_release": self.proposed,
            "selection": self.fixture.base.selection,
            "preflight": self.fixture.base.preflight,
            "admission": self.fixture.base.admission,
            "store": self.fixture.base.store,
            "audit": self.fixture.audit,
            "recovery_anchor": self.fixture.recovery_anchor,
            "route_probe": self.fixture.route_probe,
            "monitor": self.fixture.base.monitor,
            "alerts": self.fixture.alerts,
            "now": self.now,
        }
        values.update(changes)
        return validate_joined_offline_r2_entry(**values)  # type: ignore[arg-type]

    def validate_end_to_end(self, **changes: object):
        q = self.qualification
        values: dict[str, object] = {
            "packet": self.packet,
            "anchor": self.anchor,
            "owner_decision": self.owner_decision,
            "owner_trust": self.owner_trust,
            "owner_anchor": self.owner_anchor,
            "qualification_packet": q.packet,
            "qualification_evidence": q.evidence,
            "drill_protocol": q.drill_protocol,
            "drill_index": q.drill_index,
            "source_handoff": self.source_handoff,
            "readiness": self.readiness,
            "review_trust": q.trust,
            "reviews": q.reviews(),
            "expected_inspection_protocol_sha256": qualification_module.sha(
                "inspection-protocol"
            ),
            "expected_reviewer_roster_sha256": qualification_module.sha(
                "reviewer-roster"
            ),
            "expected_review_trust_sha256": digest(canonical_bytes(q.trust)),
            "expected_technical_review_sha256": qualification_module.sha(
                "technical-review-freeze"
            ),
            "signed_release": self.proposed,
            "selection": self.fixture.base.selection,
            "preflight": self.fixture.base.preflight,
            "admission": self.fixture.base.admission,
            "store": self.fixture.base.store,
            "audit": self.fixture.audit,
            "recovery_anchor": self.fixture.recovery_anchor,
            "route_probe": self.fixture.route_probe,
            "monitor": self.fixture.base.monitor,
            "alerts": self.fixture.alerts,
            "now": self.now,
        }
        values.update(changes)
        return validate_end_to_end_offline_r2_entry(**values)  # type: ignore[arg-type]

    def test_end_to_end_readiness_to_r2_is_reviewable_only(self) -> None:
        before = self.fixture.base.admission.read_current()
        checkpoint = self.fixture.base.admission.checkpoint.read_current()
        result = self.validate_end_to_end()
        self.assertEqual((result.status, result.reasons), ("reviewable", ()))
        self.assertTrue(result.signed_owner_decision_checked)
        self.assertTrue(result.readiness_checked)
        self.assertFalse(result.owner_release_authorized)
        self.assertFalse(result.dispatch_authorized)
        self.assertEqual(self.fixture.base.admission.read_current(), before)
        self.assertEqual(
            self.fixture.base.admission.checkpoint.read_current(), checkpoint
        )
        self.assert_shadow_unchanged()

    def test_end_to_end_rechecks_all_readiness_inputs(self) -> None:
        q = self.qualification
        cases = (
            (
                {
                    "readiness": self.readiness.model_copy(
                        update={
                            "valid_until": self.now,
                        }
                    )
                },
                "g6_05_readiness_invalid",
            ),
            (
                {
                    "readiness": self.readiness.model_copy(
                        update={
                            "source_inspections": (
                                self.readiness.source_inspections[0].model_copy(
                                    update={"status": "reject"}
                                ),
                                *self.readiness.source_inspections[1:],
                            )
                        }
                    )
                },
                "g6_05_readiness_invalid",
            ),
            (
                {"reviews": q.reviews(decision="reject")},
                "g6_05_readiness_invalid",
            ),
            (
                {
                    "source_handoff": self.source_handoff.model_copy(
                        update={
                            "references": (
                                self.source_handoff.references[0].model_copy(
                                    update={"status": "unavailable"}
                                ),
                                *self.source_handoff.references[1:],
                            )
                        }
                    )
                },
                "g6_05_readiness_invalid",
            ),
            (
                {
                    "qualification_evidence": q.evidence.model_copy(
                        update={
                            "route_observations": (
                                q.evidence.route_observations[0].model_copy(
                                    update={"valid_until": self.now}
                                ),
                            )
                        }
                    )
                },
                "g6_05_readiness_invalid",
            ),
            (
                {"expected_technical_review_sha256": digest(b"wrong-review")},
                "g6_05_readiness_invalid",
            ),
            (
                {"expected_inspection_protocol_sha256": digest(b"wrong-inspection")},
                "g6_05_readiness_invalid",
            ),
            (
                {"expected_review_trust_sha256": digest(b"wrong-q7-trust")},
                "g6_05_readiness_invalid",
            ),
            (
                {
                    "owner_anchor": self.owner_anchor.model_copy(
                        update={
                            "decision_readiness_sha256": digest(
                                b"wrong-frozen-readiness"
                            )
                        }
                    )
                },
                "g6_05_readiness_owner_binding_mismatch",
            ),
            (
                {"owner_decision": None},
                "g6_05_owner_decision_missing",
            ),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason, changes=tuple(changes)):
                result = self.validate_end_to_end(**changes)
                self.assertEqual(result.status, "blocked")
                self.assertIn(reason, result.reasons)
                self.assertFalse(result.dispatch_authorized)
                self.assert_shadow_unchanged()

    def test_end_to_end_qualified_scope_and_decision_time_deny(self) -> None:
        q = self.qualification
        narrower = q.packet.model_copy(
            update={"scope": q.packet.scope.model_copy(update={"max_tasks": 1})}
        )
        result = self.validate_end_to_end(qualification_packet=narrower)
        self.assertIn("g6_05_qualified_scope_mismatch", result.reasons)
        self.assertIn("g6_05_qualified_cohort_mismatch", result.reasons)
        changed_roster = q.packet.model_copy(
            update={
                "scope": q.packet.scope.model_copy(
                    update={"task_enrollment_sha256": digest(b"other-roster")}
                )
            }
        )
        result = self.validate_end_to_end(qualification_packet=changed_roster)
        self.assertIn("g6_05_qualified_cohort_mismatch", result.reasons)
        changed_policy = q.packet.model_copy(
            update={
                "candidate": q.packet.candidate.model_copy(
                    update={"candidate_policy_sha256": digest(b"other-policy")}
                )
            }
        )
        result = self.validate_end_to_end(qualification_packet=changed_policy)
        self.assertIn("g6_05_qualified_scope_mismatch", result.reasons)
        earlier = self.owner_decision.decision.model_copy(
            update={"issued_at": self.readiness.assembled_at - timedelta(seconds=1)}
        )
        resigned = sign_synthetic_g605_owner_decision(
            earlier, self.owner_decision_key.private_bytes_raw()
        )
        result = self.validate_end_to_end(owner_decision=resigned)
        self.assertIn("g6_05_decision_readiness_window_mismatch", result.reasons)
        self.assertEqual(result.status, "blocked")
        self.assert_shadow_unchanged()

    def assert_shadow_unchanged(self) -> None:
        state = self.fixture.base.admission.read_current()
        cohort = state.cohort
        assert cohort is not None
        self.assertEqual(cohort.signed_release, self.fixture.shadow)
        self.assertEqual(cohort.assignments, ())
        self.assertEqual(state.attempts, ())
        self.assertEqual(self.fixture.base.store.list_intents(), ())
        self.assertEqual(self.fixture.audit.read_current(), ())
        self.assertEqual(self.fixture.base.transport.entries, [])

    def test_complete_synthetic_entry_is_only_reviewable(self) -> None:
        before = self.fixture.base.admission.read_current()
        checkpoint = self.fixture.base.admission.checkpoint.read_current()
        result = self.validate()
        self.assertEqual((result.status, result.reasons), ("reviewable", ()))
        self.assertFalse(result.signed_owner_decision_checked)
        self.assertEqual(result.remaining_cohort_microusd, 200)
        self.assertEqual((result.assignment_count, result.claim_count), (0, 0))
        self.assertFalse(result.owner_release_authorized)
        self.assertFalse(result.dispatch_authorized)
        self.assertEqual(self.fixture.base.admission.read_current(), before)
        self.assertEqual(
            self.fixture.base.admission.checkpoint.read_current(), checkpoint
        )
        self.assert_shadow_unchanged()

    def test_missing_go_review_oncall_or_binding_blocks(self) -> None:
        cases = (
            (
                self.packet.model_copy(
                    update={
                        "g6_05": self.packet.g6_05.model_copy(
                            update={"status": "no_go"}
                        )
                    }
                ),
                "g6_05_go_invalid",
            ),
            (
                self.packet.model_copy(
                    update={
                        "g6_05": self.packet.g6_05.model_copy(
                            update={"packet_sha256": digest(b"changed")}
                        )
                    }
                ),
                "g6_05_go_invalid",
            ),
            (
                self.packet.model_copy(
                    update={
                        "r0": self.packet.r0.model_copy(
                            update={"status": "unavailable"}
                        )
                    }
                ),
                "r0_review_invalid",
            ),
            (
                self.packet.model_copy(
                    update={
                        "r1": self.packet.r1.model_copy(
                            update={"evidence_sha256": digest(b"changed")}
                        )
                    }
                ),
                "r1_review_invalid",
            ),
            (
                self.packet.model_copy(update={"oncall_ready": False}),
                "oncall_not_ready",
            ),
            (
                self.packet.model_copy(update={"manifest_sha256": digest(b"changed")}),
                "manifest_binding_mismatch",
            ),
            (
                self.packet.model_copy(
                    update={"signed_release_sha256": digest(b"changed")}
                ),
                "release_binding_mismatch",
            ),
        )
        for packet, reason in cases:
            with self.subTest(reason=reason):
                result = self.validate(packet=packet)
                self.assertEqual(result.status, "blocked")
                self.assertIn(reason, result.reasons)
                self.assertFalse(result.dispatch_authorized)
        self.assert_shadow_unchanged()

    def test_changed_or_unsigned_release_and_shadow_self_promotion_block(self) -> None:
        bad_signature = self.proposed.model_copy(
            update={
                "owner_signature_base64": self.fixture.shadow.owner_signature_base64
            }
        )
        self.assertIn(
            "release_signature_invalid",
            self.validate(signed_release=bad_signature).reasons,
        )
        self.assertIn(
            "release_transition_invalid",
            self.validate(signed_release=self.fixture.shadow).reasons,
        )
        changed_go = self.packet.g6_05.model_copy(
            update={"candidate_policy_sha256": digest(b"changed-policy")}
        )
        self.assertIn(
            "source_binding_mismatch",
            self.validate(
                packet=self.packet.model_copy(update={"g6_05": changed_go})
            ).reasons,
        )
        with self.assertRaises(ValueError):
            self.fixture.assign()
        self.assert_shadow_unchanged()

    def test_stale_route_preflight_and_required_path_outages_block(self) -> None:
        current = self.fixture.route_probe.current
        stale = current.model_copy(
            update={"observed_at": self.now - timedelta(minutes=2)}
        )
        self.fixture.route_probe.current = stale
        self.packet = self.packet.model_copy(
            update={"route_observation_sha256": digest(canonical_bytes(stale))}
        )
        self.assertIn("route_observation_stale", self.validate().reasons)
        self.fixture.route_probe.current = current
        self.packet = self.packet.model_copy(
            update={"route_observation_sha256": digest(canonical_bytes(current))}
        )
        self.fixture.route_probe.current = current.model_copy(
            update={"available": False}
        )
        self.assertIn("route_unavailable", self.validate().reasons)
        self.fixture.route_probe.current = current
        self.fixture.base.monitor.healthy = False
        self.assertIn("required_path_unavailable", self.validate().reasons)
        self.fixture.base.monitor.healthy = True
        self.fixture.alerts.delivery_acknowledged = False
        self.assertIn("required_path_unavailable", self.validate().reasons)
        self.fixture.alerts.delivery_acknowledged = True
        expired = self.fixture.base.preflight.model_copy(
            update={"valid_until": self.now}
        )
        self.assertIn("preflight_expired", self.validate(preflight=expired).reasons)
        self.assert_shadow_unchanged()

    def test_budget_time_stop_and_recovery_denials(self) -> None:
        no_headroom = self.anchor.model_copy(update={"full_request_microusd": 201})
        self.assertIn(
            "budget_headroom_invalid", self.validate(anchor=no_headroom).reasons
        )
        expired = self.anchor.model_copy(update={"valid_until": self.now})
        self.assertIn("entry_time_invalid", self.validate(anchor=expired).reasons)
        stale_recovery = self.fixture.recovery_anchor.model_copy(
            update={"retained_exposure_microusd": 100}
        )
        # A retained high-water exposure alone is conservative, not a mismatch.
        self.assertEqual(
            self.validate(recovery_anchor=stale_recovery).status, "reviewable"
        )
        retained_exposure = self.fixture.recovery_anchor.model_copy(
            update={"retained_exposure_microusd": 150}
        )
        retained_result = self.validate(recovery_anchor=retained_exposure)
        self.assertIn("budget_headroom_invalid", retained_result.reasons)
        self.assertEqual(retained_result.remaining_cohort_microusd, 50)
        missing_assignment = self.fixture.recovery_anchor.model_copy(
            update={"assignment_task_ids": ("missing-task",)}
        )
        self.assertIn(
            "recovery_mismatch",
            self.validate(recovery_anchor=missing_assignment).reasons,
        )
        stopped = self.fixture.base.stop_entry()
        self.fixture.base.admission.advance_control(
            stopped, self.now + timedelta(seconds=1)
        )
        self.assertIn("release_transition_invalid", self.validate().reasons)
        self.assert_shadow_unchanged()

    def test_witness_and_audit_outages_block_without_entry(self) -> None:
        with patch.object(
            self.fixture.base.admission,
            "read_current",
            side_effect=OSError("synthetic witness outage"),
        ):
            result = self.validate()
        self.assertEqual(result.status, "blocked")
        self.assertIn("witness_unavailable", result.reasons)
        self.fixture.audit.healthy = False
        result = self.validate()
        self.assertEqual(result.status, "blocked")
        self.assertIn("required_path_unavailable", result.reasons)
        self.fixture.audit.healthy = True
        self.assert_shadow_unchanged()

    def test_joined_owner_go_is_only_synthetic_r2_reviewable(self) -> None:
        owner = validate_offline_g605_owner_decision(
            signed=self.owner_decision,
            trust=self.owner_trust,
            anchor=self.owner_anchor,
            now=self.now,
        )
        self.assertTrue(owner.go_reference_reviewable)
        self.assertFalse(owner.g5_qualified)
        self.assertFalse(owner.qualification_authorized)
        self.assertFalse(owner.dispatch_authorized)
        result = self.validate_joined()
        self.assertEqual((result.status, result.reasons), ("reviewable", ()))
        self.assertTrue(result.signed_owner_decision_checked)
        self.assertFalse(result.owner_release_authorized)
        self.assertFalse(result.dispatch_authorized)
        self.assert_shadow_unchanged()

    def test_joined_owner_no_go_tamper_and_wrong_trust_block(self) -> None:
        missing = self.validate_joined(owner_decision=None)
        self.assertIn("g6_05_owner_decision_missing", missing.reasons)
        self.assertFalse(missing.signed_owner_decision_checked)
        no_go = sign_synthetic_g605_owner_decision(
            self.owner_decision.decision.model_copy(update={"status": "no_go"}),
            self.owner_decision_key.private_bytes_raw(),
        )
        result = self.validate_joined(owner_decision=no_go)
        self.assertIn("g6_05_owner_decision_invalid", result.reasons)
        self.assertIn("g6_05_signed_go_binding_mismatch", result.reasons)
        altered = SignedG605OwnerDecision(
            decision=self.owner_decision.decision.model_copy(
                update={"max_stop_latency_ms": 1}
            ),
            signature_base64=self.owner_decision.signature_base64,
        )
        self.assertIn(
            "g6_05_owner_decision_invalid",
            self.validate_joined(owner_decision=altered).reasons,
        )
        wrong_trust = self.owner_anchor.model_copy(
            update={"owner_trust_sha256": digest(b"wrong-owner-trust")}
        )
        self.assertIn(
            "g6_05_owner_decision_invalid",
            self.validate_joined(owner_anchor=wrong_trust).reasons,
        )
        self.assert_shadow_unchanged()

    def test_joined_owner_expiry_and_readiness_rebind_block(self) -> None:
        stale = self.owner_decision.decision.model_copy(
            update={"valid_until": self.now}
        )
        signed_stale = sign_synthetic_g605_owner_decision(
            stale, self.owner_decision_key.private_bytes_raw()
        )
        self.assertIn(
            "g6_05_owner_decision_invalid",
            self.validate_joined(owner_decision=signed_stale).reasons,
        )
        wrong_readiness = self.owner_anchor.model_copy(
            update={"decision_readiness_sha256": digest(b"changed-readiness")}
        )
        self.assertIn(
            "g6_05_owner_decision_invalid",
            self.validate_joined(owner_anchor=wrong_readiness).reasons,
        )
        self.assert_shadow_unchanged()

    def test_joined_owner_scope_and_signed_digest_mismatch_block(self) -> None:
        changed_go = self.packet.g6_05.model_copy(
            update={"decision_sha256": digest(b"unrelated-go")}
        )
        changed_packet = self.packet.model_copy(update={"g6_05": changed_go})
        self.assertIn(
            "g6_05_signed_go_binding_mismatch",
            self.validate_joined(packet=changed_packet).reasons,
        )
        narrower = sign_synthetic_g605_owner_decision(
            self.owner_decision.decision.model_copy(update={"max_assignments": 1}),
            self.owner_decision_key.private_bytes_raw(),
        )
        result = self.validate_joined(owner_decision=narrower)
        self.assertIn("g6_05_operating_envelope_mismatch", result.reasons)
        self.assertIn("g6_05_signed_go_binding_mismatch", result.reasons)
        changed_route = sign_synthetic_g605_owner_decision(
            self.owner_decision.decision.model_copy(
                update={"selected_candidate_id": digest(b"wrong-route")}
            ),
            self.owner_decision_key.private_bytes_raw(),
        )
        result = self.validate_joined(owner_decision=changed_route)
        self.assertIn("g6_05_operating_envelope_mismatch", result.reasons)
        shorter = sign_synthetic_g605_owner_decision(
            self.owner_decision.decision.model_copy(
                update={"valid_until": self.now + timedelta(minutes=1)}
            ),
            self.owner_decision_key.private_bytes_raw(),
        )
        self.assertIn(
            "g6_05_signed_go_binding_mismatch",
            self.validate_joined(owner_decision=shorter).reasons,
        )
        self.assert_shadow_unchanged()

    def test_owner_decision_schema_rejects_unsafe_envelope_and_content(self) -> None:
        decision = self.owner_decision.decision
        with self.assertRaises(ValidationError):
            G605OwnerDecision.model_validate(
                {
                    **decision.model_dump(),
                    "max_concurrent": decision.max_assignments + 1,
                }
            )
        with self.assertRaises(ValidationError):
            G605OwnerDecision.model_validate(
                {**decision.model_dump(), "source_text": "forbidden"}
            )

    def test_owner_decision_cli_only_reports_bounded_reference(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("decision", self.owner_decision),
                ("trust", self.owner_trust),
                ("anchor", self.owner_anchor),
            ):
                (root / f"{name}.json").write_text(value.model_dump_json())
            command = [
                sys.executable,
                "-m",
                "mos_eisley.run.routing_owner_decision",
                str(root / "decision.json"),
                str(root / "trust.json"),
                str(root / "anchor.json"),
                "--now",
                self.now.isoformat(),
            ]
            passed = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            payload = json.loads(passed.stdout)
            self.assertTrue(payload["go_reference_reviewable"])
            self.assertFalse(payload["qualification_authorized"])
            self.assertNotIn("decision", payload)
            rejected = sign_synthetic_g605_owner_decision(
                self.owner_decision.decision.model_copy(update={"status": "no_go"}),
                self.owner_decision_key.private_bytes_raw(),
            )
            (root / "decision.json").write_text(rejected.model_dump_json())
            denied = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(denied.returncode, 1, denied.stderr)
            self.assertIn("owner_no_go", json.loads(denied.stdout)["reasons"])
