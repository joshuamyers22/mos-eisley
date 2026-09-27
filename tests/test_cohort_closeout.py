"""Synthetic metadata-only G6-06 closeout and assessment packet tests."""

from __future__ import annotations

from datetime import timedelta
from unittest import TestCase

from mos_eisley.core.models import digest
from mos_eisley.run.cohort_closeout import (
    AttemptCloseoutLink,
    CloseoutEvidenceIndex,
    CohortCloseoutPacket,
    FrozenCloseoutProtocol,
    TaskFollowupIndex,
    validate_offline_cohort_closeout,
)
from tests import test_cohort_controller as cohort_module


class CohortCloseoutTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.now = self.fixture.now

    def close(self) -> None:
        self.fixture.controller.advance_release(
            signed_release=self.fixture.release("closed", 2),
            now=self.now + timedelta(seconds=1),
        )

    def packet(self) -> tuple[FrozenCloseoutProtocol, CohortCloseoutPacket]:
        witness = self.fixture.base.admission.read_current()
        cohort = witness.cohort
        assert cohort is not None
        cutoff = self.now + timedelta(seconds=2)
        protocol = FrozenCloseoutProtocol(
            manifest_sha256=self.fixture.manifest.manifest_sha256,
            assessment_protocol_sha256=digest(b"frozen-synthetic-rubric"),
            cutoff_at=cutoff,
            followup_due_at=cutoff + timedelta(days=1),
        )
        links = tuple(
            AttemptCloseoutLink(
                attempt_key=row.attempt.attempt_key,
                claim_id=row.claim_id,
                task_id=row.attempt.task_id,
                intent_sha256=(
                    digest(b"synthetic-intent:" + row.claim_id.encode())
                    if row.status != "held"
                    else None
                ),
                local_status=row.status if row.status != "held" else None,
                local_charged_microusd=(
                    row.charged_microusd if row.status != "held" else None
                ),
            )
            for row in witness.attempts
        )
        followups = tuple(
            TaskFollowupIndex(
                task_id=item.task_id,
                status="present",
                evidence_sha256=digest(f"synthetic-followup:{item.task_id}".encode()),
                observed_at=cutoff + timedelta(hours=1),
            )
            for item in cohort.assignments
        )
        evidence = CloseoutEvidenceIndex(
            route_coverage_sha256=digest(b"synthetic-route-coverage"),
            cap_history_sha256=digest(b"synthetic-cap-history"),
            all_task_latency_sha256=digest(b"synthetic-all-task-latency"),
            monitoring_incidents_sha256=digest(b"synthetic-incidents"),
            followup_custody_sha256=digest(b"synthetic-followup-custody"),
            protocol_deviations_sha256=digest(b"synthetic-deviations"),
        )
        packet = CohortCloseoutPacket(
            manifest_sha256=protocol.manifest_sha256,
            assessment_protocol_sha256=protocol.assessment_protocol_sha256,
            release_sha256=cohort.signed_release.release.release_sha256,
            witness_epoch_id=witness.epoch_id,
            witness_generation=witness.generation,
            witness_state_sha256=witness.state_sha256,
            prepared_at=protocol.followup_due_at + timedelta(seconds=1),
            assignment_task_ids=tuple(item.task_id for item in cohort.assignments),
            attempt_links=links,
            followups=followups,
            evidence=evidence,
        )
        return protocol, packet

    def validate(self, protocol: FrozenCloseoutProtocol, packet: CohortCloseoutPacket):
        return validate_offline_cohort_closeout(
            packet,
            protocol=protocol,
            witness=self.fixture.base.admission.read_current(),
            checkpoint=self.fixture.base.admission.checkpoint.read_current(),
            now=packet.prepared_at,
        )

    def test_complete_synthetic_packet_is_only_reviewable(self) -> None:
        self.fixture.live()
        self.fixture.assign()
        self.assertEqual(self.fixture.base.execute().status, "settled")
        self.close()
        protocol, packet = self.packet()
        result = self.validate(protocol, packet)
        self.assertEqual((result.status, result.reasons), ("reviewable", ()))
        self.assertEqual((result.assignment_count, result.claim_count), (1, 1))
        self.assertEqual(
            (result.settled_microusd, result.retained_exposure_microusd), (15, 0)
        )
        self.assertFalse(result.assessment_authority)
        self.assertFalse(result.dispatch_authority)

    def test_no_dispatch_assignment_stays_in_denominator(self) -> None:
        self.fixture.live()
        self.fixture.assign()
        self.close()
        protocol, packet = self.packet()
        result = self.validate(protocol, packet)
        self.assertEqual((result.assignment_count, result.claim_count), (1, 0))
        self.assertEqual(result.status, "reviewable")
        omitted = packet.model_copy(update={"assignment_task_ids": ()})
        self.assertIn("roster_mismatch", self.validate(protocol, omitted).reasons)

    def test_missing_followup_remains_unknown_and_blocks_mature_packet(self) -> None:
        self.fixture.live()
        self.fixture.assign()
        self.close()
        protocol, packet = self.packet()
        missing = packet.model_copy(
            update={
                "followups": (TaskFollowupIndex(task_id="task-a", status="missing"),)
            }
        )
        result = self.validate(protocol, missing)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.followup_unknown_count, 1)
        self.assertIn("followup_incomplete", result.reasons)
        early = missing.model_copy(
            update={"prepared_at": protocol.cutoff_at + timedelta(hours=1)}
        )
        self.assertEqual(self.validate(protocol, early).status, "provisional")

    def test_duplicate_or_replacement_followup_is_blocked(self) -> None:
        self.fixture.live()
        self.fixture.assign()
        self.close()
        protocol, packet = self.packet()
        for followups in (
            (),
            packet.followups + packet.followups,
            (TaskFollowupIndex(task_id="replacement", status="missing"),),
        ):
            with self.subTest(followups=followups):
                result = self.validate(
                    protocol, packet.model_copy(update={"followups": followups})
                )
                self.assertEqual(result.status, "blocked")
                self.assertIn("followup_roster_mismatch", result.reasons)

    def test_assignment_after_frozen_cutoff_is_blocked(self) -> None:
        self.fixture.live()
        self.fixture.assign(now=self.now + timedelta(seconds=3))
        self.fixture.controller.advance_release(
            signed_release=self.fixture.release("closed", 2),
            now=self.now + timedelta(seconds=4),
        )
        protocol, packet = self.packet()
        result = self.validate(protocol, packet)
        self.assertEqual(result.status, "blocked")
        self.assertIn("post_cutoff_assignment", result.reasons)

    def test_claim_and_settlement_links_cannot_be_omitted_or_rewritten(self) -> None:
        self.fixture.live()
        self.fixture.assign()
        self.fixture.base.execute()
        self.close()
        protocol, packet = self.packet()
        omitted = packet.model_copy(update={"attempt_links": ()})
        self.assertIn(
            "attempt_index_mismatch", self.validate(protocol, omitted).reasons
        )
        duplicate = packet.model_copy(
            update={"attempt_links": packet.attempt_links + packet.attempt_links}
        )
        self.assertIn(
            "attempt_index_mismatch", self.validate(protocol, duplicate).reasons
        )
        link = packet.attempt_links[0]
        changed = packet.model_copy(
            update={
                "attempt_links": (
                    link.model_copy(update={"claim_id": digest(b"wrong-claim")}),
                )
            }
        )
        self.assertIn("claim_link_mismatch", self.validate(protocol, changed).reasons)
        unlinked = packet.model_copy(
            update={"attempt_links": (link.model_copy(update={"intent_sha256": None}),)}
        )
        self.assertIn(
            "settlement_link_mismatch", self.validate(protocol, unlinked).reasons
        )
        mischarged = packet.model_copy(
            update={
                "attempt_links": (
                    link.model_copy(update={"local_charged_microusd": 1}),
                )
            }
        )
        self.assertIn("charge_mismatch", self.validate(protocol, mischarged).reasons)

    def test_held_claim_keeps_full_exposure(self) -> None:
        self.fixture.live()
        self.fixture.assign()
        self.fixture.claim()
        self.close()
        protocol, packet = self.packet()
        result = self.validate(protocol, packet)
        self.assertEqual(result.status, "reviewable")
        self.assertEqual(result.retained_exposure_microusd, 100)
        self.assertEqual(result.intent_count, 0)

    def test_registration_release_and_checkpoint_mismatches_block(self) -> None:
        self.fixture.live()
        self.fixture.assign()
        self.close()
        protocol, packet = self.packet()
        changed_protocol = protocol.model_copy(
            update={"assessment_protocol_sha256": digest(b"changed-rubric")}
        )
        self.assertIn(
            "protocol_binding_mismatch",
            self.validate(changed_protocol, packet).reasons,
        )
        changed_release = packet.model_copy(
            update={"release_sha256": digest(b"stale-release")}
        )
        self.assertIn(
            "cohort_binding_mismatch", self.validate(protocol, changed_release).reasons
        )
        checkpoint = self.fixture.base.admission.checkpoint.read_current().model_copy(
            update={"generation": 0}
        )
        result = validate_offline_cohort_closeout(
            packet,
            protocol=protocol,
            witness=self.fixture.base.admission.read_current(),
            checkpoint=checkpoint,
            now=packet.prepared_at,
        )
        self.assertIn("checkpoint_mismatch", result.reasons)

    def test_open_cohort_and_missing_evidence_cannot_be_reviewable(self) -> None:
        self.fixture.live()
        self.fixture.assign()
        protocol, packet = self.packet()
        partial = packet.model_copy(update={"evidence": CloseoutEvidenceIndex()})
        result = self.validate(protocol, partial)
        self.assertEqual(result.status, "blocked")
        self.assertIn("cohort_not_closed", result.reasons)
        self.assertIn("evidence_index_incomplete", result.reasons)
