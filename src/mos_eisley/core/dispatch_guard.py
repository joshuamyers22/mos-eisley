"""Task-local trusted admission revalidation; never grants dispatch authority."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar

_guard: ContextVar[Callable[[], None] | None] = ContextVar(
    "dispatch_guard", default=None
)


def revalidate_dispatch() -> None:
    check = _guard.get()
    if check is not None:
        check()


@contextmanager
def dispatch_guard(check: Callable[[], None]) -> Generator[None]:
    token = _guard.set(check)
    try:
        yield
    finally:
        _guard.reset(token)
