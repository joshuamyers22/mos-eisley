"""Read-only, text-free provenance for the next queued chat context."""

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.conversation import conversation_config, prepare_conversation_request
from mos_eisley.conversation_context import (
    ContextSelection,
    RequestContext,
    describe_selection,
    project_context,
)
from mos_eisley.conversation_context_pressure import (
    ContextPressurePolicy,
    ContextPressureReport,
    context_pressure_report,
    measure_current_context,
)
from mos_eisley.conversation_limits import ContextByteLimit
from mos_eisley.conversation_memory import memory_system
from mos_eisley.conversation_request_admission import (
    RequestBudgetPreview as RequestBudgetPreview,
)
from mos_eisley.conversation_request_admission import describe_request
from mos_eisley.conversation_state import (
    ConversationMemoryContext,
    ConversationTaskStateContext,
    RuntimeConversationState,
    SessionID,
)
from mos_eisley.core.models import Contract, Digest, canonical_fingerprint
from mos_eisley.task_profile import (
    RuntimeTaskProfile,
    TaskProfileAcquirer,
    TaskProfileAdmission,
    admit_task_profile,
    validate_task_profile_scope,
)
from mos_eisley.task_state_acquisition import (
    RuntimeTaskState,
    TaskStateAcquirer,
    TaskStateAdmission,
    admit_task_state,
    validate_task_state_scope,
)


class ContextPreviewUnavailable(ValueError):
    """A safe notice when there is no queued chat target."""


class ContextPreview(Contract):
    schema_version: Literal[3] = 3
    session_id: SessionID
    revision: Annotated[int, Field(ge=0)]
    selection: ContextSelection
    context_sha256: Digest
    context_bytes: Annotated[int, Field(ge=1)]
    context_max_bytes: ContextByteLimit
    within_context_budget: bool
    request: RequestBudgetPreview
    memory_selected: bool
    active_work: bool
    pressure: ContextPressureReport
    task_profile: TaskProfileAdmission | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    task_state: TaskStateAdmission | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

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
            f"Model request: {self.request.bytes}/{self.request.max_bytes} "
            "canonical bytes "
            + (
                "(fits request budget)."
                if self.request.within_budget
                else "(over request budget)."
            ),
            f"Route: {self.request.provider}/{self.request.model}; "
            f"effort {self.request.effort}.",
            f"Reserved: {self.request.output_reserve_bytes} output bytes; "
            f"{self.request.headroom_bytes} headroom bytes.",
            f"Selection policy: {self.selection.policy_version}; "
            + (
                "saved memory selected."
                if self.memory_selected
                else "no saved memory selected."
            ),
        ]
        lines.extend(describe_selection(self.selection))
        if self.task_profile is not None:
            profile = self.task_profile
            lines.extend(
                (
                    f"Task profile: {profile.manifest.profile_id}; "
                    f"work unit {profile.manifest.work_unit.work_unit_id}@"
                    f"{profile.manifest.work_unit.revision}; "
                    f"diagnostics {profile.report.status}.",
                    f"Selected task inputs: "
                    f"{profile.manifest.sizes.instruction_bytes} instruction bytes; "
                    f"{profile.manifest.sizes.tool_schema_bytes} tool-schema bytes.",
                    "Reusable memory and temporary task state are recorded as "
                    "separate sources; selected tool schemas grant no execution.",
                )
            )
            if profile.acquisition is not None:
                acquisition = profile.acquisition
                lines.append(
                    f"Automatically acquired {acquisition.role} guidance from "
                    f"role-context snapshot "
                    f"{acquisition.role_context_snapshot_sha256}."
                )
                if acquisition.semantic_discovery is not None:
                    discovery = acquisition.semantic_discovery
                    lines.append(
                        f"Validated semantic discovery: {discovery.category}; "
                        f"selected {discovery.selected_profile_id} from "
                        f"{len(discovery.candidate_profile_ids)} candidate(s)."
                    )
        if self.task_state is not None:
            task_state = self.task_state
            lines.extend(
                (
                    f"Current task state: bundle {task_state.bundle_sha256}; "
                    f"revision {task_state.bundle_revision}.",
                    f"Checkpoint {task_state.checkpoint_id}@"
                    f"{task_state.checkpoint_revision}; current work unit "
                    f"{task_state.current_work_unit.work_unit_id}@"
                    f"{task_state.current_work_unit.revision}.",
                    f"Temporary task-state context: {task_state.context_bytes} bytes; "
                    + (
                        "explicit continuation claimed; no execution authority."
                        if task_state.continuation_enabled
                        else "no continuation or execution authority."
                    ),
                )
            )
            if task_state.continuation_enabled:
                acquisition = task_state.acquisition
                lines.append(
                    "Live workspace freshness: "
                    + ("ready." if acquisition.freshness_ready else "blocked.")
                )
                if acquisition.stale_verification_ids:
                    lines.append(
                        "Stale checkpoint verifications: "
                        + ", ".join(acquisition.stale_verification_ids)
                        + "."
                    )
        if self.active_work:
            lines.append("Active work may change this selection before dispatch.")
        lines.append(
            "Read-only preview of saved context; no work started. "
            "Memory, provider limits and recording availability "
            "are rechecked at dispatch."
        )
        lines.extend(("", self.pressure.describe()))
        return "\n".join(lines)


