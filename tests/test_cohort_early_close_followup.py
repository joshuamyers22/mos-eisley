"""G6-06 C07 inert early-close, failed task and follow-up rehearsal."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.core.models import digest
from mos_eisley.run.cohort_closeout import (
    AttemptCloseoutLink,
    CloseoutEvidenceIndex,
    CohortCloseoutPacket,
    FrozenCloseoutProtocol,
    TaskFollowupIndex,
    validate_offline_cohort_closeout,
)
from mos_eisley.run.routing_transaction import OfflineOutcome
from tests import test_cohort_controller as cohort_module


class CohortEarlyCloseFollowupTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.live()
        self.fixture.assign()
        cutoff = self.fixture.now + timedelta(seconds=2)
        self.protocol = FrozenCloseoutProtocol(
            manifest_sha256=self.fixture.manifest.manifest_sha256,
            assessment_protocol_sha256=digest(b"c07-frozen-synthetic-rubric"),
            cutoff_at=cutoff,
            followup_due_at=cutoff + timedelta(days=1),
        )

    def close(self) -> None:
        self.fixture.controller.advance_release(
            signed_release=self.fixture.release("closed", 2),
            now=self.fixture.now + timedelta(seconds=1),
        )

    def packet(
        self,
        *,
        prepared_at: datetime,
        followups: tuple[TaskFollowupIndex, ...],
        observed_local_outcomes: tuple[OfflineOutcome, ...] = (),
    ) -> CohortCloseoutPacket:
        witness = self.fixture.base.admission.read_current()
        cohort = witness.cohort
        assert cohort is not None
        intents = {
            item.attempt_key: item for item in self.fixture.base.store.list_intents()
        }
        local = {item.attempt_key: item for item in observed_local_outcomes}
        return CohortCloseoutPacket(
            manifest_sha256=self.protocol.manifest_sha256,
            assessment_protocol_sha256=self.protocol.assessment_protocol_sha256,
            release_sha256=cohort.signed_release.release.release_sha256,
            witness_epoch_id=witness.epoch_id,
            witness_generation=witness.generation,
            witness_state_sha256=witness.state_sha256,
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
                for row in witness.attempts
            ),
            followups=followups,
            evidence=CloseoutEvidenceIndex(
                route_coverage_sha256=digest(b"c07-route-coverage"),
                cap_history_sha256=digest(b"c07-cap-history"),
                all_task_latency_sha256=digest(b"c07-all-task-latency"),
                monitoring_incidents_sha256=digest(b"c07-incidents"),
                followup_custody_sha256=digest(b"c07-followup-custody"),
                protocol_deviations_sha256=digest(b"c07-deviations"),
            ),
        )

    def validate(self, packet: CohortCloseoutPacket):
        return validate_offline_cohort_closeout(
            packet,
            protocol=self.protocol,
            witness=self.fixture.base.admission.read_current(),
            checkpoint=self.fixture.base.admission.checkpoint.read_current(),
            now=packet.prepared_at,
        )

    def test_early_close_keeps_failed_task_and_blocks_replacement(self) -> None:
        def failed_task(phase: str) -> None:
            if phase == "before_admission":
                raise RuntimeError("synthetic task failed before claim")

        with self.assertRaisesRegex(RuntimeError, "synthetic task failed"):
            self.fixture.execute(fault=failed_task)
        self.close()
        with self.assertRaises(ValueError):
            self.fixture.assign("task-b", "session-a")
        with self.assertRaises(ValueError):
            self.fixture.execute()
        with self.assertRaises(ValueError):
            self.fixture.controller.advance_release(
                signed_release=self.fixture.release("bounded_live", 3),
                now=self.fixture.now + timedelta(seconds=2),
            )
        self.assertEqual(self.fixture.base.transport.entries, [])
        pending = (TaskFollowupIndex(task_id="task-a", status="pending"),)
        before_due = self.packet(
            prepared_at=self.protocol.cutoff_at + timedelta(hours=1),
            followups=pending,
        )
        provisional = self.validate(before_due)
        self.assertEqual(provisional.status, "provisional")
        self.assertEqual(
            (provisional.assignment_count, provisional.claim_count), (1, 0)
        )
        self.assertEqual(provisional.followup_unknown_count, 1)
        self.assertFalse(provisional.assessment_authority)
        mature = self.packet(
            prepared_at=self.protocol.followup_due_at + timedelta(seconds=1),
            followups=(TaskFollowupIndex(task_id="task-a", status="missing"),),
        )
        blocked = self.validate(mature)
        self.assertEqual(blocked.status, "blocked")
        self.assertIn("followup_incomplete", blocked.reasons)
        forged = mature.model_copy(
            update={
                "assignment_task_ids": ("task-b",),
                "followups": (TaskFollowupIndex(task_id="task-b", status="missing"),),
            }
        )
        self.assertIn("roster_mismatch", self.validate(forged).reasons)

    def test_cancelled_task_remains_in_original_roster(self) -> None:
        def cancelled_task(phase: str) -> None:
            if phase == "before_admission":
                raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            self.fixture.execute(fault=cancelled_task)
        self.close()
        packet = self.packet(
            prepared_at=self.protocol.followup_due_at + timedelta(seconds=1),
            followups=(TaskFollowupIndex(task_id="task-a", status="missing"),),
        )
        result = self.validate(packet)
        self.assertEqual((result.assignment_count, result.claim_count), (1, 0))
        self.assertEqual(result.followup_unknown_count, 1)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(self.fixture.base.transport.entries, [])

    def test_lost_local_outcome_write_blocks_closeout_after_one_send(self) -> None:
        with (
            patch.object(
                self.fixture.base.store,
                "finish",
                side_effect=OSError("synthetic local outcome write failed"),
            ),
            self.assertRaisesRegex(OSError, "outcome write failed"),
        ):
            self.fixture.execute()
        self.assertEqual(len(self.fixture.base.transport.entries), 1)
        self.close()
        witness = self.fixture.base.admission.read_current()
        self.assertEqual(
            (witness.attempts[0].status, witness.attempts[0].charged_microusd),
            ("settled", 15),
        )
        with self.assertRaises(ValueError):
            self.fixture.execute()
        packet = self.packet(
            prepared_at=self.protocol.followup_due_at + timedelta(seconds=1),
            followups=(
                TaskFollowupIndex(
                    task_id="task-a",
                    status="present",
                    evidence_sha256=digest(b"c07-synthetic-followup"),
                    observed_at=self.protocol.cutoff_at + timedelta(hours=1),
                ),
            ),
        )
        result = self.validate(packet)
        self.assertEqual(
            (result.assignment_count, result.claim_count, result.intent_count),
            (1, 1, 1),
        )
        self.assertEqual(result.settled_microusd, 15)
        self.assertEqual(result.status, "blocked")
        self.assertIn("settlement_link_mismatch", result.reasons)
        self.assertFalse(result.assessment_authority)
        self.assertEqual(len(self.fixture.base.transport.entries), 1)

    def test_delayed_followup_only_changes_reviewability_after_recording(self) -> None:
        settled = self.fixture.execute()
        self.assertEqual(settled.status, "settled")
        self.close()
        due = self.protocol.followup_due_at
        missing = self.packet(
            prepared_at=due + timedelta(seconds=1),
            followups=(TaskFollowupIndex(task_id="task-a", status="missing"),),
            observed_local_outcomes=(settled,),
        )
        self.assertEqual(self.validate(missing).status, "blocked")
        late = self.packet(
            prepared_at=due + timedelta(hours=2),
            followups=(
                TaskFollowupIndex(
                    task_id="task-a",
                    status="present",
                    evidence_sha256=digest(b"c07-late-synthetic-followup"),
                    observed_at=due + timedelta(hours=1),
                ),
            ),
            observed_local_outcomes=(settled,),
        )
        result = self.validate(late)
        self.assertEqual(result.status, "reviewable")
        self.assertEqual(
            (result.assignment_count, result.followup_present_count), (1, 1)
        )
        self.assertFalse(result.assessment_authority)
        self.assertFalse(result.dispatch_authority)
