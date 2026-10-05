"""Inert private-storage boundary; target admission remains gated."""

from dataclasses import dataclass, field
from typing import Never

from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.identity import (
    PosixDescriptor,
    PosixFileIdentity,
    PrincipalIdentity,
    WindowsHandle,
)
from mos_eisley.platform.identity_wire import NamespaceRecord


class StorageAdmissionError(OSError):
    """Opened storage cannot be admitted under the private-root policy."""


class StorageLeaseClosedError(StorageAdmissionError):
    """The owned lease has been released; no descriptor query was attempted."""


class StorageReleaseError(StorageAdmissionError):
    """Release is unconfirmed; affected acquisition is disabled until reset."""


class StorageCapacityError(StorageAdmissionError):
    """The bounded process-local lease capacity is exhausted."""


class NamespaceReadError(StorageAdmissionError):
    """The fixed child could not be opened or queried; not typed absence."""


class NamespaceChangedError(StorageAdmissionError):
    """Root, child selection or content changed during inspection."""


class NamespaceLimitError(StorageAdmissionError):
    """Record size or bounded read-attempt capacity was exceeded."""


class NamespaceMalformedError(StorageAdmissionError):
    """The selected bytes are not an exact supported namespace record."""


@dataclass(frozen=True, slots=True)
class NamespaceMissing:
    """Advisory absence; grants no creation or enrollment authority."""

    root_identity: PosixFileIdentity = field(repr=False)


@dataclass(frozen=True, slots=True)
class StorageCheckedNamespace:
    """Advisory record observation; cannot grant custody, enrollment or writes."""

    record: NamespaceRecord = field(repr=False)
    root_identity: PosixFileIdentity = field(repr=False)
    record_identity: PosixFileIdentity = field(repr=False)
    record_sha256: str = field(repr=False)


def admit_private_directory(
    opened: PosixDescriptor | WindowsHandle, expected_principal: PrincipalIdentity
) -> Never:
    """Refuse public admission until accountable target qualification completes."""
    raise UnsupportedPlatformError("private storage admission remains unqualified")


def read_namespace_record(root: object) -> Never:
    """Refuse public reads until accountable target qualification completes."""
    raise UnsupportedPlatformError("private namespace reading remains unqualified")
