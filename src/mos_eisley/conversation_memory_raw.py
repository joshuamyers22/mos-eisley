"""Bounded exact-byte reads and preview-bound deletion for memory maintenance."""

import base64
import json
import os
import re
import stat
from collections.abc import Callable

from mos_eisley.conversation_memory import RECORD_BYTES
from mos_eisley.core.models import digest

MAX_RAW_REVIEW_BYTES = 4 * 1024 * 1024


class MemoryDiscardError(ValueError):
    """Carry returned unlink/flush progress for an interrupted deletion."""

    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(
            "Memory discard stopped; inspect the exact file before retrying."
        )
        self.receipt = receipt


def raw_file_identity(info: os.stat_result) -> dict[str, int]:
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "ctime_ns": info.st_ctime_ns,
        "mtime_ns": info.st_mtime_ns,
        "bytes": info.st_size,
        "owner_uid": info.st_uid,
    }


def verify_raw_record(root: int, name: str, record: dict[str, object]) -> None:
    info = os.stat(name, dir_fd=root, follow_symlinks=False)
    if raw_file_identity(info) != record["file_identity"] or info.st_nlink != 1:
        raise ValueError("Memory file changed; preview discard again.")


def read_raw_record(
    root: int, name: str, raw_sha256: str, max_bytes: int
) -> tuple[bytes, dict[str, object]]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_mode & 0o077
            or before.st_nlink != 1
        ):
            raise ValueError("Discard requires a private, single-link regular file.")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            payload = stream.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError(
                "Memory file exceeds the 256 KiB review limit."
                if max_bytes == RECORD_BYTES
                else "Memory file exceeds the requested review byte limit."
            )
        if digest(payload) != raw_sha256:
            raise ValueError("Memory bytes do not match the reviewed raw hash.")
        for current in (
            os.fstat(fd),
            os.stat(name, dir_fd=root, follow_symlinks=False),
        ):
            if (
                current.st_dev != before.st_dev
                or current.st_ino != before.st_ino
                or current.st_ctime_ns != before.st_ctime_ns
                or current.st_size != before.st_size
                or current.st_nlink != 1
            ):
                raise ValueError("Memory file changed; preview discard again.")
        return payload, {
            "raw_sha256": raw_sha256,
            "raw_bytes_base64": base64.b64encode(payload).decode("ascii"),
            "review_max_bytes": max_bytes,
            "file_identity": raw_file_identity(before),
        }
    finally:
        os.close(fd)


def discard_reviewed(
    root: int,
    name: str,
    inspect: Callable[[], dict[str, object]],
    expected_sha256: str | None,
    error_type: type[MemoryDiscardError],
) -> dict[str, object]:
    body = inspect()
    preview_hash = digest(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    )
    receipt: dict[str, object] = {
        **body,
        "preview_sha256": preview_hash,
        "status": "planned",
        "removed": False,
        "synced": False,
    }
    if expected_sha256 is None:
        return receipt
    if expected_sha256 != preview_hash or inspect() != body:
        raise ValueError("Memory discard changed; preview it again.")
    try:
        os.unlink(name, dir_fd=root)
        receipt["removed"] = True
        os.fsync(root)
        receipt["synced"] = True
    except OSError as error:
        receipt["status"] = "incomplete"
        raise error_type(receipt) from error
    receipt["status"] = "completed"
    return receipt


def validate_raw_review(
    raw_sha256: str, expected_sha256: str | None, max_bytes: int
) -> None:
    for value in (raw_sha256, expected_sha256):
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("Discard requires lowercase SHA-256 hashes.")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_RAW_REVIEW_BYTES:
        raise ValueError("--review-max-bytes must be between 1 and 4,194,304.")
