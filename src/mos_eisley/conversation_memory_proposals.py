"""User-selected assistant proposals remain inert until a reviewed scoped apply."""

import json
import re
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_memory import (
    MEMORY_BYTES,
    MemorySnapshot,
    MemoryStore,
    Scope,
)
from mos_eisley.conversation_memory_replace import replacement_text, unique_object
from mos_eisley.core.models import digest


def fingerprint(value: object) -> str:
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def proposal(answer: str) -> dict[str, str]:
    try:
        if len(answer) > 8000:
            raise ValueError("Oversized proposal.")
        value: object = json.loads(answer, object_pairs_hook=unique_object)
        if not isinstance(value, dict):
            raise ValueError("Expected an object.")
        fields = cast(dict[str, object], value)
        action = fields.get("operation")
        keys = {
            "append": {"operation", "text"},
            "replace": {"operation", "old", "new"},
            "forget": {"operation", "old"},
        }
        if (
            not isinstance(action, str)
            or action not in keys
            or set(fields) != keys[action]
        ):
            raise ValueError("Unknown proposal fields.")
        for text in fields.values():
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Expected nonempty text.")
            text.encode("utf-8")
        result = cast(dict[str, str], fields)
        if action == "replace":
            replacement_text(json.dumps({"old": result["old"], "new": result["new"]}))
        return result
    except (ValueError, RecursionError):
        raise ValueError(
            "Select a completed assistant reply containing only a memory proposal "
            "JSON object: append with text, replace with old/new, or forget with old. "
            "No scope, extra fields or automatic extraction are accepted."
        ) from None


@dataclass(frozen=True)
class ProposalPreview:
    review_id: str
    scope: Scope
    path: str
    workspace: str
    source: dict[str, object]
    change: dict[str, str]
    before: MemorySnapshot | None
    after_text: str

    def material(self) -> dict[str, object]:
        return {
            "operation": "accept_memory_proposal",
            "review_id": self.review_id,
            "scope": self.scope,
            "path": self.path,
            "workspace": self.workspace,
            "source": dict(self.source),
            "source_sha256": fingerprint(self.source),
            "proposal": dict(self.change),
            "before": self.before.model_dump(mode="json") if self.before else None,
            "after_text": self.after_text,
        }

    @property
    def sha256(self) -> str:
        return fingerprint(self.material())

    def receipt(self) -> dict[str, object]:
        return {
            "type": "conversation.memory.proposal.preview",
            **self.material(),
            "preview_sha256": self.sha256,
            "text": (
                f"Review assistant proposal from message {self.source['message']} "
                f"for {self.scope} memory at {self.path}. Nothing has been saved.\n"
                f"Proposed operation: {self.change['operation']}\n"
                f"Assistant proposal (untrusted):\n{self.source['answer']}\n"
                f"Complete resulting text:\n{self.after_text}\n"
                f"Apply with /memory apply-proposal {self.sha256}\n"
                "Or /memory discard-proposal. Queued work is paused. "
                "This review lasts only in this session."
            ),
        }


