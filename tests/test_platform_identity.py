"""Isolated identity values/queries; no CLI or private-store imports."""

import os
import socket
import stat
import struct
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import patch

from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.identity import (
    IdentityContextError,
    IdentityQueryError,
    PosixDescriptor,
    PosixFileIdentity,
    PosixPrincipal,
    WindowsFileIdentity,
    WindowsHandle,
    WindowsPrincipal,
    current_principal,
    file_identity,
)


def sid(count: int) -> bytes:
    return bytes((1, count)) + b"\x00\x00\x00\x00\x00\x05" + b"\xff" * (4 * count)


class IdentityValueTests(unittest.TestCase):
    def test_integer_values_are_strict(self) -> None:
        for invalid in (-1, True, False, 1.5, "2", None):
            value = cast(int, invalid)
            with self.subTest(value=invalid):
                for create in (
                    partial(PosixPrincipal, value),
                    partial(PosixFileIdentity, value, 1),
                    partial(PosixFileIdentity, 1, value),
                    partial(WindowsFileIdentity, value, bytes(16)),
                    partial(PosixDescriptor, value),
                    partial(WindowsHandle, value),
                ):
                    with self.assertRaises(ValueError):
                        create()
        self.assertEqual(PosixPrincipal(0).uid, 0)
        self.assertEqual(PosixFileIdentity(0, 0).inode, 0)
        self.assertEqual(PosixDescriptor(0).fd, 0)

    def test_sid_boundaries_and_equality(self) -> None:
        for count in range(16):
            value = WindowsPrincipal(sid(count))
            self.assertEqual(value.sid, sid(count))
            self.assertEqual(value, WindowsPrincipal(sid(count)))
            self.assertEqual(hash(value), hash(WindowsPrincipal(sid(count))))
        payload = bytearray(sid(15))
        original = WindowsPrincipal(bytes(payload))
        # Every authority/subauthority byte participates, including upper bits.
        for position in range(2, len(payload)):
            changed = payload.copy()
            changed[position] ^= 1
            self.assertNotEqual(original, WindowsPrincipal(bytes(changed)))

    def test_sid_malformed_or_mutable_inputs_are_refused(self) -> None:
        for invalid in (
            b"",
            sid(1)[:-1],
            sid(1) + b"\x00",
            b"\x02" + sid(1)[1:],
            sid(16),
            b"\x01\xff" + bytes(6),
            bytearray(sid(1)),
            memoryview(sid(1)),
            "S-1-5-1000",
            None,
        ):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                WindowsPrincipal(cast(bytes, invalid))

    def test_full_width_file_ids_and_volume(self) -> None:
        original = WindowsFileIdentity(2**64 - 1, bytes(16))
        for position in range(16):
            payload = bytearray(16)
            payload[position] = 0x80
            self.assertNotEqual(
                original, WindowsFileIdentity(2**64 - 1, bytes(payload))
            )
        self.assertNotEqual(original, WindowsFileIdentity(2**32 - 1, bytes(16)))
        self.assertEqual(original, WindowsFileIdentity(2**64 - 1, bytes(16)))
        with self.assertRaises(ValueError):
            WindowsFileIdentity(2**64, bytes(16))
        for invalid in (
            bytes(15),
            bytes(17),
            bytearray(16),
            memoryview(bytes(16)),
            "0" * 32,
        ):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                WindowsFileIdentity(1, cast(bytes, invalid))

    def test_tags_and_immutability(self) -> None:
        self.assertNotEqual(PosixPrincipal(1), WindowsPrincipal(sid(1)))
        self.assertNotEqual(PosixFileIdentity(1, 1), WindowsFileIdentity(1, bytes(16)))
        self.assertNotEqual(PosixFileIdentity(1, 1), PosixFileIdentity(2, 1))
        self.assertNotEqual(PosixFileIdentity(1, 1), PosixFileIdentity(1, 2))
        value = PosixPrincipal(1)
        self.assertEqual(value.kind, "posix-uid")
        with self.assertRaises(FrozenInstanceError):
            attribute = "uid"
            setattr(value, attribute, 2)
        with self.assertRaises(ValueError):
            replace(value, kind="posix-uid")
        self.assertNotIn("uid=", repr(value))
        self.assertNotIn("sid=", repr(WindowsPrincipal(sid(1))))
        self.assertNotIn("fd=", repr(PosixDescriptor(123)))

    def test_reference_widths(self) -> None:
        maximum = 2 ** (8 * struct.calcsize("P")) - 1
        self.assertEqual(WindowsHandle(maximum - 1).value, maximum - 1)
        for invalid in (0, maximum, maximum + 1):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                WindowsHandle(invalid)
        self.assertEqual(PosixDescriptor(2**31 - 1).fd, 2**31 - 1)
        with self.assertRaises(ValueError):
            PosixDescriptor(2**31)


