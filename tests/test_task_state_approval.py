"""Stale-approval handling at the fresh-continuation boundary."""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase, TestCase

from test_task_profile_admission import CapturingClient
from test_task_state_continuation import (
    SESSION_A,
    SESSION_B,
    ContinuationFixture,
    FixedInspector,
)

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.task_state_store import save_task_state
from mos_eisley.task_state_acquisition import CurrentTaskStateSelection
from mos_eisley.task_state_approval import (
    TaskApprovalRecord,
    TaskApprovalSelection,
    task_approval_subject_sha256,
)
from mos_eisley.task_state_continuation import FreshContextContinuationAcquirer

ISSUED = datetime(2026, 9, 14, 12, tzinfo=UTC)


class ApprovalFixture(ContinuationFixture):
    def prepare_approval(
        self,
        *,
        expires_at: datetime = ISSUED + timedelta(hours=1),
        selected_work_id: str | None = None,
        revoked: bool = False,
    ) -> None:
        selected = self.next_work.reference
        if selected_work_id is not None:
            selected = selected.model_copy(update={"work_unit_id": selected_work_id})
        approval = TaskApprovalRecord(
            scope=self.next_work.scope,
            approval_id="approval-g1-continuation",
            selected_work_unit=selected,
            work_subject_sha256=task_approval_subject_sha256(self.next_work),
            authority="fixture-user",
            source_sha256=digest(b"explicit fixture approval"),
            approved_actions=("continue-task",),
            issued_at=ISSUED,
            expires_at=expires_at,
        )
        self.approval = approval
        self.next_work = self.next_work.model_copy(
            update={"authorization_refs": (approval.sha256,)}
        )
        self.proposed = self.proposed.model_copy(
            update={
                "work_units": tuple(
                    self.next_work
                    if item.reference == self.next_work.reference
                    else item
                    for item in self.proposed.work_units
                )
            }
        )
        save_task_state(
            self.storage,
            self.proposed,
            {
                self.old_artifact.sha256: self.old_payload,
                self.new_artifact.sha256: self.new_payload,
            },
        )
        current = CurrentTaskStateSelection.model_validate_json(
            self.selection_path.read_bytes()
        )
        self.selection_path.write_bytes(
            canonical_bytes(
                current.model_copy(update={"bundle_sha256": self.proposed.sha256})
            )
        )
        self.selection_path.chmod(0o600)
        selection = TaskApprovalSelection(
            scope=self.next_work.scope,
            approvals=(approval,),
            revoked_approval_refs=(approval.sha256,) if revoked else (),
        )
        self.approval_path = self.root / "task-approvals.json"
        self.approval_path.write_bytes(canonical_bytes(selection))
        self.approval_path.chmod(0o600)

    def approved_acquirer(
        self, clock: Callable[[], datetime]
    ) -> FreshContextContinuationAcquirer:
        return FreshContextContinuationAcquirer.from_paths(
            self.storage,
            self.selection_path,
            self.continuation_path,
            self.claim_path,
            inspector=FixedInspector([self.inspection]),
            approval_selection_path=self.approval_path,
            approval_clock=clock,
        )


