"""Explicit mutual TLS ingress; handshakes count against owner connection limits."""

import asyncio
import ipaddress
import os
import socket
import ssl
import stat
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Self, cast

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID
from pydantic import Field, SecretStr, model_validator

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_schedule_driver import ActiveSessionTimers
from mos_eisley.conversation_schedule_transport import (
    ConnectedSocket,
    Delivery,
    IngressTransportGrant,
    LoopbackEventTransport,
    LoopbackIngressSettings,
    credential_backend,
)
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.tools.mcp_oauth_store import CredentialBackend


class TLSIngressSettings(Contract):
    listen_address: Annotated[str, Field(max_length=15)] = "127.0.0.1"
    allow_remote_bind: bool = False
    peer_networks: Annotated[tuple[str, ...], Field(min_length=1, max_length=4)] = (
        "127.0.0.1/32",
    )
    server_name: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,252}$")]
    ca_file: Annotated[str, Field(max_length=4096)]
    certificate_file: Annotated[str, Field(max_length=4096)]
    private_key_file: Annotated[str, Field(max_length=4096)]
    ca_certificate_sha256: Digest
    server_certificate_sha256: Digest
    client_certificate_sha256: Digest
    port: Annotated[int, Field(ge=0, le=65535)] = 0
    max_connections: Annotated[int, Field(ge=1, le=4)] = 4
    queue_limit: Annotated[int, Field(ge=1, le=4)] = 4
    request_timeout_seconds: Annotated[float, Field(ge=0.05, le=30)] = 5.0
    handshake_timeout_seconds: Annotated[float, Field(ge=0.05, le=10)] = 2.0

    @model_validator(mode="after")
    def explicit_network(self) -> Self:
        address = ipaddress.IPv4Address(self.listen_address)
        if (
            address.is_unspecified
            or address.is_multicast
            or address.is_link_local
            or (address.is_reserved and not address.is_loopback)
        ):
            raise ValueError("TLS listener requires an explicit unicast IPv4 address.")
        if not address.is_loopback and not self.allow_remote_bind:
            raise ValueError("Remote TLS binding requires explicit host authorization.")
        for value in self.peer_networks:
            network = ipaddress.IPv4Network(value, strict=True)
            if (
                network.prefixlen < 24
                or network.network_address.is_multicast
                or network.network_address.is_link_local
                or network.network_address.is_unspecified
                or (network.network_address.is_reserved and not network.is_loopback)
            ):
                raise ValueError("TLS peers require narrow explicit IPv4 networks.")
            if not network.is_loopback and not self.allow_remote_bind:
                raise ValueError(
                    "Remote TLS peers require explicit host authorization."
                )
        for value in (self.ca_file, self.certificate_file, self.private_key_file):
            if not Path(value).is_absolute():
                raise ValueError("TLS material requires explicit absolute paths.")
        return self

    @property
    def authorization_sha256(self) -> str:
        return digest(canonical_bytes(self))


