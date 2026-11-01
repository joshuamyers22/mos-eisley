"""Content-free, constant-space observations of one owned native exchange."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract

PROGRESS_CAP = 1_000_000
BoundedCount = Annotated[int, Field(ge=0, le=PROGRESS_CAP)]
ExchangePhase = Literal["input", "output", "exit"]


class NativeStreamProgress(Contract):
    bytes_observed: BoundedCount
    first_read_ms: BoundedCount | None
    last_read_ms: BoundedCount | None
    eof: bool


class NativeProgressReceipt(Contract):
    schema_version: Literal[1] = 1
    phase: ExchangePhase
    elapsed_ms: BoundedCount
    stdin_drained: bool
    stdout: NativeStreamProgress
    stderr: NativeStreamProgress
    leader_exited_before_cleanup: bool
    cleanup_completed: bool


@dataclass
class StreamObservation:
    bytes_observed: int = 0
    first_read_ms: int | None = None
    last_read_ms: int | None = None
    eof: bool = False

    def observe(self, size: int, elapsed_ms: int) -> None:
        self.bytes_observed = min(PROGRESS_CAP, self.bytes_observed + size)
        if self.first_read_ms is None:
            self.first_read_ms = elapsed_ms
        self.last_read_ms = elapsed_ms

    def receipt(self) -> NativeStreamProgress:
        return NativeStreamProgress(
            bytes_observed=self.bytes_observed,
            first_read_ms=self.first_read_ms,
            last_read_ms=self.last_read_ms,
            eof=self.eof,
        )


@dataclass
class NativeProgress:
    started_at: float = field(default_factory=time.monotonic)
    phase: ExchangePhase = "input"
    stdin_drained: bool = False
    stdout: StreamObservation = field(default_factory=StreamObservation)
    stderr: StreamObservation = field(default_factory=StreamObservation)

    def elapsed_ms(self) -> int:
        return min(
            PROGRESS_CAP, max(0, int((time.monotonic() - self.started_at) * 1000))
        )

    def receipt(
        self, *, elapsed_ms: int, leader_exited: bool, cleanup_completed: bool
    ) -> NativeProgressReceipt:
        return NativeProgressReceipt(
            phase=self.phase,
            elapsed_ms=elapsed_ms,
            stdin_drained=self.stdin_drained,
            stdout=self.stdout.receipt(),
            stderr=self.stderr.receipt(),
            leader_exited_before_cleanup=leader_exited,
            cleanup_completed=cleanup_completed,
        )
