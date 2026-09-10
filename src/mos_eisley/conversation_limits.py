"""Independent bounds for retained snapshots and catalog scan work."""

from typing import Annotated

from pydantic import Field

DEFAULT_SNAPSHOT_BYTES = 2_000_000
MIN_SNAPSHOT_BYTES = 64_000
MAX_SNAPSHOT_BYTES = 32_000_000
MAX_CATALOG_SCAN_BYTES = 128_000_000

SnapshotByteLimit = Annotated[int, Field(ge=MIN_SNAPSHOT_BYTES, le=MAX_SNAPSHOT_BYTES)]


def snapshot_byte_limit(value: str) -> int:
    maximum = int(value)
    if not MIN_SNAPSHOT_BYTES <= maximum <= MAX_SNAPSHOT_BYTES:
        raise ValueError("session byte limit must be between 64000 and 32000000")
    return maximum


def catalog_byte_limit(value: str) -> int:
    maximum = int(value)
    if not 1 <= maximum <= MAX_CATALOG_SCAN_BYTES:
        raise ValueError("catalog byte limit must be between 1 and 128000000")
    return maximum
