"""Per-launch admission for queued user text, independent of stored history."""

from collections.abc import Iterable
from typing import Annotated, Protocol

from pydantic import Field

from mos_eisley.core.models import Contract

DEFAULT_PENDING_TEXT_BYTES = 64_000
MIN_PENDING_TEXT_BYTES = 4_000
MAX_PENDING_TEXT_BYTES = 512_000


class PendingMessage(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def status(self) -> str: ...


def pending_text_bytes(entries: Iterable[PendingMessage]) -> int:
    """Count queued text without loading review or historical memory artifacts."""
    return sum(
        len(entry.text.encode("utf-8")) for entry in entries if entry.status == "queued"
    )


class PendingTextBudgetError(ValueError):
    def __init__(self, queued: int, submitted: int, maximum: int) -> None:
        self.queued_bytes = queued
        self.submitted_bytes = submitted
        self.required_bytes = queued + submitted
        self.maximum_bytes = maximum
        super().__init__(
            f"Pending text needs {self.required_bytes} bytes "
            f"({queued} queued + {submitted} submitted); limit is {maximum}. "
            "New input was not queued; no attempt was consumed. "
            "Continue or cancel queued work, shorten this input, or reopen with "
            "--pending-text-max-bytes BYTES."
        )


class PendingTextLimits(Contract):
    max_bytes: Annotated[
        int, Field(ge=MIN_PENDING_TEXT_BYTES, le=MAX_PENDING_TEXT_BYTES)
    ] = DEFAULT_PENDING_TEXT_BYTES

    def admit(self, entries: Iterable[PendingMessage], text: str) -> None:
        queued = pending_text_bytes(entries)
        submitted = len(text.encode("utf-8"))
        if queued + submitted > self.max_bytes:
            raise PendingTextBudgetError(queued, submitted, self.max_bytes)


def pending_text_byte_limit(value: str) -> int:
    maximum = int(value)
    if not MIN_PENDING_TEXT_BYTES <= maximum <= MAX_PENDING_TEXT_BYTES:
        raise ValueError("pending text limit must be between 4000 and 512000")
    return maximum
