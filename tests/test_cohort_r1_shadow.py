"""G6-06 R1 offline shadow-only exact decision and metadata tests."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.core.models import digest
from mos_eisley.run.cohort_controller import OfflineCohortController
from mos_eisley.run.cohort_shadow import (
    OfflineShadowDecisionBatch,
    evaluate_offline_shadow_route,
    write_offline_shadow_batch,
)
from mos_eisley.run.routing_transaction import (
    SyntheticCohortAuditSink,
    SyntheticExactRouteProbe,
    SyntheticRouteObservation,
)
from mos_eisley.run.witnessed_admission import (
    CohortManifest,
    CohortRelease,
    SyntheticCohortTrust,
    sign_synthetic_cohort_release,
)
from tests import test_exact_route as exact_module
from tests import test_witnessed_admission as witness_module


class CohortR1ShadowTests(TestCase):
    def setUp(self) -> None:
        self.configure("calibrated_route")

    def configure(self, action: str) -> None:
        self.base = witness_module.WitnessedAdmissionTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.resolver = exact_module.ExactRouteTests()
        self.resolver.setUp()
        self.addCleanup(self.resolver.doCleanups)
        self.resolver.now = self.base.now
        self.resolver.policy = self.resolver.make_policy(action)
        self.resolver.preflight = self.resolver.make_preflight(
            self.resolver.policy
        ).model_copy(
            update={
                "control_anchor_policy_sha256": (
                    self.base.admission.anchor_policy.policy_sha256
                ),
                "anchored_control_entry_sha256": self.base.genesis.anchor_entry_sha256,
            }
        )
        self.now = self.resolver.now
        owner_key = Ed25519PrivateKey.generate()
        operator_key = Ed25519PrivateKey.generate()
        go_sha256 = digest(b"r1-synthetic-g6-05-go")
        trust = SyntheticCohortTrust(
            owner_signer_id="r1-owner",
            owner_public_key_hex=owner_key.public_key().public_bytes_raw().hex(),
            operator_signer_id="r1-operator",
            operator_public_key_hex=operator_key.public_key().public_bytes_raw().hex(),
            g6_05_go_sha256=go_sha256,
        )
        self.manifest = CohortManifest(
            owner_id="owner-a",
            cohort_id="cohort-a",
            witness_epoch_id=self.base.enrollment.epoch_id,
            witness_enrollment_sha256=self.base.enrollment.enrollment_sha256,
            budget_policy_sha256=self.base.budget_policy.policy_sha256,
            candidate_policy_sha256=self.resolver.policy.candidate_policy_sha256,
            promotion_receipt_sha256=self.resolver.preflight.promotion_receipt_sha256,
            broker_build_sha256=digest(b"r1-synthetic-broker-build"),
            target_host_id="r1-fixture-host",
            tasks=self.base.budget_policy.tasks,
            stages=("stage-a",),
            max_assignments=2,
            max_concurrent=1,
            valid_from=self.now - timedelta(minutes=1),
            valid_until=self.now + timedelta(minutes=5),
        )
        self.release = sign_synthetic_cohort_release(
            CohortRelease(
                manifest_sha256=self.manifest.manifest_sha256,
                g6_05_go_sha256=go_sha256,
                witness_epoch_id=self.manifest.witness_epoch_id,
                broker_build_sha256=self.manifest.broker_build_sha256,
                target_host_id=self.manifest.target_host_id,
                sequence=0,
                phase="shadow_only",
                issued_at=self.now - timedelta(seconds=1),
                valid_until=self.now + timedelta(minutes=5),
            ),
            owner_signer_id="r1-owner",
            owner_private_key=owner_key.private_bytes_raw(),
            operator_signer_id="r1-operator",
            operator_private_key=operator_key.private_bytes_raw(),
        )
        self.controller = OfflineCohortController(self.base.admission)
        self.controller.enroll_shadow(
            manifest=self.manifest,
            trust=trust,
            signed_release=self.release,
            now=self.now,
        )
        self.audit = SyntheticCohortAuditSink.create_witnessed(
            self.base.root / f"r1-audit-{action}.sqlite", admission=self.base.admission
        )
        selected_route = (
            self.resolver.routes[0]
            if action == "calibrated_route"
            else self.resolver.routes[1]
        )
        self.probe = SyntheticExactRouteProbe(
            SyntheticRouteObservation(
                route=selected_route,
                observed_at=self.now - timedelta(seconds=1),
                valid_until=self.now + timedelta(minutes=1),
                available=True,
            )
        )

    def decide(self, **changes: object):
        values: dict[str, object] = {
            "admission": self.base.admission,
            "owner_id": "owner-a",
            "cohort_id": "cohort-a",
            "task_id": "task-a",
            "session_id": "session-a",
            "stage_id": "stage-a",
            "plan": self.resolver.plan,
            "sealed_study": self.resolver.sealed,
            "policy": self.resolver.policy,
            "preflight": self.resolver.preflight,
            "features": self.resolver.features,
            "requirements": self.resolver.requirements,
            "registry": self.resolver.registry,
            "installed_backend": "fixture",
            "installed_client_version": "fixture/1",
            "route_probe": self.probe,
            "monitor": self.base.monitor,
            "now": self.now,
        }
        values.update(changes)
        return evaluate_offline_shadow_route(**values)  # type: ignore[arg-type]

    def assert_no_assignment_claim_or_send(self) -> None:
        state = self.base.admission.read_current()
        cohort = state.cohort
        assert cohort is not None
        self.assertEqual(cohort.assignments, ())
        self.assertEqual(state.attempts, ())
        self.assertEqual(self.base.store.list_intents(), ())
        self.assertEqual(self.audit.read_current(), ())
        self.assertEqual(self.base.transport.entries, [])

    def test_calibrated_shadow_decision_records_only_bounded_metadata(self) -> None:
        before = self.base.admission.read_current()
        checkpoint = self.base.admission.checkpoint.read_current()
        decision = self.decide()
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.selection_source, "calibrated_route")
        self.assertEqual(
            decision.selected_candidate_id, self.resolver.routes[0].candidate_id
        )
        self.assertEqual(decision.manifest_sha256, self.manifest.manifest_sha256)
        self.assertFalse(decision.assignment_authorized)
        self.assertFalse(decision.claim_authorized)
        self.assertFalse(decision.dispatch_authorized)
        batch = OfflineShadowDecisionBatch(
            manifest_sha256=self.manifest.manifest_sha256,
            release_sha256=self.release.release.release_sha256,
            candidate_policy_sha256=self.manifest.candidate_policy_sha256,
            decisions=(decision,),
        )
        path = self.base.root / "r1-shadow-decisions.json"
        write_offline_shadow_batch(path, batch)
        recorded = json.loads(path.read_text())
        self.assertEqual(recorded["decisions"][0]["status"], "selected")
        with self.assertRaises(ValidationError):
            OfflineShadowDecisionBatch.model_validate(
                batch.model_dump() | {"dispatch_authorized": True}
            )
        with self.assertRaises(ValidationError):
            OfflineShadowDecisionBatch.model_validate(
                batch.model_dump()
                | {"candidate_policy_sha256": digest(b"r1-changed-policy")}
            )
        raw = path.read_bytes()
        self.assertNotIn(self.base.request.system.encode(), raw)
        self.assertNotIn(b"Synthetic task", raw)
        self.assertEqual(self.base.admission.read_current(), before)
        self.assertEqual(self.base.admission.checkpoint.read_current(), checkpoint)
        self.assert_no_assignment_claim_or_send()

    def test_shadow_release_cannot_assign_or_claim(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.assign(
                owner_id="owner-a",
                cohort_id="cohort-a",
                task_id="task-a",
                session_id="session-a",
                stage_id="stage-a",
                candidate_policy_sha256=self.manifest.candidate_policy_sha256,
                expected_release_sha256=self.release.release.release_sha256,
                now=self.now,
            )
        with self.assertRaises(ValueError):
            self.base.claim()
        self.assert_no_assignment_claim_or_send()

    def test_eligible_task_population_has_exact_shadow_coverage(self) -> None:
        decisions = tuple(
            self.decide(task_id=item.task_id, session_id=item.session_id)
            for item in self.manifest.tasks
        )
        self.assertEqual(len(decisions), len(self.manifest.tasks))
        self.assertEqual(len({item.task_session_sha256 for item in decisions}), 3)
        self.assertTrue(all(item.status == "selected" for item in decisions))
        self.assertEqual(
            {item.selected_candidate_id for item in decisions},
            {self.resolver.routes[0].candidate_id},
        )
        self.assert_no_assignment_claim_or_send()

    def test_unavailable_changed_and_stale_routes_do_not_auto_fallback(self) -> None:
        original = self.probe.current
        variants = (
            original.model_copy(update={"available": False}),
            original.model_copy(update={"valid_until": self.now}),
            original.model_copy(update={"route": self.resolver.routes[1]}),
        )
        for observation in variants:
            with self.subTest(observation=observation):
                self.probe.current = observation
                denied = self.decide()
                self.assertEqual(
                    (denied.status, denied.denial), ("denied", "route_unavailable")
                )
                self.assertEqual(denied.selection_source, "calibrated_route")
                self.assertEqual(
                    denied.selected_candidate_id, self.resolver.routes[0].candidate_id
                )
                self.assert_no_assignment_claim_or_send()
        self.probe.current = original
        changed = self.resolver.make_policy("role_fallback")
        self.assertEqual(self.decide(policy=changed).denial, "policy_mismatch")
        self.assert_no_assignment_claim_or_send()

    def test_frozen_policy_fallback_is_a_separate_shadow_lineage(self) -> None:
        self.configure("role_fallback")
        decision = self.decide()
        self.assertEqual(
            (decision.status, decision.selection_source),
            ("selected", "policy_fallback"),
        )
        self.assertEqual(
            decision.selected_candidate_id, self.resolver.routes[1].candidate_id
        )
        self.assert_no_assignment_claim_or_send()

    def test_monitor_expiry_stop_and_scope_fail_closed(self) -> None:
        self.base.monitor.healthy = False
        self.assertEqual(self.decide().denial, "monitor_unavailable")
        self.base.monitor.healthy = True
        self.assertEqual(
            self.decide(now=self.now + timedelta(seconds=31)).denial,
            "resolver_denied",
        )
        stale_control = self.resolver.preflight.model_copy(
            update={"anchored_control_entry_sha256": digest(b"r1-stale-control")}
        )
        self.assertEqual(
            self.decide(preflight=stale_control).denial,
            "control_blocked",
        )
        self.assertEqual(
            self.decide(now=self.now + timedelta(minutes=6)).denial,
            "release_inactive",
        )
        for changes in ({"owner_id": "other"}, {"task_id": "unlisted"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.decide(**changes)
        stopped = self.base.stop_entry()
        self.base.admission.advance_control(stopped, self.now + timedelta(seconds=1))
        self.assertEqual(
            self.decide(now=self.now + timedelta(seconds=1)).denial,
            "control_blocked",
        )
        self.assert_no_assignment_claim_or_send()
