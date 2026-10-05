"""Integration preserves each panel's saved evidence and admission boundaries."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_conversation_diff_attachment import CapturingClient, source
from test_conversation_goal import definition
from test_conversation_loop import create

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_diff import DiffAttachment, attachment_suffix
from mos_eisley.conversation_diff_attachment import (
    select_patch_lines,
)
from mos_eisley.conversation_loop_commands import loop_command, recorded_loop_observer
from mos_eisley.conversation_schedule_driver import ActiveSessionTimers
from mos_eisley.conversation_source_attachment import attachment_fingerprint
from mos_eisley.conversation_state import LiveChatIdentity
from mos_eisley.core.agent import AgentConfig, AgentResult
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock
from mos_eisley.git_review import GitReviewSelection, GitReviewTarget


class AttachmentCompatibilityTests(IsolatedAsyncioTestCase):
    async def test_recorded_timer_host_cannot_activate_live_chat(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            identity = LiveChatIdentity(
                model="gpt-5.6-luna",
                effort="low",
                max_output_tokens=64,
                spend_policy_sha256="a" * 64,
                spend_ledger_id="b" * 64,
                artifacts_root=str(root),
            )

            async def forbidden_call(
                _config: AgentConfig, _attempt: int
            ) -> AgentResult:
                self.fail("Recorded timer host dispatched live chat")
                raise AssertionError

            cassette = demo_cassette()
            controller = ConversationController(
                ConversationController.fresh(root, cassette, live_chat=identity),
                cassette,
                lambda _: None,
                run_live_chat=forbidden_call,
                goal_clock=lambda: 100.0,
            )
            controller.create_goal(definition())
            controller.schedule_observer = recorded_loop_observer(controller)
            before = controller.state
            timers = ActiveSessionTimers(controller, lambda _: None)
            timers.open()
            try:
                self.assertFalse(timers.qualified)
                self.assertFalse(controller.schedule_timer_active)
                self.assertEqual(timers.tick(), ())
                self.assertEqual(
                    loop_command(controller, create(), lambda _: None), "rejected"
                )
                self.assertEqual(controller.state, before)
            finally:
                timers.close()

    async def test_both_formats_resume_without_reinterpreting_saved_evidence(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            snapshot, patch = source(root)
            workspace = select_patch_lines(snapshot, patch, 6, 6, visible_lines=500)
            review = DiffAttachment(
                workspace=str(root),
                path="a.txt",
                snapshot_sha256="a" * 64,
                file_sha256="b" * 64,
                basis="unstaged",
                selection=GitReviewSelection(
                    kind="uncommitted", targets=(GitReviewTarget(path="a.txt"),)
                ),
                new_start=1,
                new_end=1,
                excerpt="+after\n",
                excerpt_sha256=digest(b"+after\n"),
            )
            cassette = demo_cassette()
            controller = ConversationController(
                ConversationController.fresh(root, cassette), cassette, lambda _: None
            )
            controller.submit("Workspace source", attachments=(workspace,))
            controller.submit(
                "Review source" + attachment_suffix((review,)),
                diff_attachments=(review,),
            )
            client = CapturingClient()
            await controller.step(client)
            await controller.step(client)
            restored = ConversationState.model_validate_json(
                canonical_bytes(controller.state)
            )
            self.assertEqual(restored.entries[0].diff_attachments, (workspace,))
            self.assertEqual(restored.entries[1].diff_attachments, (review,))
            for entry in restored.entries:
                assert entry.request_admission is not None
                self.assertEqual(
                    entry.request_admission.diff_attachment_sha256,
                    attachment_fingerprint(entry.diff_attachments),
                )
            for index, attachment in enumerate((workspace, review)):
                block = client.requests[index].turns[-1].blocks[0]
                assert isinstance(block, TextBlock)
                if index == 0:
                    records: list[dict[str, object]] = json.loads(
                        block.text.rsplit("\n", 1)[-1]
                    )
                    self.assertEqual(records[0]["excerpt"], attachment.excerpt)
                else:
                    record: dict[str, object] = json.loads(
                        block.text.rsplit("\n", 1)[-1]
                    )
                    self.assertEqual(record["excerpt"], attachment.excerpt)

            legacy = restored.model_dump(mode="json")
            admission = legacy["entries"][1]["request_admission"]
            admission["schema_version"] = 5
            admission.pop("diff_attachment_sha256")
            self.assertEqual(
                ConversationState.model_validate_json(json.dumps(legacy))
                .entries[1]
                .diff_attachments,
                (review,),
            )
            # Legacy workspace excerpts never lose their schema-7 binding.
            legacy["entries"][0]["request_admission"]["schema_version"] = 5
            legacy["entries"][0]["request_admission"].pop("diff_attachment_sha256")
            with self.assertRaisesRegex(ValueError, "diff attachments"):
                ConversationState.model_validate_json(json.dumps(legacy))

            with self.assertRaisesRegex(ValueError, "separate message"):
                controller.submit("Mixed sources", diff_attachments=(workspace, review))
            self.assertEqual(len(controller.state.entries), 2)
