"""Bounded read-only host callbacks; abandoned results never enter the owner queue."""

import math
import time
from collections.abc import Callable, Generator
from concurrent.futures import Future, TimeoutError
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock, Thread
from typing import Protocol


class PendingRead(Protocol):
    def done(self) -> bool: ...


class ScheduleHandlerError(ValueError):
    pass


class ScheduleReads:
    """One daemon reader per controller; hung reads quarantine the lane, not retry."""

    def __init__(self, timeout: float = 2.0) -> None:
        if not math.isfinite(timeout) or not 0 < timeout <= 10:
            raise ValueError(
                "Schedule handler timeout must be positive and at most 10s."
            )
        self.timeout = timeout
        self._lock = Lock()
        self._future: PendingRead | None = None
        self._poisoned = False
        self._epoch = 0
        self._operation: ContextVar[tuple[float, int] | None] = ContextVar(
            "schedule_read_operation", default=None
        )

    @property
    def blocked(self) -> bool:
        return self._poisoned

    @contextmanager
    def operation(self) -> Generator[None]:
        current = self._operation.get()
        token = self._operation.set(
            current or (time.monotonic() + self.timeout, self._epoch)
        )
        try:
            yield
        finally:
            self._operation.reset(token)

    def check(self) -> None:
        operation = self._operation.get()
        if operation is not None and (
            time.monotonic() >= operation[0] or operation[1] != self._epoch
        ):
            raise ScheduleHandlerError("Schedule read operation expired or cancelled.")

    def cancel(self) -> None:
        with self._lock:
            self._epoch += 1
            if self._future is not None and not self._future.done():
                self._poisoned = True

    def reset(self) -> None:
        with self._lock:
            if self._future is not None and not self._future.done():
                raise ScheduleHandlerError("An abandoned read is still running.")
            self._future = None
            self._poisoned = False
            self._epoch += 1

    def call[T](self, read: Callable[[], T]) -> T:
        with self.operation():
            self.check()
            with self._lock:
                if self._poisoned or (
                    self._future is not None and not self._future.done()
                ):
                    raise ScheduleHandlerError(
                        "Schedule read lane is quarantined or busy."
                    )
                result: Future[T] = Future()
                self._future = result

            def run() -> None:
                try:
                    result.set_result(read())
                except BaseException as error:
                    result.set_exception(error)

            try:
                try:
                    Thread(target=run, name="mos-schedule-read", daemon=True).start()
                except Exception as error:
                    result.set_exception(error)
                    raise ScheduleHandlerError(
                        "Schedule read could not start."
                    ) from None
                while True:
                    self.check()
                    try:
                        value = result.result(timeout=0.01)
                    except TimeoutError:
                        if result.done():
                            raise ScheduleHandlerError(
                                "Schedule handler failed."
                            ) from None
                        continue
                    self.check()
                    return value
            except BaseException as error:
                if not result.done() or isinstance(error, ScheduleHandlerError):
                    with self._lock:
                        self._poisoned = True
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise ScheduleHandlerError(
                    "Schedule handler failed, expired or was cancelled."
                ) from None
