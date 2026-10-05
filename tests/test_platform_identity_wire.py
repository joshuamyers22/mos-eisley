"""Pure wire boundary tests, usable from dependency-free installed wheels."""

import hashlib
import json
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from typing import cast
from unittest.mock import patch

from mos_eisley.platform.identity import (
    FileIdentity,
    PosixFileIdentity,
    PosixPrincipal,
    PrincipalIdentity,
    WindowsFileIdentity,
    WindowsPrincipal,
)
from mos_eisley.platform.identity_wire import (
    MAX_IDENTITY_WIRE_BYTES,
    IdentityWireError,
    NamespaceRecord,
    OwnerBinding,
    ScopedFileIdentity,
    decode_file_identity,
    decode_namespace_record,
    decode_owner_binding,
    decode_principal,
    decode_scoped_file_identity,
    encode_file_identity,
    encode_namespace_record,
    encode_owner_binding,
    encode_principal,
    encode_scoped_file_identity,
)

NAMESPACE = "0123456789abcdef" * 2
SID = bytes.fromhex("0101000000000005ffffffff")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class IdentityWireTests(unittest.TestCase):
    def test_exact_principal_bytes_and_sid_boundaries(self) -> None:
        self.assertEqual(
            encode_principal(PosixPrincipal(1000)), b'{"kind":"posix-uid","uid":1000}'
        )
        self.assertEqual(
            encode_principal(WindowsPrincipal(SID)),
            b'{"kind":"windows-sid","sid_hex":"0101000000000005ffffffff"}',
        )
        for count in range(16):
            sid = (
                bytes((1, count))
                + bytes.fromhex("ffffffffffff")
                + b"\xff" * (4 * count)
            )
            value = WindowsPrincipal(sid)
            self.assertEqual(decode_principal(encode_principal(value)), value)
        value = PosixPrincipal(2**127 + 1)
        self.assertEqual(decode_principal(encode_principal(value)), value)

    def test_exact_file_bytes_and_full_native_width(self) -> None:
        value = WindowsFileIdentity(2**64 - 1, bytes(range(16)))
        self.assertEqual(
            encode_file_identity(value),
            b'{"file_id_hex":"000102030405060708090a0b0c0d0e0f",'
            b'"kind":"windows-file","volume_serial_hex":"ffffffffffffffff"}',
        )
        self.assertEqual(decode_file_identity(encode_file_identity(value)), value)
        self.assertEqual(
            encode_file_identity(PosixFileIdentity(0, 0)),
            b'{"device":0,"inode":0,"kind":"posix-file"}',
        )
        for bit in range(128):
            value = WindowsFileIdentity(2**63 + 1, (1 << bit).to_bytes(16, "little"))
            self.assertEqual(decode_file_identity(encode_file_identity(value)), value)
        value = PosixFileIdentity(2**80 + 1, 2**127 + 1)
        self.assertEqual(decode_file_identity(encode_file_identity(value)), value)

    def test_binding_shapes_and_immutability(self) -> None:
        for principal in (PosixPrincipal(0), WindowsPrincipal(SID)):
            value = OwnerBinding(NAMESPACE, principal)
            self.assertEqual(decode_owner_binding(encode_owner_binding(value)), value)
            attribute = "namespace_id"
            with self.assertRaises(FrozenInstanceError):
                setattr(value, attribute, "f" * 32)
            self.assertNotIn(NAMESPACE, repr(value))
        for identity in (PosixFileIdentity(0, 1), WindowsFileIdentity(0, bytes(16))):
            value = ScopedFileIdentity(NAMESPACE, identity)
            self.assertEqual(
                decode_scoped_file_identity(encode_scoped_file_identity(value)), value
            )
            attribute = "identity"
            with self.assertRaises(FrozenInstanceError):
                setattr(value, attribute, PosixFileIdentity(2, 3))
        self.assertNotEqual(
            OwnerBinding(NAMESPACE, PosixPrincipal(1)),
            OwnerBinding("f" * 32, PosixPrincipal(1)),
        )

    def test_integer_aliases_refuse(self) -> None:
        for value in (True, False, 1.0, -1, "1", None):
            for obj, decoder in (
                ({"kind": "posix-uid", "uid": value}, decode_principal),
                (
                    {"kind": "posix-file", "device": value, "inode": 1},
                    decode_file_identity,
                ),
                (
                    {"kind": "posix-file", "device": 1, "inode": value},
                    decode_file_identity,
                ),
            ):
                with (
                    self.subTest(value=value, obj=obj),
                    self.assertRaises(IdentityWireError),
                ):
                    decoder(canonical(obj))

    def test_hex_and_sid_malformations_refuse(self) -> None:
        for sid in (
            "",
            "00",
            SID.hex().upper(),
            SID.hex() + "00",
            SID.hex()[:-2],
            "02" + SID.hex()[2:],
            "0110" + "00" * 6,
            "01ff" + "00" * 6,
            "010000000000000z",
            "01000000 00000000",
            1,
            None,
        ):
            with self.subTest(sid=sid), self.assertRaises(IdentityWireError):
                decode_principal(canonical({"kind": "windows-sid", "sid_hex": sid}))
        for field, valid in (
            ("volume_serial_hex", "a" * 16),
            ("file_id_hex", "a" * 32),
        ):
            for invalid in (
                valid[:-1],
                valid + "a",
                valid.upper(),
                "z" * len(valid),
                " " + valid[1:],
                0,
                None,
            ):
                obj: dict[str, object] = {
                    "kind": "windows-file",
                    "volume_serial_hex": "a" * 16,
                    "file_id_hex": "a" * 32,
                }
                obj[field] = invalid
                with (
                    self.subTest(field=field, invalid=invalid),
                    self.assertRaises(IdentityWireError),
                ):
                    decode_file_identity(canonical(obj))

    def test_exact_members_tags_and_cross_kind_refusal(self) -> None:
        for payload in (
            b"{}",
            b"[]",
            b"null",
            b"1",
            b'"posix-uid"',
            b'{"kind":"posix-uid"}',
            b'{"kind":"unknown","uid":1}',
            b'{"kind":"posix-uid","schema_version":2,"uid":1}',
            b'{"kind":"posix-uid","namespace_id":"x","uid":1}',
            b'{"kind":"windows-sid","owner_uid":1}',
            encode_file_identity(PosixFileIdentity(1, 2)),
        ):
            with self.subTest(payload=payload), self.assertRaises(IdentityWireError):
                decode_principal(payload)
        with self.assertRaises(IdentityWireError):
            decode_file_identity(encode_principal(PosixPrincipal(1)))
        for decoder in (decode_owner_binding, decode_scoped_file_identity):
            with self.assertRaises(IdentityWireError):
                decoder(b'{"owner_uid":1,"schema_version":1}')

    def test_duplicate_keys_refuse_at_every_depth(self) -> None:
        values = (
            (decode_principal, b'{"kind":"posix-uid","uid":1,"uid":1}'),
            (decode_principal, b'{"kind":"posix-uid","u\\u0069d":1,"uid":1}'),
            (
                decode_owner_binding,
                b'{"namespace_id":"'
                + NAMESPACE.encode()
                + b'","principal":{"kind":"posix-uid","uid":1,"uid":2}}',
            ),
            (
                decode_scoped_file_identity,
                b'{"identity":{"device":1,"inode":2,'
                b'"kind":"posix-file","kind":"posix-file"},"namespace_id":"'
                + NAMESPACE.encode()
                + b'"}',
            ),
        )
        for decoder, payload in values:
            with self.subTest(payload=payload), self.assertRaises(IdentityWireError):
                decoder(payload)

    def test_encoding_aliases_and_hostile_json_refuse(self) -> None:
        for payload in (
            b"",
            b"\xff",
            b'\xef\xbb\xbf{"kind":"posix-uid","uid":1}',
            b'{"uid":1,"kind":"posix-uid"}',
            b' {"kind":"posix-uid","uid":1}',
            b'{"kind":"posix-uid", "uid":1}',
            b'{"kind":"posix-uid","uid":1}\n',
            b'{"kind":"posix-uid","uid":NaN}',
            b'{"kind":"posix-uid","uid":Infinity}',
            b'{"kind":"posix-uid","uid":-Infinity}',
            b'{"kind":"posix-uid","uid":1e999}',
            b'{"kind":"posix-uid","uid":-0}',
            b'{"kind":"posix-uid","uid":01}',
            b'{"kind":"posix-uid","uid":1}{}',
            b'{"kind":"\\ud800","uid":1}',
            b"[" * 1500 + b"]" * 1500,
        ):
            with (
                self.subTest(payload=payload[:50]),
                self.assertRaises(IdentityWireError),
            ):
                decode_principal(payload)

    def test_namespace_and_nested_shapes_refuse(self) -> None:
        for namespace in ("", "a" * 31, "a" * 33, "A" * 32, "g" * 32, 1, None):
            with self.subTest(namespace=namespace):
                with self.assertRaises(IdentityWireError):
                    OwnerBinding(cast(str, namespace), PosixPrincipal(1))
                with self.assertRaises(IdentityWireError):
                    decode_scoped_file_identity(
                        canonical(
                            {
                                "namespace_id": namespace,
                                "identity": {
                                    "kind": "posix-file",
                                    "device": 1,
                                    "inode": 2,
                                },
                            }
                        )
                    )
        nested_values: tuple[object, ...] = (
            [],
            None,
            {"kind": "posix-uid", "uid": True},
            {"kind": "posix-uid", "uid": 1, "schema_version": 99},
        )
        for nested in nested_values:
            with self.assertRaises(IdentityWireError):
                decode_owner_binding(
                    canonical({"namespace_id": NAMESPACE, "principal": nested})
                )
        with self.assertRaises(IdentityWireError):
            decode_owner_binding(
                canonical(
                    {
                        "namespace_id": NAMESPACE,
                        "principal": {"kind": "posix-uid", "uid": 1},
                        "schema_version": 2,
                    }
                )
            )

    def test_byte_limit_and_wrong_input_types(self) -> None:
        # Exactly 4,096 bytes with an exact large integer is supported.
        overhead = len(b'{"kind":"posix-uid","uid":}')
        digits = "1" * (MAX_IDENTITY_WIRE_BYTES - overhead)
        payload = b'{"kind":"posix-uid","uid":' + digits.encode() + b"}"
        self.assertEqual(len(payload), MAX_IDENTITY_WIRE_BYTES)
        value = decode_principal(payload)
        self.assertEqual(encode_principal(value), payload)
        for invalid in (
            payload + b" ",
            "{}",
            bytearray(b"{}"),
            memoryview(b"{}"),
            None,
        ):
            with self.assertRaises(IdentityWireError):
                decode_principal(cast(bytes, invalid))
        with self.assertRaises(IdentityWireError):
            encode_principal(PosixPrincipal(int(digits + "1")))

    def test_bound_precedes_json_parsing_and_errors_omit_input(self) -> None:
        from mos_eisley.platform import identity_wire

        with (
            patch.object(
                identity_wire.json,
                "loads",
                side_effect=AssertionError("parsed oversize"),
            ),
            self.assertRaises(IdentityWireError),
        ):
            decode_owner_binding(b"x" * (MAX_IDENTITY_WIRE_BYTES + 1))
        payload = b'{"kind":"private-marker-do-not-log","uid":1}'
        with self.assertRaises(IdentityWireError) as error:
            decode_principal(payload)
        self.assertNotIn("private-marker", str(error.exception))

    def test_invalid_values_cannot_be_encoded(self) -> None:
        with self.assertRaises(IdentityWireError):
            encode_principal(cast(PrincipalIdentity, {"kind": "posix-uid", "uid": 1}))
        with self.assertRaises(IdentityWireError):
            encode_file_identity(cast(FileIdentity, PosixPrincipal(1)))
        with self.assertRaises(IdentityWireError):
            OwnerBinding(NAMESPACE, cast(PrincipalIdentity, None))
        with self.assertRaises(IdentityWireError):
            ScopedFileIdentity(NAMESPACE, cast(FileIdentity, PosixPrincipal(1)))
        with self.assertRaises(IdentityWireError):
            encode_owner_binding(cast(OwnerBinding, None))
        with self.assertRaises(IdentityWireError):
            encode_scoped_file_identity(cast(ScopedFileIdentity, None))

    def test_import_and_roundtrip_do_not_query_or_write(self) -> None:
        script = """
import ctypes, os, pathlib, socket, sys
from unittest.mock import patch
from contextlib import ExitStack
fail = AssertionError('codec performed I/O or native query')
with ExitStack() as stack:
    for module, name in ((os, 'getuid'), (os, 'geteuid'), (os, 'open'),
                         (os, 'stat'), (pathlib.Path, 'mkdir'),
                         (socket, 'socket'), (ctypes, 'WinDLL')):
        stack.enter_context(patch.object(module, name, create=True, side_effect=fail))
    from mos_eisley.platform.identity_wire import *
    principal = decode_principal(b'{"kind":"posix-uid","uid":1}')
    assert encode_principal(principal) == b'{"kind":"posix-uid","uid":1}'
    owner = OwnerBinding('0' * 32, principal)
    assert decode_owner_binding(encode_owner_binding(owner)) == owner
    file = decode_file_identity(b'{"device":1,"inode":2,"kind":"posix-file"}')
    scoped = ScopedFileIdentity('0' * 32, file)
    assert decode_scoped_file_identity(encode_scoped_file_identity(scoped)) == scoped
    for name in ('posix_identity', 'windows_identity', 'windows_file_identity'):
        assert 'mos_eisley.platform.' + name not in sys.modules
    assert 'mos_eisley.tools.mcp_oauth_store' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", script], check=True)


# These are synthetic public metadata, not enrolled roots or credential material.
# The fingerprint covers bytes(range(32)); no private key or custody is supplied.
PUBLIC_FINGERPRINT = "630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd"
POSIX_NAMESPACE_GOLDEN = (
    b'{"kind":"identity-namespace","migration_verification_key_sha256":'
    b'"630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd",'
    b'"namespace_id":"0123456789abcdef0123456789abcdef",'
    b'"principal":{"kind":"posix-uid","uid":1000},"schema_version":1}'
)
WINDOWS_NAMESPACE_GOLDEN = (
    b'{"kind":"identity-namespace","migration_verification_key_sha256":'
    b'"630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd",'
    b'"namespace_id":"0123456789abcdef0123456789abcdef",'
    b'"principal":{"kind":"windows-sid","sid_hex":"0101000000000005ffffffff"},'
    b'"schema_version":1}'
)


class NamespaceRecordWireTests(unittest.TestCase):
    def test_golden_bytes_and_independent_digests(self) -> None:
        self.assertEqual(
            hashlib.sha256(bytes(range(32))).hexdigest(), PUBLIC_FINGERPRINT
        )
        for principal, payload, digest in (
            (
                PosixPrincipal(1000),
                POSIX_NAMESPACE_GOLDEN,
                "e4bf05808edbded8844ce0cf7582aa6ac5169b311bf3aab89057e8fc2ece2a02",
            ),
            (
                WindowsPrincipal(SID),
                WINDOWS_NAMESPACE_GOLDEN,
                "8ed6dd5daf53954ba540ce22d0a965f56c5f63d6374808db055c4adde6e521e2",
            ),
        ):
            with self.subTest(principal=principal):
                record = NamespaceRecord(NAMESPACE, principal, PUBLIC_FINGERPRINT)
                self.assertEqual(encode_namespace_record(record), payload)
                self.assertEqual(decode_namespace_record(payload), record)
                self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)
                self.assertNotEqual(digest, PUBLIC_FINGERPRINT)

    def test_immutable_redacted_metadata_has_no_enrollment_authority(self) -> None:
        first = decode_namespace_record(POSIX_NAMESPACE_GOLDEN)
        copied = decode_namespace_record(bytes(bytearray(POSIX_NAMESPACE_GOLDEN)))
        self.assertEqual(first, copied)
        self.assertEqual(hash(first), hash(copied))
        self.assertEqual(first.kind, "identity-namespace")
        self.assertEqual(first.schema_version, 1)
        for attribute, value in (
            ("namespace_id", "f" * 32),
            ("principal", PosixPrincipal(0)),
            ("migration_verification_key_sha256", "f" * 64),
            ("kind", "other"),
            ("schema_version", 2),
        ):
            with self.assertRaises(FrozenInstanceError):
                setattr(first, attribute, value)
        for private in (NAMESPACE, PUBLIC_FINGERPRINT, "1000"):
            self.assertNotIn(private, repr(first))
        from mos_eisley.platform import identity_wire

        for name in (
            "EnrolledNamespaceContext",
            "PrivateDirectoryLease",
            "admit_private_directory",
            "read_namespace_record",
        ):
            self.assertFalse(hasattr(identity_wire, name))
        self.assertNotEqual(first, OwnerBinding(NAMESPACE, PosixPrincipal(1000)))

    def test_exact_members_versions_and_legacy_refusal(self) -> None:
        obj = json.loads(POSIX_NAMESPACE_GOLDEN)
        for member in obj:
            invalid = dict(obj)
            del invalid[member]
            with self.subTest(missing=member), self.assertRaises(IdentityWireError):
                decode_namespace_record(canonical(invalid))
        for member, values in (
            ("kind", (None, 1, "posix-uid", "identity-namespace-v2")),
            ("schema_version", (True, False, 1.0, 0, -1, 2, "1", None)),
        ):
            for value in values:
                invalid = dict(obj)
                invalid[member] = value
                with (
                    self.subTest(member=member, value=value),
                    self.assertRaises(IdentityWireError),
                ):
                    decode_namespace_record(canonical(invalid))
        for payload in (
            canonical({**obj, "owner_uid": 1000}),
            canonical({"owner_uid": 1000, "schema_version": 1}),
            encode_owner_binding(OwnerBinding(NAMESPACE, PosixPrincipal(1000))),
            encode_principal(PosixPrincipal(1000)),
            b"[]",
            b"null",
        ):
            with self.assertRaises(IdentityWireError):
                decode_namespace_record(payload)
        with self.assertRaises(IdentityWireError):
            decode_owner_binding(POSIX_NAMESPACE_GOLDEN)

    def test_namespace_and_fingerprint_shapes_refuse(self) -> None:
        obj = json.loads(POSIX_NAMESPACE_GOLDEN)
        for member, width in (
            ("namespace_id", 32),
            ("migration_verification_key_sha256", 64),
        ):
            for invalid in (
                None,
                0,
                "",
                "a" * (width - 1),
                "a" * (width + 1),
                "A" * width,
                "g" * width,
                " " + "a" * (width - 1),
            ):
                candidate = dict(obj)
                candidate[member] = invalid
                with self.subTest(member=member, invalid=invalid):
                    with self.assertRaises(IdentityWireError):
                        decode_namespace_record(canonical(candidate))
                    with self.assertRaises(IdentityWireError):
                        NamespaceRecord(
                            cast(str, invalid)
                            if member == "namespace_id"
                            else NAMESPACE,
                            PosixPrincipal(1),
                            cast(str, invalid)
                            if member == "migration_verification_key_sha256"
                            else PUBLIC_FINGERPRINT,
                        )

    def test_nested_principal_and_sid_boundaries(self) -> None:
        for count in range(16):
            sid = bytes((1, count)) + b"\xff" * 6 + b"\xff" * (count * 4)
            record = NamespaceRecord(
                NAMESPACE, WindowsPrincipal(sid), PUBLIC_FINGERPRINT
            )
            self.assertEqual(
                decode_namespace_record(encode_namespace_record(record)), record
            )
        obj = json.loads(POSIX_NAMESPACE_GOLDEN)
        invalid_principals: tuple[object, ...] = (
            None,
            [],
            {"kind": "posix-uid", "uid": True},
            {"kind": "posix-uid", "uid": -1},
            {"kind": "posix-uid", "uid": 1, "extra": 1},
            {"kind": "windows-sid", "sid_hex": SID.hex().upper()},
            {"kind": "windows-sid", "sid_hex": "02" + SID.hex()[2:]},
            {"kind": "windows-sid", "sid_hex": SID.hex() + "00"},
            {"kind": "windows-sid", "sid_hex": "0110" + "00" * 6},
            {"kind": "windows-file", "file_id_hex": "0" * 32},
        )
        for principal in invalid_principals:
            with (
                self.subTest(principal=principal),
                self.assertRaises(IdentityWireError),
            ):
                decode_namespace_record(canonical({**obj, "principal": principal}))
        with self.assertRaises(IdentityWireError):
            NamespaceRecord(
                NAMESPACE, cast(PrincipalIdentity, None), PUBLIC_FINGERPRINT
            )
        with self.assertRaises(IdentityWireError):
            encode_namespace_record(cast(NamespaceRecord, {}))

    def test_duplicate_and_noncanonical_encodings_refuse(self) -> None:
        for payload in (
            POSIX_NAMESPACE_GOLDEN.replace(
                b'"schema_version":1', b'"schema_version":1,"schema_version":1'
            ),
            POSIX_NAMESPACE_GOLDEN.replace(
                b'"uid":1000', b'"uid":1000,"u\\u0069d":1000'
            ),
            POSIX_NAMESPACE_GOLDEN.replace(
                b'"kind":"identity-namespace"',
                b'"kind":"identity-namespace","kind":"identity-namespace"',
            ),
            b" " + POSIX_NAMESPACE_GOLDEN,
            POSIX_NAMESPACE_GOLDEN + b"\n",
            POSIX_NAMESPACE_GOLDEN.replace(
                b'"schema_version":1', b'"schema_version":1e0'
            ),
            POSIX_NAMESPACE_GOLDEN.replace(b'"uid":1000', b'"uid":NaN'),
            POSIX_NAMESPACE_GOLDEN.replace(b'"uid":1000', b'"uid":Infinity'),
            POSIX_NAMESPACE_GOLDEN.replace(b'"uid":1000', b'"uid":1e999'),
            POSIX_NAMESPACE_GOLDEN.replace(b'"kind"', b'"k\\u0069nd"', 1),
            b"\xef\xbb\xbf" + POSIX_NAMESPACE_GOLDEN,
            b"\xff",
            b"",
            b"[" * 1500 + b"]" * 1500,
        ):
            with (
                self.subTest(payload=payload[:30]),
                self.assertRaises(IdentityWireError),
            ):
                decode_namespace_record(payload)

    def test_exact_limit_and_oversize_encoder_decoder(self) -> None:
        overhead = len(POSIX_NAMESPACE_GOLDEN) - len(b"1000")
        digits = "1" * (MAX_IDENTITY_WIRE_BYTES - overhead)
        payload = POSIX_NAMESPACE_GOLDEN.replace(
            b'"uid":1000', b'"uid":' + digits.encode()
        )
        self.assertEqual(len(payload), MAX_IDENTITY_WIRE_BYTES)
        record = decode_namespace_record(payload)
        self.assertEqual(encode_namespace_record(record), payload)
        from mos_eisley.platform import identity_wire

        with (
            patch.object(
                identity_wire.json,
                "loads",
                side_effect=AssertionError("parsed oversize"),
            ),
            self.assertRaises(IdentityWireError),
        ):
            decode_namespace_record(payload + b" ")
        with self.assertRaises(IdentityWireError):
            encode_namespace_record(
                NamespaceRecord(
                    NAMESPACE, PosixPrincipal(int(digits + "1")), PUBLIC_FINGERPRINT
                )
            )
        for invalid in (
            None,
            "{}",
            bytearray(POSIX_NAMESPACE_GOLDEN),
            memoryview(POSIX_NAMESPACE_GOLDEN),
        ):
            with self.assertRaises(IdentityWireError):
                decode_namespace_record(cast(bytes, invalid))

    def test_failures_do_not_disclose_input(self) -> None:
        payload = POSIX_NAMESPACE_GOLDEN.replace(
            b"identity-namespace", b"private-marker-do-not-log"
        )
        with self.assertRaises(IdentityWireError) as error:
            decode_namespace_record(payload)
        self.assertNotIn("private-marker", str(error.exception))
        self.assertIsNone(error.exception.__cause__)

    def test_inert_clean_import_and_roundtrip_for_both_principals(self) -> None:
        script = """
