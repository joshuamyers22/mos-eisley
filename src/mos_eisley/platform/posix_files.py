"""Qualified POSIX descriptor admission for the bounded-reader contract."""

import os
import stat
from pathlib import Path


def read_regular_file(path: Path, limit: int) -> bytes:
    # Final-component symlink replacement cannot bypass O_NOFOLLOW. O_NONBLOCK
    # admits FIFOs without waiting so the opened descriptor can be rejected.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        stream = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("input must be a regular file")
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("input exceeds the byte limit")
    return payload
