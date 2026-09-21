"""Bounded, text-only recorded conversations with explicit continuation."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Generic, Protocol
from uuid import uuid4

from typing_extensions import TypeVar

from mos_eisley.conversation_compaction import (
    AuthorCompaction,
    AuthorCompactionDraft,
    compaction_system,
    create_author_compaction,
)
from mos_eisley.conversation_context import (
    admit_context,
    project_context,
)
from mos_eisley.conversation_inputs import ActiveInputLimitError, ActiveInputLimits
from mos_eisley.conversation_memory import (
    ConversationMemory,
    MemoryRefreshError,
    memory_system,
)
from mos_eisley.conversation_pending import PendingTextLimits, pending_text_bytes
from mos_eisley.conversation_pressure import (
    ContextPressureBreakdown,
    ContextPressurePolicy,
    ContextPressureSnapshot,
    assess_context_pressure,
    build_pressure_snapshot,
    make_pressure_boundary,
    measure_pressure_activity,
)
from mos_eisley.conversation_request_admission import (
    AuthorCompactionAdmission,
    record_admission,
)
from mos_eisley.conversation_review import (
    REVIEW_PROMPT,
    ConversationReviewPacket,
    review_summary,
    run_conversation_review,
)
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    RuntimeConversationState,
    WorkingConversationState,
    validate_runtime_state,
)
from mos_eisley.conversation_state import (
    ConversationEntry as ConversationEntry,
)
from mos_eisley.conversation_state import (
    ConversationMemoryContext as ConversationMemoryContext,
)
from mos_eisley.conversation_state import (
    ConversationState as ConversationState,
)
from mos_eisley.conversation_state import (
    SessionID as SessionID,
)
from mos_eisley.conversation_state import (
    Status as Status,
)
from mos_eisley.conversation_task_profile import (
    ScopedTaskProfile,
    ScopedToolDispatcher,
    admit_fresh_continuation,
    admit_scoped_profile,
    classify_context,
    continuation_system,
)
from mos_eisley.core.agent import (
    AgentConfig,
    AgentFailure,
    build_request,
    check_request_budget,
    run_agent,
)
from mos_eisley.core.budget import Budget, resolve_budget
from mos_eisley.core.models import canonical_bytes, canonical_fingerprint, digest
from mos_eisley.core.ports import ModelClient, ToolDispatcher
from mos_eisley.core.protocol import ModelRequest, TextBlock, Turn
from mos_eisley.core.registry import fixture_registry
from mos_eisley.providers.agent_recorded import AgentCassette, RecordedAgentClient
from mos_eisley.run.task_checkpoint_store import (
    CheckpointClosureError,
    CheckpointClosureReason,
    ClaimedContinuation,
    ContinuationClaimError,
    ResolvedContinuation,
)
from mos_eisley.run.task_state_store import TaskStateBundle
from mos_eisley.task_state import (
    ContinuationSelection,
    OwnerProjectScope,
    TaskCheckpointHead,
    TaskContinuationClaim,
    WorkspaceState,
)
from mos_eisley.tools.none import NoToolsDispatcher


def conversation_config(
    turns: tuple[Turn, ...],
    memory: ConversationMemory | None = None,
    *,
    task_system: str = "",
    tools_enabled: bool = False,
) -> AgentConfig:
    return AgentConfig(
        provider="fixture",
        model="tool-reviewer-v1",
        effort="high",
        system=conversation_base_system(memory) + memory_system(memory) + task_system,
        initial_turns=turns,
        max_iterations=8 if tools_enabled else 1,
        max_tool_calls=32 if tools_enabled else 0,
    )


def conversation_base_system(memory: ConversationMemory | None) -> str:
    return (
        "Continue the conversation using only its explicit text history."
        if memory is None
        else "Use the conversation's explicit history and saved context."
    )


def prepare_conversation_request(
    config: AgentConfig, dispatcher: ToolDispatcher | None = None
) -> tuple[ModelRequest, Budget]:
    """Build the complete fixture request and resolve its local byte budget."""
    resolved = fixture_registry().resolve(config.provider, config.model, config.effort)
    budget = resolve_budget(resolved.spec, resolved.effort, config.budget)
    request = build_request(
        config,
        resolved,
        budget,
        NoToolsDispatcher() if dispatcher is None else dispatcher,
        config.initial_turns,
    )
    return request, budget


def context_for(state: RuntimeConversationState, index: int) -> tuple[Turn, ...]:
    compaction = None if not state.author_compactions else state.author_compactions[-1]
    return project_context(state.entries, index, compaction).turns


StateT = TypeVar("StateT", bound=RuntimeConversationState, default=ConversationState)


class CheckpointCloser(Protocol):
    def __call__(
        self,
        bundle: TaskStateBundle,
        artifacts: Mapping[str, bytes],
        *,
        expected_revision: int,
        reason: CheckpointClosureReason = "completed_milestone",
    ) -> TaskCheckpointHead: ...


class ContinuationClaimer(Protocol):
    def __call__(
        self,
        selection: ContinuationSelection,
        *,
        session_id: str,
        observed_workspace: WorkspaceState,
    ) -> ClaimedContinuation: ...


class ContinuationResolver(Protocol):
    def __call__(
        self,
        claim: TaskContinuationClaim,
        *,
        observed_workspace: WorkspaceState,
    ) -> ResolvedContinuation: ...


def _latest_pressure_snapshot(
    state: RuntimeConversationState,
) -> ContextPressureSnapshot | None:
    return next(
        (
            entry.request_admission.pressure
            for entry in reversed(state.entries)
            if entry.request_admission is not None
            and entry.request_admission.pressure is not None
        ),
        None,
    )


def _pressure_boundary_position(state: RuntimeConversationState) -> int:
    return next(
        (
            position
            for position, entry in enumerate(state.entries)
            if entry.status in {"queued", "running"}
        ),
        len(state.entries),
    )


class ConversationController(Generic[StateT]):
    """One request per message; steering is applied after the active request.

    Persistence runs before dispatch and after every transition. The CLI supplies
    only recorded clients. Live providers require a separate spending/transfer gate.
    """

    def __init__(
        self,
        state: StateT,
        cassette: AgentCassette,
        save: Callable[[StateT], StateT | None],
        *,
        validate_memory: Callable[[], None] | None = None,
        validate_review: Callable[[ConversationReviewPacket], None] | None = None,
        load_entry: Callable[[int, ArchivedConversationEntry], ConversationEntry]
        | None = None,
        input_limits: ActiveInputLimits | None = None,
        pending_limits: PendingTextLimits | None = None,
        task_scope: OwnerProjectScope | None = None,
        resolve_task_profile: Callable[[int], ScopedTaskProfile | None] | None = None,
        tool_dispatcher: ToolDispatcher | None = None,
        close_task_checkpoint: CheckpointCloser | None = None,
        claim_task_continuation: ContinuationClaimer | None = None,
        resolve_task_continuation: ContinuationResolver | None = None,
        observe_task_workspace: Callable[[], WorkspaceState] | None = None,
        context_pressure_policy: ContextPressurePolicy | None = None,
    ) -> None:
        if input_limits is not None:
            input_limits.admit_memory(state.memory)
        recording = canonical_fingerprint(cassette)
        if input_limits is not None:
            input_limits.admit_size("retained_cassette", recording.bytes)
        if recording.sha256 != state.cassette_sha256:
            raise ValueError("resume requires the exact recorded cassette")
        if state.exchanges_consumed > len(cassette.exchanges):
            raise ValueError("cassette does not cover saved attempts")
        if task_scope is None and (
            resolve_task_profile is not None
            or tool_dispatcher is not None
            or close_task_checkpoint is not None
            or claim_task_continuation is not None
            or resolve_task_continuation is not None
            or observe_task_workspace is not None
        ):
            raise ValueError("task runtime dependencies require an expected scope")
        if tool_dispatcher is not None and (
            resolve_task_profile is None and resolve_task_continuation is None
        ):
            raise ValueError("task tools require a profile acquisition path")
        continuation_dependencies = (
            claim_task_continuation,
            resolve_task_continuation,
            observe_task_workspace,
        )
        if any(item is not None for item in continuation_dependencies) and not all(
            item is not None for item in continuation_dependencies
        ):
            raise ValueError("continuation runtime dependencies must be complete")
        if (
            task_scope is not None
            and resolve_task_profile is None
            and close_task_checkpoint is None
            and claim_task_continuation is None
        ):
            raise ValueError(
                "task scope requires a profile resolver or checkpoint store"
            )
        if task_scope is not None and (
            task_scope.owner_uid != state.owner_uid
            or task_scope.workspace_sha256 != digest(state.workspace.encode("utf-8"))
        ):
            raise ValueError("task scope does not match the conversation workspace")
        if (
            task_scope is not None
            and state.task_checkpoint is not None
            and state.task_checkpoint.scope != task_scope
        ):
            raise ValueError("saved checkpoint does not match the selected task scope")
        if (
            context_pressure_policy is not None
            and state.context_pressure_policy is not None
            and context_pressure_policy != state.context_pressure_policy
        ):
            raise ValueError("context-pressure policy differs from saved session")
        self.state = state
        self.cassette = cassette
        self.save = save
        self.validate_memory = validate_memory
        self.validate_review = validate_review
        self.load_entry = load_entry
        self.input_limits = input_limits
        self.pending_limits = pending_limits
        self.task_scope = task_scope
        self.resolve_task_profile = resolve_task_profile
        self.tool_dispatcher = tool_dispatcher
        self.close_task_checkpoint = close_task_checkpoint
        self.claim_task_continuation = claim_task_continuation
        self.resolve_task_continuation = resolve_task_continuation
        self.observe_task_workspace = observe_task_workspace
        self.context_pressure_policy = (
            context_pressure_policy
            or state.context_pressure_policy
            or ContextPressurePolicy()
        )
        self._busy = False
        self._broken = False
        if any(entry.status == "running" for entry in state.entries):
            self._update(
                tuple(
                    entry.model_copy(update={"status": "interrupted"})
                    if entry.status == "running"
                    else entry
                    for entry in state.entries
                )
            )

    @staticmethod
    def fresh(
        workspace: Path,
        cassette: AgentCassette,
        memory: ConversationMemory | None = None,
        *,
        memory_disabled: bool = False,
        memory_project_root: str | None = None,
        memory_project_mapping: str | None = None,
        snapshot_max_bytes: int | None = None,
        context_max_bytes: int | None = None,
        input_limits: ActiveInputLimits | None = None,
        context_pressure_policy: ContextPressurePolicy | None = None,
    ) -> ConversationState:
        if not workspace.is_dir():
            raise ValueError("conversation workspace must be a directory")
        if input_limits is not None:
            input_limits.admit_memory(memory)
        recording = canonical_fingerprint(cassette)
        if input_limits is not None:
            input_limits.admit_size("retained_cassette", recording.bytes)
        return ConversationState(
            session_id=uuid4().hex,
            owner_uid=os.getuid(),
            workspace=str(workspace.resolve(strict=True)),
            cassette_sha256=recording.sha256,
            memory=memory,
            memory_disabled=memory_disabled,
            memory_project_root=memory_project_root,
            memory_project_mapping=memory_project_mapping,
            snapshot_max_bytes=snapshot_max_bytes,
            context_max_bytes=context_max_bytes,
            context_pressure_policy=context_pressure_policy,
        )

    def _update(
        self,
        entries: tuple[ConversationEntry | ArchivedConversationEntry, ...],
        *,
        consumed: int | None = None,
    ) -> None:
        if self._broken:
            raise ValueError("session persistence failed; reopen before continuing")
        updated = type(self.state).model_validate(
            dict(
                session_id=self.state.session_id,
                session_name=self.state.session_name,
                owner_uid=self.state.owner_uid,
                workspace=self.state.workspace,
                memory_project_root=self.state.memory_project_root,
                memory_project_mapping=self.state.memory_project_mapping,
                cassette_sha256=self.state.cassette_sha256,
                revision=self.state.revision + 1,
                exchanges_consumed=(
                    self.state.exchanges_consumed if consumed is None else consumed
                ),
                entries=entries,
                memory=self.state.memory,
                memory_disabled=self.state.memory_disabled,
                retained_cassette=self.state.retained_cassette,
                builtin_recording=self.state.builtin_recording,
                snapshot_max_bytes=self.state.snapshot_max_bytes,
                context_max_bytes=self.state.context_max_bytes,
                task_checkpoint=self.state.task_checkpoint,
                task_continuation=self.state.task_continuation,
                author_compactions=self.state.author_compactions,
                context_pressure_policy=self.context_pressure_policy,
                context_pressure_boundary=self.state.context_pressure_boundary,
            )
        )
        self._commit(updated)

    def _commit(self, updated: StateT) -> None:
        if self._broken:
            raise ValueError("session persistence failed; reopen before continuing")
        if self.input_limits is not None:
            self.input_limits.admit(updated.memory, self.cassette)
        try:
            saved = self.save(updated)
        except BaseException:
            self._broken = True
            raise
        self.state = updated if saved is None else saved

    def refresh_memory(
        self,
        memory: ConversationMemory | None,
        cassette: AgentCassette,
        *,
        disabled: bool = False,
        builtin: bool = False,
        snapshot_max_bytes: int | None = None,
    ) -> None:
        if self._busy or any(entry.status == "running" for entry in self.state.entries):
            raise MemoryRefreshError("Stop active work before changing session memory.")
        try:
            if self.input_limits is not None:
                self.input_limits.admit_memory(memory)
            recording = canonical_fingerprint(cassette)
            if self.input_limits is not None:
                self.input_limits.admit_size("retained_cassette", recording.bytes)
        except ActiveInputLimitError as error:
            raise MemoryRefreshError(str(error)) from None
        consumed = self.state.exchanges_consumed
        if (
            len(cassette.exchanges) < consumed
            or cassette.exchanges[:consumed] != self.cassette.exchanges[:consumed]
        ):
            raise MemoryRefreshError(
                "A replacement recording must preserve every consumed exchange."
            )
        # Legacy entries inherit the old session selection. Freeze it before
        # changing the active selection; historical context never enters new prompts.
        entries = tuple(
            entry.model_copy(
                update={
                    "memory_context": ConversationMemoryContext(
                        memory=self.state.memory
                    )
                }
            )
            if entry.status != "queued"
            and not entry.is_review
            and not entry.has_memory_context
            else entry
            for entry in self.state.entries
        )
        try:
            updated = type(self.state).model_validate(
                dict(
                    session_id=self.state.session_id,
                    session_name=self.state.session_name,
                    owner_uid=self.state.owner_uid,
                    workspace=self.state.workspace,
                    memory_project_root=self.state.memory_project_root,
                    memory_project_mapping=self.state.memory_project_mapping,
                    revision=self.state.revision + 1,
                    exchanges_consumed=consumed,
                    entries=entries,
                    memory=memory,
                    memory_disabled=disabled,
                    retained_cassette=cassette,
                    cassette_sha256=recording.sha256,
                    builtin_recording=builtin,
                    context_max_bytes=self.state.context_max_bytes,
                    task_checkpoint=self.state.task_checkpoint,
                    task_continuation=self.state.task_continuation,
                    author_compactions=self.state.author_compactions,
                    context_pressure_policy=self.context_pressure_policy,
                    context_pressure_boundary=self.state.context_pressure_boundary,
                    snapshot_max_bytes=(
                        self.state.snapshot_max_bytes
                        if snapshot_max_bytes is None
                        else snapshot_max_bytes
                    ),
                )
            )
            updated = validate_runtime_state(updated)
        except ValueError:
            raise MemoryRefreshError(
                "The selected memory or recording is invalid for this session."
            ) from None
        self._commit(updated)
        self.cassette = cassette

    def rename(self, name: str | None) -> None:
        if self._busy or any(entry.status == "running" for entry in self.state.entries):
            raise ValueError("Stop active work before renaming the session.")
        updated = validate_runtime_state(
            self.state.model_copy(
                update={"session_name": name, "revision": self.state.revision + 1}
            )
        )
        if name != self.state.session_name:
            self._commit(updated)

    def resize_storage(self, maximum: int) -> None:
        if self._busy or any(entry.status == "running" for entry in self.state.entries):
            raise ValueError("stop active work before changing the storage budget")
        updated = self.state.model_copy(
            update={"snapshot_max_bytes": maximum, "revision": self.state.revision + 1}
        )
        updated = validate_runtime_state(updated)
        if maximum != self.state.snapshot_max_bytes:
            self._commit(updated)

    def resize_context(self, maximum: int) -> None:
        if self._busy or any(entry.status == "running" for entry in self.state.entries):
            raise ValueError("stop active work before changing the context budget")
        updated = self.state.model_copy(
            update={"context_max_bytes": maximum, "revision": self.state.revision + 1}
        )
        updated = validate_runtime_state(updated)
        if maximum != self.state.context_max_bytes:
            self._commit(updated)

    def compact_author(self, draft: AuthorCompactionDraft) -> AuthorCompaction:
        """Commit one reconstructable author derivative without consuming work."""
        if self._busy or any(
            entry.status in {"queued", "running"} for entry in self.state.entries
        ):
            raise ValueError("stop or finish pending work before author compaction")
        previous = (
            None
            if not self.state.author_compactions
            else self.state.author_compactions[-1]
        )
        continuation = self.state.task_continuation
        compaction = create_author_compaction(
            entries=self.state.entries,
            owner_uid=self.state.owner_uid,
            workspace=self.state.workspace,
            source_revision=self.state.revision,
            source_state_sha256=digest(canonical_bytes(self.state)),
            draft=draft,
            previous=previous,
            repository_revision=(
                None
                if continuation is None
                else continuation.selection.workspace.revision
            ),
            checkpoint_sha256=(
                None
                if continuation is None
                else continuation.selection.checkpoint_sha256
            ),
            continuation_claim_id=(
                None if continuation is None else continuation.claim_id
            ),
            task_ledger=(
                None if continuation is None else continuation.selection.ledger_baseline
            ),
            work_unit_id=(
                None
                if continuation is None
                else continuation.selection.selected_work_unit.work_unit_id
            ),
            work_unit_revision=(
                None
                if continuation is None
                else continuation.selection.selected_work_unit.revision
            ),
        )
        latest_pressure = _latest_pressure_snapshot(self.state)
        updated = validate_runtime_state(
            self.state.model_copy(
                update={
                    "author_compactions": self.state.author_compactions + (compaction,),
                    "context_pressure_policy": self.context_pressure_policy,
                    "context_pressure_boundary": make_pressure_boundary(
                        kind="compaction",
                        conversation_revision=self.state.revision + 1,
                        next_message_position=len(self.state.entries),
                        latest_request_bytes=(
                            0
                            if latest_pressure is None
                            else latest_pressure.request_bytes
                        ),
                        compaction_count=len(self.state.author_compactions) + 1,
                    ),
                    "revision": self.state.revision + 1,
                }
            )
        )
        self._commit(updated)
        return compaction

    def close_milestone(
        self,
        bundle: TaskStateBundle,
        artifacts: Mapping[str, bytes],
        *,
        expected_checkpoint_revision: int,
        reason: CheckpointClosureReason = "completed_milestone",
    ) -> TaskCheckpointHead:
        """Close a durable task boundary and retain its text-free task-state head."""
        if self._busy or any(entry.status == "running" for entry in self.state.entries):
            raise CheckpointClosureError(
                "stop active conversation work before closing a checkpoint"
            )
        if self.task_scope is None or self.close_task_checkpoint is None:
            raise CheckpointClosureError(
                "checkpoint closure requires a scoped checkpoint store"
            )
        try:
            bundle = TaskStateBundle.model_validate(bundle.model_dump(mode="python"))
        except ValueError:
            raise CheckpointClosureError(
                "task-state bundle failed conversation closure validation"
            ) from None
        if bundle.scope != self.task_scope:
            raise CheckpointClosureError(
                "milestone checkpoint does not match the conversation task scope"
            )
        saved_head = self.state.task_checkpoint
        if saved_head is None:
            if expected_checkpoint_revision != 0:
                raise CheckpointClosureError(
                    "conversation checkpoint revision changed before closure"
                )
        elif (
            saved_head.checkpoint_id != bundle.checkpoint.checkpoint_id
            or expected_checkpoint_revision != saved_head.checkpoint_revision
        ):
            raise CheckpointClosureError(
                "conversation checkpoint revision changed before closure"
            )
        head = self.close_task_checkpoint(
            bundle,
            artifacts,
            expected_revision=expected_checkpoint_revision,
            reason=reason,
        )
        if (
            head.scope != self.task_scope
            or head.checkpoint_id != bundle.checkpoint.checkpoint_id
            or head.checkpoint_revision != bundle.checkpoint.revision
            or head.checkpoint_sha256 != bundle.checkpoint.sha256
            or head.bundle_revision != bundle.revision
            or head.bundle_sha256 != bundle.sha256
            or head.closure_reason != reason
        ):
            raise CheckpointClosureError(
                "checkpoint store returned a mismatched closure receipt"
            )
        if self.state.task_checkpoint == head:
            return head
        latest_pressure = _latest_pressure_snapshot(self.state)
        updated = validate_runtime_state(
            self.state.model_copy(
                update={
                    "task_checkpoint": head,
                    "task_continuation": None,
                    "context_pressure_policy": self.context_pressure_policy,
                    "context_pressure_boundary": make_pressure_boundary(
                        kind="checkpoint",
                        conversation_revision=self.state.revision + 1,
                        next_message_position=_pressure_boundary_position(self.state),
                        latest_request_bytes=(
                            0
                            if latest_pressure is None
                            else latest_pressure.request_bytes
                        ),
                        compaction_count=len(self.state.author_compactions),
                    ),
                    "revision": self.state.revision + 1,
                }
            )
        )
        try:
            self._commit(updated)
        except BaseException:
            raise CheckpointClosureError(
                "checkpoint closed but its conversation link is uncertain; "
                "reopen and inspect before retrying"
            ) from None
        return head

    def begin_continuation(
        self, selection: ContinuationSelection
    ) -> TaskContinuationClaim:
        """Claim a checkpoint for this fresh session without dispatching work."""
        if self._busy or any(entry.status == "running" for entry in self.state.entries):
            raise ContinuationClaimError(
                "stop active conversation work before selecting a continuation"
            )
        if self.state.entries:
            raise ContinuationClaimError(
                "checkpoint continuation requires a fresh conversation history"
            )
        if self.task_scope is None or self.claim_task_continuation is None:
            raise ContinuationClaimError(
                "continuation requires a scoped checkpoint store"
            )
        if self.state.task_continuation is not None:
            if self.state.task_continuation.selection == selection:
                return self.state.task_continuation
            raise ContinuationClaimError("conversation already selected a continuation")
        assert self.observe_task_workspace is not None
        receipt = self.claim_task_continuation(
            selection,
            session_id=self.state.session_id,
            observed_workspace=self.observe_task_workspace(),
        )
        profile_manifest = receipt.profile.profile.manifest
        profile_source = receipt.profile.acquisition
        if (
            receipt.head.scope != self.task_scope
            or receipt.claim.session_id != self.state.session_id
            or receipt.claim.selection != selection
            or receipt.claim.context_sha256 != receipt.context.sha256
            or profile_manifest.scope != self.task_scope
            or profile_manifest.work_unit != selection.selected_work_unit
            or profile_source.checkpoint_id != receipt.head.checkpoint_id
            or profile_source.checkpoint_revision != receipt.head.checkpoint_revision
            or profile_source.checkpoint_sha256 != receipt.head.checkpoint_sha256
            or profile_source.bundle_revision != receipt.head.bundle_revision
            or profile_source.bundle_sha256 != receipt.head.bundle_sha256
        ):
            raise ContinuationClaimError(
                "checkpoint store returned a mismatched continuation receipt"
            )
        updated = validate_runtime_state(
            self.state.model_copy(
                update={
                    "task_checkpoint": receipt.head,
                    "task_continuation": receipt.claim,
                    "context_pressure_policy": self.context_pressure_policy,
                    "context_pressure_boundary": make_pressure_boundary(
                        kind="continuation",
                        conversation_revision=self.state.revision + 1,
                        next_message_position=0,
                        latest_request_bytes=0,
                        compaction_count=0,
                    ),
                    "revision": self.state.revision + 1,
                }
            )
        )
        try:
            self._commit(updated)
        except BaseException:
            raise ContinuationClaimError(
                "continuation was claimed but its conversation link is uncertain; "
                "reopen the same session before retrying"
            ) from None
        return receipt.claim

    def submit(self, text: str) -> None:
        if not text.strip():
            raise ValueError("message cannot be blank")
        self._append(ConversationEntry(text=text, steering_for=self.active_chat_index))

    def submit_continuation(
        self, text: str, selection: ContinuationSelection
    ) -> TaskContinuationClaim:
        """Persist an explicit fresh-context selection and its user request."""
        claim = self.begin_continuation(selection)
        self.submit(text)
        return claim

    @property
    def pending_text_bytes(self) -> int:
        return pending_text_bytes(self.state.entries)

    def _append(self, entry: ConversationEntry) -> None:
        if self._broken:
            raise ValueError("session persistence failed; reopen before continuing")
        if self.pending_limits is not None:
            self.pending_limits.admit(self.state.entries, entry.text)
        self._update(self.state.entries + (entry,))

    @property
    def active_chat_index(self) -> int | None:
        return next(
            (
                index
                for index, entry in enumerate(self.state.entries)
                if entry.status == "running" and not entry.is_review
            ),
            None,
        )

    def steer(self, text: str) -> None:
        if self.active_chat_index is None:
            raise ValueError("steering requires an active chat request")
        self.submit(text)

    def submit_review(self, packet: ConversationReviewPacket) -> None:
        packet = ConversationReviewPacket.model_validate_json(packet.model_dump_json())
        self._check_review_guidance(packet)
        self._append(ConversationEntry(text=REVIEW_PROMPT, review_packet=packet))

    def _check_review_guidance(self, packet: ConversationReviewPacket) -> None:
        guidance = packet.guidance_review
        if guidance is None:
            return
        if (
            self.validate_review is None
            or guidance.owner_uid != self.state.owner_uid
            or guidance.workspace.path != self.state.workspace
        ):
            raise ValueError(
                "Guided review requires this project's current policy selection."
            )
        self.validate_review(packet)

    def cancel_queued(self) -> None:
        self._update(
            tuple(
                entry.model_copy(update={"status": "cancelled"})
                if entry.status == "queued"
                else entry
                for entry in self.state.entries
            )
        )

    async def step(
        self,
        client: ModelClient | None = None,
        *,
        on_started: Callable[[], None] | None = None,
    ) -> bool:
        if self._busy:
            raise ValueError("a conversation request is already active")
        index = next(
            (
                i
                for i, entry in enumerate(self.state.entries)
                if entry.status == "queued"
            ),
            None,
        )
        if index is None:
            return False
        if self.input_limits is not None:
            self.input_limits.admit(self.state.memory, self.cassette)
        if self.validate_memory is not None:
            self.validate_memory()
        consumed = self.state.exchanges_consumed
        entry = self.state.entries[index]
        if isinstance(entry, ArchivedConversationEntry):
            if self.load_entry is None:
                raise ValueError("archived work requires its verified storage handle")
            entry = self.load_entry(index, entry)
        is_review = entry.is_review
        if entry.review_packet is not None:
            self._check_review_guidance(entry.review_packet)
        if not is_review and self.state.retained_cassette is not None:
            entry = entry.model_copy(
                update={
                    "memory_context": ConversationMemoryContext(
                        memory=self.state.memory
                    )
                }
            )
        if not is_review and consumed >= len(self.cassette.exchanges):
            raise ValueError("recorded conversation has no remaining exchange")
        # Select and admit the exact immutable context before persisting running
        # or burning an attempt. The config is reused after dispatch admission.
        config: AgentConfig | None = None
        request_dispatcher: ToolDispatcher = NoToolsDispatcher()
        if not is_review:
            author_compaction = (
                None
                if not self.state.author_compactions
                else self.state.author_compactions[-1]
            )
            projected = project_context(self.state.entries, index, author_compaction)
            admitted_profile = None
            continuation_context = None
            continuation_admission = None
            profile_acquisition = None
            profile = None
            if self.state.task_continuation is not None:
                if (
                    self.resolve_task_continuation is None
                    or self.observe_task_workspace is None
                ):
                    raise ContinuationClaimError(
                        "saved continuation requires its scoped checkpoint store"
                    )
                resolved_continuation = self.resolve_task_continuation(
                    self.state.task_continuation,
                    observed_workspace=self.observe_task_workspace(),
                )
                continuation_context = resolved_continuation.context
                profile = resolved_continuation.profile.profile
                profile_acquisition = resolved_continuation.profile.acquisition
                continuation_admission = admit_fresh_continuation(
                    self.state.task_continuation, continuation_context
                )
            elif self.resolve_task_profile is not None:
                profile = self.resolve_task_profile(index)
            if profile is not None:
                assert self.task_scope is not None
                available = (
                    ()
                    if self.tool_dispatcher is None
                    else self.tool_dispatcher.definitions
                )
                admitted_profile = admit_scoped_profile(
                    profile,
                    self.task_scope,
                    available,
                    self.state.memory,
                    acquisition=profile_acquisition,
                )
                if (
                    continuation_context is not None
                    and admitted_profile.record.work_unit
                    != continuation_context.selection.selected_work_unit
                ):
                    raise ContinuationClaimError(
                        "task profile selects a different continuation work unit"
                    )
                if admitted_profile.selected_tools:
                    if self.tool_dispatcher is None:
                        raise ValueError("selected task tools are unavailable")
                    request_dispatcher = ScopedToolDispatcher(
                        self.tool_dispatcher, admitted_profile.selected_tools
                    )
            classification = classify_context(
                self.state.memory,
                profile,
                None
                if self.state.task_continuation is None
                else self.state.task_continuation.claim_id,
            )
            compaction_suffix = (
                ""
                if author_compaction is None
                else compaction_system(author_compaction)
            )
            checkpoint_suffix = (
                ""
                if continuation_context is None
                else continuation_system(continuation_context)
            )
            profile_suffix = (
                "" if admitted_profile is None else admitted_profile.system_suffix
            )
            task_system = compaction_suffix + checkpoint_suffix + profile_suffix
            config = conversation_config(
                projected.turns,
                self.state.memory,
                task_system=task_system,
                tools_enabled=bool(request_dispatcher.definitions),
            )
            context_size = admit_context(
                config.system, config.initial_turns, self.state.context_byte_limit
            )
            request, budget = prepare_conversation_request(config, request_dispatcher)
            request_size = check_request_budget(request, budget)
            pressure = build_pressure_snapshot(
                policy=self.context_pressure_policy,
                source_revision=self.state.revision,
                request_ordinal=consumed + 1,
                context_bytes=context_size,
                context_max_bytes=self.state.context_byte_limit,
                request_bytes=request_size,
                request_max_bytes=budget.usable_input,
                known_breakdown=ContextPressureBreakdown(
                    base_system_bytes=len(
                        conversation_base_system(self.state.memory).encode("utf-8")
                    ),
                    conversation_bytes=sum(
                        len(canonical_bytes(turn)) for turn in projected.turns
                    ),
                    reusable_memory_bytes=len(
                        memory_system(self.state.memory).encode("utf-8")
                    ),
                    task_profile_bytes=len(profile_suffix.encode("utf-8")),
                    checkpoint_bytes=len(checkpoint_suffix.encode("utf-8")),
                    compaction_bytes=len(compaction_suffix.encode("utf-8")),
                    tool_schema_bytes=sum(
                        len(canonical_bytes(definition))
                        for definition in request_dispatcher.definitions
                    ),
                ),
                entries=self.state.entries,
                boundary=self.state.context_pressure_boundary,
                compaction_count=len(self.state.author_compactions),
            )
            pressure_advisory = assess_context_pressure(
                pressure, _latest_pressure_snapshot(self.state)
            )
            entry = entry.model_copy(
                update={
                    "request_admission": record_admission(
                        source_revision=self.state.revision,
                        message_count=len(self.state.entries),
                        exchange_index=consumed,
                        selection=projected.selection,
                        context_max_bytes=self.state.context_byte_limit,
                        request=request,
                        budget=budget,
                        memory_selected=self.state.memory is not None,
                        context_classification=classification,
                        task_profile=None
                        if admitted_profile is None
                        else admitted_profile.record,
                        task_continuation=continuation_admission,
                        author_compaction=(
                            None
                            if author_compaction is None
                            else AuthorCompactionAdmission(
                                compaction_id=author_compaction.compaction_id,
                                revision=author_compaction.revision,
                                compacted_through=(author_compaction.compacted_through),
                                source_revision=author_compaction.source_revision,
                                before_bytes=author_compaction.before_bytes,
                                after_bytes=author_compaction.after_bytes,
                                prior_compaction_sha256=(
                                    author_compaction.prior_compaction_sha256
                                ),
                            )
                        ),
                        pressure=pressure,
                        pressure_advisory=pressure_advisory,
                    )
                }
            )
        self._busy = True

        def replace(entry: ConversationEntry, *, started: bool = False) -> None:
            entries = list(self.state.entries)
            entries[index] = entry
            self._update(
                tuple(entries),
                consumed=consumed + 1 if started and not is_review else None,
            )

        try:
            # Burn this recorded position before awaiting; resume never retries it.
            replace(entry.model_copy(update={"status": "running"}), started=True)
            if on_started is not None:
                on_started()
            try:
                if entry.review_packet is not None:
                    packet = entry.review_packet
                    review_result = (
                        await run_conversation_review(
                            packet,
                            validate_guidance=lambda: self._check_review_guidance(
                                packet
                            ),
                        )
                        if packet.guidance_review is not None
                        else await run_conversation_review(packet)
                    )
                    completed = ConversationEntry(
                        text=entry.text,
                        status="failed"
                        if review_result.verdict.decision == "infrastructure_error"
                        else "completed",
                        answer=review_summary(review_result),
                        review_packet=entry.review_packet,
                        review_result=review_result,
                    )
                else:
                    assert config is not None
                    recorded = RecordedAgentClient(
                        AgentCassette(exchanges=(self.cassette.exchanges[consumed],))
                    )
                    result = await run_agent(
                        config,
                        fixture_registry(),
                        recorded if client is None else client,
                        request_dispatcher,
                    )
                    if any(
                        not isinstance(block, TextBlock)
                        for block in result.turns[-1].blocks
                    ):
                        raise AgentFailure(
                            "conversation preview requires text responses"
                        )
                    pressure_activity = measure_pressure_activity(
                        result.turns, self.context_pressure_policy
                    )
                    completed = ConversationEntry(
                        text=entry.text,
                        steering_for=entry.steering_for,
                        memory_context=entry.memory_context,
                        request_admission=entry.request_admission,
                        status="completed",
                        answer=result.final_text,
                        usage=result.usage,
                        pressure_activity=(
                            None
                            if pressure_activity.tool_calls == 0
                            else pressure_activity
                        ),
                    )
            except asyncio.CancelledError:
                replace(entry.model_copy(update={"status": "cancelled"}))
                raise
            except (AgentFailure, ValueError):
                replace(entry.model_copy(update={"status": "failed"}))
                raise
            replace(completed)
            if completed.status == "failed":
                raise AgentFailure("recorded review did not satisfy its review policy")
            return True
        finally:
            self._busy = False


RuntimeConversationController = (
    ConversationController[ConversationState]
    | ConversationController[WorkingConversationState]
)
