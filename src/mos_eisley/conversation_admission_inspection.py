"""Read-only terminal inspection of one saved chat admission."""

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.conversation_context import Position, describe_selection
from mos_eisley.conversation_pressure import describe_pressure
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
        lines = [
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
        ]
        if saved.task_profile is not None:
            profile = saved.task_profile
            lines.extend(
                (
                    f"Task profile: {profile.profile_id}; work unit "
                    f"{profile.work_unit.work_unit_id} revision "
                    f"{profile.work_unit.revision}.",
                    f"Selected task inputs: {len(profile.selected_instruction_ids)} "
                    f"instruction(s), {len(profile.selected_tool_ids)} tool(s); "
                    f"{len(profile.warning_codes)} visible warning type(s).",
                    f"Task profile SHA-256: {profile.profile_sha256}",
                )
            )
            if profile.acquisition is not None:
                acquisition = profile.acquisition
                lines.extend(
                    (
                        "Profile acquisition: work-unit-owned checkpoint "
                        f"{acquisition.checkpoint_id} revision "
                        f"{acquisition.checkpoint_revision}.",
                        f"Task bundle SHA-256: {acquisition.bundle_sha256}",
                    )
                )
        if saved.task_continuation is not None:
            continuation = saved.task_continuation
            lines.extend(
                (
                    f"Continuation claim: {continuation.claim_id}; checkpoint "
                    f"{continuation.checkpoint_id} revision "
                    f"{continuation.checkpoint_revision}.",
                    f"Selected continuation work unit: "
                    f"{continuation.selected_work_unit.work_unit_id} revision "
                    f"{continuation.selected_work_unit.revision}.",
                    f"Fresh-context SHA-256: {continuation.context_sha256}",
                )
            )
        if saved.author_compaction is not None:
            compaction = saved.author_compaction
            lines.extend(
                (
                    f"Author compaction: {compaction.compaction_id}; revision "
                    f"{compaction.revision}; messages 0-"
                    f"{compaction.compacted_through} reconstructed.",
                    f"Compaction view: {compaction.before_bytes} source bytes → "
                    f"{compaction.after_bytes} model-visible bytes; grants no "
                    "authority.",
                )
            )
        if saved.pressure is not None:
            lines.extend(describe_pressure(saved.pressure, saved.pressure_advisory))
        classification = saved.context_classification
        if classification is not None:
            lines.append(
                "Context classes: "
                f"{len(classification.reusable_memory)} reusable memory source(s), "
                f"{len(classification.task_instruction_ids)} task instruction(s), "
                f"{len(classification.temporary_task_state_ids)} temporary-state "
                "item(s); "
                + (
                    f"checkpoint claim {classification.continuation_claim_id} selected."
                    if classification.checkpoint_selected
                    else "no checkpoint selected."
                )
            )
        lines.extend(
            (
                f"Context SHA-256: {saved.context_sha256}",
                f"Request SHA-256: {request.sha256}",
                *describe_selection(saved.selection),
                "Positions describe messages present at admission; later submissions "
                "are outside this record.",
                "Saved admission is not proof of transmission or provider receipt. "
                "Read-only inspection; no work started.",
            )
        )
        return "\n".join(lines)


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
