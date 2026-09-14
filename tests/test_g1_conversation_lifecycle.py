"""End-to-end recorded conversation acceptance for the bounded G1 slice."""

import asyncio
from collections.abc import Callable
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from test_conversation_review import review_packet
from test_task_profile_admission import CapturingClient
from test_task_state_continuation import ContinuationFixture

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_review import REVIEW_FOLLOWUP, review_summary
from mos_eisley.core.models import (
    CriticRequest,
    CriticSpec,
    Critique,
    JudgeDecision,
    JudgeRequest,
)
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.run.conversation_store import ConversationStore


class WaitingClient:
    def __init__(self, response: ModelResponse) -> None:
        self.response = response
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.started.set()
        await self.release.wait()
        return self.response


class G1ConversationLifecycleTests(ContinuationFixture, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_continuation(self)

    async def test_continued_conversation_returns_a_blind_review_to_context(
        self,
    ) -> None:
        packet = review_packet()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state,
            cassette,
            lambda _: None,
            task_state_acquirer=self.acquirer(),
        )
        chat_client = CapturingClient()
        controller.submit(DEMO_PROMPTS[0])
        await controller.step(chat_client)
        first_context = controller.state.entries[0].task_state_context
        assert first_context is not None

        critic_requests: list[CriticRequest] = []
        judge_requests: list[JudgeRequest] = []

        class BlindnessWitness(RecordedReviewer):
            async def critique(
                self, critic: CriticSpec, request: CriticRequest
            ) -> Critique:
                critic_requests.append(request)
                return await super().critique(critic, request)

            async def judge(self, request: JudgeRequest) -> JudgeDecision:
                judge_requests.append(request)
                return await super().judge(request)

        controller.submit_review(packet)
        retained_packet = controller.state.entries[1].review_packet
        with patch("mos_eisley.conversation_review.RecordedReviewer", BlindnessWitness):
            await controller.step()

        review_entry = controller.state.entries[1]
        result = review_entry.review_result
        assert result is not None
        self.assertEqual(retained_packet, packet)
        self.assertEqual(review_entry.answer, review_summary(result))
        self.assertIsNone(review_entry.task_state_context)
        self.assertEqual(controller.state.exchanges_consumed, 1)
        self.assertEqual(len(critic_requests), 2)
        self.assertEqual(len(judge_requests), 1)
        for request in (*critic_requests, *judge_requests):
            encoded = request.model_dump_json()
            self.assertNotIn(DEMO_PROMPTS[0], encoded)
            self.assertNotIn("runtime_task_state", encoded)
            self.assertNotIn("continuation_claim_sha256", encoded)

        followup_client = CapturingClient()
        controller.submit(REVIEW_FOLLOWUP)
        await controller.step(followup_client)
        followup = controller.state.entries[2]
        assert followup.task_state_context is not None
        self.assertEqual(
            followup.task_state_context.task_state.current_work_unit.reference,
            self.next_work.reference,
        )
        self.assertEqual(
            followup.task_state_context.task_state.checkpoint.task_ledger,
            first_context.task_state.checkpoint.task_ledger,
        )
        visible_text = tuple(
            block.text
            for turn in followup_client.requests[0].turns
            for block in turn.blocks
            if isinstance(block, TextBlock)
        )
        self.assertIn(review_summary(result), visible_text)

    async def test_stop_resume_preserves_claim_and_never_replays_cancelled_attempt(
        self,
    ) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        sessions = self.root / "sessions"
        claim_before: bytes
        with ConversationStore(sessions, state.session_id, self.workspace) as store:
            store.save(state)
            controller = ConversationController(
                state,
                cassette,
                store.save,
                task_state_acquirer=self.acquirer(),
            )
            claim_before = self.claim_path.read_bytes()
            response = cassette.exchanges[0].response
            assert response is not None
            waiting = WaitingClient(response)
            original_step = controller.step

            async def waiting_step(
                *, on_started: Callable[[], None] | None = None
            ) -> bool:
                return await original_step(waiting, on_started=on_started)

            queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
            queue.put_nowait(DEMO_PROMPTS[0])
            events: list[dict[str, object]] = []
            with patch.object(controller, "step", side_effect=waiting_step):
                running = asyncio.create_task(
                    terminal(controller, queue, events.append)
                )
                await waiting.started.wait()
                queue.put_nowait("/stop")
                queue.put_nowait(None)
                await asyncio.wait_for(running, timeout=2)

            cancelled = controller.state.entries[0]
            self.assertEqual(cancelled.status, "cancelled")
            self.assertEqual(cancelled.text, DEMO_PROMPTS[0])
            self.assertIsNotNone(cancelled.request_admission)
            self.assertIsNotNone(cancelled.task_state_context)
            self.assertEqual(controller.state.exchanges_consumed, 1)
            self.assertIn("message.cancelled", {event["type"] for event in events})

        with ConversationStore(
            sessions, state.session_id, self.workspace, create=False
        ) as store:
            restored = ConversationController(
                store.load(),
                cassette,
                store.save,
                task_state_acquirer=self.acquirer(),
            )
            self.assertEqual(self.claim_path.read_bytes(), claim_before)
            self.assertFalse(await restored.step())
            self.assertEqual(restored.state.exchanges_consumed, 1)

            resumed_client = CapturingClient()
            restored.submit(DEMO_PROMPTS[1])
            await restored.step(resumed_client)

            self.assertEqual(len(resumed_client.requests), 1)
            self.assertEqual(restored.state.exchanges_consumed, 2)
            self.assertEqual(restored.state.entries[0].status, "cancelled")
            completed = restored.state.entries[1]
            self.assertEqual(completed.status, "completed")
            assert completed.task_state_context is not None
            resumed_task = completed.task_state_context.task_state
            self.assertEqual(
                resumed_task.current_work_unit.reference, self.next_work.reference
            )
            self.assertEqual(
                resumed_task.checkpoint.task_ledger,
                self.proposed.checkpoint.task_ledger,
            )
            request_text = tuple(
                block.text
                for turn in resumed_client.requests[0].turns
                for block in turn.blocks
                if isinstance(block, TextBlock)
            )
            self.assertNotIn(DEMO_PROMPTS[0], request_text)
