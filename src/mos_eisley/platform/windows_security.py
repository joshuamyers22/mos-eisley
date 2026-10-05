"""Pure bounded owner/DACL decoding; metadata grants no live storage authority."""

import struct
from dataclasses import dataclass, field
from typing import Literal

from mos_eisley.platform.identity import WindowsPrincipal

MAX_DIRECTORY_SECURITY_BYTES = 65_536
_HEADER_SIZE = 20
_FILE_ALL_ACCESS = 0x001F01FF
_CONTROLS = (0x9004, 0x9404)


class WindowsSecurityDecodeError(ValueError):
    """Bytes do not match the bounded private-directory security profile."""


@dataclass(frozen=True, slots=True)
class WindowsPrivateDacl:
    """Normalized untrusted metadata, never a live observation or owned lease."""

    owner: WindowsPrincipal = field(repr=False)
    control: int = field(repr=False)
    policy_id: Literal["windows-private-directory-owner-dacl-v1"] = field(
        default="windows-private-directory-owner-dacl-v1", init=False
    )
    acl_revision: Literal[2] = field(default=2, init=False)
    ace_type: Literal[0] = field(default=0, init=False)
    ace_flags: Literal[0] = field(default=0, init=False)
    access_mask: int = field(default=_FILE_ALL_ACCESS, init=False)

    def __post_init__(self) -> None:
        if (
            type(self.owner) is not WindowsPrincipal
            or type(self.control) is not int
            or self.control not in _CONTROLS
        ):
            raise WindowsSecurityDecodeError("invalid directory security metadata")


def _extent(offset: int, size: int, limit: int) -> int:
    if offset < 0 or size < 0 or offset > limit or size > limit - offset:
        raise WindowsSecurityDecodeError("invalid directory security extent")
    return offset + size


def _sid(payload: bytes, offset: int, limit: int) -> tuple[bytes, int]:
    _extent(offset, 8, limit)
    revision, count = payload[offset], payload[offset + 1]
    if revision != 1 or count > 15:
        raise WindowsSecurityDecodeError("invalid directory security SID")
    end = _extent(offset, 8 + 4 * count, limit)
    return payload[offset:end], end


def decode_private_directory_security(
    payload: bytes, expected: WindowsPrincipal
) -> WindowsPrivateDacl:
    """Decode the frozen owner-only profile without querying any native state.

    Only exact immutable byte/principal inputs are admitted. At most two bounded
    SIDs are copied; offsets and ACL slack never become authority or native pointers.
    """
    if (
        type(payload) is not bytes
        or not _HEADER_SIZE <= len(payload) <= MAX_DIRECTORY_SECURITY_BYTES
        or type(expected) is not WindowsPrincipal
    ):
        raise WindowsSecurityDecodeError("invalid directory security input")
    revision, reserved, control, owner, group, sacl, dacl = struct.unpack_from(
        "<BBHIIII", payload
    )
    if revision != 1 or reserved != 0 or control not in _CONTROLS or group or sacl:
        raise WindowsSecurityDecodeError("unsupported directory security header")
    for offset in (owner, dacl):
        if offset < _HEADER_SIZE or offset % 4:
            raise WindowsSecurityDecodeError("invalid directory security offset")
    owner_sid, owner_end = _sid(payload, owner, len(payload))
    if owner_sid != expected.sid:
        raise WindowsSecurityDecodeError("directory security owner mismatch")
    _extent(dacl, 8, len(payload))
    acl_revision, reserved1, acl_size, ace_count, reserved2 = struct.unpack_from(
        "<BBHHH", payload, dacl
    )
    if (
        acl_revision != 2
        or reserved1 != 0
        or reserved2 != 0
        or acl_size < 8
        or acl_size % 4
        or ace_count != 1
    ):
        raise WindowsSecurityDecodeError("unsupported directory security ACL")
    acl_end = _extent(dacl, acl_size, len(payload))
    if owner < acl_end and dacl < owner_end:
        raise WindowsSecurityDecodeError("overlapping directory security components")
    ace = dacl + 8
    _extent(ace, 8, acl_end)
    ace_type, ace_flags, ace_size, access_mask = struct.unpack_from(
        "<BBHI", payload, ace
    )
    if ace_type != 0 or ace_flags != 0 or access_mask != _FILE_ALL_ACCESS:
        raise WindowsSecurityDecodeError("unsupported directory security ACE")
    ace_end = _extent(ace, ace_size, acl_end)
    ace_sid, sid_end = _sid(payload, ace + 8, ace_end)
    if sid_end != ace_end or ace_sid != owner_sid:
        raise WindowsSecurityDecodeError("invalid directory security ACE trustee")
    return WindowsPrivateDacl(expected, control)
