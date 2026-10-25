"""Pinned, zero-retry HTTP attachment inside the trusted host broker only."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import math
import re
import socket
import ssl
from collections.abc import Awaitable, Callable, Generator, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from typing import Annotated, Any, Literal, Self, cast

import certifi
import httpcore2
from pydantic import Field, JsonValue, TypeAdapter, model_validator

from mos_eisley.core.dispatch_guard import revalidate_dispatch
from mos_eisley.core.models import Contract, Identifier
from mos_eisley.core.ports import ProviderError
from mos_eisley.run.network_credentials import (
    CredentialBoundaryError,
    CredentialRef,
    NativeNetworkCredentials,
)

MAX_BYTES = 1_000_000
_JSON = TypeAdapter(dict[str, JsonValue])


_private_exchange: ContextVar[bool] = ContextVar(
    "private_network_exchange", default=False
)
_log_lock = Lock()


class _PrivateExchangeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _private_exchange.get()


_log_filter = _PrivateExchangeFilter()


@contextmanager
def _private_logging() -> Generator[None]:
    # The pinned HTTP/1.1 client can debug-log arbitrary response headers and
    # protocol exceptions. Filters apply at the producing loggers, before any
    # handlers. ContextVar isolation preserves logging for concurrent legacy calls.
    # Recheck this inventory when upgrading httpcore2 or enabling another protocol.
    with _log_lock:
        for name in ("httpcore2.connection", "httpcore2.http11"):
            logging.getLogger(name).addFilter(_log_filter)
    token = _private_exchange.set(True)
    try:
        yield
    finally:
        _private_exchange.reset(token)


class NetworkEndpoint(Contract):
    """Trusted admin record; never constructed from model or project input."""

    schema_version: Literal[1] = 1
    endpoint_id: Identifier
    scheme: Literal["https", "http"] = "https"
    host: str = Field(min_length=1, max_length=253)
    port: Annotated[int, Field(ge=1, le=65535)] = 443
    addresses: tuple[str, ...] = Field(min_length=1, max_length=16)
    allow_loopback: bool = False
    operations: dict[Identifier, str] = Field(min_length=1, max_length=8)
    header: Literal["authorization", "x-api-key"] = "authorization"
    expires_at: float

    @model_validator(mode="after")
    def valid_endpoint(self) -> Self:
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", self.host)
            or not math.isfinite(self.expires_at)
            or len(set(self.addresses)) != len(self.addresses)
        ):
            raise ValueError("invalid endpoint")
        for value in self.addresses:
            address = ipaddress.ip_address(value)
            if str(address) != value or not (
                address.is_loopback
                if self.allow_loopback
                else (
                    address.is_global
                    and not address.is_multicast
                    and not address.is_reserved
                    and not address.is_unspecified
                )
            ):
                raise ValueError("endpoint address is outside approved network class")
        if self.scheme == "http" and not self.allow_loopback:
            raise ValueError("TLS required outside explicit loopback")
        for path in self.operations.values():
            if not re.fullmatch(r"/[A-Za-z0-9_/-]+", path) or "//" in path:
                raise ValueError("operation requires an exact absolute path")
        return self


class _AttachmentStream(httpcore2.AsyncNetworkStream):
    def __init__(
        self,
        stream: httpcore2.AsyncNetworkStream,
        authorize: Callable[[], Awaitable[str]],
        marker: bytes,
    ) -> None:
        self.stream = stream
        self.authorize = authorize
        self.marker = marker
        self.first = True

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self.stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        secret = await self.authorize()
        if self.first:
            if buffer.count(self.marker) != 1 or not buffer.endswith(b"\r\n\r\n"):
                raise CredentialBoundaryError("Unsupported network client behavior")
            buffer = buffer.replace(self.marker, secret.encode("ascii"), 1)
            self.first = False
        await self.stream.write(buffer, timeout)

    async def aclose(self) -> None:
        await self.stream.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        self.stream = await self.stream.start_tls(ssl_context, server_hostname, timeout)
        return self

    def get_extra_info(self, info: str) -> Any:
        return self.stream.get_extra_info(info)


class _PinnedBackend(httpcore2.AsyncNetworkBackend):
    def __init__(
        self,
        endpoint: NetworkEndpoint,
        authorize: Callable[[], Awaitable[str]],
        marker: bytes,
    ) -> None:
        self._backend = cast(httpcore2.AsyncNetworkBackend, httpcore2.AnyIOBackend())
        self.endpoint = endpoint
        self.authorize = authorize
        self.marker = marker

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        if host != self.endpoint.host or port != self.endpoint.port:
            raise CredentialBoundaryError("Network destination changed")
        # Resolve once, compare the complete set, then connect a literal address.
        # There is no second hostname lookup between validation and connection.
        answers = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )
        addresses = {str(ipaddress.ip_address(item[4][0])) for item in answers}
        if addresses != set(self.endpoint.addresses):
            raise CredentialBoundaryError("Network destination changed")
        stream = await self._backend.connect_tcp(
            self.endpoint.addresses[0], port, timeout, local_address, socket_options
        )
        return _AttachmentStream(stream, self.authorize, self.marker)


class CredentialNetwork:
    """No arbitrary client, headers, URL, proxy, redirect, retry or streaming API.

    This is a host transport collaborator, not a tool or a new authority issuer.
    Trusted policy/spend admission must precede each call. Existing request-bound
    brokers and durable session journals retain consumption and uncertain effects.
    """

    def __init__(
        self,
        endpoint: NetworkEndpoint,
        reference: CredentialRef,
        credentials: NativeNetworkCredentials,
        *,
        admission_check: Callable[[], None],
        timeout: float = 30,
        tls_ca_pem: str | None = None,
    ) -> None:
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("invalid network deadline")
        # Freeze nested mutable values; retain no caller-owned dictionaries.
        self._endpoint = NetworkEndpoint.model_validate_json(endpoint.model_dump_json())
        self._reference = reference
        self._credentials = credentials
        self._admission_check = admission_check
        self._timeout = timeout
        # Explicit CA bundle: ambient SSL_CERT_FILE/DIR cannot change trust.
        self._tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._tls.load_verify_locations(cafile=certifi.where())
        if tls_ca_pem is not None:
            self._tls.load_verify_locations(cadata=tls_ca_pem)

    async def post(
        self, operation: str, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        import secrets
        import time

        endpoint = self._endpoint
        marker = ("mos-attachment-" + secrets.token_hex(32)).encode("ascii")
        seen: list[str] = []
        generation: str | None = None

        async def authorize() -> str:
            nonlocal generation
            revalidate_dispatch()
            self._admission_check()
            if time.time() >= endpoint.expires_at:
                raise CredentialBoundaryError("Network approval expired")
            credential = await asyncio.to_thread(
                self._credentials.resolve,
                self._reference,
                endpoint.endpoint_id,
                operation,
            )
            revalidate_dispatch()
            self._admission_check()
            if time.time() >= min(
                endpoint.expires_at, credential.expires_at.timestamp()
            ):
                raise CredentialBoundaryError("Network approval expired")
            if generation is not None and (
                generation != credential.generation
                or credential.secret.get_secret_value() != seen[0]
            ):
                raise CredentialBoundaryError(
                    "Network credential changed during dispatch"
                )
            generation = credential.generation
            secret = credential.secret.get_secret_value()
            if secret not in seen:
                seen.append(secret)
            return secret

        result: dict[str, JsonValue] | None = None
        try:
            with _private_logging():
                async with asyncio.timeout(self._timeout):
                    if operation not in endpoint.operations:
                        raise CredentialBoundaryError("Network operation not approved")
                    revalidate_dispatch()
                    self._admission_check()
                    self._credentials.check_owner(self._reference)
                    encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
                    if len(encoded) > MAX_BYTES:
                        raise ValueError("request limit")
                    # Marker only: the actual credential is resolved after DNS, TCP
                    # and TLS, immediately before the first socket write.
                    value = (
                        b"Bearer " + marker
                        if endpoint.header == "authorization"
                        else marker
                    )
                    headers = [
                        (b"host", f"{endpoint.host}:{endpoint.port}".encode("ascii")),
                        (endpoint.header.encode("ascii"), value),
                        (b"content-type", b"application/json"),
                        (b"accept-encoding", b"identity"),
                        (b"content-length", str(len(encoded)).encode("ascii")),
                    ]
                    if time.time() >= endpoint.expires_at:
                        raise CredentialBoundaryError("Network approval expired")
                    backend = _PinnedBackend(endpoint, authorize, marker)
                    async with httpcore2.AsyncConnectionPool(
                        ssl_context=self._tls,
                        network_backend=backend,
                        retries=0,
                        max_connections=1,
                        max_keepalive_connections=0,
                        http2=False,
                    ) as pool:
                        url = (
                            f"{endpoint.scheme}://{endpoint.host}:{endpoint.port}"
                            + endpoint.operations[operation]
                        )
                        async with pool.stream(
                            "POST", url, headers=headers, content=encoded
                        ) as response:
                            if response.status != 200:
                                raise ValueError(
                                    "unsuccessful response; redirects forbidden"
                                )
                            if any(
                                key.lower() == b"content-encoding"
                                and value != b"identity"
                                for key, value in response.headers
                            ):
                                raise ValueError("encoded responses unsupported")
                            body = bytearray()
                            async for block in response.aiter_stream():
                                if len(body) + len(block) > MAX_BYTES:
                                    raise ValueError("response limit")
                                body.extend(block)
                            result = _JSON.validate_json(bytes(body))
                            # Reject even an approved server echoing authentication.
                            decoded = json.dumps(result, ensure_ascii=False)
                            if any(secret in decoded for secret in seen):
                                raise ValueError("credential echoed by destination")
        except Exception:
            result = None
        # Raise outside the exception handler: no native response/exception chain
        # survives on the public failure, including through __context__.
        if result is None:
            raise ProviderError("Credentialed network exchange failed")
        return result
