"""Persisted conversation contracts and reference-based runtime state."""

from typing import Annotated, Generic, Literal, Self

from pydantic import Field, model_validator
from typing_extensions import TypeVar

from mos_eisley.conversation_limits import (
    DEFAULT_CONTEXT_BYTES,
    DEFAULT_SNAPSHOT_BYTES,
    ContextByteLimit,
    SnapshotByteLimit,
)
from mos_eisley.conversation_memory import ConversationMemory
from mos_eisley.conversation_review import (
    MAX_REVIEW_RESULT_BYTES,
    REVIEW_PROMPT,
    ConversationReviewPacket,
    review_summary,
)
from mos_eisley.core.agent import AgentUsage
from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    ReviewResult,
    Text,
    canonical_bytes,
    canonical_fingerprint,
    digest,
)
from mos_eisley.providers.agent_recorded import AgentCassette

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

    @property
    def is_review(self) -> bool:
        return self.review_packet is not None

    @property
    def has_memory_context(self) -> bool:
        return self.memory_context is not None

    @property
    def review_brief_id(self) -> str | None:
        return None if self.review_packet is None else self.review_packet.brief.brief_id

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


class ArchivedConversationEntry(Contract):
    """Runtime references, admitted only against a fully verified SQLite checkpoint.

    These are never valid JSON snapshot entries. Only the latest review result may
    stay decoded for the live renderer; it is excluded from working-state dumps.
    """

    text: Text
    status: Status = "queued"
    answer: Text | None = None
    usage: AgentUsage | None = None
    steering_for: Annotated[int | None, Field(ge=0, le=15)] = Field(
        default=None, exclude_if=lambda value: value is None
    )
    artifact_refs: Annotated[dict[str, Digest], Field(min_length=1, max_length=3)]
    source_sha256: Digest
    review_brief_id: Identifier | None = None
    review_result: ReviewResult | None = Field(default=None, exclude=True)

    @property
    def memory_context(self) -> None:
        return None

    @property
    def review_packet(self) -> None:
        return None

    @property
    def is_review(self) -> bool:
        return "review_packet" in self.artifact_refs

    @property
    def has_memory_context(self) -> bool:
        return "memory_context" in self.artifact_refs

    @model_validator(mode="after")
    def consistent_references(self) -> Self:
        refs = self.artifact_refs
        if not refs.keys() <= {"memory_context", "review_packet", "review_result"}:
            raise ValueError("invalid archived artifact field")
        if self.has_memory_context and (self.status == "queued" or self.is_review):
            raise ValueError("invalid archived memory context")
        if self.is_review:
            if (
                self.text != REVIEW_PROMPT
                or self.usage is not None
                or self.steering_for is not None
                or self.review_brief_id is None
            ):
                raise ValueError("invalid archived review metadata")
            if "review_result" in refs:
                if self.status not in {"completed", "failed"} or self.answer is None:
                    raise ValueError("invalid archived review outcome")
            elif self.status == "completed" or self.answer is not None:
                raise ValueError("archived review requires retained evidence")
        elif "review_result" in refs or self.review_brief_id is not None:
            raise ValueError("archived review evidence requires a packet")
        else:
            ConversationEntry(
                text=self.text,
                status=self.status,
                answer=self.answer,
                usage=self.usage,
                steering_for=self.steering_for,
            )
        if self.review_result is not None and (
            digest(canonical_bytes(self.review_result)) != refs.get("review_result")
            or len(canonical_bytes(self.review_result)) > MAX_REVIEW_RESULT_BYTES
            or self.review_result.verdict.brief_id != self.review_brief_id
            or review_summary(self.review_result) != self.answer
        ):
            raise ValueError("invalid cached review result")
        return self

    def record_body(self) -> dict[str, object]:
        return self.model_dump(
            mode="json", include={"text", "status", "answer", "usage", "steering_for"}
        )


EntryT = TypeVar(
    "EntryT",
    bound=ConversationEntry | ArchivedConversationEntry,
    default=ConversationEntry,
)


class ConversationState(Contract, Generic[EntryT]):
    schema_version: Literal[1] = 1
    mode: Literal["recorded_conversation"] = "recorded_conversation"
    session_id: SessionID
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    cassette_sha256: Digest
    revision: Annotated[int, Field(ge=0)] = 0
    exchanges_consumed: Annotated[int, Field(ge=0, le=16)] = 0
    entries: Annotated[tuple[EntryT, ...], Field(max_length=16)] = ()
    memory: ConversationMemory | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    memory_disabled: bool = Field(default=False, exclude_if=lambda value: not value)
    retained_cassette: AgentCassette | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    builtin_recording: bool = Field(default=False, exclude_if=lambda value: not value)
    snapshot_max_bytes: SnapshotByteLimit | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    context_max_bytes: ContextByteLimit | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @property
    def context_byte_limit(self) -> int:
        return self.context_max_bytes or DEFAULT_CONTEXT_BYTES

    @property
    def snapshot_byte_limit(self) -> int:
        return self.snapshot_max_bytes or DEFAULT_SNAPSHOT_BYTES

    @model_validator(mode="after")
    def valid_progress(self) -> Self:
        if self.memory_disabled and self.memory is not None:
            raise ValueError("disabled memory must not contain active context")
        if self.retained_cassette is not None and (
            canonical_fingerprint(self.retained_cassette).sha256 != self.cassette_sha256
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
                if target.status == "queued" or target.is_review:
                    raise ValueError("steering requires a dispatched chat target")
                targets.add(entry.steering_for)
        started = tuple(
            entry
            for entry in self.entries
            if entry.status != "queued" and not entry.is_review
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


class WorkingConversationState(
    ConversationState[ConversationEntry | ArchivedConversationEntry]
):
    """Runtime-only state whose historical artifacts remain in verified storage."""


RuntimeConversationState = ConversationState | WorkingConversationState


def validate_runtime_state[StateT: RuntimeConversationState](state: StateT) -> StateT:
    # Dump nested models to fresh data so strict validation cannot trust shallowly
    # frozen instances. Native tuples/timestamps need no JSON encode/decode cycle.
    # Persisted JSON readers retain their separate decoding/compatibility boundary.
    validated = type(state).model_validate(state.model_dump(mode="python"))
    entries: list[ConversationEntry | ArchivedConversationEntry] = []
    for old, entry in zip(state.entries, validated.entries, strict=True):
        if (
            isinstance(old, ArchivedConversationEntry)
            and isinstance(entry, ArchivedConversationEntry)
            and old.review_result is not None
        ):
            entry = ArchivedConversationEntry.model_validate(
                {
                    **dict(entry),
                    "review_result": ReviewResult.model_validate(
                        old.review_result.model_dump(mode="python")
                    ),
                }
            )
        entries.append(entry)
    return validated.model_copy(update={"entries": tuple(entries)})
