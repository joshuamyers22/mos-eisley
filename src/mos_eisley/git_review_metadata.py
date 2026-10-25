"""Owner-controlled, reciprocal standard linked-worktree metadata admission.

No Git discovery runs here. These checks do not contain hostile same-owner races.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from mos_eisley.core.models import Contract, Digest, digest


class MetadataIdentity(Contract):
    device: int
    inode: int


class MetadataPointer(Contract):
    identity: MetadataIdentity
    sha256: Digest


class GitWorktreeBinding(Contract):
    admin: str
    common: str
    admin_identity: MetadataIdentity
    common_identity: MetadataIdentity
    namespace_identity: MetadataIdentity
    gitfile: MetadataPointer
    commondir: MetadataPointer
    backlink: MetadataPointer


def _owned(info: os.stat_result, *, directory: bool) -> MetadataIdentity:
    correct_type = (
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    )
    if (
        not correct_type
        or info.st_uid != os.getuid()
        or info.st_mode & 0o022
        or (not directory and info.st_nlink != 1)
    ):
        raise ValueError("Worktree metadata must be regular and owner-controlled.")
    return MetadataIdentity(device=info.st_dev, inode=info.st_ino)


def open_directory(path: Path) -> int:
    """Open an absolute canonical path without following any symlink component."""
    if not path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise ValueError("Git metadata requires a canonical absolute directory.")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _pointer(fd: int, name: str) -> tuple[bytes, MetadataPointer]:
    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(file_fd)
        identity = _owned(before, directory=False)
        if before.st_size > 4096:
            raise ValueError("Worktree metadata pointer exceeds its bound.")
        data = os.read(file_fd, 4097)
        after = os.fstat(file_fd)
        if (
            len(data) > 4096
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
                before.st_mode,
                before.st_uid,
                before.st_nlink,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
            )
            or len(data) != before.st_size
        ):
            raise ValueError("Worktree metadata pointer changed during acquisition.")
        return data, MetadataPointer(identity=identity, sha256=digest(data))
    finally:
        os.close(file_fd)


@dataclass(frozen=True)
class GitMetadataLayout:
    admin: Path
    common: Path
    binding: GitWorktreeBinding | None


def inspect_layout(workspace: Path, root_fd: int) -> GitMetadataLayout:
    """Accept a normal repository or a reciprocal .git/worktrees/NAME layout."""
    _owned(os.fstat(root_fd), directory=True)
    info = os.stat(".git", dir_fd=root_fd, follow_symlinks=False)
    if stat.S_ISDIR(info.st_mode):
        _owned(info, directory=True)
        return GitMetadataLayout(workspace / ".git", workspace / ".git", None)
    data, gitfile = _pointer(root_fd, ".git")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Worktree metadata pointer must be UTF-8.") from exc
    if not text.startswith("gitdir: ") or not text.endswith("\n"):
        raise ValueError("Worktree requires a canonical gitdir pointer.")
    raw = text[len("gitdir: ") : -1]
    admin = Path(raw)
    if (
        "\x00" in raw
        or "\n" in raw
        or str(admin) != raw
        or not admin.is_absolute()
        or ".." in admin.parts
    ):
        raise ValueError("Worktree requires a canonical absolute gitdir pointer.")
    if admin.parent.name != "worktrees" or admin.parent.parent.name != ".git":
        raise ValueError("Only standard linked-worktree metadata is supported.")
    common = admin.parent.parent
    if common == workspace / ".git":
        raise ValueError("Worktree metadata cannot redirect into its own gitfile.")
    common_fd = open_directory(common)
    try:
        # The creator checkout must protect its .git entry from other writers.
        _owned(os.stat("..", dir_fd=common_fd, follow_symlinks=False), directory=True)
        common_identity = _owned(os.fstat(common_fd), directory=True)
        namespace_fd = os.open(
            "worktrees", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=common_fd
        )
        try:
            namespace_identity = _owned(os.fstat(namespace_fd), directory=True)
            admin_fd = os.open(
                admin.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=namespace_fd,
            )
            try:
                admin_identity = _owned(os.fstat(admin_fd), directory=True)
                relative, commondir = _pointer(admin_fd, "commondir")
                back, backlink = _pointer(admin_fd, "gitdir")
                if (
                    relative != b"../..\n"
                    or back != os.fsencode(workspace / ".git") + b"\n"
                ):
                    raise ValueError(
                        "Worktree metadata requires reciprocal destinations."
                    )
            finally:
                os.close(admin_fd)
        finally:
            os.close(namespace_fd)
    finally:
        os.close(common_fd)
    return GitMetadataLayout(
        admin,
        common,
        GitWorktreeBinding(
            admin=str(admin),
            common=str(common),
            admin_identity=admin_identity,
            common_identity=common_identity,
            namespace_identity=namespace_identity,
            gitfile=gitfile,
            commondir=commondir,
            backlink=backlink,
        ),
    )
