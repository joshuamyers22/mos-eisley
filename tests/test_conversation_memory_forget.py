"""Reviewed exact-span deletion rejects stale and ambiguous memory edits."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_forget import MemoryForget


class ForgetTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = MemoryStore(self.root / "memory", self.root)
        self.forget = MemoryForget(self.store)

    def preview(self, text: str, scope: str = "project") -> str:
        result = self.forget.command(f"/memory forget {scope} {text}")
        assert result is not None
        return str(result["preview_sha256"])

    def test_preview_is_read_only_and_apply_preserves_all_other_text_and_scope(
        self,
    ) -> None:
        original = "First.\n\nRemove café — exactly.\n\nLast."
        self.store.change("project", "set", text=original)
        self.store.change("user", "set", text="untouched")
        before = self.store.path("project").read_bytes()
        user = self.store.path("user").read_bytes()
        token = self.preview("Remove café — exactly.")
        self.assertEqual(self.store.path("project").read_bytes(), before)
        assert self.forget.pending is not None
        self.assertEqual(self.forget.pending.after_text, "First.\n\n\n\nLast.")
        result = self.forget.command("/memory apply-forget " + token)
        self.assertIsNotNone(result)
        saved = self.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "First.\n\n\n\nLast.")
        self.assertEqual(saved.document.revision, 2)
        self.assertEqual(self.store.path("user").read_bytes(), user)
        self.assertIsNone(self.forget.pending)
        with self.assertRaisesRegex(ValueError, "No forget preview"):
            self.forget.apply(token)

    def test_missing_ambiguous_overlapping_and_invalid_requests_do_not_write(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.preview("missing")
        self.assertFalse(self.store.root.exists())
        self.store.change("project", "set", text="aaaa duplicate duplicate")
        before = self.store.path("project").read_bytes()
        for text in ("aa", "duplicate", "MISSING"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.preview(text)
        for command in (
            "/memory forget",
            "/memory forget all duplicate",
            "/memory forget project ",
            "/memory forget project a\nb",
            "/memory forget project \x00",
            "/memory forget project " + "x" * 8000,
            "/memory apply-forget wrong",
            "/memory discard-forget extra",
        ):
            with self.subTest(command=command[:50]), self.assertRaises(ValueError):
                self.forget.command(command)
        self.assertEqual(self.store.path("project").read_bytes(), before)

    def test_disabled_document_stays_disabled_and_whole_text_can_be_removed(
        self,
    ) -> None:
        self.store.change("project", "set", text="remove all")
        self.store.change("project", "disable")
        token = self.preview("remove all")
        self.forget.apply(token)
        saved = self.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "")
        self.assertFalse(saved.document.enabled)
        self.assertEqual(saved.document.revision, 3)

    def test_stale_edit_disable_and_clear_invalidate_apply(self) -> None:
        for action in ("append", "disable", "clear"):
            with self.subTest(action=action):
                self.store.change("project", "set", text="unique target")
                token = self.preview("target")
                self.store.change("project", action, text="concurrent")
                before = self.store.path("project").read_bytes()
                with self.assertRaisesRegex(ValueError, "fresh preview"):
                    self.forget.apply(token)
                self.assertEqual(self.store.path("project").read_bytes(), before)
                self.assertIsNone(self.forget.pending)

    def test_tokens_are_bound_to_review_and_cannot_cross_sessions_or_replay(
        self,
    ) -> None:
        self.store.change("project", "set", text="target")
        first = self.preview("target")
        second = self.preview("target")
        self.assertNotEqual(first, second)
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.forget.apply(first)
        self.assertIsNotNone(self.forget.pending)
        with self.assertRaisesRegex(ValueError, "No forget preview"):
            MemoryForget(self.store).apply(second)
        self.forget.command("/memory discard-forget")
        with self.assertRaisesRegex(ValueError, "No forget preview"):
            self.forget.apply(second)
        self.preview("target")
        with self.assertRaises(ValueError):
            self.preview("not found")
        self.assertIsNone(self.forget.pending)

    def test_store_retarget_and_unsafe_or_corrupt_current_reject_apply(self) -> None:
        self.store.change("project", "set", text="target")
        token = self.preview("target")
        other = self.root / "other"
        other.mkdir()
        self.forget.store = MemoryStore(self.store.root, other)
        with self.assertRaisesRegex(ValueError, "target changed"):
            self.forget.apply(token)
        self.forget.store = self.store
        for replacement in ("public", "corrupt", "symlink"):
            with self.subTest(replacement=replacement):
                path = self.store.path("project")
                if path.exists() or path.is_symlink():
                    path.unlink()
                self.store.change("project", "set", text="target")
                token = self.preview("target")
                victim = self.root / "victim"
                victim.write_text("private victim")
                if replacement == "public":
                    path.chmod(0o644)
                elif replacement == "corrupt":
                    path.write_text("PRIVATE INVALID CANARY")
                else:
                    path.unlink()
                    path.symlink_to(victim)
                with self.assertRaises(ValueError) as raised:
                    self.forget.apply(token)
                self.assertNotIn("CANARY", str(raised.exception))
                self.assertEqual(victim.read_text(), "private victim")

    def test_compare_and_swap_catches_write_after_preview_without_lost_update(
        self,
    ) -> None:
        self.store.change("project", "set", text="target old")
        token = self.preview("target")
        original = self.store.change

        def concurrent(*args: object, **kwargs: object):
            original("project", "append", text="new preference")
            return original(
                "project",
                "set",
                text="old",
                expected_sha256=str(kwargs["expected_sha256"]),
            )

        with (
            patch.object(self.store, "change", side_effect=concurrent),
            self.assertRaises(ValueError),
        ):
            self.forget.apply(token)
        saved = self.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "target old\n\nnew preference")

    def test_failed_directory_flush_reports_possible_publication_and_consumes_preview(
        self,
    ) -> None:
        self.store.change("project", "set", text="remove target")
        token = self.preview("remove ")
        original = os.fsync
        calls = 0

        def fail(fd: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("directory flush")
            original(fd)

        with (
            patch("mos_eisley.conversation_memory.os.fsync", side_effect=fail),
            self.assertRaisesRegex(ValueError, "may already have been published"),
        ):
            self.forget.apply(token)
        saved = self.store.read("project")
        assert saved is not None
        self.assertEqual(saved.document.text, "target")
        self.assertIsNone(self.forget.pending)
