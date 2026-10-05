"""POSIX identity observations; no ownership policy or descriptor lifecycle."""

import os
import stat

from mos_eisley.platform.identity import (
    IdentityContextError,
    IdentityQueryError,
    PosixDescriptor,
    PosixFileIdentity,
    PosixPrincipal,
)


def current_principal() -> PosixPrincipal:
    try:
        principal = PosixPrincipal(os.getuid())
        effective = PosixPrincipal(os.geteuid())
    except (OSError, ValueError) as error:
        raise IdentityQueryError("current principal query failed") from error
    if principal != effective:
        raise IdentityContextError("current principal context is unsupported")
    return principal


def file_identity(opened: PosixDescriptor) -> PosixFileIdentity:
    try:
        info = os.fstat(opened.fd)
        identity = PosixFileIdentity(info.st_dev, info.st_ino)
    except (OSError, ValueError) as error:
        raise IdentityQueryError("opened object identity query failed") from error
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise IdentityQueryError("opened object is ineligible for identity query")
    return identity
