"""Bounded save-local artifact reuse, complete verification and cancellation."""

from collections import Counter
from collections.abc import Generator
from contextlib import closing
from typing import cast
from unittest import TestCase

from mos_eisley.core.models import digest
from mos_eisley.run.conversation_read_cache import (
    MAX_SAVE_CACHE_BYTES,
    ArtifactReadCache,
)


class Source:
    def __init__(self, *payloads: bytes) -> None:
        self.values = {digest(payload): payload for payload in payloads}
        self.calls: Counter[str] = Counter()
        self.closed: Counter[str] = Counter()
        self.fail_after_last_chunk = False

    def read(self, sha: str) -> Generator[bytes]:
        self.calls[sha] += 1
        payload = self.values[sha]
        try:
            for offset in range(0, len(payload), 32_768):
                yield payload[offset : offset + 32_768]
            if self.fail_after_last_chunk:
                raise ValueError("source integrity check failed")
        finally:
            self.closed[sha] += 1

    def cache(self, maximum: int = MAX_SAVE_CACHE_BYTES) -> ArtifactReadCache:
        return ArtifactReadCache(
            self.read,
            {sha: len(payload) for sha, payload in self.values.items()},
            frozenset(self.values),
            max_bytes=maximum,
        )


class ArtifactReadCacheTests(TestCase):
    def test_verified_chunks_are_reused_at_exact_budget_and_released_on_exit(
        self,
    ) -> None:
        payload = b"x" * MAX_SAVE_CACHE_BYTES
        sha = digest(payload)
        source = Source(payload)
        with source.cache() as cache:
            for _ in range(3):
                chunks = list(cache.read(sha))
                self.assertEqual(b"".join(chunks), payload)
                self.assertEqual(len(chunks), 2)
            self.assertEqual(source.calls[sha], 1)
            self.assertEqual(source.closed[sha], 1)
            self.assertEqual(cache.cached_bytes, MAX_SAVE_CACHE_BYTES)
        self.assertEqual(cache.cached_bytes, 0)
        with self.assertRaisesRegex(ValueError, "closed"):
            list(cache.read(sha))
        with self.assertRaisesRegex(ValueError, "closed"), cache:
            self.fail("closed cache entered")

    def test_aggregate_budget_bypasses_values_that_do_not_fit(self) -> None:
        first, second = b"a" * 40_000, b"b" * 40_000
        source = Source(first, second)
        with source.cache() as cache:
            for payload in (first, second, first, second):
                self.assertEqual(b"".join(cache.read(digest(payload))), payload)
                self.assertLessEqual(cache.cached_bytes, MAX_SAVE_CACHE_BYTES)
            self.assertEqual(cache.cached_bytes, len(first))
        self.assertEqual(source.calls[digest(first)], 1)
        self.assertEqual(source.calls[digest(second)], 2)

    def test_oversized_and_ineligible_values_stream_without_caching(self) -> None:
        small, large = b"small", b"x" * (MAX_SAVE_CACHE_BYTES + 1)
        source = Source(small, large)
        with ArtifactReadCache(
            source.read,
            {digest(large): len(large)},
            frozenset({digest(large)}),
        ) as cache:
            for payload in (small, large, small, large):
                self.assertEqual(b"".join(cache.read(digest(payload))), payload)
                self.assertEqual(cache.cached_bytes, 0)
        self.assertTrue(all(count == 2 for count in source.calls.values()))

    def test_source_failure_after_last_chunk_does_not_publish_cache(self) -> None:
        payload = b"verified only when source finishes"
        sha = digest(payload)
        source = Source(payload)
        source.fail_after_last_chunk = True
        with source.cache() as cache:
            with self.assertRaisesRegex(ValueError, "source integrity"):
                list(cache.read(sha))
            self.assertEqual(cache.cached_bytes, 0)
            self.assertEqual(source.closed[sha], 1)
            source.fail_after_last_chunk = False
            self.assertEqual(b"".join(cache.read(sha)), payload)
            self.assertEqual(b"".join(cache.read(sha)), payload)
            self.assertEqual(source.calls[sha], 2)

    def test_partial_consumption_closes_source_and_releases_fill(self) -> None:
        payload = b"x" * MAX_SAVE_CACHE_BYTES
        sha = digest(payload)
        source = Source(payload)
        with source.cache() as cache:
            with closing(cache.read(sha)) as stream:
                self.assertEqual(len(next(stream)), 32_768)
                self.assertEqual(cache.cached_bytes, 0)
            self.assertEqual(source.closed[sha], 1)
            self.assertEqual(cache.cached_bytes, 0)
            self.assertEqual(b"".join(cache.read(sha)), payload)
            self.assertEqual(source.calls[sha], 2)

    def test_reentrant_reads_cannot_overcommit_fill_budget(self) -> None:
        first, second = b"a" * 40_000, b"b" * 40_000
        source = Source(first, second)
        with source.cache() as cache:
            with closing(cache.read(digest(first))) as stream:
                next(stream)
                with self.assertRaisesRegex(ValueError, "sequential"):
                    list(cache.read(digest(second)))
            self.assertEqual(b"".join(cache.read(digest(second))), second)
            self.assertEqual(cache.cached_bytes, len(second))

    def test_size_and_digest_mismatches_never_populate_cache(self) -> None:
        expected = b"expected"
        sha = digest(expected)
        for payload in (b"short", b"longer than expected", b"modified"):
            source = Source(expected)
            source.values[sha] = payload
            with (
                self.subTest(payload=payload),
                ArtifactReadCache(
                    source.read, {sha: len(expected)}, frozenset({sha})
                ) as cache,
            ):
                with self.assertRaises(ValueError):
                    list(cache.read(sha))
                self.assertEqual(cache.cached_bytes, 0)
                self.assertEqual(source.closed[sha], 1)

    def test_mutable_chunks_cannot_enter_cache(self) -> None:
        payload = b"immutable"
        sha = digest(payload)

        def source(_: str) -> Generator[bytes]:
            yield cast(bytes, bytearray(payload))

        with ArtifactReadCache(source, {sha: len(payload)}, frozenset({sha})) as cache:
            with self.assertRaisesRegex(ValueError, "immutable"):
                list(cache.read(sha))
            self.assertEqual(cache.cached_bytes, 0)

    def test_new_operation_reads_source_again_and_checks_changed_content(self) -> None:
        payload = b"original"
        sha = digest(payload)
        source = Source(payload)
        with source.cache() as cache:
            list(cache.read(sha))
        source.values[sha] = b"modified"
        with source.cache() as cache, self.assertRaisesRegex(ValueError, "integrity"):
            list(cache.read(sha))
        self.assertEqual(source.calls[sha], 2)

    def test_invalid_limits_and_metadata_are_rejected_and_zero_bypasses(self) -> None:
        source = Source(b"valid")
        for maximum in (True, -1, MAX_SAVE_CACHE_BYTES + 1):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                source.cache(maximum)
        sha = digest(b"valid")
        invalid_sizes: tuple[dict[str, int], ...] = ({}, {sha: 0}, {sha: True})
        for sizes in invalid_sizes:
            with self.subTest(sizes=sizes), self.assertRaises(ValueError):
                ArtifactReadCache(source.read, sizes, frozenset({sha}))
        with source.cache(0) as cache:
            list(cache.read(sha))
            list(cache.read(sha))
            self.assertEqual(cache.cached_bytes, 0)
        self.assertEqual(source.calls[sha], 2)
