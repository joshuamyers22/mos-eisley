"""OS keychain credentials and user-owned cross-process refresh locks."""

import asyncio
import fcntl
import os
import stat
import sys
from collections.abc import AsyncGenerator, Awaitable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol, cast


class OAuthFailure(ValueError):
    """Safe diagnostic; never include OAuth responses or secrets."""


class CredentialBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def credential_backend() -> CredentialBackend:
    # Select native backends directly: no plaintext or environment-selected plugin.
    if sys.platform == "darwin":
        from keyring.backends.macOS import Keyring

        return cast(CredentialBackend, Keyring())
    if sys.platform == "linux":
        from keyring.backends.SecretService import Keyring

        return cast(CredentialBackend, Keyring())
    raise OAuthFailure("OAuth requires macOS Keychain or Linux Secret Service")


async def keychain_operation[T](operation: Awaitable[T]) -> T:
    # A blocking keychain mutation cannot be cancelled. Keep the refresh lock until
    # its worker finishes so a late save cannot undo a concurrent logout.
    task = asyncio.ensure_future(operation)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        if not task.cancelled():
            task.exception()
        raise asyncio.CancelledError
    return task.result()


class OAuthStore:
    service = "mos-eisley.mcp.oauth.v1"

    def __init__(self, key: str) -> None:
        self.key = key
        self.owner = os.geteuid()
        self.backend = credential_backend()
        self.directory = Path.home() / ".mos-eisley-oauth-locks"

    def check_owner(self) -> None:
        if os.geteuid() != self.owner:
            raise OAuthFailure("OAuth credential owner changed")

    async def get(self) -> str | None:
        self.check_owner()
        try:
            value = await keychain_operation(
                asyncio.to_thread(self.backend.get_password, self.service, self.key)
            )
            if value is not None and len(value) > 65536:
                raise OAuthFailure("OAuth credential record exceeds limit")
            return value
        except Exception:
            raise OAuthFailure("OAuth keychain unavailable or invalid") from None

    async def set(self, value: str) -> None:
        self.check_owner()
        try:
            await keychain_operation(
                asyncio.to_thread(
                    self.backend.set_password, self.service, self.key, value
                )
            )
        except Exception:
            raise OAuthFailure("OAuth credentials could not be saved") from None

    async def delete(self) -> None:
        self.check_owner()
        try:
            if await self.get() is not None:
                await keychain_operation(
                    asyncio.to_thread(
                        self.backend.delete_password, self.service, self.key
                    )
                )
        except Exception:
            raise OAuthFailure("OAuth credentials could not be removed") from None

    @asynccontextmanager
    async def locked(self) -> AsyncGenerator[None]:
        self.check_owner()
        self.directory.mkdir(mode=0o700, exist_ok=True)
        parent = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptor: int | None = None
        try:
            info = os.fstat(parent)
            if info.st_uid != self.owner or stat.S_IMODE(info.st_mode) != 0o700:
                raise OAuthFailure(
                    "OAuth lock directory must be private and user-owned"
                )
            descriptor = os.open(
                self.key + ".lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=parent,
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != self.owner
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise OAuthFailure("OAuth lock file must be private and user-owned")
            async with asyncio.timeout(30):
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        await asyncio.sleep(0.05)
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(parent)
