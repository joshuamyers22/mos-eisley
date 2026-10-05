"""G6-06 C08 coordinated witness, intent and audit rollback rehearsal."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest import TestCase

from mos_eisley.core.models import digest
from mos_eisley.run.routing_transaction import (
    capture_synthetic_cohort_recovery_anchor,
    inspect_offline_cohort_recovery,
)
from tests import test_cohort_controller as cohort_module


class CohortCombinedRollbackTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.live()
        self.fixture.assign("task-a", "session-a")
        self.fixture.assign("task-c", "session-b")
        self.paths: dict[str, Path] = {
            "witness": self.fixture.base.admission.path,
            "checkpoint": self.fixture.base.admission.checkpoint.path,
            "intent": self.fixture.base.store.path,
            "audit": self.fixture.audit.path,
        }
        self.old: dict[str, Path] = {}
        for name, path in self.paths.items():
            copy = self.fixture.base.root / f"before-{name}.sqlite"
            shutil.copyfile(path, copy)
            self.old[name] = copy

    def finish_first(self, *, uncertain: bool = False) -> None:
        if uncertain:
            self.fixture.base.transport = self.fixture.base.make_transport(
                error=TimeoutError("synthetic provider timeout")
            )
        outcome = self.fixture.execute()
        self.assertEqual(outcome.status, "uncertain" if uncertain else "settled")
        self.fixture.recovery_anchor = capture_synthetic_cohort_recovery_anchor(
            self.fixture.base.admission, self.fixture.base.store, self.fixture.audit
        )
        self.assertEqual(len(self.fixture.base.transport.entries), 1)

    def restore(self, *names: str) -> None:
        for name in names:
            shutil.copyfile(self.old[name], self.paths[name])

    def inventory(self):
        return inspect_offline_cohort_recovery(
            self.fixture.base.admission,
            self.fixture.base.store,
            self.fixture.audit,
            anchor=self.fixture.recovery_anchor,
        )

    def try_next_task(self) -> None:
        envelope = self.fixture.base.make_envelope(
            task_id="task-c", session_id="session-b", attempt_id="attempt-c"
        )
        with self.assertRaises(ValueError):
            self.fixture.execute(envelope=envelope)
        self.assertEqual(len(self.fixture.base.transport.entries), 1)

    def test_healthy_high_water_matches_without_mutation(self) -> None:
        self.finish_first()
        before = tuple(path.read_bytes() for path in self.paths.values())
        inventory = self.inventory()
        after = tuple(path.read_bytes() for path in self.paths.values())
        self.assertEqual(before, after)
        self.assertEqual((inventory.status, inventory.reasons), ("consistent", ()))
        self.assertEqual(
            (
                inventory.anchored_assignment_count,
                inventory.anchored_claim_count,
                inventory.anchored_intent_count,
                inventory.anchored_audit_count,
            ),
            (2, 1, 1, 1),
        )
        self.assertFalse(inventory.admission_authorized)

    def test_missing_or_wrong_scope_high_water_denies_before_claim(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires audit, alert and recovery"):
            self.fixture.execute(recovery_anchor=None)
        wrong = self.fixture.recovery_anchor.model_copy(
            update={"witness_id": digest(b"different-witness")}
        )
        with self.assertRaisesRegex(ValueError, "high water disagrees"):
            self.fixture.execute(recovery_anchor=wrong)
        self.assertEqual(self.fixture.base.admission.read_current().attempts, ())
        self.assertEqual(self.fixture.base.transport.entries, [])
        self.assertEqual(self.fixture.base.store.list_intents(), ())

    def test_each_store_rollback_blocks_new_send(self) -> None:
        for name, reason in (
            ("witness", "witness_unreadable"),
            ("checkpoint", "witness_unreadable"),
            ("intent", "intent_rollback"),
            ("audit", "audit_rollback"),
        ):
            with self.subTest(name=name):
                case = cohort_module.CohortControllerTests()
                case.setUp()
                self.addCleanup(case.doCleanups)
                case.live()
                case.assign("task-a", "session-a")
                case.assign("task-c", "session-b")
                paths = {
                    "witness": case.base.admission.path,
                    "checkpoint": case.base.admission.checkpoint.path,
                    "intent": case.base.store.path,
                    "audit": case.audit.path,
                }
                old = case.base.root / f"old-{name}.sqlite"
                shutil.copyfile(paths[name], old)
                self.assertEqual(case.execute().status, "settled")
                case.recovery_anchor = capture_synthetic_cohort_recovery_anchor(
                    case.base.admission, case.base.store, case.audit
                )
                shutil.copyfile(old, paths[name])
                inventory = inspect_offline_cohort_recovery(
                    case.base.admission,
                    case.base.store,
                    case.audit,
                    anchor=case.recovery_anchor,
                )
                self.assertEqual(inventory.status, "blocked")
                self.assertIn(reason, inventory.reasons)
                with self.assertRaises(ValueError):
                    case.execute(
                        envelope=case.base.make_envelope(
                            task_id="task-c",
                            session_id="session-b",
                            attempt_id="attempt-c",
                        )
                    )
                self.assertEqual(len(case.base.transport.entries), 1)

    def test_coordinated_intent_and_audit_restore_is_detected(self) -> None:
        self.finish_first()
        self.restore("intent", "audit")
        inventory = self.inventory()
        self.assertEqual(inventory.status, "blocked")
        self.assertIn("intent_rollback", inventory.reasons)
        self.assertIn("audit_rollback", inventory.reasons)
        self.assertNotIn("audit_join_incomplete", inventory.reasons)
        self.try_next_task()

    def test_witness_and_local_restore_with_current_checkpoint_is_detected(
        self,
    ) -> None:
        self.finish_first()
        self.restore("witness", "intent", "audit")
        inventory = self.inventory()
        self.assertEqual(inventory.status, "blocked")
        self.assertIn("witness_unreadable", inventory.reasons)
        self.assertIn("intent_rollback", inventory.reasons)
        self.assertIn("audit_rollback", inventory.reasons)
        self.try_next_task()

    def test_full_local_restore_needs_external_high_water(self) -> None:
        self.finish_first()
        self.restore("witness", "checkpoint", "intent", "audit")
        before = tuple(path.read_bytes() for path in self.paths.values())
        self.assertEqual(
            self.fixture.base.admission.read_current().generation,
            self.fixture.recovery_anchor.checkpoint.generation - 2,
        )
        inventory = self.inventory()
        self.assertEqual(
            before, tuple(path.read_bytes() for path in self.paths.values())
        )
        self.assertEqual(inventory.status, "blocked")
        self.assertIn("checkpoint_rollback", inventory.reasons)
        self.assertIn("claim_rollback", inventory.reasons)
        self.assertIn("intent_rollback", inventory.reasons)
        self.assertIn("audit_rollback", inventory.reasons)
        self.try_next_task()
        self.assertEqual(
            before, tuple(path.read_bytes() for path in self.paths.values())
        )

    def test_rolled_back_uncertain_claim_keeps_full_possible_exposure(self) -> None:
        self.finish_first(uncertain=True)
        self.restore("witness", "checkpoint", "intent", "audit")
        inventory = self.inventory()
        self.assertEqual(inventory.status, "blocked")
        self.assertEqual(inventory.conservative_exposure_microusd, 100)
        self.assertEqual(inventory.anchored_claim_count, 1)
        self.try_next_task()