def preview_context(
    state: RuntimeConversationState,
    task_profile: RuntimeTaskProfile | None = None,
    task_profile_acquirer: TaskProfileAcquirer | None = None,
    task_state: RuntimeTaskState | None = None,
    task_state_acquirer: TaskStateAcquirer | None = None,
    pressure_policy: ContextPressurePolicy | None = None,
) -> ContextPreview:
    if task_profile is not None and task_profile_acquirer is not None:
        raise ValueError("choose a fixed or automatically acquired task profile")
    if task_state is not None and task_state_acquirer is not None:
        raise ValueError("choose fixed or automatically acquired task state")
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
    projected = project_context(
        state.entries,
        index,
        state.author_compactions[-1] if state.author_compactions else None,
    )
    if task_state_acquirer is not None:
        task_state = task_state_acquirer.acquire(
            owner_uid=state.owner_uid,
            workspace=state.workspace,
            session_id=state.session_id,
        )
    if task_state is not None:
        validate_task_state_scope(
            task_state, owner_uid=state.owner_uid, workspace=state.workspace
        )
    if task_profile_acquirer is not None:
        task_profile = task_profile_acquirer.acquire(
            owner_uid=state.owner_uid,
            workspace=state.workspace,
            task_text=state.entries[index].text,
        )
    if task_profile is not None:
        validate_task_profile_scope(
            task_profile, owner_uid=state.owner_uid, workspace=state.workspace
        )
    if (
        task_profile is not None
        and task_state is not None
        and task_profile.manifest.work_unit != task_state.current_work_unit.reference
    ):
        raise ValueError("task profile and task state select different work")
    config = conversation_config(
        projected.turns, state.memory, task_profile, task_state
    )
    fingerprint = canonical_fingerprint(
        RequestContext(system=config.system, turns=projected.turns)
    )
    request, budget = prepare_conversation_request(config, task_profile)
    request_sha256 = canonical_fingerprint(request).sha256
    task_state_admission = None
    task_state_context_sha256 = None
    if task_state is not None:
        task_state_context = canonical_fingerprint(
            ConversationTaskStateContext(task_state=task_state)
        )
        task_state_context_sha256 = task_state_context.sha256
        task_state_admission = admit_task_state(
            task_state,
            request_sha256=request_sha256,
            context_sha256=task_state_context.sha256,
            context_bytes=task_state_context.bytes,
        )
    profile_admission = None
    if task_profile is not None:
        profile_admission = admit_task_profile(
            task_profile,
            request_sha256=request_sha256,
            reusable_memory_context_sha256=(
                None
                if state.memory is None
                else canonical_fingerprint(
                    ConversationMemoryContext(memory=state.memory)
                ).sha256
            ),
            temporary_task_state_sha256=task_state_context_sha256,
        )
    context_pressure = measure_current_context(
        request,
        budget,
        context_bytes=fingerprint.bytes,
        context_capacity_bytes=state.context_byte_limit,
        project_guidance=("" if task_profile is None else task_profile.system_suffix),
        selected_memory=memory_system(state.memory),
        checkpoint="" if task_state is None else task_state.system_suffix,
    )
    return ContextPreview(
        session_id=state.session_id,
        revision=state.revision,
        selection=projected.selection,
        context_sha256=fingerprint.sha256,
        context_bytes=fingerprint.bytes,
        context_max_bytes=state.context_byte_limit,
        within_context_budget=fingerprint.bytes <= state.context_byte_limit,
        request=describe_request(request, budget),
        memory_selected=state.memory is not None,
        active_work=any(entry.status == "running" for entry in state.entries),
        pressure=context_pressure_report(
            state,
            current=context_pressure,
            task_state=task_state,
            policy=pressure_policy,
        ),
        task_profile=profile_admission,
        task_state=task_state_admission,
    )
