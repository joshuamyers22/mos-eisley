"""Native-vault lifecycle authority, bounded mutations and late-write denial."""

import asyncio
import fcntl
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import test_conversation_schedule_transport as transport_fixtures
from pydantic import SecretStr

from mos_eisley.conversation_schedule_credentials import (
    CredentialLifecycle,
    CredentialVaultError,
    NativeIngressVault,
)
from mos_eisley.conversation_schedule_transport import SERVICE
from mos_eisley.core.models import digest


class MemoryVault:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.calls: list[str] = []
        self.hook: Callable[[str], None] = lambda _: None

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append("get")
        self.hook("get")
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.calls.append("set")
        self.hook("set")
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.calls.append("delete")
        self.hook("delete")
        self.values.pop((service, username), None)


class CredentialTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.helper = transport_fixtures.TransportTests()
        self.helper.setUp()

    async def test_provision_lookup_rotate_revoke_and_tombstones(self) -> None:
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            adapter, _ = self.helper.make(chat)
            grant = adapter.grant
            backend = MemoryVault()
            with TemporaryDirectory() as directory:
                vault = NativeIngressVault(Path(directory), backend=backend)
                token = SecretStr(transport_fixtures.TOKEN)
                before = chat.state
                await vault.provision(grant, token)
                self.assertEqual(await vault.lookup(grant), token)
                active = vault.inspect(grant)
                assert active is not None
                self.assertEqual(active.status, "active")
                replacement = grant.model_copy(
                    update={"credential_sha256": digest(("e" * 64).encode())}
                )
                await vault.rotate(grant, replacement, SecretStr("e" * 64))
                self.assertIsNone(await vault.lookup(grant))
                self.assertEqual(await vault.lookup(replacement), SecretStr("e" * 64))
                await vault.revoke(replacement)
                self.assertIsNone(await vault.lookup(replacement))
                self.assertEqual(backend.values, {})
                restarted = NativeIngressVault(Path(directory), backend=backend)
                with self.assertRaises(CredentialVaultError):
                    await restarted.provision(grant, token)
                self.assertEqual(chat.state, before)
                for path in Path(directory).glob("*.json"):
                    self.assertNotIn(transport_fixtures.TOKEN, path.read_text())
                    self.assertNotIn("e" * 64, path.read_text())

    async def test_foreign_owner_scope_and_unsafe_storage_precede_native_access(self):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            grant = self.helper.make(chat)[0].grant
            backend = MemoryVault()
            with TemporaryDirectory() as directory:
                vault = NativeIngressVault(Path(directory) / "private", backend=backend)
                foreign = grant.model_copy(
                    update={
                        "binding": grant.binding.model_copy(
                            update={"owner_uid": grant.binding.owner_uid + 1}
                        )
                    }
                )
                for action in (vault.provision,):
                    with self.assertRaises(CredentialVaultError):
                        await action(foreign, SecretStr(transport_fixtures.TOKEN))
                with self.assertRaises(CredentialVaultError):
                    await vault.revoke(foreign)
                with self.assertRaises(CredentialVaultError):
                    await vault.lookup(foreign)
                self.assertFalse(vault.directory.exists())
                vault.directory.mkdir(mode=0o755)
                vault.directory.chmod(0o755)
                with self.assertRaises(CredentialVaultError):
                    await vault.provision(grant, SecretStr(transport_fixtures.TOKEN))
                self.assertEqual(backend.calls, [])

    async def test_timeout_and_cancelled_provision_never_activate_late_write(self):
        for cancel in (False, True):
            with self.helper.helper.session(
                transport_fixtures.fixtures.ConversationStore
            ) as (chat, *_):
                grant = self.helper.make(chat)[0].grant
                backend = MemoryVault()
                release, entered = Event(), Event()

                def hang(
                    kind: str, entered: Event = entered, release: Event = release
                ) -> None:
                    if kind == "set":
                        entered.set()
                        release.wait(2)

                backend.hook = hang
                with TemporaryDirectory() as directory:
                    vault = NativeIngressVault(
                        Path(directory), backend=backend, timeout=0.05
                    )
                    task = asyncio.create_task(
                        vault.provision(grant, SecretStr(transport_fixtures.TOKEN))
                    )
                    try:
                        await transport_fixtures.until(entered.is_set)
                        if cancel:
                            task.cancel()
                            with self.assertRaises(asyncio.CancelledError):
                                await task
                        else:
                            with self.assertRaises(CredentialVaultError):
                                await task
                        self.assertIsNone(vault.get_password(SERVICE, grant.account))
                        with self.assertRaises(CredentialVaultError):
                            await vault.revoke(grant)
                        self.assertIsNone(vault.get_password(SERVICE, grant.account))
                    finally:
                        release.set()
                        await asyncio.gather(task, return_exceptions=True)
                    await transport_fixtures.until(
                        lambda: (SERVICE, grant.account) in backend.values  # noqa: B023
                    )
                    restarted = NativeIngressVault(Path(directory), backend=backend)
                    self.assertIsNone(restarted.get_password(SERVICE, grant.account))
                    backend.hook = lambda _: None
                    await restarted.revoke(grant)
                    self.assertEqual(backend.values, {})
                    with self.assertRaises(CredentialVaultError):
                        await restarted.provision(
                            grant, SecretStr(transport_fixtures.TOKEN)
                        )

    async def test_revocation_failure_keeps_durable_denial_and_generic_errors(self):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            grant = self.helper.make(chat)[0].grant
            backend = MemoryVault()
            with TemporaryDirectory() as directory:
                vault = NativeIngressVault(Path(directory), backend=backend)
                await vault.provision(grant, SecretStr(transport_fixtures.TOKEN))

                def fail(kind: str) -> None:
                    if kind == "delete":
                        raise RuntimeError("PRIVATE-TOKEN-and-artifact")

                backend.hook = fail
                with self.assertRaises(CredentialVaultError) as failed:
                    await vault.revoke(grant)
                self.assertNotIn("PRIVATE", str(failed.exception))
                restarted = NativeIngressVault(Path(directory), backend=backend)
                self.assertIsNone(restarted.get_password(SERVICE, grant.account))
                record = restarted.inspect(grant)
                assert record is not None
                self.assertTrue(record.unresolved)
                backend.hook = lambda _: None
                await restarted.revoke(grant)
                self.assertIsNone(await restarted.lookup(grant))

    async def test_lost_activation_ack_inspection_does_not_replay_native_write(self):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            grant = self.helper.make(chat)[0].grant
            backend = MemoryVault()
            with TemporaryDirectory() as directory:
                vault = NativeIngressVault(Path(directory), backend=backend)
                original = vault._write  # pyright: ignore[reportPrivateUsage]

                def lose_ack(root: int, record: CredentialLifecycle) -> None:
                    original(root, record)
                    if record.status == "active":
                        raise OSError("private receipt lost")

                with (
                    patch.object(vault, "_write", side_effect=lose_ack),
                    self.assertRaises(CredentialVaultError),
                ):
                    await vault.provision(grant, SecretStr(transport_fixtures.TOKEN))
                calls = backend.calls.copy()
                record = vault.inspect(grant)
                assert record is not None
                self.assertEqual(record.status, "active")
                self.assertEqual(backend.calls, calls)
                with self.assertRaises(CredentialVaultError):
                    await vault.provision(grant, SecretStr(transport_fixtures.TOKEN))
                self.assertEqual(backend.calls, calls)
                await vault.revoke(grant)

    async def test_concurrent_handles_revoke_supersedes_pending_native_write(self):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            grant = self.helper.make(chat)[0].grant
            backend = MemoryVault()
            entered, release = Event(), Event()

            def hold(kind: str) -> None:
                if kind == "set":
                    entered.set()
                    release.wait(2)

            backend.hook = hold
            with TemporaryDirectory() as directory:
                first = NativeIngressVault(Path(directory), backend=backend)
                second = NativeIngressVault(Path(directory), backend=backend)
                creation = asyncio.create_task(
                    first.provision(grant, SecretStr(transport_fixtures.TOKEN))
                )
                deletion = None
                try:
                    await transport_fixtures.until(entered.is_set)
                    deletion = asyncio.create_task(second.revoke(grant))

                    def revoked() -> bool:
                        record = second.inspect(grant)
                        return record is not None and record.status == "revoking"

                    await transport_fixtures.until(revoked)
                    self.assertIsNone(second.get_password(SERVICE, grant.account))
                    release.set()
                    with self.assertRaises(CredentialVaultError):
                        await creation
                    await deletion
                    self.assertEqual(backend.values, {})
                    self.assertIsNone(await second.lookup(grant))
                    with self.assertRaises(CredentialVaultError):
                        await first.provision(
                            grant, SecretStr(transport_fixtures.TOKEN)
                        )
                finally:
                    release.set()
                    tasks = [creation] if deletion is None else [creation, deletion]
                    await asyncio.gather(*tasks, return_exceptions=True)

    async def test_rotation_validation_and_wrong_namespace_do_not_touch_vault(self):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            grant = self.helper.make(chat)[0].grant
            backend = MemoryVault()
            with TemporaryDirectory() as directory:
                vault = NativeIngressVault(Path(directory), backend=backend)
                await vault.provision(grant, SecretStr(transport_fixtures.TOKEN))
                before = vault.inspect(grant)
                calls = backend.calls.copy()
                replacement = grant.model_copy(
                    update={"credential_sha256": digest(("e" * 64).encode())}
                )
                for altered, token in (
                    (replacement, SecretStr("a" * 64)),
                    (
                        replacement.model_copy(update={"source_id": "elsewhere"}),
                        SecretStr("e" * 64),
                    ),
                ):
                    with self.assertRaises(CredentialVaultError):
                        await vault.rotate(grant, altered, token)
                with self.assertRaises(CredentialVaultError):
                    vault.get_password("mos-eisley.mcp.oauth.v1", grant.account)
                self.assertEqual(vault.inspect(grant), before)
                self.assertEqual(backend.calls, calls)
                await vault.revoke(grant)

    async def test_private_record_symlinks_links_permissions_and_corruption_fail_closed(
        self,
    ):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            grant = self.helper.make(chat)[0].grant
            backend = MemoryVault()
            with TemporaryDirectory() as directory:
                root = Path(directory)
                vault = NativeIngressVault(root, backend=backend)
                await vault.provision(grant, SecretStr(transport_fixtures.TOKEN))
                record = root / (grant.account + ".json")
                original = record.read_bytes()
                for change in (
                    "permissions",
                    "symlink",
                    "hardlink",
                    "corrupt",
                    "oversized",
                ):
                    backup = root / "backup"
                    if change == "permissions":
                        record.chmod(0o644)
                    elif change == "symlink":
                        record.rename(backup)
                        record.symlink_to(backup)
                    elif change == "hardlink":
                        backup.hardlink_to(record)
                    elif change == "corrupt":
                        record.write_text("invalid metadata")
                    else:
                        record.write_bytes(original + b" " * 2049)
                    calls = backend.calls.copy()
                    try:
                        with self.assertRaises(CredentialVaultError):
                            vault.get_password(SERVICE, grant.account)
                        with self.assertRaises(CredentialVaultError):
                            vault.inspect(grant)
                        self.assertEqual(backend.calls, calls)
                    finally:
                        if change == "symlink":
                            record.unlink()
                            backup.rename(record)
                        elif change == "hardlink":
                            backup.unlink()
                        record.chmod(0o600)
                        record.write_bytes(original)
                await vault.revoke(grant)

    async def test_absent_inspection_is_read_only_and_busy_authority_denies_lookup(
        self,
    ):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            grant = self.helper.make(chat)[0].grant
            backend = MemoryVault()
            with TemporaryDirectory() as directory:
                root = Path(directory) / "private"
                vault = NativeIngressVault(root, backend=backend)
                self.assertIsNone(vault.inspect(grant))
                self.assertFalse(root.exists())
                self.assertIsNone(vault.get_password(SERVICE, grant.account))
                self.assertFalse(root.exists())
                self.assertEqual(backend.calls, [])
                await vault.provision(grant, SecretStr(transport_fixtures.TOKEN))
                before = backend.calls.copy()
                with (root / (grant.account + ".state.lock")).open("rb") as locked:
                    fcntl.flock(locked.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaises(CredentialVaultError):
                        vault.get_password(SERVICE, grant.account)
                    self.assertEqual(backend.calls, before)
                await vault.revoke(grant)
