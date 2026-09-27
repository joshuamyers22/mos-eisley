"""G6-06 R2 metadata-only entry packet and synthetic denial rehearsal."""

from __future__ import annotations

from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.cohort_entry import (
    FrozenR2EntryAnchor,
    OfflineR2EntryPacket,
    R2GoReference,
    R2ReviewReference,
    validate_offline_r2_entry,
)
from tests import test_cohort_controller as cohort_module


class CohortR2EntryTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.now = self.fixture.now
        self.proposed = self.fixture.release("bounded_live", 1)
        self.anchor = FrozenR2EntryAnchor(
            manifest_sha256=self.fixture.manifest.manifest_sha256,
            g6_05_go_sha256=self.fixture.go_sha256,
            g6_05_packet_sha256=digest(b"r2-synthetic-g6-05-packet"),
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
