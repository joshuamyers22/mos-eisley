"""Explicit loopback ingress: socket tasks read frames, the active owner commits."""

import asyncio
import hmac
import math
import os
import re
import socket
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Annotated, Literal, Protocol, cast

from pydantic import Field, SecretStr

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_schedule import ScheduleBinding
from mos_eisley.conversation_schedule_driver import ActiveSessionTimers
from mos_eisley.conversation_schedule_ingress import (
    MAX_PACKET_BYTES,
    InertExternalIngress,
)
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.tools.mcp_oauth_store import CredentialBackend

SERVICE = "mos-eisley.schedule.ingress.v1"
SUCCESS = (
    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
    b'Content-Length: 21\r\nConnection: close\r\n\r\n{"status":"received"}'
)
REJECTED = (
    b"HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\n"
    b'Content-Length: 24\r\nConnection: close\r\n\r\n{"status":"unavailable"}'
)


def credential_backend() -> CredentialBackend:
    # Local import avoids the grant/host-vault cycle; no native lookup on import.
    from mos_eisley.conversation_schedule_credentials import NativeIngressVault

    return NativeIngressVault()


class IngressTransportGrant(Contract):
    binding: ScheduleBinding
    schedule_id: Identifier
    source_id: Identifier
    source_authorization_sha256: Digest
    credential_id: Identifier
    credential_sha256: Digest
    not_after: Annotated[float, Field(ge=0)]
    transport_authorization_sha256: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @property
    def account(self) -> str:
        return digest(canonical_bytes(self))


class LoopbackIngressSettings(Contract):
    # Deliberate literal-loopback exception, following MCP's HTTP boundary.
    allow_loopback_http: Literal[True]
    port: Annotated[int, Field(ge=0, le=65535)] = 0
    max_connections: Annotated[int, Field(ge=1, le=4)] = 4
    queue_limit: Annotated[int, Field(ge=1, le=4)] = 4
    request_timeout_seconds: Annotated[float, Field(ge=0.05, le=30)] = 5.0


class ConnectedSocket(Protocol):
    def dup(self) -> socket.socket: ...


class Delivery:
    def __init__(
        self,
        packet: bytes,
        token: str,
        deadline: float,
        peer: socket.socket,
        *,
        check_authorization: Callable[[], None] | None = None,
    ) -> None:
        self.check_authorization = check_authorization
        self.peer = peer
        self.packet = packet
        self.token = SecretStr(token)
        self.deadline = deadline
        self.ack: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    def check(self) -> None:
        if self.ack.cancelled() or time.monotonic() >= self.deadline:
            raise ValueError("Ingress transport unavailable.")
        # asyncio cannot deliver EOF while the owner waits on a trusted read.
        # A non-consuming kernel check catches that disconnect before commit.
        if self.check_authorization is not None:
            self.check_authorization()
        try:
            self.peer.recv(1, socket.MSG_PEEK)
        except BlockingIOError:
            return
        raise ValueError("Ingress transport unavailable.")


