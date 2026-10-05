"""Fixed-child candidate fixtures use only synthetic private temporary roots."""

import ctypes
import errno
import os
import stat
import struct
import subprocess
import sys
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.identity import PosixDescriptor, PosixPrincipal
from mos_eisley.platform.identity_wire import NamespaceRecord, encode_namespace_record
from mos_eisley.platform.storage import (
    NamespaceChangedError,
    NamespaceLimitError,
    NamespaceMalformedError,
    NamespaceMissing,
    NamespaceReadError,
    StorageAdmissionError,
    StorageCapacityError,
    StorageCheckedNamespace,
    StorageLeaseClosedError,
    StorageReleaseError,
    read_namespace_record,
)

if TYPE_CHECKING:
    from mos_eisley.platform.posix_storage import PrivateDirectoryLease
    from mos_eisley.platform.posix_storage_native import NativeRootQueries

CHILD = "identity-namespace.v1.json"


def lifecycle_state(value: object, name: str) -> set[int]:
    """Inspect ownership only for test cleanup and lifecycle assertions."""
    return cast(set[int], getattr(value, name))


class NamespaceReadContractTests(unittest.TestCase):
    def test_public_reader_refuses_without_query(self) -> None:
        with (
            patch("os.open", side_effect=AssertionError("unqualified open")),
            patch("os.fstat", side_effect=AssertionError("unqualified query")),
            self.assertRaises(UnsupportedPlatformError),
        ):
            read_namespace_record(object())

    def test_clean_import_and_result_repr_are_inert(self) -> None:
        code = """
import ctypes, os, sys
from unittest.mock import patch
with patch.object(ctypes, 'CDLL', side_effect=AssertionError('native loading')), \\
     patch('os.open', side_effect=AssertionError('opened file')):
    from mos_eisley.platform.storage import (
        read_namespace_record, NamespaceMissing, StorageCheckedNamespace)
    from mos_eisley.platform.identity import PosixFileIdentity, PosixPrincipal
    from mos_eisley.platform.identity_wire import NamespaceRecord
    identity = PosixFileIdentity(11, 22)
    record = NamespaceRecord('a' * 32, PosixPrincipal(33), 'b' * 64)
    assert repr(NamespaceMissing(identity)) == 'NamespaceMissing()'
    assert repr(StorageCheckedNamespace(record, identity, identity, 'c' * 64)) == \\
        'StorageCheckedNamespace()'
    assert 'mos_eisley.platform.posix_storage' not in sys.modules
    try:
        read_namespace_record(object())
    except OSError:
        pass
    else:
        raise AssertionError('unqualified reader admitted')
"""
        subprocess.run([sys.executable, "-c", code], check=True, timeout=5)


