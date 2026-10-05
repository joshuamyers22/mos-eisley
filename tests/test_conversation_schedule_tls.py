"""Local PKI/mTLS fixtures; no remote listener, CA, vault or deployment required."""

import asyncio
import socket
import ssl
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import test_conversation_schedule_transport as fixtures
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pydantic import SecretStr, ValidationError
from test_conversation_schedule_credentials import MemoryVault

from mos_eisley.conversation_cli import terminal
from mos_eisley.conversation_input import ConversationInput
from mos_eisley.conversation_schedule_credentials import NativeIngressVault
from mos_eisley.conversation_schedule_handlers import ScheduleReads
from mos_eisley.conversation_schedule_tls import TLSEventTransport, TLSIngressSettings
from mos_eisley.conversation_schedule_transport import (
    REJECTED,
    SUCCESS,
    ConnectedSocket,
)
from mos_eisley.core.models import digest


class PKI:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.ca_key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(UTC)
        subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "ingress fixture CA")]
        )
        self.ca = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(self.ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=3))
            .not_valid_after(now + timedelta(days=3))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    True, False, False, False, False, True, True, False, False
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(self.ca_key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    self.ca_key.public_key()
                ),
                critical=False,
            )
            .sign(self.ca_key, hashes.SHA256())
        )
        self.write("ca.pem", self.ca.public_bytes(serialization.Encoding.PEM))
        self.server = self.leaf("server", server=True)
        self.client = self.leaf("client")
        self.other = self.leaf("other")
        self.expired = self.leaf("expired", expired=True)

    def write(self, name: str, value: bytes) -> Path:
        path = self.root / name
        path.write_bytes(value)
        path.chmod(0o600)
        return path

    def leaf(
        self, name: str, *, server: bool = False, expired: bool = False
    ) -> x509.Certificate:
        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name(
                    [
                        x509.NameAttribute(
                            NameOID.COMMON_NAME, "ingress.test" if server else name
                        )
                    ]
                )
            )
            .issuer_name(self.ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now + timedelta(days=-1 if expired else 1))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    True, False, False, False, False, False, False, False, False
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage(
                    [
                        ExtendedKeyUsageOID.SERVER_AUTH
                        if server
                        else ExtendedKeyUsageOID.CLIENT_AUTH
                    ]
                ),
                critical=False,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    self.ca_key.public_key()
                ),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("ingress.test" if server else name)]
                ),
                critical=False,
            )
            .sign(self.ca_key, hashes.SHA256())
        )
        self.write(name + ".pem", cert.public_bytes(serialization.Encoding.PEM))
        self.write(
            name + "-key.pem",
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )
        return cert

    def client_context(
        self, *, identity: str | None = "client", trust: Path | None = None
    ) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.load_verify_locations(cafile=str(trust or self.root / "ca.pem"))
        context.set_alpn_protocols(["http/1.1"])
        if identity is not None:
            context.load_cert_chain(
                str(self.root / (identity + ".pem")),
                str(self.root / (identity + "-key.pem")),
            )
        return context

    def settings(self, **changes: object) -> TLSIngressSettings:
        values = {
            "server_name": "ingress.test",
            "ca_file": str(self.root / "ca.pem"),
            "certificate_file": str(self.root / "server.pem"),
            "private_key_file": str(self.root / "server-key.pem"),
            "ca_certificate_sha256": digest(
                self.ca.public_bytes(serialization.Encoding.DER)
            ),
            "server_certificate_sha256": digest(
                self.server.public_bytes(serialization.Encoding.DER)
            ),
            "client_certificate_sha256": digest(
                self.client.public_bytes(serialization.Encoding.DER)
            ),
            **changes,
        }
        return TLSIngressSettings.model_validate(values)


class TLSTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.helper = fixtures.TransportTests()
        self.helper.setUp()

    @asynccontextmanager
    async def opened(
        self,
        chat: fixtures.fixtures.ConversationController,
        *,
        attached: bool = True,
        **changes: object,
    ):
        # Source fixtures use 100 ms to test hung callbacks. TLS setup validates
        # real certificates, so use the production read budget for this fixture.
        chat.schedule_reads = ScheduleReads()
        with TemporaryDirectory(prefix="mos-tls-fixture-") as directory:
            pki = PKI(Path(directory))
            config = pki.settings(**changes)
            grant = self.helper.make(chat)[0].grant.model_copy(
                update={"transport_authorization_sha256": config.authorization_sha256}
            )
            raw = MemoryVault()
            vault = NativeIngressVault(Path(directory) / "authority", backend=raw)
            await vault.provision(grant, SecretStr(fixtures.TOKEN))
            revoked: set[str] = set()

            def validate(settings: TLSIngressSettings) -> None:
                if revoked.intersection(
                    (
                        settings.ca_certificate_sha256,
                        settings.server_certificate_sha256,
                        settings.client_certificate_sha256,
                    )
                ):
                    raise ValueError("PRIVATE certificate artifact revoked")

            adapter = TLSEventTransport(
                chat, grant, config, validate_certificates=validate, backend=vault
            )
            owner = fixtures.ActiveSessionTimers(chat, lambda _: None)
            if attached:
                owner.open()
            try:
                if attached:
                    await adapter.open(owner)
                yield adapter, pki, vault, owner, revoked
            finally:
                await adapter.close()
                if attached:
                    owner.close()
                await vault.revoke(grant)

    async def send(
        self,
        adapter: TLSEventTransport,
        pki: PKI,
        packet: bytes,
        *,
        context: ssl.SSLContext | None = None,
        token: str = fixtures.TOKEN,
        host: str | None = None,
    ):
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            adapter.port,
            ssl=context or pki.client_context(),
            server_hostname="ingress.test",
            ssl_handshake_timeout=1,
            ssl_shutdown_timeout=0.1,
        )
        writer.write(
            (
                f"POST /events HTTP/1.1\r\nHost: {host or adapter.http_host}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(packet)}\r\n"
                f"Authorization: Bearer {token}\r\n\r\n"
            ).encode()
            + packet
        )
        await writer.drain()

        async def close() -> None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

        self.addAsyncCleanup(close)
        return reader, writer

    async def test_tls_owner_commit_metadata_duplicate_and_durable_revocation(self):
        for kind in fixtures.fixtures.BACKENDS:
            with self.helper.helper.session(kind) as (chat, source, *_):
                async with self.opened(chat) as (adapter, pki, vault, owner, _):
                    packet = self.helper.helper.sign(self.helper.helper.body(source))
                    before = chat.state
                    for _iteration in range(2):
                        reader, _ = await self.send(adapter, pki, packet)
                        await self.helper.queued(adapter)
                        self.assertEqual(chat.state, before)
                        self.assertTrue(adapter.drain(owner))
                        self.assertEqual(await self.helper.response(reader), SUCCESS)
                        before = chat.state
                    self.assertEqual(chat.state.schedules[0].state.accepted_events, 1)
                    self.assertEqual(chat.state.entries, ())
                    reader, _ = await self.send(
                        adapter,
                        pki,
                        self.helper.helper.sign(self.helper.helper.body(source, 2)),
                    )
                    await self.helper.queued(adapter)
                    await vault.revoke(adapter.grant)
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(await self.helper.response(reader), REJECTED)
                    self.assertEqual(chat.state, before)

    async def test_startup_accepts_certificate_validation_over_short_fixture_budget(
        self,
    ):
        original = TLSEventTransport._context  # pyright: ignore[reportPrivateUsage]

        def delayed_context(adapter: TLSEventTransport):
            time.sleep(0.15)
            return original(adapter)

        with (
            self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
                chat,
                *_,
            ),
            patch.object(TLSEventTransport, "_context", delayed_context),
        ):
            async with self.opened(chat) as (adapter, pki, _, owner, _):
                self.assertGreater(adapter.port, 0)
                self.assertIs(adapter.owner, owner)
                self.assertEqual(adapter.tls, pki.settings())

    async def test_untrusted_expired_missing_and_wrong_pinned_client_certificates(self):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            source,
            *_,
        ):
            async with self.opened(chat) as (adapter, pki, _, _owner, _):
                before = chat.state
                for identity in (None, "expired", "other"):
                    try:
                        reader, _ = await self.send(
                            adapter,
                            pki,
                            self.helper.helper.sign(self.helper.helper.body(source)),
                            context=pki.client_context(identity=identity),
                        )
                        self.assertEqual(await self.helper.response(reader), b"")
                    except (ssl.SSLError, ConnectionError):
                        pass
                    await fixtures.until(lambda: not adapter.tasks)
                    self.assertTrue(adapter.queue.empty())
                    self.assertEqual(chat.state, before)
                with TemporaryDirectory() as directory:
                    unrelated = PKI(Path(directory))
                    try:
                        reader, _ = await self.send(
                            adapter,
                            pki,
                            self.helper.helper.sign(self.helper.helper.body(source)),
                            context=unrelated.client_context(trust=pki.root / "ca.pem"),
                        )
                        self.assertEqual(await self.helper.response(reader), b"")
                    except (ssl.SSLError, ConnectionError):
                        pass
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        await self.send(
                            adapter,
                            pki,
                            b"invalid",
                            context=pki.client_context(trust=unrelated.root / "ca.pem"),
                        )
                self.assertEqual(chat.state, before)

    async def test_cross_owner_wrong_bearer_host_and_certificate_revocation_are_generic(
        self,
    ):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            source,
            *_,
        ):
            async with self.opened(chat) as (adapter, pki, _, owner, revoked):
                valid = self.helper.helper.sign(self.helper.helper.body(source))
                forged = self.helper.helper.sign(
                    self.helper.helper.body(source).model_copy(
                        update={
                            "binding": source.authorization.binding.model_copy(
                                update={"owner_uid": chat.state.owner_uid + 1}
                            )
                        }
                    )
                )
                for packet, token in ((forged, fixtures.TOKEN), (valid, "e" * 64)):
                    before = chat.state
                    reader, _ = await self.send(adapter, pki, packet, token=token)
                    await self.helper.queued(adapter)
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(await self.helper.response(reader), REJECTED)
                    self.assertEqual(chat.state, before)
                reader, _ = await self.send(
                    adapter, pki, valid, host="private.invalid:1"
                )
                self.assertEqual(await self.helper.response(reader), REJECTED)
                reader, _ = await self.send(adapter, pki, valid)
                await self.helper.queued(adapter)
                revoked.add(adapter.tls.client_certificate_sha256)
                self.assertFalse(adapter.drain(owner))
                self.assertEqual(await self.helper.response(reader), REJECTED)
                self.assertEqual(chat.state, before)

    async def test_pending_handshakes_have_deadlines_and_count_toward_connection_limit(
        self,
    ):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            *_,
        ):
            async with self.opened(
                chat, max_connections=1, handshake_timeout_seconds=0.1
            ) as (adapter, _, _, _owner, _):
                before = chat.state
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", adapter.port
                )
                await fixtures.until(lambda: len(adapter.tasks) == 1)
                extra, extra_writer = await asyncio.open_connection(
                    "127.0.0.1", adapter.port
                )
                self.assertEqual(await self.helper.response(extra), b"")
                extra_writer.close()
                await extra_writer.wait_closed()
                self.assertEqual(await self.helper.response(reader), b"")
                writer.close()
                await writer.wait_closed()
                await fixtures.until(lambda: not adapter.tasks)
                self.assertEqual(chat.state, before)

    async def test_request_deadline_and_cancel_pending_handshake(self):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            source,
            *_,
        ):
            async with self.opened(chat, request_timeout_seconds=0.1) as (
                adapter,
                pki,
                _,
                owner,
                _,
            ):
                before = chat.state
                reader, _ = await self.send(
                    adapter,
                    pki,
                    self.helper.helper.sign(self.helper.helper.body(source)),
                )
                await self.helper.queued(adapter)
                self.assertFalse(adapter.drain(owner, busy=True))
                self.assertEqual(await self.helper.response(reader), REJECTED)
                self.assertFalse(adapter.drain(owner))
                self.assertEqual(chat.state, before)
                raw, writer = await asyncio.open_connection("127.0.0.1", adapter.port)
                await fixtures.until(lambda: len(adapter.tasks) > 0)
                await adapter.close()
                self.assertEqual(await self.helper.response(raw), b"")
                writer.close()
                await writer.wait_closed()
                self.assertEqual(chat.state, before)

    async def test_disconnect_before_owner_admission_and_lost_sender_ack(self):
        for kind in fixtures.fixtures.BACKENDS:
            with self.helper.helper.session(kind) as (chat, source, *_):
                async with self.opened(chat) as (adapter, pki, _, owner, _):
                    packet = self.helper.helper.sign(self.helper.helper.body(source))
                    _, writer = await self.send(adapter, pki, packet)
                    await self.helper.queued(adapter)
                    writer.transport.abort()
                    await fixtures.until(lambda: not adapter.tasks)
                    before = chat.state
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(chat.state, before)
                    _, writer = await self.send(adapter, pki, packet)
                    await self.helper.queued(adapter)
                    self.assertTrue(adapter.drain(owner))
                    writer.transport.abort()
                    retained = chat.state
                    reader, _ = await self.send(adapter, pki, packet)
                    await self.helper.queued(adapter)
                    self.assertTrue(adapter.drain(owner))
                    self.assertEqual(await self.helper.response(reader), SUCCESS)
                    self.assertEqual(chat.state, retained)

    async def test_scope_pin_and_unsafe_listener_fail_before_material_or_vault_reads(
        self,
    ):
        with TemporaryDirectory() as directory:
            pki = PKI(Path(directory))
            for change in (
                {"listen_address": "0.0.0.0", "allow_remote_bind": True},
                {"listen_address": "10.0.0.1"},
                {"peer_networks": ("0.0.0.0/0",)},
                {"listen_address": "example.com"},
            ):
                with self.assertRaises((ValidationError, ValueError)):
                    pki.settings(**change)
            with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
                chat,
                *_,
            ):
                grant = self.helper.make(chat)[0].grant
                raw = fixtures.Vault(grant)
                adapter = TLSEventTransport(
                    chat,
                    grant,
                    pki.settings(),
                    validate_certificates=lambda _: None,
                    backend=raw,
                )
                owner = fixtures.ActiveSessionTimers(chat, lambda _: None)
                owner.open()
                try:
                    with self.assertRaisesRegex(
                        ValueError, "^Ingress transport unavailable"
                    ):
                        await adapter.open(owner)
                    self.assertEqual(raw.reads, 0)
                    self.assertIsNone(adapter.listener)
                finally:
                    await adapter.close()
                    owner.close()

    async def test_invalid_server_material_never_opens_listener_or_reads_vault(self):
        for failure in ("expired", "pin", "key", "permissions", "symlink", "issuer"):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                pki = PKI(Path(directory))
                if failure == "expired":
                    pki.server = pki.leaf("server", server=True, expired=True)
                elif failure == "key":
                    (pki.root / "server-key.pem").write_bytes(
                        (pki.root / "client-key.pem").read_bytes()
                    )
                elif failure == "permissions":
                    (pki.root / "server-key.pem").chmod(0o644)
                elif failure == "symlink":
                    key = pki.root / "server-key.pem"
                    key.unlink()
                    key.symlink_to(pki.root / "client-key.pem")
                elif failure == "issuer":
                    with TemporaryDirectory() as unrelated_directory:
                        unrelated = PKI(Path(unrelated_directory))
                        pki.ca = unrelated.ca
                        pki.write(
                            "ca.pem",
                            unrelated.ca.public_bytes(serialization.Encoding.PEM),
                        )
                settings = pki.settings(
                    **(
                        {"server_certificate_sha256": "0" * 64}
                        if failure == "pin"
                        else {}
                    )
                )
                with self.helper.helper.session(
                    fixtures.fixtures.ConversationStore
                ) as (chat, *_):
                    grant = self.helper.make(chat)[0].grant.model_copy(
                        update={
                            "transport_authorization_sha256": (
                                settings.authorization_sha256
                            )
                        }
                    )
                    backend = fixtures.Vault(grant)
                    adapter = TLSEventTransport(
                        chat,
                        grant,
                        settings,
                        validate_certificates=lambda _: None,
                        backend=backend,
                    )
                    owner = fixtures.ActiveSessionTimers(chat, lambda _: None)
                    owner.open()
                    before = chat.state
                    try:
                        with self.assertRaisesRegex(
                            ValueError, "^Ingress transport unavailable.$"
                        ):
                            await adapter.open(owner)
                        self.assertIsNone(adapter.listener)
                        self.assertEqual(backend.reads, 0)
                        self.assertEqual(chat.state, before)
                    finally:
                        await adapter.close()
                        owner.close()

    async def test_expiry_and_all_certificate_revocations_before_commit(self):
        for failure in ("ca", "server", "client", "expiry"):
            with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
                chat,
                source,
                *_,
            ):
                async with self.opened(chat) as (adapter, pki, _, owner, revoked):
                    before = chat.state
                    packet = self.helper.helper.sign(self.helper.helper.body(source))
                    reader, _ = await self.send(adapter, pki, packet)
                    await self.helper.queued(adapter)
                    if failure == "expiry":
                        adapter.certificate_clock = lambda: (
                            datetime.now(UTC) + timedelta(days=5)
                        )
                    else:
                        revoked.add(
                            getattr(adapter.tls, failure + "_certificate_sha256")
                        )
                    self.assertFalse(adapter.drain(owner))
                    self.assertEqual(await self.helper.response(reader), REJECTED)
                    self.assertEqual(chat.state, before)

    async def test_hung_revocation_read_is_bounded_and_late_completion_inert(self):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            source,
            *_,
        ):
            async with self.opened(chat, request_timeout_seconds=0.1) as (
                adapter,
                pki,
                _,
                owner,
                _,
            ):
                release = Event()
                packet = self.helper.helper.sign(self.helper.helper.body(source))
                reader, _ = await self.send(adapter, pki, packet)
                await self.helper.queued(adapter)
                before = chat.state

                def hang(_settings: TLSIngressSettings) -> None:
                    release.wait(2)

                adapter.validate_certificates = hang
                started = time.monotonic()
                try:
                    self.assertFalse(adapter.drain(owner))
                    self.assertLess(time.monotonic() - started, 0.5)
                    self.assertEqual(await self.helper.response(reader), REJECTED)
                    self.assertEqual(chat.state, before)
                finally:
                    release.set()
                await asyncio.sleep(0.02)
                self.assertEqual(chat.state, before)

    async def test_peer_filter_attempt_flood_and_queue_limit(self):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            source,
            *_,
        ):
            async with self.opened(chat, queue_limit=1) as (adapter, pki, _, owner, _):
                packet = self.helper.helper.sign(self.helper.helper.body(source))
                before = chat.state
                first, _ = await self.send(adapter, pki, packet)
                await self.helper.queued(adapter)
                second, _ = await self.send(adapter, pki, packet)
                self.assertEqual(await self.helper.response(second), REJECTED)
                self.assertEqual(adapter.queue.qsize(), 1)
                self.assertEqual(chat.state, before)
                self.assertTrue(adapter.drain(owner))
                self.assertEqual(await self.helper.response(first), SUCCESS)
                retained = chat.state
                adapter._attempts = (time.monotonic(),) * 16  # pyright: ignore[reportPrivateUsage]
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", adapter.port
                )
                self.assertEqual(await self.helper.response(reader), b"")
                writer.close()
                await writer.wait_closed()
                self.assertEqual(chat.state, retained)
            async with self.opened(chat, peer_networks=("127.0.0.2/32",)) as (
                adapter,
                _,
                _,
                _,
                _,
            ):
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", adapter.port
                )
                self.assertEqual(await self.helper.response(reader), b"")
                writer.close()
                await writer.wait_closed()
                self.assertTrue(adapter.queue.empty())

    async def test_transport_policy_binding_preserves_old_loopback_accounts(self):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            *_,
        ):
            grant = self.helper.make(chat)[0].grant
            self.assertNotIn(
                "transport_authorization_sha256", grant.model_dump(mode="json")
            )
            self.assertEqual(
                grant.account,
                grant.model_copy(
                    update={"transport_authorization_sha256": None}
                ).account,
            )
            bound = grant.model_copy(
                update={"transport_authorization_sha256": "a" * 64}
            )
            self.assertNotEqual(grant.account, bound.account)

    async def test_shared_terminal_owns_tls_admission_dispatch_and_shutdown(self):
        for kind in fixtures.fixtures.BACKENDS:
            with self.helper.helper.session(kind) as (chat, source, *_):
                async with self.opened(chat, attached=False) as (adapter, pki, _, _, _):
                    client = fixtures.CapturingClient()
                    original = chat.step

                    async def step(
                        *, on_started: Callable[[], None] | None = None
                    ) -> bool:
                        return await original(client, on_started=on_started)  # noqa: B023

                    queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
                    with patch.object(chat, "step", step):
                        task = asyncio.create_task(
                            terminal(
                                chat, queue, lambda _: None, ingress_transport=adapter
                            )
                        )
                        try:
                            await fixtures.until(lambda: adapter.listener is not None)  # noqa: B023
                            reader, _ = await self.send(
                                adapter,
                                pki,
                                self.helper.helper.sign(
                                    self.helper.helper.body(source)
                                ),
                            )
                            self.assertEqual(
                                await self.helper.response(reader), SUCCESS
                            )
                            await fixtures.until(
                                lambda: (
                                    len(chat.state.entries) == 1
                                    and chat.state.entries[0].status == "completed"
                                )
                            )
                            self.assertNotIn(
                                fixtures.fixtures.PAYLOAD, str(client.requests)
                            )
                            await queue.put(None)
                            await asyncio.wait_for(task, 1)
                            self.assertTrue(adapter.closed)
                            self.assertIsNone(adapter.listener)
                            self.assertEqual(adapter.tasks, set())
                        finally:
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)

    async def test_disconnect_and_read_cancellation_during_trusted_validation(self):
        for failure in ("disconnect", "cancel"):
            with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
                chat,
                source,
                *_,
            ):
                async with self.opened(chat) as (adapter, pki, _, owner, _):
                    packet = self.helper.helper.sign(self.helper.helper.body(source))
                    reader, writer = await self.send(adapter, pki, packet)
                    await self.helper.queued(adapter)
                    peer = cast(ConnectedSocket, writer.get_extra_info("socket")).dup()

                    def interrupt(
                        _settings: TLSIngressSettings,
                        failure: str = failure,
                        peer: socket.socket = peer,
                    ) -> None:
                        if failure == "disconnect":
                            peer.shutdown(socket.SHUT_RDWR)
                        else:
                            chat.schedule_reads.cancel()

                    adapter.validate_certificates = interrupt
                    before = chat.state
                    try:
                        self.assertFalse(adapter.drain(owner))
                        self.assertEqual(chat.state, before)
                    finally:
                        peer.close()
                    if failure == "cancel":
                        self.assertEqual(await self.helper.response(reader), REJECTED)

    async def test_credential_rotation_requires_new_bound_grant_and_preserves_metadata(
        self,
    ):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            source,
            *_,
        ):
            async with self.opened(chat) as (adapter, pki, vault, owner, _):
                packet = self.helper.helper.sign(self.helper.helper.body(source))
                reader, _ = await self.send(adapter, pki, packet)
                await self.helper.queued(adapter)
                self.assertTrue(adapter.drain(owner))
                self.assertEqual(await self.helper.response(reader), SUCCESS)
                retained = chat.state
                token = "e" * 64
                replacement = adapter.grant.model_copy(
                    update={
                        "credential_sha256": digest(token.encode()),
                    }
                )
                await vault.rotate(adapter.grant, replacement, SecretStr(token))
                reader, _ = await self.send(adapter, pki, packet)
                await self.helper.queued(adapter)
                self.assertFalse(adapter.drain(owner))
                self.assertEqual(await self.helper.response(reader), REJECTED)
                successor = TLSEventTransport(
                    chat,
                    replacement,
                    adapter.tls,
                    validate_certificates=adapter.validate_certificates,
                    backend=vault,
                )
                try:
                    await successor.open(owner)
                    reader, _ = await self.send(successor, pki, packet, token=token)
                    await self.helper.queued(successor)
                    self.assertTrue(successor.drain(owner))
                    self.assertEqual(await self.helper.response(reader), SUCCESS)
                    self.assertEqual(chat.state, retained)
                finally:
                    await successor.close()
                    await vault.revoke(replacement)

    async def test_lost_store_ack_restart_and_revocation_retain_exposure(self):
        for kind in fixtures.fixtures.BACKENDS:
            for phase in ("metadata", "queue", "running"):
                with self.helper.helper.session(kind) as (chat, source, _, _, _, store):
                    async with self.opened(chat) as (adapter, pki, vault, owner, _):

                        def lose_ack(
                            state: fixtures.fixtures.ConversationState,
                        ) -> None:
                            store.save(state)
                            raise OSError("PRIVATE persistence artifact")

                        if phase == "metadata":
                            chat.save = lose_ack
                        reader, _ = await self.send(
                            adapter,
                            pki,
                            self.helper.helper.sign(self.helper.helper.body(source)),
                        )
                        await self.helper.queued(adapter)
                        if phase == "metadata":
                            with self.assertRaises(OSError):
                                adapter.drain(owner)
                            expected = REJECTED
                        else:
                            self.assertTrue(adapter.drain(owner))
                            expected = SUCCESS
                        self.assertEqual(await self.helper.response(reader), expected)
                        if phase == "queue":
                            chat.save = lose_ack
                            with self.assertRaises(OSError):
                                owner.tick()
                        elif phase == "running":
                            self.assertEqual(len(owner.tick()), 1)
                            chat.save = lose_ack
                            client = fixtures.CapturingClient()
                            with self.assertRaises(OSError):
                                await chat.step(client)
                            self.assertEqual(client.requests, [])
                        committed = store.load()
                        retained = committed.schedules[0].state
                        await vault.revoke(adapter.grant)
                        self.assertIsNone(await vault.lookup(adapter.grant))
                        self.assertEqual(store.load(), committed)
                        resumed = fixtures.fixtures.ConversationController(
                            committed,
                            chat.cassette,
                            store.save,
                            goal_clock=lambda: 100.0,
                            schedule_observer=lambda s: s.binding,
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
                            recovered.ledger.input_bytes, retained.ledger.input_bytes
                        )
                        self.assertFalse(await resumed.step(fixtures.CapturingClient()))

    async def test_bound_grant_cannot_downgrade_or_change_policy_or_owner(self):
        with self.helper.helper.session(fixtures.fixtures.ConversationStore) as (
            chat,
            *_,
        ):
            async with self.opened(chat) as (adapter, pki, vault, owner, _):
                before = chat.state
                downgraded = fixtures.LoopbackEventTransport(
                    chat,
                    adapter.grant,
                    fixtures.LoopbackIngressSettings(allow_loopback_http=True),
                    backend=vault,
                )
                try:
                    with self.assertRaisesRegex(
                        ValueError, "^Ingress transport unavailable.$"
                    ):
                        await downgraded.open(owner)
                    self.assertIsNone(downgraded.server)
                finally:
                    await downgraded.close()
                changed = pki.settings(max_connections=1)
                foreign = adapter.grant.model_copy(
                    update={
                        "binding": adapter.grant.binding.model_copy(
                            update={"owner_uid": chat.state.owner_uid + 1}
                        )
                    }
                )
                for grant, settings in (
                    (adapter.grant, changed),
                    (foreign, adapter.tls),
                ):
                    rejected = TLSEventTransport(
                        chat,
                        grant,
                        settings,
                        validate_certificates=lambda _: None,
                        backend=vault,
                    )
                    try:
                        with self.assertRaisesRegex(
                            ValueError, "^Ingress transport unavailable.$"
                        ):
                            await rejected.open(owner)
                        self.assertIsNone(rejected.listener)
                        self.assertEqual(chat.state, before)
                    finally:
                        await rejected.close()
