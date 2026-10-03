"""Contextual identity values and inert, fail-closed query entry points.

Values identify principals/objects within established host and namespace scope.
They do not authorize access, bind paths, prove content integrity or provide leases.
"""

import struct
import sys
from dataclasses import dataclass, field
from typing import Literal

from mos_eisley.platform.files import UnsupportedPlatformError


def _nonnegative_integer(value: object) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("identity component must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class PosixPrincipal:
    uid: int = field(repr=False)
    kind: Literal["posix-uid"] = field(default="posix-uid", init=False)

    def __post_init__(self) -> None:
        _nonnegative_integer(self.uid)


@dataclass(frozen=True, slots=True)
class WindowsPrincipal:
    sid: bytes = field(repr=False)
    kind: Literal["windows-sid"] = field(default="windows-sid", init=False)

    def __post_init__(self) -> None:
        if (
            type(self.sid) is not bytes
            or not 8 <= len(self.sid) <= 68
            or self.sid[0] != 1
            or self.sid[1] > 15
            or len(self.sid) != 8 + 4 * self.sid[1]
        ):
            raise ValueError("identity requires a valid bounded binary SID")


@dataclass(frozen=True, slots=True)
class PosixFileIdentity:
    device: int = field(repr=False)
    inode: int = field(repr=False)
    kind: Literal["posix-file"] = field(default="posix-file", init=False)

    def __post_init__(self) -> None:
        _nonnegative_integer(self.device)
        _nonnegative_integer(self.inode)


@dataclass(frozen=True, slots=True)
class WindowsFileIdentity:
    volume_serial: int = field(repr=False)
    file_id: bytes = field(repr=False)
    kind: Literal["windows-file"] = field(default="windows-file", init=False)

    def __post_init__(self) -> None:
        _nonnegative_integer(self.volume_serial)
        if self.volume_serial >= 2**64:
            raise ValueError("identity volume serial exceeds its native width")
        if type(self.file_id) is not bytes or len(self.file_id) != 16:
            raise ValueError("identity requires a full-width binary file ID")


PrincipalIdentity = PosixPrincipal | WindowsPrincipal
FileIdentity = PosixFileIdentity | WindowsFileIdentity


@dataclass(frozen=True, slots=True)
class PosixDescriptor:
    """A borrowed descriptor; caller must keep it live throughout the query."""

    fd: int = field(repr=False)

    def __post_init__(self) -> None:
        _nonnegative_integer(self.fd)
        if self.fd > 2**31 - 1:
            raise ValueError("descriptor exceeds its qualified native width")


@dataclass(frozen=True, slots=True)
class WindowsHandle:
    """A borrowed native HANDLE, distinct from a CRT file descriptor."""

    value: int = field(repr=False)

    def __post_init__(self) -> None:
        _nonnegative_integer(self.value)
        invalid_handle = 2 ** (8 * struct.calcsize("P")) - 1
        if self.value == 0 or self.value >= invalid_handle:
            raise ValueError("invalid native handle value")


class IdentityContextError(OSError):
    """Current context cannot be admitted under the identity contract."""


class IdentityQueryError(OSError):
    """An opened-object or current-principal query failed safely."""


def _require_posix() -> None:
    if sys.platform not in {"darwin", "linux"}:
        raise UnsupportedPlatformError("identity queries are unsupported here")


def current_principal() -> PrincipalIdentity:
    """Query a fresh real UID, refusing unequal real/effective UID context."""
    _require_posix()
    from mos_eisley.platform.posix_identity import current_principal as query

    return query()


def file_identity(opened: PosixDescriptor | WindowsHandle) -> FileIdentity:
    """Inspect a borrowed live file/directory reference without path lookup.

    Comparison requires common host/filesystem scope and live original objects.
    Identity equality neither admits private storage nor guarantees stable content.
    """
    if type(opened) not in (PosixDescriptor, WindowsHandle):
        raise ValueError("identity query requires a typed borrowed reference")
    _require_posix()
    if not isinstance(opened, PosixDescriptor):
        raise ValueError("reference kind does not match the qualified platform")
    from mos_eisley.platform.posix_identity import file_identity as query

    return query(opened)
