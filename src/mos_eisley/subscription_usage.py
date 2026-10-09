"""Private locked one-use invocation ledger; uncertain slots never refund usage."""

from __future__ import annotations

import contextlib
import os
import stat
from collections.abc import Generator
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, TypeAdapter

from mos_eisley.core.models import Contract, Digest
from mos_eisley.platform.posix_storage_native import NativeRootQueries
from mos_eisley.providers.codex_subscription import write_receipt
from mos_eisley.subscription_authorization import (
    SubscriptionAuthorization,
    SubscriptionRole,
)

_OBJECT = TypeAdapter(dict[str, JsonValue])


def private_directory(path: Path) -> int:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        check_private(fd, directory=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def check_private(fd: int, *, directory: bool) -> None:
    info = os.fstat(fd)
    if (
        info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or not (
            stat.S_ISDIR(info.st_mode)
            if directory
            else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
        )
    ):
        raise ValueError("Subscription usage storage is not private")
    NativeRootQueries().protection(fd, stat.S_IMODE(info.st_mode))


def entry_names(directory: int) -> tuple[str, ...]:
    names: list[str] = []
    with os.scandir(directory) as entries:
        for entry in entries:
            if len(names) == 66:
                raise ValueError("Subscription ledger exceeds its entry bound")
            names.append(entry.name)
    return tuple(names)


def metadata(directory: int, name: str) -> dict[str, JsonValue]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        check_private(fd, directory=False)
        raw = os.read(fd, 16_001)
        if len(raw) > 16_000:
            raise ValueError("Subscription metadata exceeds its bound")
        return _OBJECT.validate_json(raw, strict=True)
    finally:
        os.close(fd)


class UsageReservation(Contract):
    authorization_sha256: Digest
    role: SubscriptionRole
    request_sha256: Digest
    call_id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$")]
    state: Literal["reserved"]
    billing_verified: Literal[False]


def reservation_metadata(
    directory: int, authorization: SubscriptionAuthorization
) -> UsageReservation:
    raw = metadata(directory, "reservation.json")
    if raw.get("billing_verified") is not False:
        raise ValueError("Subscription reservation cannot attest billing")
    result = UsageReservation.model_validate(raw)
    if result.authorization_sha256 != authorization.sha256:
        raise ValueError("Subscription reservation identity changed")
    authorization.grant(result.role)
    return result


class UsageSlot:
    def __init__(self, directory: int, path: Path) -> None:
        self.directory = directory
        self.path = path

    def complete(self) -> None:
        write_receipt(
            self.directory,
            "completion.json",
            {"state": "completed", "billing_verified": False},
        )


@contextlib.contextmanager
def reserve_usage(
    authorization: SubscriptionAuthorization,
    role: SubscriptionRole,
    request_sha256: str,
    call_id: str,
) -> Generator[UsageSlot, None, None]:
    import fcntl
    import re

    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}", call_id):
        raise ValueError("Subscription call identity is invalid")

    parent = private_directory(authorization.usage_root)
    directory = lock = slot = None
    try:
        name = authorization.authorization_id
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
        directory = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        check_private(directory, directory=True)
        lock = os.open(
            "lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=directory,
        )
        check_private(lock, directory=False)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        names = entry_names(directory)
        if len(names) > 66:
            raise ValueError("Subscription ledger exceeds its bound")
        if "binding.json" not in names:
            if set(names) != {"lock"}:
                raise ValueError("Subscription usage binding is missing")
            write_receipt(
                directory,
                "binding.json",
                {"authorization_sha256": authorization.sha256},
            )
        if metadata(directory, "binding.json") != {
            "authorization_sha256": authorization.sha256
        }:
            raise ValueError("Subscription usage authorization changed")
        slots = sorted(n for n in names if n.startswith("slot-"))
        if set(names) - {"lock", "binding.json", *slots} or slots != [
            f"slot-{i:04d}" for i in range(1, len(slots) + 1)
        ]:
            raise ValueError("Subscription usage history is malformed")
        role_calls = 0
        for previous in slots:
            prior = os.open(
                previous, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            try:
                check_private(prior, directory=True)
                reservation = reservation_metadata(prior, authorization)
                if reservation.call_id == call_id:
                    raise ValueError("Subscription call identity cannot be replayed")
                role_calls += reservation.role == role
                if metadata(prior, "completion.json") != {
                    "state": "completed",
                    "billing_verified": False,
                }:
                    raise ValueError("Prior subscription usage is uncertain")
            except FileNotFoundError:
                raise ValueError(
                    "Prior subscription usage is uncertain; explicit recovery required"
                ) from None
            finally:
                os.close(prior)
        if (
            len(slots) >= authorization.max_invocations
            or role_calls >= authorization.grant(role).max_invocations
        ):
            raise ValueError("Subscription invocation allowance exhausted")
        name = f"slot-{len(slots) + 1:04d}"
        os.mkdir(name, mode=0o700, dir_fd=directory)
        os.fsync(directory)
        slot = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
        )
        check_private(slot, directory=True)
        write_receipt(
            slot,
            "reservation.json",
            {
                "authorization_sha256": authorization.sha256,
                "role": role,
                "call_id": call_id,
                "request_sha256": request_sha256,
                "state": "reserved",
                "billing_verified": False,
            },
        )
        yield UsageSlot(
            slot, authorization.usage_root / authorization.authorization_id / name
        )
    finally:
        for fd in (slot, lock, directory, parent):
            if fd is not None:
                os.close(fd)


def verify_saved_attempts(
    authorization: SubscriptionAuthorization, consumed: int
) -> None:
    """A saved dispatched attempt cannot resume with missing or uncertain usage."""
    if consumed == 0:
        return
    import fcntl

    root = private_directory(authorization.usage_root)
    directory = lock = None
    try:
        directory = os.open(
            authorization.authorization_id,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=root,
        )
        check_private(directory, directory=True)
        lock = os.open(
            "lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        check_private(lock, directory=False)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if metadata(directory, "binding.json") != {
            "authorization_sha256": authorization.sha256
        }:
            raise ValueError("Saved subscription usage binding changed")
        names = sorted(n for n in entry_names(directory) if n.startswith("slot-"))
        if len(names) > 64 or names != [
            f"slot-{i:04d}" for i in range(1, len(names) + 1)
        ]:
            raise ValueError("Saved subscription usage history is malformed")
        calls: list[str] = []
        for name in names:
            slot = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            try:
                check_private(slot, directory=True)
                reservation = reservation_metadata(slot, authorization)
                call = reservation.call_id
                if reservation.authorization_sha256 != authorization.sha256 or metadata(
                    slot, "completion.json"
                ) != {"state": "completed", "billing_verified": False}:
                    raise ValueError("Saved subscription usage is uncertain or changed")
                calls.append(call)
            finally:
                os.close(slot)
        for attempt in range(consumed):
            if not any(
                call == f"chat-{attempt:04d}"
                or call.startswith(f"coding-{attempt:04d}.")
                for call in calls
            ):
                raise ValueError("Saved subscription attempt has missing usage state")
    finally:
        for fd in (lock, directory, root):
            if fd is not None:
                os.close(fd)
