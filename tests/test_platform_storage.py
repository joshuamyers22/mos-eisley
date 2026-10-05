"""Synthetic candidate storage tests; no existing private stores are opened."""

import copy
import ctypes
import errno
import os
import pickle
import shutil
import stat
import struct
import subprocess
import sys
import unittest
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.identity import PosixDescriptor, PosixPrincipal
from mos_eisley.platform.storage import (
    StorageAdmissionError,
    StorageCapacityError,
    StorageLeaseClosedError,
    StorageReleaseError,
    admit_private_directory,
)

if TYPE_CHECKING:
    from mos_eisley.platform.posix_storage import (
        PrivateDirectoryLease,
        PrivateDirectoryObservation,
    )


def test_attribute(value: object, name: str) -> object:
    """Inspect owned-resource internals only for lifecycle fault assertions."""
    return getattr(value, name)


class PlatformStorageContractTests(unittest.TestCase):
    def test_public_selection_remains_closed(self) -> None:
        with (
            patch("os.fstat", side_effect=AssertionError("queried unadmitted root")),
            self.assertRaises(UnsupportedPlatformError),
        ):
            admit_private_directory(PosixDescriptor(0), PosixPrincipal(0))

    def test_clean_import_and_unsupported_selection_are_inert(self) -> None:
        code = """
import ctypes, os, sys
from unittest.mock import patch
with patch.object(ctypes, 'CDLL', side_effect=AssertionError('native load')), \\
     patch('os.open', side_effect=AssertionError('open')):
    from mos_eisley.platform.storage import admit_private_directory
    from mos_eisley.platform.identity import PosixDescriptor, PosixPrincipal
    for name in ('posix_storage', 'posix_storage_native', 'posix_identity'):
        assert 'mos_eisley.platform.' + name not in sys.modules
    try:
        admit_private_directory(PosixDescriptor(0), PosixPrincipal(0))
    except OSError:
        pass
    else:
        raise AssertionError('public selection admitted')
"""
        subprocess.run([sys.executable, "-c", code], check=True, timeout=5)


