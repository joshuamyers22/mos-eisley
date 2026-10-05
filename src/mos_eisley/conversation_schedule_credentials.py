"""Owner-only native credentials; uncertain writes never activate ingress."""

import asyncio
import fcntl
import math
import os
import re
import stat
import time
from collections.abc import Callable, Generator
from concurrent.futures import Future
from contextlib import contextmanager, suppress
from pathlib import Path
from threading import Lock, Thread
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, SecretStr

from mos_eisley.conversation_schedule_handlers import PendingRead
from mos_eisley.conversation_schedule_transport import SERVICE, IngressTransportGrant
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.tools.mcp_oauth_store import CredentialBackend, credential_backend


class CredentialVaultError(ValueError):
    """Generic diagnostic; native errors and credential material stay private."""


class CredentialLifecycle(Contract):
    owner_uid: Annotated[int, Field(ge=0)]
    account: Digest
    operation_id: Identifier
    status: Literal["pending", "active", "revoking", "revoked"]

    @property
    def unresolved(self) -> bool:
        return self.status in {"pending", "revoking"}


class NativeIngressVault:
    """Explicit host provisioning with durable denial and serialized native writes."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        backend: CredentialBackend | None = None,
        timeout: float = 2.0,
    ) -> None:
        if not math.isfinite(timeout) or not 0 < timeout <= 10:
            raise CredentialVaultError("Invalid credential deadline.")
        self.directory = directory or Path.home() / ".mos-eisley-ingress-credentials"
        self.owner = os.geteuid()
        self.backend = backend
        self.timeout = timeout
        self._pending: PendingRead | None = None
        self._lane = Lock()

    def _owner(self, grant: IngressTransportGrant | None = None) -> None:
        if (
            os.getuid() != self.owner
            or os.geteuid() != self.owner
            or (grant is not None and grant.binding.owner_uid != self.owner)
        ):
            raise CredentialVaultError("Credential owner unavailable.")

    def _private(self, fd: int, *, directory: bool = False) -> None:
        info = os.fstat(fd)
        if (
            info.st_uid != self.owner
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or not (
                stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
            )
            or (not directory and info.st_nlink != 1)
        ):
            raise CredentialVaultError("Credential storage unavailable.")

    @contextmanager
    def _root(self, *, create: bool = True) -> Generator[int]:
        self._owner()
        if create:
            self.directory.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self._private(fd, directory=True)
            yield fd
        finally:
            os.close(fd)

    @contextmanager
    def _lock(self, root: int, name: str, *, create: bool = True) -> Generator[int]:
        fd = os.open(
            name,
            os.O_RDWR | (os.O_CREAT if create else 0) | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=root,
        )
        try:
            self._private(fd)
            yield fd
        finally:
            os.close(fd)

    def _read(self, root: int, account: str) -> CredentialLifecycle | None:
        try:
            fd = os.open(
                account + ".json",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root,
            )
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            self._private(stream.fileno())
            if os.fstat(stream.fileno()).st_size > 2048:
                raise CredentialVaultError("Credential storage unavailable.")
            value = CredentialLifecycle.model_validate_json(stream.read(2049))
        if value.account != account or value.owner_uid != self.owner:
            raise CredentialVaultError("Credential storage unavailable.")
        return value

    def _write(self, root: int, value: CredentialLifecycle) -> None:
        name = uuid4().hex + ".tmp"
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=root,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(canonical_bytes(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, value.account + ".json", src_dir_fd=root, dst_dir_fd=root)
            os.fsync(root)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(name, dir_fd=root)

    def inspect(self, grant: IngressTransportGrant) -> CredentialLifecycle | None:
        try:
            self._owner(grant)
            with self._root(create=False) as root:
                return self._read(root, grant.account)
        except FileNotFoundError:
            return None
        except Exception:
            raise CredentialVaultError("Credential inspection unavailable.") from None

    def _transition(
        self,
        grant: IngressTransportGrant,
        *,
        revoke: bool = False,
        finish: CredentialLifecycle | None = None,
    ) -> CredentialLifecycle:
        self._owner(grant)
        with (
            self._root() as root,
            self._lock(root, grant.account + ".state.lock") as fd,
        ):
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            current = self._read(root, grant.account)
            if finish is not None:
                if current != finish:
                    raise CredentialVaultError("Credential operation superseded.")
                value = finish.model_copy(
                    update={
                        "status": "revoked" if finish.status == "revoking" else "active"
                    }
                )
            else:
                if not revoke and current is not None:
                    raise CredentialVaultError(
                        "Credential already retained; inspect before retry."
                    )
                value = CredentialLifecycle(
                    owner_uid=self.owner,
                    account=grant.account,
                    operation_id=uuid4().hex,
                    status="revoking" if revoke else "pending",
                )
            self._write(root, value)
            return value

    async def _execute[T](
        self, grant: IngressTransportGrant, call: Callable[[], T]
    ) -> T:
        self._owner(grant)
        deadline = time.monotonic() + self.timeout
        with self._lane:
            if self._pending is not None and not self._pending.done():
                raise CredentialVaultError(
                    "Credential operation unresolved; inspect before retry."
                )
            result: Future[T] = Future()
            self._pending = result

        def run() -> None:
            try:
                with (
                    self._root() as root,
                    self._lock(root, grant.account + ".native.lock") as fd,
                ):
                    while True:
                        self._owner(grant)
                        if time.monotonic() >= deadline:
                            raise CredentialVaultError("Credential operation expired.")
                        try:
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            time.sleep(0.01)
                    result.set_result(call())
            except BaseException:
                result.set_exception(
                    CredentialVaultError("Native credential operation unavailable.")
                )

        try:
            try:
                Thread(target=run, name="mos-ingress-vault", daemon=True).start()
            except Exception:
                result.set_exception(
                    CredentialVaultError("Credential worker unavailable.")
                )
                raise CredentialVaultError("Credential worker unavailable.") from None
            while not result.done():
                if time.monotonic() >= deadline:
                    raise CredentialVaultError(
                        "Credential operation unresolved; inspect before retry."
                    )
                await asyncio.sleep(0.01)
            self._owner(grant)
            if time.monotonic() >= deadline:
                raise CredentialVaultError(
                    "Credential operation unresolved; inspect before retry."
                )
            return result.result()
        except asyncio.CancelledError:
            raise
        except Exception:
            raise CredentialVaultError(
                "Credential operation unavailable; inspect before retry."
            ) from None

    def _backend(self) -> CredentialBackend:
        return self.backend if self.backend is not None else credential_backend()

    def _authority(self, account: str) -> CredentialLifecycle | None:
        try:
            with self._root(create=False) as root:
                before = self._read(root, account)
                if before is None:
                    return None
                with self._lock(root, account + ".state.lock", create=False) as fd:
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    return self._read(root, account)
        except FileNotFoundError:
            return None

    def _lookup_value(self, service: str, username: str) -> str | None:
        self._owner()
        if service != SERVICE or not re.fullmatch(r"[0-9a-f]{64}", username):
            raise CredentialVaultError("Credential scope unavailable.")
        before = self._authority(username)
        if before is None or before.status != "active":
            return None
        value = self._backend().get_password(SERVICE, username)
        self._owner()
        if self._authority(username) != before:
            raise CredentialVaultError("Credential authorization changed.")
        return value

    def get_password(self, service: str, username: str) -> str | None:
        """Read-only port with surrounding authority checks and generic errors."""
        try:
            return self._lookup_value(service, username)
        except Exception:
            raise CredentialVaultError("Credential lookup unavailable.") from None

    async def lookup(self, grant: IngressTransportGrant) -> SecretStr | None:
        try:
            value = await self._execute(
                grant, lambda: self.get_password(SERVICE, grant.account)
            )
            if value is None:
                return None
            if (
                len(value) != 64
                or not re.fullmatch(r"[0-9a-f]{64}", value)
                or digest(value.encode()) != grant.credential_sha256
            ):
                raise CredentialVaultError("Credential unavailable.")
            return SecretStr(value)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise CredentialVaultError("Credential lookup unavailable.") from None

    def _token(self, grant: IngressTransportGrant, token: SecretStr) -> str:
        secret = token.get_secret_value()
        if (
            len(secret) != 64
            or not re.fullmatch(r"[0-9a-f]{64}", secret)
            or digest(secret.encode()) != grant.credential_sha256
        ):
            raise CredentialVaultError("Credential does not match grant.")
        return secret

    async def provision(self, grant: IngressTransportGrant, token: SecretStr) -> None:
        """One grant creation; lost outcomes require inspection before further work."""
        try:
            self._owner(grant)
            secret = self._token(grant, token)
            pending = self._transition(grant)

            def write() -> None:
                backend = self._backend()
                if self.inspect(grant) != pending:
                    raise CredentialVaultError("Credential operation superseded.")
                backend.set_password(SERVICE, grant.account, secret)
                if backend.get_password(SERVICE, grant.account) != secret:
                    raise CredentialVaultError("Credential verification unavailable.")

            await self._execute(grant, write)
            self._transition(grant, finish=pending)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise CredentialVaultError(
                "Credential provisioning unavailable; inspect before retry."
            ) from None

    async def revoke(self, grant: IngressTransportGrant) -> None:
        """Persist denial first; a late native write cannot restore authorization."""
        try:
            revoking = self._transition(grant, revoke=True)

            def delete() -> None:
                backend = self._backend()
                self._owner(grant)
                if backend.get_password(SERVICE, grant.account) is not None:
                    backend.delete_password(SERVICE, grant.account)
                if backend.get_password(SERVICE, grant.account) is not None:
                    raise CredentialVaultError("Credential revocation unavailable.")

            await self._execute(grant, delete)
            self._transition(grant, finish=revoking)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise CredentialVaultError(
                "Credential revocation unresolved; inspect before retry."
            ) from None

    async def rotate(
        self,
        previous: IngressTransportGrant,
        replacement: IngressTransportGrant,
        token: SecretStr,
    ) -> None:
        self._owner(previous)
        self._owner(replacement)
        if (
            previous.model_copy(
                update={"credential_sha256": replacement.credential_sha256}
            )
            != replacement
            or previous.account == replacement.account
        ):
            raise CredentialVaultError("Credential rotation scope unavailable.")
        self._token(replacement, token)
        await self.revoke(previous)
        await self.provision(replacement, token)

    # Mutations require a frozen grant through the explicit lifecycle API.
    def set_password(self, service: str, username: str, password: str) -> None:
        raise CredentialVaultError("Explicit credential provisioning required.")

    def delete_password(self, service: str, username: str) -> None:
        raise CredentialVaultError("Explicit credential revocation required.")
