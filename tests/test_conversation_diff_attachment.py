"""Frozen diff lines stay bounded, untrusted, and bound to admitted requests."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_diff_attachment import (
    DiffAttachment,
    DiffAttachmentError,
    attached_prompt,
    attachment_fingerprint,
    select_patch_lines,
)
from mos_eisley.conversation_git import DiffBasis, GitSnapshot, GitState, Patch
from mos_eisley.conversation_pending import PendingTextBudgetError, PendingTextLimits
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse


class CapturingClient:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        response = demo_cassette().exchanges[0].response
        assert response is not None
        return response


PATCH = (
    b"diff --git a/a.txt b/a.txt\n"
    b"index 1111111..2222222 100644\n"
    b"--- a/a.txt\n"
    b"+++ b/a.txt\n"
    b"@@ -1,2 +1,2 @@\n"
    b"-before\n"
    b"+after\n"
    b" context\n"
)


def source(root: Path, data: bytes = PATCH) -> tuple[GitSnapshot, Patch]:
    sha = "a" * 64
    return (
        GitSnapshot(GitState.READY, root.resolve(), root.resolve(), (), sha, True),
        Patch("a.txt", DiffBasis.UNSTAGED, sha, data, digest(data)),
    )


class DiffAttachmentTests(TestCase):
    def test_freezes_exact_lines_and_coordinates(self) -> None:
        snapshot, patch = source(Path("/tmp/workspace"))
        attachment = select_patch_lines(snapshot, patch, 5, 6, visible_lines=500)
        self.assertEqual(attachment.excerpt, "-before\n+after\n")
        self.assertEqual((attachment.old_start, attachment.old_end), (1, 1))
        self.assertEqual((attachment.new_start, attachment.new_end), (1, 1))
        self.assertEqual(attachment.snapshot_digest, snapshot.digest)
        self.assertEqual(attachment.patch_digest, patch.digest)
        self.assertEqual(attachment.excerpt_digest, digest(attachment.excerpt.encode()))
        addition = select_patch_lines(snapshot, patch, 6, 6, visible_lines=500)
        self.assertIsNone(addition.old_start)
        self.assertEqual((addition.new_start, addition.new_end), (1, 1))

    def test_rejects_headers_stale_patches_invalid_text_and_limits(self) -> None:
        snapshot, patch = source(Path("/tmp/workspace"))
        for first, last in ((0, 0), (4, 6), (6, 8), (5, 45)):
            with (
                self.subTest(first=first, last=last),
                self.assertRaises(DiffAttachmentError),
            ):
                select_patch_lines(snapshot, patch, first, last, visible_lines=8)
        with self.assertRaisesRegex(DiffAttachmentError, "changed"):
            select_patch_lines(
                replace(snapshot, digest="b" * 64),
                patch,
                6,
                6,
                visible_lines=500,
            )
        invalid_data = PATCH.replace(b"after", b"\xff")
        invalid = replace(patch, data=invalid_data, digest=digest(invalid_data))
        with self.assertRaisesRegex(DiffAttachmentError, "UTF-8"):
            select_patch_lines(snapshot, invalid, 6, 6, visible_lines=500)
        large_data = PATCH.replace(b"after", b"a" * 2100)
        large = replace(patch, data=large_data, digest=digest(large_data))
        with self.assertRaisesRegex(DiffAttachmentError, "2,048-byte"):
            select_patch_lines(snapshot, large, 6, 6, visible_lines=500)

    def test_prompt_is_bounded_and_provenance_cannot_be_mutated(self) -> None:
        plain = 'é\n"\\' * 1000
        self.assertEqual(attached_prompt(plain, ()), plain)
        snapshot, patch = source(Path("/tmp/workspace"))
        attachment = select_patch_lines(snapshot, patch, 6, 6, visible_lines=500)
        prompt = attached_prompt("Explain this change", (attachment,))
        self.assertIn("Untrusted diff excerpts", prompt)
        self.assertIn('"excerpt":"+after\\n"', prompt)
        self.assertEqual(
            attachment_fingerprint((attachment,)),
            digest(prompt.removeprefix("Explain this change").encode()),
        )
        with self.assertRaisesRegex(ValueError, "frozen"):
            DiffAttachment.model_validate(
                {**attachment.model_dump(), "excerpt": "+different\n"}
            )
        with self.assertRaises(DiffAttachmentError):
            attached_prompt("x" * 7900, (attachment,))

    def test_no_newline_marker_does_not_hide_following_added_line(self) -> None:
        data = PATCH.replace(
            b"-before\n+after\n",
            b"-before\n\\ No newline at end of file\n+after\n",
        )
        snapshot, patch = source(Path("/tmp/workspace"), data)
        selected = select_patch_lines(snapshot, patch, 7, 7, visible_lines=500)
        self.assertEqual(selected.excerpt, "+after\n")
        self.assertEqual(selected.new_start, 1)


class DiffAdmissionTests(IsolatedAsyncioTestCase):
    async def test_request_admission_retains_attachment_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, patch = source(root)
            attachment = select_patch_lines(snapshot, patch, 5, 6, visible_lines=500)
            cassette = demo_cassette()
            saved: list[ConversationState] = []
            controller = ConversationController(
                ConversationController.fresh(root, cassette), cassette, saved.append
            )
            controller.submit("Explain this change", attachments=(attachment,))
            client = CapturingClient()
            await controller.step(client)
            entry = controller.state.entries[0]
            admission = entry.request_admission
            assert admission is not None
            self.assertEqual(entry.diff_attachments, (attachment,))
            self.assertEqual(admission.schema_version, 7)
            self.assertEqual(
                admission.diff_attachment_sha256,
                attachment_fingerprint((attachment,)),
            )
            self.assertIn("Untrusted diff excerpts", entry.text)
            self.assertIn("Untrusted diff excerpts", str(client.requests[0]))
            self.assertEqual(
                ConversationState.model_validate_json(canonical_bytes(controller.state))
                .entries[0]
                .diff_attachments,
                (attachment,),
            )
            self.assertTrue(
                any(state.entries[0].status == "running" for state in saved)
            )

    async def test_pending_budget_counts_attached_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, patch = source(root)
            attachment = select_patch_lines(snapshot, patch, 6, 6, visible_lines=500)
            cassette = demo_cassette()
            controller = ConversationController(
                ConversationController.fresh(root, cassette),
                cassette,
                lambda _: None,
                pending_limits=PendingTextLimits(max_bytes=4000),
            )
            controller.submit("x" * 3800)
            with self.assertRaises(PendingTextBudgetError):
                controller.submit("Explain", attachments=(attachment,))
            self.assertEqual(len(controller.state.entries), 1)
            self.assertEqual(controller.pending_text_bytes, 3800)
