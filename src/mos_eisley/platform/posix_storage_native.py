"""Bounded descriptor ACL/filesystem queries for direct POSIX qualification."""

import ctypes
import errno
import os
import platform
import struct
import sys
from typing import Protocol, cast

from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.storage import StorageAdmissionError

MAX_SECURITY_BYTES = 64 * 1024


class _Function(Protocol):
    argtypes: list[object]
    restype: object

    def __call__(self, *args: object) -> int: ...


class _AttrList(ctypes.Structure):
    _fields_ = [
        ("bitmapcount", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16),
        ("common", ctypes.c_uint32),
        ("volume", ctypes.c_uint32),
        ("directory", ctypes.c_uint32),
        ("file", ctypes.c_uint32),
        ("fork", ctypes.c_uint32),
    ]


def require_candidate_host() -> str:
    if (
        sys.platform not in {"darwin", "linux"}
        or struct.calcsize("P") != 8
        or sys.byteorder != "little"
        or platform.machine() not in {"arm64", "aarch64", "x86_64"}
    ):
        raise UnsupportedPlatformError("private-root native ABI is unqualified")
    if sys.platform == "linux":
        if platform.machine() not in {"aarch64", "x86_64"}:
            raise UnsupportedPlatformError("private-root native ABI is unqualified")
        try:
            libc_version = os.confstr("CS_GNU_LIBC_VERSION") or ""
        except (ValueError, OSError):
            raise UnsupportedPlatformError("private-root libc is unqualified") from None
        if not libc_version.startswith("glibc "):
            raise UnsupportedPlatformError("private-root libc is unqualified")
    return sys.platform


def _function(library: object, name: str, args: list[object]) -> _Function:
    result = cast(_Function, getattr(library, name))
    result.argtypes = args
    result.restype = ctypes.c_int
    return result


def validate_linux_base_acl(payload: bytes, mode: int) -> None:
    # Linux UAPI: version u32 followed by (tag u16, perm u16, id u32).
    expected = struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, perm, 0xFFFFFFFF)
        for tag, perm in ((1, (mode >> 6) & 7), (4, 0), (32, 0))
    )
    if payload != expected:
        raise StorageAdmissionError("directory access ACL is not base-mode equivalent")


def validate_darwin_security(payload: bytes) -> None:
    if len(payload) < 12:
        raise StorageAdmissionError("invalid directory security attributes")
    length, offset, size = struct.unpack_from("<IiI", payload)
    start = 4 + offset
    if length != len(payload) or start < 12 or start + size > length:
        raise StorageAdmissionError("invalid directory security bounds")
    if (length, offset, size) == (12, 8, 0):
        return
    if size != 44:
        raise StorageAdmissionError("directory has extended or unknown ACL")
    magic = struct.unpack_from("<I", payload, start)[0]
    count, flags = struct.unpack_from("<II", payload, start + 36)
    if (
        magic != 0x012CC16D
        or count not in (0, 0xFFFFFFFF)
        or flags != 0
        or payload[start + 4 : start + 36] != bytes(32)
    ):
        raise StorageAdmissionError("directory has extended or unknown ACL")


class NativeRootQueries:
    def __init__(self) -> None:
        self._host = require_candidate_host()
        library = ctypes.CDLL(
            "/usr/lib/libSystem.B.dylib" if self._host == "darwin" else None,
            use_errno=True,
        )
        self._library = library
        self._statfs = _function(
            library,
            "fstatfs$INODE64"
            if self._host == "darwin" and platform.machine() == "x86_64"
            else "fstatfs",
            [ctypes.c_int, ctypes.c_void_p],
        )
        if self._host == "darwin":
            self._security = _function(
                library,
                "fgetattrlist",
                [
                    ctypes.c_int,
                    ctypes.POINTER(_AttrList),
                    ctypes.c_void_p,
                    ctypes.c_size_t,
                    ctypes.c_ulong,
                ],
            )
        else:
            self._security = _function(
                library,
                "fgetxattr",
                [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t],
            )
            self._security.restype = ctypes.c_ssize_t

    def filesystem(self, fd: int) -> tuple[str, bytes, int, int]:
        # Exact LP64 output layouts, independent of path names and mount tables.
        buffer = ctypes.create_string_buffer(2168 if self._host == "darwin" else 120)
        if self._statfs(fd, buffer) != 0:
            raise StorageAdmissionError("directory filesystem query failed")
        raw = buffer.raw
        if self._host == "darwin":
            flags = struct.unpack_from("<I", raw, 64)[0]
            if raw[72:88].split(b"\0", 1)[0] != b"apfs" or not flags & 0x1000:
                raise StorageAdmissionError("directory filesystem is unqualified")
            extended_flags = struct.unpack_from("<I", raw, 2136)[0]
            if flags & (0x200 | 0x200000) or extended_flags & ~1:
                raise StorageAdmissionError("directory mount protection is unqualified")
            return "darwin-local-apfs-v1", raw[48:56], flags, extended_flags
        magic = struct.unpack_from("<q", raw)[0]
        flags = struct.unpack_from("<q", raw, 80)[0]
        if magic != 0xEF53 or not flags & 0x20 or flags & ~0x1FFF:
            raise StorageAdmissionError("directory filesystem is unqualified")
        return "linux-glibc-ext-family-v1", raw[56:64], flags, 0

    def protection(self, fd: int, mode: int) -> None:
        buffer = ctypes.create_string_buffer(MAX_SECURITY_BYTES)
        if self._host == "darwin":
            # SDK _PC_EXTENDED_SECURITY_NP: unsupported cannot mean absent ACL.
            if os.fpathconf(fd, 13) != 1:
                raise StorageAdmissionError("directory ACL inspection is unsupported")
            attrs = _AttrList(5, 0, 0x00400000, 0, 0, 0, 0)
            if self._security(fd, ctypes.byref(attrs), buffer, len(buffer), 0) != 0:
                raise StorageAdmissionError("directory security query failed")
            length = struct.unpack_from("<I", buffer.raw)[0]
            if not 12 <= length <= MAX_SECURITY_BYTES:
                raise StorageAdmissionError("invalid directory security length")
            validate_darwin_security(buffer.raw[:length])
            return
        for name in (b"system.posix_acl_access", b"system.posix_acl_default"):
            ctypes.set_errno(0)
            size = self._security(fd, name, buffer, len(buffer))
            if size == -1 and ctypes.get_errno() == errno.ENODATA:
                continue
            if not 0 <= size <= MAX_SECURITY_BYTES:
                raise StorageAdmissionError("directory ACL query failed")
            if name == b"system.posix_acl_default":
                raise StorageAdmissionError("directory has a default ACL")
            validate_linux_base_acl(buffer.raw[:size], mode)

    def read_once(self, fd: int, count: int) -> bytes:
        """One bounded native read, including EINTR in the caller's attempt cap."""
        if not 0 < count <= 4097:
            raise ValueError("invalid namespace read capacity")
        read = _function(
            self._library, "read", [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
        )
        read.restype = ctypes.c_ssize_t
        buffer = ctypes.create_string_buffer(count)
        ctypes.set_errno(0)
        size = read(fd, buffer, count)
        if size == -1 and ctypes.get_errno() == errno.EINTR:
            raise InterruptedError("namespace read interrupted")
        if not 0 <= size <= count:
            raise StorageAdmissionError("namespace native read failed")
        return buffer.raw[:size]
