"""Read-only terminal inspection of one saved chat admission."""

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.conversation_context import Position, describe_selection
from mos_eisley.conversation_request_admission import RequestAdmission
from mos_eisley.conversation_state import RuntimeConversationState, SessionID, Status
from mos_eisley.core.models import Contract


class AdmissionInspectionUnavailable(ValueError):
    """Safe notices for invalid selectors and attempts without saved metadata."""


class AdmissionInspection(Contract):
    schema_version: Literal[1] = 1
    session_id: SessionID
    revision: Annotated[int, Field(ge=0)]
    message_index: Position
    status: Status
    admission: RequestAdmission

    def describe(self) -> str:
        saved = self.admission
        request = saved.request
        return "\n".join(
            [
                f"Saved request admission • message {self.message_index} "
                f"• status {self.status}",
                f"Viewing revision {self.revision}; admitted from revision "
                f"{saved.source_revision} with {saved.message_count} message(s).",
                f"Recorded exchange: {saved.exchange_index}; "
                f"admission schema: {saved.schema_version}; "
                f"selection policy: {saved.selection.policy_version}.",
                f"Context at admission: {saved.context_bytes}/"
                f"{saved.context_max_bytes} canonical bytes.",
                f"Model request at admission: {request.bytes}/"
                f"{request.max_bytes} canonical bytes.",
                f"Route: {request.provider}/{request.model}; effort {request.effort}.",
                f"Reserved: {request.output_reserve_bytes} output bytes; "
                f"{request.headroom_bytes} headroom bytes.",
                "Saved memory selected at admission."
                if saved.memory_selected
                else "No saved memory selected at admission.",
                f"Context SHA-256: {saved.context_sha256}",
                f"Request SHA-256: {request.sha256}",
                *describe_selection(saved.selection),
                "Positions describe messages present at admission; later submissions "
                "are outside this record.",
                "Saved admission is not proof of transmission or provider receipt. "
                "Read-only inspection; no work started.",
            ]
        )


def inspect_admission(
    state: RuntimeConversationState, position: int
) -> AdmissionInspection:
    if type(position) is not int or not 0 <= position < len(state.entries):
        raise AdmissionInspectionUnavailable("No saved message at that position.")
    entry = state.entries[position]
    if entry.request_admission is None:
        if entry.is_review:
            notice = "Review messages use isolated packets and have no chat admission."
        elif entry.status == "queued":
            notice = "This message is queued and has no saved request admission."
        else:
            notice = (
                "No request admission was saved for this message. "
                "Historical admission cannot be reconstructed by this command."
            )
        raise AdmissionInspectionUnavailable(notice)
    return AdmissionInspection(
        session_id=state.session_id,
        revision=state.revision,
        message_index=position,
        status=entry.status,
        admission=entry.request_admission,
    )


def admission_position(command: str) -> int:
    parts = command.split()
    if (
        len(parts) != 2
        or parts[0] != "/context"
        or not 1 <= len(parts[1]) <= 2
        or not parts[1].isascii()
        or not parts[1].isdecimal()
        or not 0 <= int(parts[1]) <= 15
    ):
        raise AdmissionInspectionUnavailable(
            "Use /context to preview queued work or /context N to inspect "
            "a saved message number (0–15)."
        )
    return int(parts[1])
