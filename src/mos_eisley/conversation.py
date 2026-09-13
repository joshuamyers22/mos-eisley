"""Bounded, text-only recorded conversations with explicit continuation."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Generic
from uuid import uuid4

from typing_extensions import TypeVar

from mos_eisley.conversation_context import (
    admit_context,
    context_turns,
    project_context,
)
from mos_eisley.conversation_inputs import ActiveInputLimitError, ActiveInputLimits
from mos_eisley.conversation_memory import (
    ConversationMemory,
    MemoryRefreshError,
    memory_system,
)
from mos_eisley.conversation_pending import PendingTextLimits, pending_text_bytes
from mos_eisley.conversation_request_admission import record_admission
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
from mos_eisley.core.agent import (
    AgentConfig,
    AgentFailure,
    build_request,
    check_request_budget,
    run_agent,
)
from mos_eisley.core.budget import Budget, resolve_budget
from mos_eisley.core.models import canonical_fingerprint
from mos_eisley.core.ports import ModelClient
from mos_eisley.core.protocol import ModelRequest, TextBlock, Turn
from mos_eisley.core.registry import fixture_registry
from mos_eisley.providers.agent_recorded import AgentCassette, RecordedAgentClient
from mos_eisley.tools.none import NoToolsDispatcher


def conversation_config(
    turns: tuple[Turn, ...], memory: ConversationMemory | None = None
) -> AgentConfig:
    return AgentConfig(
        provider="fixture",
        model="tool-reviewer-v1",
        effort="high",
        system=(
            "Continue the conversation using only its explicit text history."
            if memory is None
            else "Use the conversation's explicit history and saved context."
        )
        + memory_system(memory),
        initial_turns=turns,
        max_iterations=1,
        max_tool_calls=0,
    )


def prepare_conversation_request(config: AgentConfig) -> tuple[ModelRequest, Budget]:
    """Build the complete fixture request and resolve its local byte budget."""
    resolved = fixture_registry().resolve(config.provider, config.model, config.effort)
    budget = resolve_budget(resolved.spec, resolved.effort, config.budget)
    request = build_request(
        config, resolved, budget, NoToolsDispatcher(), config.initial_turns
    )
    return request, budget


def context_for(state: RuntimeConversationState, index: int) -> tuple[Turn, ...]:
    return context_turns(state.entries, index)


StateT = TypeVar("StateT", bound=RuntimeConversationState, default=ConversationState)


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
        self.state = state
        self.cassette = cassette
        self.save = save
        self.validate_memory = validate_memory
        self.validate_review = validate_review
        self.load_entry = load_entry
        self.input_limits = input_limits
        self.pending_limits = pending_limits
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

    def submit(self, text: str) -> None:
        if not text.strip():
            raise ValueError("message cannot be blank")
        self._append(ConversationEntry(text=text, steering_for=self.active_chat_index))

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
        if not is_review:
            projected = project_context(self.state.entries, index)
            config = conversation_config(projected.turns, self.state.memory)
            admit_context(
                config.system, config.initial_turns, self.state.context_byte_limit
            )
            request, budget = prepare_conversation_request(config)
            check_request_budget(request, budget)
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
                        NoToolsDispatcher(),
                    )
                    if any(
                        not isinstance(block, TextBlock)
                        for block in result.turns[-1].blocks
                    ):
                        raise AgentFailure(
                            "conversation preview requires text responses"
                        )
                    completed = ConversationEntry(
                        text=entry.text,
                        steering_for=entry.steering_for,
                        memory_context=entry.memory_context,
                        request_admission=entry.request_admission,
                        status="completed",
                        answer=result.final_text,
                        usage=result.usage,
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
