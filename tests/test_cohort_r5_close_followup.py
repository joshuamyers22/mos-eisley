"""G6-06 R5 offline R4-triggered close and follow-up rehearsal."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest import TestCase

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.cohort_close_handoff import (
    FrozenR5CloseAnchor,
    OfflineR4TriggerReproduction,
    OfflineR5CloseResult,
    reproduce_offline_r4_trigger,
    validate_offline_r5_close_handoff,
    validate_reproduced_offline_r5_close_handoff,
)
from mos_eisley.run.cohort_closeout import (
    AttemptCloseoutLink,
    CloseoutEvidenceIndex,
    CohortCloseoutPacket,
    FrozenCloseoutProtocol,
    TaskFollowupIndex,
    validate_offline_cohort_closeout,
)
from mos_eisley.run.cohort_surveillance import (
    FrozenR4SurveillanceAnchor,
    OfflineR4SurveillancePacket,
    OfflineR4SurveillanceResult,
)
from mos_eisley.run.routing_transaction import (
    FrozenCohortRecoveryAnchor,
    OfflineOutcome,
    capture_synthetic_cohort_recovery_anchor,
)
from mos_eisley.run.witnessed_admission import (
    SignedCohortRelease,
    WitnessedState,
    sign_synthetic_cohort_release,
)
from tests import test_cohort_r4_surveillance as r4_module


class CohortR5CloseFollowupTests(TestCase):
    def setUp(self) -> None:
        self.r4 = r4_module.CohortR4SurveillanceTests()
        self.r4.setUp()
        self.addCleanup(self.r4.doCleanups)
        self.fixture = self.r4.fixture
        self.base = self.fixture.base
        self.now = self.fixture.now
        cutoff = self.now + timedelta(seconds=2)
        self.protocol = FrozenCloseoutProtocol(
            manifest_sha256=self.fixture.manifest.manifest_sha256,
            assessment_protocol_sha256=digest(b"r5-synthetic-assessment-protocol"),
            cutoff_at=cutoff,
            followup_due_at=cutoff + timedelta(days=1),
        )

    def closed_release(self, issued_at: datetime) -> SignedCohortRelease:
        release = self.fixture.release("closed", 2).release.model_copy(
            update={"issued_at": issued_at}
        )
        return sign_synthetic_cohort_release(
            release,
            owner_signer_id="cohort-owner",
            owner_private_key=self.fixture.owner_key.private_bytes_raw(),
            operator_signer_id="cohort-operator",
            operator_private_key=self.fixture.release_operator_key.private_bytes_raw(),
        )

    def packet(
        self,
        *,
        prepared_at: datetime,
        followups: tuple[TaskFollowupIndex, ...],
        local_dispositions: tuple[OfflineOutcome, ...] = (),
    ) -> CohortCloseoutPacket:
        state = self.base.admission.read_current()
        cohort = state.cohort
        assert cohort is not None
        intents = {item.attempt_key: item for item in self.base.store.list_intents()}
        local = {item.attempt_key: item for item in local_dispositions}
        return CohortCloseoutPacket(
            manifest_sha256=self.protocol.manifest_sha256,
            assessment_protocol_sha256=self.protocol.assessment_protocol_sha256,
            release_sha256=cohort.signed_release.release.release_sha256,
            witness_epoch_id=state.epoch_id,
            witness_generation=state.generation,
            witness_state_sha256=state.state_sha256,
            prepared_at=prepared_at,
            assignment_task_ids=tuple(item.task_id for item in cohort.assignments),
            attempt_links=tuple(
                AttemptCloseoutLink(
                    attempt_key=row.attempt.attempt_key,
                    claim_id=row.claim_id,
                    task_id=row.attempt.task_id,
                    intent_sha256=(
                        intents[row.attempt.attempt_key].intent_sha256
                        if row.attempt.attempt_key in intents
                        else None
                    ),
                    local_status=(
                        local[row.attempt.attempt_key].status
                        if row.attempt.attempt_key in local
                        else None
                    ),
                    local_charged_microusd=(
                        local[row.attempt.attempt_key].charged_microusd
                        if row.attempt.attempt_key in local
                        else None
                    ),
                )
                for row in state.attempts
            ),
            followups=followups,
            evidence=CloseoutEvidenceIndex(
                route_coverage_sha256=digest(b"r5-route-coverage"),
                cap_history_sha256=digest(b"r5-cap-history"),
                all_task_latency_sha256=digest(b"r5-all-task-latency"),
                monitoring_incidents_sha256=digest(b"r5-monitoring-incidents"),
                followup_custody_sha256=digest(b"r5-followup-custody"),
                protocol_deviations_sha256=digest(b"r5-protocol-deviations"),
            ),
        )

    def freeze(
        self,
        *,
        r4_packet: OfflineR4SurveillancePacket,
        r4_result: OfflineR4SurveillanceResult,
        trigger: str,
        closed: SignedCohortRelease,
    ) -> tuple[FrozenR5CloseAnchor, WitnessedState, FrozenCohortRecoveryAnchor]:
        prior = self.base.admission.read_current()
        recovery = capture_synthetic_cohort_recovery_anchor(
            self.base.admission, self.base.store, self.fixture.audit
        )
        anchor = FrozenR5CloseAnchor(
            manifest_sha256=self.protocol.manifest_sha256,
            closeout_protocol_sha256=digest(canonical_bytes(self.protocol)),
            preclose_state_sha256=prior.state_sha256,
            closed_release_sha256=closed.release.release_sha256,
            r4_packet_sha256=digest(canonical_bytes(r4_packet)),
            r4_result_sha256=digest(canonical_bytes(r4_result)),
            trigger=trigger,  # type: ignore[arg-type]
            triggered_at=r4_packet.observed_at,
            max_close_latency_seconds=5,
            valid_until=self.protocol.followup_due_at + timedelta(days=1),
        )
        return anchor, prior, recovery

    def inspect(
        self,
        packet: CohortCloseoutPacket,
        *,
        anchor: FrozenR5CloseAnchor,
        r4_packet: OfflineR4SurveillancePacket,
        r4_result: OfflineR4SurveillanceResult,
        prior: WitnessedState,
        recovery: FrozenCohortRecoveryAnchor,
    ) -> OfflineR5CloseResult:
        return validate_offline_r5_close_handoff(
            packet,
            protocol=self.protocol,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            preclose_state=prior,
            admission=self.base.admission,
            store=self.base.store,
            audit=self.fixture.audit,
            recovery_anchor=recovery,
            now=packet.prepared_at,
        )

    def reproduce_trigger(
        self,
        *,
        anchor: FrozenR5CloseAnchor,
        r4_anchor: FrozenR4SurveillanceAnchor,
        expected_r4_anchor_sha256: str,
        r4_packet: OfflineR4SurveillancePacket,
        r4_result: OfflineR4SurveillanceResult,
        prior: WitnessedState,
        recovery: FrozenCohortRecoveryAnchor,
    ) -> OfflineR4TriggerReproduction:
        return reproduce_offline_r4_trigger(
            protocol=self.protocol,
            close_anchor=anchor,
            r4_anchor=r4_anchor,
            expected_r4_anchor_sha256=expected_r4_anchor_sha256,
            r4_packet=r4_packet,
            r4_result=r4_result,
            preclose_state=prior,
            selection=self.base.selection,
            preflight=self.base.preflight,
            admission=self.base.admission,
            store=self.base.store,
            audit=self.fixture.audit,
            recovery_anchor=recovery,
            route_probe=self.fixture.route_probe,
            monitor=self.base.monitor,
            alerts=self.fixture.alerts,
            transport=self.base.transport,
            now=r4_packet.observed_at,
        )

    def inspect_reproduced(
        self,
        packet: CohortCloseoutPacket,
        *,
        anchor: FrozenR5CloseAnchor,
        r4_packet: OfflineR4SurveillancePacket,
        r4_result: OfflineR4SurveillanceResult,
        prior: WitnessedState,
        recovery: FrozenCohortRecoveryAnchor,
        reproduction: OfflineR4TriggerReproduction,
        expected_reproduction_sha256: str,
    ) -> OfflineR5CloseResult:
        return validate_reproduced_offline_r5_close_handoff(
            packet,
            protocol=self.protocol,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            preclose_state=prior,
            admission=self.base.admission,
            store=self.base.store,
            audit=self.fixture.audit,
            recovery_anchor=recovery,
            reproduction=reproduction,
            expected_reproduction_sha256=expected_reproduction_sha256,
            now=packet.prepared_at,
        )

    def stop_and_close(self, closed: SignedCohortRelease) -> None:
        stopped = self.base.stop_entry()
        self.base.admission.advance_control(stopped, self.now + timedelta(seconds=1))
        self.fixture.controller.advance_release(
            signed_release=closed, now=self.now + timedelta(seconds=1)
        )

    def test_reproduced_hard_stop_joins_later_pending_close(self) -> None:
        r4_packet = self.r4.packet().model_copy(update={"safety_signal": "hard_stop"})
        r4_anchor = self.r4.anchor.model_copy(update={"safety_signal": "hard_stop"})
        expected_r4_anchor_sha256 = digest(canonical_bytes(r4_anchor))
        r4_result = self.r4.inspect(r4_packet, anchor=r4_anchor)
        self.assertEqual(r4_result.status, "hard_stop")
        closed = self.closed_release(self.now + timedelta(seconds=1))
        anchor, prior, recovery = self.freeze(
            r4_packet=r4_packet,
            r4_result=r4_result,
            trigger="r4_hard_stop",
            closed=closed,
        )
        before = self.base.admission.read_current()
        before_checkpoint = self.base.admission.checkpoint.read_current()
        before_intents = self.base.store.list_intents()
        before_audit = self.fixture.audit.read_current()
        before_entries = tuple(self.base.transport.entries)
        reproduction = self.reproduce_trigger(
            anchor=anchor,
            r4_anchor=r4_anchor,
            expected_r4_anchor_sha256=expected_r4_anchor_sha256,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(
            (reproduction.status, reproduction.reasons), ("reproduced", ())
        )
        self.assertFalse(reproduction.close_authorized)
        self.assertFalse(reproduction.dispatch_authorized)
        self.assertEqual(self.base.admission.read_current(), before)
        self.assertEqual(
            self.base.admission.checkpoint.read_current(), before_checkpoint
        )
        self.assertEqual(self.base.store.list_intents(), before_intents)
        self.assertEqual(self.fixture.audit.read_current(), before_audit)
        self.assertEqual(tuple(self.base.transport.entries), before_entries)
        frozen_reproduction_sha256 = digest(canonical_bytes(reproduction))
        self.stop_and_close(closed)
        pending = self.packet(
            prepared_at=self.protocol.cutoff_at + timedelta(hours=1),
            followups=(TaskFollowupIndex(task_id="task-a", status="pending"),),
        )
        result = self.inspect_reproduced(
            pending,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
            reproduction=reproduction,
            expected_reproduction_sha256=frozen_reproduction_sha256,
        )
        self.assertEqual((result.status, result.reasons), ("pending_followup", ()))
        self.assertFalse(result.close_authorized)
        self.assertFalse(result.dispatch_authorized)
        rejected = self.inspect_reproduced(
            pending,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
            reproduction=reproduction,
            expected_reproduction_sha256=digest(b"substituted-reproduction"),
        )
        self.assertEqual(rejected.status, "blocked")
        self.assertIn("r4_trigger_reproduction_invalid", rejected.reasons)
        blocked_receipt = reproduction.model_copy(
            update={"status": "blocked", "reasons": ("synthetic_fault",)}
        )
        blocked_result = self.inspect_reproduced(
            pending,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
            reproduction=blocked_receipt,
            expected_reproduction_sha256=digest(canonical_bytes(blocked_receipt)),
        )
        self.assertIn("r4_trigger_reproduction_invalid", blocked_result.reasons)

    def test_substituted_r4_result_and_changed_sources_block_reproduction(self) -> None:
        r4_packet = self.r4.packet()
        r4_anchor = self.r4.anchor
        expected_r4_anchor_sha256 = digest(canonical_bytes(r4_anchor))
        actual = self.r4.inspect(r4_packet)
        self.assertEqual(actual.status, "healthy")
        forged = actual.model_copy(
            update={"status": "hard_stop", "stop_required": True}
        )
        closed = self.closed_release(self.now + timedelta(seconds=1))
        anchor, prior, recovery = self.freeze(
            r4_packet=r4_packet,
            r4_result=forged,
            trigger="r4_hard_stop",
            closed=closed,
        )
        substituted = self.reproduce_trigger(
            anchor=anchor,
            r4_anchor=r4_anchor,
            expected_r4_anchor_sha256=expected_r4_anchor_sha256,
            r4_packet=r4_packet,
            r4_result=forged,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(substituted.status, "blocked")
        self.assertIn("r4_result_not_reproduced", substituted.reasons)
        self.assertEqual(self.base.admission.read_current(), prior)

        wrong_root = self.reproduce_trigger(
            anchor=anchor,
            r4_anchor=r4_anchor,
            expected_r4_anchor_sha256=digest(b"different-r4-anchor"),
            r4_packet=r4_packet,
            r4_result=forged,
            prior=prior,
            recovery=recovery,
        )
        self.assertIn("r4_anchor_mismatch", wrong_root.reasons)

        valid_anchor = anchor.model_copy(
            update={"r4_result_sha256": digest(canonical_bytes(actual))}
        )
        current_route = self.fixture.route_probe.current
        self.fixture.route_probe.current = current_route.model_copy(
            update={"available": False}
        )
        changed_route = self.reproduce_trigger(
            anchor=valid_anchor,
            r4_anchor=r4_anchor,
            expected_r4_anchor_sha256=expected_r4_anchor_sha256,
            r4_packet=r4_packet,
            r4_result=actual,
            prior=prior,
            recovery=recovery,
        )
        self.assertIn("r4_result_not_reproduced", changed_route.reasons)
        self.fixture.route_probe.current = current_route
        self.fixture.assign("task-c", "session-b")
        changed_witness = self.reproduce_trigger(
            anchor=valid_anchor,
            r4_anchor=r4_anchor,
            expected_r4_anchor_sha256=expected_r4_anchor_sha256,
            r4_packet=r4_packet,
            r4_result=actual,
            prior=prior,
            recovery=recovery,
        )
        self.assertIn("preclose_source_changed", changed_witness.reasons)
        self.assertIn("r4_result_not_reproduced", changed_witness.reasons)
        cohort = self.base.admission.read_current().cohort
        assert cohort is not None
        self.assertEqual(cohort.signed_release.release.phase, "bounded_live")
        self.assertEqual(self.base.admission.read_current().attempts, ())
        self.assertEqual(self.base.transport.entries, [])

    def test_registered_cutoff_reproduction_requires_exact_cutoff(self) -> None:
        r4_packet = self.r4.packet(now=self.protocol.cutoff_at)
        r4_anchor = self.r4.anchor
        expected_r4_anchor_sha256 = digest(canonical_bytes(r4_anchor))
        r4_result = self.r4.inspect(r4_packet, now=self.protocol.cutoff_at)
        closed = self.closed_release(self.protocol.cutoff_at + timedelta(seconds=1))
        anchor, prior, recovery = self.freeze(
            r4_packet=r4_packet,
            r4_result=r4_result,
            trigger="registered_cutoff",
            closed=closed,
        )
        accepted = self.reproduce_trigger(
            anchor=anchor,
            r4_anchor=r4_anchor,
            expected_r4_anchor_sha256=expected_r4_anchor_sha256,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual((accepted.status, accepted.reasons), ("reproduced", ()))
        wrong_cutoff = anchor.model_copy(
            update={"triggered_at": self.protocol.cutoff_at + timedelta(seconds=1)}
        )
        denied = self.reproduce_trigger(
            anchor=wrong_cutoff,
            r4_anchor=r4_anchor,
            expected_r4_anchor_sha256=expected_r4_anchor_sha256,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(denied.status, "blocked")
        self.assertIn("cutoff_trigger_mismatch", denied.reasons)
        self.assertEqual(self.base.admission.read_current(), prior)
        self.assertEqual(self.base.transport.entries, [])

    def test_r4_hard_stop_closes_original_roster_and_tracks_late_followup(self) -> None:
        self.fixture.assign("task-c", "session-b")
        settled = self.fixture.execute()
        self.assertEqual(settled.status, "settled")
        r4_packet = self.r4.packet().model_copy(update={"safety_signal": "hard_stop"})
        safety_anchor = self.r4.anchor.model_copy(update={"safety_signal": "hard_stop"})
        r4_result = self.r4.inspect(r4_packet, anchor=safety_anchor)
        self.assertEqual(r4_result.status, "hard_stop")
        self.assertTrue(r4_result.stop_required)
        closed = self.closed_release(self.now + timedelta(seconds=1))
        anchor, prior, recovery = self.freeze(
            r4_packet=r4_packet,
            r4_result=r4_result,
            trigger="r4_hard_stop",
            closed=closed,
        )
        self.stop_and_close(closed)
        current = self.base.admission.read_current()
        assert prior.cohort is not None and current.cohort is not None
        self.assertEqual(current.cohort.assignments, prior.cohort.assignments)
        self.assertEqual(
            tuple(row.claim_id for row in current.attempts),
            tuple(row.claim_id for row in prior.attempts),
        )
        with self.assertRaises(ValueError):
            self.fixture.execute(
                envelope=self.base.make_envelope(
                    task_id="task-c", session_id="session-b", attempt_id="attempt-c"
                )
            )
        with self.assertRaises(ValueError):
            self.fixture.controller.advance_release(
                signed_release=self.fixture.release("bounded_live", 3),
                now=self.now + timedelta(seconds=2),
            )
        self.assertEqual(len(self.base.transport.entries), 1)

        pending = self.packet(
            prepared_at=self.protocol.cutoff_at + timedelta(hours=1),
            followups=(
                TaskFollowupIndex(task_id="task-a", status="pending"),
                TaskFollowupIndex(task_id="task-c", status="pending"),
            ),
            local_dispositions=(settled,),
        )
        provisional = self.inspect(
            pending,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(
            (provisional.status, provisional.reasons), ("pending_followup", ())
        )
        self.assertEqual(
            (
                provisional.assignment_count,
                provisional.claim_count,
                provisional.followup_unknown_count,
            ),
            (2, 1, 2),
        )
        self.assertFalse(provisional.assessment_authorized)
        self.assertFalse(provisional.dispatch_authorized)

        due = self.protocol.followup_due_at
        missing = self.packet(
            prepared_at=due + timedelta(seconds=2),
            followups=(
                TaskFollowupIndex(
                    task_id="task-a",
                    status="present",
                    evidence_sha256=digest(b"r5-synthetic-a-followup"),
                    observed_at=due + timedelta(seconds=1),
                ),
                TaskFollowupIndex(task_id="task-c", status="missing"),
            ),
            local_dispositions=(settled,),
        )
        blocked = self.inspect(
            missing,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(blocked.status, "blocked")
        self.assertIn("followup_incomplete", blocked.closeout_reasons)
        forged = missing.model_copy(
            update={
                "assignment_task_ids": ("task-a",),
                "followups": (
                    missing.followups[0],
                    TaskFollowupIndex(task_id="replacement", status="missing"),
                ),
            }
        )
        forged_result = self.inspect(
            forged,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(forged_result.status, "blocked")
        self.assertIn("roster_mismatch", forged_result.closeout_reasons)
        self.assertIn("followup_roster_mismatch", forged_result.closeout_reasons)

        late = self.packet(
            prepared_at=due + timedelta(hours=2),
            followups=(
                missing.followups[0],
                TaskFollowupIndex(
                    task_id="task-c",
                    status="present",
                    evidence_sha256=digest(b"r5-synthetic-c-late-followup"),
                    observed_at=due + timedelta(hours=1),
                ),
            ),
            local_dispositions=(settled,),
        )
        reviewable = self.inspect(
            late,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual((reviewable.status, reviewable.reasons), ("reviewable", ()))
        self.assertEqual(reviewable.followup_unknown_count, 0)
        self.assertFalse(reviewable.assessment_authorized)
        wrong_intent = late.attempt_links[0].model_copy(
            update={"intent_sha256": digest(b"substituted-intent")}
        )
        substituted = self.inspect(
            late.model_copy(update={"attempt_links": (wrong_intent,)}),
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(substituted.status, "blocked")
        self.assertIn("packet_intent_mismatch", substituted.reasons)

    def test_registered_cutoff_closes_no_dispatch_assignment(self) -> None:
        r4_packet = self.r4.packet(now=self.protocol.cutoff_at)
        r4_result = self.r4.inspect(r4_packet, now=self.protocol.cutoff_at)
        self.assertEqual(r4_result.status, "healthy")
        closed_at = self.protocol.cutoff_at + timedelta(seconds=1)
        closed = self.closed_release(closed_at)
        anchor, prior, recovery = self.freeze(
            r4_packet=r4_packet,
            r4_result=r4_result,
            trigger="registered_cutoff",
            closed=closed,
        )
        wrong_signature = self.fixture.shadow.operator_signature_base64
        invalid = closed.model_copy(
            update={"operator_signature_base64": wrong_signature}
        )
        with self.assertRaises(ValueError):
            self.fixture.controller.advance_release(
                signed_release=invalid, now=closed_at
            )
        self.assertEqual(self.base.admission.read_current(), prior)
        self.fixture.controller.advance_release(signed_release=closed, now=closed_at)
        with self.assertRaises(ValueError):
            self.fixture.assign("task-c", "session-b", now=closed_at)
        pending = self.packet(
            prepared_at=self.protocol.cutoff_at + timedelta(hours=1),
            followups=(TaskFollowupIndex(task_id="task-a", status="pending"),),
        )
        result = self.inspect(
            pending,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(result.status, "pending_followup")
        self.assertEqual((result.assignment_count, result.claim_count), (1, 0))
        self.assertEqual(self.base.transport.entries, [])
        self.fixture.audit.healthy = False
        unavailable = self.inspect(
            pending,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(unavailable.status, "blocked")
        self.assertIn("recovery_unavailable", unavailable.reasons)

    def test_post_cutoff_assignment_during_close_delay_is_blocked(self) -> None:
        r4_packet = self.r4.packet(now=self.protocol.cutoff_at)
        r4_result = self.r4.inspect(r4_packet, now=self.protocol.cutoff_at)
        self.fixture.assign(
            "task-c",
            "session-b",
            now=self.protocol.cutoff_at + timedelta(seconds=1),
        )
        closed_at = self.protocol.cutoff_at + timedelta(seconds=2)
        closed = self.closed_release(closed_at)
        anchor, prior, recovery = self.freeze(
            r4_packet=r4_packet,
            r4_result=r4_result,
            trigger="registered_cutoff",
            closed=closed,
        )
        self.fixture.controller.advance_release(signed_release=closed, now=closed_at)
        packet = self.packet(
            prepared_at=self.protocol.cutoff_at + timedelta(hours=1),
            followups=(
                TaskFollowupIndex(task_id="task-a", status="pending"),
                TaskFollowupIndex(task_id="task-c", status="pending"),
            ),
        )
        result = self.inspect(
            packet,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("preclose_snapshot_mismatch", result.reasons)
        self.assertIn("post_cutoff_assignment", result.closeout_reasons)

    def test_retained_high_water_blocks_unreconciled_closeout(self) -> None:
        settled = self.fixture.execute()
        self.fixture.recovery_anchor = capture_synthetic_cohort_recovery_anchor(
            self.base.admission, self.base.store, self.fixture.audit
        ).model_copy(update={"retained_exposure_microusd": 190})
        r4_packet = self.r4.packet()
        r4_result = self.r4.inspect(r4_packet)
        self.assertEqual(r4_result.status, "hard_stop")
        self.assertEqual(r4_result.conservative_exposure_microusd, 205)
        closed = self.closed_release(self.now + timedelta(seconds=1))
        anchor, prior, _ = self.freeze(
            r4_packet=r4_packet,
            r4_result=r4_result,
            trigger="r4_hard_stop",
            closed=closed,
        )
        recovery = self.fixture.recovery_anchor
        self.stop_and_close(closed)
        due = self.protocol.followup_due_at
        packet = self.packet(
            prepared_at=due + timedelta(seconds=2),
            followups=(
                TaskFollowupIndex(
                    task_id="task-a",
                    status="present",
                    evidence_sha256=digest(b"r5-synthetic-followup"),
                    observed_at=due + timedelta(seconds=1),
                ),
            ),
            local_dispositions=(settled,),
        )
        base_closeout = validate_offline_cohort_closeout(
            packet,
            protocol=self.protocol,
            witness=self.base.admission.read_current(),
            checkpoint=self.base.admission.checkpoint.read_current(),
            now=packet.prepared_at,
        )
        self.assertEqual(base_closeout.status, "reviewable")
        result = self.inspect(
            packet,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("retained_exposure_unreconciled", result.reasons)
        self.assertEqual(result.conservative_exposure_microusd, 205)
        self.assertFalse(result.assessment_authorized)

    def test_substituted_trigger_or_close_binding_is_blocked(self) -> None:
        r4_packet = self.r4.packet()
        r4_result = self.r4.inspect(r4_packet)
        self.assertEqual(r4_result.status, "healthy")
        closed = self.closed_release(self.now + timedelta(seconds=1))
        anchor, prior, recovery = self.freeze(
            r4_packet=r4_packet,
            r4_result=r4_result,
            trigger="r4_hard_stop",
            closed=closed,
        )
        self.fixture.controller.advance_release(
            signed_release=closed, now=self.now + timedelta(seconds=1)
        )
        packet = self.packet(
            prepared_at=self.protocol.cutoff_at + timedelta(hours=1),
            followups=(TaskFollowupIndex(task_id="task-a", status="pending"),),
        )
        result = self.inspect(
            packet,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertIn("r4_hard_stop_missing", result.reasons)
        changed = anchor.model_copy(
            update={"closed_release_sha256": digest(b"substituted-close")}
        )
        changed_result = self.inspect(
            packet,
            anchor=changed,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertIn("closed_release_invalid", changed_result.reasons)
        changed_protocol = anchor.model_copy(
            update={"closeout_protocol_sha256": digest(b"changed-protocol")}
        )
        protocol_result = self.inspect(
            packet,
            anchor=changed_protocol,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertIn("trigger_binding_mismatch", protocol_result.reasons)
        substituted = r4_result.model_copy(update={"status": "hard_stop"})
        substituted_result = self.inspect(
            packet,
            anchor=anchor,
            r4_packet=r4_packet,
            r4_result=substituted,
            prior=prior,
            recovery=recovery,
        )
        self.assertIn("trigger_binding_mismatch", substituted_result.reasons)
