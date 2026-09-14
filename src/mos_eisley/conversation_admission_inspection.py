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
            f"Context SHA-256: {saved.context_sha256}",
            f"Request SHA-256: {request.sha256}",
            *describe_selection(saved.selection),
            "Positions describe messages present at admission; later submissions "
            "are outside this record.",
        ]
        if saved.task_profile is not None:
            profile = saved.task_profile
            lines.extend(
                (
                    f"Task profile: {profile.manifest.profile_id}; "
                    f"work unit {profile.manifest.work_unit.work_unit_id}@"
                    f"{profile.manifest.work_unit.revision}; "
                    f"diagnostics {profile.report.status}.",
                    f"Task profile SHA-256: {profile.manifest.sha256}",
                    "Reusable memory source: "
                    + (profile.reusable_memory_context_sha256 or "none"),
                    "Temporary task-state source: "
                    + (profile.temporary_task_state_sha256 or "none"),
                    "Selected tool schemas grant no execution authority.",
                )
            )
            if profile.acquisition is not None:
                acquisition = profile.acquisition
                lines.extend(
                    (
                        f"Automatically acquired {acquisition.role} guidance from "
                        f"role-context snapshot "
                        f"{acquisition.role_context_snapshot_sha256}.",
                        f"Role-context SHA-256: {acquisition.role_context_sha256}",
                        f"Selection source SHA-256: "
                        f"{acquisition.selection_source_sha256}",
                    )
                )
                if acquisition.semantic_discovery is not None:
                    discovery = acquisition.semantic_discovery
                    lines.extend(
                        (
                            f"Validated semantic discovery: {discovery.category}; "
                            f"selected {discovery.selected_profile_id} from "
                            f"{len(discovery.candidate_profile_ids)} candidate(s).",
                            f"Discovery decision SHA-256: {discovery.decision_sha256}",
                            f"Queued-task SHA-256: {discovery.task_text_sha256}",
                        )
                    )
                if acquisition.tool_catalog is not None:
                    catalog = acquisition.tool_catalog
                    candidate_count = len(catalog.selected_tool_ids) + len(
                        catalog.omitted_tool_ids
                    )
                    lines.extend(
                        (
                            f"Runtime tool catalog: {catalog.catalog_id}@"
                            f"{catalog.catalog_revision}; selected "
                            f"{len(catalog.selected_tool_ids)} of "
                            f"{candidate_count} candidate(s).",
                            f"Tool decision SHA-256: {catalog.decision_sha256}",
                            "Schemas are request-scoped; tool execution remains "
                            "disabled.",
                        )
                    )
        if saved.task_state is not None:
            task_state = saved.task_state
            lines.extend(
                (
                    f"Task-state bundle: {task_state.bundle_sha256}; "
                    f"revision {task_state.bundle_revision}.",
                    f"Checkpoint: {task_state.checkpoint_id}@"
                    f"{task_state.checkpoint_revision}; SHA-256 "
                    f"{task_state.checkpoint_sha256}.",
                    f"Current work unit: "
                    f"{task_state.current_work_unit.work_unit_id}@"
                    f"{task_state.current_work_unit.revision}.",
                    f"Task-state context SHA-256: {task_state.context_sha256}; "
                    f"{task_state.context_bytes} bytes.",
                    f"Current-selection source SHA-256: "
                    f"{task_state.acquisition.selection_source_sha256}.",
                    "Evidence views omitted from prompt: "
                    + (
                        ", ".join(task_state.acquisition.omitted_evidence_view_ids)
                        or "none"
                    )
                    + ".",
                    "Live workspace freshness is not yet verified; continuation "
                    "is not enabled.",
                )
            )
        lines.append(
            "Saved admission is not proof of transmission or provider receipt. "
            "Read-only inspection; no work started."
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
