"""Bounded regular-file reads, rejecting symlinks and special files."""

import os
import stat
from pathlib import Path


def read_bounded(path: Path, limit: int = 2_000_000) -> bytes:
    # O_NOFOLLOW closes the final-component lstat/open race. O_NONBLOCK avoids
    # waiting on a malicious FIFO before fstat can reject it.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("input must be a regular file")
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("input exceeds the byte limit")
    return payload