class TaskStateApprovalTests(ApprovalFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_continuation(self)

    def test_current_approval_is_bound_to_context_and_claim(self) -> None:
        self.prepare_approval()
        checked_at = ISSUED + timedelta(minutes=5)

        state = self.approved_acquirer(lambda: checked_at).acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )

        approval = state.acquisition.approval
        assert approval is not None
        self.assertTrue(state.acquisition.authority_revalidated)
        self.assertTrue(approval.approval_ready)
        self.assertEqual(approval.checked_at, checked_at)
        self.assertEqual(approval.current_approval_refs, (self.approval.sha256,))
        self.assertFalse(approval.grants_authority)
        claim = self.claim_path.read_text()
        self.assertIn(self.approval.sha256, claim)
        self.assertIn(approval.selection_sha256, claim)

    def test_expired_approval_is_not_revived_by_a_new_session(self) -> None:
        self.prepare_approval(expires_at=ISSUED + timedelta(minutes=1))
        acquirer = self.approved_acquirer(lambda: ISSUED + timedelta(minutes=2))

        with self.assertRaisesRegex(ValueError, "stale: expired"):
            acquirer.acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_B,
            )

        self.assertFalse(self.claim_path.exists())

    def test_same_session_retry_rechecks_absolute_expiry(self) -> None:
        self.prepare_approval(expires_at=ISSUED + timedelta(minutes=10))
        now = [ISSUED + timedelta(minutes=1)]
        acquirer = self.approved_acquirer(lambda: now[0])
        acquirer.acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )
        now[0] = ISSUED + timedelta(minutes=11)

        with self.assertRaisesRegex(ValueError, "stale: expired"):
            acquirer.acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )

    def test_expiry_during_claim_fails_before_runtime_return(self) -> None:
        self.prepare_approval(expires_at=ISSUED + timedelta(minutes=10))
        times = iter(
            (
                ISSUED + timedelta(minutes=9),
                ISSUED + timedelta(minutes=11),
            )
        )

        with self.assertRaisesRegex(ValueError, "stale: expired"):
            self.approved_acquirer(lambda: next(times)).acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )

        self.assertTrue(self.claim_path.exists())

    def test_missing_selection_fails_before_claim(self) -> None:
        self.prepare_approval()
        with self.assertRaisesRegex(ValueError, "requires a task approval selection"):
            self.acquirer().acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertFalse(self.claim_path.exists())

    def test_revoked_approval_fails_before_claim(self) -> None:
        self.prepare_approval(revoked=True)
        with self.assertRaisesRegex(ValueError, "stale: revoked"):
            self.approved_acquirer(lambda: ISSUED + timedelta(minutes=1)).acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertFalse(self.claim_path.exists())

    def test_approval_for_other_work_and_edited_selection_fail_closed(self) -> None:
        self.prepare_approval(selected_work_id="other-work")
        with self.assertRaisesRegex(ValueError, "stale: mismatched"):
            self.approved_acquirer(lambda: ISSUED + timedelta(minutes=1)).acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertFalse(self.claim_path.exists())

        self.prepare_approval()
        acquirer = self.approved_acquirer(lambda: ISSUED + timedelta(minutes=1))
        self.approval_path.write_bytes(self.approval_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "changed since launch"):
            acquirer.acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )


class ConversationTaskApprovalTests(ApprovalFixture, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_continuation(self)

    async def test_stale_approval_prevents_recorded_dispatch_and_attempt(self) -> None:
        self.prepare_approval(expires_at=ISSUED + timedelta(minutes=1))
        acquirer = self.approved_acquirer(lambda: ISSUED + timedelta(minutes=2))
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)

        with self.assertRaisesRegex(ValueError, "stale: expired"):
            ConversationController(
                state,
                cassette,
                lambda _: None,
                task_state_acquirer=acquirer,
            )

        self.assertFalse(self.claim_path.exists())
        self.assertEqual(state.exchanges_consumed, 0)

    async def test_current_approval_is_rechecked_for_each_request(self) -> None:
        self.prepare_approval(expires_at=ISSUED + timedelta(minutes=10))
        now = [ISSUED + timedelta(minutes=1)]
        acquirer = self.approved_acquirer(lambda: now[0])
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state,
            cassette,
            lambda _: None,
            task_state_acquirer=acquirer,
        )
        controller.submit(DEMO_PROMPTS[0])
        await controller.step(CapturingClient())
        now[0] = ISSUED + timedelta(minutes=11)
        controller.submit(DEMO_PROMPTS[1])

        with self.assertRaisesRegex(ValueError, "stale: expired"):
            await controller.step(CapturingClient())

        self.assertEqual(controller.state.exchanges_consumed, 1)
