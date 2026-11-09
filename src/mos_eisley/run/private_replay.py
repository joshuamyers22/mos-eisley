"""Descriptor-bound private reads for recorded review replay, not portable input."""

import os
import stat
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.posix_identity import current_principal


def _stamp(info: os.stat_result) -> tuple[int, ...]:
    # Reading may update atime; protection, identity and content metadata may not.
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_gid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _admit(info: os.stat_result, uid: int, *, directory: bool = False) -> None:
    if (
        not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or info.st_uid != uid
        or info.st_mode & 0o077
        or (not directory and info.st_nlink != 1)
    ):
        raise ValueError("replay requires private storage owned by this user")


@dataclass(frozen=True)
class ReplayDirectory:
    fd: int
    uid: int

    def read(self, name: str, limit: int) -> bytes:
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("invalid replay artifact name")
        if type(limit) is not int or limit < 0:
            raise ValueError("invalid replay byte limit")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            _admit(before, self.uid)
            if before.st_size > limit:
                raise ValueError("replay input exceeds the byte limit")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                payload = stream.read(limit + 1)
            if len(payload) > limit:
                raise ValueError("replay input exceeds the byte limit")
            if (
                _stamp(os.fstat(fd)) != _stamp(before)
                or _stamp(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                != _stamp(before)
                or current_principal().uid != self.uid
            ):
                raise ValueError("replay artifact changed during reading")
            return payload
        finally:
            os.close(fd)


@contextmanager
def private_replay(path: Path) -> Generator[ReplayDirectory]:
    if sys.platform not in {"darwin", "linux"}:
        raise UnsupportedPlatformError("private recorded replay is unsupported here")
    uid = current_principal().uid
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        _admit(before, uid, directory=True)
        yield ReplayDirectory(fd, uid)
        if (
            _stamp(os.fstat(fd)) != _stamp(before)
            or _stamp(os.stat(path, follow_symlinks=False)) != _stamp(before)
            or current_principal().uid != uid
        ):
            raise ValueError("replay directory changed during reading")
    finally:
        os.close(fd)
