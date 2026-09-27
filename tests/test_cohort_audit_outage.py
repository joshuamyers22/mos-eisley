"""G6-06 C04 synthetic audit and required-alert outage rehearsal."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from unittest import TestCase

from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.routing_transaction import inspect_offline_cohort_audit
from tests import test_cohort_controller as cohort_module


class CohortAuditOutageTests(TestCase):
    def setUp(self) -> None:
        self.fixture = cohort_module.CohortControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.live()
        self.fixture.assign()

    def inventory(self):
        return inspect_offline_cohort_audit(
            self.fixture.base.admission,
            self.fixture.base.store,
            self.fixture.audit,
        )

    def assert_no_claim_or_send(self) -> None:
        self.assertEqual(self.fixture.base.admission.read_current().attempts, ())
        self.assertEqual(self.fixture.base.store.list_intents(), ())
        self.assertEqual(self.fixture.base.transport.entries, [])

    def test_missing_or_unhealthy_required_paths_deny_before_claim(self) -> None:
        for changes in ({"audit": None}, {"alerts": None}):
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, "requires audit and alert"),
            ):
                self.fixture.execute(**changes)
            self.assert_no_claim_or_send()

        self.fixture.audit.healthy = False
        with self.assertRaisesRegex(ValueError, "audit sink unavailable"):
            self.fixture.execute()
        self.assert_no_claim_or_send()
        self.fixture.audit.healthy = True

        self.fixture.alerts.delivery_acknowledged = False
        with self.assertRaisesRegex(ValueError, "alert path unavailable"):
            self.fixture.execute()
        self.assert_no_claim_or_send()

    def test_audit_loss_after_intent_abandons_and_exposes_gap(self) -> None:
        def lose_audit(phase: str) -> None:
            if phase == "after_intent":
                self.fixture.audit.healthy = False

        outcome = self.fixture.execute(fault=lose_audit)
        self.assertEqual(outcome.status, "abandoned")
        self.assertEqual(self.fixture.base.transport.entries, [])
        self.fixture.audit.healthy = True
        inventory = self.inventory()
        self.assertEqual(
            (
                inventory.assignment_count,
                inventory.claim_count,
                inventory.intent_count,
                inventory.audit_count,
                inventory.missing_audit_count,
                inventory.retained_exposure_microusd,
            ),
            (1, 1, 1, 0, 1, 100),
        )
        self.assertFalse(inventory.complete)
        self.fixture.assign("task-c", "session-b")
        with self.assertRaisesRegex(ValueError, "missing required link"):
            self.fixture.execute(
                envelope=self.fixture.base.make_envelope(
                    task_id="task-c", session_id="session-b", attempt_id="attempt-c"
                )
            )
        self.assertEqual(len(self.fixture.base.admission.read_current().attempts), 1)

    def test_alert_loss_at_preclaim_cut_leaves_no_claim(self) -> None:
        def lose_alert(phase: str) -> None:
            if phase == "before_admission":
                self.fixture.alerts.delivery_acknowledged = False

        with self.assertRaisesRegex(ValueError, "alert path unavailable"):
            self.fixture.execute(fault=lose_alert)
        self.assert_no_claim_or_send()

    def test_lost_alert_after_audit_abandons_with_full_exposure(self) -> None:
        def lose_alert(phase: str) -> None:
            if phase == "after_audit":
                self.fixture.alerts.delivery_acknowledged = False

        outcome = self.fixture.execute(fault=lose_alert)
        self.assertEqual(outcome.status, "abandoned")
        self.assertEqual(self.fixture.base.transport.entries, [])
        inventory = self.inventory()
        self.assertTrue(inventory.complete)
        self.assertEqual(
            (inventory.audit_count, inventory.retained_exposure_microusd), (1, 100)
        )
        self.fixture.alerts.delivery_acknowledged = True
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(self.fixture.base.transport.entries, [])

    def test_audit_join_is_read_only_and_contains_no_task_content(self) -> None:
        self.assertEqual(self.fixture.execute().status, "settled")
        first = self.inventory()
        second = self.inventory()
        self.assertEqual(first, second)
        self.assertEqual(
            (
                first.assignment_count,
                first.claim_count,
                first.intent_count,
                first.audit_count,
                first.retained_exposure_microusd,
            ),
            (1, 1, 1, 1, 0),
        )
        self.assertTrue(first.complete)
        raw = self.fixture.audit.path.read_bytes()
        self.assertNotIn(b"Synthetic task", raw)
        self.assertNotIn(self.fixture.base.request.system.encode(), raw)

    def test_missing_audit_row_blocks_next_admission_after_restore(self) -> None:
        self.fixture.execute()
        with sqlite3.connect(self.fixture.audit.path) as connection:
            connection.execute("DELETE FROM before_send")
        inventory = self.inventory()
        self.assertEqual(inventory.missing_audit_count, 1)
        self.assertFalse(inventory.complete)
        self.fixture.assign("task-c", "session-b")
        with self.assertRaisesRegex(ValueError, "missing required link"):
            self.fixture.execute(
                envelope=self.fixture.base.make_envelope(
                    task_id="task-c", session_id="session-b", attempt_id="attempt-c"
                )
            )

    def test_local_intent_rollback_leaves_unmatched_audit_event(self) -> None:
        self.fixture.execute()
        with sqlite3.connect(self.fixture.base.store.path) as connection:
            connection.execute("DELETE FROM intents")
        inventory = self.inventory()
        self.assertEqual(
            (inventory.intent_count, inventory.unmatched_audit_count), (0, 1)
        )
        self.assertFalse(inventory.complete)

    def test_changed_audit_join_is_rejected_on_read(self) -> None:
        self.fixture.execute()
        event = self.fixture.audit.read_current()[0]
        changed = event.model_copy(update={"task_id": "other-task"})
        with sqlite3.connect(self.fixture.audit.path) as connection:
            connection.execute(
                "UPDATE before_send SET event_json=? WHERE attempt_key=?",
                (canonical_bytes(changed), event.attempt_key),
            )
        with self.assertRaisesRegex(ValueError, "audit join is invalid"):
            self.inventory()

    def test_lost_alert_after_final_check_keeps_single_in_flight_bound(self) -> None:
        def lose_alert(phase: str) -> None:
            if phase == "after_final_check":
                self.fixture.alerts.delivery_acknowledged = False

        self.assertEqual(self.fixture.execute(fault=lose_alert).status, "settled")
        self.assertEqual(len(self.fixture.base.transport.entries), 1)
        self.fixture.alerts.delivery_acknowledged = True
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assertEqual(len(self.fixture.base.transport.entries), 1)

    def test_restored_alert_does_not_clear_witnessed_stop(self) -> None:
        self.fixture.alerts.delivery_acknowledged = False
        stopped = self.fixture.base.stop_entry()
        self.fixture.base.admission.advance_control(
            stopped, self.fixture.now + timedelta(seconds=1)
        )
        self.fixture.alerts.delivery_acknowledged = True
        with self.assertRaises(ValueError):
            self.fixture.execute()
        self.assert_no_claim_or_send()
