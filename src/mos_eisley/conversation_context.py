"""Text-only conversation context selection and independent byte admission."""

from collections.abc import Sequence
from typing import Annotated, Literal, NamedTuple, Protocol

from pydantic import Field, TypeAdapter

from mos_eisley.conversation_limits import ContextByteLimit
from mos_eisley.core.models import Contract, canonical_bytes
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
    policy_version: Literal[1] = 1
    message_index: Position
    turn_sources: Annotated[
        tuple[ContextTurnSource, ...], Field(min_length=1, max_length=31)
    ]
    omitted: Annotated[tuple[ContextOmission, ...], Field(max_length=15)]


class ContextProjection(NamedTuple):
    turns: tuple[Turn, ...]
    selection: ContextSelection


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


def project_context(entries: Sequence[ContextMessage], index: int) -> ContextProjection:
    """Preserve all completed exchanges and unanswered steering intent.

    This interface needs only text and links, so callers need not hydrate memory
    snapshots, review packets or review evidence to select conversation history.
    The current preview remains bounded to sixteen messages; no truncation occurs.
    """
    if not 0 <= index < len(entries) <= 16:
        raise ValueError("invalid conversation context position or message count")
    for position, entry in enumerate(entries[: index + 1]):
        if entry.steering_for is not None and not 0 <= entry.steering_for < position:
            raise ValueError("context steering must refer to an earlier message")

    def user_positions(position: int) -> tuple[int, ...]:
        positions = [position]
        while (target := entries[position].steering_for) is not None and entries[
            target
        ].status != "completed":
            positions.append(target)
            position = target
        return tuple(reversed(positions))

    sources: list[ContextTurnSource] = []
    for position, entry in enumerate(entries[:index]):
        if entry.status == "completed" and entry.answer is not None:
            sources.extend(
                (
                    ContextTurnSource(role="user", positions=user_positions(position)),
                    ContextTurnSource(role="assistant", positions=(position,)),
                )
            )
    sources.append(ContextTurnSource(role="user", positions=user_positions(index)))
    selected = {position for source in sources for position in source.positions}
    selection = ContextSelection(
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
            if position not in selected
        ),
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
