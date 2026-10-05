"""Opt-in real macOS Keychain qualification; only disposable exact accounts."""

import asyncio
import os
import secrets
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import patch
from uuid import uuid4

import test_conversation_schedule_transport as transport_fixtures
from pydantic import SecretStr

from mos_eisley.conversation_schedule_credentials import (
    CredentialVaultError,
    NativeIngressVault,
)
from mos_eisley.conversation_schedule_transport import (
    REJECTED,
    SUCCESS,
    IngressTransportGrant,
)
from mos_eisley.core.models import digest
from mos_eisley.tools.mcp_oauth_store import CredentialBackend, credential_backend

ENABLED = (
    sys.platform == "darwin"
    and os.environ.get("MOS_EISLEY_NATIVE_KEYCHAIN_QUALIFICATION") == "1"
)


class NativeFaultPort:
    """Real native calls with controlled failure/acknowledgement boundaries."""

    def __init__(self, backend: CredentialBackend) -> None:
        self.backend = backend
        self.hook: Callable[[str], None] = lambda _: None

    def get_password(self, service: str, username: str) -> str | None:
        value = self.backend.get_password(service, username)
        self.hook("get")
        return value

    def set_password(self, service: str, username: str, password: str) -> None:
        self.backend.set_password(service, username, password)
        self.hook("set")

    def delete_password(self, service: str, username: str) -> None:
        self.backend.delete_password(service, username)
        self.hook("delete")


