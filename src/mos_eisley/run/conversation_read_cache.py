"""Bounded, operation-local reuse of completely verified archived artifact bytes."""

import hashlib
from collections.abc import Callable, Generator
from contextlib import closing
from types import TracebackType
from typing import Self

MAX_SAVE_CACHE_BYTES = 65_536


class ArtifactReadCache:
    """Keep eligible immutable chunks only after complete size/hash verification.

    The budget counts encoded payload bytes, not Python object overhead or total
    process RAM. Oversized and single-use inputs should bypass this cache.
    """

    def __init__(
        self,
        source: Callable[[str], Generator[bytes]],
        sizes: dict[str, int],
        eligible: frozenset[str],
        *,
        max_bytes: int = MAX_SAVE_CACHE_BYTES,
    ) -> None:
        if (
            type(max_bytes) is not int
            or not 0 <= max_bytes <= MAX_SAVE_CACHE_BYTES
            or not eligible <= sizes.keys()
            or any(type(sizes[sha]) is not int or sizes[sha] < 1 for sha in eligible)
        ):
            raise ValueError("invalid artifact read-cache budget or sizes")
        self._source = source
        self._sizes = dict(sizes)
        self._eligible = eligible
        self._maximum = max_bytes
        self._cached: dict[str, tuple[bytes, ...]] = {}
        self._bytes = 0
        self._closed = False
        self._reading = False

    @property
    def cached_bytes(self) -> int:
        return self._bytes

    def __enter__(self) -> Self:
        if self._closed:
            raise ValueError("artifact read cache is closed")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._cached.clear()
        self._bytes = 0
        self._closed = True

    def read(self, sha: str) -> Generator[bytes]:
        if self._closed:
            raise ValueError("artifact read cache is closed")
        if self._reading:
            raise ValueError("artifact cache reads must be sequential")
        self._reading = True
        try:
            yield from self._read(sha)
        finally:
            self._reading = False

    def _read(self, sha: str) -> Generator[bytes]:
        if (cached := self._cached.get(sha)) is not None:
            yield from cached
            return
        if sha not in self._eligible or self._sizes[sha] > self._maximum - self._bytes:
            with closing(self._source(sha)) as stream:
                yield from stream
            return
        expected = self._sizes[sha]
        chunks: list[bytes] = []
        size = 0
        checksum = hashlib.sha256()
        with closing(self._source(sha)) as stream:
            for chunk in stream:
                if type(chunk) is not bytes:
                    raise ValueError("artifact cache requires immutable byte chunks")
                size += len(chunk)
                if size > expected:
                    raise ValueError("artifact size changed during cache fill")
                checksum.update(chunk)
                chunks.append(chunk)
                yield chunk
        if self._closed or size != expected or checksum.hexdigest() != sha:
            raise ValueError("artifact integrity mismatch during cache fill")
        self._cached[sha] = tuple(chunks)
        self._bytes += size
