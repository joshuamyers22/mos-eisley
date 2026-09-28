"""G6-06 R6 synthetic metadata-only assessment handoff rehearsal."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest import TestCase

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.cohort_assessment_handoff import (
    FrozenR6AssessmentAnchor,
    OfflineR6AssessmentPacket,
    OfflineR6AssessmentResult,
    R6DispatchIndex,
    R6EvidenceReferences,
    R6RosterIndex,
    validate_offline_r6_assessment_handoff,
    validate_reproduced_offline_r6_assessment_handoff,
)
from mos_eisley.run.cohort_close_handoff import OfflineR5CloseResult
from mos_eisley.run.cohort_closeout import CohortCloseoutPacket, TaskFollowupIndex
from tests import test_cohort_r5_close_followup as r5_module


class CohortR6AssessmentHandoffTests(TestCase):
    def setUp(self) -> None:
        self.r5 = r5_module.CohortR5CloseFollowupTests()
        self.r5.setUp()
        self.addCleanup(self.r5.doCleanups)
        self.fixture = self.r5.fixture
        self.fixture.assign("task-c", "session-b")
        settled = self.fixture.execute()
        self.assertEqual(settled.status, "settled")
        cutoff = self.r5.protocol.cutoff_at
        r4_packet = self.r5.r4.packet(now=cutoff)
        r4_result = self.r5.r4.inspect(r4_packet, now=cutoff)
        self.assertEqual(r4_result.status, "healthy")
        closed = self.r5.closed_release(cutoff)
        r5_anchor, prior, recovery = self.r5.freeze(
            r4_packet=r4_packet,
            r4_result=r4_result,
            trigger="registered_cutoff",
            closed=closed,
        )
        self.r4_packet = r4_packet
        self.r4_result = r4_result
        self.r5_anchor = r5_anchor
        self.preclose_state = prior
        self.recovery_anchor = recovery
        self.reproduction = self.r5.reproduce_trigger(
            anchor=r5_anchor,
            r4_anchor=self.r5.r4.anchor,
            expected_r4_anchor_sha256=digest(canonical_bytes(self.r5.r4.anchor)),
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
        )
        self.assertEqual(
            (self.reproduction.status, self.reproduction.reasons),
            ("reproduced", ()),
        )
        self.reproduction_sha256 = digest(canonical_bytes(self.reproduction))
        self.fixture.controller.advance_release(signed_release=closed, now=cutoff)
        due = self.r5.protocol.followup_due_at
        self.closeout = self.r5.packet(
            prepared_at=due + timedelta(seconds=1),
            followups=(
                TaskFollowupIndex(
                    task_id="task-a",
                    status="present",
                    evidence_sha256=digest(b"r6-synthetic-a-followup"),
                    observed_at=due,
                ),
                TaskFollowupIndex(
                    task_id="task-c",
                    status="present",
                    evidence_sha256=digest(b"r6-synthetic-c-followup"),
                    observed_at=due,
                ),
            ),
            local_dispositions=(settled,),
        )
        self.r5_result = self.r5.inspect_reproduced(
            self.closeout,
            anchor=r5_anchor,
            r4_packet=r4_packet,
            r4_result=r4_result,
            prior=prior,
            recovery=recovery,
            reproduction=self.reproduction,
            expected_reproduction_sha256=self.reproduction_sha256,
        )
        self.assertEqual(self.r5_result.status, "reviewable")
        self.evidence = R6EvidenceReferences(
            quality_review_sha256=digest(b"r6-synthetic-quality-reference"),
            damage_review_sha256=digest(b"r6-synthetic-damage-reference"),
            completion_review_sha256=digest(b"r6-synthetic-completion-reference"),
            all_task_latency_sha256=digest(b"r6-synthetic-latency-reference"),
            whole_task_cost_sha256=digest(b"r6-synthetic-cost-reference"),
            stop_incident_sha256=digest(b"r6-synthetic-incident-reference"),
            missingness_sha256=digest(b"r6-synthetic-missingness-reference"),
            independent_review_sha256=digest(b"r6-synthetic-review-reference"),
        )
        roster_sha256 = digest(
            canonical_bytes(R6RosterIndex(task_ids=self.closeout.assignment_task_ids))
        )
        self.dispatch_index = R6DispatchIndex(
            entered_attempt_keys=tuple(item.attempt_key for item in r4_packet.entries)
        )
        self.anchor = FrozenR6AssessmentAnchor(
            manifest_sha256=self.r5.protocol.manifest_sha256,
            closeout_protocol_sha256=digest(canonical_bytes(self.r5.protocol)),
            closeout_packet_sha256=digest(canonical_bytes(self.closeout)),
            r5_result_sha256=digest(canonical_bytes(self.r5_result)),
            r5_reproduction_sha256=self.reproduction_sha256,
            roster_sha256=roster_sha256,
            dispatch_index_sha256=digest(canonical_bytes(self.dispatch_index)),
            evidence_references_sha256=digest(canonical_bytes(self.evidence)),
            owner_signer_id="cohort-owner",
            operator_signer_id="cohort-operator",
            expected_reviewer_id="independent-r6-reviewer",
            expected_review_status="accepted",
            expected_claim_type="descriptive_only",
            expected_disposition="continue_fixed",
            incident_status="clear",
            cohort_started_at=self.r5.now,
            review_not_before=due,
            valid_until=due + timedelta(days=1),
        )
        self.packet = OfflineR6AssessmentPacket(
            manifest_sha256=self.anchor.manifest_sha256,
            closeout_protocol_sha256=self.anchor.closeout_protocol_sha256,
            closeout_packet_sha256=self.anchor.closeout_packet_sha256,
            r5_result_sha256=self.anchor.r5_result_sha256,
            r5_reproduction_sha256=self.reproduction_sha256,
            roster_sha256=roster_sha256,
            dispatch_index=self.dispatch_index,
            assignment_count=2,
            claim_count=1,
            no_dispatch_count=1,
            possible_transfer_count=0,
            followup_present_count=2,
            followup_unknown_count=0,
            settled_microusd=15,
            retained_exposure_microusd=0,
            conservative_exposure_microusd=15,
            evidence=self.evidence,
            reviewer_id="independent-r6-reviewer",
            review_status="accepted",
            incident_status="clear",
            claim_type="descriptive_only",
            proposed_disposition="continue_fixed",
            prepared_at=due + timedelta(seconds=1),
            reviewed_at=due + timedelta(seconds=2),
        )

    def validate(
        self,
        packet: OfflineR6AssessmentPacket | None = None,
        *,
        anchor: FrozenR6AssessmentAnchor | None = None,
        closeout: CohortCloseoutPacket | None = None,
        r5_result: OfflineR5CloseResult | None = None,
        now: datetime | None = None,
    ) -> OfflineR6AssessmentResult:
        current = packet or self.packet
        return validate_offline_r6_assessment_handoff(
            current,
            anchor=anchor or self.anchor,
            protocol=self.r5.protocol,
            closeout_packet=closeout or self.closeout,
            r5_result=r5_result or self.r5_result,
            now=now or current.reviewed_at,
        )

    def validate_reproduced(self, **changes: object) -> OfflineR6AssessmentResult:
        values: dict[str, object] = {
            "packet": self.packet,
            "anchor": self.anchor,
            "protocol": self.r5.protocol,
            "closeout_packet": self.closeout,
            "r5_result": self.r5_result,
            "r5_anchor": self.r5_anchor,
            "r4_packet": self.r4_packet,
            "r4_result": self.r4_result,
            "preclose_state": self.preclose_state,
            "admission": self.r5.base.admission,
            "store": self.r5.base.store,
            "audit": self.fixture.audit,
            "recovery_anchor": self.recovery_anchor,
            "reproduction": self.reproduction,
            "now": self.packet.reviewed_at,
        }
        values.update(changes)
        return validate_reproduced_offline_r6_assessment_handoff(
            **values  # type: ignore[arg-type]
        )

    def test_complete_synthetic_handoff_is_reviewable_without_authority(self) -> None:
        before = self.r5.base.admission.read_current()
        checkpoint = self.r5.base.admission.checkpoint.read_current()
        result = self.validate_reproduced()
        self.assertEqual((result.status, result.reasons), ("reviewable", ()))
        self.assertEqual(
            (
                result.assignment_count,
                result.claim_count,
                result.no_dispatch_count,
                result.possible_transfer_count,
                result.followup_unknown_count,
                result.conservative_exposure_microusd,
            ),
            (2, 1, 1, 0, 0, 15),
        )
        self.assertFalse(result.assessment_authorized)
        self.assertTrue(result.r5_reproduction_checked)
        self.assertFalse(result.comparative_claim_authorized)
        self.assertFalse(result.policy_promotion_authorized)
        self.assertFalse(result.next_cohort_authorized)
        self.assertFalse(result.dispatch_authorized)
        self.assertEqual(self.r5.base.admission.read_current(), before)
        self.assertEqual(self.r5.base.admission.checkpoint.read_current(), checkpoint)
        self.assertEqual(len(self.r5.base.transport.entries), 1)

    def test_missing_blocked_or_substituted_reproduction_blocks_r6(self) -> None:
        self.assertEqual(self.validate().status, "reviewable")
        missing = self.validate_reproduced(reproduction=None)
        self.assertEqual(missing.status, "blocked")
        self.assertIn("r5_reproduction_missing", missing.reasons)
        wrong_receipt = self.reproduction.model_copy(
            update={
                "reproduced_at": self.reproduction.reproduced_at
                + timedelta(seconds=1)
            }
        )
        substituted = self.validate_reproduced(reproduction=wrong_receipt)
        self.assertIn("r5_reproduction_binding_mismatch", substituted.reasons)
        self.assertIn("r5_reproduction_handoff_invalid", substituted.reasons)
        blocked_receipt = self.reproduction.model_copy(
            update={"status": "blocked", "reasons": ("synthetic_fault",)}
        )
        blocked_sha256 = digest(canonical_bytes(blocked_receipt))
        anchor = self.anchor.model_copy(
            update={"r5_reproduction_sha256": blocked_sha256}
        )
        packet = self.packet.model_copy(
            update={"r5_reproduction_sha256": blocked_sha256}
        )
        blocked = self.validate_reproduced(
            anchor=anchor, packet=packet, reproduction=blocked_receipt
        )
        self.assertEqual(blocked.status, "blocked")
        self.assertIn("r5_reproduction_handoff_invalid", blocked.reasons)
        no_digest = self.validate_reproduced(
            packet=self.packet.model_copy(update={"r5_reproduction_sha256": None})
        )
        self.assertIn("r5_reproduction_missing", no_digest.reasons)

    def test_early_or_incomplete_handoff_is_blocked(self) -> None:
        early_time = self.r5.protocol.followup_due_at - timedelta(seconds=1)
        early = self.packet.model_copy(
            update={"prepared_at": early_time, "reviewed_at": early_time}
        )
        self.assertIn(
            "review_time_invalid", self.validate(early, now=early_time).reasons
        )

        pending_closeout = self.closeout.model_copy(
            update={
                "prepared_at": self.r5.protocol.cutoff_at + timedelta(hours=1),
                "followups": (
                    self.closeout.followups[0],
                    TaskFollowupIndex(task_id="task-c", status="pending"),
                ),
            }
        )
        pending_r5 = self.r5_result.model_copy(
            update={"status": "pending_followup", "followup_unknown_count": 1}
        )
        pending_anchor = self.anchor.model_copy(
            update={
                "closeout_packet_sha256": digest(canonical_bytes(pending_closeout)),
                "r5_result_sha256": digest(canonical_bytes(pending_r5)),
            }
        )
        pending_packet = self.packet.model_copy(
            update={
                "closeout_packet_sha256": pending_anchor.closeout_packet_sha256,
                "r5_result_sha256": pending_anchor.r5_result_sha256,
            }
        )
        pending_result = self.validate(
            pending_packet,
            anchor=pending_anchor,
            closeout=pending_closeout,
            r5_result=pending_r5,
        )
        self.assertEqual(pending_result.status, "blocked")
        self.assertIn("r5_handoff_not_mature", pending_result.reasons)
        self.assertIn("denominator_mismatch", pending_result.reasons)

    def test_favorable_subset_and_understated_cost_are_blocked(self) -> None:
        subset = self.packet.model_copy(
            update={
                "assignment_count": 1,
                "no_dispatch_count": 0,
                "followup_present_count": 1,
                "roster_sha256": digest(
                    canonical_bytes(R6RosterIndex(task_ids=("task-a",)))
                ),
            }
        )
        result = self.validate(subset)
        self.assertEqual(result.status, "blocked")
        self.assertIn("denominator_mismatch", result.reasons)
        self.assertIn("source_binding_mismatch", result.reasons)
        understated = self.packet.model_copy(
            update={"conservative_exposure_microusd": 1}
        )
        self.assertIn("cost_exposure_mismatch", self.validate(understated).reasons)

    def test_claim_is_not_inferred_to_be_a_transport_entry(self) -> None:
        missing_entry = R6DispatchIndex(entered_attempt_keys=())
        packet = self.packet.model_copy(update={"dispatch_index": missing_entry})
        anchor = self.anchor.model_copy(
            update={"dispatch_index_sha256": digest(canonical_bytes(missing_entry))}
        )
        result = self.validate(packet, anchor=anchor)
        self.assertEqual(result.status, "blocked")
        self.assertIn("denominator_mismatch", result.reasons)
        self.assertEqual(result.possible_transfer_count, 1)
        self.assertEqual(result.no_dispatch_count, 1)

    def test_review_evidence_and_incident_status_cannot_be_substituted(self) -> None:
        changed_evidence = self.evidence.model_copy(
            update={"quality_review_sha256": digest(b"changed-quality-reference")}
        )
        changed = self.packet.model_copy(update={"evidence": changed_evidence})
        self.assertIn("independent_review_invalid", self.validate(changed).reasons)
        self.assertIn(
            "independent_review_invalid",
            self.validate(
                self.packet.model_copy(update={"reviewer_id": "cohort-owner"})
            ).reasons,
        )
        self.assertIn(
            "independent_review_invalid",
            self.validate(
                self.packet.model_copy(update={"review_status": "unavailable"})
            ).reasons,
        )
        severe = self.packet.model_copy(update={"incident_status": "severe"})
        result = self.validate(severe)
        self.assertIn("incident_status_mismatch", result.reasons)
        self.assertIn("incident_disposition_invalid", result.reasons)
        severe_anchor = self.anchor.model_copy(
            update={"incident_status": "severe", "expected_disposition": "no_go"}
        )
        no_go = severe.model_copy(update={"proposed_disposition": "no_go"})
        reviewable = self.validate(no_go, anchor=severe_anchor)
        self.assertEqual(reviewable.status, "reviewable")
        self.assertFalse(reviewable.assessment_authorized)

    def test_comparison_requires_explicit_registration_and_grants_no_claim(
        self,
    ) -> None:
        baseline = digest(b"r6-synthetic-baseline-registration")
        design = digest(b"r6-synthetic-comparison-design")
        proposed = self.packet.model_copy(
            update={
                "claim_type": "registered_comparison",
                "baseline_registration_sha256": baseline,
                "comparison_design_sha256": design,
                "proposed_disposition": "propose_next_cohort",
            }
        )
        self.assertIn("comparison_unregistered", self.validate(proposed).reasons)
        registered = self.anchor.model_copy(
            update={
                "baseline_registration_sha256": baseline,
                "comparison_design_sha256": design,
                "comparison_registered_at": self.r5.now - timedelta(seconds=1),
                "expected_claim_type": "registered_comparison",
                "expected_disposition": "propose_next_cohort",
            }
        )
        result = self.validate(proposed, anchor=registered)
        self.assertEqual(result.status, "reviewable")
        self.assertFalse(result.comparative_claim_authorized)
        self.assertFalse(result.next_cohort_authorized)
        late_registration = registered.model_copy(
            update={"comparison_registered_at": self.r5.now + timedelta(seconds=1)}
        )
        self.assertIn(
            "comparison_unregistered",
            self.validate(proposed, anchor=late_registration).reasons,
        )

    def test_changed_r5_or_protocol_binding_is_blocked(self) -> None:
        changed = self.packet.model_copy(
            update={"r5_result_sha256": digest(b"other-r5-result")}
        )
        self.assertIn("source_binding_mismatch", self.validate(changed).reasons)
        changed_protocol = self.anchor.model_copy(
            update={"closeout_protocol_sha256": digest(b"changed-protocol")}
        )
        self.assertIn(
            "source_binding_mismatch", self.validate(anchor=changed_protocol).reasons
        )
        changed_decision = self.packet.model_copy(
            update={"proposed_disposition": "propose_next_cohort"}
        )
        self.assertIn(
            "decision_binding_mismatch", self.validate(changed_decision).reasons
        )
        rejected_anchor = self.anchor.model_copy(
            update={"expected_review_status": "rejected"}
        )
        self.assertIn(
            "independent_review_invalid", self.validate(anchor=rejected_anchor).reasons
        )
