"""Read-only, text-free provenance for the next queued chat context."""

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.conversation import conversation_config
from mos_eisley.conversation_context import (
    ContextSelection,
    RequestContext,
    project_context,
)
from mos_eisley.conversation_limits import ContextByteLimit
from mos_eisley.conversation_state import RuntimeConversationState, SessionID
from mos_eisley.core.models import Contract, Digest, canonical_fingerprint


class ContextPreviewUnavailable(ValueError):
    """A safe notice when there is no queued chat target."""


class ContextPreview(Contract):
    schema_version: Literal[1] = 1
    session_id: SessionID
    revision: Annotated[int, Field(ge=0)]
    selection: ContextSelection
    context_sha256: Digest
    context_bytes: Annotated[int, Field(ge=1)]
    context_max_bytes: ContextByteLimit
    within_context_budget: bool
    memory_selected: bool
    active_work: bool

    def describe(self) -> str:
        lines = [
            f"Context preview • message {self.selection.message_index} "
            f"• revision {self.revision}",
            f"Context: {self.context_bytes}/{self.context_max_bytes} bytes "
            + (
                "(fits saved context budget)."
                if self.within_context_budget
                else "(over saved context budget)."
            ),
            f"Selection policy: {self.selection.policy_version}; "
            + (
                "saved memory selected."
                if self.memory_selected
                else "no saved memory selected."
            ),
        ]
        for turn, source in enumerate(self.selection.turn_sources):
            positions = ", ".join(str(position) for position in source.positions)
            lines.append(f"Turn {turn}: {source.role} from message(s) {positions}.")
        for omission in self.selection.omitted:
            reason = (
                "after the selected message"
                if omission.reason == "after_target"
                else "no completed answer or required steering link"
            )
            lines.append(f"Omitted message {omission.position}: {reason}.")
        if self.active_work:
            lines.append("Active work may change this selection before dispatch.")
        lines.append(
            "Read-only preview of saved context; no work started. "
            "Memory, provider limits and recording availability "
            "are rechecked at dispatch."
        )
        return "\n".join(lines)


def preview_context(state: RuntimeConversationState) -> ContextPreview:
    index = next(
        (
            index
            for index, entry in enumerate(state.entries)
            if entry.status == "queued"
        ),
        None,
    )
    if index is None:
        raise ContextPreviewUnavailable("No queued message to preview.")
    if state.entries[index].is_review:
        raise ContextPreviewUnavailable(
            "The next queued message is a review; it uses its isolated review packet "
            "rather than chat history."
        )
    projected = project_context(state.entries, index)
    config = conversation_config(projected.turns, state.memory)
    fingerprint = canonical_fingerprint(
        RequestContext(system=config.system, turns=projected.turns)
    )
    return ContextPreview(
        session_id=state.session_id,
        revision=state.revision,
        selection=projected.selection,
        context_sha256=fingerprint.sha256,
        context_bytes=fingerprint.bytes,
        context_max_bytes=state.context_byte_limit,
        within_context_budget=fingerprint.bytes <= state.context_byte_limit,
        memory_selected=state.memory is not None,
        active_work=any(entry.status == "running" for entry in state.entries),
    )