class LoopbackEventTransport:
    """One source, one owner and one POST route; no artifact or administration API."""

    def __init__(
        self,
        controller: RuntimeConversationController,
        grant: IngressTransportGrant,
        settings: LoopbackIngressSettings,
        *,
        backend: CredentialBackend | None = None,
    ) -> None:
        self.controller = controller
        self.grant = IngressTransportGrant.model_validate_json(canonical_bytes(grant))
        self.settings = LoopbackIngressSettings.model_validate_json(
            canonical_bytes(settings)
        )
        self.backend: CredentialBackend | None = backend  # Selected on explicit open.
        self.queue: asyncio.Queue[Delivery] = asyncio.Queue(
            maxsize=settings.queue_limit
        )
        self.ready = asyncio.Event()
        self.server: asyncio.Server | None = None
        self.owner: ActiveSessionTimers | None = None
        self.tasks: set[asyncio.Task[None]] = set()
        self.closed = False
        self._attempts: tuple[float, ...] = ()

    def _transport_scope(self) -> None:
        if self.grant.transport_authorization_sha256 is not None:
            raise ValueError("Ingress transport unavailable.")

    def _scope(self) -> None:
        self._transport_scope()
        chat, grant = self.controller, self.grant
        now = chat.goal_clock()
        if (
            self.closed
            or self.owner is None
            or not self.owner.qualified
            or self.owner.controller is not chat
            or os.geteuid() != grant.binding.owner_uid
            or chat.state.owner_uid != grant.binding.owner_uid
            or chat.state.session_id != grant.binding.session_id
            or digest(chat.state.workspace.encode()) != grant.binding.workspace_sha256
            or chat.persistence_broken
            or not math.isfinite(now)
            or now < 0
            or now >= grant.not_after
        ):
            raise ValueError("Ingress transport unavailable.")
        record = next(
            (
                s
                for s in chat.state.schedules
                if s.state.spec.schedule_id == grant.schedule_id
            ),
            None,
        )
        source = chat.schedule_sources.get((grant.schedule_id, grant.source_id))
        if (
            record is None
            or record.state.spec.binding != grant.binding
            or not isinstance(source, InertExternalIngress)
            or source.authorization.binding != grant.binding
            or source.authorization.pin.authorization_sha256
            != grant.source_authorization_sha256
            or source.authorization.pin not in record.state.spec.local_source_pins
            or grant.not_after > source.authorization.not_after
        ):
            raise ValueError("Ingress transport unavailable.")

    def _credential(self, token: SecretStr | None = None) -> None:
        self._scope()
        backend = self.backend
        if backend is None:
            raise ValueError("Ingress transport unavailable.")
        value = backend.get_password(SERVICE, self.grant.account)
        if (
            value is None
            or len(value) != 64
            or not re.fullmatch(r"[0-9a-f]{64}", value)
            or digest(value.encode()) != self.grant.credential_sha256
            or (
                token is not None
                and not hmac.compare_digest(value, token.get_secret_value())
            )
        ):
            raise ValueError("Ingress transport unavailable.")
        self._scope()

    async def open(self, owner: ActiveSessionTimers) -> None:
        if self.server is not None or self.owner is not None or self.closed:
            raise ValueError("Ingress transport unavailable.")
        self.owner = owner
        deadline = time.monotonic() + self.settings.request_timeout_seconds
        try:
            self._scope()
            with self.controller.schedule_reads.operation(deadline=deadline):
                if self.backend is None:
                    self.backend = self.controller.schedule_reads.call(
                        credential_backend
                    )
                self.controller.schedule_reads.call(self._credential)
            async with asyncio.timeout_at(deadline):
                self.server = await asyncio.start_server(
                    self._connected,
                    host="127.0.0.1",
                    port=self.settings.port,
                    limit=4096,
                    backlog=self.settings.max_connections,
                )
                self._scope()
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception:
            await self.close()
            raise ValueError("Ingress transport unavailable.") from None

    @property
    def port(self) -> int:
        if self.server is None or not self.server.sockets:
            raise ValueError("Ingress transport unavailable.")
        return int(self.server.sockets[0].getsockname()[1])

    def _connected(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        now = time.monotonic()
        attempts = tuple(t for t in self._attempts if now - t < 1)
        if (
            self.closed
            or len(self.tasks) >= self.settings.max_connections
            or len(attempts) >= 16
        ):
            writer.close()
            return
        self._attempts = (*attempts, now)
        task = asyncio.create_task(self._connection(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    @property
    def http_host(self) -> str:
        return f"127.0.0.1:{self.port}"

    def _delivery(
        self, packet: bytes, token: str, deadline: float, writer: asyncio.StreamWriter
    ) -> Delivery:
        connection = cast(ConnectedSocket, writer.get_extra_info("socket"))
        peer = connection.dup()
        peer.setblocking(False)
        return Delivery(packet, token, deadline, peer)

    async def _connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        delivery: Delivery | None = None
        disconnected: asyncio.Task[bytes] | None = None
        reply = REJECTED
        deadline = time.monotonic() + self.settings.request_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                header = await reader.readuntil(b"\r\n\r\n")
                if len(header) > 4096:
                    raise ValueError("Invalid frame")
                lines = header.decode("ascii").split("\r\n")
                if lines[0] != "POST /events HTTP/1.1":
                    raise ValueError("Invalid frame")
                headers: dict[str, str] = {}
                for line in lines[1:-2]:
                    key, value = line.split(":", 1)
                    key = key.lower()
                    if key in headers or key not in {
                        "host",
                        "content-type",
                        "content-length",
                        "authorization",
                        "connection",
                    }:
                        raise ValueError("Invalid frame")
                    headers[key] = value.strip()
                if (
                    headers.get("host") != self.http_host
                    or headers.get("content-type") != "application/json"
                    or not re.fullmatch(
                        r"[1-9][0-9]{0,4}", headers.get("content-length", "")
                    )
                    or not re.fullmatch(
                        r"Bearer [0-9a-f]{64}", headers.get("authorization", "")
                    )
                ):
                    raise ValueError("Invalid frame")
                size = int(headers["content-length"])
                if size > MAX_PACKET_BYTES:
                    raise ValueError("Invalid frame")
                packet = await reader.readexactly(size)
                delivery = self._delivery(
                    packet, headers["authorization"][7:], deadline, writer
                )
                self.queue.put_nowait(delivery)
                self.ready.set()
                disconnected = asyncio.create_task(reader.read(1))
                done, _ = await asyncio.wait(
                    (delivery.ack, disconnected), return_when=asyncio.FIRST_COMPLETED
                )
                if disconnected in done:
                    delivery.ack.cancel()
                elif delivery.ack.result():
                    reply = SUCCESS
        except (Exception, asyncio.CancelledError):
            if delivery is not None:
                delivery.ack.cancel()
        finally:
            if delivery is not None:
                delivery.peer.close()
            if disconnected is not None:
                disconnected.cancel()
                with suppress(asyncio.CancelledError):
                    await disconnected
            if not writer.is_closing():
                with suppress(Exception):
                    writer.write(reply)
                    async with asyncio.timeout(0.25):
                        await writer.drain()
            writer.close()
            with suppress(Exception):
                async with asyncio.timeout(0.25):
                    await writer.wait_closed()

    def drain(self, owner: ActiveSessionTimers, *, busy: bool = False) -> bool:
        """One delivery at an idle owner boundary; sockets never touch the store."""
        if busy or not self.controller.schedule_timer_idle:
            return False
        if owner is not self.owner or not owner.qualified:
            raise ValueError("Ingress transport unavailable.")
        if self.queue.empty():
            self.ready.clear()
            return False
        delivery = self.queue.get_nowait()
        if self.queue.empty():
            self.ready.clear()
        if delivery.ack.cancelled() or time.monotonic() >= delivery.deadline:
            if not delivery.ack.done():
                delivery.ack.set_result(False)
            return False

        def guard() -> None:
            delivery.check()
            self._credential(delivery.token)
            delivery.check()

        try:
            with self.controller.schedule_reads.operation(deadline=delivery.deadline):
                self.controller.receive_external_event(
                    self.grant.schedule_id,
                    self.grant.source_id,
                    delivery.packet,
                    expected_revision=self.controller.state.revision,
                    transport_guard=guard,
                )
        except Exception:
            if not delivery.ack.done():
                delivery.ack.set_result(False)
            if self.controller.persistence_broken:
                raise
            return False
        if not delivery.ack.done():
            delivery.ack.set_result(True)
        return True

    async def close(self) -> None:
        self.closed = True
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        while not self.queue.empty():
            self.queue.get_nowait().ack.cancel()
        self.ready.clear()
        self.owner = None
