"""Synthetic G6-06 cohort release, roster, concurrency and crash tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import digest
from mos_eisley.evaluation.routing_activation import RoutingActivationAuthorityPolicy
from mos_eisley.run.activation_control import RoutingControlAnchorPolicy
from mos_eisley.run.cohort_controller import OfflineCohortController
from mos_eisley.run.routing_transaction import (
    OfflineOutcome,
    SyntheticCohortAuditSink,
    SyntheticExactRouteProbe,
    SyntheticRequiredAlertChannel,
    SyntheticRouteObservation,
)
from mos_eisley.run.witnessed_admission import (
    CohortManifest,
    CohortRelease,
    SignedCohortRelease,
    SyntheticAdmissionTrust,
    SyntheticCheckpointStore,
    SyntheticCohortTrust,
    SyntheticWitnessedAdmission,
    WitnessedAdmissionReceipt,
    WitnessedAssignment,
    sign_synthetic_cohort_release,
)
from tests import test_witnessed_admission as witnessed_module


def run_assignment_bundle(path: str, cut: str) -> None:
    """Process target for actual witness journal/checkpoint cutpoints."""
    bundle = json.loads(Path(path).read_text())
    admission = SyntheticWitnessedAdmission(
        Path(bundle["witness_path"]),
        SyntheticCheckpointStore(Path(bundle["checkpoint_path"])),
        SyntheticAdmissionTrust.model_validate_json(json.dumps(bundle["trust"])),
        RoutingControlAnchorPolicy.model_validate_json(
            json.dumps(bundle["anchor_policy"])
        ),
        RoutingActivationAuthorityPolicy.model_validate_json(
            json.dumps(bundle["activation_authorities"])
        ),
        bytes.fromhex(bundle["witness_private_key"]),
    )

    def stop_at(phase: str) -> None:
        if phase == cut:
            os._exit(77)

    OfflineCohortController(admission).assign(
        owner_id="owner-a",
        cohort_id="cohort-a",
        task_id=bundle["task_id"],
        session_id=bundle["session_id"],
        stage_id="stage-a",
        candidate_policy_sha256=bundle["policy_sha256"],
        expected_release_sha256=bundle["release_sha256"],
        now=admission.budget_policy.valid_from + timedelta(minutes=1),
        fault=stop_at,
    )


class CohortControllerTests(TestCase):
    def setUp(self) -> None:
        self.base = witnessed_module.WitnessedAdmissionTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.now = self.base.now
        self.owner_key = Ed25519PrivateKey.generate()
        self.release_operator_key = Ed25519PrivateKey.generate()
        self.go_sha256 = digest(b"synthetic-g6-05-go")
        self.release_trust = SyntheticCohortTrust(
            owner_signer_id="cohort-owner",
            owner_public_key_hex=self.owner_key.public_key().public_bytes_raw().hex(),
            operator_signer_id="cohort-operator",
            operator_public_key_hex=self.release_operator_key.public_key()
            .public_bytes_raw()
            .hex(),
            g6_05_go_sha256=self.go_sha256,
        )
        self.manifest = CohortManifest(
            owner_id="owner-a",
            cohort_id="cohort-a",
            witness_epoch_id=self.base.enrollment.epoch_id,
            witness_enrollment_sha256=self.base.enrollment.enrollment_sha256,
            budget_policy_sha256=self.base.budget_policy.policy_sha256,
            candidate_policy_sha256=self.base.selection.candidate_policy_sha256,
            promotion_receipt_sha256=self.base.preflight.promotion_receipt_sha256,
            broker_build_sha256=digest(b"synthetic-broker-build"),
            target_host_id="fixture-host",
            tasks=self.base.budget_policy.tasks,
            stages=("stage-a",),
            max_assignments=2,
            max_concurrent=1,
            valid_from=self.now - timedelta(minutes=1),
            valid_until=self.now + timedelta(minutes=5),
        )
        self.controller = OfflineCohortController(self.base.admission)
        self.route_probe = SyntheticExactRouteProbe(
            SyntheticRouteObservation(
                route=self.base.selection.route,
                observed_at=self.now - timedelta(seconds=1),
                valid_until=self.now + timedelta(minutes=1),
                available=True,
            )
        )
        self.audit = SyntheticCohortAuditSink.create_witnessed(
            self.base.root / "cohort-audit.sqlite", admission=self.base.admission
        )
        self.alerts = SyntheticRequiredAlertChannel()
        self.shadow = self.release("shadow_only", 0)
        self.controller.enroll_shadow(
            manifest=self.manifest,
            trust=self.release_trust,
            signed_release=self.shadow,
            now=self.now,
        )

    def release(
        self, phase: str, sequence: int, manifest: CohortManifest | None = None
    ) -> SignedCohortRelease:
        selected = manifest or self.manifest
        return sign_synthetic_cohort_release(
            CohortRelease(
                manifest_sha256=selected.manifest_sha256,
                g6_05_go_sha256=self.go_sha256,
                witness_epoch_id=selected.witness_epoch_id,
                broker_build_sha256=selected.broker_build_sha256,
                target_host_id=selected.target_host_id,
                sequence=sequence,
                phase=phase,  # type: ignore[arg-type]
                issued_at=self.now + timedelta(seconds=sequence - 1),
                valid_until=self.now + timedelta(minutes=5),
            ),
            owner_signer_id="cohort-owner",
            owner_private_key=self.owner_key.private_bytes_raw(),
            operator_signer_id="cohort-operator",
            operator_private_key=self.release_operator_key.private_bytes_raw(),
        )

    def live(self) -> SignedCohortRelease:
        release = self.release("bounded_live", 1)
        self.controller.advance_release(signed_release=release, now=self.now)
        return release

    def assign(
        self,
        task_id: str = "task-a",
        session_id: str = "session-a",
        *,
        release: SignedCohortRelease | None = None,
        **changes: object,
    ) -> WitnessedAssignment:
        current = release or self.release("bounded_live", 1)
        values: dict[str, object] = {
            "owner_id": "owner-a",
            "cohort_id": "cohort-a",
            "task_id": task_id,
            "session_id": session_id,
            "stage_id": "stage-a",
            "candidate_policy_sha256": self.manifest.candidate_policy_sha256,
            "expected_release_sha256": current.release.release_sha256,
            "now": self.now,
        }
        values.update(changes)
        return self.controller.assign(**values)  # type: ignore[arg-type]

    def claim(
        self, task_id: str = "task-a", session_id: str = "session-a"
    ) -> WitnessedAdmissionReceipt:
        envelope = self.base.make_envelope(
            task_id=task_id, session_id=session_id, attempt_id=f"attempt-{task_id}"
        )
        return self.controller.claim(
            attempt=self.base.make_attempt(envelope),
            expected_control=self.base.genesis,
            current_preflight=self.base.preflight,
            now=self.now,
        )

    def execute(self, **changes: object) -> OfflineOutcome:
        values: dict[str, object] = {
            "route_probe": self.route_probe,
            "audit": self.audit,
            "alerts": self.alerts,
        }
        values.update(changes)
        return self.base.execute(**values)

    def bundle(
        self, admission: SyntheticWitnessedAdmission, task_id: str, session_id: str
    ) -> Path:
        cohort = admission.read_current().cohort
        assert cohort is not None
        bundle = {
            "witness_path": str(admission.path),
            "checkpoint_path": str(admission.checkpoint.path),
            "trust": self.base.trust.model_dump(mode="json"),
            "anchor_policy": self.base.activation.control_anchor_policy.model_dump(
                mode="json"
            ),
            "activation_authorities": self.base.activation.authority_policy.model_dump(
                mode="json"
            ),
            "witness_private_key": self.base.witness_key.private_bytes_raw().hex(),
            "task_id": task_id,
            "session_id": session_id,
            "policy_sha256": self.manifest.candidate_policy_sha256,
            "release_sha256": cohort.signed_release.release.release_sha256,
        }
        path = admission.path.with_name(f"bundle-{task_id}.json")
        path.write_text(json.dumps(bundle))
        return path

    @staticmethod
    def run_bundle(bundle_path: Path, cut: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "from tests.test_cohort_controller import run_assignment_bundle; "
                "import sys; run_assignment_bundle(sys.argv[1], sys.argv[2])",
                str(bundle_path),
                cut,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_shadow_and_unassigned_claim_cannot_dispatch(self) -> None:
        with self.assertRaises(ValueError):
            self.assign(release=self.shadow)
        with self.assertRaisesRegex(ValueError, "no active slot"):
            self.claim()
        self.assertEqual(self.base.admission.read_current().attempts, ())
        self.assertEqual(self.base.transport.entries, [])

    def test_signed_release_bindings_and_shadow_to_live_progression(self) -> None:
        bad = self.release("bounded_live", 1).model_copy(
            update={"operator_signature_base64": self.shadow.operator_signature_base64}
        )
        with self.assertRaises(ValueError):
            self.controller.advance_release(signed_release=bad, now=self.now)
        wrong_manifest = self.manifest.model_copy(
            update={"broker_build_sha256": digest(b"changed-build")}
        )
        with self.assertRaises(ValueError):
            self.controller.advance_release(
                signed_release=self.release("bounded_live", 1, wrong_manifest),
                now=self.now,
            )
        live = self.live()
        cohort = self.controller.inspect(owner_id="owner-a", cohort_id="cohort-a")
        assert cohort is not None
        self.assertEqual(
            cohort.signed_release,
            live,
        )
        with self.assertRaises(ValueError):
            self.controller.advance_release(signed_release=live, now=self.now)
        with self.assertRaises(ValueError):
            self.controller.inspect(owner_id="other", cohort_id="cohort-a")

    def test_assignment_is_one_use_and_broker_remains_inert(self) -> None:
        live = self.live()
        with self.assertRaisesRegex(ValueError, "no active slot"):
            self.execute()
        first = self.assign(release=live)
        generation = self.base.admission.read_current().generation
        self.assertEqual(self.assign(release=live), first)
        self.assertEqual(self.base.admission.read_current().generation, generation)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.assign(release=live, session_id="session-b")
        outcome = self.execute()
        self.assertEqual(outcome.status, "settled")
        self.assertEqual(len(self.base.transport.entries), 1)
        cohort = self.controller.inspect(owner_id="owner-a", cohort_id="cohort-a")
        assert cohort is not None
        self.assertEqual(len(cohort.assignments), 1)
        self.assertEqual(cohort.assignments[0].task_id, "task-a")

    def test_assignment_cap_and_stale_release_deny(self) -> None:
        live = self.live()
        with self.assertRaises(ValueError):
            self.assign(release=self.shadow)
        with self.assertRaises(ValueError):
            self.assign(release=live, owner_id="other")
        with self.assertRaises(ValueError):
            self.assign(release=live, stage_id="wrong")
        self.assign(release=live)
        self.assign("task-b", "session-a", release=live)
        with self.assertRaises(ValueError):
            self.assign("task-c", "session-b", release=live)
        cohort = self.controller.inspect(owner_id="owner-a", cohort_id="cohort-a")
        assert cohort is not None
        self.assertEqual(len(cohort.assignments), 2)

    def test_concurrency_releases_only_after_settled_result(self) -> None:
        self.live()
        self.assign("task-a", "session-a")
        self.assign("task-c", "session-b")
        receipt = self.claim()
        with self.assertRaisesRegex(ValueError, "no active slot"):
            self.claim("task-c", "session-b")
        self.base.admission.settle_exact(
            receipt=receipt,
            charged_microusd=15,
            status="settled",
            now=self.now,
        )
        second = self.claim("task-c", "session-b")
        self.assertEqual(second.task_id, "task-c")

    def test_settled_assignment_cannot_claim_a_second_attempt(self) -> None:
        self.live()
        self.assign()
        receipt = self.claim()
        self.base.admission.settle_exact(
            receipt=receipt,
            charged_microusd=15,
            status="settled",
            now=self.now,
        )
        second = self.base.make_envelope(attempt_id="attempt-second")
        with self.assertRaisesRegex(ValueError, "no active slot"):
            self.controller.claim(
                attempt=self.base.make_attempt(second),
                expected_control=self.base.genesis,
                current_preflight=self.base.preflight,
                now=self.now,
            )
        self.assertEqual(len(self.base.admission.read_current().attempts), 1)

    def test_uncertain_claim_retains_concurrency_and_full_exposure(self) -> None:
        self.live()
        self.assign("task-a", "session-a")
        self.assign("task-c", "session-b")
        receipt = self.claim()
        self.base.admission.settle_exact(
            receipt=receipt,
            charged_microusd=100,
            status="uncertain",
            now=self.now,
        )
        with self.assertRaisesRegex(ValueError, "no active slot"):
            self.claim("task-c", "session-b")
        self.assertEqual(len(self.base.admission.read_current().attempts), 1)

    def test_stop_and_close_keep_roster_and_deny_new_claims(self) -> None:
        self.live()
        self.assign()
        stopped = self.base.stop_entry()
        self.base.admission.advance_control(stopped, self.now + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            self.assign("task-b", "session-a", now=self.now + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            self.claim()
        closed = self.release("closed", 2)
        self.controller.advance_release(
            signed_release=closed, now=self.now + timedelta(seconds=1)
        )
        with self.assertRaises(ValueError):
            self.controller.advance_release(
                signed_release=self.release("bounded_live", 3),
                now=self.now + timedelta(seconds=2),
            )
        cohort = self.controller.inspect(owner_id="owner-a", cohort_id="cohort-a")
        assert cohort is not None
        self.assertEqual(
            (cohort.signed_release.release.phase, len(cohort.assignments)),
            ("closed", 1),
        )

    def test_close_after_intent_prevents_inert_transport_entry(self) -> None:
        self.live()
        self.assign()

        def close_after_intent(phase: str) -> None:
            if phase == "after_intent":
                self.controller.advance_release(
                    signed_release=self.release("closed", 2),
                    now=self.now + timedelta(seconds=1),
                )

        outcome = self.execute(fault=close_after_intent)
        self.assertEqual(outcome.status, "abandoned")
        self.assertEqual(self.base.transport.entries, [])
        cohort = self.controller.inspect(owner_id="owner-a", cohort_id="cohort-a")
        assert cohort is not None
        self.assertEqual(len(cohort.assignments), 1)
        self.assertEqual(len(self.base.admission.read_current().attempts), 1)

    def test_assignment_rollback_is_detected_by_checkpoint(self) -> None:
        self.live()
        old = self.base.root / "old-witness.sqlite"
        shutil.copyfile(self.base.admission.path, old)
        self.assign()
        shutil.copyfile(old, self.base.admission.path)
        with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
            self.base.admission.read_current()

    def test_process_kills_preserve_assignment_boundaries(self) -> None:
        for cut, readable, assignments in (
            ("before_db_commit", True, 0),
            ("after_db_commit", False, 1),
            ("after_checkpoint", True, 1),
        ):
            with self.subTest(cut=cut):
                case = self.base.root / f"cut-{cut}"
                case.mkdir()
                admission = self.base.bootstrap(path=case / "witness.sqlite")
                controller = OfflineCohortController(admission)
                controller.enroll_shadow(
                    manifest=self.manifest,
                    trust=self.release_trust,
                    signed_release=self.shadow,
                    now=self.now,
                )
                controller.advance_release(
                    signed_release=self.release("bounded_live", 1), now=self.now
                )
                result = self.run_bundle(
                    self.bundle(admission, "task-a", "session-a"), cut
                )
                self.assertEqual(result.returncode, 77, result.stderr)
                if readable:
                    cohort = admission.read_current().cohort
                    assert cohort is not None
                    self.assertEqual(len(cohort.assignments), assignments)
                else:
                    with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
                        admission.read_current()

    def test_competing_processes_cannot_exceed_last_assignment_slot(self) -> None:
        case = self.base.root / "competing"
        case.mkdir()
        admission = self.base.bootstrap(path=case / "witness.sqlite")
        manifest = self.manifest.model_copy(update={"max_assignments": 1})
        controller = OfflineCohortController(admission)
        controller.enroll_shadow(
            manifest=manifest,
            trust=self.release_trust,
            signed_release=self.release("shadow_only", 0, manifest),
            now=self.now,
        )
        controller.advance_release(
            signed_release=self.release("bounded_live", 1, manifest), now=self.now
        )
        paths = (
            self.bundle(admission, "task-a", "session-a"),
            self.bundle(admission, "task-c", "session-b"),
        )
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "from tests.test_cohort_controller import run_assignment_bundle; "
                    "import sys; run_assignment_bundle(sys.argv[1], sys.argv[2])",
                    str(path),
                    "none",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for path in paths
        ]
        results = [process.communicate(timeout=10) for process in processes]
        self.assertEqual(
            sorted(process.returncode for process in processes), [0, 1], results
        )
        cohort = admission.read_current().cohort
        assert cohort is not None
        self.assertEqual(len(cohort.assignments), 1)
