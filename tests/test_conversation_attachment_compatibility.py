"""Integration preserves each panel's saved evidence and admission boundaries."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_conversation_diff_attachment import CapturingClient, source

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_diff import DiffAttachment, attachment_suffix
from mos_eisley.conversation_diff_attachment import (
    DiffAttachmentError,
    select_patch_lines,
)
from mos_eisley.conversation_source_attachment import attachment_fingerprint
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock
from mos_eisley.git_review import GitReviewSelection, GitReviewTarget


class AttachmentCompatibilityTests(IsolatedAsyncioTestCase):
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
                envelope = json.loads(block.text.rsplit("\n", 1)[-1])
                record = envelope[0] if isinstance(envelope, list) else envelope
                self.assertEqual(record["excerpt"], attachment.excerpt)

            legacy = restored.model_dump(mode="json")
            admission = legacy["entries"][1]["request_admission"]
            admission["schema_version"] = 6
            admission.pop("diff_attachment_sha256")
            self.assertEqual(
                ConversationState.model_validate_json(json.dumps(legacy)).entries[1].diff_attachments,
                (review,),
            )
            # Legacy workspace excerpts never lose their schema-7 binding.
            legacy["entries"][0]["request_admission"]["schema_version"] = 6
            legacy["entries"][0]["request_admission"].pop("diff_attachment_sha256")
            with self.assertRaisesRegex(ValueError, "diff attachments"):
                ConversationState.model_validate_json(json.dumps(legacy))

            with self.assertRaises(DiffAttachmentError):
                controller.submit("Mixed sources", diff_attachments=(workspace, review))
            self.assertEqual(len(controller.state.entries), 2)
