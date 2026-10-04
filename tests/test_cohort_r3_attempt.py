"""G6-06 R3 offline per-attempt handoff and fault rehearsal."""

from __future__ import annotations

from datetime import timedelta
from unittest import TestCase

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.routing_transaction import (
    inspect_offline_cohort_audit,
    inspect_offline_cohort_recovery,
)
from tests import test_cohort_r2_entry as r2_module


class CohortR3AttemptTests(TestCase):
    def setUp(self) -> None:
        self.r2 = r2_module.CohortR2EntryTests()
        self.r2.setUp()
        self.addCleanup(self.r2.doCleanups)
        self.fixture = self.r2.fixture
        self.base = self.fixture.base
        entry = self.r2.validate_end_to_end()
        self.assertEqual((entry.status, entry.reasons), ("reviewable", ()))
        self.assertTrue(entry.signed_owner_decision_checked)
        self.assertTrue(entry.readiness_checked)
        self.assertFalse(entry.owner_release_authorized)
        self.assertFalse(entry.dispatch_authorized)
        self.assertEqual(self.base.admission.read_current().attempts, ())
        self.assertEqual(self.base.transport.entries, [])

    def enter_live(self, **changes: object) -> None:
        entry = self.r2.validate_end_to_end(**changes)
        if entry.status != "reviewable":
            raise ValueError(
                "R2-to-R3 offline handoff blocked: " + ", ".join(entry.reasons)
            )
        self.fixture.controller.advance_release(
            signed_release=self.r2.proposed, now=self.fixture.now
        )
        cohort = self.base.admission.read_current().cohort
        assert cohort is not None
        self.assertEqual(cohort.signed_release, self.r2.proposed)
        self.assertEqual(cohort.assignments, ())
        self.assertEqual(self.base.admission.read_current().attempts, ())
        self.assertEqual(self.base.transport.entries, [])

    def inventory(self):
        return inspect_offline_cohort_audit(
            self.base.admission, self.base.store, self.fixture.audit
        )

    def assert_no_claim_or_send(self) -> None:
        self.assertEqual(self.base.admission.read_current().attempts, ())
        self.assertEqual(self.base.store.list_intents(), ())
        self.assertEqual(self.fixture.audit.read_current(), ())
        self.assertEqual(self.base.transport.entries, [])

    def test_reviewable_entry_cannot_promote_shadow_or_assign(self) -> None:
        with self.assertRaises(ValueError):
            self.fixture.assign(release=self.r2.proposed)
        with self.assertRaises(ValueError):
            self.fixture.execute()
        cohort = self.base.admission.read_current().cohort
        assert cohort is not None
        self.assertEqual(cohort.signed_release, self.fixture.shadow)
        self.assertEqual(cohort.assignments, ())
        self.assert_no_claim_or_send()

    def test_r2_to_r3_handoff_rechecks_readiness_before_release(self) -> None:
        self.assertEqual(self.r2.validate().status, "reviewable")
        q = self.r2.qualification
        cases: tuple[tuple[str, dict[str, object]], ...] = (
            (
                "expired_readiness",
                {
                    "readiness": self.r2.readiness.model_copy(
                        update={"valid_until": self.fixture.now}
                    )
                },
            ),
            (
                "rejected_inspection",
                {
                    "readiness": self.r2.readiness.model_copy(
                        update={
                            "source_inspections": (
                                self.r2.readiness.source_inspections[0].model_copy(
                                    update={"status": "reject"}
                                ),
                                *self.r2.readiness.source_inspections[1:],
                            )
                        }
                    )
                },
            ),
            ("rejected_q7", {"reviews": q.reviews(decision="reject")}),
            (
                "changed_source_handoff",
                {
                    "source_handoff": self.r2.source_handoff.model_copy(
                        update={
                            "references": (
                                self.r2.source_handoff.references[0].model_copy(
                                    update={"status": "unavailable"}
                                ),
                                *self.r2.source_handoff.references[1:],
                            )
                        }
                    )
                },
            ),
            (
                "changed_frozen_root",
                {"expected_review_trust_sha256": digest(b"changed-q7-root")},
            ),
            (
                "changed_cohort_roster",
                {
                    "qualification_packet": q.packet.model_copy(
                        update={
                            "scope": q.packet.scope.model_copy(
                                update={
                                    "task_enrollment_sha256": digest(
                                        b"different-roster"
                                    )
                                }
                            )
                        }
                    )
                },
            ),
            ("owner_decision_missing", {"owner_decision": None}),
        )
        before = self.base.admission.read_current()
        checkpoint = self.base.admission.checkpoint.read_current()
        for name, changes in cases:
            with self.subTest(name=name):
                self.assertEqual(self.r2.validate().status, "reviewable")
                denied = self.r2.validate_end_to_end(**changes)
                self.assertEqual(denied.status, "blocked")
                self.assertTrue(denied.readiness_checked)
                with self.assertRaisesRegex(ValueError, "handoff blocked"):
                    self.enter_live(**changes)
                self.assertEqual(self.base.admission.read_current(), before)
                self.assertEqual(
                    self.base.admission.checkpoint.read_current(), checkpoint
                )
                with self.assertRaises(ValueError):
                    self.fixture.assign(release=self.r2.proposed)
                self.assert_no_claim_or_send()

    def test_explicit_release_and_assignment_precede_one_inert_attempt(self) -> None:
        self.enter_live()
        assignment = self.fixture.assign()
        self.assertEqual(
            assignment.release_sha256, self.r2.proposed.release.release_sha256
        )
        self.assert_no_claim_or_send()

        outcome = self.fixture.execute()
        self.assertEqual((outcome.status, outcome.charged_microusd), ("settled", 15))
        state = self.base.admission.read_current()
        checkpoint = self.base.admission.checkpoint.read_current()
        self.assertEqual(checkpoint.state_sha256, state.state_sha256)
        self.assertEqual(len(state.attempts), 1)
        attempt = state.attempts[0]
        self.assertEqual(attempt.status, "settled")
        self.assertEqual(attempt.attempt.attempt_key, outcome.attempt_key)
        self.assertEqual(attempt.attempt.candidate_id, self.base.selection.candidate_id)
        intents = self.base.store.list_intents()
        audit = self.fixture.audit.read_current()
        self.assertEqual((len(intents), len(audit)), (1, 1))
        self.assertEqual(intents[0].claim_id, attempt.claim_id)
        self.assertEqual(audit[0].intent_sha256, intents[0].intent_sha256)
        self.assertEqual(audit[0].claim_id, attempt.claim_id)
        self.assertEqual(
            self.base.transport.entries,
            [digest(canonical_bytes(self.base.request))],
        )
        self.assertTrue(self.inventory().complete)
        recovery = inspect_offline_cohort_recovery(
            self.base.admission,
            self.base.store,
            self.fixture.audit,
            anchor=self.fixture.recovery_anchor,
        )
        self.assertEqual(recovery.status, "consistent")
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.base.transport.entries), 1)

    def test_unassigned_or_stale_evidence_denies_before_claim(self) -> None:
        self.enter_live()
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assert_no_claim_or_send()
        self.fixture.assign()

        expired = self.base.preflight.model_copy(
            update={"valid_until": self.fixture.now}
        )
        with self.assertRaises(ValueError):
            self.fixture.execute(preflight=expired)
        self.assert_no_claim_or_send()

        changed_selection = self.base.selection.model_copy(
            update={"candidate_policy_sha256": digest(b"changed-policy")}
        )
        with self.assertRaises(ValueError):
            self.fixture.execute(selection=changed_selection)
        self.assert_no_claim_or_send()

        current = self.fixture.route_probe.current
        self.fixture.route_probe.current = current.model_copy(
            update={"available": False}
        )
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.fixture.route_probe.current = current
        self.assert_no_claim_or_send()

        self.fixture.alerts.delivery_acknowledged = False
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.fixture.alerts.delivery_acknowledged = True
        self.assert_no_claim_or_send()

        self.base.monitor.healthy = False
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.base.monitor.healthy = True
        self.assert_no_claim_or_send()

    def test_cut_after_claim_retains_full_exposure_without_intent_or_send(self) -> None:
        self.enter_live()
        self.fixture.assign()

        def cut(phase: str) -> None:
            if phase == "after_admission":
                raise RuntimeError("synthetic cut after claim")

        with self.assertRaisesRegex(RuntimeError, "after claim"):
            self.fixture.execute(fault=cut)
        state = self.base.admission.read_current()
        self.assertEqual(len(state.attempts), 1)
        self.assertEqual(
            (state.attempts[0].status, state.attempts[0].charged_microusd),
            ("held", 100),
        )
        self.assertEqual(self.base.store.list_intents(), ())
        self.assertEqual(self.fixture.audit.read_current(), ())
        self.assertEqual(self.base.transport.entries, [])
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.base.admission.read_current().attempts), 1)

    def test_cut_after_intent_exposes_missing_audit_and_denies_next_attempt(
        self,
    ) -> None:
        self.enter_live()
        self.fixture.assign()

        def cut(phase: str) -> None:
            if phase == "after_intent":
                raise RuntimeError("synthetic cut after intent")

        with self.assertRaisesRegex(RuntimeError, "after intent"):
            self.fixture.execute(fault=cut)
        self.assertEqual(len(self.base.admission.read_current().attempts), 1)
        self.assertEqual(len(self.base.store.list_intents()), 1)
        self.assertEqual(self.fixture.audit.read_current(), ())
        self.assertEqual(self.base.transport.entries, [])
        self.assertFalse(self.inventory().complete)
        self.fixture.assign("task-c", "session-b")
        with self.assertRaises(ValueError):
            self.fixture.execute(
                envelope=self.base.make_envelope(
                    task_id="task-c", session_id="session-b", attempt_id="attempt-c"
                )
            )
        self.assertEqual(len(self.base.admission.read_current().attempts), 1)

    def test_stop_after_audit_abandons_full_exposure_without_send(self) -> None:
        self.enter_live()
        self.fixture.assign()

        def stop(phase: str) -> None:
            if phase == "after_audit":
                stopped = self.base.stop_entry()
                self.base.admission.advance_control(
                    stopped, self.fixture.now + timedelta(seconds=1)
                )

        outcome = self.fixture.execute(fault=stop)
        self.assertEqual((outcome.status, outcome.charged_microusd), ("abandoned", 100))
        self.assertTrue(self.inventory().complete)
        self.assertEqual(self.base.transport.entries, [])
        self.assertEqual(self.base.admission.read_current().attempts[0].status, "held")
        with self.assertRaises(ValueError):
            self.fixture.execute()

    def test_route_change_after_final_read_bounds_one_inert_entry(self) -> None:
        self.enter_live()
        self.fixture.assign()

        def lose_route(phase: str) -> None:
            if phase == "after_final_check":
                current = self.fixture.route_probe.current
                self.fixture.route_probe.current = current.model_copy(
                    update={"available": False}
                )

        outcome = self.fixture.execute(fault=lose_route)
        self.assertEqual(outcome.status, "settled")
        self.assertEqual(len(self.base.transport.entries), 1)
        self.assertTrue(self.inventory().complete)
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.base.transport.entries), 1)

    def test_transport_uncertainty_retains_full_exposure_and_no_retry(self) -> None:
        self.enter_live()
        self.fixture.assign()
        self.base.transport.error = TimeoutError("synthetic transport timeout")
        outcome = self.fixture.execute()
        self.assertEqual((outcome.status, outcome.charged_microusd), ("uncertain", 100))
        self.assertEqual(len(self.base.transport.entries), 1)
        self.assertEqual(
            (
                self.base.admission.read_current().attempts[0].status,
                self.base.admission.read_current().attempts[0].charged_microusd,
            ),
            ("uncertain", 100),
        )
        self.assertTrue(self.inventory().complete)
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.base.transport.entries), 1)
        self.fixture.assign("task-c", "session-b")
        with self.assertRaisesRegex(ValueError, "no active slot"):
            self.fixture.execute(
                envelope=self.base.make_envelope(
                    task_id="task-c", session_id="session-b", attempt_id="attempt-c"
                )
            )
        self.assertEqual(len(self.base.admission.read_current().attempts), 1)
        self.assertEqual(len(self.base.transport.entries), 1)
