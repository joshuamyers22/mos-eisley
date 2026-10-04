"""Direct POSIX private-root candidate; public storage selection stays closed."""

import os
import stat
from dataclasses import dataclass, field
from hashlib import sha256
from threading import RLock
from types import TracebackType
from typing import Never, SupportsIndex

from mos_eisley.platform.identity import (
    PosixDescriptor,
    PosixFileIdentity,
    PosixPrincipal,
)
from mos_eisley.platform.identity_wire import (
    MAX_IDENTITY_WIRE_BYTES,
    IdentityWireError,
    decode_namespace_record,
)
from mos_eisley.platform.posix_identity import current_principal
from mos_eisley.platform.posix_storage_native import (
    NativeRootQueries,
    require_candidate_host,
)
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
)

_LOCK = RLock()
_OWNED: set[int] = set()
_UNCERTAIN: set[int] = set()
_MAX_LEASES = 64
_TOKEN = object()
_NAMESPACE_CHILD = "identity-namespace.v1.json"
_MAX_READ_ATTEMPTS = 16


@dataclass(frozen=True, slots=True)
class PrivateDirectoryObservation:
    """Fresh advisory metadata; not enrollment or write authority."""

    principal: PosixPrincipal = field(repr=False)
    identity: PosixFileIdentity = field(repr=False)
    mode: int
    filesystem_policy: str
    filesystem_id: bytes = field(repr=False)
    mount_flags: int
    extended_mount_flags: int
    changed_ns: int = field(repr=False)


def _observe(fd: int, expected: PosixPrincipal) -> PrivateDirectoryObservation:
    import fcntl

    if current_principal() != expected:
        raise StorageAdmissionError("directory principal changed or mismatched")
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    if flags & os.O_ACCMODE != os.O_RDONLY or flags & getattr(os, "O_PATH", 0):
        raise StorageAdmissionError("directory reference requires read-only access")
    info = os.fstat(fd)
    mode = stat.S_IMODE(info.st_mode)
    if not stat.S_ISDIR(info.st_mode) or mode not in (0o700, 0o500):
        raise StorageAdmissionError("directory type or mode is ineligible")
    if info.st_uid != expected.uid or info.st_nlink == 0:
        raise StorageAdmissionError("directory owner or attachment is ineligible")
    try:
        query = NativeRootQueries()
    except (OSError, AttributeError) as error:
        raise StorageAdmissionError("directory native binding failed") from error
    policy, filesystem_id, mount_flags, extended_mount_flags = query.filesystem(fd)
    query.protection(fd, mode)
    after = os.fstat(fd)
    if (
        current_principal() != expected
        or (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_ctime_ns,
        )
        != (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_uid,
            info.st_gid,
            info.st_nlink,
            info.st_ctime_ns,
        )
        or fcntl.fcntl(fd, fcntl.F_GETFL) != flags
    ):
        raise StorageAdmissionError("directory changed during observation")
    return PrivateDirectoryObservation(
        expected,
        PosixFileIdentity(info.st_dev, info.st_ino),
        mode,
        policy,
        filesystem_id,
        mount_flags,
        extended_mount_flags,
        info.st_ctime_ns,
    )


def _release(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        _UNCERTAIN.add(fd)
        raise StorageReleaseError("storage reference release is unconfirmed") from None
    else:
        _OWNED.discard(fd)


def _record_snapshot(info: os.stat_result) -> tuple[int, ...]:
    # Exclude atime: ordinary read effects do not change publication binding.
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _observe_record(
    fd: int, root: PrivateDirectoryObservation, query: NativeRootQueries
) -> tuple[int, ...]:
    if current_principal() != root.principal:
        raise NamespaceChangedError("namespace principal changed")
    info = os.fstat(fd)
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISREG(info.st_mode)
        or mode not in (0o600, 0o400)
        or info.st_nlink != 1
        or info.st_uid != root.principal.uid
        or info.st_dev != root.identity.device
    ):
        raise StorageAdmissionError("namespace object protection is ineligible")
    if not 0 <= info.st_size <= MAX_IDENTITY_WIRE_BYTES:
        raise NamespaceLimitError("namespace record exceeds byte capacity")
    if query.filesystem(fd) != (
        root.filesystem_policy,
        root.filesystem_id,
        root.mount_flags,
        root.extended_mount_flags,
    ):
        raise StorageAdmissionError("namespace filesystem differs from root")
    query.protection(fd, mode)
    before = _record_snapshot(info)
    if (
        current_principal() != root.principal
        or _record_snapshot(os.fstat(fd)) != before
    ):
        raise NamespaceChangedError("namespace object changed during observation")
    return before


def _check_record_entry(root_fd: int, observed: tuple[int, ...]) -> None:
    entry = os.stat(_NAMESPACE_CHILD, dir_fd=root_fd, follow_symlinks=False)
    if _record_snapshot(entry) != observed:
        raise NamespaceChangedError("namespace directory entry changed")


def _bounded_record_bytes(fd: int, query: NativeRootQueries, size: int) -> bytes:
    parts: list[bytes] = []
    received = requested = 0
    for _ in range(_MAX_READ_ATTEMPTS):
        capacity = min(
            512, MAX_IDENTITY_WIRE_BYTES + 1 - requested, size + 1 - received
        )
        if capacity <= 0:
            break
        requested += capacity
        try:
            part = query.read_once(fd, capacity)
        except InterruptedError:
            continue
        if not part:
            if received != size:
                raise NamespaceChangedError("namespace size changed during read")
            return b"".join(parts)
        received += len(part)
        if received > MAX_IDENTITY_WIRE_BYTES:
            raise NamespaceLimitError("namespace record exceeds byte capacity")
        if received > size:
            raise NamespaceChangedError("namespace size changed during read")
        parts.append(part)
    raise NamespaceLimitError("namespace read attempt or request capacity exhausted")


