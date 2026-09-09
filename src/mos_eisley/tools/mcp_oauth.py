"""Explicit OAuth controller: discovery, PKCE, keychain lifecycle, no call retries."""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2
from mcp.client.auth.utils import (
    build_protected_resource_metadata_discovery_urls,
    extract_resource_metadata_from_www_auth,
    extract_scope_from_www_auth,
)
from pydantic import Field, SecretStr

from mos_eisley.core.models import Contract
from mos_eisley.tools.mcp_http import (
    MCPHTTPSettings,
    MCPHTTPTransport,
    PinnedMCPBackend,
)
from mos_eisley.tools.mcp_oauth_store import OAuthFailure, OAuthStore


class OAuthRecord(Contract):
    binding: str
    access_token: Annotated[
        str, Field(pattern=r"^[A-Za-z0-9._~+/-]+=*$", max_length=8192)
    ]
    refresh_token: Annotated[str, Field(max_length=8192)] | None = None
    expires_at: Annotated[float, Field(allow_inf_nan=False)]
    token_endpoint: str
    revocation_endpoint: str | None = None
    scopes: tuple[str, ...]


def origin(url: str) -> str:
    parsed = httpx2.URL(url)
    return f"{parsed.scheme}://{parsed.netloc.decode('ascii')}"


