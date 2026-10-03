"""Bounded regular-file contract; unsupported platforms fail before file I/O."""

import sys
from pathlib import Path


class UnsupportedPlatformError(OSError):
    """No qualified implementation exists for the current platform."""


def read_regular_file(path: Path, limit: int) -> bytes:
    """Return at most limit bytes, refusing oversized and nonregular inputs.

    A limit must be a nonnegative integer (bool is excluded). Only the final
    path component is protected against symlinks; this is not a containment,
    ownership, hardlink or content-snapshot policy.
    """
    if type(limit) is not int or limit < 0:
        raise ValueError("byte limit must be a nonnegative integer")
    if sys.platform not in {"darwin", "linux"}:
        raise UnsupportedPlatformError("bounded file reading is unsupported here")
    from mos_eisley.platform.posix_files import read_regular_file as posix_read

    return posix_read(path, limit)
