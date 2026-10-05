"""G6-06 C09 metadata-only policy, rubric and assessment freeze rehearsal."""

from __future__ import annotations

from datetime import timedelta
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.core.models import digest
from mos_eisley.run.cohort_closeout import (
    CloseoutValidation,
    TaskFollowupIndex,
    validate_offline_cohort_closeout,
)
from tests import test_cohort_early_close_followup as c07_module


class CohortAssessmentFreezeTests(TestCase):
    def setUp(self) -> None:
        self.rehearsal = c07_module.CohortEarlyCloseFollowupTests()
        self.rehearsal.setUp()
        self.addCleanup(self.rehearsal.doCleanups)
        self.fixture = self.rehearsal.fixture

    def present_followup(self, task_id: str = "task-a") -> TaskFollowupIndex:
        return TaskFollowupIndex(
            task_id=task_id,
            status="present",
            evidence_sha256=digest(f"c09-synthetic-followup:{task_id}".encode()),
            observed_at=self.rehearsal.protocol.cutoff_at + timedelta(minutes=1),
        )

    def test_policy_retune_cannot_change_assigned_cohort(self) -> None:
        witness_before = self.fixture.base.admission.read_current()
        cohort_before = witness_before.cohort
        assert cohort_before is not None
        changed_policy = digest(b"c09-proposed-policy-after-interim-signal")
        with self.assertRaises(ValueError):
            self.fixture.assign(
                "task-b", "session-a", candidate_policy_sha256=changed_policy
            )
        changed_manifest = self.fixture.manifest.model_copy(
            update={"candidate_policy_sha256": changed_policy}
        )
        with self.assertRaises(ValueError):
            self.fixture.controller.advance_release(
                signed_release=self.fixture.release(
                    "bounded_live", 2, changed_manifest
                ),
                now=self.fixture.now + timedelta(seconds=1),
            )
        witness_after = self.fixture.base.admission.read_current()
        cohort_after = witness_after.cohort
        assert cohort_after is not None
        self.assertEqual(cohort_after.manifest, cohort_before.manifest)
        self.assertEqual(cohort_after.signed_release, cohort_before.signed_release)
        self.assertEqual(cohort_after.assignments, cohort_before.assignments)
        self.assertEqual(witness_after.attempts, ())
        self.assertEqual(self.fixture.base.transport.entries, [])

    def test_changed_rubric_cannot_rebind_registered_packet(self) -> None:
        self.rehearsal.close()
        packet = self.rehearsal.packet(
            prepared_at=self.rehearsal.protocol.followup_due_at + timedelta(seconds=1),
            followups=(self.present_followup(),),
        )
        original = self.rehearsal.validate(packet)
        self.assertEqual(original.status, "reviewable")
        self.assertFalse(original.assessment_authority)
        changed_rubric = digest(b"c09-revised-rubric-after-interim-signal")
        changed_packet = packet.model_copy(
            update={"assessment_protocol_sha256": changed_rubric}
        )
        self.assertIn(
            "protocol_binding_mismatch",
            self.rehearsal.validate(changed_packet).reasons,
        )
        changed_protocol = self.rehearsal.protocol.model_copy(
            update={"assessment_protocol_sha256": changed_rubric}
        )
        result = validate_offline_cohort_closeout(
            packet,
            protocol=changed_protocol,
            witness=self.fixture.base.admission.read_current(),
            checkpoint=self.fixture.base.admission.checkpoint.read_current(),
            now=packet.prepared_at,
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("protocol_binding_mismatch", result.reasons)

    def test_early_signal_cannot_mature_or_authorize_assessment(self) -> None:
        self.rehearsal.close()
        early = self.rehearsal.packet(
            prepared_at=self.rehearsal.protocol.cutoff_at + timedelta(hours=1),
            followups=(self.present_followup(),),
        )
        provisional = self.rehearsal.validate(early)
        self.assertEqual(provisional.status, "provisional")
        self.assertIn("followup_window_open", provisional.reasons)
        self.assertFalse(provisional.assessment_authority)
        future_dated = early.model_copy(
            update={
                "prepared_at": self.rehearsal.protocol.followup_due_at
                + timedelta(seconds=1)
            }
        )
        result = validate_offline_cohort_closeout(
            future_dated,
            protocol=self.rehearsal.protocol,
            witness=self.fixture.base.admission.read_current(),
            checkpoint=self.fixture.base.admission.checkpoint.read_current(),
            now=early.prepared_at,
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("packet_time_invalid", result.reasons)
        self.assertIn("followup_window_open", result.reasons)
        with self.assertRaises(ValidationError):
            CloseoutValidation.model_validate(
                provisional.model_dump() | {"assessment_authority": True}
            )

    def test_favorable_subset_cannot_replace_intent_to_treat_roster(self) -> None:
        self.fixture.assign("task-c", "session-b")
        settled = self.fixture.execute()
        self.assertEqual(settled.status, "settled")
        self.rehearsal.close()
        packet = self.rehearsal.packet(
            prepared_at=self.rehearsal.protocol.followup_due_at + timedelta(seconds=1),
            followups=(
                self.present_followup("task-a"),
                self.present_followup("task-c"),
            ),
            observed_local_outcomes=(settled,),
        )
        complete = self.rehearsal.validate(packet)
        self.assertEqual(complete.status, "reviewable")
        self.assertEqual((complete.assignment_count, complete.claim_count), (2, 1))
        self.assertFalse(complete.assessment_authority)
        subset = packet.model_copy(
            update={
                "assignment_task_ids": ("task-a",),
                "followups": (self.present_followup("task-a"),),
            }
        )
        denied = self.rehearsal.validate(subset)
        self.assertEqual(denied.status, "blocked")
        self.assertIn("roster_mismatch", denied.reasons)
        self.assertIn("followup_roster_mismatch", denied.reasons)
        self.assertEqual((denied.assignment_count, denied.claim_count), (2, 1))
        self.assertFalse(denied.assessment_authority)