class OAuthController:
    def __init__(self, settings: MCPHTTPSettings) -> None:
        self.settings = MCPHTTPSettings.model_validate_json(settings.model_dump_json())
        if self.settings.oauth is None:
            raise OAuthFailure("OAuth configuration is required")
        self.oauth = self.settings.oauth
        self.resource = str(self.settings.endpoint)
        binding = json.dumps(
            {
                "uid": os.geteuid(),
                "resource": self.resource,
                "issuer": self.oauth.issuer,
                "client": self.oauth.client_id,
                "account": self.oauth.account,
                "scopes": self.oauth.scopes,
            },
            sort_keys=True,
        )
        self.binding = hashlib.sha256(binding.encode()).hexdigest()
        self.auth_origins = {
            origin(self.oauth.issuer),
            *self.oauth.allowed_auth_origins,
        }
        for value in self.auth_origins:
            if origin(value) != value:
                raise OAuthFailure("OAuth authorization grants must be origins")
            self.endpoint_settings(value, auth=True)
        self.endpoint_settings(self.oauth.issuer, auth=True)
        self.store = OAuthStore(self.binding)

    def endpoint_settings(self, url: str, *, auth: bool) -> MCPHTTPSettings:
        allowed = self.auth_origins if auth else {origin(self.resource)}
        if origin(url) not in allowed:
            raise OAuthFailure("OAuth destination is not approved")
        return MCPHTTPSettings(
            url=url,
            authentication="none",
            private_networks=self.settings.private_networks,
            ca_file=self.settings.ca_file,
            max_response_bytes=65536,
            allow_loopback_http=self.settings.allow_loopback_http
            and url.startswith("http:"),
        )

    async def request(
        self,
        url: str,
        *,
        auth: bool,
        data: dict[str, str] | None = None,
    ) -> httpx2.Response:
        target = self.endpoint_settings(url, auth=auth)
        try:
            async with (
                asyncio.timeout(15),
                httpx2.AsyncClient(
                    transport=MCPHTTPTransport(target),
                    timeout=10,
                    trust_env=False,
                    follow_redirects=False,
                ) as client,
            ):
                if data is None:
                    return await client.get(url)
                return await client.post(url, data=data)
        except Exception:
            raise OAuthFailure(
                "OAuth endpoint failed; authenticate again explicitly"
            ) from None

    async def document(self, urls: list[str], *, auth: bool) -> dict[str, Any]:
        for url in dict.fromkeys(urls):
            response = await self.request(url, auth=auth)
            if response.status_code == 404:
                continue
            if response.status_code != 200:
                raise OAuthFailure("OAuth discovery failed")
            try:
                value: Any = response.json()
                if not isinstance(value, dict):
                    raise ValueError
                return cast(dict[str, Any], value)
            except Exception:
                raise OAuthFailure("OAuth metadata is invalid") from None
        raise OAuthFailure("OAuth metadata is unavailable")

    async def discover(self) -> dict[str, Any]:
        probe = await self.request(self.resource, auth=False)
        hint = extract_resource_metadata_from_www_auth(probe)
        urls = build_protected_resource_metadata_discovery_urls(hint, self.resource)
        resource = await self.document(urls, auth=False)
        if resource.get(
            "resource"
        ) != self.resource or self.oauth.issuer not in resource.get(
            "authorization_servers", []
        ):
            raise OAuthFailure("OAuth resource or issuer does not match configuration")
        required = extract_scope_from_www_auth(probe)
        if required is not None and not set(required.split()).issubset(
            self.oauth.scopes
        ):
            raise OAuthFailure("OAuth scopes require explicit configuration and login")
        issuer = urlsplit(self.oauth.issuer)
        base = origin(self.oauth.issuer)
        path = issuer.path.rstrip("/")
        metadata = await self.document(
            [
                base + "/.well-known/oauth-authorization-server" + path,
                base + "/.well-known/openid-configuration" + path,
                self.oauth.issuer.rstrip("/") + "/.well-known/openid-configuration",
            ],
            auth=True,
        )
        if metadata.get("issuer") != self.oauth.issuer:
            raise OAuthFailure("OAuth issuer metadata mismatch")
        if "S256" not in metadata.get("code_challenge_methods_supported", []):
            raise OAuthFailure("OAuth server must support PKCE S256")
        if "code" not in metadata.get("response_types_supported", []):
            raise OAuthFailure("OAuth server must support authorization codes")
        if "none" not in metadata.get("token_endpoint_auth_methods_supported", []):
            raise OAuthFailure("OAuth requires a pre-registered public client")
        for field in (
            "authorization_endpoint",
            "token_endpoint",
            "revocation_endpoint",
        ):
            value = metadata.get(field)
            if value is None and field == "revocation_endpoint":
                continue
            if not isinstance(value, str):
                raise OAuthFailure("OAuth endpoint metadata is invalid")
            self.endpoint_settings(value, auth=True)
        return metadata

    def token_record(
        self,
        response: httpx2.Response,
        metadata: dict[str, Any],
        previous: OAuthRecord | None = None,
    ) -> OAuthRecord:
        try:
            if response.status_code != 200:
                raise ValueError
            body = response.json()
            if body.get("token_type", "").lower() != "bearer":
                raise ValueError
            if (
                body.get("resource", self.resource) != self.resource
                or body.get("iss", self.oauth.issuer) != self.oauth.issuer
            ):
                raise ValueError
            scopes = tuple(body.get("scope", " ".join(self.oauth.scopes)).split())
            if set(scopes) != set(self.oauth.scopes):
                raise ValueError
            lifetime = body["expires_in"]
            if type(lifetime) is not int or not 0 < lifetime <= 31536000:
                raise ValueError
            return OAuthRecord(
                binding=self.binding,
                access_token=body["access_token"],
                refresh_token=body.get(
                    "refresh_token", previous.refresh_token if previous else None
                ),
                expires_at=time.time() + lifetime,
                token_endpoint=metadata["token_endpoint"],
                revocation_endpoint=metadata.get("revocation_endpoint"),
                scopes=scopes,
            )
        except Exception:
            raise OAuthFailure(
                "OAuth token exchange rejected; login is required"
            ) from None

    async def login(self, show_url: Callable[[str], Awaitable[None]]) -> None:
        async with (
            asyncio.timeout(self.oauth.login_timeout_seconds),
            self.store.locked(),
        ):
            await self.store.delete()
            metadata = await self.discover()
            verifier = secrets.token_urlsafe(48)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            state = secrets.token_urlsafe(32)
            # Check the browser destination's current DNS policy too. Browser DNS and
            # provider login-page redirects remain outside this controller's sockets.
            endpoint = self.endpoint_settings(
                metadata["authorization_endpoint"], auth=True
            )
            stream = await PinnedMCPBackend(endpoint).connect_tcp(
                endpoint.endpoint.raw_host.decode("ascii"),
                endpoint.endpoint.port
                or (443 if endpoint.endpoint.scheme == "https" else 80),
                timeout=10,
            )
            await stream.aclose()
            async with OAuthCallback(
                self.oauth.callback_port,
                state,
                self.oauth.issuer,
                metadata.get("authorization_response_iss_parameter_supported") is True,
            ) as callback:
                url = (
                    metadata["authorization_endpoint"]
                    + "?"
                    + urlencode(
                        {
                            "response_type": "code",
                            "client_id": self.oauth.client_id,
                            "redirect_uri": self.oauth.redirect_uri,
                            "scope": " ".join(self.oauth.scopes),
                            "resource": self.resource,
                            "state": state,
                            "code_challenge": challenge,
                            "code_challenge_method": "S256",
                        }
                    )
                )
                await show_url(url)
                code = await callback.code
            response = await self.request(
                metadata["token_endpoint"],
                auth=True,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.oauth.client_id,
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": self.oauth.redirect_uri,
                    "resource": self.resource,
                },
            )
            record = self.token_record(response, metadata)
            await self.store.set(record.model_dump_json())

    def parse_record(self, raw: str) -> OAuthRecord:
        try:
            record = OAuthRecord.model_validate_json(raw)
            if record.binding != self.binding or set(record.scopes) != set(
                self.oauth.scopes
            ):
                raise ValueError
            return record
        except Exception:
            raise OAuthFailure(
                "OAuth stored identity is invalid; login is required"
            ) from None

    async def access_token(self) -> SecretStr:
        async with self.store.locked():
            raw = await self.store.get()
            if raw is None:
                raise OAuthFailure("OAuth login is required")
            record = self.parse_record(raw)
            if record.expires_at <= time.time() + 30:
                # Delete before sending: a lost refresh response must not reuse a
                # potentially rotated refresh token on a later invocation.
                await self.store.delete()
                if not record.refresh_token:
                    raise OAuthFailure("OAuth token expired; login is required")
                response = await self.request(
                    record.token_endpoint,
                    auth=True,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": record.refresh_token,
                        "client_id": self.oauth.client_id,
                        "resource": self.resource,
                        "scope": " ".join(self.oauth.scopes),
                    },
                )
                record = self.token_record(
                    response,
                    {
                        "token_endpoint": record.token_endpoint,
                        "revocation_endpoint": record.revocation_endpoint,
                    },
                    record,
                )
                await self.store.set(record.model_dump_json())
            return SecretStr(record.access_token)

    async def invalidate(self) -> None:
        async with self.store.locked():
            await self.store.delete()

    async def logout(self) -> dict[str, Any]:
        async with self.store.locked():
            raw = await self.store.get()
            await self.store.delete()
            result: dict[str, Any] = {
                "local_credentials_removed": True,
                "revocation": "not_available",
            }
            if raw is None:
                result["revocation"] = "no_credentials"
                return result
            record = self.parse_record(raw)
            if record.revocation_endpoint:
                result["revocation"] = "provider_accepted"
                for token, hint in (
                    (record.refresh_token, "refresh_token"),
                    (record.access_token, "access_token"),
                ):
                    if token is None:
                        continue
                    try:
                        response = await self.request(
                            record.revocation_endpoint,
                            auth=True,
                            data={
                                "token": token,
                                "token_type_hint": hint,
                                "client_id": self.oauth.client_id,
                            },
                        )
                        if response.status_code != 200:
                            result["revocation"] = "failed_or_incomplete"
                    except Exception:
                        result["revocation"] = "failed_or_incomplete"
            return result