@unittest.skipUnless(sys.platform in {"darwin", "linux"}, "POSIX candidate only")
class PosixRootTests(unittest.TestCase):
    def setUp(self) -> None:
        from mos_eisley.platform import posix_storage as storage

        self.storage = storage
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.principal = PosixPrincipal(os.getuid())

    def acquire(self) -> "PrivateDirectoryLease":
        return self.storage.admit_private_directory(
            PosixDescriptor(self.fd), self.principal
        )

    def test_native_success_borrowed_state_and_idempotent_close(self) -> None:
        flags = os.get_inheritable(self.fd)
        offset = os.lseek(self.fd, 0, os.SEEK_CUR)
        with self.acquire() as lease:
            observed = lease.inspect()
            self.assertEqual(observed.identity.device, os.fstat(self.fd).st_dev)
            self.assertEqual(observed.identity.inode, os.fstat(self.fd).st_ino)
            owned = cast(int, test_attribute(lease, "_fd"))
            self.assertFalse(os.get_inheritable(owned))
            self.assertNotEqual(owned, self.fd)
            self.assertNotIn(str(self.fd), repr(lease))
            for mode in (0o500, 0o700):
                os.fchmod(self.fd, mode)
                with self.acquire() as second:
                    self.assertEqual(second.inspect().mode, mode)
            # Mutating root protection invalidates the earlier observation.
            with self.assertRaises(StorageAdmissionError):
                lease.inspect()
        self.assertTrue(lease.closed)
        with patch("os.close") as close, patch("os.fstat") as query:
            lease.close()
            with self.assertRaises(StorageLeaseClosedError):
                lease.inspect()
            close.assert_not_called()
            query.assert_not_called()
        self.assertEqual(os.get_inheritable(self.fd), flags)
        self.assertEqual(os.lseek(self.fd, 0, os.SEEK_CUR), offset)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_rename_and_path_substitution_do_not_redirect_held_root(self) -> None:
        with self.acquire() as lease:
            moved = self.root.with_name(self.root.name + "-moved")
            self.root.rename(moved)
            try:
                self.root.mkdir(mode=0o700)
                # Rename itself may update ctime, requiring fresh admission.
                with self.acquire() as fresh:
                    self.assertEqual(
                        fresh.inspect().identity.inode, os.fstat(self.fd).st_ino
                    )
                    self.assertNotEqual(
                        fresh.inspect().identity.inode, self.root.stat().st_ino
                    )
                self.assertFalse(lease.closed)
            finally:
                self.root.rmdir()
                moved.rename(self.root)

    def test_compiled_native_abi_and_mount_oracle(self) -> None:
        compiler = shutil.which("cc")
        if compiler is None:
            if os.environ.get("MOS_REQUIRE_POSIX_STORAGE") == "1":
                self.fail("native ABI compiler is required for qualification")
            self.skipTest("native ABI compiler unavailable; qualification pending")
        source = Path(__file__).parent / "fixtures" / "posix_root_abi.c"
        executable = self.root / "oracle"
        subprocess.run([compiler, str(source), "-o", str(executable)], check=True)
        result = subprocess.run(
            [str(executable), str(self.fd)],
            pass_fds=(self.fd,),
            check=True,
            text=True,
            capture_output=True,
        ).stdout.splitlines()
        size, fsid, flags, observed_flags = map(int, result[0].split())
        from mos_eisley.platform.posix_storage_native import NativeRootQueries

        policy = NativeRootQueries().filesystem(self.fd)
        self.assertEqual(observed_flags, policy[2])
        if sys.platform == "darwin":
            self.assertEqual((size, fsid, flags), (2168, 48, 64))
            self.assertEqual(result[1], "24 8 13")
        else:
            self.assertEqual((size, fsid, flags), (120, 56, 80))

    def test_capacity_and_atomic_duplicate_failure_preserve_borrowed(self) -> None:
        import fcntl

        with (
            patch.object(self.storage, "_MAX_LEASES", 0),
            patch.object(self.storage, "_observe") as query,
        ):
            with self.assertRaises(StorageCapacityError):
                self.acquire()
            query.assert_not_called()
        original = fcntl.fcntl

        def fail_dup(fd: int, command: int, argument: int = 0) -> int:
            if command == fcntl.F_DUPFD_CLOEXEC:
                raise OSError("synthetic duplicate fault")
            return original(fd, command, argument)

        with patch("fcntl.fcntl", side_effect=fail_dup), patch("os.close") as close:
            with self.assertRaises(StorageAdmissionError):
                self.acquire()
            close.assert_not_called()
        os.fstat(self.fd)

    def test_invalid_types_and_hosts_refuse_before_dup_or_load(self) -> None:
        for opened, principal in (
            (None, self.principal),
            (self.fd, self.principal),
            (PosixDescriptor(self.fd), None),
        ):
            with patch.object(self.storage, "NativeRootQueries") as native:
                with self.assertRaises(ValueError):
                    self.storage.admit_private_directory(
                        cast(PosixDescriptor, opened), cast(PosixPrincipal, principal)
                    )
                native.assert_not_called()
        with (
            patch("sys.platform", "win32"),
            patch.object(self.storage, "NativeRootQueries") as native,
        ):
            with self.assertRaises(UnsupportedPlatformError):
                self.acquire()
            native.assert_not_called()

    def test_borrowed_inheritance_and_changed_context_survive_refusal(self) -> None:
        os.set_inheritable(self.fd, True)
        try:
            with self.acquire() as lease:
                owned = cast(int, test_attribute(lease, "_fd"))
                self.assertFalse(os.get_inheritable(owned))
                self.assertTrue(os.get_inheritable(self.fd))
            with (
                patch("os.geteuid", return_value=self.principal.uid + 1),
                self.assertRaises(StorageAdmissionError),
            ):
                self.acquire()
            self.assertTrue(os.get_inheritable(self.fd))
        finally:
            os.set_inheritable(self.fd, False)

    def test_owner_mode_special_and_closed_refusals(self) -> None:
        with self.assertRaises(StorageAdmissionError):
            self.storage.admit_private_directory(
                PosixDescriptor(self.fd), PosixPrincipal(self.principal.uid + 1)
            )
        for mode in (0o750, 0o600, 0o1700):
            os.fchmod(self.fd, mode)
            with self.assertRaises(StorageAdmissionError):
                self.acquire()
            os.fstat(self.fd)
        os.fchmod(self.fd, 0o700)
        path = self.root / "regular"
        path.write_bytes(b"synthetic")
        fd = os.open(path, os.O_RDONLY)
        try:
            with self.assertRaises(StorageAdmissionError):
                self.storage.admit_private_directory(
                    PosixDescriptor(fd), self.principal
                )
        finally:
            os.close(fd)
        with self.assertRaises(StorageAdmissionError):
            self.storage.admit_private_directory(PosixDescriptor(fd), self.principal)
        read_fd, write_fd = os.pipe()
        try:
            for special in (read_fd, write_fd):
                with self.assertRaises(StorageAdmissionError):
                    self.storage.admit_private_directory(
                        PosixDescriptor(special), self.principal
                    )
                os.fstat(special)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_real_additional_and_inheritable_acl_refusal(self) -> None:
        if sys.platform == "darwin":
            for entry in (
                "everyone allow list",
                "everyone allow list,file_inherit,directory_inherit",
            ):
                subprocess.run(["/bin/chmod", "+a", entry, str(self.root)], check=True)
                try:
                    self.assertEqual(stat.S_IMODE(os.fstat(self.fd).st_mode), 0o700)
                    with self.assertRaises(StorageAdmissionError):
                        self.acquire()
                finally:
                    subprocess.run(["/bin/chmod", "-N", str(self.root)], check=True)
        else:
            access = struct.pack("<I", 2) + b"".join(
                struct.pack("<HHI", tag, perm, uid)
                for tag, perm, uid in (
                    (1, 7, 0xFFFFFFFF),
                    (2, 4, self.principal.uid + 1),
                    (4, 0, 0xFFFFFFFF),
                    (16, 0, 0xFFFFFFFF),
                    (32, 0, 0xFFFFFFFF),
                )
            )
            default = struct.pack("<I", 2) + b"".join(
                struct.pack("<HHI", tag, perm, 0xFFFFFFFF)
                for tag, perm in ((1, 7), (4, 0), (32, 0))
            )
            for name, payload in (
                ("system.posix_acl_access", access),
                ("system.posix_acl_default", default),
            ):
                os.setxattr(self.fd, name, payload)
                try:
                    with self.assertRaises(StorageAdmissionError):
                        self.acquire()
                finally:
                    os.removexattr(self.fd, name)
        with self.acquire() as lease:
            self.assertEqual(lease.inspect().principal, self.principal)

    def test_post_dup_failure_and_failed_enter_release_owned_reference(self) -> None:
        real = cast(
            Callable[[int, PosixPrincipal], "PrivateDirectoryObservation"],
            test_attribute(self.storage, "_observe"),
        )
        calls = 0

        def fail_after_dup(
            fd: int, expected: PosixPrincipal
        ) -> "PrivateDirectoryObservation":
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StorageAdmissionError("synthetic fault")
            return real(fd, expected)

        with (
            patch.object(self.storage, "_observe", side_effect=fail_after_dup),
            patch("os.close", wraps=os.close) as close,
        ):
            with self.assertRaises(StorageAdmissionError):
                self.acquire()
            close.assert_called_once()
            self.assertNotEqual(close.call_args.args[0], self.fd)
        lease = self.acquire()
        os.fchmod(self.fd, 0o750)
        with self.assertRaises(StorageAdmissionError):
            lease.__enter__()
        self.assertTrue(lease.closed)
        os.fstat(self.fd)

    def test_close_failure_is_bounded_disables_acquisition_without_retry(self) -> None:
        lease = self.acquire()
        owned = cast(int, test_attribute(lease, "_fd"))
        assert owned is not None
        try:
            with patch(
                "os.close", side_effect=OSError("synthetic close uncertainty")
            ) as close:
                with self.assertRaises(StorageReleaseError):
                    lease.close()
                lease.close()
                close.assert_called_once_with(owned)
            with patch.object(self.storage, "_observe") as query:
                with self.assertRaises(StorageReleaseError):
                    self.acquire()
                query.assert_not_called()
            with self.assertRaises(StorageLeaseClosedError):
                lease.inspect()
        finally:
            # Test-only recovery: the mock never closed this synthetic owned FD.
            os.close(owned)
            cast(set[int], test_attribute(self.storage, "_OWNED")).remove(owned)
            cast(set[int], test_attribute(self.storage, "_UNCERTAIN")).remove(owned)
        os.fstat(self.fd)

    def test_lease_cannot_be_serialized_copied_or_minted_from_metadata(self) -> None:
        with self.acquire() as lease:
            for operation in (pickle.dumps, copy.copy, copy.deepcopy):
                with self.assertRaises(TypeError):
                    operation(lease)
            with self.assertRaises(TypeError):
                self.storage.PrivateDirectoryLease(
                    self.fd, lease.inspect(), token=object()
                )

    def test_principal_and_protection_changes_and_native_failures_refuse(self) -> None:
        with self.acquire() as lease:
            with (
                patch.object(
                    self.storage,
                    "current_principal",
                    return_value=PosixPrincipal(self.principal.uid + 1),
                ),
                self.assertRaises(StorageAdmissionError),
            ):
                lease.inspect()
            os.fchmod(self.fd, 0o750)
            with self.assertRaises(StorageAdmissionError):
                lease.inspect()
        os.fchmod(self.fd, 0o700)
        with (
            patch.object(
                self.storage,
                "NativeRootQueries",
                side_effect=AttributeError("missing API"),
            ),
            self.assertRaises(StorageAdmissionError),
        ):
            self.acquire()
        self.assertFalse(test_attribute(self.storage, "_OWNED"))


