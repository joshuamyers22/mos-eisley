"""G6-06 R0 inert cohort path, stop and frozen fallback integration checks."""

from __future__ import annotations

from datetime import timedelta
from unittest import TestCase

from mos_eisley.run.exact_route import ExactRouteSelection
from mos_eisley.run.routing_transaction import (
    SyntheticExactRouteProbe,
    SyntheticRouteObservation,
    inspect_offline_cohort_audit,
    inspect_offline_cohort_recovery,
)
from tests import test_cohort_controller as cohort_module
from tests import test_exact_route as exact_module


class CohortR0IntegratedTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.live()
        self.fixture.assign("task-a", "session-a")

    def test_one_inert_task_joins_assignment_claim_intent_audit_and_recovery(
        self,
    ) -> None:
        base = self.fixture.base
        self.assertEqual(base.selection.source, "calibrated_route")
        self.assertEqual(
            base.selection.candidate_policy_sha256,
            self.fixture.manifest.candidate_policy_sha256,
        )
        outcome = self.fixture.execute()
        self.assertEqual((outcome.status, outcome.charged_microusd), ("settled", 15))
        witness = base.admission.read_current()
        checkpoint = base.admission.checkpoint.read_current()
        cohort = witness.cohort
        assert cohort is not None
        self.assertEqual(checkpoint.state_sha256, witness.state_sha256)
        self.assertEqual(checkpoint.generation, witness.generation)
        self.assertEqual(len(cohort.assignments), 1)
        self.assertEqual(len(witness.attempts), 1)
        self.assertEqual(witness.attempts[0].attempt.attempt_key, outcome.attempt_key)
        intents = base.store.list_intents()
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].intent_sha256, outcome.intent_sha256)
        self.assertEqual(intents[0].claim_id, witness.attempts[0].claim_id)
        audit = inspect_offline_cohort_audit(
            base.admission, base.store, self.fixture.audit
        )
        self.assertTrue(audit.complete)
        self.assertEqual(
            (
                audit.assignment_count,
                audit.claim_count,
                audit.intent_count,
                audit.audit_count,
            ),
            (1, 1, 1, 1),
        )
        recovery = inspect_offline_cohort_recovery(
            base.admission,
            base.store,
            self.fixture.audit,
            anchor=self.fixture.recovery_anchor,
        )
        self.assertEqual(recovery.status, "consistent")
        self.assertEqual(recovery.conservative_exposure_microusd, 0)
        self.assertEqual(len(base.transport.entries), 1)
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(base.transport.entries), 1)

    def test_signed_stop_denies_new_cohort_attempt_and_frozen_fallback_stays_inert(
        self,
    ) -> None:
        base = self.fixture.base
        self.fixture.assign("task-c", "session-b")
        stopped = base.stop_entry()
        base.admission.advance_control(stopped, self.fixture.now + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            self.fixture.execute(
                envelope=base.make_envelope(
                    task_id="task-c", session_id="session-b", attempt_id="attempt-c"
                )
            )
        self.assertEqual(base.admission.read_current().attempts, ())
        self.assertEqual(base.store.list_intents(), ())
        self.assertEqual(base.transport.entries, [])

        resolver = exact_module.ExactRouteTests()
        resolver.setUp()
        self.addCleanup(resolver.doCleanups)
        resolver.policy = resolver.make_policy("role_fallback")
        resolver.preflight = resolver.make_preflight(resolver.policy)
        fallback = resolver.resolve()
        self.assertIsInstance(fallback, ExactRouteSelection)
        assert isinstance(fallback, ExactRouteSelection)
        self.assertEqual(fallback.source, "policy_fallback")
        observation = SyntheticExactRouteProbe(
            SyntheticRouteObservation(
                route=fallback.route,
                observed_at=resolver.now - timedelta(seconds=1),
                valid_until=resolver.now + timedelta(seconds=1),
                available=True,
            )
        )
        observation.check(fallback, resolver.now)
        with self.assertRaises(ValueError):
            self.fixture.execute(selection=fallback)
        self.assertEqual(base.transport.entries, [])
