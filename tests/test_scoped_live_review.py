"""Scoped live review shares inert preview and never inherits execution authority."""

import argparse
import asyncio
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import test_conversation_live_review as live_fixture
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation_tui import until
from test_git_review import RepositoryFixture

from mos_eisley import review_live_cli
from mos_eisley.cli import main
from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_live_review import (
    preview_selected_live_review,
    run_selected_live_review,
    select_live_review,
)
from mos_eisley.conversation_review import (
    ConversationLiveReviewPacket,
    ConversationReviewPacket,
)
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import ReviewPolicy, canonical_bytes, digest
from mos_eisley.git_review import freeze_git_scope
from mos_eisley.git_review_cli import parse_review_selection
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.review_approval_terminal import TerminalReviewApproval
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.operator_review_probe import OperatorReviewIdentity
from mos_eisley.run.review_source import check_review_source, read_review_source
from mos_eisley.run.review_verdict import RetainedReviewResult


class ScopedLiveReviewTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        fixture = live_fixture.LiveSelectionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.workspace = fixture.guided.fixture.workspace
        repo = RepositoryFixture()
        repo.root = self.workspace
        repo.git("init", "-b", "main")
        repo.git("config", "user.name", "Synthetic Author")
        repo.git("config", "user.email", "synthetic@example.invalid")
        self.source = self.workspace / "pricing.py"
        self.source.write_text("before\n")
        repo.git("add", "pricing.py")
        repo.git("commit", "-m", "initial")
        self.source.write_text("after\n")
        self.command = "/review --uncommitted --file pricing.py"
        self.scope = freeze_git_scope(
            self.workspace, parse_review_selection(self.command)
        )
        fixture.guided.prepared = fixture.guided.prepare(self.scope.brief())
        selection, manifest = fixture.selection()
        scope_path = fixture.base.root / "scope.json"
        scope_path.write_bytes(canonical_bytes(self.scope))
        self.selection = selection.model_copy(
            update={
                "git_scope": scope_path,
                "expected_scope_sha256": digest(scope_path.read_bytes()),
            }
        )
        self.manifest = manifest
        manifest.write_bytes(canonical_bytes(self.selection))
        self.selection.identity.write_bytes(
            canonical_bytes(
                OperatorReviewIdentity(
                    author_provider="openai",
                    author_model="gpt-6",
                    author_artifact_sha256=digest(b"author"),
                    max_total_microusd=1000,
                )
            )
        )
        self.campaign = patch(
            "mos_eisley.conversation_live_review.read_campaign_seal",
            return_value=(None, None),
        )
        self.campaign.start()
        self.addCleanup(self.campaign.stop)
        charge = patch(
            "mos_eisley.conversation_live_review.campaign_charged_microusd",
            return_value=50,
        )
        charge.start()
        self.addCleanup(charge.stop)
        self.packet = select_live_review(manifest, self.workspace)

    def preview(self):
        return preview_selected_live_review(self.packet, self.manifest, self.workspace)

    async def result(self):
        cassette = self.fixture.guided.cassette()
        return await review(
            self.packet.brief,
            tuple(r.critic for r in cassette.critics),
            RecordedReviewer(cassette),
            ReviewPolicy(),
        )

    def controller(self):
        cassette = demo_cassette()

        def preview(packet: ConversationLiveReviewPacket) -> dict[str, object]:
            intent = preview_selected_live_review(packet, self.manifest, self.workspace)
            return {**intent.model_dump(mode="json"), "text": intent.describe()}

        controller = ConversationController(
            ConversationController.fresh(self.workspace, cassette),
            cassette,
            lambda state: None,
            validate_review=lambda packet: None,
            run_live_review=lambda packet: self.result(),
            preview_live_review=preview,
        )
        return controller

    async def test_preview_binds_guided_source_and_is_inert(self) -> None:
        self.assertNotEqual(self.packet.brief, self.scope.brief())
        before = self.fixture.base.ledger.path.read_bytes()
        source_paths = (
            self.source,
            self.workspace / ".git/index",
            self.workspace / ".git/HEAD",
            self.workspace / ".git/config",
        )
        source_before = {path: path.read_bytes() for path in source_paths}
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=AssertionError("preview dispatched"),
        ):
            preview = self.preview()
        self.assertEqual(preview.target, self.scope.preview())
        self.assertEqual(preview.remaining_microusd, 650)
        self.assertEqual(preview.reserved_upper_bound_microusd, 650)
        self.assertFalse(preview.provider_dispatch_authorized)
        self.assertFalse(preview.posting_authorized)
        self.assertTrue(preview.read_only)
        self.assertIsNone(preview.estimated_cost_microusd)
        self.assertEqual(before, self.fixture.base.ledger.path.read_bytes())
        self.assertEqual(
            source_before, {path: path.read_bytes() for path in source_paths}
        )
        self.assertFalse(self.selection.review_dir.exists())
        self.assertFalse(self.selection.key_file.exists())
        raw = canonical_bytes(self.packet)
        self.assertEqual(
            ConversationLiveReviewPacket.model_validate_json(raw), self.packet
        )
        self.assertNotIn(b"key_file", raw)
        self.assertNotIn(b"launch_authority_policy", raw)
        self.assertEqual(self.packet.schema_version, 2)
        args = self.selection.command()
        self.assertEqual(
            args[args.index("--expected-scope-sha256") + 1], self.scope.scope_id
        )

    async def test_cli_json_plain_and_conversation_intent_agree(self) -> None:
        args = self.fixture.fixture.cli_arguments()
        args = [
            str(self.selection.config) if a.endswith("launch-config.json") else a
            for a in args
        ]
        # cli_arguments writes equivalent configuration/prepared inputs and uses
        # this fixture's same workspace, ledger, policy and unused output parent.
        args += [
            "--git-scope",
            str(self.selection.git_scope),
            "--expected-scope-sha256",
            self.scope.scope_id,
        ]
        for json_mode in (True, False):
            selected = args if json_mode else [a for a in args if a != "--json"]
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(selected), 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["intent"], self.preview().model_dump(mode="json"))
        events: list[dict[str, object]] = []
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait(self.command)
        queue.put_nowait(None)
        controller = self.controller()
        await terminal(controller, queue, events.append, self.packet)
        intent = next(e for e in events if e["type"] == "conversation.review_launch")
        self.assertEqual(intent["target"], self.scope.preview())
        self.assertEqual(controller.state.entries[0].status, "completed")
        self.assertEqual(controller.state.entries[0].review_packet, self.packet)

    async def test_stale_source_and_manifest_fail_before_child(self) -> None:
        self.source.write_text("changed after preview\n")
        with patch("asyncio.create_subprocess_exec") as child:
            with self.assertRaisesRegex(ValueError, "scope changed"):
                await run_selected_live_review(
                    self.packet, self.manifest, self.workspace
                )
            child.assert_not_called()
        controller = self.controller()
        controller.submit_review(self.packet)
        with self.assertRaisesRegex(ValueError, "scope changed"):
            await controller.step()
        self.assertEqual(controller.state.entries[0].status, "queued")
        self.source.write_text("after\n")
        assert self.selection.git_scope is not None
        self.selection.git_scope.write_bytes(canonical_bytes(self.scope) + b" ")
        with self.assertRaisesRegex(ValueError, "scope changed"):
            self.preview()

    async def test_source_changed_during_review_cannot_be_published(self) -> None:
        result = await self.result()
        controller = self.controller()

        async def changed(packet: ConversationLiveReviewPacket):
            self.source.write_text("changed during review\n")
            return result

        controller.run_live_review = changed
        controller.submit_review(self.packet)
        with self.assertRaisesRegex(ValueError, "scope changed"):
            await controller.step()
        self.assertEqual(controller.state.entries[0].status, "failed")
        self.assertIsNone(controller.state.entries[0].review_result)
        self.assertFalse(await controller.step())

    async def test_terminal_approval_and_result_reject_changed_source(self) -> None:
        preview = self.fixture.fixture.launch().preview
        output = io.StringIO()

        def check_source() -> None:
            read_review_source(
                self.selection.git_scope,
                self.scope.scope_id,
                self.workspace,
                self.scope.brief(),
            )

        async def answer(prompt: str) -> str:
            self.source.write_text("changed while inspecting phase\n")
            return "approve " + preview.sha256

        ui = TerminalReviewApproval(answer, output, check_source=check_source)
        with self.assertRaisesRegex(ValueError, "scope changed"):
            await ui.approve(preview)
        output.seek(0)
        output.truncate(0)
        retained = RetainedReviewResult(
            approval_sha256="a" * 64,
            judge_completion_sha256="b" * 64,
            judge_outcome_sha256="c" * 64,
            result=await self.result(),
        )
        with self.assertRaisesRegex(ValueError, "scope changed"):
            await ui.show_result(retained)
        self.assertEqual(output.getvalue(), "")

    async def test_child_rechecks_source_and_configuration_before_credentials(
        self,
    ) -> None:
        parser = argparse.ArgumentParser()
        review_live_cli.add_arguments(parser)
        args = parser.parse_args(self.selection.command()[4:])
        args.docker = Path("/usr/bin/false")
        before = self.fixture.base.ledger.path.read_bytes()
        for change in ("source", "configuration"):
            with (
                self.subTest(change=change),
                patch("mos_eisley.review_live_cli._campaign_charge", return_value=50),
                patch(
                    "mos_eisley.review_live_cli.BrokeredReviewConformanceProbe"
                ) as factory,
                patch("mos_eisley.review_live_cli.load_review_key") as key,
                patch(
                    "mos_eisley.review_live_cli.read_line",
                    new=AsyncMock(
                        return_value=str(self.fixture.base.root / "decision.json")
                    ),
                ),
                redirect_stdout(io.StringIO()),
            ):
                probe = factory.return_value
                probe.launch_scope.model_dump.return_value = {}

                async def change_before_use(change: str = change):
                    if change == "source":
                        self.source.write_text("changed while awaiting signatures\n")
                    else:
                        self.selection.config.write_bytes(b"changed config")
                    assert factory.call_args is not None
                    factory.call_args.kwargs["authority_policy"]()
                    raise AssertionError("stale inputs reached credential use")

                probe.run = AsyncMock(side_effect=change_before_use)
                with self.assertRaises(ValueError):
                    await asyncio.to_thread(review_live_cli.run_command, args)
                key.assert_not_called()
                self.assertFalse(self.selection.completion_output.exists())
                self.assertEqual(self.fixture.base.ledger.path.read_bytes(), before)
                self.source.write_text("after\n")
                self.selection.config.write_bytes(
                    canonical_bytes(self.fixture.configuration)
                )

    async def test_scope_budget_policy_quorum_and_workspace_rejection(self) -> None:
        foreign = self.scope.model_copy(update={"owner_uid": self.scope.owner_uid + 1})
        with self.assertRaises(ValueError):
            check_review_source(foreign, self.workspace, foreign.brief())
        with self.assertRaisesRegex(ValueError, "together"):
            read_review_source(
                self.selection.git_scope, None, self.workspace, self.scope.brief()
            )
        with self.assertRaises(ValueError):
            read_review_source(
                self.selection.git_scope,
                self.scope.scope_id,
                self.fixture.base.root,
                self.scope.brief(),
            )
        config = self.fixture.configuration.model_copy(
            update={"policy": ReviewPolicy()}
        )
        self.selection.config.write_bytes(canonical_bytes(config))
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.preview()

        # Re-selecting the changed config still cannot lower the existing quorum.
        current = self.selection.model_copy(
            update={"expected_config_sha256": digest(canonical_bytes(config))}
        )
        self.manifest.write_bytes(canonical_bytes(current))
        packet = select_live_review(self.manifest, self.workspace)
        with self.assertRaises(ValueError):
            preview_selected_live_review(packet, self.manifest, self.workspace)
        self.selection.config.write_bytes(canonical_bytes(self.fixture.configuration))
        self.manifest.write_bytes(canonical_bytes(self.selection))
        with (
            patch(
                "mos_eisley.conversation_live_review.campaign_charged_microusd",
                return_value=900,
            ),
            self.assertRaisesRegex(ValueError, "ceiling"),
        ):
            self.preview()
        self.selection.guidance_policy.write_bytes(b"changed policy")
        with self.assertRaises(ValueError):
            self.preview()

    async def test_guided_recorded_scope_keeps_source_and_prepared_brief_distinct(
        self,
    ) -> None:
        packet = ConversationReviewPacket(
            schema_version=4,
            brief=self.packet.brief,
            cassette=self.fixture.guided.cassette(),
            guidance_review=self.packet.guidance_review,
            git_scope=self.scope,
        )
        controller = self.controller()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait(self.command)
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append, packet)
        self.assertEqual(controller.state.entries[0].status, "completed")
        self.assertEqual(controller.state.entries[0].review_packet, packet)
        self.assertFalse(any(e["type"] == "conversation.review_launch" for e in events))

    async def test_scoped_packet_resume_and_cancel_do_not_restore_authority(
        self,
    ) -> None:
        for backend in (ConversationStore, SQLiteConversationStore):
            root = self.fixture.base.root / backend.__name__
            controller = self.controller()
            with backend(root, controller.state.session_id, self.workspace) as store:
                store.save(controller.state)
                controller.save = store.save
                controller.submit_review(self.packet)
            with backend(
                root, controller.state.session_id, self.workspace, create=False
            ) as store:
                restored = store.load()
                self.assertEqual(restored.entries[0].review_packet, self.packet)
                controller = ConversationController(
                    restored,
                    demo_cassette(),
                    store.save,
                    validate_review=lambda packet: None,
                )
                with self.assertRaisesRegex(ValueError, "current launch inputs"):
                    await controller.step()
                started = asyncio.Event()

                async def run(
                    packet: ConversationLiveReviewPacket,
                    started: asyncio.Event = started,
                ):
                    started.set()
                    await asyncio.Event().wait()
                    return await self.result()

                controller.run_live_review = run
                task = asyncio.create_task(controller.step())
                await started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(controller.state.entries[0].status, "cancelled")
                self.assertFalse(await controller.step())

    async def test_tui_scope_preview_and_explicit_dispatch(self) -> None:
        controller = self.controller()
        with create_pipe_input() as input:
            ui = ConversationTUI(
                controller, self.packet, input=input, output=DummyOutput()
            )
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text(self.command + "\r")
                async with asyncio.timeout(30):
                    while (
                        not controller.state.entries
                        or controller.state.entries[0].status != "completed"
                    ):
                        await asyncio.sleep(0.01)
                self.assertIn("Live review preview", ui.review_scope_preview or "")
                self.assertIn(self.scope.scope_id, ui.review_scope_preview or "")
                self.assertIn(
                    "posting are not authorized", ui.review_scope_preview or ""
                )
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)
