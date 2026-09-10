"""Bounded, text-only recorded conversations with explicit continuation."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from mos_eisley.conversation_memory import (
    ConversationMemory,
    MemoryRefreshError,
    memory_system,
)
from mos_eisley.conversation_review import (
    MAX_REVIEW_RESULT_BYTES,
    REVIEW_PROMPT,
    ConversationReviewPacket,
    review_summary,
    run_conversation_review,
)
from mos_eisley.core.agent import AgentConfig, AgentFailure, AgentUsage, run_agent
from mos_eisley.core.models import (
    Contract,
    Digest,
    ReviewResult,
    Text,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ModelClient
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.core.registry import fixture_registry
from mos_eisley.providers.agent_recorded import AgentCassette, RecordedAgentClient
from mos_eisley.tools.none import NoToolsDispatcher

SessionID = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
Status = Literal["queued", "running", "completed", "cancelled", "interrupted", "failed"]


class ConversationMemoryContext(Contract):
    memory: ConversationMemory | None = None


class ConversationEntry(Contract):
    text: Text
    status: Status = "queued"
    answer: Text | None = None
    usage: AgentUsage | None = None
    memory_context: ConversationMemoryContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    steering_for: Annotated[int | None, Field(ge=0, le=15)] = Field(
        default=None, exclude_if=lambda value: value is None
    )
    review_packet: ConversationReviewPacket | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    review_result: ReviewResult | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def complete_answer(self) -> Self:
        if self.memory_context is not None and (
            self.status == "queued" or self.review_packet is not None
        ):
            raise ValueError("queued messages and reviews cannot bind chat memory")
        if self.review_packet is not None:
            if self.steering_for is not None:
                raise ValueError("review packets cannot carry conversation steering")
            if self.text != REVIEW_PROMPT or self.usage is not None:
                raise ValueError(
                    "review entries require canonical text and no chat usage"
                )
            if self.review_result is not None:
                result = self.review_result
                expected_status = (
                    "failed"
                    if result.verdict.decision == "infrastructure_error"
                    else "completed"
                )
                if (
                    self.status != expected_status
                    or result.verdict.brief_id != self.review_packet.brief.brief_id
                    or self.answer != review_summary(result)
                    or len(canonical_bytes(result)) > MAX_REVIEW_RESULT_BYTES
                ):
                    raise ValueError("review result does not match its entry")
                return self
            if self.status == "completed" or self.answer is not None:
                raise ValueError("completed review requires retained evidence")
            return self
        if self.review_result is not None:
            raise ValueError("review result requires an explicit packet")
        if self.status == "completed":
            if self.answer is None or self.usage is None:
                raise ValueError("completed messages require an answer and usage")
        elif self.answer is not None or self.usage is not None:
            raise ValueError("unfinished messages cannot carry an answer")
        return self


class ConversationState(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["recorded_conversation"] = "recorded_conversation"
    session_id: SessionID
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    cassette_sha256: Digest
    revision: Annotated[int, Field(ge=0)] = 0
    exchanges_consumed: Annotated[int, Field(ge=0, le=16)] = 0
    entries: Annotated[tuple[ConversationEntry, ...], Field(max_length=16)] = ()
    memory: ConversationMemory | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    memory_disabled: bool = Field(default=False, exclude_if=lambda value: not value)
    retained_cassette: AgentCassette | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    builtin_recording: bool = Field(default=False, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def valid_progress(self) -> Self:
        if self.memory_disabled and self.memory is not None:
            raise ValueError("disabled memory must not contain active context")
        if self.retained_cassette is not None and (
            digest(canonical_bytes(self.retained_cassette)) != self.cassette_sha256
            or self.exchanges_consumed > len(self.retained_cassette.exchanges)
        ):
            raise ValueError("retained recording does not match the session")
        if self.builtin_recording and self.retained_cassette is None:
            raise ValueError("refreshed builtin recording must be retained")
        if self.memory is not None:
            self.memory.validate_identity(self.owner_uid, self.workspace)
        targets: set[int] = set()
        for index, entry in enumerate(self.entries):
            if (
                entry.memory_context is not None
                and entry.memory_context.memory is not None
            ):
                entry.memory_context.memory.validate_identity(
                    self.owner_uid, self.workspace
                )
            if entry.steering_for is not None:
                if entry.steering_for >= index:
                    raise ValueError("steering must refer to an earlier message")
                target = self.entries[entry.steering_for]
                if target.status == "queued" or target.review_packet is not None:
                    raise ValueError("steering requires a dispatched chat target")
                targets.add(entry.steering_for)
        started = tuple(
            entry
            for entry in self.entries
            if entry.status != "queued" and entry.review_packet is None
        )
        # Cancelling a queued message does not consume an exchange.
        dispatched = sum(entry.status != "cancelled" for entry in started)
        # A cancelled steering target must have consumed an attempt, unlike an
        # ordinary queued message cancelled before dispatch.
        dispatched += sum(
            self.entries[index].status == "cancelled" for index in targets
        )
        if not dispatched <= self.exchanges_consumed <= len(started):
            raise ValueError("invalid conversation exchange count")
        if sum(entry.status == "running" for entry in self.entries) > 1:
            raise ValueError("only one message may be running")
        return self


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


def context_for(state: ConversationState, index: int) -> tuple[Turn, ...]:
    def user_blocks(position: int) -> tuple[TextBlock, ...]:
        entry = state.entries[position]
        blocks: tuple[TextBlock, ...] = ()
        # An unanswered task contributes its intent, never a fabricated answer.
        # Follow the earlier-only chain so interrupted refinements retain intent too.
        target = entry.steering_for
        if target is not None and state.entries[target].status != "completed":
            blocks = user_blocks(target)
        return blocks + (TextBlock(text=entry.text),)

    turns: list[Turn] = []
    for position, entry in enumerate(state.entries[:index]):
        if entry.status == "completed" and entry.answer is not None:
            turns.extend(
                (
                    Turn(role="user", blocks=user_blocks(position)),
                    Turn(role="assistant", blocks=(TextBlock(text=entry.answer),)),
                )
            )
    turns.append(Turn(role="user", blocks=user_blocks(index)))
    return tuple(turns)


class ConversationController:
    """One request per message; steering is applied after the active request.

    Persistence runs before dispatch and after every transition. The CLI supplies
    only recorded clients. Live providers require a separate spending/transfer gate.
    """

    def __init__(
        self,
        state: ConversationState,
        cassette: AgentCassette,
        save: Callable[[ConversationState], None],
        *,
        validate_memory: Callable[[], None] | None = None,
    ) -> None:
        if digest(canonical_bytes(cassette)) != state.cassette_sha256:
            raise ValueError("resume requires the exact recorded cassette")
        if state.exchanges_consumed > len(cassette.exchanges):
            raise ValueError("cassette does not cover saved attempts")
        self.state = state
        self.cassette = cassette
        self.save = save
        self.validate_memory = validate_memory
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
    ) -> ConversationState:
        if not workspace.is_dir():
            raise ValueError("conversation workspace must be a directory")
        return ConversationState(
            session_id=uuid4().hex,
            owner_uid=os.getuid(),
            workspace=str(workspace.resolve(strict=True)),
            cassette_sha256=digest(canonical_bytes(cassette)),
            memory=memory,
            memory_disabled=memory_disabled,
        )

    def _update(
        self, entries: tuple[ConversationEntry, ...], *, consumed: int | None = None
    ) -> None:
        if self._broken:
            raise ValueError("session persistence failed; reopen before continuing")
        updated = ConversationState(
            session_id=self.state.session_id,
            owner_uid=self.state.owner_uid,
            workspace=self.state.workspace,
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
        )
        self._commit(updated)

    def _commit(self, updated: ConversationState) -> None:
        if self._broken:
            raise ValueError("session persistence failed; reopen before continuing")
        try:
            self.save(updated)
        except BaseException:
            self._broken = True
            raise
        self.state = updated

    def refresh_memory(
        self,
        memory: ConversationMemory | None,
        cassette: AgentCassette,
        *,
        disabled: bool = False,
        builtin: bool = False,
    ) -> None:
        if self._busy or any(entry.status == "running" for entry in self.state.entries):
            raise MemoryRefreshError("Stop active work before changing session memory.")
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
            and entry.review_packet is None
            and entry.memory_context is None
            else entry
            for entry in self.state.entries
        )
        try:
            updated = ConversationState(
                session_id=self.state.session_id,
                owner_uid=self.state.owner_uid,
                workspace=self.state.workspace,
                revision=self.state.revision + 1,
                exchanges_consumed=consumed,
                entries=entries,
                memory=memory,
                memory_disabled=disabled,
                retained_cassette=cassette,
                cassette_sha256=digest(canonical_bytes(cassette)),
                builtin_recording=builtin,
            )
            updated = ConversationState.model_validate_json(updated.model_dump_json())
        except ValueError:
            raise MemoryRefreshError(
                "The selected memory or recording is invalid for this session."
            ) from None
        self._commit(updated)
        self.cassette = cassette

    def submit(self, text: str) -> None:
        if not text.strip():
            raise ValueError("message cannot be blank")
        self._update(
            self.state.entries
            + (ConversationEntry(text=text, steering_for=self.active_chat_index),)
        )

    @property
    def active_chat_index(self) -> int | None:
        return next(
            (
                index
                for index, entry in enumerate(self.state.entries)
                if entry.status == "running" and entry.review_packet is None
            ),
            None,
        )

    def steer(self, text: str) -> None:
        if self.active_chat_index is None:
            raise ValueError("steering requires an active chat request")
        self.submit(text)

    def submit_review(self, packet: ConversationReviewPacket) -> None:
        packet = ConversationReviewPacket.model_validate_json(packet.model_dump_json())
        self._update(
            self.state.entries
            + (ConversationEntry(text=REVIEW_PROMPT, review_packet=packet),)
        )

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
        if self.validate_memory is not None:
            self.validate_memory()
        consumed = self.state.exchanges_consumed
        entry = self.state.entries[index]
        is_review = entry.review_packet is not None
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
                    review_result = await run_conversation_review(entry.review_packet)
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
                    recorded = RecordedAgentClient(
                        AgentCassette(exchanges=(self.cassette.exchanges[consumed],))
                    )
                    result = await run_agent(
                        conversation_config(
                            context_for(self.state, index), self.state.memory
                        ),
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
