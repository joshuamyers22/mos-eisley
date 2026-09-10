"""Text-only conversation context selection and independent byte admission."""

from collections.abc import Sequence
from typing import Annotated, Protocol

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

    def user_blocks(position: int) -> tuple[TextBlock, ...]:
        positions = [position]
        while (target := entries[position].steering_for) is not None and entries[
            target
        ].status != "completed":
            positions.append(target)
            position = target
        return tuple(TextBlock(text=entries[item].text) for item in reversed(positions))

    turns: list[Turn] = []
    for position, entry in enumerate(entries[:index]):
        if entry.status == "completed" and entry.answer is not None:
            turns.extend(
                (
                    Turn(role="user", blocks=user_blocks(position)),
                    Turn(role="assistant", blocks=(TextBlock(text=entry.answer),)),
                )
            )
    turns.append(Turn(role="user", blocks=user_blocks(index)))
    return tuple(turns)


def admit_context(system: str, turns: tuple[Turn, ...], maximum: int) -> int:
    """Count canonical UTF-8 JSON for system + turns, not tokens or wire bytes."""
    maximum = TypeAdapter[int](ContextByteLimit).validate_python(maximum)
    size = len(canonical_bytes(RequestContext(system=system, turns=turns)))
    if size > maximum:
        raise ContextBudgetError(size, maximum)
    return size