import ctypes, os, pathlib, secrets, socket, sys, time
from contextlib import ExitStack
from unittest.mock import patch
fail = AssertionError('namespace codec performed I/O, native or enrollment action')
with ExitStack() as stack:
    for module, name in ((os, 'getuid'), (os, 'geteuid'), (os, 'open'),
                         (os, 'stat'), (os, 'urandom'), (pathlib.Path, 'mkdir'),
                         (pathlib.Path, 'read_bytes'), (pathlib.Path, 'write_bytes'),
                         (socket, 'socket'), (ctypes, 'WinDLL'), (ctypes, 'CDLL'),
                         (secrets, 'token_bytes'), (time, 'time')):
        stack.enter_context(patch.object(module, name, create=True, side_effect=fail))
    from mos_eisley.platform.identity import PosixPrincipal, WindowsPrincipal
    from mos_eisley.platform.identity_wire import (
        NamespaceRecord, encode_namespace_record, decode_namespace_record)
    sid = bytes.fromhex('0101000000000005ffffffff')
    for principal in (PosixPrincipal(1000), WindowsPrincipal(sid)):
        record = NamespaceRecord('0' * 32, principal, '0' * 64)
        assert decode_namespace_record(encode_namespace_record(record)) == record
    for name in ('posix_identity', 'windows_identity', 'windows_file_identity'):
        assert 'mos_eisley.platform.' + name not in sys.modules
    assert 'mos_eisley.tools.mcp_oauth_store' not in sys.modules
    assert 'keyring' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", script], check=True)


if __name__ == "__main__":
    unittest.main()
