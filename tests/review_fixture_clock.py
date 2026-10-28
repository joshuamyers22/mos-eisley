"""Scoped UTC for synthetic review fixtures; elapsed time remains monotonic."""

import sys
import time
from collections.abc import Callable
from datetime import UTC, timedelta, tzinfo
from datetime import datetime as RealDatetime
from unittest import TestCase
from unittest.mock import patch


class ReviewFixtureClock:
    def __init__(
        self,
        *,
        utc_now: Callable[[], RealDatetime] = lambda: RealDatetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._anchor = utc_now()
        self._monotonic = monotonic
        self._started = monotonic()

    def now(self) -> RealDatetime:
        return self._anchor + timedelta(seconds=self._monotonic() - self._started)


class _DatetimeMeta(type):
    def __instancecheck__(cls, instance: object) -> bool:
        return isinstance(instance, RealDatetime)


def install_review_fixture_clock(
    owner: TestCase, clock: ReviewFixtureClock | None = None
) -> ReviewFixtureClock:
    selected = clock if clock is not None else ReviewFixtureClock()

    class FixtureDatetime(RealDatetime, metaclass=_DatetimeMeta):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> RealDatetime:
            value = selected.now()
            return (
                value.astimezone(tz)
                if tz is not None
                else value.astimezone().replace(tzinfo=None)
            )

    # All modules are imported by unittest discovery before these test cases run.
    # Patch consumers, not stdlib datetime or the event loop's monotonic clock.
    # The owner restores every patch after this one synthetic fixture case.
    for name, module in tuple(sys.modules.items()):
        current = getattr(module, "datetime", None)
        if (
            name.startswith(("mos_eisley.", "test_", "tests.test_"))
            and isinstance(current, type)
            and issubclass(current, RealDatetime)
        ):
            owner.enterContext(patch.object(module, "datetime", FixtureDatetime))
    return selected