@unittest.skipUnless(sys.platform in {"darwin", "linux"}, "POSIX candidate only")
class PosixNamespaceReadTests(unittest.TestCase):
    def setUp(self) -> None:
        from mos_eisley.platform import posix_storage as storage
        from mos_eisley.platform.posix_storage_native import NativeRootQueries

        self.storage = storage
        self.owned = lifecycle_state(storage, "_OWNED")
        self.uncertain = lifecycle_state(storage, "_UNCERTAIN")
        self.query = NativeRootQueries
        self.temp = TemporaryDirectory(prefix="mos-ns-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / CHILD
        self.principal = PosixPrincipal(os.getuid())
        self.record = NamespaceRecord("a" * 32, self.principal, "b" * 64)
        self.payload = encode_namespace_record(self.record)
        self.path.write_bytes(self.payload)
        self.path.chmod(0o600)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)

    def acquire(self) -> "PrivateDirectoryLease":
        return self.storage.admit_private_directory(
            PosixDescriptor(self.fd), self.principal
        )

    def test_native_success_exact_hash_and_borrowed_state(self) -> None:
        original_open = os.open
        opened: list[int] = []

        def observe_open(path: str, flags: int, *, dir_fd: int) -> int:
            self.assertEqual(path, CHILD)
            self.assertNotEqual(dir_fd, self.fd)
            self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
            for required in (os.O_NOFOLLOW, os.O_NONBLOCK, os.O_CLOEXEC):
                self.assertTrue(flags & required)
            fd = original_open(path, flags, dir_fd=dir_fd)
            self.assertFalse(os.get_inheritable(fd))
            opened.append(fd)
            return fd

        flags, offset = os.get_inheritable(self.fd), os.lseek(self.fd, 0, os.SEEK_CUR)
        owned_before = self.owned.copy()
        for mode in (0o600, 0o400):
            self.path.chmod(mode)
            with self.acquire() as lease, patch("os.open", side_effect=observe_open):
                result = self.storage.read_namespace_record(lease)
                self.assertIsInstance(result, StorageCheckedNamespace)
                assert isinstance(result, StorageCheckedNamespace)
                self.assertEqual(result.record, self.record)
                self.assertEqual(result.record_sha256, sha256(self.payload).hexdigest())
                self.assertEqual(result.record_identity.inode, self.path.stat().st_ino)
                self.assertEqual(result.root_identity.inode, os.fstat(self.fd).st_ino)
                self.assertEqual(repr(result), "StorageCheckedNamespace()")
                self.assertFalse(hasattr(result, "enrolled"))
                self.assertFalse(hasattr(result, "apply"))
                self.assertFalse(lease.closed)
                with self.assertRaises(OSError):
                    os.fstat(opened[-1])
        self.assertEqual(self.owned, owned_before)
        self.assertEqual(os.get_inheritable(self.fd), flags)
        self.assertEqual(os.lseek(self.fd, 0, os.SEEK_CUR), offset)
        self.assertEqual(self.path.read_bytes(), self.payload)
        self.assertEqual([p.name for p in self.root.iterdir()], [CHILD])

    def test_missing_is_typed_and_does_not_create(self) -> None:
        self.path.unlink()
        with self.acquire() as lease:
            result = self.storage.read_namespace_record(lease)
            self.assertIsInstance(result, NamespaceMissing)
            self.assertEqual(list(self.root.iterdir()), [])
            self.assertFalse(lease.closed)

    def test_original_path_substitution_never_redirects_held_root(self) -> None:
        moved = self.root.with_name(self.root.name + "-moved")
        with self.acquire() as lease:
            self.root.rename(moved)
            try:
                self.root.mkdir(mode=0o700)
                foreign = self.root / CHILD
                foreign.write_bytes(self.payload.replace(b"a" * 32, b"c" * 32))
                foreign.chmod(0o600)
                with self.assertRaises(StorageAdmissionError):
                    self.storage.read_namespace_record(lease)
                with self.acquire() as fresh:
                    result = self.storage.read_namespace_record(fresh)
                    assert isinstance(result, StorageCheckedNamespace)
                    self.assertEqual(result.record, self.record)
                    self.assertNotEqual(
                        result.root_identity.inode, self.root.stat().st_ino
                    )
            finally:
                (self.root / CHILD).unlink()
                self.root.rmdir()
                moved.rename(self.root)

    def test_child_owner_device_and_filesystem_mismatch_refuse_before_read(
        self,
    ) -> None:
        original_stat = os.fstat
        for index in (4, 2):

            def wrong_identity(fd: int, index: int = index) -> os.stat_result:
                info = original_stat(fd)
                if not stat.S_ISREG(info.st_mode):
                    return info
                values = list(info)
                values[index] += 1
                return os.stat_result(values)

            with (
                self.acquire() as lease,
                patch("os.fstat", side_effect=wrong_identity),
                patch.object(self.query, "read_once") as read,
            ):
                with self.assertRaises(StorageAdmissionError):
                    self.storage.read_namespace_record(lease)
                read.assert_not_called()
        original_filesystem = self.query.filesystem

        def changed_mount(query: object, fd: int) -> tuple[str, bytes, int, int]:
            observed = original_filesystem(cast("NativeRootQueries", query), fd)
            if stat.S_ISREG(os.fstat(fd).st_mode):
                return observed[0], b"foreign", observed[2], observed[3]
            return observed

        with (
            self.acquire() as lease,
            patch.object(self.query, "filesystem", changed_mount),
            self.assertRaises(StorageAdmissionError),
        ):
            self.storage.read_namespace_record(lease)

    def test_only_open_enoent_can_be_missing(self) -> None:
        for error in (PermissionError(), OSError(errno.EIO, "fixture")):
            with (
                self.acquire() as lease,
                patch("os.open", side_effect=error),
                self.assertRaises(NamespaceReadError),
            ):
                self.storage.read_namespace_record(lease)
        with (
            self.acquire() as lease,
            patch("os.open", side_effect=FileNotFoundError()),
            self.assertRaises(NamespaceChangedError),
        ):
            self.storage.read_namespace_record(lease)
        with (
            self.acquire() as lease,
            patch("os.stat", side_effect=FileNotFoundError()),
            self.assertRaises(NamespaceReadError),
        ):
            self.storage.read_namespace_record(lease)

    def test_missing_rechecks_root_and_entry(self) -> None:
        self.path.unlink()
        with self.acquire() as lease:
            original_stat = os.stat

            def change_root(
                path: str, *, dir_fd: int, follow_symlinks: bool
            ) -> os.stat_result:
                os.fchmod(self.fd, 0o755)
                return original_stat(
                    path, dir_fd=dir_fd, follow_symlinks=follow_symlinks
                )

            with (
                patch("os.stat", side_effect=change_root),
                self.assertRaises(StorageAdmissionError),
            ):
                self.storage.read_namespace_record(lease)

    def test_wrong_input_and_closed_lease_refuse_before_io(self) -> None:
        with self.assertRaises(ValueError):
            self.storage.read_namespace_record(cast("PrivateDirectoryLease", object()))
        lease = self.acquire()
        lease.close()
        with patch("os.open") as opened, patch("os.fstat") as queried:
            with self.assertRaises(StorageLeaseClosedError):
                self.storage.read_namespace_record(lease)
            opened.assert_not_called()
            queried.assert_not_called()

    def test_stale_root_and_capacity_refuse_before_open(self) -> None:
        with self.acquire() as lease:
            os.fchmod(self.fd, 0o500)
            with patch("os.open") as opened, self.assertRaises(StorageAdmissionError):
                self.storage.read_namespace_record(lease)
            opened.assert_not_called()
        with self.acquire() as lease, patch.object(self.storage, "_MAX_LEASES", 1):
            with patch("os.open") as opened, self.assertRaises(StorageCapacityError):
                self.storage.read_namespace_record(lease)
            opened.assert_not_called()

    def test_symlink_fifo_directory_socket_and_multiple_links_refuse(self) -> None:
        import socket

        self.path.unlink()
        target = self.root / "target"
        target.write_bytes(self.payload)
        target.chmod(0o600)
        actions = (
            lambda: self.path.symlink_to(target),
            lambda: os.mkfifo(self.path, 0o600),
            lambda: self.path.mkdir(mode=0o700),
            lambda: os.link(target, self.path),
        )
        for action in actions:
            action()
            try:
                with (
                    self.acquire() as lease,
                    patch.object(self.query, "read_once") as read,
                ):
                    with self.assertRaises(StorageAdmissionError):
                        self.storage.read_namespace_record(lease)
                    read.assert_not_called()
            finally:
                if self.path.is_dir():
                    self.path.rmdir()
                else:
                    self.path.unlink()
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(self.path))
            with self.acquire() as lease, self.assertRaises(StorageAdmissionError):
                self.storage.read_namespace_record(lease)

    def test_actual_file_modes_acl_and_private_record_principal(self) -> None:
        for mode in (0o644, 0o200, 0o700, 0o1600):
            self.path.chmod(mode)
            with self.acquire() as lease, self.assertRaises(StorageAdmissionError):
                self.storage.read_namespace_record(lease)
        self.path.chmod(0o600)
        foreign = NamespaceRecord("a" * 32, PosixPrincipal(os.getuid() + 1), "b" * 64)
        self.path.write_bytes(encode_namespace_record(foreign))
        with self.acquire() as lease, self.assertRaises(StorageAdmissionError):
            self.storage.read_namespace_record(lease)
        self.path.write_bytes(self.payload)
        if sys.platform == "darwin":
            subprocess.run(
                ["/bin/chmod", "+a", "everyone allow read", str(self.path)], check=True
            )
            try:
                with self.acquire() as lease, self.assertRaises(StorageAdmissionError):
                    self.storage.read_namespace_record(lease)
            finally:
                subprocess.run(["/bin/chmod", "-N", str(self.path)], check=True)
        else:
            acl = struct.pack("<I", 2) + b"".join(
                struct.pack("<HHI", tag, perm, uid)
                for tag, perm, uid in (
                    (1, 6, 0xFFFFFFFF),
                    (2, 4, os.getuid() + 1),
                    (4, 0, 0xFFFFFFFF),
                    (16, 0, 0xFFFFFFFF),
                    (32, 0, 0xFFFFFFFF),
                )
            )
            os.setxattr(self.path, "system.posix_acl_access", acl)
            try:
                self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
                with self.acquire() as lease, self.assertRaises(StorageAdmissionError):
                    self.storage.read_namespace_record(lease)
            finally:
                os.removexattr(self.path, "system.posix_acl_access")
        with self.acquire() as lease:
            self.assertIsInstance(
                self.storage.read_namespace_record(lease), StorageCheckedNamespace
            )

    def test_entry_replacement_and_detachment_during_read_refuse(self) -> None:
        original = self.query.read_once
        for replacement in (True, False):
            self.path.write_bytes(self.payload)
            self.path.chmod(0o600)
            other = self.root / "replacement"
            if replacement:
                other.write_bytes(self.payload)
                other.chmod(0o600)
            changed = False

            def replace(
                query: object,
                fd: int,
                count: int,
                replacement: bool = replacement,
                other: Path = other,
            ) -> bytes:
                nonlocal changed
                data = original(cast("NativeRootQueries", query), fd, count)
                if not changed:
                    changed = True
                    if replacement:
                        other.replace(self.path)
                    else:
                        self.path.unlink()
                return data

            with (
                self.acquire() as lease,
                patch.object(self.query, "read_once", replace),
                self.assertRaises(StorageAdmissionError),
            ):
                self.storage.read_namespace_record(lease)

    def test_replacement_immediately_after_open_is_detected_before_read(self) -> None:
        other = self.root / "replacement"
        other.write_bytes(self.payload)
        other.chmod(0o600)
        original_open = os.open

        def replace(path: str, flags: int, *, dir_fd: int) -> int:
            fd = original_open(path, flags, dir_fd=dir_fd)
            other.replace(self.path)
            return fd

        with (
            self.acquire() as lease,
            patch("os.open", side_effect=replace),
            patch.object(self.query, "read_once") as read,
        ):
            with self.assertRaises(StorageAdmissionError):
                self.storage.read_namespace_record(lease)
            read.assert_not_called()

    def test_same_identity_content_mutation_and_root_principal_change_refuse(
        self,
    ) -> None:
        original = self.query.read_once
        inode = self.path.stat().st_ino
        changed = False

        def mutate(query: object, fd: int, count: int) -> bytes:
            nonlocal changed
            data = original(cast("NativeRootQueries", query), fd, count)
            if not changed:
                changed = True
                self.path.write_bytes(self.payload.replace(b"a" * 32, b"c" * 32))
            return data

        with (
            self.acquire() as lease,
            patch.object(self.query, "read_once", mutate),
            self.assertRaises(NamespaceChangedError),
        ):
            self.storage.read_namespace_record(lease)
        self.assertEqual(self.path.stat().st_ino, inode)
        with self.acquire() as lease:
            principal_changed = False

            def change_principal(query: object, fd: int, count: int) -> bytes:
                nonlocal principal_changed
                data = original(cast("NativeRootQueries", query), fd, count)
                if not principal_changed:
                    principal_changed = True
                    principal_patch.start()
                return data

            principal_patch = patch.object(
                self.storage,
                "current_principal",
                return_value=PosixPrincipal(os.getuid() + 1),
            )
            try:
                with (
                    patch.object(self.query, "read_once", change_principal),
                    self.assertRaises(StorageAdmissionError),
                ):
                    self.storage.read_namespace_record(lease)
            finally:
                principal_patch.stop()

    def test_file_protection_changes_and_native_query_failure_refuse(self) -> None:
        original = self.query.read_once

        def chmod(query: object, fd: int, count: int) -> bytes:
            data = original(cast("NativeRootQueries", query), fd, count)
            self.path.chmod(0o644)
            return data

        with (
            self.acquire() as lease,
            patch.object(self.query, "read_once", chmod),
            self.assertRaises(StorageAdmissionError),
        ):
            self.storage.read_namespace_record(lease)
        self.path.chmod(0o600)
        original_protection = self.query.protection

        def fail_file(query: object, fd: int, mode: int) -> None:
            if mode == 0o600:
                raise OSError("synthetic query failure")
            original_protection(cast("NativeRootQueries", query), fd, mode)

        with (
            self.acquire() as lease,
            patch.object(self.query, "protection", fail_file),
            self.assertRaises(NamespaceReadError),
        ):
            self.storage.read_namespace_record(lease)

    def test_malformed_empty_unknown_and_exact_limit_never_return_truncated_record(
        self,
    ) -> None:
        for payload in (
            b"",
            b"secret-fixture",
            self.payload.replace(b'"schema_version":1', b'"schema_version":2'),
            b"x" * 4096,
        ):
            self.path.write_bytes(payload)
            with (
                self.acquire() as lease,
                self.assertRaises(NamespaceMalformedError) as error,
            ):
                self.storage.read_namespace_record(lease)
            self.assertNotIn("secret-fixture", str(error.exception))
        self.path.write_bytes(b"x" * 4097)
        with self.acquire() as lease, patch.object(self.query, "read_once") as read:
            with self.assertRaises(NamespaceLimitError):
                self.storage.read_namespace_record(lease)
            read.assert_not_called()

    def test_partial_reads_and_eintr_are_bounded(self) -> None:
        original = self.query.read_once
        requests: list[int] = []

        def partial(query: object, fd: int, count: int) -> bytes:
            requests.append(count)
            if len(requests) == 1:
                raise InterruptedError()
            return original(cast("NativeRootQueries", query), fd, min(count, 64))

        with self.acquire() as lease, patch.object(self.query, "read_once", partial):
            result = self.storage.read_namespace_record(lease)
            self.assertIsInstance(result, StorageCheckedNamespace)
        self.assertLessEqual(len(requests), 16)
        self.assertLessEqual(sum(requests), 4097)
        for outcome in (InterruptedError(), b"x"):
            with (
                self.acquire() as lease,
                patch.object(
                    self.query,
                    "read_once",
                    side_effect=outcome if isinstance(outcome, Exception) else None,
                    return_value=outcome,
                ) as read,
            ):
                with self.assertRaises(NamespaceLimitError):
                    self.storage.read_namespace_record(lease)
                self.assertLessEqual(read.call_count, 16)
                self.assertLessEqual(
                    sum(call.args[1] for call in read.call_args_list), 4097
                )
        with (
            self.acquire() as lease,
            patch.object(self.query, "read_once", return_value=b""),
            self.assertRaises(NamespaceChangedError),
        ):
            self.storage.read_namespace_record(lease)

    def test_every_failure_closes_child_and_success_cannot_hide_close_failure(
        self,
    ) -> None:
        original_close = os.close
        for failure in (OSError("read failed"), RuntimeError("cancel fixture")):
            with self.acquire() as lease:
                owned_before = self.owned.copy()
                with (
                    patch.object(self.query, "read_once", side_effect=failure),
                    self.assertRaises((NamespaceReadError, RuntimeError)),
                ):
                    self.storage.read_namespace_record(lease)
                self.assertEqual(self.owned, owned_before)
                self.assertFalse(lease.closed)
        with self.acquire() as lease:
            uncertain: list[int] = []

            def fail_close(fd: int) -> None:
                uncertain.append(fd)
                raise OSError("close unconfirmed")

            try:
                with patch("os.close", side_effect=fail_close) as close:
                    with self.assertRaises(StorageReleaseError):
                        self.storage.read_namespace_record(lease)
                    with patch("os.open") as opened:
                        with self.assertRaises(StorageReleaseError):
                            self.storage.read_namespace_record(lease)
                        opened.assert_not_called()
                    self.assertEqual(close.call_count, 1)
                self.assertIn(uncertain[0], self.uncertain)
                with self.assertRaises(StorageReleaseError):
                    self.acquire()
            finally:
                # Test-only cleanup: the injected failure deliberately did not close.
                for fd in uncertain:
                    original_close(fd)
                    self.uncertain.remove(fd)
                    self.owned.remove(fd)

    def test_partial_ownership_registration_failure_still_closes_child(self) -> None:
        class FailingOwnership(set[int]):
            def add(self, element: int) -> None:
                raise MemoryError("synthetic ownership failure")

        original_open = os.open
        opened: list[int] = []

        def observe_open(path: str, flags: int, *, dir_fd: int) -> int:
            fd = original_open(path, flags, dir_fd=dir_fd)
            opened.append(fd)
            return fd

        with self.acquire() as lease:
            with (
                patch.object(self.storage, "_OWNED", FailingOwnership(self.owned)),
                patch("os.open", side_effect=observe_open),
                self.assertRaises(MemoryError),
            ):
                self.storage.read_namespace_record(lease)
            self.assertEqual(len(opened), 1)
            with self.assertRaises(OSError):
                os.fstat(opened[0])

    def test_inheritable_child_and_post_close_root_change_refuse(self) -> None:
        with (
            self.acquire() as lease,
            patch("os.get_inheritable", return_value=True),
            self.assertRaises(StorageAdmissionError),
        ):
            self.storage.read_namespace_record(lease)
        original_close = os.close

        def change_after_close(fd: int) -> None:
            original_close(fd)
            os.fchmod(self.fd, 0o500)

        with (
            self.acquire() as lease,
            patch("os.close", side_effect=change_after_close),
            self.assertRaises(StorageAdmissionError),
        ):
            self.storage.read_namespace_record(lease)


@unittest.skipUnless(sys.platform in {"darwin", "linux"}, "POSIX native candidate only")
class NativeNamespaceReadTests(unittest.TestCase):
    def test_native_read_bounds_errors_and_interrupts(self) -> None:
        from mos_eisley.platform import posix_storage_native as native

        query = native.NativeRootQueries()
        for count in (0, -1, 4098):
            with self.assertRaises(ValueError):
                query.read_once(0, count)
        for size, code, error in (
            (-1, errno.EINTR, InterruptedError),
            (-1, errno.EIO, StorageAdmissionError),
            (5, 0, StorageAdmissionError),
        ):

            def read(*args: object, code: int = code, size: int = size) -> int:
                ctypes.set_errno(code)
                return size

            with (
                patch.object(native, "_function", return_value=read),
                self.assertRaises(error),
            ):
                query.read_once(0, 4)


if __name__ == "__main__":
    unittest.main()