class IdentityContractTests(unittest.TestCase):
    def test_invalid_reference_refuses_before_platform_io(self) -> None:
        for invalid in (1, True, None, Path("not-a-reference")):
            with self.subTest(value=invalid), patch("os.fstat") as query:
                with self.assertRaises(ValueError):
                    file_identity(cast(PosixDescriptor, invalid))
                query.assert_not_called()

    def test_unsupported_platform_refuses_without_queries(self) -> None:
        for platform in ("win32", "unqualified"):
            with (
                self.subTest(platform=platform),
                patch("sys.platform", platform),
                patch("os.fstat") as query,
            ):
                with self.assertRaises(UnsupportedPlatformError):
                    current_principal()
                for reference in (PosixDescriptor(0), WindowsHandle(1)):
                    with self.assertRaises(UnsupportedPlatformError):
                        file_identity(reference)
                query.assert_not_called()

    def test_actual_host_selection(self) -> None:
        if sys.platform in {"darwin", "linux"}:
            self.assertEqual(current_principal(), PosixPrincipal(os.getuid()))
        else:
            with self.assertRaises(UnsupportedPlatformError):
                current_principal()
            with self.assertRaises(UnsupportedPlatformError):
                file_identity(WindowsHandle(1))

    def test_inert_import_and_construction_in_clean_process(self) -> None:
        code = """
import builtins
import os
import sys
from unittest.mock import patch
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name in ('ctypes', '_ctypes') or name.startswith('ctypes.'):
        raise AssertionError('unexpected DLL interface import')
    return original_import(name, *args, **kwargs)
dll_module_was_loaded = 'ctypes' in sys.modules
for name in ('getuid', 'geteuid', 'O_NOFOLLOW'):
    if hasattr(os, name):
        delattr(os, name)
with patch('os.open', side_effect=AssertionError('unexpected open')), \\
     patch('os.fstat', side_effect=AssertionError('unexpected query')), \
     patch('builtins.__import__', side_effect=guarded_import):
    from mos_eisley.platform.identity import (
        PosixPrincipal, WindowsPrincipal, PosixDescriptor, WindowsHandle,
        UnsupportedPlatformError, current_principal, file_identity,
    )
    assert 'mos_eisley.platform.posix_identity' not in sys.modules
    PosixPrincipal(0)
    WindowsPrincipal(bytes((1, 0)) + bytes(6))
    assert ('ctypes' in sys.modules) == dll_module_was_loaded
    sys.platform = 'win32'
    for query in (current_principal, lambda: file_identity(WindowsHandle(1)),
                  lambda: file_identity(PosixDescriptor(0))):
        try:
            query()
        except UnsupportedPlatformError:
            pass
        else:
            raise AssertionError('unsupported platform admitted')
    assert 'mos_eisley.platform.posix_identity' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", code], timeout=5, check=True)


@unittest.skipUnless(sys.platform in {"darwin", "linux"}, "qualified POSIX queries")
class PosixIdentityTests(unittest.TestCase):
    def test_principal_is_fresh_and_ignores_environment(self) -> None:
        with patch.dict(os.environ, {"USER": "spoofed", "UID": "999999"}):
            self.assertEqual(current_principal(), PosixPrincipal(os.getuid()))
        with (
            patch("os.getuid", side_effect=(10, 11)) as real,
            patch("os.geteuid", side_effect=(10, 11)) as effective,
        ):
            self.assertEqual(current_principal(), PosixPrincipal(10))
            self.assertEqual(current_principal(), PosixPrincipal(11))
            self.assertEqual(real.call_count, 2)
            self.assertEqual(effective.call_count, 2)

    def test_mismatched_principal_context_is_refused(self) -> None:
        with (
            patch("os.getuid", return_value=10),
            patch("os.geteuid", return_value=11),
            self.assertRaisesRegex(IdentityContextError, "context is unsupported"),
        ):
            current_principal()

    def test_principal_query_failures_preserve_cause(self) -> None:
        for name in ("getuid", "geteuid"):
            error = OSError("sensitive native diagnostic")
            with self.subTest(query=name), patch(f"os.{name}", side_effect=error):
                with self.assertRaises(IdentityQueryError) as caught:
                    current_principal()
                self.assertIs(caught.exception.__cause__, error)
                self.assertNotIn("sensitive", str(caught.exception))
        with patch("os.getuid", return_value=-1):
            with self.assertRaises(IdentityQueryError) as caught:
                current_principal()
            self.assertIsInstance(caught.exception.__cause__, ValueError)

    def test_wrong_reference_kind_never_queries(self) -> None:
        with patch("os.fstat") as query:
            with self.assertRaises(ValueError):
                file_identity(WindowsHandle(1))
            query.assert_not_called()

    def test_open_objects_aliases_replacement_and_offset(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "original"
            path.write_bytes(b"original")
            with path.open("rb") as stream:
                ref = PosixDescriptor(stream.fileno())
                info = os.fstat(ref.fd)
                identity = file_identity(ref)
                self.assertEqual(identity, PosixFileIdentity(info.st_dev, info.st_ino))
                stream.seek(3)
                offset = os.lseek(ref.fd, 0, os.SEEK_CUR)
                inheritance = os.get_inheritable(ref.fd)
                self.assertEqual(file_identity(ref), identity)
                self.assertEqual(stream.tell(), 3)
                self.assertEqual(os.lseek(ref.fd, 0, os.SEEK_CUR), offset)
                self.assertEqual(os.get_inheritable(ref.fd), inheritance)
                duplicate = os.dup(ref.fd)
                try:
                    self.assertEqual(
                        file_identity(PosixDescriptor(duplicate)), identity
                    )
                finally:
                    os.close(duplicate)
                link = root / "hardlink"
                os.link(path, link)
                with link.open("rb") as linked:
                    self.assertEqual(
                        file_identity(PosixDescriptor(linked.fileno())), identity
                    )
                path.rename(root / "renamed")
                path.write_bytes(b"replacement")
                with path.open("rb") as replacement:
                    self.assertNotEqual(
                        file_identity(PosixDescriptor(replacement.fileno())), identity
                    )
                self.assertEqual(file_identity(ref), identity)
                self.assertEqual(stream.read(), b"ginal")
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                info = os.fstat(fd)
                self.assertEqual(
                    file_identity(PosixDescriptor(fd)),
                    PosixFileIdentity(info.st_dev, info.st_ino),
                )
                os.fstat(fd)  # Caller still owns a usable directory descriptor.
            finally:
                os.close(fd)

    def test_query_takes_one_sample_without_path_lookup(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"data")
            with path.open("rb") as stream:
                with (
                    patch("os.fstat", wraps=os.fstat) as query,
                    patch("os.stat", side_effect=AssertionError("path lookup")),
                    patch("os.open", side_effect=AssertionError("path open")),
                ):
                    file_identity(PosixDescriptor(stream.fileno()))
                    query.assert_called_once_with(stream.fileno())
                self.assertEqual(stream.read(), b"data")

    def test_closed_descriptor_and_native_failure(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"data")
            with path.open("rb") as stream:
                reference = PosixDescriptor(stream.fileno())
                error = OSError("sensitive descriptor diagnostic")
                with patch("os.fstat", side_effect=error):
                    with self.assertRaises(IdentityQueryError) as caught:
                        file_identity(reference)
                    self.assertIs(caught.exception.__cause__, error)
                    self.assertNotIn("sensitive", str(caught.exception))
                self.assertEqual(stream.read(), b"data")
            with self.assertRaises(IdentityQueryError) as caught:
                file_identity(reference)
            self.assertIsInstance(caught.exception.__cause__, OSError)

    def test_native_metadata_is_validated_without_truncation(self) -> None:
        observed = os.stat_result((stat.S_IFREG, 2**80, 2**70, 1, 0, 0, 0, 0, 0, 0))
        with patch("os.fstat", return_value=observed):
            self.assertEqual(
                file_identity(PosixDescriptor(1)), PosixFileIdentity(2**70, 2**80)
            )
        invalid = os.stat_result((stat.S_IFREG, -1, 1, 1, 0, 0, 0, 0, 0, 0))
        with patch("os.fstat", return_value=invalid):
            with self.assertRaises(IdentityQueryError) as caught:
                file_identity(PosixDescriptor(1))
            self.assertIsInstance(caught.exception.__cause__, ValueError)

    def test_content_changes_do_not_change_object_identity(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"original")
            with path.open("rb") as stream:
                reference = PosixDescriptor(stream.fileno())
                before = file_identity(reference)
                path.write_bytes(b"changed")
                self.assertEqual(file_identity(reference), before)
                self.assertEqual(stream.read(), b"changed")

    def test_special_objects_are_refused_without_closing(self) -> None:
        read_fd, write_fd = os.pipe()
        try:
            with self.assertRaises(IdentityQueryError):
                file_identity(PosixDescriptor(read_fd))
            os.fstat(read_fd)
        finally:
            os.close(read_fd)
            os.close(write_fd)
        with socket.socket() as stream:
            with self.assertRaises(IdentityQueryError):
                file_identity(PosixDescriptor(stream.fileno()))
            os.fstat(stream.fileno())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fifo"
            os.mkfifo(path)
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                with self.assertRaises(IdentityQueryError):
                    file_identity(PosixDescriptor(fd))
                os.fstat(fd)
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