@unittest.skipUnless(sys.platform in {"darwin", "linux"}, "POSIX binding fixtures")
class RootNativeFaultTests(unittest.TestCase):
    def test_acl_binary_bounds_and_base_policy(self) -> None:
        from mos_eisley.platform.posix_storage_native import (
            validate_darwin_security,
            validate_linux_base_acl,
        )

        validate_darwin_security(struct.pack("<IiI", 12, 8, 0))
        good = (
            struct.pack("<IiII", 56, 8, 44, 0x012CC16D)
            + bytes(32)
            + struct.pack("<II", 0, 0)
        )
        validate_darwin_security(good)
        for invalid in (
            b"",
            good[:-1],
            struct.pack("<IiI", 12, -8, 0),
            good[:48] + struct.pack("<II", 1, 0),
            good[:48] + struct.pack("<II", 0, 1),
            good[:16] + b"\x01" + good[17:],
        ):
            with self.assertRaises(StorageAdmissionError):
                validate_darwin_security(invalid)
        base = struct.pack("<I", 2) + b"".join(
            struct.pack("<HHI", t, p, 0xFFFFFFFF) for t, p in ((1, 7), (4, 0), (32, 0))
        )
        validate_linux_base_acl(base, 0o700)
        for invalid in (
            b"",
            base[:-1],
            base + b"\0" * 8,
            b"\x03" + base[1:],
            base[:6] + b"\x00" + base[7:],
        ):
            with self.assertRaises(StorageAdmissionError):
                validate_linux_base_acl(invalid, 0o700)

    def test_filesystem_layout_unknown_flags_and_security_lengths(self) -> None:
        from mos_eisley.platform.posix_storage_native import NativeRootQueries

        for host in ("darwin", "linux"):
            with (
                patch("sys.platform", host),
                patch("platform.machine", return_value="x86_64"),
                patch("os.confstr", return_value="glibc 2.39"),
                patch("ctypes.CDLL"),
            ):
                query = NativeRootQueries()

            def output(
                fd: object, buffer: ctypes.Array[ctypes.c_char], native_host: str = host
            ) -> int:
                raw = bytearray(2168 if native_host == "darwin" else 120)
                if native_host == "darwin":
                    struct.pack_into("<I", raw, 64, 0x1000)
                    raw[72:77] = b"apfs\0"
                else:
                    struct.pack_into("<q", raw, 0, 0xEF53)
                    struct.pack_into("<q", raw, 80, 0x1020)
                ctypes.memmove(buffer, bytes(raw), len(raw))
                return 0

            with patch.object(query, "_statfs", side_effect=output):
                self.assertIn(host, query.filesystem(0)[0])

            def unknown(fd: object, buffer: ctypes.Array[ctypes.c_char]) -> int:
                return 0  # all-zero output refuses rather than inventing eligibility

            with (
                patch.object(query, "_statfs", side_effect=unknown),
                self.assertRaises(StorageAdmissionError),
            ):
                query.filesystem(0)
            if host == "darwin":
                for length in (0, 11, 65537):

                    def bad_length(
                        fd: object,
                        attrs: object,
                        buffer: ctypes.Array[ctypes.c_char],
                        size: object,
                        options: object,
                        declared: int = length,
                    ) -> int:
                        ctypes.memmove(buffer, struct.pack("<I", declared), 4)
                        return 0

                    with (
                        patch.object(query, "_security", side_effect=bad_length),
                        patch("os.fpathconf", return_value=1),
                        self.assertRaises(StorageAdmissionError),
                    ):
                        query.protection(0, 0o700)
            else:
                for result in (-2, 0, 65537):
                    with (
                        patch.object(query, "_security", return_value=result),
                        self.assertRaises(StorageAdmissionError),
                    ):
                        query.protection(0, 0o700)

    def test_unknown_abi_refuses_before_loading(self) -> None:
        from mos_eisley.platform.posix_storage_native import NativeRootQueries

        for machine in ("unknown", "i386"):
            with (
                patch("platform.machine", return_value=machine),
                patch("ctypes.CDLL") as load,
            ):
                with self.assertRaises(UnsupportedPlatformError):
                    NativeRootQueries()
                load.assert_not_called()

    def test_native_errors_bounds_and_unsupported_acl_do_not_mean_absence(self) -> None:
        from mos_eisley.platform.posix_storage_native import NativeRootQueries

        query = NativeRootQueries()
        with (
            patch.object(query, "_statfs", return_value=-1),
            self.assertRaises(StorageAdmissionError),
        ):
            query.filesystem(0)
        if sys.platform == "darwin":
            with (
                patch("os.fpathconf", return_value=0),
                patch.object(query, "_security") as security,
            ):
                with self.assertRaises(StorageAdmissionError):
                    query.protection(0, 0o700)
                security.assert_not_called()
        for code in (errno.EACCES, errno.EOPNOTSUPP, errno.ERANGE):
            ctypes.set_errno(code)

            def failed(*args: object, native_error: int = code) -> int:
                ctypes.set_errno(native_error)
                return -1

            with (
                patch.object(query, "_security", side_effect=failed),
                patch("os.fpathconf", return_value=1),
                self.assertRaises(StorageAdmissionError),
            ):
                query.protection(0, 0o700)


if __name__ == "__main__":
    unittest.main()
