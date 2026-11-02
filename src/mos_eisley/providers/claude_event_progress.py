"""Bounded, content-free observation; never a replacement completion parser."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import JsonValue, TypeAdapter

from mos_eisley.core.models import Contract
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.native_progress import PROGRESS_CAP, BoundedCount

MAX_LINE_BYTES = 128_000
MAX_INSPECTION_BYTES = 1_000_000
MAX_INSPECTION_EVENTS = 4096
_OBJECT = TypeAdapter(dict[str, JsonValue])


class EventMilestone(Contract):
    count: BoundedCount = 0
    first_ms: BoundedCount | None = None
    last_ms: BoundedCount | None = None


class ClaudeEventReceipt(Contract):
    schema_version: Literal[1] = 1
    init: EventMilestone
    thinking: EventMilestone
    assistant: EventMilestone
    result: EventMilestone
    result_validation: Literal["not_seen", "valid", "invalid", "unavailable"]
    rate_limit_events: BoundedCount
    other_events: BoundedCount
    events_after_result: BoundedCount
    malformed_lines: BoundedCount
    oversized_lines: BoundedCount
    inspection_limited: bool
    pending_line_bytes: BoundedCount
    stdout_eof: bool
    stdout_eof_ms: BoundedCount | None
    adapter_elapsed_ms: BoundedCount | None = None


class ClaudeEventObserver:
    """Transient buffers are bounded and never included in repr or receipts."""

    def __init__(self, validate_result: Callable[[bytes], object]) -> None:
        self._validate = validate_result
        self._line = bytearray()
        self._prefix = bytearray()
        self._pending = self._processed = self._events = 0
        self._overlong = False
        self._limited = False
        self._milestones = {
            name: EventMilestone()
            for name in ("init", "thinking", "assistant", "result")
        }
        self._validation: Literal["not_seen", "valid", "invalid", "unavailable"] = (
            "not_seen"
        )
        self._rate = self._other = self._after = self._malformed = self._oversized = 0
        self._eof = False
        self._eof_ms: int | None = None

    def __repr__(self) -> str:
        return "ClaudeEventObserver(content_redacted=True)"

    def observe(self, data: bytes, elapsed_ms: int) -> None:
        elapsed_ms = min(PROGRESS_CAP, max(0, elapsed_ms))
        if not data:
            self._eof, self._eof_ms = True, elapsed_ms
            if self._pending:
                self._finish_line(elapsed_ms)
            return
        if len(self._prefix) + len(data) <= MAX_INSPECTION_BYTES and not self._limited:
            self._prefix.extend(data)
        else:
            self._limited = True
        # Split only at NDJSON newlines; split UTF-8 code points stay in the buffer.
        for part in data.splitlines(keepends=True):
            self._pending = min(PROGRESS_CAP, self._pending + len(part))
            if len(self._line) + len(part) <= MAX_LINE_BYTES and not self._overlong:
                self._line.extend(part)
            else:
                self._overlong = True
                self._line.clear()
            if part.endswith(b"\n"):
                self._finish_line(elapsed_ms)

    def _finish_line(self, elapsed_ms: int) -> None:
        self._processed = min(PROGRESS_CAP, self._processed + self._pending)
        self._events = min(MAX_INSPECTION_EVENTS + 1, self._events + 1)
        if self._events > MAX_INSPECTION_EVENTS:
            self._limited = True
        if self._overlong:
            self._oversized = min(PROGRESS_CAP, self._oversized + 1)
        elif self._events > MAX_INSPECTION_EVENTS:
            self._limited = True
        else:
            self._classify(bytes(self._line), elapsed_ms)
        self._line.clear()
        self._pending = 0
        self._overlong = False

    def _classify(self, line: bytes, elapsed_ms: int) -> None:
        try:
            event = _OBJECT.validate_json(line, strict=True)
        except (ValueError, UnicodeError, RecursionError):
            self._malformed = min(PROGRESS_CAP, self._malformed + 1)
            return
        if self._milestones["result"].count:
            self._after = min(PROGRESS_CAP, self._after + 1)
        kind = event.get("type")
        name = (
            "init"
            if kind == "system" and event.get("subtype") == "init"
            else "thinking"
            if kind == "system" and event.get("subtype") == "thinking_tokens"
            else "assistant"
            if kind == "assistant"
            else "result"
            if kind == "result"
            else None
        )
        if name is None:
            if kind == "rate_limit_event":
                self._rate = min(PROGRESS_CAP, self._rate + 1)
            else:
                self._other = min(PROGRESS_CAP, self._other + 1)
            return
        old = self._milestones[name]
        self._milestones[name] = EventMilestone(
            count=min(PROGRESS_CAP, old.count + 1),
            first_ms=old.first_ms if old.first_ms is not None else elapsed_ms,
            last_ms=elapsed_ms,
        )
        if name == "result" and self._validation == "not_seen":
            if self._limited or self._oversized or self._malformed:
                self._validation = "unavailable"
            else:
                try:
                    self._validate(bytes(self._prefix[: self._processed]))
                except (ValueError, RecursionError, ProviderError):
                    self._validation = "invalid"
                else:
                    self._validation = "valid"

    def receipt(self, *, adapter_elapsed_ms: int | None = None) -> ClaudeEventReceipt:
        return ClaudeEventReceipt(
            init=self._milestones["init"],
            thinking=self._milestones["thinking"],
            assistant=self._milestones["assistant"],
            result=self._milestones["result"],
            result_validation=self._validation,
            rate_limit_events=self._rate,
            other_events=self._other,
            events_after_result=self._after,
            malformed_lines=self._malformed,
            oversized_lines=self._oversized,
            inspection_limited=self._limited,
            pending_line_bytes=min(PROGRESS_CAP, self._pending),
            stdout_eof=self._eof,
            stdout_eof_ms=self._eof_ms,
            adapter_elapsed_ms=adapter_elapsed_ms,
        )

    def discard_content(self) -> None:
        self._line.clear()
        self._prefix.clear()

    def mark_limited(self) -> None:
        """The transport refused bytes before this observer could inspect them."""
        self._limited = True
