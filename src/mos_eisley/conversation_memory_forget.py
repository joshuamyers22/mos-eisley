"""Session-local reviewed removal of one unique, explicitly supplied text span."""

import json
import re
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from mos_eisley.conversation_memory import MemorySnapshot, MemoryStore, Scope
from mos_eisley.core.models import digest


@dataclass(frozen=True)
class ForgetPreview:
    review_id: str
    scope: Scope
    path: str
    workspace: str
    before: MemorySnapshot
    removed: str
    start: int
    after_text: str

    def material(self) -> dict[str, object]:
        return {
            "operation": "forget_exact_text",
            "review_id": self.review_id,
            "scope": self.scope,
            "path": self.path,
            "workspace": self.workspace,
            "before": self.before.model_dump(mode="json"),
            "removed_text": self.removed,
            "character_start": self.start,
            "character_end": self.start + len(self.removed),
            "after_text": self.after_text,
        }

    @property
    def sha256(self) -> str:
        return digest(
            json.dumps(
                self.material(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )

    def receipt(self) -> dict[str, object]:
        return {
            "type": "conversation.memory.forget.preview",
            **self.material(),
            "preview_sha256": self.sha256,
            "text": (
                f"Review forgetting exact text from {self.scope} memory "
                f"at {self.path}. "
                "Nothing has been changed. Queued work is paused.\n"
                f"Text to remove:\n{self.removed}\n"
                f"Complete resulting text:\n{self.after_text}\n"
                f"Apply with /memory apply-forget {self.sha256}\n"
                "Or /memory discard-forget. This preview lasts only in this session."
            ),
        }

    def saved_receipt(self, saved: MemorySnapshot) -> dict[str, object]:
        return {
            "type": "conversation.memory.forget.saved",
            "scope": self.scope,
            "path": self.path,
            "preview_sha256": self.sha256,
            "removed_text": self.removed,
            "document": saved.model_dump(mode="json"),
            "text": (
                f"Removed exact text from {self.scope} memory at {self.path}. "
                f"Revision {saved.document.revision}, SHA-256 {saved.sha256}.\n"
                f"Removed text:\n{self.removed}\n"
                "Session memory is unchanged; use /memory refresh, then /continue. "
                "Earlier sessions and backups are not erased."
            ),
        }


class MemoryForget:
    def __init__(
        self, store: MemoryStore, *, action: Literal["forget", "replace"] = "forget"
    ) -> None:
        self.store = store
        self.action = action
        self.pending: ForgetPreview | None = None

    def command(self, line: str) -> dict[str, object] | None:
        parts = line.split(maxsplit=2)
        if len(parts) < 2 or parts[0] != "/memory":
            return None
        action = parts[1]
        if action not in {"forget", "apply-forget", "discard-forget"}:
            return None
        if action == "forget":
            # An unsuccessful new preview cannot leave an older one selected.
            self.pending = None
        if len(line) > 8000 or any(char in line for char in "\r\n\x00"):
            raise ValueError(
                "Forget commands require one line within 8,000 characters."
            )
        if action == "discard-forget":
            if len(parts) != 2:
                raise ValueError("Use /memory discard-forget without arguments.")
            self.pending = None
            return {
                "type": "conversation.memory.forget.discarded",
                "text": (
                    "Forget preview discarded. No saved memory changed. Work is paused."
                ),
            }
        if action == "apply-forget":
            if len(parts) != 3 or re.fullmatch(r"[0-9a-f]{64}", parts[2]) is None:
                raise ValueError("Use /memory apply-forget PREVIEW_SHA256.")
            return self.apply(parts[2])
        args = parts[2].split(maxsplit=1) if len(parts) == 3 else []
        if len(args) != 2 or args[0] not in {"user", "project"} or not args[1].strip():
            raise ValueError("Use /memory forget user|project EXACT_TEXT.")
        scope: Scope = "user" if args[0] == "user" else "project"
        self.pending = self.preview(scope, args[1])
        return self.pending.receipt()

    def preview(self, scope: Scope, text: str) -> ForgetPreview:
        try:
            before = self.store.read(scope)
        except (OSError, ValueError):
            raise ValueError(
                "Saved memory could not be inspected. No preview created."
            ) from None
        if before is None:
            raise ValueError(
                "No saved document exists in that scope. Nothing was changed."
            )
        start = before.document.text.find(text)
        if start < 0:
            raise ValueError("Exact text was not found. Nothing was changed.")
        if before.document.text.find(text, start + 1) >= 0:
            raise ValueError("Text matches more than once. Supply a unique exact span.")
        return ForgetPreview(
            uuid4().hex,
            scope,
            str(self.store.path(scope)),
            self.store.workspace,
            before,
            text,
            start,
            before.document.text[:start] + before.document.text[start + len(text) :],
        )

    def apply(self, expected_sha256: str) -> dict[str, object]:
        preview = self.pending
        if preview is None:
            raise ValueError(
                f"No {self.action} preview in this session. Create a fresh preview."
            )
        if expected_sha256 != preview.sha256:
            raise ValueError(
                f"{self.action.capitalize()} preview hash does not match. "
                "Review the current preview."
            )
        self.pending = None
        if (
            self.store.workspace != preview.workspace
            or str(self.store.path(preview.scope)) != preview.path
        ):
            raise ValueError(
                f"Memory target changed. Create a fresh {self.action} preview."
            )
        try:
            saved = self.store.change(
                preview.scope,
                "set",
                text=preview.after_text,
                expected_sha256=preview.before.sha256,
            )
        except (OSError, ValueError):
            raise ValueError(
                f"{self.action.capitalize()} could not be completed. "
                "Inspect current memory before creating "
                "a fresh preview; a failed write may already have been published. "
                "The session selection is unchanged."
            ) from None
        return preview.saved_receipt(saved)