class PrivateDirectoryLease:
    """Owned process-local candidate lease; explicit context-managed release."""

    def __init__(
        self, fd: int, observed: PrivateDirectoryObservation, *, token: object
    ) -> None:
        if token is not _TOKEN:
            raise TypeError("directory leases require live admission")
        self._fd: int | None = fd
        self._observed = observed

    def __repr__(self) -> str:
        return f"PrivateDirectoryLease(closed={self.closed})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        raise TypeError("directory leases cannot be serialized or copied")

    @property
    def closed(self) -> bool:
        with _LOCK:
            return self._fd is None

    def inspect(self) -> PrivateDirectoryObservation:
        with _LOCK:
            if self._fd is None:
                raise StorageLeaseClosedError("directory lease is closed")
            try:
                first = _observe(self._fd, self._observed.principal)
                second = _observe(self._fd, self._observed.principal)
            except (OSError, ValueError) as error:
                raise StorageAdmissionError("directory revalidation failed") from error
            if first != self._observed or second != first:
                raise StorageAdmissionError("directory observation changed")
            return second

    def close(self) -> None:
        with _LOCK:
            if self._fd is not None:
                fd, self._fd = self._fd, None
                _release(fd)

    def read_namespace_record(self) -> StorageCheckedNamespace | NamespaceMissing:
        """Observe only the fixed relative child; never mint enrollment authority."""
        with _LOCK:
            if self._fd is None:
                raise StorageLeaseClosedError("directory lease is closed")
            if _UNCERTAIN:
                raise StorageReleaseError("namespace acquisition is disabled")
            if len(_OWNED) >= _MAX_LEASES:
                raise StorageCapacityError("storage reference capacity is exhausted")
            root = self.inspect()
            try:
                fd = os.open(
                    _NAMESPACE_CHILD,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                    dir_fd=self._fd,
                )
            except FileNotFoundError:
                try:
                    os.stat(_NAMESPACE_CHILD, dir_fd=self._fd, follow_symlinks=False)
                except FileNotFoundError:
                    self.inspect()
                    return NamespaceMissing(root.identity)
                except OSError:
                    raise NamespaceReadError("namespace absence query failed") from None
                raise NamespaceChangedError(
                    "namespace appeared during absence query"
                ) from None
            except OSError:
                raise NamespaceReadError("namespace relative open failed") from None
            try:
                _OWNED.add(fd)
                if os.get_inheritable(fd):
                    raise StorageAdmissionError("namespace reference is inheritable")
                query = NativeRootQueries()
                before = _observe_record(fd, root, query)
                _check_record_entry(self._fd, before)
                payload = _bounded_record_bytes(fd, query, before[6])
                if _observe_record(fd, root, query) != before:
                    raise NamespaceChangedError("namespace object changed during read")
                _check_record_entry(self._fd, before)
                self.inspect()
                try:
                    record = decode_namespace_record(payload)
                except IdentityWireError:
                    raise NamespaceMalformedError(
                        "namespace record is malformed"
                    ) from None
                if record.principal != root.principal:
                    raise StorageAdmissionError("namespace record principal mismatched")
                result = StorageCheckedNamespace(
                    record,
                    root.identity,
                    PosixFileIdentity(before[0], before[1]),
                    sha256(payload).hexdigest(),
                )
            except StorageAdmissionError:
                raise
            except (OSError, ValueError, AttributeError):
                raise NamespaceReadError("namespace read or query failed") from None
            finally:
                _release(fd)
            self.inspect()
            return result

    def __enter__(self) -> "PrivateDirectoryLease":
        try:
            self.inspect()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def admit_private_directory(
    opened: PosixDescriptor, expected_principal: PosixPrincipal
) -> PrivateDirectoryLease:
    if (
        type(opened) is not PosixDescriptor
        or type(expected_principal) is not PosixPrincipal
    ):
        raise ValueError("admission requires a POSIX descriptor and principal")
    require_candidate_host()
    import fcntl

    with _LOCK:
        if _UNCERTAIN:
            raise StorageReleaseError("directory acquisition is disabled")
        if len(_OWNED) >= _MAX_LEASES:
            raise StorageCapacityError("directory lease capacity is exhausted")
        fd: int | None = None
        try:
            before = _observe(opened.fd, expected_principal)
            # Atomic CLOEXEC duplication preserves borrowed flags and shared offset.
            fd = fcntl.fcntl(opened.fd, fcntl.F_DUPFD_CLOEXEC, 0)
            _OWNED.add(fd)
            if os.get_inheritable(fd):
                raise StorageAdmissionError("directory duplicate is inheritable")
            after = _observe(fd, expected_principal)
            if after != before or _observe(opened.fd, expected_principal) != before:
                raise StorageAdmissionError("directory changed during acquisition")
            return PrivateDirectoryLease(fd, after, token=_TOKEN)
        except BaseException as error:
            if fd is not None:
                _release(fd)
            if isinstance(error, (OSError, ValueError)):
                raise StorageAdmissionError(
                    "private directory admission failed"
                ) from error
            raise


def read_namespace_record(
    root: PrivateDirectoryLease,
) -> StorageCheckedNamespace | NamespaceMissing:
    if type(root) is not PrivateDirectoryLease:
        raise ValueError("namespace reading requires a live POSIX directory lease")
    return root.read_namespace_record()
