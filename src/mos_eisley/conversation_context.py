"""Text-only conversation context selection and independent byte admission."""

from collections.abc import Sequence
from typing import Annotated, Literal, NamedTuple, Protocol, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_compaction import AuthorCompaction
from mos_eisley.conversation_limits import ContextByteLimit
from mos_eisley.core.models import Contract, Digest, canonical_bytes
from mos_eisley.core.protocol import TextBlock, Turn


class ContextMessage(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def answer(self) -> str | None: ...

    @property
    def steering_for(self) -> int | None: ...


class RequestContext(Contract):
    system: Annotated[str, Field(max_length=64_000)]
    turns: Annotated[tuple[Turn, ...], Field(min_length=1, max_length=31)]


Position = Annotated[int, Field(ge=0, le=15)]


class ContextTurnSource(Contract):
    role: Literal["user", "assistant"]
    positions: Annotated[tuple[Position, ...], Field(min_length=1, max_length=16)]


class ContextOmission(Contract):
    position: Position
    reason: Literal["after_target", "no_completed_answer_or_required_link"]


class ContextSelection(Contract):
    policy_version: Literal[1, 2] = 1
    message_index: Position
    turn_sources: Annotated[
        tuple[ContextTurnSource, ...], Field(min_length=1, max_length=31)
    ]
    omitted: Annotated[tuple[ContextOmission, ...], Field(max_length=15)]
    compaction_id: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    compacted_positions: Annotated[tuple[Position, ...], Field(max_length=16)] = Field(
        default=(), exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def consistent_compaction(self) -> Self:
        compacted = self.compacted_positions
        if self.policy_version == 1:
            if self.compaction_id is not None or compacted:
                raise ValueError("selection policy 1 cannot contain compaction")
        elif (
            self.compaction_id is None
            or not compacted
            or compacted != tuple(range(compacted[-1] + 1))
            or compacted[-1] >= self.message_index
        ):
            raise ValueError("selection policy 2 requires an exact earlier prefix")
        return self


class ContextProjection(NamedTuple):
    turns: tuple[Turn, ...]
    selection: ContextSelection


def describe_selection(selection: ContextSelection) -> list[str]:
    """Describe source positions without accessing message or artifact content."""
    lines: list[str] = []
    if selection.compaction_id is not None:
        positions = ", ".join(
            str(position) for position in selection.compacted_positions
        )
        lines.append(
            f"Author compaction {selection.compaction_id} reconstructs message(s) "
            f"{positions} from retained originals."
        )
    for turn, source in enumerate(selection.turn_sources):
        positions = ", ".join(str(position) for position in source.positions)
        lines.append(f"Turn {turn}: {source.role} from message(s) {positions}.")
    for omission in selection.omitted:
        reason = (
            "after the selected message"
            if omission.reason == "after_target"
            else "no completed answer or required steering link"
        )
        lines.append(f"Omitted message {omission.position}: {reason}.")
    return lines


class ContextBudgetError(ValueError):
    """A local admission rejection whose message contains only sizes and guidance."""

    def __init__(self, size: int, maximum: int) -> None:
        self.required_bytes = size
        self.maximum_bytes = maximum
        super().__init__(
            f"Conversation context needs {size} bytes; saved limit is {maximum}. "
            "Message remains queued; no attempt was consumed. Resume with "
            "--context-max-bytes within 4000–1000000, or start a fresh session."
        )


def context_turns(entries: Sequence[ContextMessage], index: int) -> tuple[Turn, ...]:
    return project_context(entries, index).turns


def project_context(
    entries: Sequence[ContextMessage],
    index: int,
    compaction: AuthorCompaction | None = None,
) -> ContextProjection:
    """Preserve all completed exchanges and unanswered steering intent.

    This interface needs only text and links, so callers need not hydrate memory
    snapshots, review packets or review evidence to select conversation history.
    The current preview remains bounded to sixteen messages; no truncation occurs.
    """
    if not 0 <= index < len(entries) <= 16:
        raise ValueError("invalid conversation context position or message count")
    compacted_through = -1 if compaction is None else compaction.compacted_through
    if compacted_through >= index:
        raise ValueError("author compaction cannot cover the selected message")
    for position, entry in enumerate(entries[: index + 1]):
        if entry.steering_for is not None and not 0 <= entry.steering_for < position:
            raise ValueError("context steering must refer to an earlier message")

    def user_positions(position: int) -> tuple[int, ...]:
        positions = [position]
        while (target := entries[position].steering_for) is not None and entries[
            target
        ].status != "completed":
            if target <= compacted_through:
                break
            positions.append(target)
            position = target
        return tuple(reversed(positions))

    sources: list[ContextTurnSource] = []
    for position, entry in enumerate(
        entries[compacted_through + 1 : index], start=compacted_through + 1
    ):
        if entry.status == "completed" and entry.answer is not None:
            sources.extend(
                (
                    ContextTurnSource(role="user", positions=user_positions(position)),
                    ContextTurnSource(role="assistant", positions=(position,)),
                )
            )
    sources.append(ContextTurnSource(role="user", positions=user_positions(index)))
    selected = {position for source in sources for position in source.positions}
    compacted = set(range(compacted_through + 1))
    selection = ContextSelection(
        policy_version=2 if compaction is not None else 1,
        message_index=index,
        turn_sources=tuple(sources),
        omitted=tuple(
            ContextOmission(
                position=position,
                reason="after_target"
                if position > index
                else "no_completed_answer_or_required_link",
            )
            for position in range(len(entries))
            if position not in selected and position not in compacted
        ),
        compaction_id=None if compaction is None else compaction.compaction_id,
        compacted_positions=tuple(sorted(compacted)),
    )
    turns: list[Turn] = []
    for source in sources:
        blocks: list[TextBlock] = []
        for position in source.positions:
            text = (
                entries[position].text
                if source.role == "user"
                else entries[position].answer
            )
            assert text is not None
            blocks.append(TextBlock(text=text))
        turns.append(Turn(role=source.role, blocks=tuple(blocks)))
    return ContextProjection(tuple(turns), selection)


def admit_context(system: str, turns: tuple[Turn, ...], maximum: int) -> int:
    """Count canonical UTF-8 JSON for system + turns, not tokens or wire bytes."""
    maximum = TypeAdapter[int](ContextByteLimit).validate_python(maximum)
    size = len(canonical_bytes(RequestContext(system=system, turns=turns)))
    if size > maximum:
        raise ContextBudgetError(size, maximum)
    return size
