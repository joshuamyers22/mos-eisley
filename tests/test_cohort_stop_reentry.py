"""G6-06 C06 synthetic witnessed stop, restart and re-entry denial tests."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest import TestCase

from mos_eisley.core.models import digest
from mos_eisley.evaluation.routing_activation import RoutingActivationAuthorityPolicy
from mos_eisley.run.activation_control import (
    AnchoredRoutingControl,
    RoutingControlAnchorPolicy,
)
from mos_eisley.run.cohort_stop import inspect_offline_cohort_stop
from mos_eisley.run.routing_transaction import (
    FrozenCohortRecoveryAnchor,
    OfflineTransactionStore,
    SyntheticCohortAuditSink,
    capture_synthetic_cohort_recovery_anchor,
)
from mos_eisley.run.store import private_write
from mos_eisley.run.witnessed_admission import (
    SyntheticAdmissionTrust,
    SyntheticCheckpointStore,
    SyntheticWitnessedAdmission,
    sign_witness_enrollment,
)
from tests import test_cohort_controller as cohort_module


def inspect_restarted_stop_bundle(path: str) -> None:
    """Separate-process read-only stop inventory from synthetic private stores."""
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
    inventory = inspect_offline_cohort_stop(
        admission,
        OfflineTransactionStore(Path(bundle["intent_path"])),
        SyntheticCohortAuditSink(Path(bundle["audit_path"])),
        recovery_anchor=FrozenCohortRecoveryAnchor.model_validate_json(
            json.dumps(bundle["recovery_anchor"])
        ),
    )
    print(inventory.model_dump_json())


class CohortStopReentryTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.live()
        self.fixture.assign("task-a", "session-a")

    def stop(self) -> AnchoredRoutingControl:
        stopped = self.fixture.base.stop_entry()
        self.fixture.base.admission.advance_control(
            stopped, self.fixture.now + timedelta(seconds=1)
        )
        return stopped

    def inventory(self):
        return inspect_offline_cohort_stop(
            self.fixture.base.admission,
            self.fixture.base.store,
            self.fixture.audit,
            recovery_anchor=self.fixture.recovery_anchor,
        )

    def restart_bundle(self) -> Path:
        base = self.fixture.base
        self.fixture.recovery_anchor = capture_synthetic_cohort_recovery_anchor(
            base.admission, base.store, self.fixture.audit
        )
        bundle = {
            "witness_path": str(base.admission.path),
            "checkpoint_path": str(base.admission.checkpoint.path),
            "intent_path": str(base.store.path),
            "audit_path": str(self.fixture.audit.path),
            "trust": base.trust.model_dump(mode="json"),
            "anchor_policy": base.activation.control_anchor_policy.model_dump(
                mode="json"
            ),
            "activation_authorities": base.activation.authority_policy.model_dump(
                mode="json"
            ),
            "witness_private_key": base.witness_key.private_bytes_raw().hex(),
            "recovery_anchor": self.fixture.recovery_anchor.model_dump(mode="json"),
        }
        path = base.root / "stop-restart-bundle.json"
        private_write(path, json.dumps(bundle).encode())
        return path

    def test_stop_before_claim_persists_and_preserves_assignment(self) -> None:
        stopped = self.stop()
        with self.assertRaises(ValueError):
            self.fixture.execute()
        with self.assertRaises(ValueError):
            self.fixture.assign("task-c", "session-b")
        inventory = self.inventory()
        self.assertEqual(
            inventory.stop_control_entry_sha256, stopped.anchor_entry_sha256
        )
        self.assertEqual(
            (
                inventory.assignment_count,
                inventory.claim_count,
                inventory.intent_count,
                inventory.possible_in_flight_count,
            ),
            (1, 0, 0, 0),
        )
        self.assertTrue(inventory.stop_acknowledged)
        self.assertFalse(inventory.reentry_authorized)
        self.assertEqual(self.fixture.base.transport.entries, [])

    def test_stop_after_claim_abandons_and_survives_separate_process(self) -> None:
        def stop_after_claim(phase: str) -> None:
            if phase == "after_admission":
                self.stop()

        outcome = self.fixture.execute(fault=stop_after_claim)
        self.assertEqual(outcome.status, "abandoned")
        self.assertEqual(self.fixture.base.transport.entries, [])
        inventory = self.inventory()
        self.assertEqual(
            (
                inventory.assignment_count,
                inventory.claim_count,
                inventory.intent_count,
                inventory.audit_count,
                inventory.possible_in_flight_count,
                inventory.conservative_exposure_microusd,
            ),
            (1, 1, 1, 1, 1, 100),
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from tests.test_cohort_stop_reentry import "
                "inspect_restarted_stop_bundle; import sys; "
                "inspect_restarted_stop_bundle(sys.argv[1])",
                str(self.restart_bundle()),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        restarted = json.loads(result.stdout)
        self.assertTrue(restarted["stop_acknowledged"])
        self.assertFalse(restarted["reentry_authorized"])
        self.assertEqual(restarted["conservative_exposure_microusd"], 100)
        base = self.fixture.base
        reopened = SyntheticWitnessedAdmission(
            base.admission.path,
            SyntheticCheckpointStore(base.admission.checkpoint.path),
            base.trust,
            base.activation.control_anchor_policy,
            base.activation.authority_policy,
            base.witness_key.private_bytes_raw(),
        )
        with self.assertRaises(ValueError):
            self.fixture.execute(
                admission=reopened,
                store=OfflineTransactionStore(base.store.path),
                audit=SyntheticCohortAuditSink(self.fixture.audit.path),
            )

    def test_stop_after_final_read_keeps_one_possible_in_flight_entry(self) -> None:
        self.fixture.base.transport = self.fixture.base.make_transport(
            error=TimeoutError("synthetic provider timeout")
        )

        def stop_after_final(phase: str) -> None:
            if phase == "after_final_check":
                self.stop()

        outcome = self.fixture.execute(fault=stop_after_final)
        self.assertEqual(outcome.status, "uncertain")
        self.assertEqual(len(self.fixture.base.transport.entries), 1)
        inventory = self.inventory()
        self.assertEqual(inventory.possible_in_flight_count, 1)
        self.assertEqual(inventory.conservative_exposure_microusd, 100)
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.fixture.base.transport.entries), 1)

    def test_unavailable_alert_path_never_claims_stop_acknowledged(self) -> None:
        self.fixture.alerts.delivery_acknowledged = False
        with self.assertRaises(ValueError):
            self.fixture.execute()
        with self.assertRaisesRegex(ValueError, "no witnessed stop"):
            self.inventory()
        self.assertEqual(self.fixture.base.admission.read_current().attempts, ())
        self.stop()
        self.fixture.alerts.delivery_acknowledged = True
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertTrue(self.inventory().stop_acknowledged)

    def test_invalid_operator_stop_signature_cannot_claim_acknowledgment(self) -> None:
        stopped = self.fixture.base.stop_entry()
        signature = stopped.signed_control.signature.model_copy(
            update={"signature_base64": base64.b64encode(bytes(64)).decode("ascii")}
        )
        bad = stopped.model_copy(
            update={
                "signed_control": stopped.signed_control.model_copy(
                    update={"signature": signature}
                )
            }
        )
        with self.assertRaises(ValueError):
            self.fixture.base.admission.advance_control(
                bad, self.fixture.now + timedelta(seconds=1)
            )
        with self.assertRaisesRegex(ValueError, "no witnessed stop"):
            self.inventory()
        self.fixture.alerts.delivery_acknowledged = False
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(self.fixture.base.admission.read_current().attempts, ())

    def test_same_epoch_stop_cannot_be_cleared_or_released_again(self) -> None:
        stopped = self.stop()
        cleared = stopped.signed_control.control.model_copy(
            update={
                "sequence": stopped.signed_control.control.sequence + 1,
                "issued_at": self.fixture.now + timedelta(seconds=2),
                "emergency_stop": False,
            }
        )
        cleared_entry = AnchoredRoutingControl(
            anchor_id=stopped.anchor_id,
            previous_entry_sha256=stopped.anchor_entry_sha256,
            anchored_at=self.fixture.now + timedelta(seconds=2),
            signed_control=self.fixture.base.activation.sign_control(cleared),
        )
        with self.assertRaisesRegex(ValueError, "did not advance safely"):
            self.fixture.base.admission.advance_control(
                cleared_entry, self.fixture.now + timedelta(seconds=2)
            )
        with self.assertRaisesRegex(ValueError, "did not advance safely"):
            self.fixture.controller.advance_release(
                signed_release=self.fixture.release("bounded_live", 2),
                now=self.fixture.now + timedelta(seconds=1),
            )
        self.fixture.controller.advance_release(
            signed_release=self.fixture.release("closed", 2),
            now=self.fixture.now + timedelta(seconds=1),
        )
        with self.assertRaises(ValueError):
            self.fixture.controller.advance_release(
                signed_release=self.fixture.release("bounded_live", 3),
                now=self.fixture.now + timedelta(seconds=2),
            )
        self.assertEqual(self.inventory().assignment_count, 1)

    def test_new_epoch_does_not_inherit_old_cohort_release(self) -> None:
        self.stop()
        base = self.fixture.base
        enrollment = base.enrollment.model_copy(
            update={
                "epoch_id": digest(b"new-synthetic-epoch"),
                "witness_id": digest(b"new-synthetic-witness"),
                "checkpoint_id": digest(b"new-synthetic-checkpoint"),
            }
        )
        signed = sign_witness_enrollment(
            enrollment, "operator-a", base.operator_key.private_bytes_raw()
        )
        new_admission = base.bootstrap(
            path=base.root / "new-epoch.sqlite", signed_enrollment=signed
        )
        with self.assertRaises(ValueError):
            new_admission.enroll_cohort(
                manifest=self.fixture.manifest,
                trust=self.fixture.release_trust,
                signed_release=self.fixture.shadow,
                now=self.fixture.now,
            )
        new_manifest = self.fixture.manifest.model_copy(
            update={
                "witness_epoch_id": enrollment.epoch_id,
                "witness_enrollment_sha256": enrollment.enrollment_sha256,
            }
        )
        with self.assertRaises(ValueError):
            new_admission.enroll_cohort(
                manifest=new_manifest,
                trust=self.fixture.release_trust,
                signed_release=self.fixture.shadow,
                now=self.fixture.now,
            )
        self.assertIsNone(new_admission.read_current().cohort)
        self.assertEqual(self.inventory().assignment_count, 1)
