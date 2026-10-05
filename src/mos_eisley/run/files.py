"""Compatibility entry point for bounded regular-file reads."""

from pathlib import Path

from mos_eisley.platform.files import read_regular_file


def read_bounded(path: Path, limit: int = 2_000_000) -> bytes:
    return read_regular_file(path, limit)
