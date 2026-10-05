"""Owner, authority, budget and transient-context boundaries for author branches."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from test_conversation import WaitingClient
from test_conversation_context import CapturingClient
from test_conversation_review import review_packet

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_branch_commands import BranchCommands
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_state import ConversationState
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


class BranchBoundaryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.published: list[ConversationState] = []
        self.cassette = demo_cassette().model_copy(
            update={"exchanges": demo_cassette().exchanges * 8}
        )
        self.chat = ConversationController(
            ConversationController.fresh(self.root, self.cassette),
            self.cassette,
            lambda _: None,
            publish_fork=self.published.append,
        )
        self.chat.submit("Selected author intent")
        await self.chat.step(CapturingClient())

    async def asyncTearDown(self) -> None:
        self.temporary.cleanup()

    async def test_fork_selection_drops_queued_steering_and_authority(self) -> None:
        self.chat.submit("Keep this unsent main request")
        before = self.chat.state.entries
        child = self.chat.create_fork(
            (0,), boundary=0, expected_revision=self.chat.state.revision
        )
        self.assertEqual(self.chat.state.entries, before)
        self.assertEqual(child.entries, ())
        self.assertIsNone(child.task_checkpoint)
        self.assertIsNone(child.task_continuation)
        self.assertIsNone(child.memory)
        self.assertTrue(child.memory_disabled)
        assert child.fork_origin is not None
        self.assertFalse(child.fork_origin.grants_authority)
        self.assertEqual(
            child.fork_origin.context.messages[0].text, "Selected author intent"
        )
        self.assertNotIn("unsent", child.model_dump_json())
        self.assertEqual(len(self.published), 1)
        self.assertEqual(child.exchanges_consumed, self.chat.state.exchanges_consumed)

    async def test_stale_cross_owner_and_invalid_selection_dispatch_nothing(
        self,
    ) -> None:
        before = self.chat.state
        for positions, boundary, revision in (
            ((0,), 0, before.revision - 1),
            ((0, 0), 0, before.revision),
            ((1,), 0, before.revision),
            ((0,), 1, before.revision),
        ):
            with self.assertRaises(ValueError):
                self.chat.create_fork(
                    positions, boundary=boundary, expected_revision=revision
                )
            self.assertEqual(self.chat.state, before)
        self.chat.state = before.model_copy(update={"owner_uid": os.getuid() + 1})
        with self.assertRaises(ValueError):
            await self.chat.ask_side(
                "Question", (0,), expected_revision=self.chat.state.revision
            )
        self.assertEqual(self.published, [])

    async def test_forks_reserve_disjoint_parent_allowances(self) -> None:
        first = self.chat.create_fork(
            (0,), boundary=0, expected_revision=self.chat.state.revision
        )
        budget = self.chat.state.branch_budget
        assert budget is not None
        second = self.chat.create_fork(
            (0,), boundary=0, expected_revision=self.chat.state.revision
        )
        self.assertNotEqual(first.session_id, second.session_id)
        assert self.chat.state.branch_budget is not None
        assert second.branch_budget is not None
        self.assertEqual(
            self.chat.state.branch_budget.ledger.attempts,
            budget.ledger.attempts + second.branch_budget.ceiling.attempts,
        )
        self.assertEqual(
            self.chat.state.branch_budget.ledger.output_bytes,
            budget.ledger.output_bytes + second.branch_budget.ceiling.output_bytes,
        )

    async def test_failed_parent_persistence_never_publishes(self) -> None:
        def fail(_state: ConversationState) -> None:
            raise OSError("Synthetic persistence failure")

        self.chat.save = fail
        with self.assertRaises(OSError):
            self.chat.create_fork(
                (0,), boundary=0, expected_revision=self.chat.state.revision
            )
        self.assertEqual(self.published, [])

    async def test_failed_publication_retains_allocation_and_uncertainty(self) -> None:
        def fail(_state: ConversationState) -> None:
            raise OSError("Synthetic publication failure")

        self.chat.publish_fork = fail
        with self.assertRaises(OSError):
            self.chat.create_fork(
                (0,), boundary=0, expected_revision=self.chat.state.revision
            )
        self.assertEqual(self.chat.state.forks[0].state, "uncertain")
        assert self.chat.state.branch_budget is not None
        self.assertEqual(self.chat.state.branch_budget.ledger.attempts, 2)

    async def test_side_answer_is_transient_and_attachment_has_provenance(self) -> None:
        before = self.chat.state.entries
        client = CapturingClient()
        answer = await self.chat.ask_side(
            "PRIVATE_SIDE_QUESTION",
            (0,),
            expected_revision=self.chat.state.revision,
            client=client,
        )
        self.assertEqual(self.chat.state.entries, before)
        self.assertNotIn("PRIVATE_SIDE_QUESTION", self.chat.state.model_dump_json())
        self.assertEqual(client.requests[0].tools, ())
        self.assertIn("Selected author intent", client.requests[0].system)
        self.chat.attach_side(answer.receipt.side_id)
        self.assertIn(answer.receipt.side_id, self.chat.state.entries[-1].text)
        self.assertIn("PRIVATE_SIDE_QUESTION", self.chat.state.entries[-1].text)
        with self.assertRaises(ValueError):
            self.chat.attach_side(answer.receipt.side_id)

    async def test_restart_preserves_spend_and_forgets_unattached_answer(self) -> None:
        answer = await self.chat.ask_side(
            "Question",
            (),
            expected_revision=self.chat.state.revision,
            client=CapturingClient(),
        )
        restarted = ConversationController(
            self.chat.state, self.cassette, lambda _: None
        )
        self.assertEqual(restarted.state.branch_budget, self.chat.state.branch_budget)
        self.assertEqual(restarted.state.exchanges_consumed, 2)
        with self.assertRaises(ValueError):
            restarted.attach_side(answer.receipt.side_id)

    async def test_side_cancellation_preserves_reserved_exposure(self) -> None:
        client = WaitingClient()
        task = asyncio.create_task(
            self.chat.ask_side(
                "Question",
                (),
                expected_revision=self.chat.state.revision,
                client=client,
            )
        )
        await client.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        assert self.chat.state.branch_budget is not None
        self.assertGreater(self.chat.state.branch_budget.ledger.output_bytes, 0)
        self.assertGreater(self.chat.state.branch_budget.ledger.uncertain_effects, 0)
        self.assertEqual(self.chat.state.exchanges_consumed, 2)
        restarted = ConversationController(
            self.chat.state, self.cassette, lambda _: None
        )
        with self.assertRaises(ValueError):
            await restarted.ask_side(
                "Retry",
                (),
                expected_revision=restarted.state.revision,
                client=CapturingClient(),
            )

    async def test_side_call_does_not_interrupt_main_request_or_steering(self) -> None:
        self.chat.submit("Active main task")
        main_client = WaitingClient()
        main = asyncio.create_task(self.chat.step(main_client))
        await main_client.started.wait()
        await self.chat.ask_side(
            "Question",
            (0,),
            expected_revision=self.chat.state.revision,
            client=CapturingClient(),
        )
        self.chat.steer("Keep main steering")
        main_client.release.set()
        await main
        self.assertEqual(self.chat.state.entries[-1].text, "Keep main steering")
        self.assertEqual(self.chat.state.entries[1].status, "completed")
        self.assertEqual(self.chat.state.exchanges_consumed, 3)

    async def test_review_results_are_never_selected_as_branch_context(self) -> None:
        self.chat.submit_review(review_packet())
        await self.chat.step()
        with self.assertRaises(ValueError):
            self.chat.create_fork(
                (1,), boundary=1, expected_revision=self.chat.state.revision
            )
        client = CapturingClient()
        await self.chat.ask_side(
            "Question", (0,), expected_revision=self.chat.state.revision, client=client
        )
        self.assertNotIn("critic-", client.requests[0].system)
        self.assertNotIn("review_result", client.requests[0].system)

    async def test_fork_context_preview_matches_dispatched_request_and_budget(
        self,
    ) -> None:
        child = self.chat.create_fork(
            (0,), boundary=0, expected_revision=self.chat.state.revision
        )
        branch = ConversationController(child, self.cassette, lambda _: None)
        branch.submit("Continue selected conversation")
        preview = preview_context(branch.state)
        client = CapturingClient()
        await branch.step(client)
        self.assertEqual(
            preview.request.sha256, digest(canonical_bytes(client.requests[0]))
        )
        self.assertIn("Selected author intent", client.requests[0].system)
        branch.submit("This exceeds the single-attempt fork allowance")
        self.assertFalse(await branch.step(CapturingClient()))

    async def test_owner_scoped_stores_preserve_branch_metadata(self) -> None:
        child = self.chat.create_fork(
            (0,), boundary=0, expected_revision=self.chat.state.revision
        )
        for kind in (ConversationStore, SQLiteConversationStore):
            storage = self.root / kind.__name__
            with kind(storage, child.session_id, self.root, create=True) as store:
                store.save(child)
            with kind(storage, child.session_id, self.root) as store:
                loaded = store.load()
                self.assertEqual(loaded.fork_origin, child.fork_origin)
                self.assertEqual(loaded.branch_budget, child.branch_budget)

    async def test_rejected_worktree_command_preserves_tui_submission_draft(
        self,
    ) -> None:
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        accepted: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/fork --worktree", False, accepted))
        queue.put_nowait("/quit")
        events: list[dict[str, object]] = []
        await terminal(self.chat, queue, events.append)
        self.assertFalse(await accepted)
        self.assertEqual(self.published, [])
        self.assertTrue(any(e["type"] == "conversation.unavailable" for e in events))

    async def test_local_command_creates_identified_fork_without_model_call(
        self,
    ) -> None:
        events: list[dict[str, object]] = []
        consumed = self.chat.state.exchanges_consumed
        commands = BranchCommands(self.chat, events.append)
        self.assertEqual(await commands.execute("/fork 0 0"), "accepted")
        self.assertEqual(self.chat.state.exchanges_consumed, consumed)
        self.assertEqual(events[-1]["session_id"], self.published[0].session_id)

    async def test_side_admission_releases_editor_and_typed_cancel_stops_only_side(
        self,
    ) -> None:
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        accepted: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/side - Question", False, accepted))
        waiting = WaitingClient()
        events: list[dict[str, object]] = []
        with patch(
            "mos_eisley.conversation_branch_controller.RecordedAgentClient",
            return_value=waiting,
        ):
            task = asyncio.create_task(terminal(self.chat, queue, events.append))
            try:
                await asyncio.wait_for(waiting.started.wait(), 2)
                self.assertTrue(await asyncio.wait_for(accepted, 2))
                cancelled: asyncio.Future[bool] = (
                    asyncio.get_running_loop().create_future()
                )
                queue.put_nowait(
                    ConversationSubmission("/side cancel", False, cancelled)
                )
                self.assertTrue(await asyncio.wait_for(cancelled, 2))
                self.assertEqual(self.chat.state.sides[-1].state, "cancelled")
                self.assertEqual(self.chat.state.entries[0].status, "completed")
            finally:
                queue.put_nowait("/quit")
                await asyncio.wait_for(task, 2)

    async def test_checkout_change_requires_explicit_revalidation_before_dispatch(
        self,
    ) -> None:
        child = self.chat.create_fork(
            (0,), boundary=0, expected_revision=self.chat.state.revision
        )
        branch = ConversationController(child, self.cassette, lambda _: None)
        branch.observe_branch_workspace = lambda _: digest(b"changed checkout")
        branch.submit("Continue selected conversation")
        client = CapturingClient()
        before = branch.state.exchanges_consumed
        with self.assertRaises(ValueError):
            await branch.step(client)
        self.assertEqual(client.requests, [])
        self.assertEqual(branch.state.exchanges_consumed, before)
        branch.revalidate_fork()
        self.assertTrue(await branch.step(client))