class OAuthCallback:
    def __init__(
        self, port: int, state: str, issuer: str, require_issuer: bool
    ) -> None:
        self.port, self.state, self.issuer = port, state, issuer
        self.require_issuer = require_issuer
        self.code: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self.tasks: set[asyncio.Task[None]] = set()
        self.server: asyncio.Server | None = None

    async def __aenter__(self) -> "OAuthCallback":
        self.server = await asyncio.start_server(
            self.accept, "127.0.0.1", self.port, limit=8192
        )
        return self

    def accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.create_task(self.handle(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        status = "400 Bad Request"
        try:
            async with asyncio.timeout(5):
                head = (await reader.readuntil(b"\r\n\r\n")).decode("ascii")
                lines = head.split("\r\n")
                method, target, version = lines[0].split(" ")
                headers = [line.split(":", 1) for line in lines[1:] if line]
                hosts = [
                    value.strip() for key, value in headers if key.lower() == "host"
                ]
                parsed = urlsplit(target)
                values = parse_qs(
                    parsed.query,
                    keep_blank_values=True,
                    strict_parsing=True,
                    max_num_fields=12,
                )
                if (
                    method != "GET"
                    or version != "HTTP/1.1"
                    or parsed.scheme
                    or parsed.netloc
                    or parsed.path != "/oauth/callback"
                    or parsed.fragment
                    or hosts != [f"127.0.0.1:{self.port}"]
                    or self.code.done()
                    or any(len(v) != 1 for v in values.values())
                    or not secrets.compare_digest(
                        values.get("state", [""])[0], self.state
                    )
                ):
                    raise ValueError
                supplied = values.get("iss", [None])[0]
                if (supplied is not None and supplied != self.issuer) or (
                    self.require_issuer and supplied is None
                ):
                    raise ValueError
                if "error" in values:
                    self.code.set_exception(
                        OAuthFailure("OAuth authorization was denied")
                    )
                else:
                    code = values["code"][0]
                    if not code or len(code) > 4096:
                        raise ValueError
                    self.code.set_result(code)
                status = "200 OK"
        except Exception:
            pass
        finally:
            writer.write(
                (
                    f"HTTP/1.1 {status}\r\nContent-Length: 0\r\n"
                    "Cache-Control: no-store\r\nConnection: close\r\n\r\n"
                ).encode()
            )
            writer.close()
            await writer.wait_closed()

    async def __aexit__(self, *_: object) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if not self.code.done():
            self.code.cancel()
        elif not self.code.cancelled():
            self.code.exception()
