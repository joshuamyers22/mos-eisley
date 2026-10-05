"""Portable synthetic descriptors; these are not native Windows qualification."""

import dataclasses
import struct
import subprocess
import sys
import unittest
from typing import cast

from mos_eisley.platform.identity import PosixPrincipal, WindowsPrincipal
from mos_eisley.platform.windows_security import (
    MAX_DIRECTORY_SECURITY_BYTES,
    WindowsPrivateDacl,
    WindowsSecurityDecodeError,
    decode_private_directory_security,
)

# Literal synthetic fixtures: header / owner / ACL header / allow ACE / trustee.
# S-1-5-4294967295 is fixture metadata, never a queried host principal.
OWNER_SID = bytes.fromhex("0101000000000005ffffffff")
OWNER_FIRST = bytes.fromhex(
    "0100049014000000000000000000000020000000"
    "0101000000000005ffffffff"
    "02001c0001000000"
    "00001400ff011f00"
    "0101000000000005ffffffff"
)
ACL_FIRST = bytes.fromhex(
    "0100049430000000000000000000000014000000"
    "02001c0001000000"
    "00001400ff011f00"
    "0101000000000005ffffffff"
    "0101000000000005ffffffff"
)


def changed(payload: bytes, offset: int, replacement: bytes) -> bytes:
    return payload[:offset] + replacement + payload[offset + len(replacement) :]


def integer(payload: bytes, offset: int, value: int, width: int) -> bytes:
    return changed(payload, offset, value.to_bytes(width, "little"))


def descriptor(sid: bytes) -> bytes:
    """Build boundary fixtures independently of the production decoder."""
    ace = b"\0\0" + (8 + len(sid)).to_bytes(2, "little")
    ace += bytes.fromhex("ff011f00") + sid
    acl = b"\x02\0" + (8 + len(ace)).to_bytes(2, "little") + b"\x01\0\0\0"
    header = bytes.fromhex("01000490140000000000000000000000")
    return header + (20 + len(sid)).to_bytes(4, "little") + sid + acl + ace


class WindowsSecurityParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.owner = WindowsPrincipal(OWNER_SID)

    def refuses(self, payload: bytes) -> None:
        with self.assertRaises(WindowsSecurityDecodeError):
            decode_private_directory_security(payload, self.owner)

    def test_literal_goldens_and_normalized_fields(self) -> None:
        self.assertEqual(len(OWNER_FIRST), 60)
        first = decode_private_directory_security(OWNER_FIRST, self.owner)
        second = decode_private_directory_security(ACL_FIRST, self.owner)
        self.assertEqual(first.owner, self.owner)
        self.assertEqual(first.control, 0x9004)
        self.assertEqual(second.control, 0x9404)
        self.assertEqual(first.policy_id, "windows-private-directory-owner-dacl-v1")
        self.assertEqual(
            (first.acl_revision, first.ace_type, first.ace_flags), (2, 0, 0)
        )
        self.assertEqual(first.access_mask, 0x001F01FF)
        self.assertNotEqual(first, second)
        same_control = integer(ACL_FIRST, 2, 0x9004, 2)
        self.assertEqual(
            first, decode_private_directory_security(same_control, self.owner)
        )
        self.assertEqual(hash(first), hash(WindowsPrivateDacl(self.owner, 0x9004)))

    def test_private_frozen_metadata_has_no_authority(self) -> None:
        result = decode_private_directory_security(OWNER_FIRST, self.owner)
        self.assertNotIn(OWNER_SID.hex(), repr(result))
        self.assertNotIn(repr(OWNER_SID), repr(result))
        for name in ("handle", "payload", "lease", "enrolled", "apply", "close"):
            self.assertFalse(hasattr(result, name), name)
        for name in ("control", "policy_id", "access_mask"):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(result, name, 0)
        self.assertFalse(hasattr(result, "__dict__"))

    def test_metadata_constructor_requires_frozen_typed_fields(self) -> None:
        for owner in (None, OWNER_SID, PosixPrincipal(1000)):
            with self.assertRaises(WindowsSecurityDecodeError):
                WindowsPrivateDacl(cast(WindowsPrincipal, owner), 0x9004)
        for control in (True, 0, 0x8004, "36868", None):
            with self.assertRaises(WindowsSecurityDecodeError):
                WindowsPrivateDacl(self.owner, cast(int, control))

    def test_exact_immutable_input_types(self) -> None:
        class BytesSubclass(bytes):
            pass

        class PrincipalSubclass(WindowsPrincipal):
            pass

        for payload in (
            None,
            "private-input",
            bytearray(OWNER_FIRST),
            memoryview(OWNER_FIRST),
            BytesSubclass(OWNER_FIRST),
        ):
            with self.assertRaises(WindowsSecurityDecodeError):
                decode_private_directory_security(cast(bytes, payload), self.owner)
        for owner in (
            None,
            OWNER_SID,
            PosixPrincipal(1000),
            PrincipalSubclass(OWNER_SID),
        ):
            with self.assertRaises(WindowsSecurityDecodeError):
                decode_private_directory_security(
                    OWNER_FIRST, cast(WindowsPrincipal, owner)
                )

    def test_every_golden_prefix_truncation_refuses(self) -> None:
        for golden in (OWNER_FIRST, ACL_FIRST):
            for length in range(len(golden)):
                with self.subTest(order=golden[:20].hex(), length=length):
                    self.refuses(golden[:length])

    def test_size_cap_and_acl_slack_boundary(self) -> None:
        largest = OWNER_FIRST + b"\xa5" * (
            MAX_DIRECTORY_SECURITY_BYTES - len(OWNER_FIRST)
        )
        # The full declared ACL allocation, including slack, is bounded and aligned.
        largest = integer(largest, 34, MAX_DIRECTORY_SECURITY_BYTES - 32, 2)
        expected = decode_private_directory_security(OWNER_FIRST, self.owner)
        self.assertEqual(
            decode_private_directory_security(largest, self.owner), expected
        )
        self.refuses(largest + b"\0")
        self.refuses(largest[:-1])
        self.refuses(b"\0" * 20)

    def test_padding_and_component_order_are_not_freshness(self) -> None:
        # Move both components, with independent unused header/ACL/tail padding.
        padded = OWNER_FIRST[:20] + b"\xa5" * 4 + OWNER_FIRST[20:32]
        padded += b"\x5a" * 4 + OWNER_FIRST[32:] + b"\xcc" * 8
        padded = integer(integer(padded, 4, 24, 4), 16, 40, 4)
        padded = integer(padded, 42, 36, 2)
        self.assertEqual(
            decode_private_directory_security(padded, self.owner),
            decode_private_directory_security(OWNER_FIRST, self.owner),
        )

    def test_sid_zero_and_fifteen_subauthority_boundaries(self) -> None:
        for count in (0, 15):
            sid = bytes((1, count)) + bytes.fromhex("000000000005")
            sid += b"\xff\xff\xff\xff" * count
            owner = WindowsPrincipal(sid)
            golden = descriptor(sid)
            self.assertEqual(
                decode_private_directory_security(golden, owner).owner, owner
            )
            for length in range(len(golden)):
                with self.assertRaises(WindowsSecurityDecodeError):
                    decode_private_directory_security(golden[:length], owner)

    def test_header_revision_reserved_and_excluded_offsets(self) -> None:
        for offset, value, width in (
            (0, 0, 1),
            (0, 2, 1),
            (0, 255, 1),
            (1, 1, 1),
            (8, 20, 4),
            (12, 32, 4),
            (8, 0xFFFFFFFF, 4),
            (12, 0xFFFFFFFF, 4),
        ):
            with self.subTest(offset=offset, value=value):
                self.refuses(integer(OWNER_FIRST, offset, value, width))

    def test_all_other_control_bits_refuse(self) -> None:
        for bit in range(16):
            control = 0x9004 ^ (1 << bit)
            if control != 0x9404:
                with self.subTest(bit=bit):
                    self.refuses(integer(OWNER_FIRST, 2, control, 2))
        for control in (0, 0x8004, 0x9000, 0x900C, 0x9504, 0xFFFF):
            self.refuses(integer(OWNER_FIRST, 2, control, 2))

    def test_every_single_byte_mutation_of_unpadded_golden(self) -> None:
        # Every byte in this packed descriptor participates in the frozen profile.
        # Only the separately allowed auto-inherited bookkeeping bit may change.
        for offset, original in enumerate(OWNER_FIRST):
            for replacement in range(256):
                if replacement == original:
                    continue
                payload = integer(OWNER_FIRST, offset, replacement, 1)
                if offset == 3 and replacement == 0x94:
                    self.assertEqual(
                        decode_private_directory_security(payload, self.owner).control,
                        0x9404,
                    )
                else:
                    with self.subTest(offset=offset, replacement=replacement):
                        self.refuses(payload)

    def test_component_offsets_refuse_invalid_ranges(self) -> None:
        for field in (4, 16):
            for offset in (0, 4, 16, 19, 21, 31, 59, 60, 64, 0xFFFFFFFC, 0xFFFFFFFF):
                with self.subTest(field=field, offset=offset):
                    self.refuses(integer(OWNER_FIRST, field, offset, 4))

    def test_overlap_refuses_even_when_both_components_parse(self) -> None:
        sid = bytes.fromhex("0101000000000005ffffffff")
        # Put the owner in allocated ACL slack, after the valid sole ACE.
        overlapped = OWNER_FIRST + sid
        overlapped = integer(overlapped, 4, 60, 4)
        overlapped = integer(overlapped, 34, 40, 2)
        self.refuses(overlapped)
        # In the inverse ordering, extend ACL slack into the following owner.
        self.refuses(integer(ACL_FIRST, 22, 40, 2))

    def test_owner_and_trustee_sid_revision_count_and_extents(self) -> None:
        for start in (20, 48):
            for offset, value in ((0, 0), (0, 2), (1, 2), (1, 15), (1, 16), (1, 255)):
                with self.subTest(start=start, offset=offset, value=value):
                    self.refuses(integer(OWNER_FIRST, start + offset, value, 1))

    def test_full_sid_comparison_rejects_changed_components(self) -> None:
        for start in (20, 48):
            for index in range(2, len(OWNER_SID)):
                with self.subTest(start=start, index=index):
                    changed_byte = OWNER_FIRST[start + index] ^ 1
                    self.refuses(integer(OWNER_FIRST, start + index, changed_byte, 1))
        other = WindowsPrincipal(bytes.fromhex("0101000000000006ffffffff"))
        with self.assertRaises(WindowsSecurityDecodeError):
            decode_private_directory_security(OWNER_FIRST, other)

    def test_acl_revision_reserved_count_and_extent(self) -> None:
        for offset, values, width in (
            (32, (0, 1, 3, 4, 255), 1),
            (33, (1, 255), 1),
            (34, (0, 4, 8, 12, 24, 27, 29, 32, 0xFFFF), 2),
            (36, (0, 2, 0xFFFF), 2),
            (38, (1, 0xFFFF), 2),
        ):
            for value in values:
                with self.subTest(offset=offset, value=value):
                    self.refuses(integer(OWNER_FIRST, offset, value, width))

    def test_every_other_ace_type_and_flags_refuse(self) -> None:
        for offset in (40, 41):
            for value in range(1, 256):
                with self.subTest(offset=offset, value=value):
                    self.refuses(integer(OWNER_FIRST, offset, value, 1))

    def test_ace_size_truncation_and_application_data_refuse(self) -> None:
        for size in (0, 4, 8, 12, 16, 19, 21, 24, 0xFFFF):
            self.refuses(integer(OWNER_FIRST, 42, size, 2))
        # Allocation slack is legal, ACE application data is not.
        extra = integer(OWNER_FIRST + b"\0" * 4, 34, 32, 2)
        self.assertEqual(
            decode_private_directory_security(extra, self.owner),
            decode_private_directory_security(OWNER_FIRST, self.owner),
        )
        self.refuses(integer(extra, 42, 24, 2))

    def test_exact_access_mask_rejects_every_bit_change_and_generic_alias(self) -> None:
        for bit in range(32):
            with self.subTest(bit=bit):
                self.refuses(integer(OWNER_FIRST, 44, 0x001F01FF ^ (1 << bit), 4))
        for mask in (0, 0x10000000, 0x80000000, 0x001200A1, 0xFFFFFFFF):
            self.refuses(integer(OWNER_FIRST, 44, mask, 4))

    def test_extra_ace_count_refuses_valid_foreign_allow(self) -> None:
        foreign = changed(OWNER_FIRST[40:], 19, b"\xfe")
        extra = OWNER_FIRST + foreign
        extra = integer(integer(extra, 34, 48, 2), 36, 2, 2)
        self.refuses(extra)

    def test_errors_do_not_include_private_payload_or_cause(self) -> None:
        private = b"private-marker-do-not-log" * 4
        with self.assertRaises(WindowsSecurityDecodeError) as error:
            decode_private_directory_security(private, self.owner)
        self.assertNotIn("private-marker", str(error.exception))
        self.assertNotIn(OWNER_SID.hex(), str(error.exception))
        self.assertIsNone(error.exception.__cause__)

    def test_inert_clean_process_import_decode_and_public_gates(self) -> None:
        script = """
import ctypes, os, pathlib, secrets, socket, sys, time
from contextlib import ExitStack
from unittest.mock import patch
fail = AssertionError('security parser performed native or external action')
with ExitStack() as stack:
    for module, name in ((os, 'getuid'), (os, 'geteuid'), (os, 'open'),
                         (os, 'stat'), (os, 'urandom'), (pathlib.Path, 'mkdir'),
                         (pathlib.Path, 'read_bytes'), (pathlib.Path, 'write_bytes'),
                         (socket, 'socket'), (ctypes, 'WinDLL'), (ctypes, 'CDLL'),
                         (secrets, 'token_bytes'), (time, 'time')):
        stack.enter_context(patch.object(module, name, create=True, side_effect=fail))
    from mos_eisley.platform.identity import WindowsPrincipal, current_principal
    from mos_eisley.platform.files import UnsupportedPlatformError
    from mos_eisley.platform.windows_security import decode_private_directory_security
    principal = WindowsPrincipal(bytes.fromhex('0101000000000005ffffffff'))
    payload = bytes.fromhex(
        '0100049014000000000000000000000020000000'
        '0101000000000005ffffffff02001c0001000000'
        '00001400ff011f000101000000000005ffffffff')
    assert decode_private_directory_security(payload, principal).owner == principal
    with patch.object(sys, 'platform', 'win32'):
        try:
            current_principal()
        except UnsupportedPlatformError:
            pass
        else:
            raise AssertionError('public identity selector opened')
    for name in ('posix_identity', 'windows_identity', 'windows_file_identity',
                 'posix_storage'):
        assert 'mos_eisley.platform.' + name not in sys.modules
    assert 'keyring' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", script], check=True, timeout=30)

    def test_no_live_inspector_export(self) -> None:
        from mos_eisley.platform import windows_security

        self.assertFalse(hasattr(windows_security, "inspect_directory_security"))
        self.assertFalse(
            hasattr(windows_security, "WindowsDirectorySecurityObservation")
        )
        self.assertEqual(struct.calcsize("<BBHIIII"), 20)


if __name__ == "__main__":
    unittest.main()
