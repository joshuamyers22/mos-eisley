"""Direct POSIX private-root candidate; public storage selection stays closed."""

import os
import stat
from dataclasses import dataclass, field
from threading import RLock
from types import TracebackType
from typing import Never, SupportsIndex

from mos_eisley.platform.identity import (
    PosixDescriptor,
    PosixFileIdentity,
    PosixPrincipal,
)
from mos_eisley.platform.posix_identity import current_principal
from mos_eisley.platform.posix_storage_native import (
    NativeRootQueries,
    require_candidate_host,
)
from mos_eisley.platform.storage import (
    StorageAdmissionError,
    StorageCapacityError,
    StorageLeaseClosedError,
    StorageReleaseError,
)

_LOCK = RLock()
_OWNED: set[int] = set()
_UNCERTAIN: set[int] = set()
_MAX_LEASES = 64
_TOKEN = object()


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
        raise StorageReleaseError("directory release is unconfirmed") from None
    else:
        _OWNED.remove(fd)


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
