"""Endpoint-bound HTTP with DNS pinning and pre-decoding byte limits."""

import asyncio
import ipaddress
import os
import re
import socket
import ssl
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Annotated, Any, Literal, Self, cast

import anyio
import certifi
import httpcore2
import httpx2
from pydantic import Field, SecretStr, model_validator

from mos_eisley.core.models import Contract


class MCPHTTPError(httpx2.StreamError):
    """Fixed-text diagnostic containing no credentials or payloads."""


class MCPHTTPSettings(Contract):
    url: Annotated[str, Field(min_length=1, max_length=4096)]
    authentication: Literal["bearer", "none"]
    token_env: (
        Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")] | None
    ) = None
    token_owner_uid: Annotated[int, Field(ge=0)] | None = None
    allow_loopback_http: bool = False
    private_networks: Annotated[tuple[str, ...], Field(max_length=16)] = ()
    ca_file: Annotated[str, Field(max_length=4096)] | None = None
    max_response_bytes: Annotated[int, Field(ge=1024, le=1048576)] = 262144

    @model_validator(mode="after")
    def valid_endpoint(self) -> Self:
        url = self.endpoint
        if (
            url.scheme not in {"https", "http"}
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
            or "%" in url.host
            or any(ord(char) < 33 for char in self.url)
        ):
            raise ValueError("invalid MCP endpoint URL")
        if url.scheme == "http":
            try:
                loopback = ipaddress.ip_address(url.host).is_loopback
            except ValueError:
                loopback = False
            if not self.allow_loopback_http or not loopback:
                raise ValueError("HTTP requires an explicit literal-loopback exception")
        elif self.allow_loopback_http:
            raise ValueError("loopback HTTP exception is only valid for HTTP")
        if self.authentication == "bearer":
            if self.token_env is None:
                raise ValueError("bearer authentication requires a token reference")
        elif self.token_env is not None or self.token_owner_uid is not None:
            raise ValueError("anonymous authentication cannot contain token references")
        for cidr in self.private_networks:
            network = ipaddress.ip_network(cidr, strict=True)
            if (
                not network.is_private
                or network.is_link_local
                or (network.is_reserved and not network.is_loopback)
            ):
                raise ValueError("private network grants must name private CIDRs")
        if self.ca_file is not None and not Path(self.ca_file).is_absolute():
            raise ValueError("CA file must be an absolute path")
        return self

    @property
    def endpoint(self) -> httpx2.URL:
        try:
            return httpx2.URL(self.url)
        except httpx2.InvalidURL:
            raise ValueError("invalid MCP endpoint URL") from None

    def allows_address(self, address: str) -> bool:
        ip = ipaddress.ip_address(address)
        if isinstance(ip, ipaddress.IPv6Address) and (
            ip.ipv4_mapped is not None
            or ip.sixtofour is not None
            or ip.teredo is not None
        ):
            return False
        if (
            ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or (ip.is_reserved and not ip.is_loopback)
        ):
            return False
        if self.endpoint.scheme == "http":
            return self.allow_loopback_http and ip == ipaddress.ip_address(
                self.endpoint.host
            )
        return ip.is_global or any(
            ip in ipaddress.ip_network(cidr) for cidr in self.private_networks
        )

    def token(self) -> SecretStr | None:
        if self.authentication == "none":
            return None
        if self.token_owner_uid is not None and self.token_owner_uid != os.geteuid():
            raise MCPHTTPError("MCP credential owner does not match this process")
        assert self.token_env is not None
        value = os.environ.get(self.token_env, "")
        if len(value) > 8192 or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", value):
            raise MCPHTTPError("MCP token reference is missing or invalid")
        return SecretStr(value)


