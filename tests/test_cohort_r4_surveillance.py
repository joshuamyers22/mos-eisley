"""G6-06 R4 synthetic surveillance, fault and signed-stop rehearsal."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.cohort_surveillance import (
    FrozenR4SurveillanceAnchor,
    OfflineR4SurveillancePacket,
    OfflineR4SurveillanceResult,
    OfflineR4TransportEntryReference,
    inspect_offline_r4_surveillance,
)
from tests import test_cohort_controller as cohort_module


class CohortR4SurveillanceTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.release = self.fixture.live()
        self.fixture.assign()
        self.base = self.fixture.base
        self.now = self.fixture.now
        self.anchor = FrozenR4SurveillanceAnchor(
            manifest_sha256=self.fixture.manifest.manifest_sha256,
            release_sha256=self.release.release.release_sha256,
            selection_sha256=digest(canonical_bytes(self.base.selection)),
            safety_evidence_sha256=digest(b"synthetic-r4-safety-evidence"),
            safety_signal="clear",
            safety_reviewed_at=self.now - timedelta(seconds=2),
            safety_valid_until=self.now + timedelta(minutes=2),
            max_route_age_seconds=60,
            max_observation_age_seconds=10,
            stop_ack_deadline_seconds=5,
            warning_remaining_cohort_microusd=50,
            hard_stop_exposure_microusd=180,
            valid_until=self.now + timedelta(minutes=2),
        )

    def packet(self, *, now: datetime | None = None) -> OfflineR4SurveillancePacket:
        current = now or self.now
        state = self.base.admission.read_current()
        refs: list[OfflineR4TransportEntryReference] = []
        if self.base.transport.entries:
            claim = state.attempts[0]
            intent = self.base.store.list_intents()[0]
            refs.append(
                OfflineR4TransportEntryReference(
                    entry_index=0,
                    attempt_key=claim.attempt.attempt_key,
                    request_sha256=self.base.transport.entries[0],
                    intent_sha256=intent.intent_sha256,
                    claim_id=claim.claim_id,
                    observed_at=current,
                )
            )
        return OfflineR4SurveillancePacket(
            manifest_sha256=self.anchor.manifest_sha256,
            release_sha256=self.anchor.release_sha256,
            selection_sha256=self.anchor.selection_sha256,
            route_observation_sha256=digest(
                canonical_bytes(self.fixture.route_probe.current)
            ),
            control_entry_sha256=state.control.anchor_entry_sha256,
            safety_signal="clear",
            safety_evidence_sha256=self.anchor.safety_evidence_sha256,
            safety_reviewed_at=self.anchor.safety_reviewed_at,
            safety_valid_until=self.anchor.safety_valid_until,
            observed_at=current,
            entries=tuple(refs),
        )

    def inspect(
        self,
        packet: OfflineR4SurveillancePacket | None = None,
        *,
        anchor: FrozenR4SurveillanceAnchor | None = None,
        now: datetime | None = None,
    ) -> OfflineR4SurveillanceResult:
        return inspect_offline_r4_surveillance(
            packet or self.packet(now=now),
            anchor=anchor or self.anchor,
            selection=self.base.selection,
            preflight=self.base.preflight,
            admission=self.base.admission,
            store=self.base.store,
            audit=self.fixture.audit,
            recovery_anchor=self.fixture.recovery_anchor,
            route_probe=self.fixture.route_probe,
            monitor=self.base.monitor,
            alerts=self.fixture.alerts,
            transport=self.base.transport,
            now=now or self.now,
        )

    def test_healthy_snapshot_joins_one_inert_entry_without_mutation(self) -> None:
        self.assertEqual(self.fixture.execute().status, "settled")
        packet = self.packet()
        before_state = self.base.admission.read_current()
        before_checkpoint = self.base.admission.checkpoint.read_current()
        before_intents = self.base.store.list_intents()
        before_audit = self.fixture.audit.read_current()
        before_entries = tuple(self.base.transport.entries)
        result = self.inspect(packet)
        self.assertEqual((result.status, result.reasons), ("healthy", ()))
        self.assertEqual(
            (
                result.assignment_count,
                result.claim_count,
                result.unresolved_claim_count,
                result.uncertain_claim_count,
                result.intent_count,
                result.audit_count,
                result.transport_entry_count,
            ),
            (1, 1, 0, 0, 1, 1, 1),
        )
        self.assertEqual(
            (result.conservative_exposure_microusd, result.remaining_cohort_microusd),
            (15, 185),
        )
        self.assertFalse(result.stop_required)
        self.assertFalse(result.new_admission_authorized)
        self.assertFalse(result.stop_authorized)
        self.assertFalse(result.dispatch_authorized)
        self.assertEqual(self.base.admission.read_current(), before_state)
        self.assertEqual(
            self.base.admission.checkpoint.read_current(), before_checkpoint
        )
        self.assertEqual(self.base.store.list_intents(), before_intents)
        self.assertEqual(self.fixture.audit.read_current(), before_audit)
        self.assertEqual(tuple(self.base.transport.entries), before_entries)

    def test_missing_duplicate_or_changed_transport_reference_is_hard_stop(
        self,
    ) -> None:
        self.fixture.execute()
        packet = self.packet()
        missing = packet.model_copy(update={"entries": ()})
        self.assertIn("transport_entry_unjoined", self.inspect(missing).reasons)
        changed = packet.model_copy(
            update={
                "entries": (
                    packet.entries[0].model_copy(
                        update={"claim_id": digest(b"wrong-claim")}
                    ),
                )
            }
        )
        self.assertIn("transport_entry_unjoined", self.inspect(changed).reasons)
        duplicate = packet.model_copy(update={"entries": packet.entries * 2})
        self.assertIn("transport_entry_invalid", self.inspect(duplicate).reasons)
        self.base.transport.entries.append(self.base.transport.entries[0])
        self.assertIn("transport_entry_unjoined", self.inspect(packet).reasons)
        self.assertTrue(self.inspect(packet).stop_required)

    def test_cut_after_claim_or_intent_requires_stop_without_send(self) -> None:
        def cut(phase: str) -> None:
            if phase == "after_intent":
                raise RuntimeError("synthetic intent cut")

        with self.assertRaises(RuntimeError):
            self.fixture.execute(fault=cut)
        result = self.inspect()
        self.assertEqual(result.status, "hard_stop")
        self.assertIn("audit_join_incomplete", result.reasons)
        self.assertIn("intent_audit_missing", result.reasons)
        self.assertEqual(result.conservative_exposure_microusd, 100)
        self.assertEqual(result.transport_entry_count, 0)
        self.assertTrue(result.stop_required)
        self.assertEqual(self.base.transport.entries, [])

    def test_cut_after_claim_exposes_missing_intent(self) -> None:
        def cut(phase: str) -> None:
            if phase == "after_admission":
                raise RuntimeError("synthetic claim cut")

        with self.assertRaises(RuntimeError):
            self.fixture.execute(fault=cut)
        result = self.inspect()
        self.assertEqual(result.status, "hard_stop")
        self.assertIn("claim_intent_missing", result.reasons)
        self.assertEqual(result.conservative_exposure_microusd, 100)
        self.assertEqual(result.transport_entry_count, 0)

    def test_route_control_safety_and_required_path_faults_fail_closed(self) -> None:
        self.fixture.execute()
        packet = self.packet()
        stale = self.fixture.route_probe.current.model_copy(
            update={"observed_at": self.now - timedelta(minutes=2)}
        )
        self.fixture.route_probe.current = stale
        stale_packet = packet.model_copy(
            update={"route_observation_sha256": digest(canonical_bytes(stale))}
        )
        self.assertIn("route_observation_stale", self.inspect(stale_packet).reasons)
        self.fixture.route_probe.current = self.fixture.route_probe.current.model_copy(
            update={"available": False}
        )
        self.assertIn("route_unavailable", self.inspect().reasons)
        self.assertIn(
            "control_binding_mismatch",
            self.inspect(
                packet.model_copy(
                    update={"control_entry_sha256": digest(b"wrong-control")}
                )
            ).reasons,
        )
        self.assertIn(
            "safety_hard_stop",
            self.inspect(
                packet.model_copy(update={"safety_signal": "hard_stop"})
            ).reasons,
        )
        self.assertIn(
            "safety_signal_unavailable",
            self.inspect(
                packet.model_copy(update={"safety_signal": "unavailable"})
            ).reasons,
        )
        hard_safety_anchor = self.anchor.model_copy(
            update={"safety_signal": "hard_stop"}
        )
        hard_safety_packet = packet.model_copy(update={"safety_signal": "hard_stop"})
        self.assertIn(
            "safety_hard_stop",
            self.inspect(hard_safety_packet, anchor=hard_safety_anchor).reasons,
        )
        self.assertIn(
            "safety_signal_unavailable",
            self.inspect(packet, anchor=hard_safety_anchor).reasons,
        )
        self.base.monitor.healthy = False
        self.assertIn("monitor_unavailable", self.inspect(packet).reasons)
        self.base.monitor.healthy = True
        self.fixture.alerts.delivery_acknowledged = False
        self.assertIn("alert_unavailable", self.inspect(packet).reasons)
        self.fixture.assign("task-c", "session-b")
        with self.assertRaises(ValueError):
            self.fixture.execute(
                envelope=self.base.make_envelope(
                    task_id="task-c", session_id="session-b", attempt_id="attempt-c"
                )
            )
        self.assertEqual(len(self.base.admission.read_current().attempts), 1)
        self.assertEqual(len(self.base.transport.entries), 1)
        self.fixture.alerts.delivery_acknowledged = True
        self.fixture.audit.healthy = False
        self.assertIn("audit_unavailable", self.inspect(packet).reasons)

    def test_retained_exposure_warns_or_stops_without_refund(self) -> None:
        self.fixture.execute()
        warning_anchor = self.fixture.recovery_anchor.model_copy(
            update={"retained_exposure_microusd": 160}
        )
        original = self.fixture.recovery_anchor
        self.fixture.recovery_anchor = warning_anchor
        warned = self.inspect()
        self.assertEqual(warned.status, "warning")
        self.assertEqual(warned.remaining_cohort_microusd, 25)
        self.assertIn("cohort_headroom_warning", warned.reasons)
        self.assertFalse(warned.stop_required)
        self.fixture.recovery_anchor = original.model_copy(
            update={"retained_exposure_microusd": 190}
        )
        stopped = self.inspect()
        self.assertEqual(stopped.status, "hard_stop")
        self.assertIn("cohort_budget_exhausted", stopped.reasons)
        self.assertIn("exposure_hard_stop", stopped.reasons)
        self.assertEqual(stopped.conservative_exposure_microusd, 205)
        self.assertEqual(stopped.remaining_cohort_microusd, 0)
        self.assertTrue(stopped.stop_required)

    def test_uncertain_attempt_is_visible_without_refund(self) -> None:
        self.base.transport.error = TimeoutError("synthetic transport timeout")
        self.assertEqual(self.fixture.execute().status, "uncertain")
        result = self.inspect()
        self.assertEqual(result.status, "warning")
        self.assertIn("unresolved_exposure", result.reasons)
        self.assertEqual(
            (result.unresolved_claim_count, result.uncertain_claim_count), (1, 1)
        )
        self.assertEqual(
            (result.conservative_exposure_microusd, result.remaining_cohort_microusd),
            (100, 100),
        )
        self.assertFalse(result.new_admission_authorized)

    def test_witness_outage_and_stale_observation_fail_closed(self) -> None:
        packet = self.packet()
        with patch.object(
            self.base.admission,
            "read_current",
            side_effect=OSError("synthetic witness outage"),
        ):
            result = self.inspect(packet)
        self.assertEqual(result.status, "hard_stop")
        self.assertIn("witness_unavailable", result.reasons)
        stale = packet.model_copy(
            update={"observed_at": self.now - timedelta(seconds=11)}
        )
        self.assertIn("observation_stale", self.inspect(stale).reasons)

    def test_stop_request_needs_signed_witness_ack_before_deadline(self) -> None:
        self.fixture.execute()
        pending = self.packet().model_copy(update={"stop_requested_at": self.now})
        stop_anchor = self.anchor.model_copy(update={"stop_requested_at": self.now})
        before = self.inspect(pending, anchor=stop_anchor)
        self.assertEqual(before.status, "hard_stop")
        self.assertIn("stop_ack_missing", before.reasons)
        self.assertTrue(before.stop_required)
        self.assertIn(
            "stop_request_mismatch",
            self.inspect(self.packet(), anchor=stop_anchor).reasons,
        )

        signed_stop = self.base.stop_entry()
        self.base.admission.advance_control(
            signed_stop, self.now + timedelta(seconds=1)
        )
        after_time = self.now + timedelta(seconds=1)
        after = self.packet(now=after_time).model_copy(
            update={"stop_requested_at": self.now}
        )
        result = self.inspect(after, anchor=stop_anchor, now=after_time)
        self.assertEqual(result.status, "stopped")
        self.assertTrue(result.stop_acknowledged)
        self.assertFalse(result.stop_required)
        self.assertIn("witness_stopped", result.reasons)
        with self.assertRaises(ValueError):
            self.fixture.assign("task-c", "session-b", now=after_time)
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.base.transport.entries), 1)

        late = after.model_copy(
            update={"stop_requested_at": self.now - timedelta(seconds=10)}
        )
        late_anchor = stop_anchor.model_copy(
            update={"stop_requested_at": self.now - timedelta(seconds=10)}
        )
        late_result = self.inspect(late, anchor=late_anchor, now=after_time)
        self.assertIn("stop_ack_late", late_result.reasons)
        self.assertFalse(late_result.stop_acknowledged)
