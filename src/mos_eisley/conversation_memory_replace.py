"""Reviewed replacement of one exact memory span with explicitly supplied text."""

import json
import re
from dataclasses import dataclass
from typing import cast

from mos_eisley.conversation_memory import (
    MEMORY_BYTES,
    MemorySnapshot,
    MemoryStore,
    Scope,
)
from mos_eisley.conversation_memory_forget import ForgetPreview, MemoryForget


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not allowed.")
        result[key] = value
    return result


def replacement_text(payload: str) -> tuple[str, str]:
    try:
        data: object = json.loads(payload, object_pairs_hook=unique_object)
        if not isinstance(data, dict):
            raise ValueError("Expected an object.")
        values = cast(dict[str, object], data)
        if set(values) != {"old", "new"}:
            raise ValueError("Expected old and new only.")
        old, new = values["old"], values["new"]
        if not isinstance(old, str) or not isinstance(new, str):
            raise ValueError("Expected strings.")
        if not old.strip() or not new.strip() or old == new:
            raise ValueError("Expected distinct nonempty text.")
        old.encode("utf-8")
        new.encode("utf-8")
    except (ValueError, RecursionError):
        raise ValueError(
            'Replacement requires JSON with exactly "old" and "new" strings. '
            "Use distinct, nonempty UTF-8 text; use forget for deletion."
        ) from None
    return old, new


@dataclass(frozen=True)
class ReplacePreview(ForgetPreview):
    replacement: str

    def material(self) -> dict[str, object]:
        return {
            **super().material(),
            "operation": "replace_exact_text",
            "replacement_text": self.replacement,
        }

    def receipt(self) -> dict[str, object]:
        return {
            "type": "conversation.memory.replace.preview",
            **self.material(),
            "preview_sha256": self.sha256,
            "text": (
                f"Review replacing exact text in {self.scope} memory at {self.path}. "
                "Nothing has been changed. Queued work is paused.\n"
                f"Old text:\n{self.removed}\nNew text:\n{self.replacement}\n"
                f"Complete resulting text:\n{self.after_text}\n"
                f"Apply with /memory apply-replace {self.sha256}\n"
                "Or /memory discard-replace. This preview lasts only in this session."
            ),
        }

    def saved_receipt(self, saved: MemorySnapshot) -> dict[str, object]:
        return {
            "type": "conversation.memory.replace.saved",
            "scope": self.scope,
            "path": self.path,
            "preview_sha256": self.sha256,
            "removed_text": self.removed,
            "replacement_text": self.replacement,
            "document": saved.model_dump(mode="json"),
            "text": (
                f"Replaced exact text in {self.scope} memory at {self.path}. "
                f"Revision {saved.document.revision}, SHA-256 {saved.sha256}.\n"
                f"Old text:\n{self.removed}\nNew text:\n{self.replacement}\n"
                "Session memory is unchanged; use /memory refresh, then /continue. "
                "Earlier sessions and backups are not rewritten."
            ),
        }


class MemoryReplace(MemoryForget):
    def __init__(self, store: MemoryStore) -> None:
        super().__init__(store, action="replace")

    def command(self, line: str) -> dict[str, object] | None:
        parts = line.split(maxsplit=2)
        if len(parts) < 2 or parts[0] != "/memory":
            return None
        action = parts[1]
        if action not in {"replace", "apply-replace", "discard-replace"}:
            return None
        if action == "replace":
            self.pending = None
        if len(line) > 8000 or any(char in line for char in "\r\n\x00"):
            raise ValueError(
                "Replacement commands require one line within 8,000 characters."
            )
        if action == "discard-replace":
            if len(parts) != 2:
                raise ValueError("Use /memory discard-replace without arguments.")
            self.pending = None
            return {
                "type": "conversation.memory.replace.discarded",
                "text": (
                    "Replacement preview discarded. No saved memory changed. "
                    "Work is paused."
                ),
            }
        if action == "apply-replace":
            if len(parts) != 3 or re.fullmatch(r"[0-9a-f]{64}", parts[2]) is None:
                raise ValueError("Use /memory apply-replace PREVIEW_SHA256.")
            return self.apply(parts[2])
        args = parts[2].split(maxsplit=1) if len(parts) == 3 else []
        if len(args) != 2 or args[0] not in {"user", "project"}:
            raise ValueError(
                'Use /memory replace user|project {"old":"TEXT","new":"TEXT"}.'
            )
        scope: Scope = "user" if args[0] == "user" else "project"
        old, new = replacement_text(args[1])
        before = self.preview(scope, old)
        after = (
            before.after_text[: before.start] + new + before.after_text[before.start :]
        )
        if len(after.encode("utf-8")) > MEMORY_BYTES:
            raise ValueError("Replacement would exceed 32 KiB. No preview created.")
        self.pending = ReplacePreview(
            before.review_id,
            scope,
            before.path,
            before.workspace,
            before.before,
            old,
            before.start,
            after,
            new,
        )
        return self.pending.receipt()
