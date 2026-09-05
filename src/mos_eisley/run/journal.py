"""Append-and-sync JSONL journal for recovering request boundaries after crashes."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from types import TracebackType

from mos_eisley.core.protocol import JournalEvent


class JsonlJournal:
    def __init__(self, path: Path) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        self._fd = os.open(path, flags, 0o600)
        self._expected_sequence = 0
        self._closed = False
        self._lock = threading.Lock()

    def record(self, event: JournalEvent) -> None:
        payload = event.model_dump_json().encode("utf-8") + b"\n"
        if len(payload) > 128_000:
            raise ValueError("journal event exceeds byte limit")
        with self._lock:
            if self._closed:
                raise ValueError("journal is closed")
            if event.sequence != self._expected_sequence:
                raise ValueError("journal event sequence is not contiguous")
            offset = 0
            while offset < len(payload):
                written = os.write(self._fd, payload[offset:])
                if written == 0:
                    raise OSError("journal write made no progress")
                offset += written
            os.fsync(self._fd)
            self._expected_sequence += 1

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                os.close(self._fd)
                self._closed = True

    def __enter__(self) -> JsonlJournal:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class MemoryJournal:
    def __init__(self) -> None:
        self.events: list[JournalEvent] = []

    def record(self, event: JournalEvent) -> None:
        if event.sequence != len(self.events):
            raise ValueError("journal event sequence is not contiguous")
        self.events.append(event)