@skipUnless(ENABLED, "Explicit macOS native-vault qualification required")
class NativeKeychainTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.helper = transport_fixtures.TransportTests()
        self.helper.setUp()

    async def send(
        self,
        adapter: transport_fixtures.LoopbackEventTransport,
        packet: bytes,
        *,
        token: str,
    ):
        reader, writer = await self.helper.send(adapter, packet, token=token)

        async def close() -> None:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

        self.addAsyncCleanup(close)
        return reader, writer

    async def test_native_provision_rotation_revocation_and_transport(self) -> None:
        for kind in transport_fixtures.fixtures.BACKENDS:
            with self.helper.helper.session(kind) as (chat, source, *_):
                adapter, _ = self.helper.make(chat)
                token = SecretStr(secrets.token_hex(32))
                grant = adapter.grant.model_copy(
                    update={
                        "credential_id": "native-qualification-" + uuid4().hex,
                        "credential_sha256": digest(token.get_secret_value().encode()),
                    }
                )
                adapter.grant = grant
                with TemporaryDirectory(prefix="mos-native-vault-") as directory:
                    vault = NativeIngressVault(Path(directory), timeout=5)
                    adapter.backend = vault
                    owner = transport_fixtures.ActiveSessionTimers(chat, lambda _: None)
                    owner.open()
                    cleanup: list[IngressTransportGrant] = [grant]
                    try:
                        before = chat.state
                        foreign = grant.model_copy(
                            update={
                                "binding": grant.binding.model_copy(
                                    update={"owner_uid": grant.binding.owner_uid + 1}
                                )
                            }
                        )
                        with self.assertRaises(CredentialVaultError):
                            await vault.provision(foreign, token)
                        await vault.provision(grant, token)
                        self.assertEqual(await vault.lookup(grant), token)
                        await adapter.open(owner)
                        packet = self.helper.helper.sign(
                            self.helper.helper.body(source)
                        )
                        reader, writer = await self.send(
                            adapter, packet, token=token.get_secret_value()
                        )
                        await self.helper.queued(adapter)
                        self.assertEqual(chat.state, before)
                        self.assertTrue(adapter.drain(owner))
                        self.assertEqual(await self.helper.response(reader), SUCCESS)
                        writer.close()
                        await writer.wait_closed()
                        retained = chat.state
                        # Native rotation revokes the old exact grant first.
                        replacement_token = SecretStr(secrets.token_hex(32))
                        replacement = grant.model_copy(
                            update={
                                "credential_sha256": digest(
                                    replacement_token.get_secret_value().encode()
                                )
                            }
                        )
                        cleanup.append(replacement)
                        await vault.rotate(grant, replacement, replacement_token)
                        self.assertIsNone(await vault.lookup(grant))
                        self.assertEqual(
                            await vault.lookup(replacement), replacement_token
                        )
                        reader, writer = await self.send(
                            adapter, packet, token=token.get_secret_value()
                        )
                        await self.helper.queued(adapter)
                        self.assertFalse(adapter.drain(owner))
                        self.assertEqual(await self.helper.response(reader), REJECTED)
                        writer.close()
                        await writer.wait_closed()
                        self.assertEqual(chat.state, retained)
                        await adapter.close()
                        renewed, _ = self.helper.make(chat)
                        renewed.grant, renewed.backend = replacement, vault
                        await renewed.open(owner)
                        try:
                            reader, writer = await self.send(
                                renewed,
                                packet,
                                token=replacement_token.get_secret_value(),
                            )
                            await self.helper.queued(renewed)
                            self.assertTrue(renewed.drain(owner))
                            self.assertEqual(
                                await self.helper.response(reader), SUCCESS
                            )
                            writer.close()
                            await writer.wait_closed()
                            self.assertEqual(chat.state, retained)
                            reader, writer = await self.send(
                                renewed,
                                self.helper.helper.sign(
                                    self.helper.helper.body(source, 2)
                                ),
                                token=replacement_token.get_secret_value(),
                            )
                            await self.helper.queued(renewed)
                            await vault.revoke(replacement)
                            self.assertFalse(renewed.drain(owner))
                            self.assertEqual(
                                await self.helper.response(reader), REJECTED
                            )
                            writer.close()
                            await writer.wait_closed()
                            self.assertEqual(chat.state, retained)
                            restarted = NativeIngressVault(Path(directory), timeout=5)
                            self.assertIsNone(await restarted.lookup(replacement))
                            self.assertFalse(
                                token.get_secret_value()
                                in chat.state.model_dump_json(),
                                "Credential material reached durable state.",
                            )
                            self.assertFalse(
                                replacement_token.get_secret_value()
                                in chat.state.model_dump_json(),
                                "Credential material reached durable state.",
                            )
                        finally:
                            await renewed.close()
                    finally:
                        await adapter.close()
                        owner.close()
                        for selected in cleanup:
                            await vault.revoke(selected)
                            self.assertIsNone(await vault.lookup(selected))

    async def test_native_revocation_after_lost_ack_preserves_metadata_and_exposure(
        self,
    ):
        for kind in transport_fixtures.fixtures.BACKENDS:
            for phase in ("metadata", "queue", "running"):
                with self.helper.helper.session(kind) as (chat, source, _, _, _, store):
                    adapter, _ = self.helper.make(chat)
                    token = SecretStr(secrets.token_hex(32))
                    grant = adapter.grant.model_copy(
                        update={
                            "credential_id": "native-lost-ack-" + uuid4().hex,
                            "credential_sha256": digest(
                                token.get_secret_value().encode()
                            ),
                        }
                    )
                    adapter.grant = grant
                    with TemporaryDirectory(prefix="mos-native-vault-") as directory:
                        vault = NativeIngressVault(Path(directory), timeout=5)
                        adapter.backend = vault
                        owner = transport_fixtures.ActiveSessionTimers(
                            chat, lambda _: None
                        )
                        owner.open()
                        try:
                            await vault.provision(grant, token)
                            await adapter.open(owner)
                            packet = self.helper.helper.sign(
                                self.helper.helper.body(source)
                            )

                            def lose_ack(
                                state: transport_fixtures.fixtures.ConversationState,
                            ) -> None:
                                store.save(state)
                                raise OSError("private native acknowledgement lost")

                            if phase == "metadata":
                                chat.save = lose_ack
                            reader, writer = await self.send(
                                adapter, packet, token=token.get_secret_value()
                            )
                            await self.helper.queued(adapter)
                            if phase == "metadata":
                                with self.assertRaises(OSError):
                                    adapter.drain(owner)
                                expected = REJECTED
                            else:
                                self.assertTrue(adapter.drain(owner))
                                expected = SUCCESS
                            self.assertEqual(
                                await self.helper.response(reader), expected
                            )
                            writer.close()
                            await writer.wait_closed()
                            if phase == "queue":
                                chat.save = lose_ack
                                with self.assertRaises(OSError):
                                    owner.tick()
                            elif phase == "running":
                                self.assertEqual(len(owner.tick()), 1)
                                chat.save = lose_ack
                                client = transport_fixtures.CapturingClient()
                                with self.assertRaises(OSError):
                                    await chat.step(client)
                                self.assertEqual(client.requests, [])
                            committed = store.load()
                            retained = committed.schedules[0].state
                            self.assertEqual(retained.accepted_events, 1)
                            self.assertEqual(
                                retained.ledger.attempts,
                                0 if phase == "metadata" else 1,
                            )
                            await vault.revoke(grant)
                            self.assertIsNone(await vault.lookup(grant))
                            self.assertEqual(store.load(), committed)
                            resumed = (
                                transport_fixtures.fixtures.ConversationController(
                                    committed,
                                    chat.cassette,
                                    store.save,
                                    goal_clock=lambda: 100.0,
                                    schedule_observer=lambda s: s.binding,
                                )
                            )
                            recovered = resumed.state.schedules[0].state
                            self.assertEqual(recovered.accepted_events, 1)
                            self.assertEqual(
                                recovered.ingress_rates, retained.ingress_rates
                            )
                            self.assertEqual(
                                recovered.ledger.attempts, retained.ledger.attempts
                            )
                            self.assertEqual(
                                recovered.ledger.input_bytes,
                                retained.ledger.input_bytes,
                            )
                            self.assertFalse(
                                await resumed.step(transport_fixtures.CapturingClient())
                            )
                            self.assertIsNone(
                                await NativeIngressVault(
                                    Path(directory), timeout=5
                                ).lookup(grant)
                            )
                        finally:
                            await adapter.close()
                            owner.close()
                            await vault.revoke(grant)
                            self.assertIsNone(await vault.lookup(grant))

    async def test_native_late_writes_after_timeout_or_cancel_cannot_restore_access(
        self,
    ):
        for cancel in (False, True):
            with self.helper.helper.session(
                transport_fixtures.fixtures.ConversationStore
            ) as (chat, *_):
                grant = self.helper.make(chat)[0].grant
                token = SecretStr(secrets.token_hex(32))
                grant = grant.model_copy(
                    update={
                        "credential_id": "native-late-" + uuid4().hex,
                        "credential_sha256": digest(token.get_secret_value().encode()),
                    }
                )
                port = NativeFaultPort(credential_backend())
                entered, release = Event(), Event()

                def block(
                    kind: str, entered: Event = entered, release: Event = release
                ) -> None:
                    if kind == "set":
                        entered.set()
                        release.wait(2)

                port.hook = block
                with TemporaryDirectory(prefix="mos-native-vault-") as directory:
                    vault = NativeIngressVault(
                        Path(directory), backend=port, timeout=0.1
                    )
                    cleanup = NativeIngressVault(Path(directory), timeout=5)
                    task = asyncio.create_task(vault.provision(grant, token))
                    try:
                        await transport_fixtures.until(entered.is_set)
                        if cancel:
                            task.cancel()
                            with self.assertRaises(asyncio.CancelledError):
                                await task
                        else:
                            with self.assertRaises(CredentialVaultError):
                                await task
                        with self.assertRaises(CredentialVaultError):
                            await vault.revoke(grant)
                        self.assertIsNone(
                            vault.get_password(
                                transport_fixtures.SERVICE, grant.account
                            )
                        )
                        self.assertIsNone(
                            cleanup.get_password(
                                transport_fixtures.SERVICE, grant.account
                            )
                        )
                        release.set()
                        await cleanup.revoke(grant)
                        self.assertIsNone(await cleanup.lookup(grant))
                        with self.assertRaises(CredentialVaultError):
                            await cleanup.provision(grant, token)
                    finally:
                        release.set()
                        await asyncio.gather(task, return_exceptions=True)
                        await cleanup.revoke(grant)
                        self.assertIsNone(await cleanup.lookup(grant))

    async def test_native_lookup_failure_and_cancelled_revocation_are_generic(self):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, source, *_):
            adapter, _ = self.helper.make(chat)
            token = SecretStr(secrets.token_hex(32))
            grant = adapter.grant.model_copy(
                update={
                    "credential_id": "native-failure-" + uuid4().hex,
                    "credential_sha256": digest(token.get_secret_value().encode()),
                }
            )
            adapter.grant = grant
            port = NativeFaultPort(credential_backend())
            with TemporaryDirectory(prefix="mos-native-vault-") as directory:
                vault = NativeIngressVault(Path(directory), backend=port, timeout=5)
                cleanup = NativeIngressVault(Path(directory), timeout=5)
                adapter.backend = vault
                owner = transport_fixtures.ActiveSessionTimers(chat, lambda _: None)
                owner.open()
                release, entered = Event(), Event()
                try:
                    await vault.provision(grant, token)
                    await adapter.open(owner)
                    before = chat.state

                    def fail(kind: str) -> None:
                        if kind == "get":
                            raise RuntimeError("PRIVATE-ARTIFACT-and-credential")

                    port.hook = fail
                    packet = self.helper.helper.sign(self.helper.helper.body(source))
                    reader, writer = await self.send(
                        adapter, packet, token=token.get_secret_value()
                    )
                    await self.helper.queued(adapter)
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(await self.helper.response(reader), REJECTED)
                    writer.close()
                    await writer.wait_closed()
                    with self.assertRaises(CredentialVaultError) as failure:
                        await vault.lookup(grant)
                    self.assertNotIn("PRIVATE", str(failure.exception))
                    self.assertEqual(chat.state, before)

                    def block(kind: str) -> None:
                        if kind == "delete":
                            entered.set()
                            release.wait(2)

                    port.hook = block
                    task = asyncio.create_task(vault.revoke(grant))
                    await transport_fixtures.until(entered.is_set)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    reader, writer = await self.send(
                        adapter, packet, token=token.get_secret_value()
                    )
                    await self.helper.queued(adapter)
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(await self.helper.response(reader), REJECTED)
                    writer.close()
                    await writer.wait_closed()
                    self.assertEqual(chat.state, before)
                    release.set()
                    await cleanup.revoke(grant)
                    self.assertIsNone(await cleanup.lookup(grant))
                    with (
                        patch(
                            "mos_eisley.conversation_schedule_credentials.os.geteuid",
                            return_value=grant.binding.owner_uid + 1,
                        ),
                        self.assertRaises(CredentialVaultError),
                    ):
                        await cleanup.lookup(grant)
                finally:
                    release.set()
                    await adapter.close()
                    owner.close()
                    await cleanup.revoke(grant)
                    self.assertIsNone(await cleanup.lookup(grant))

    async def test_native_lookup_timeout_and_revocation_discard_late_secret(self):
        with self.helper.helper.session(
            transport_fixtures.fixtures.ConversationStore
        ) as (chat, *_):
            grant = self.helper.make(chat)[0].grant
            token = SecretStr(secrets.token_hex(32))
            grant = grant.model_copy(
                update={
                    "credential_id": "native-read-" + uuid4().hex,
                    "credential_sha256": digest(token.get_secret_value().encode()),
                }
            )
            port = NativeFaultPort(credential_backend())
            entered, release = Event(), Event()
            with TemporaryDirectory(prefix="mos-native-vault-") as directory:
                vault = NativeIngressVault(Path(directory), backend=port, timeout=0.1)
                cleanup = NativeIngressVault(Path(directory), timeout=5)
                await cleanup.provision(grant, token)

                def hold(kind: str) -> None:
                    if kind == "get":
                        entered.set()
                        release.wait(2)

                port.hook = hold
                task = asyncio.create_task(vault.lookup(grant))
                try:
                    await transport_fixtures.until(entered.is_set)
                    with self.assertRaises(CredentialVaultError):
                        await task
                    with self.assertRaises(CredentialVaultError):
                        await vault.revoke(grant)
                    self.assertIsNone(
                        cleanup.get_password(transport_fixtures.SERVICE, grant.account)
                    )
                    release.set()
                    await cleanup.revoke(grant)
                    self.assertIsNone(await cleanup.lookup(grant))
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
                    await cleanup.revoke(grant)
                    self.assertIsNone(await cleanup.lookup(grant))
