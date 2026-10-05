"""Pure bounded identity codecs; decoded metadata grants no owner/storage trust."""

import json
import re
from dataclasses import dataclass, field
from typing import Literal, cast

from mos_eisley.platform.identity import (
    FileIdentity,
    PosixFileIdentity,
    PosixPrincipal,
    PrincipalIdentity,
    WindowsFileIdentity,
    WindowsPrincipal,
)

MAX_IDENTITY_WIRE_BYTES = 4096


class IdentityWireError(ValueError):
    """Unsupported, malformed, noncanonical or oversized identity representation."""


def _namespace(value: str) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise IdentityWireError("invalid identity namespace")


@dataclass(frozen=True, slots=True)
class OwnerBinding:
    namespace_id: str = field(repr=False)
    principal: PrincipalIdentity = field(repr=False)

    def __post_init__(self) -> None:
        _namespace(self.namespace_id)
        if type(self.principal) not in (PosixPrincipal, WindowsPrincipal):
            raise IdentityWireError("invalid principal value")


@dataclass(frozen=True, slots=True)
class NamespaceRecord:
    """Untrusted namespace metadata; never proof of custody or enrollment."""

    namespace_id: str = field(repr=False)
    principal: PrincipalIdentity = field(repr=False)
    migration_verification_key_sha256: str = field(repr=False)
    kind: Literal["identity-namespace"] = field(
        default="identity-namespace", init=False
    )
    schema_version: Literal[1] = field(default=1, init=False)

    def __post_init__(self) -> None:
        _namespace(self.namespace_id)
        if type(self.principal) not in (PosixPrincipal, WindowsPrincipal):
            raise IdentityWireError("invalid principal value")
        _hex(self.migration_verification_key_sha256, 64, 64)


@dataclass(frozen=True, slots=True)
class ScopedFileIdentity:
    namespace_id: str = field(repr=False)
    identity: FileIdentity = field(repr=False)

    def __post_init__(self) -> None:
        _namespace(self.namespace_id)
        if type(self.identity) not in (PosixFileIdentity, WindowsFileIdentity):
            raise IdentityWireError("invalid file identity value")


def _encode(value: dict[str, object]) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise IdentityWireError("invalid identity encoding") from None
    if len(payload) > MAX_IDENTITY_WIRE_BYTES:
        raise IdentityWireError("identity encoding exceeds limit")
    return payload


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise IdentityWireError("duplicate identity member")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise IdentityWireError("invalid JSON constant")


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise IdentityWireError("identity requires an object")
    return cast(dict[str, object], value)