class MemoryProposals:
    def __init__(self, store: MemoryStore, controller: RuntimeConversationController):
        self.store = store
        self.controller = controller
        self.pending: ProposalPreview | None = None

    def source(self, number: int) -> dict[str, object]:
        entries = self.controller.state.entries
        if number < 0 or number >= len(entries):
            raise ValueError("Select an existing message number, starting at 0.")
        entry = entries[number]
        if entry.status != "completed" or entry.is_review or entry.answer is None:
            raise ValueError("Select a completed assistant chat reply, not a review.")
        return {
            "session_id": self.controller.state.session_id,
            "message": number,
            "prompt": entry.text,
            "answer": entry.answer,
        }

    def command(self, line: str) -> dict[str, object] | None:
        parts = line.split(maxsplit=4)
        if len(parts) < 2 or parts[0] != "/memory":
            return None
        action = parts[1]
        if action not in {"review-proposal", "apply-proposal", "discard-proposal"}:
            return None
        if action == "review-proposal":
            self.pending = None
        if len(line) > 8000 or any(char in line for char in "\r\n\x00"):
            raise ValueError(
                "Proposal commands require one line within 8,000 characters."
            )
        if action == "discard-proposal":
            if len(parts) != 2:
                raise ValueError("Use /memory discard-proposal without arguments.")
            self.pending = None
            return {
                "type": "conversation.memory.proposal.discarded",
                "text": "Proposal review discarded. No memory changed. Work is paused.",
            }
        if action == "apply-proposal":
            if len(parts) != 3 or re.fullmatch(r"[0-9a-f]{64}", parts[2]) is None:
                raise ValueError("Use /memory apply-proposal PREVIEW_SHA256.")
            return self.apply(parts[2])
        if (
            len(parts) != 4
            or parts[2] not in {"user", "project"}
            or re.fullmatch(r"(?:0|[1-9][0-9]{0,5})", parts[3]) is None
        ):
            raise ValueError("Use /memory review-proposal user|project MESSAGE_NUMBER.")
        scope: Scope = "user" if parts[2] == "user" else "project"
        source = self.source(int(parts[3]))
        change = proposal(str(source["answer"]))
        try:
            before = self.store.read(scope)
        except (OSError, ValueError):
            raise ValueError(
                "Saved memory could not be inspected. No review created."
            ) from None
        text = before.document.text if before else ""
        if change["operation"] == "append":
            after = (text + "\n\n" if text else "") + change["text"]
        else:
            old = change["old"]
            start = text.find(old)
            if start < 0 or text.find(old, start + 1) >= 0:
                raise ValueError(
                    "Proposal must identify one unique exact saved text span."
                )
            after = text[:start] + change.get("new", "") + text[start + len(old) :]
        if len(after.encode("utf-8")) > MEMORY_BYTES:
            raise ValueError("Proposal result would exceed 32 KiB. No review created.")
        self.pending = ProposalPreview(
            uuid4().hex,
            scope,
            str(self.store.path(scope)),
            self.store.workspace,
            source,
            change,
            before,
            after,
        )
        return self.pending.receipt()

    def apply(self, expected: str) -> dict[str, object]:
        preview = self.pending
        if preview is None:
            raise ValueError(
                "No proposal review in this session. Create a fresh review."
            )
        if expected != preview.sha256:
            raise ValueError(
                "Proposal hash does not match. Review the current proposal."
            )
        self.pending = None
        if (
            self.store.workspace != preview.workspace
            or str(self.store.path(preview.scope)) != preview.path
            or self.source(int(str(preview.source["message"]))) != preview.source
        ):
            raise ValueError(
                "Proposal source or target changed. Create a fresh review."
            )
        try:
            saved = self.store.change(
                preview.scope,
                "set",
                text=preview.after_text,
                expected_sha256=preview.before.sha256 if preview.before else "missing",
            )
        except (OSError, ValueError):
            raise ValueError(
                "Proposal could not be saved. Inspect current memory before creating "
                "a fresh review; a failed write may already have been published. "
                "Session memory is unchanged."
            ) from None
        return {
            "type": "conversation.memory.proposal.saved",
            "scope": preview.scope,
            "path": preview.path,
            "preview_sha256": expected,
            "source_sha256": fingerprint(preview.source),
            "source": dict(preview.source),
            "proposal": dict(preview.change),
            "document": saved.model_dump(mode="json"),
            "text": (
                f"Accepted assistant proposal into {preview.scope} memory "
                f"at {preview.path}. "
                f"Revision {saved.document.revision}, SHA-256 {saved.sha256}.\n"
                f"Complete saved text:\n{saved.document.text}\n"
                "Session memory is unchanged; use /memory refresh, then /continue. "
                "Earlier sessions and backups are not rewritten."
            ),
        }
