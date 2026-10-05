"""G6-06 C05 inert route-loss and exact fallback race rehearsal."""

from __future__ import annotations

from datetime import timedelta
from unittest import TestCase

from mos_eisley.run.exact_route import ExactRouteDenial, ExactRouteSelection
from mos_eisley.run.routing_transaction import (
    SyntheticExactRouteProbe,
    SyntheticRouteObservation,
)
from tests import test_cohort_controller as cohort_module
from tests import test_exact_route as exact_module


class CohortRouteChangeTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.live()
        self.fixture.assign()

    def unavailable(self) -> None:
        current = self.fixture.route_probe.current
        self.fixture.route_probe.current = current.model_copy(
            update={"available": False}
        )

    def assert_no_claim_or_entry(self) -> None:
        self.assertEqual(self.fixture.base.admission.read_current().attempts, ())
        self.assertEqual(self.fixture.base.transport.entries, [])
        self.assertIsNone(
            self.fixture.base.store.get(self.fixture.base.envelope.attempt_key)
        )

    def test_missing_unavailable_stale_or_changed_probe_denies_before_claim(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "requires an exact-route"):
            self.fixture.base.execute()
        self.assert_no_claim_or_entry()

        current = self.fixture.route_probe.current
        variants = (
            current.model_copy(update={"available": False}),
            current.model_copy(
                update={"valid_until": self.fixture.now - timedelta(milliseconds=1)}
            ),
            current.model_copy(
                update={"route": self.fixture.base.sources.plan.routes[-1]}
            ),
        )
        for observation in variants:
            with self.subTest(observation=observation):
                self.fixture.route_probe.current = observation
                with self.assertRaisesRegex(ValueError, "unavailable or stale"):
                    self.fixture.execute()
                self.assert_no_claim_or_entry()
        self.fixture.route_probe.current = current

    def test_route_removed_at_before_claim_cut_denies_without_claim(self) -> None:
        def remove_at_cut(phase: str) -> None:
            if phase == "before_admission":
                self.unavailable()

        with self.assertRaisesRegex(ValueError, "unavailable or stale"):
            self.fixture.execute(fault=remove_at_cut)
        self.assert_no_claim_or_entry()

    def test_route_removed_after_claim_abandons_and_cannot_retry(self) -> None:
        def remove_after_claim(phase: str) -> None:
            if phase == "after_admission":
                self.unavailable()

        outcome = self.fixture.execute(fault=remove_after_claim)
        self.assertEqual(outcome.status, "abandoned")
        self.assertEqual(self.fixture.base.transport.entries, [])
        state = self.fixture.base.admission.read_current()
        self.assertEqual(len(state.attempts), 1)
        self.assertEqual(
            (state.attempts[0].status, state.attempts[0].charged_microusd),
            ("held", 100),
        )
        self.assertIsNotNone(
            self.fixture.base.store.get(self.fixture.base.envelope.attempt_key)
        )

        self.fixture.route_probe.current = self.fixture.route_probe.current.model_copy(
            update={"available": True}
        )
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.fixture.base.admission.read_current().attempts), 1)
        self.assertEqual(self.fixture.base.transport.entries, [])

    def test_route_removed_after_final_check_has_one_in_flight_entry(self) -> None:
        def remove_after_final(phase: str) -> None:
            if phase == "after_final_check":
                self.unavailable()

        outcome = self.fixture.execute(fault=remove_after_final)
        self.assertEqual(outcome.status, "settled")
        self.assertEqual(len(self.fixture.base.transport.entries), 1)
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.fixture.base.transport.entries), 1)

    def test_frozen_fallback_needs_fresh_selection_and_observation(self) -> None:
        resolver = exact_module.ExactRouteTests()
        resolver.setUp()
        self.addCleanup(resolver.doCleanups)
        resolver.policy = resolver.make_policy("role_fallback")
        resolver.preflight = resolver.make_preflight(resolver.policy)
        selected = resolver.resolve()
        self.assertIsInstance(selected, ExactRouteSelection)
        assert isinstance(selected, ExactRouteSelection)
        self.assertEqual(selected.source, "policy_fallback")

        current = SyntheticExactRouteProbe(
            SyntheticRouteObservation(
                route=selected.route,
                observed_at=resolver.now - timedelta(seconds=1),
                valid_until=resolver.now + timedelta(seconds=1),
                available=True,
            )
        )
        current.check(selected, resolver.now)
        current.current = current.current.model_copy(
            update={"valid_until": resolver.now}
        )
        with self.assertRaisesRegex(ValueError, "unavailable or stale"):
            current.check(selected, resolver.now)

        with self.assertRaises(ValueError):
            self.fixture.execute(selection=selected)
        self.assert_no_claim_or_entry()

        resolver.preflight = resolver.preflight.model_copy(
            update={"valid_until": resolver.now}
        )
        self.assertIsInstance(resolver.resolve(), ExactRouteDenial)