class TLSEventTransport(LoopbackEventTransport):
    """Pinned mutual TLS, native bearer and signed source, owned by the terminal."""

    def __init__(
        self,
        controller: RuntimeConversationController,
        grant: IngressTransportGrant,
        settings: TLSIngressSettings,
        *,
        validate_certificates: Callable[[TLSIngressSettings], None],
        backend: CredentialBackend | None = None,
        certificate_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.tls = TLSIngressSettings.model_validate_json(canonical_bytes(settings))
        self.authorization_sha256 = self.tls.authorization_sha256
        self.validate_certificates = validate_certificates
        self.certificate_clock = certificate_clock
        self.material: tuple[x509.Certificate, x509.Certificate] | None = None
        self.context: ssl.SSLContext | None = None
        self.listener: socket.socket | None = None
        self.accepting: asyncio.Task[None] | None = None
        super().__init__(
            controller,
            grant,
            LoopbackIngressSettings(
                allow_loopback_http=True,
                port=settings.port,
                max_connections=settings.max_connections,
                queue_limit=settings.queue_limit,
                request_timeout_seconds=settings.request_timeout_seconds,
            ),
            backend=backend,
        )

    def _transport_scope(self) -> None:
        if (
            self.tls.authorization_sha256 != self.authorization_sha256
            or self.grant.transport_authorization_sha256 != self.authorization_sha256
        ):
            raise ValueError("Ingress transport unavailable.")

    def _valid_dates(self, certificates: tuple[x509.Certificate, ...]) -> None:
        now = self.certificate_clock()
        if now.tzinfo is None or any(
            not c.not_valid_before_utc <= now < c.not_valid_after_utc
            for c in certificates
        ):
            raise ValueError("Ingress transport unavailable.")

    def _tls_guard(self, client: x509.Certificate | None = None) -> None:
        self._scope()
        if self.material is None:
            raise ValueError("Ingress transport unavailable.")
        self._valid_dates((*self.material, *((client,) if client is not None else ())))
        self.validate_certificates(self.tls)  # Trusted read-only host revocation port.
        self._scope()

    def _credential(self, token: SecretStr | None = None) -> None:
        self._tls_guard()
        super()._credential(token)
        self._tls_guard()

    def _read_material(self, name: str, *, private: bool = False) -> bytes:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != self.grant.binding.owner_uid
                or info.st_mode & 0o022
                or (private and stat.S_IMODE(info.st_mode) != 0o600)
                or info.st_size > 65536
            ):
                raise ValueError("Ingress transport unavailable.")
            value = stream.read(65537)
            if len(value) > 65536:
                raise ValueError("Ingress transport unavailable.")
            return value

    def _context(
        self,
    ) -> tuple[ssl.SSLContext, tuple[x509.Certificate, x509.Certificate]]:
        self._scope()
        ca = x509.load_pem_x509_certificate(self._read_material(self.tls.ca_file))
        server = x509.load_pem_x509_certificate(
            self._read_material(self.tls.certificate_file)
        )
        key = self._read_material(self.tls.private_key_file, private=True)
        parsed = serialization.load_pem_private_key(key, password=None)
        if (
            digest(ca.public_bytes(serialization.Encoding.DER))
            != self.tls.ca_certificate_sha256
            or digest(server.public_bytes(serialization.Encoding.DER))
            != self.tls.server_certificate_sha256
            or parsed.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            != server.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            or not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
            or server.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
            or ExtendedKeyUsageOID.SERVER_AUTH
            not in server.extensions.get_extension_for_class(
                x509.ExtendedKeyUsage
            ).value
            or self.tls.server_name
            not in server.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value.get_values_for_type(x509.DNSName)
        ):
            raise ValueError("Ingress transport unavailable.")
        ca.verify_directly_issued_by(ca)
        server.verify_directly_issued_by(ca)
        self._valid_dates((ca, server))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_REQUIRED
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        context.options |= ssl.OP_NO_TICKET
        context.num_tickets = 0
        context.set_alpn_protocols(["http/1.1"])
        context.load_verify_locations(
            cadata=ca.public_bytes(serialization.Encoding.PEM).decode("ascii")
        )
        # Load only validated captured bytes; do not reread mutable host files.
        with TemporaryDirectory(prefix="mos-ingress-tls-") as directory:
            paths = [Path(directory) / "certificate.pem", Path(directory) / "key.pem"]
            for path, value in zip(
                paths,
                (server.public_bytes(serialization.Encoding.PEM), key),
                strict=True,
            ):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(value)
            context.load_cert_chain(str(paths[0]), str(paths[1]))
        return context, (ca, server)

    async def open(self, owner: ActiveSessionTimers) -> None:
        if self.listener is not None or self.owner is not None or self.closed:
            raise ValueError("Ingress transport unavailable.")
        self.owner = owner
        deadline = time.monotonic() + self.settings.request_timeout_seconds
        try:
            self._scope()
            with self.controller.schedule_reads.operation(deadline=deadline):
                self.context, self.material = self.controller.schedule_reads.call(
                    self._context
                )
                if self.backend is None:
                    self.backend = self.controller.schedule_reads.call(
                        credential_backend
                    )
                self.controller.schedule_reads.call(self._credential)
                self.controller.schedule_reads.check()
            self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener.setblocking(False)
            self.listener.bind((self.tls.listen_address, self.tls.port))
            self.listener.listen(self.settings.max_connections)
            if time.monotonic() >= deadline:
                raise ValueError("Ingress transport unavailable.")
            self._scope()
            self.accepting = asyncio.create_task(self._accept())
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception:
            await self.close()
            raise ValueError("Ingress transport unavailable.") from None

    @property
    def port(self) -> int:
        if self.listener is None:
            raise ValueError("Ingress transport unavailable.")
        return int(self.listener.getsockname()[1])

    @property
    def http_host(self) -> str:
        return f"{self.tls.server_name}:{self.port}"

    async def _accept(self) -> None:
        assert self.listener is not None
        try:
            while not self.closed:
                connection, address = await asyncio.get_running_loop().sock_accept(
                    self.listener
                )
                now = time.monotonic()
                attempts = tuple(t for t in self._attempts if now - t < 1)
                if (
                    len(self.tasks) >= self.settings.max_connections
                    or len(attempts) >= 16
                    or not any(
                        ipaddress.IPv4Address(address[0]) in ipaddress.IPv4Network(n)
                        for n in self.tls.peer_networks
                    )
                ):
                    connection.close()
                    await asyncio.sleep(0)
                    continue
                self._attempts = (*attempts, now)
                task = asyncio.create_task(self._tls_connection(connection))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
                # A busy listener cannot monopolize terminal/user-steering turns.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.ready.set()  # Wake owner; drain fails closed without a live acceptor.

    async def _tls_connection(self, connection: socket.socket) -> None:
        writer: asyncio.StreamWriter | None = None
        try:
            self._scope()
            if self.context is None:
                raise ValueError("Ingress transport unavailable.")
            reader = asyncio.StreamReader(limit=4096)
            protocol = asyncio.StreamReaderProtocol(reader)
            transport, _ = await asyncio.get_running_loop().connect_accepted_socket(
                lambda: protocol,
                connection,
                ssl=self.context,
                ssl_handshake_timeout=self.tls.handshake_timeout_seconds,
                ssl_shutdown_timeout=0.25,
            )
            writer = asyncio.StreamWriter(
                transport, protocol, reader, asyncio.get_running_loop()
            )
            self._peer_certificate(writer)
            await self._connection(reader, writer)
        except (Exception, asyncio.CancelledError):
            pass  # TLS failures disclose no HTTP/session/native diagnostic.
        finally:
            if writer is not None:
                writer.close()
                with suppress(Exception):
                    async with asyncio.timeout(0.25):
                        await writer.wait_closed()
            connection.close()

    def _peer_certificate(self, writer: asyncio.StreamWriter) -> x509.Certificate:
        secure = cast(ssl.SSLObject | None, writer.get_extra_info("ssl_object"))
        if (
            secure is None
            or secure.version() != "TLSv1.3"
            or secure.selected_alpn_protocol() != "http/1.1"
        ):
            raise ValueError("Ingress transport unavailable.")
        certificate = secure.getpeercert(binary_form=True)
        if not certificate or digest(certificate) != self.tls.client_certificate_sha256:
            raise ValueError("Ingress transport unavailable.")
        parsed = x509.load_der_x509_certificate(certificate)
        self._valid_dates((parsed,))
        if (
            ExtendedKeyUsageOID.CLIENT_AUTH
            not in parsed.extensions.get_extension_for_class(
                x509.ExtendedKeyUsage
            ).value
        ):
            raise ValueError("Ingress transport unavailable.")
        return parsed

    def _delivery(
        self, packet: bytes, token: str, deadline: float, writer: asyncio.StreamWriter
    ) -> Delivery:
        client = self._peer_certificate(writer)
        connection = cast(ConnectedSocket, writer.get_extra_info("socket"))
        peer = connection.dup()
        peer.setblocking(False)
        return Delivery(
            packet,
            token,
            deadline,
            peer,
            check_authorization=lambda: self._tls_guard(client),
        )

    def drain(self, owner: ActiveSessionTimers, *, busy: bool = False) -> bool:
        if not self.closed and self.accepting is not None and self.accepting.done():
            raise ValueError("Ingress transport unavailable.")
        return super().drain(owner, busy=busy)

    async def close(self) -> None:
        self.closed = True
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        if self.accepting is not None:
            self.accepting.cancel()
            await asyncio.gather(self.accepting, return_exceptions=True)
            self.accepting = None
        await super().close()