class PinnedMCPBackend(httpcore2.AsyncNetworkBackend):
    """Resolve once, connect to a literal IP, retain origin Host/TLS identity."""

    def __init__(self, settings: MCPHTTPSettings) -> None:
        self.settings = settings
        self.backend = cast(httpcore2.AsyncNetworkBackend, httpcore2.AnyIOBackend())

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        endpoint = self.settings.endpoint
        expected_port = endpoint.port or (443 if endpoint.scheme == "https" else 80)
        if host != endpoint.raw_host.decode("ascii") or port != expected_port:
            raise MCPHTTPError("MCP destination is not approved")
        async with asyncio.timeout(timeout):
            answers = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            addresses = tuple(dict.fromkeys(str(answer[4][0]) for answer in answers))
            if not addresses or any(
                not self.settings.allows_address(ip) for ip in addresses
            ):
                raise MCPHTTPError("MCP DNS result is outside approved networks")
            # No second hostname resolution or alternate-address retry.
            return await self.backend.connect_tcp(
                addresses[0],
                port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise MCPHTTPError("MCP HTTP cannot access Unix sockets")

    async def sleep(self, seconds: float) -> None:
        raise MCPHTTPError("MCP HTTP connection retries are disabled")


class LimitedMCPStream(httpx2.AsyncByteStream):
    def __init__(self, response: httpcore2.Response, owner: "MCPHTTPTransport") -> None:
        self.response = response
        self.owner = owner

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = 0
        try:
            async for chunk in self.response.aiter_stream():
                size += len(chunk)
                if size > self.owner.settings.max_response_bytes:
                    raise MCPHTTPError("MCP HTTP response exceeds the byte limit")
                yield chunk
        except asyncio.CancelledError:
            self.owner.failed = True
            raise
        except Exception:
            self.owner.failed = True
            raise MCPHTTPError(
                "MCP HTTP response failed; inspect submitted writes"
            ) from None
        finally:
            await self.response.aclose()

    async def aclose(self) -> None:
        await self.response.aclose()


class MCPHTTPTransport(httpx2.AsyncBaseTransport):
    """One controller/user/endpoint token binding; no redirects or resumptions."""

    def __init__(self, settings: MCPHTTPSettings) -> None:
        self.settings = MCPHTTPSettings.model_validate_json(settings.model_dump_json())
        self._token = self.settings.token()
        self._owner = os.geteuid()
        self.failed = False
        context = ssl.create_default_context(
            cafile=self.settings.ca_file or certifi.where()
        )
        self.pool = httpcore2.AsyncConnectionPool(
            ssl_context=context,
            network_backend=PinnedMCPBackend(self.settings),
            retries=0,
            max_connections=2,
            max_keepalive_connections=2,
            http2=False,
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if self.failed or self._owner != os.geteuid():
            raise MCPHTTPError("MCP HTTP connection is unavailable")
        if (
            request.url != self.settings.endpoint
            or request.method not in {"POST", "GET", "DELETE"}
            or "last-event-id" in request.headers
        ):
            self.failed = True
            raise MCPHTTPError("MCP request destination or resumption is not permitted")
        request.headers.pop("authorization", None)
        request.headers.pop("cookie", None)
        request.headers["accept-encoding"] = "identity"
        request.headers["host"] = self.settings.endpoint.netloc.decode("ascii")
        if self._token is not None:
            request.headers["authorization"] = (
                "Bearer " + self._token.get_secret_value()
            )
        assert isinstance(request.stream, httpx2.AsyncByteStream)
        response: httpcore2.Response | None = None
        try:
            response = await self.pool.handle_async_request(
                httpcore2.Request(
                    method=request.method,
                    url=httpcore2.URL(
                        scheme=request.url.raw_scheme,
                        host=request.url.raw_host,
                        port=request.url.port,
                        target=request.url.raw_path,
                    ),
                    headers=request.headers.raw,
                    content=request.stream,
                    extensions=request.extensions,
                )
            )
            headers = httpx2.Headers(response.headers)
            if 300 <= response.status < 400:
                raise MCPHTTPError(
                    "MCP redirects are not permitted; configure the final endpoint"
                )
            if headers.get("content-encoding", "identity").lower() != "identity":
                raise MCPHTTPError("compressed MCP responses are unsupported")
            length = headers.get("content-length")
            if length is not None and (
                not length.isdecimal() or int(length) > self.settings.max_response_bytes
            ):
                raise MCPHTTPError("MCP HTTP response exceeds the byte limit")
            return httpx2.Response(
                status_code=response.status,
                headers=headers,
                stream=LimitedMCPStream(response, self),
            )
        except asyncio.CancelledError:
            self.failed = True
            if response is not None:
                await response.aclose()
            raise
        except Exception:
            self.failed = True
            if response is not None:
                await response.aclose()
            raise MCPHTTPError(
                "MCP HTTP request failed; inspect submitted writes"
            ) from None

    async def aclose(self) -> None:
        self.failed = True
        self._token = None
        await self.pool.aclose()


class MCPHTTPClient(httpx2.AsyncClient):
    """Turn transport failures into one failed MCP response, never a retry.

    The SDK's request task group otherwise cancels its caller on errors raised
    before response headers arrive. A fixed 502 lets it resolve the corresponding
    JSON-RPC request as an error while preserving user cancellation separately.
    """

    async def send(
        self,
        request: httpx2.Request,
        *,
        stream: bool = False,
        auth: Any = httpx2.USE_CLIENT_DEFAULT,
        follow_redirects: Any = httpx2.USE_CLIENT_DEFAULT,
    ) -> httpx2.Response:
        try:
            return await super().send(
                request,
                stream=stream,
                auth=auth,
                follow_redirects=follow_redirects,
            )
        except MCPHTTPError:
            return httpx2.Response(
                502,
                json={"error": "MCP transport failed; inspect submitted writes"},
                request=request,
            )