def _decode(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_IDENTITY_WIRE_BYTES:
        raise IdentityWireError("invalid identity byte input")
    try:
        value = _object(
            cast(
                object,
                json.loads(
                    payload.decode("utf-8"),
                    object_pairs_hook=_pairs,
                    parse_constant=_constant,
                ),
            )
        )
        if _encode(value) != payload:
            raise IdentityWireError("identity encoding is not canonical")
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise IdentityWireError("invalid identity encoding") from None


def _members(value: dict[str, object], *names: str) -> None:
    if set(value) != set(names):
        raise IdentityWireError("invalid identity members")


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise IdentityWireError("invalid identity integer")
    return value


def _hex(value: object, minimum: int, maximum: int) -> bytes:
    if (
        type(value) is not str
        or not minimum <= len(value) <= maximum
        or len(value) % 2
        or re.fullmatch(r"[0-9a-f]+", value) is None
    ):
        raise IdentityWireError("invalid identity hex")
    return bytes.fromhex(value)


def _principal_object(value: PrincipalIdentity) -> dict[str, object]:
    if type(value) is PosixPrincipal:
        return {"kind": "posix-uid", "uid": value.uid}
    if type(value) is WindowsPrincipal:
        return {"kind": "windows-sid", "sid_hex": value.sid.hex()}
    raise IdentityWireError("invalid principal value")


def _principal(value: dict[str, object]) -> PrincipalIdentity:
    if value.get("kind") == "posix-uid":
        _members(value, "kind", "uid")
        return PosixPrincipal(_integer(value["uid"]))
    if value.get("kind") == "windows-sid":
        _members(value, "kind", "sid_hex")
        try:
            return WindowsPrincipal(_hex(value["sid_hex"], 16, 136))
        except ValueError:
            raise IdentityWireError("invalid principal value") from None
    raise IdentityWireError("unsupported principal kind")


def _file_object(value: FileIdentity) -> dict[str, object]:
    if type(value) is PosixFileIdentity:
        return {"kind": "posix-file", "device": value.device, "inode": value.inode}
    if type(value) is WindowsFileIdentity:
        return {
            "kind": "windows-file",
            "volume_serial_hex": f"{value.volume_serial:016x}",
            "file_id_hex": value.file_id.hex(),
        }
    raise IdentityWireError("invalid file identity value")


def _file(value: dict[str, object]) -> FileIdentity:
    if value.get("kind") == "posix-file":
        _members(value, "kind", "device", "inode")
        return PosixFileIdentity(_integer(value["device"]), _integer(value["inode"]))
    if value.get("kind") == "windows-file":
        _members(value, "kind", "volume_serial_hex", "file_id_hex")
        return WindowsFileIdentity(
            int.from_bytes(_hex(value["volume_serial_hex"], 16, 16), "big"),
            _hex(value["file_id_hex"], 32, 32),
        )
    raise IdentityWireError("unsupported file identity kind")


def encode_principal(value: PrincipalIdentity) -> bytes:
    return _encode(_principal_object(value))


def decode_principal(payload: bytes) -> PrincipalIdentity:
    return _principal(_decode(payload))


def encode_file_identity(value: FileIdentity) -> bytes:
    return _encode(_file_object(value))


def decode_file_identity(payload: bytes) -> FileIdentity:
    return _file(_decode(payload))


def encode_owner_binding(value: OwnerBinding) -> bytes:
    if type(value) is not OwnerBinding:
        raise IdentityWireError("invalid owner binding value")
    return _encode(
        {
            "namespace_id": value.namespace_id,
            "principal": _principal_object(value.principal),
        }
    )


def decode_owner_binding(payload: bytes) -> OwnerBinding:
    value = _decode(payload)
    _members(value, "namespace_id", "principal")
    return OwnerBinding(
        cast(str, value["namespace_id"]),
        _principal(_object(value["principal"])),
    )


def encode_namespace_record(value: NamespaceRecord) -> bytes:
    """Encode metadata only; fingerprint syntax does not validate a public key."""
    if type(value) is not NamespaceRecord:
        raise IdentityWireError("invalid namespace record value")
    return _encode(
        {
            "kind": value.kind,
            "schema_version": value.schema_version,
            "namespace_id": value.namespace_id,
            "principal": _principal_object(value.principal),
            "migration_verification_key_sha256": (
                value.migration_verification_key_sha256
            ),
        }
    )


def decode_namespace_record(payload: bytes) -> NamespaceRecord:
    """Decode bounded canonical metadata without storage or enrollment effects."""
    value = _decode(payload)
    _members(
        value,
        "kind",
        "schema_version",
        "namespace_id",
        "principal",
        "migration_verification_key_sha256",
    )
    if value["kind"] != "identity-namespace":
        raise IdentityWireError("unsupported namespace record kind")
    if _integer(value["schema_version"]) != 1:
        raise IdentityWireError("unsupported namespace record version")
    return NamespaceRecord(
        cast(str, value["namespace_id"]),
        _principal(_object(value["principal"])),
        cast(str, value["migration_verification_key_sha256"]),
    )


def encode_scoped_file_identity(value: ScopedFileIdentity) -> bytes:
    if type(value) is not ScopedFileIdentity:
        raise IdentityWireError("invalid scoped file identity value")
    return _encode(
        {
            "namespace_id": value.namespace_id,
            "identity": _file_object(value.identity),
        }
    )


def decode_scoped_file_identity(payload: bytes) -> ScopedFileIdentity:
    value = _decode(payload)
    _members(value, "namespace_id", "identity")
    return ScopedFileIdentity(
        cast(str, value["namespace_id"]),
        _file(_object(value["identity"])),
    )
