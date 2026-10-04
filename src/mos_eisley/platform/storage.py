"""Inert private-storage boundary; target admission remains gated."""

from typing import Never

from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.identity import (
    PosixDescriptor,
    PrincipalIdentity,
    WindowsHandle,
)


class StorageAdmissionError(OSError):
    """Opened storage cannot be admitted under the private-root policy."""


class StorageLeaseClosedError(StorageAdmissionError):
    """The owned lease has been released; no descriptor query was attempted."""


class StorageReleaseError(StorageAdmissionError):
    """Release is unconfirmed; affected acquisition is disabled until reset."""


class StorageCapacityError(StorageAdmissionError):
    """The bounded process-local lease capacity is exhausted."""


def admit_private_directory(
    opened: PosixDescriptor | WindowsHandle, expected_principal: PrincipalIdentity
) -> Never:
    """Refuse public admission until accountable target qualification completes."""
    raise UnsupportedPlatformError("private storage admission remains unqualified")
