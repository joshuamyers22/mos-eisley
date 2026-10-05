"""Real loopback sockets, fixture vault and owner-only durable admission."""

import asyncio
import socket
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from threading import Event
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import test_conversation_schedule_ingress as fixtures
from test_conversation_context import CapturingClient
from test_conversation_tui import until

from mos_eisley.conversation_cli import terminal
from mos_eisley.conversation_input import ConversationInput
from mos_eisley.conversation_schedule_driver import ActiveSessionTimers
from mos_eisley.conversation_schedule_transport import (
    REJECTED,
    SERVICE,
    SUCCESS,
    IngressTransportGrant,
    LoopbackEventTransport,
    LoopbackIngressSettings,
)
from mos_eisley.core.models import digest

TOKEN = "0123456789abcdef" * 4


class Vault:
    def __init__(self, grant: IngressTransportGrant) -> None:
        self.values = {(SERVICE, grant.account): TOKEN}
        self.reads = 0
        self.hook: Callable[[], None] = lambda: None

    def get_password(self, service: str, username: str) -> str | None:
        self.reads += 1
        self.hook()
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        raise AssertionError("Transport must never write credentials")

    def delete_password(self, service: str, username: str) -> None:
        raise AssertionError("Transport must never delete credentials")


class TransportTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.helper = fixtures.IngressTests()
        self.helper.setUp()

    def make(self, chat: fixtures.ConversationController, **settings: object):
        source = chat.schedule_sources[("schedule", "ci")]
        assert isinstance(source, fixtures.InertExternalIngress)
        grant = IngressTransportGrant(
            binding=source.authorization.binding,
            schedule_id="schedule",
            source_id="ci",
            source_authorization_sha256=source.authorization.pin.authorization_sha256,
            credential_id="ingress-fixture",
            credential_sha256=digest(TOKEN.encode()),
            not_after=source.authorization.not_after,
        )
        vault = Vault(grant)
        config = {"allow_loopback_http": True, **settings}
        adapter = LoopbackEventTransport(
            chat, grant, LoopbackIngressSettings.model_validate(config), backend=vault
        )
        return adapter, vault

    @asynccontextmanager
    async def opened(self, chat: fixtures.ConversationController, **settings: object):
        adapter, vault = self.make(chat, **settings)
        owner = ActiveSessionTimers(chat, lambda _: None)
        owner.open()
        try:
            await adapter.open(owner)
            yield adapter, vault, owner
        finally:
            await adapter.close()
            owner.close()

    async def send(
        self,
        adapter: LoopbackEventTransport,
        packet: bytes,
        *,
        token: str = TOKEN,
        route: str = "/events",
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.open_connection("127.0.0.1", adapter.port)
        header = (
            f"POST {route} HTTP/1.1\r\nHost: 127.0.0.1:{adapter.port}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(packet)}\r\n"
            f"Authorization: Bearer {token}\r\n\r\n"
        ).encode()
        writer.write(header + packet)
        await writer.drain()

        async def close() -> None:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

        self.addAsyncCleanup(close)
        return reader, writer

    async def queued(self, adapter: LoopbackEventTransport) -> None:
        await asyncio.wait_for(adapter.ready.wait(), 1)
        await asyncio.sleep(0)

    async def response(self, reader: asyncio.StreamReader) -> bytes:
        return await asyncio.wait_for(reader.read(), 1)

    async def test_owner_admission_duplicate_and_private_data_omission(self) -> None:
        for kind in fixtures.BACKENDS:
            with self.helper.session(kind) as (chat, source, _, _, reads, store):
                async with self.opened(chat) as (adapter, vault, owner):
                    packet = self.helper.sign(self.helper.body(source))
                    before = chat.state
                    for _iteration in range(2):
                        reader, _ = await self.send(adapter, packet)
                        await self.queued(adapter)
                        self.assertEqual(chat.state, before)
                        self.assertFalse(adapter.drain(owner, busy=True))
                        self.assertTrue(adapter.drain(owner))
                        self.assertEqual(await self.response(reader), SUCCESS)
                        before = chat.state
                    saved = store.load()
                    self.assertEqual(saved.schedules[0].state.accepted_events, 1)
                    self.assertEqual(saved.entries, ())
                    self.assertEqual(saved.schedules[0].state.ledger.attempts, 0)
                    self.assertNotIn(TOKEN, saved.model_dump_json())
                    self.assertNotIn(fixtures.PAYLOAD, saved.model_dump_json())
                    self.assertGreater(vault.reads, 4)
                    self.assertTrue(reads)

    async def test_forgery_cross_owner_routing_and_generic_responses(self) -> None:
        with self.helper.session(fixtures.ConversationStore) as (chat, source, *_):
            async with self.opened(chat) as (adapter, vault, owner):
                valid = self.helper.sign(self.helper.body(source))
                wrong_binding = source.authorization.binding.model_copy(
                    update={"owner_uid": chat.state.owner_uid + 1}
                )
                cross = self.helper.sign(
                    self.helper.body(source).model_copy(
                        update={"binding": wrong_binding}
                    )
                )
                for packet, token in (
                    (valid, "e" * 64),
                    (cross, TOKEN),
                    (b"private invalid packet", TOKEN),
                ):
                    before = chat.state
                    reader, _ = await self.send(adapter, packet, token=token)
                    await self.queued(adapter)
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(await self.response(reader), REJECTED)
                    self.assertEqual(chat.state, before)
                reader, _ = await self.send(adapter, valid, route="/session/private")
                self.assertEqual(await self.response(reader), REJECTED)
                self.assertEqual(chat.state.schedules[0].state.accepted_events, 0)
                self.assertGreater(vault.reads, 1)

    async def test_foreign_owner_and_grant_rejected_before_vault_or_listener(self):
        with self.helper.session(fixtures.ConversationStore) as (chat, *_):
            adapter, vault = self.make(chat)
            adapter.grant = adapter.grant.model_copy(
                update={
                    "binding": adapter.grant.binding.model_copy(
                        update={"owner_uid": chat.state.owner_uid + 1}
                    )
                }
            )
            owner = ActiveSessionTimers(chat, lambda _: None)
            owner.open()
            try:
                with self.assertRaisesRegex(
                    ValueError, "^Ingress transport unavailable"
                ):
                    await adapter.open(owner)
                self.assertEqual(vault.reads, 0)
                self.assertIsNone(adapter.server)
            finally:
                await adapter.close()
                owner.close()

    async def test_revocation_before_and_during_validation_is_atomic(self) -> None:
        for kind in fixtures.BACKENDS:
            for timing in ("queued", "validation"):
                with self.helper.session(kind) as (chat, source, *_):
                    async with self.opened(chat) as (adapter, vault, owner):
                        packet = self.helper.sign(self.helper.body(source))
                        reader, _ = await self.send(adapter, packet)
                        await self.queued(adapter)
                        before = chat.state
                        if timing == "queued":
                            vault.values.clear()
                        else:
                            revision = source.authorization.binding.revision_sha256

                            def revoke(workspace: str, revision: str = revision) -> str:
                                vault.values.clear()
                                return revision

                            replacement = fixtures.InertExternalIngress(
                                source.authorization,
                                self.helper.public,
                                chat.state.workspace,
                                observe_workspace=revoke,
                            )
                            chat.register_schedule_source(
                                "schedule",
                                replacement,
                                expected_revision=chat.state.revision,
                            )
                        self.assertFalse(adapter.drain(owner))
                        self.assertEqual(await self.response(reader), REJECTED)
                        self.assertEqual(chat.state, before)

    async def test_disconnect_before_admission_and_lost_sender_ack(self) -> None:
        for kind in fixtures.BACKENDS:
            with self.helper.session(kind) as (chat, source, *_):
                async with self.opened(chat) as (adapter, _, owner):
                    packet = self.helper.sign(self.helper.body(source))
                    _, writer = await self.send(adapter, packet)
                    await self.queued(adapter)
                    delivery = adapter.queue.get_nowait()
                    adapter.queue.put_nowait(delivery)
                    writer.close()
                    await writer.wait_closed()
                    await until(delivery.ack.cancelled)
                    before = chat.state
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(chat.state, before)
                    _, writer = await self.send(adapter, packet)
                    await self.queued(adapter)
                    self.assertTrue(adapter.drain(owner))
                    # Drop the sender before the response is delivered.
                    writer.close()
                    await writer.wait_closed()
                    retained = chat.state
                    reader, _ = await self.send(adapter, packet)
                    await self.queued(adapter)
                    self.assertTrue(adapter.drain(owner))
                    self.assertEqual(await self.response(reader), SUCCESS)
                    self.assertEqual(chat.state, retained)

    async def test_request_deadline_busy_boundary_and_connection_limits(self) -> None:
        with self.helper.session(fixtures.ConversationStore) as (chat, source, *_):
            async with self.opened(
                chat, request_timeout_seconds=0.05, max_connections=1, queue_limit=1
            ) as (adapter, _, owner):
                before = chat.state
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", adapter.port
                )
                writer.write(b"POST /events HTTP/1.1\r\n")
                await writer.drain()
                await until(lambda: len(adapter.tasks) == 1)
                extra_reader, extra_writer = await asyncio.open_connection(
                    "127.0.0.1", adapter.port
                )
                self.assertEqual(await self.response(extra_reader), b"")
                extra_writer.close()
                await extra_writer.wait_closed()
                self.assertEqual(await self.response(reader), REJECTED)
                writer.close()
                await writer.wait_closed()
                await until(lambda: not adapter.tasks)
                reader, _ = await self.send(
                    adapter, self.helper.sign(self.helper.body(source))
                )
                await self.queued(adapter)
                self.assertFalse(adapter.drain(owner, busy=True))
                self.assertEqual(await self.response(reader), REJECTED)
                self.assertFalse(adapter.drain(owner))
                self.assertEqual(chat.state, before)

    async def test_hung_vault_deadline_quarantines_and_late_result_cannot_commit(self):
        with self.helper.session(fixtures.ConversationStore) as (chat, source, *_):
            async with self.opened(chat, request_timeout_seconds=0.05) as (
                adapter,
                vault,
                owner,
            ):
                release = Event()

                def wait() -> None:
                    release.wait(1)

                vault.hook = wait
                reader, _ = await self.send(
                    adapter, self.helper.sign(self.helper.body(source))
                )
                await self.queued(adapter)
                before = chat.state
                started = time.monotonic()
                try:
                    self.assertFalse(adapter.drain(owner))
                    self.assertLess(time.monotonic() - started, 0.15)
                    self.assertTrue(chat.schedule_reads.blocked)
                    self.assertEqual(await self.response(reader), REJECTED)
                finally:
                    release.set()
                await asyncio.sleep(0.02)
                self.assertEqual(chat.state, before)

    async def test_cancelled_schedule_and_lost_store_ack_preserve_exposure(self):
        for kind in fixtures.BACKENDS:
            for lost_ack in (False, True):
                with self.helper.session(kind) as (chat, source, _, _, _, store):
                    async with self.opened(chat) as (adapter, _, owner):
                        packet = self.helper.sign(self.helper.body(source))
                        reader, _ = await self.send(adapter, packet)
                        await self.queued(adapter)
                        if lost_ack:

                            def save_then_fail(
                                state: fixtures.ConversationState,
                            ) -> None:
                                store.save(state)
                                raise OSError("private-artifact-path-and-secret")

                            chat.save = save_then_fail
                            with self.assertRaises(OSError):
                                adapter.drain(owner)
                            self.assertTrue(chat.persistence_broken)
                            self.assertEqual(
                                store.load().schedules[0].state.accepted_events, 1
                            )
                        else:
                            chat.cancel_schedule(
                                "schedule", expected_revision=chat.state.revision
                            )
                            before = chat.state
                            self.assertFalse(adapter.drain(owner))
                            self.assertEqual(chat.state, before)
                        self.assertEqual(await self.response(reader), REJECTED)

    async def test_shared_terminal_owner_dispatch_and_eof_closes_transport(
        self,
    ) -> None:
        for kind in fixtures.BACKENDS:
            with self.helper.session(kind) as (chat, source, *_):
                adapter, _ = self.make(chat)
                client = CapturingClient()
                original = chat.step

                async def step(*, on_started: Callable[[], None] | None = None) -> bool:
                    return await original(client, on_started=on_started)  # noqa: B023

                queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
                with patch.object(chat, "step", step):
                    task = asyncio.create_task(
                        terminal(chat, queue, lambda _: None, ingress_transport=adapter)
                    )
                    try:
                        await until(lambda: adapter.server is not None)  # noqa: B023
                        reader, _ = await self.send(
                            adapter, self.helper.sign(self.helper.body(source))
                        )
                        self.assertEqual(await self.response(reader), SUCCESS)
                        await until(
                            lambda: (
                                len(chat.state.entries) == 1
                                and chat.state.entries[0].status == "completed"
                            )
                        )
                        self.assertNotIn(fixtures.PAYLOAD, str(client.requests))
                        await queue.put(None)
                        await asyncio.wait_for(task, 1)
                        self.assertTrue(adapter.closed)
                        self.assertIsNone(adapter.server)
                    finally:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

    async def test_queue_overflow_and_close_cancel_uncommitted_frames(self) -> None:
        with self.helper.session(fixtures.ConversationStore) as (chat, source, *_):
            async with self.opened(chat, queue_limit=1) as (adapter, _, _owner):
                packet = self.helper.sign(self.helper.body(source))
                before = chat.state
                reader, _ = await self.send(adapter, packet)
                await self.queued(adapter)
                extra_reader, _ = await self.send(adapter, packet)
                self.assertEqual(await self.response(extra_reader), REJECTED)
                self.assertEqual(adapter.queue.qsize(), 1)
                self.assertLessEqual(len(adapter.tasks), 4)
                await adapter.close()
                self.assertEqual(await self.response(reader), REJECTED)
                self.assertEqual(chat.state, before)
                self.assertTrue(adapter.queue.empty())
                self.assertEqual(adapter.tasks, set())

    async def test_read_cancellation_and_stale_revision_never_commit(self) -> None:
        for change in ("cancel_read", "revision", "expiry", "rotate"):
            with self.helper.session(fixtures.ConversationStore) as (
                chat,
                source,
                clock,
                broker,
                _,
                _store,
            ):
                async with self.opened(chat) as (adapter, vault, owner):
                    reader, _ = await self.send(
                        adapter, self.helper.sign(self.helper.body(source))
                    )
                    await self.queued(adapter)
                    before = chat.state
                    if change == "cancel_read":
                        vault.hook = chat.schedule_reads.cancel
                    elif change == "revision":
                        broker[0] = "a" * 64
                    elif change == "expiry":
                        clock[0] = source.authorization.not_after
                    else:
                        vault.values[(SERVICE, adapter.grant.account)] = "e" * 64
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(await self.response(reader), REJECTED)
                    self.assertEqual(chat.state, before)

    async def test_restart_preserves_duplicate_rate_and_exposure(self) -> None:
        for kind in fixtures.BACKENDS:
            with self.helper.session(kind, maximum=1) as (
                chat,
                source,
                clock,
                broker,
                _,
                store,
            ):
                packet = self.helper.sign(self.helper.body(source))
                async with self.opened(chat) as (adapter, _, owner):
                    reader, _ = await self.send(adapter, packet)
                    await self.queued(adapter)
                    self.assertTrue(adapter.drain(owner))
                    self.assertEqual(await self.response(reader), SUCCESS)
                    self.assertEqual(len(owner.tick()), 1)
                saved = store.load()
                charged = saved.schedules[0].state.ledger
                resumed = fixtures.ConversationController(
                    saved,
                    chat.cassette,
                    store.save,
                    goal_clock=lambda: clock[0],
                    schedule_observer=lambda s: s.binding,
                )
                resumed.goal_control("resume")
                replacement = fixtures.InertExternalIngress(
                    source.authorization,
                    self.helper.public,
                    resumed.state.workspace,
                    observe_workspace=lambda _: broker[0],
                )
                resumed.register_schedule_source(
                    "schedule", replacement, expected_revision=resumed.state.revision
                )
                resumed.resume_schedule(
                    "schedule", expected_revision=resumed.state.revision
                )
                async with self.opened(resumed) as (adapter, _, owner):
                    before = resumed.state
                    for current, reply in (
                        (packet, SUCCESS),
                        (self.helper.sign(self.helper.body(source, 2)), REJECTED),
                    ):
                        reader, _ = await self.send(adapter, current)
                        await self.queued(adapter)
                        adapter.drain(owner)
                        self.assertEqual(await self.response(reader), reply)
                        self.assertEqual(resumed.state, before)
                    self.assertEqual(resumed.state.schedules[0].state.ledger, charged)
                    self.assertFalse(await resumed.step(CapturingClient()))

    async def test_native_backend_selection_is_explicit_and_owner_scoped(self) -> None:
        with self.helper.session(fixtures.ConversationStore) as (chat, *_):
            adapter, vault = self.make(chat)
            adapter.backend = None
            owner = ActiveSessionTimers(chat, lambda _: None)
            owner.open()
            try:
                with patch(
                    "mos_eisley.conversation_schedule_transport.credential_backend",
                    return_value=vault,
                ) as select:
                    select.assert_not_called()
                    await adapter.open(owner)
                    select.assert_called_once_with()
                self.assertEqual(vault.reads, 1)
                self.assertEqual(set(vault.values), {(SERVICE, adapter.grant.account)})
            finally:
                await adapter.close()
                owner.close()

    async def test_disconnect_during_vault_read_is_detected_before_commit(self) -> None:
        with self.helper.session(fixtures.ConversationStore) as (chat, source, *_):
            async with self.opened(chat) as (adapter, vault, owner):
                reader, writer = await self.send(
                    adapter, self.helper.sign(self.helper.body(source))
                )
                await self.queued(adapter)
                peer = cast(socket.socket, writer.get_extra_info("socket"))
                vault.hook = lambda: peer.shutdown(socket.SHUT_RDWR)
                before = chat.state
                self.assertFalse(adapter.drain(owner))
                self.assertEqual(chat.state, before)
                self.assertEqual(await self.response(reader), b"")

    async def test_socket_attempt_flood_closes_without_owner_work(self) -> None:
        with self.helper.session(fixtures.ConversationStore) as (chat, source, *_):
            async with self.opened(chat) as (adapter, vault, _owner):
                self.enterContext(
                    patch.object(adapter, "_attempts", (time.monotonic(),) * 16)
                )
                before, reads = chat.state, vault.reads
                reader, _ = await self.send(
                    adapter, self.helper.sign(self.helper.body(source))
                )
                try:
                    response = await self.response(reader)
                except ConnectionResetError:
                    response = b""
                self.assertEqual(response, b"")
                self.assertTrue(adapter.queue.empty())
                self.assertEqual(vault.reads, reads)
                self.assertEqual(chat.state, before)

    async def test_hung_backend_selection_cannot_open_a_late_listener(self) -> None:
        with self.helper.session(fixtures.ConversationStore) as (chat, *_):
            adapter, vault = self.make(chat, request_timeout_seconds=0.05)
            adapter.backend = None
            release = Event()
            owner = ActiveSessionTimers(chat, lambda _: None)
            owner.open()
            before = chat.state

            def select() -> Vault:
                release.wait(1)
                return vault

            try:
                with patch(
                    "mos_eisley.conversation_schedule_transport.credential_backend",
                    side_effect=select,
                ):
                    started = time.monotonic()
                    with self.assertRaisesRegex(
                        ValueError, "Ingress transport unavailable"
                    ):
                        await adapter.open(owner)
                    self.assertLess(time.monotonic() - started, 0.15)
                release.set()
                await asyncio.sleep(0.02)
                self.assertIsNone(adapter.server)
                self.assertIsNone(adapter.backend)
                self.assertTrue(adapter.closed)
                self.assertEqual(chat.state, before)
                self.assertEqual(vault.reads, 0)
            finally:
                release.set()
                await adapter.close()
                owner.close()
