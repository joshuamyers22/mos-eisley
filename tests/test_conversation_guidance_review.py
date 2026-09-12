"""Guided review queue admission, terminal execution and historical retention."""

import argparse
import asyncio
import json
import subprocess
import sys
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import test_project_guidance_review as guidance_fixture
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_directory import DirectorySelection
from mos_eisley.conversation_guidance_review import review_guidance_validator
from mos_eisley.conversation_review import (
    ConversationReviewPacket,
    run_conversation_review,
)
from mos_eisley.conversation_state import WorkingConversationState
from mos_eisley.conversation_switch import fresh_directory_arguments
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import Brief, canonical_bytes
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.run.conversation_artifacts import read_sqlite_artifact
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.conversation_transcript import read_sqlite_transcript


class TerminalGuidanceTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.fixture = guidance_fixture.GuidedReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.fixture.base
        self.workspace = self.fixture.fixture.workspace
        self.packet = ConversationReviewPacket(
            schema_version=2,
            brief=self.fixture.prepared.brief,
            cassette=self.fixture.cassette(),
            guidance_review=self.fixture.prepared,
        )
        self.validator = review_guidance_validator(
            self.workspace,
            self.fixture.fixture.storage,
            self.fixture.fixture.policy_path,
            self.fixture.policy_sha,
        )
        assert self.validator is not None

    def controller(self, *, validated: bool = True) -> ConversationController:
        cassette = demo_cassette()
        return ConversationController(
            ConversationController.fresh(self.workspace, cassette),
            cassette,
            lambda state: None,
            validate_review=self.validator if validated else None,
        )

    async def test_validated_review_retains_guidance_without_chat_consumption(
        self,
    ) -> None:
        controller = self.controller()
        controller.submit_review(self.packet)
        self.assertTrue(await controller.step())
        entry = controller.state.entries[0]
        self.assertEqual(entry.status, "completed")
        self.assertEqual(entry.review_packet, self.packet)
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertIsNone(entry.memory_context)
        self.assertIsNone(entry.request_admission)
        self.assertNotIn("PRIVATE-POLICY-PROSE-CANARY", canonical_bytes(entry).decode())

    async def test_guided_execution_and_queueing_require_explicit_current_validator(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            await run_conversation_review(self.packet)
        controller = self.controller(validated=False)
        with self.assertRaises(ValueError):
            controller.submit_review(self.packet)
        self.assertEqual(controller.state.entries, ())

    async def test_changed_guidance_after_queue_stays_queued_without_execution(
        self,
    ) -> None:
        controller = self.controller()
        controller.submit_review(self.packet)
        self.fixture.fixture.fixture.accept(clear=True)
        with (
            patch("mos_eisley.conversation.run_conversation_review") as run,
            self.assertRaises(ValueError),
        ):
            await controller.step()
        run.assert_not_called()
        self.assertEqual(controller.state.entries[0].status, "queued")

    async def test_resume_needs_launch_policy_and_never_uses_saved_policy_path(
        self,
    ) -> None:
        controller = self.controller()
        controller.submit_review(self.packet)
        saved = ConversationState.model_validate_json(
            controller.state.model_dump_json()
        )
        resumed = ConversationController(saved, demo_cassette(), lambda state: None)
        self.assertEqual(resumed.state.entries[0].status, "queued")
        with self.assertRaises(ValueError):
            await resumed.step()
        resumed.validate_review = self.validator
        await resumed.step()
        self.assertEqual(resumed.state.entries[0].status, "completed")
        self.assertNotIn(
            str(self.fixture.fixture.policy_path),
            canonical_bytes(resumed.state).decode(),
        )

    async def test_policy_change_during_recorded_execution_discards_result(
        self,
    ) -> None:
        controller = self.controller()
        controller.submit_review(self.packet)
        from mos_eisley.review.pipeline import review

        async def changed(*args: object, **kwargs: object):
            result = await review(
                self.packet.brief,
                tuple(item.critic for item in self.packet.cassette.critics),
                RecordedReviewer(self.packet.cassette),
                self.packet.policy,
            )
            self.fixture.fixture.policy_path.write_text(
                self.fixture.fixture.policy_path.read_text() + " "
            )
            return result

        with (
            patch("mos_eisley.conversation_review.review", side_effect=changed),
            self.assertRaises(ValueError),
        ):
            await controller.step()
        self.assertEqual(controller.state.entries[0].status, "failed")
        self.assertIsNone(controller.state.entries[0].review_result)

    async def test_foreign_project_rejects_even_if_callback_is_permissive(self) -> None:
        other = self.base / "other"
        other.mkdir()
        cassette = demo_cassette()
        controller = ConversationController(
            ConversationController.fresh(other, cassette),
            cassette,
            lambda state: None,
            validate_review=lambda packet: None,
        )
        with self.assertRaises(ValueError):
            controller.submit_review(self.packet)

    async def test_plain_terminal_rejects_stale_packet_without_queueing(self) -> None:
        controller = self.controller()
        self.fixture.fixture.fixture.accept(clear=True)
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/review")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append, self.packet)
        self.assertEqual(controller.state.entries, ())
        self.assertTrue(
            any(event["type"] == "conversation.unavailable" for event in events)
        )

    async def test_full_screen_terminal_runs_same_guided_review(self) -> None:
        controller = self.controller()
        with create_pipe_input() as input:
            ui = ConversationTUI(
                controller, self.packet, input=input, output=DummyOutput()
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
                self.assertEqual(controller.state.entries[0].review_packet, self.packet)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)

    async def test_snapshot_and_sqlite_retain_packet_for_historical_inspection(
        self,
    ) -> None:
        for kind in (ConversationStore, SQLiteConversationStore):
            controller = self.controller()
            root = self.base / kind.__name__
            with kind(root, controller.state.session_id, self.workspace) as store:
                store.save(controller.state)
                controller.save = store.save
                controller.submit_review(self.packet)
                await controller.step()
                self.assertEqual(store.load().entries[0].review_packet, self.packet)
        self.fixture.fixture.policy_path.unlink()
        page = read_sqlite_transcript(
            self.base / "SQLiteConversationStore",
            controller.state.session_id,
            self.workspace,
        )
        selection = next(
            ref.selection
            for entry in page.entries
            for ref in entry.artifacts
            if ref.field == "review_packet"
        )
        assert selection is not None
        content = read_sqlite_artifact(
            self.base / "SQLiteConversationStore", self.workspace, selection
        )
        self.assertEqual(content.content, self.packet.model_dump(mode="json"))

    async def test_sqlite_queued_resume_rechecks_guidance_after_loading_artifact(
        self,
    ) -> None:
        controller = self.controller()
        root = self.base / "queued-sqlite"
        with SQLiteConversationStore(
            root, controller.state.session_id, self.workspace
        ) as store:
            store.save(controller.state)
            controller.save = store.save
            controller.submit_review(self.packet)
        with SQLiteConversationStore(
            root, controller.state.session_id, self.workspace, create=False
        ) as store:
            working = store.load_working()
            assert isinstance(working, WorkingConversationState)
            resumed = ConversationController[WorkingConversationState](
                working,
                demo_cassette(),
                store.save_working,
                load_entry=store.load_working_entry,
            )
            with self.assertRaises(ValueError):
                await resumed.step()
            self.assertEqual(resumed.state.entries[0].status, "queued")
            resumed.validate_review = self.validator
            await resumed.step()
            self.assertEqual(resumed.state.entries[0].status, "completed")

    async def test_legacy_packet_canonical_bytes_and_schema_rules(self) -> None:
        brief, cassette = demo_inputs()
        legacy = ConversationReviewPacket(brief=brief, cassette=cassette)
        self.assertNotIn("guidance_review", legacy.model_dump(mode="json"))
        await run_conversation_review(legacy)
        for data in (
            {**self.packet.model_dump(mode="json"), "schema_version": 1},
            {**legacy.model_dump(mode="json"), "schema_version": 2},
            {
                **self.packet.model_dump(mode="json"),
                "brief": brief.model_dump(mode="json"),
            },
        ):
            with self.assertRaises(ValueError):
                ConversationReviewPacket.model_validate_json(json.dumps(data))

    async def test_whole_terminal_packet_budget_still_applies(self) -> None:
        prepared = self.fixture.prepare(Brief(spec="s" * 50000, diff="d" * 30000))
        with self.assertRaisesRegex(ValueError, "packet exceeds"):
            ConversationReviewPacket(
                schema_version=2,
                brief=prepared.brief,
                cassette=self.fixture.cassette(prepared.brief),
                guidance_review=prepared,
            )

    async def test_policy_pair_and_directory_handoff_are_explicit(self) -> None:
        with self.assertRaises(ValueError):
            review_guidance_validator(
                self.workspace,
                self.fixture.fixture.storage,
                self.fixture.fixture.policy_path,
                None,
            )
        previous = argparse.Namespace(
            review_guidance_policy=self.fixture.fixture.policy_path,
            expected_review_policy_sha256=self.fixture.policy_sha,
        )
        fresh = fresh_directory_arguments(
            previous, DirectorySelection.inspect(self.workspace)
        )
        self.assertIsNone(fresh.review_guidance_policy)
        self.assertIsNone(fresh.expected_review_policy_sha256)

    def cli(self, *args: str, input: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                *args,
                "-C",
                str(self.workspace),
                "--storage",
                str(self.base / "sessions"),
                "--memory-storage",
                str(self.base / "memory"),
                "--no-memory",
                "--json",
            ],
            input=input,
            cwd=self.base,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    async def test_cli_packet_export_and_terminal_review(self) -> None:
        prepared = self.base / "prepared.json"
        prepared.write_bytes(canonical_bytes(self.fixture.prepared))
        cassette = self.base / "cassette.json"
        cassette.write_bytes(canonical_bytes(self.fixture.cassette()))
        exported = self.fixture.cli(
            "packet",
            "--prepared",
            str(prepared),
            "--expected-prepared-sha256",
            self.fixture.prepared.sha256,
            "--cassette",
            str(cassette),
        )
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertEqual(
            ConversationReviewPacket.model_validate_json(exported.stdout), self.packet
        )
        packet = self.base / "packet.json"
        packet.write_text(exported.stdout)
        args = (
            "chat",
            "--review-packet",
            str(packet),
            "--review-guidance-policy",
            str(self.fixture.fixture.policy_path),
            "--expected-review-policy-sha256",
            self.fixture.policy_sha,
            "--review-guidance-storage",
            str(self.fixture.fixture.storage),
        )
        result = self.cli(*args, input="/review\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(any("review_result" in event for event in events))
        session_id = events[-1]["session_id"]
        self.fixture.fixture.policy_path.unlink()
        resumed = self.cli("resume", session_id)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)

    async def test_cli_guided_packet_requires_current_policy_selection(self) -> None:
        packet = self.base / "packet.json"
        packet.write_bytes(canonical_bytes(self.packet))
        result = self.cli("chat", "--review-packet", str(packet), input="/review\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PRIVATE-POLICY-PROSE-CANARY", result.stdout + result.stderr)
        self.assertFalse((self.base / "sessions").exists())


if __name__ == "__main__":
    import unittest

    unittest.main()
