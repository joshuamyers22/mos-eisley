"""Synthetic Git scopes connected to isolated recorded reviews, never live models."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from test_git_review import RepositoryFixture

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_input import submission_command
from mos_eisley.conversation_review import (
    ConversationReviewPacket,
    run_conversation_review,
)
from mos_eisley.core.models import (
    CriticRequest,
    CriticSpec,
    Critique,
    JudgeDecision,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.git_review import GitReviewScope
from mos_eisley.providers.recorded import Cassette, CriticRecording, RecordedReviewer
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


def packet_for(scope: GitReviewScope) -> ConversationReviewPacket:
    brief = scope.brief()
    recordings = tuple(
        CriticRecording(
            critic=CriticSpec(
                id=f"critic-{i}",
                provider=f"fixture-{i}",
                model="fixture",
                persona="Check the selected change.",
            ),
            request_sha256=digest(
                canonical_bytes(
                    CriticRequest(
                        brief=brief,
                        persona="Check the selected change.",
                    )
                )
            ),
            response=Critique(findings=()),
        )
        for i in (1, 2)
    )
    return ConversationReviewPacket(
        schema_version=3,
        git_scope=scope,
        brief=brief,
        cassette=Cassette(
            brief_id=brief.brief_id,
            critics=recordings,
            judge_request_sha256=digest(
                canonical_bytes(
                    JudgeRequest(
                        brief=brief,
                        findings=(),
                    )
                )
            ),
            judge_response=JudgeDecision(rationale="Synthetic fixture only."),
        ),
    )


class ScopedConversationTests(RepositoryFixture, IsolatedAsyncioTestCase):
    async def test_queued_scope_survives_both_stores_and_rejects_stale_resume(
        self,
    ) -> None:
        packet = packet_for(self.changed_scope())
        cassette = demo_cassette()
        for store_type in (ConversationStore, SQLiteConversationStore):
            with (
                self.subTest(store=store_type.__name__),
                TemporaryDirectory() as storage,
            ):
                state = ConversationController.fresh(self.root, cassette)
                with store_type(
                    Path(storage) / "sessions", state.session_id, self.root
                ) as store:
                    store.save(state)
                    controller = ConversationController(state, cassette, store.save)
                    controller.submit_review(packet)
                with store_type(
                    Path(storage) / "sessions",
                    state.session_id,
                    self.root,
                    create=False,
                ) as store:
                    restored = store.load()
                    self.assertEqual(restored.entries[0].review_packet, packet)
                    self.path.write_text("stale resumed input\n")
                    resumed = ConversationController(restored, cassette, store.save)
                    with self.assertRaisesRegex(ValueError, "scope changed"):
                        await resumed.step()
                    self.assertEqual(resumed.state.exchanges_consumed, 0)
                self.path.write_text("if quantity > 10:\n    discount()\n")

    def controller(self) -> ConversationController:
        cassette = demo_cassette()
        return ConversationController(
            ConversationController.fresh(self.root, cassette),
            cassette,
            lambda state: None,
        )

    async def test_typed_scope_uses_exact_packet_and_preserves_chat_position(
        self,
    ) -> None:
        packet = packet_for(self.changed_scope())
        controller = self.controller()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/review --uncommitted")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append, packet)
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertIsNotNone(controller.state.entries[0].review_result)
        preview = next(
            event for event in events if event["type"] == "conversation.review_scope"
        )
        self.assertEqual(
            preview["scope_id"], packet.git_scope.scope_id if packet.git_scope else None
        )
        restored = ConversationState.model_validate_json(
            canonical_bytes(controller.state)
        )
        self.assertEqual(restored.entries[0].review_packet, packet)

    async def test_preview_without_packet_does_not_dispatch(self) -> None:
        self.changed_scope()
        controller = self.controller()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/review --uncommitted")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        with patch("mos_eisley.conversation.run_conversation_review") as run:
            await terminal(controller, queue, events.append)
        run.assert_not_called()
        self.assertEqual(controller.state.entries, ())
        self.assertIn("conversation.review_scope", [event["type"] for event in events])

    async def test_stale_packet_is_not_rebound_to_new_scope(self) -> None:
        packet = packet_for(self.changed_scope())
        self.path.write_text("different change\n")
        controller = self.controller()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/review --uncommitted")
        queue.put_nowait(None)
        with patch("mos_eisley.conversation.run_conversation_review") as run:
            await terminal(controller, queue, lambda event: None, packet)
        run.assert_not_called()
        self.assertEqual(controller.state.entries, ())

    async def test_source_changed_before_dispatch_never_calls_critic(self) -> None:
        packet = packet_for(self.changed_scope())
        self.path.write_text("stale\n")
        with (
            patch.object(RecordedReviewer, "critique") as critique,
            self.assertRaisesRegex(ValueError, "scope changed"),
        ):
            await run_conversation_review(packet)
        critique.assert_not_called()

    async def test_source_changed_during_review_cannot_return_result(self) -> None:
        packet = packet_for(self.changed_scope())
        original = RecordedReviewer.judge
        path = self.path

        async def mutate(
            reviewer: RecordedReviewer, request: JudgeRequest
        ) -> JudgeDecision:
            result = await original(reviewer, request)
            path.write_text("changed during review\n")
            return result

        with (
            patch.object(RecordedReviewer, "judge", mutate),
            self.assertRaisesRegex(ValueError, "scope changed"),
        ):
            await run_conversation_review(packet)

    async def test_incomplete_and_wrong_workspace_packets_are_rejected(self) -> None:
        scope = self.changed_scope()
        packet = packet_for(scope)
        other = self.root / "other"
        other.mkdir()
        cassette = demo_cassette()
        controller = ConversationController(
            ConversationController.fresh(other, cassette),
            cassette,
            lambda state: None,
        )
        with self.assertRaises(ValueError):
            controller.submit_review(packet)
        (self.root / "binary").write_bytes(b"\x00")
        with self.assertRaisesRegex(ValueError, "complete Git scope"):
            packet_for(self.changed_scope())

    def test_typed_scope_command_recognized(self) -> None:
        self.assertEqual(submission_command("/review --uncommitted"), "review")
