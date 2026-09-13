"""Private, bounded files for explicitly adopted project guidance."""

import os
import stat
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from uuid import uuid4

from mos_eisley.conversation_memory_raw import raw_file_identity

GUIDANCE_FILE_BYTES = 512 * 1024


@dataclass(frozen=True)
class GuidanceFile:
    payload: bytes
    identity: dict[str, int]


def read_file(root: int | None, name: str) -> GuidanceFile | None:
    if root is None:
        return None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
        ):
            raise ValueError("Guidance requires private, owner-held regular files.")
        payload = stream.read(GUIDANCE_FILE_BYTES + 1)
        if len(payload) > GUIDANCE_FILE_BYTES:
            raise ValueError("Guidance file exceeds 512 KiB.")
        for current in (
            os.fstat(stream.fileno()),
            os.stat(name, dir_fd=root, follow_symlinks=False),
        ):
            if (
                raw_file_identity(current) != raw_file_identity(info)
                or current.st_mode != info.st_mode
                or current.st_nlink != 1
            ):
                raise ValueError("Guidance file changed; review again.")
    return GuidanceFile(payload, raw_file_identity(info))


def publish_file(
    root: int,
    name: str,
    payload: bytes,
    verify: Callable[[], None],
    *,
    immutable: bool = False,
) -> None:
    if len(payload) > GUIDANCE_FILE_BYTES:
        raise ValueError("Guidance file exceeds 512 KiB.")
    verify()
    if immutable:
        existing = read_file(root, name)
        if existing is not None:
            if existing.payload != payload:
                raise ValueError("Pinned guidance snapshot is corrupt.")
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
            try:
                if raw_file_identity(os.fstat(fd)) != existing.identity:
                    raise ValueError("Pinned guidance snapshot changed.")
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(root)
            verify()
            if read_file(root, name) != existing:
                raise ValueError("Pinned guidance snapshot changed.")
            return
    temporary = ".guidance-" + uuid4().hex + ".tmp"
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=root,
    )
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        staged = read_file(root, temporary)
        if (
            staged is None
            or staged.payload != payload
            or staged.identity["device"] != created.st_dev
            or staged.identity["inode"] != created.st_ino
        ):
            raise ValueError("Staged guidance changed before publication.")
        verify()
        if immutable:
            os.link(
                temporary, name, src_dir_fd=root, dst_dir_fd=root, follow_symlinks=False
            )
            os.unlink(temporary, dir_fd=root)
        else:
            os.replace(temporary, name, src_dir_fd=root, dst_dir_fd=root)
        os.fsync(root)
    finally:
        with suppress(FileNotFoundError):
            named = os.stat(temporary, dir_fd=root, follow_symlinks=False)
            if (named.st_dev, named.st_ino) == (created.st_dev, created.st_ino):
                os.unlink(temporary, dir_fd=root)
