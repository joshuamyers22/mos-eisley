"""The conversation must keep live review authority outside saved state."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import test_project_guidance_review as guidance_fixture
import test_review_launch_preview as launch_fixture
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_live_review import (
    LiveReviewSelection,
    load_live_result,
    read_selection,
    select_live_review,
    stop_and_reap_live_review,
)
from mos_eisley.conversation_review import (
    ConversationLiveReviewPacket,
    review_summary,
)
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    WorkingConversationState,
)
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import ReviewPolicy, ReviewResult, canonical_bytes, digest
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.review_live_cli import ReviewLiveCompletion
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.review_verdict import RetainedReviewResult


class ConversationLiveReviewTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        fixture = guidance_fixture.GuidedReviewTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.packet = ConversationLiveReviewPacket(
            brief=fixture.prepared.brief,
            prepared_sha256=fixture.prepared.sha256,
            configuration_sha256="1" * 64,
            campaign_seal_sha256="2" * 64,
            campaign_evidence_sha256="3" * 64,
            manifest_sha256="4" * 64,
            guidance_review=fixture.prepared,
        )

    def controller(
        self,
        runner: Callable[[ConversationLiveReviewPacket], Awaitable[ReviewResult]]
        | None = None,
    ) -> ConversationController:
        cassette = demo_cassette()
        return ConversationController(
            ConversationController.fresh(self.fixture.fixture.workspace, cassette),
            cassette,
            lambda state: None,
            validate_review=lambda packet: None,
            run_live_review=runner,
        )

    async def result(self) -> ReviewResult:
        cassette = self.fixture.cassette()
        return await review(
            self.packet.brief,
            tuple(item.critic for item in cassette.critics),
            RecordedReviewer(cassette),
            ReviewPolicy(),
        )

    async def test_live_review_retains_result_and_never_saves_authority(self) -> None:
        result = await self.result()
        calls: list[str] = []

        async def run(packet: ConversationLiveReviewPacket) -> ReviewResult:
            calls.append(packet.brief.brief_id)
            return result

        controller = self.controller(run)
        controller.submit_review(self.packet)
        saved = ConversationState.model_validate_json(
            controller.state.model_dump_json()
        )
        self.assertEqual(saved.entries[0].review_packet, self.packet)
        self.assertNotIn(b"key_file", canonical_bytes(saved))
        self.assertEqual(len(calls), 0)
        await controller.step()
        self.assertEqual(calls, [self.packet.brief.brief_id])
        entry = controller.state.entries[0]
        self.assertEqual(entry.status, "completed")
        self.assertEqual(entry.answer, review_summary(result, live=True))
        self.assertEqual(entry.review_result, result)
        self.assertEqual(controller.state.exchanges_consumed, 0)

    async def test_queued_review_requires_current_launch_and_does_not_burn_attempt(
        self,
    ) -> None:
        async def run(packet: ConversationLiveReviewPacket) -> ReviewResult:
            return await self.result()

        controller = self.controller(run)
        controller.submit_review(self.packet)
        resumed = self.controller()
        resumed.state = ConversationState.model_validate_json(
            controller.state.model_dump_json()
        )
        with self.assertRaisesRegex(ValueError, "current launch inputs"):
            await resumed.step()
        self.assertEqual(resumed.state.entries[0].status, "queued")
        self.assertEqual(resumed.state.exchanges_consumed, 0)

    async def test_wrong_brief_fails_without_publishing_result(self) -> None:
        result = await self.result()
        wrong = result.model_copy(
            update={
                "verdict": result.verdict.model_copy(
                    update={"brief_id": digest(b"other")}
                )
            }
        )

        async def run(packet: ConversationLiveReviewPacket) -> ReviewResult:
            return wrong

        controller = self.controller(run)
        controller.submit_review(self.packet)
        with self.assertRaisesRegex(ValueError, "frozen brief"):
            await controller.step()
        self.assertEqual(controller.state.entries[0].status, "failed")
        self.assertIsNone(controller.state.entries[0].review_result)

    async def test_cancellation_consumes_attempt_without_retry(self) -> None:
        started = asyncio.Event()

        async def run(packet: ConversationLiveReviewPacket) -> ReviewResult:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        controller = self.controller(run)
        controller.submit_review(self.packet)
        task = asyncio.create_task(controller.step())
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(controller.state.entries[0].status, "cancelled")
        self.assertFalse(await controller.step())

    async def test_repeated_cancellation_still_reaps_live_child(self) -> None:
        exited = asyncio.Event()
        signaled = asyncio.Event()

        class Child:
            returncode: int | None = None

            def send_signal(self, _signal: int) -> None:
                signaled.set()

            async def wait(self) -> int:
                await exited.wait()
                self.returncode = 130
                return 130

        child = Child()
        task = asyncio.create_task(stop_and_reap_live_review(child))  # type: ignore[arg-type]
        await signaled.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        exited.set()
        await asyncio.wait_for(task, 1)
        self.assertEqual(child.returncode, 130)

    async def test_full_screen_review_uses_selected_live_runner(self) -> None:
        result = await self.result()
        calls: list[str] = []

        async def run(packet: ConversationLiveReviewPacket) -> ReviewResult:
            calls.append(packet.brief.brief_id)
            return result

        controller = self.controller(run)
        with create_pipe_input() as input:
            ui = ConversationTUI(
                controller,
                self.packet,
                input=input,
                output=DummyOutput(),
            )
            task = asyncio.create_task(ui.run())
            try:
                async with asyncio.timeout(5):
                    while not ui.app.is_running:
                        await asyncio.sleep(0.01)
                    input.send_text("/review\r")
                    while (
                        not controller.state.entries
                        or controller.state.entries[0].status != "completed"
                    ):
                        await asyncio.sleep(0.01)
                self.assertEqual(calls, [self.packet.brief.brief_id])
                self.assertEqual(
                    controller.state.entries[0].answer,
                    review_summary(result, live=True),
                )
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)

    async def test_sqlite_resume_rechecks_current_runner_before_dispatch(self) -> None:
        result = await self.result()

        async def run(packet: ConversationLiveReviewPacket) -> ReviewResult:
            return result

        cassette = demo_cassette()
        workspace = self.fixture.fixture.workspace
        state = ConversationController.fresh(workspace, cassette)
        with SQLiteConversationStore(
            workspace.parent / "live-review-sessions", state.session_id, workspace
        ) as store:
            store.save(state)
            controller = ConversationController(
                state,
                cassette,
                store.save,
                validate_review=lambda packet: None,
                run_live_review=run,
            )
            controller.submit_review(self.packet)
            working = store.load_working()
            self.assertIsInstance(working, WorkingConversationState)
            assert isinstance(working, WorkingConversationState)
            self.assertIsInstance(working.entries[0], ArchivedConversationEntry)
            resumed = ConversationController(
                working,
                cassette,
                store.save_working,
                load_entry=store.load_working_entry,
                validate_review=lambda packet: None,
                run_live_review=run,
            )
            await resumed.step()
            self.assertEqual(resumed.state.entries[0].status, "completed")
            self.assertEqual(store.load().entries[0].review_result, result)


class LiveSelectionTests(TestCase):
    def setUp(self) -> None:
        fixture = launch_fixture.ReviewLaunchTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.base = fixture.base
        self.guided = fixture.guided
        self.configuration = fixture.configuration

    def selection(self) -> tuple[LiveReviewSelection, Path]:
        config = self.base.root / "conversation-config.json"
        config.write_bytes(canonical_bytes(self.configuration))
        prepared = self.base.root / "conversation-prepared.json"
        prepared.write_bytes(canonical_bytes(self.guided.prepared))
        evidence = self.base.root / "campaign-evidence.json"
        evidence.write_bytes(b"campaign evidence fixture")
        manifest = self.base.root / "live-selection.json"
        selection = LiveReviewSelection(
            config=config,
            expected_config_sha256=digest(config.read_bytes()),
            identity=self.base.root / "identity.json",
            workspace=self.guided.fixture.workspace,
            guidance_storage=self.guided.fixture.storage,
            prepared=prepared,
            expected_prepared_sha256=self.guided.prepared.sha256,
            guidance_policy=self.guided.fixture.policy_path,
            expected_guidance_policy_sha256=self.guided.policy_sha,
            spend_ledger=self.base.ledger.path,
            review_dir=self.base.root / "conversation-run",
            key_file=self.base.root / "anthropic-key",
            openai_key_file=self.base.root / "openai-key",
            image_id="sha256:" + "a" * 64,
            campaign_dir=self.base.root / "campaign",
            expected_seal_sha256="b" * 64,
            evidence=evidence,
            expected_evidence_sha256=digest(evidence.read_bytes()),
            authority_policy=self.base.root / "phase-policy.json",
            launch_authority_policy=self.base.root / "launch-policy.json",
            completion_output=self.base.root / "completion.json",
        )
        manifest.write_bytes(canonical_bytes(selection))
        return selection, manifest

    def test_selection_freezes_brief_and_rechecks_source_bytes(self) -> None:
        selection, manifest = self.selection()
        with patch(
            "mos_eisley.conversation_live_review.read_campaign_seal"
        ) as campaign:
            parsed, raw_hash = read_selection(manifest, self.guided.fixture.workspace)
            packet = select_live_review(manifest, self.guided.fixture.workspace)
            self.assertEqual(parsed, selection)
            self.assertEqual(raw_hash, packet.manifest_sha256)
            self.assertEqual(packet.brief, self.guided.prepared.brief)
            self.assertNotIn(b"key_file", canonical_bytes(packet))
            self.assertEqual(campaign.call_count, 2)
            selection.config.write_bytes(selection.config.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                read_selection(manifest, self.guided.fixture.workspace)

    def test_live_child_command_uses_exact_argument_files(self) -> None:
        selection, _ = self.selection()
        command = selection.command()
        self.assertEqual(command[3], "review-live")
        self.assertEqual(command[command.index("--config") + 1], str(selection.config))
        self.assertEqual(
            command[command.index("--completion-output") + 1],
            str(selection.completion_output),
        )

    def test_completion_receipt_binds_retained_result_to_frozen_brief(self) -> None:
        selection, manifest = self.selection()
        with patch("mos_eisley.conversation_live_review.read_campaign_seal"):
            packet = select_live_review(manifest, self.guided.fixture.workspace)
        cassette = self.guided.cassette()
        result = asyncio.run(
            review(
                packet.brief,
                tuple(item.critic for item in cassette.critics),
                RecordedReviewer(cassette),
                ReviewPolicy(),
            )
        )
        retained = RetainedReviewResult(
            approval_sha256="c" * 64,
            judge_completion_sha256="d" * 64,
            judge_outcome_sha256="e" * 64,
            result=result,
        )
        selection.review_dir.mkdir()
        raw = canonical_bytes(retained)
        (selection.review_dir / "review-result.json").write_bytes(raw)
        completion = ReviewLiveCompletion(
            review_dir=str(selection.review_dir.resolve()),
            result_sha256=digest(raw),
            brief_id=packet.brief.brief_id,
            launch_decision_sha256="f" * 64,
        )
        selection.completion_output.write_bytes(canonical_bytes(completion))
        self.assertEqual(load_live_result(selection, packet), result)
        (selection.review_dir / "review-result.json").write_bytes(raw + b" ")
        with self.assertRaisesRegex(ValueError, "completion differs"):
            load_live_result(selection, packet)
