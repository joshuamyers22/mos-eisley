"""OAuth authorization/resource fixture with real MCP and synthetic credentials."""

import asyncio
import base64
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import parse_qs, urlencode

from fixtures.mcp_http_server import MCPHTTPFixture, reply
from starlette.types import ASGIApp, Receive, Scope, Send


class OAuthFixture:
    def __init__(self) -> None:
        self.fault = ""
        self.codes: dict[str, dict[str, str]] = {}
        self.refresh_tokens: set[str] = set()
        self.refreshes = 0
        self.exchanges = 0
        self.revocations = 0
        self.auth_requests: list[str] = []
        self.http = MCPHTTPFixture(middleware=self.middleware)
        self.url = self.http.url
        self.issuer = self.url.removesuffix("/mcp")
        self.http.tokens = set()
        self.http.start()

    def close(self) -> None:
        self.http.close()

    def middleware(self, app: ASGIApp) -> ASGIApp:
        async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await app(scope, receive, send)
                return
            path = scope["path"]
            headers = dict(scope["headers"])
            if path == "/mcp" and scope["method"] != "GET":
                await app(scope, receive, send)
                return
            self.auth_requests.append(path)
            if headers.get(b"authorization"):
                raise AssertionError("resource access token leaked to OAuth endpoint")

            async def document(value: Any, status: int = 200) -> None:
                await reply(
                    send,
                    status,
                    json.dumps(value).encode(),
                    [(b"content-type", b"application/json")],
                )

            if path == "/mcp":
                metadata = self.issuer + "/.well-known/oauth-protected-resource"
                if self.fault == "evil_hint":
                    metadata = "http://169.254.169.254/metadata"
                await reply(
                    send,
                    401,
                    b"",
                    [
                        (
                            b"www-authenticate",
                            (
                                f'Bearer resource_metadata="{metadata}", scope="read"'
                            ).encode(),
                        )
                    ],
                )
            elif path.startswith("/.well-known/oauth-protected-resource"):
                await document(
                    {
                        "resource": self.url
                        + ("/wrong" if self.fault == "resource" else ""),
                        "authorization_servers": [self.issuer],
                        "scopes_supported": ["read", "write"],
                    }
                )
            elif path in {
                "/.well-known/oauth-authorization-server",
                "/.well-known/openid-configuration",
            }:
                if self.fault == "oidc" and path.endswith("oauth-authorization-server"):
                    await document({}, 404)
                    return
                if self.fault == "redirect_metadata":
                    await reply(
                        send, 302, b"", [(b"location", b"http://169.254.169.254/")]
                    )
                    return
                await document(
                    {
                        "issuer": self.issuer
                        + ("/wrong" if self.fault == "issuer" else ""),
                        "authorization_endpoint": self.issuer + "/authorize",
                        "token_endpoint": "https://unapproved.invalid/token"
                        if self.fault == "evil_token"
                        else self.issuer + "/token",
                        "revocation_endpoint": self.issuer + "/revoke",
                        "response_types_supported": ["code"],
                        "token_endpoint_auth_methods_supported": ["none"],
                        "code_challenge_methods_supported": []
                        if self.fault == "pkce"
                        else ["S256"],
                        "authorization_response_iss_parameter_supported": True,
                    }
                )
            elif path == "/authorize":
                params = {
                    k: v[0] for k, v in parse_qs(scope["query_string"].decode()).items()
                }
                if (
                    params["resource"] != self.url
                    or params["code_challenge_method"] != "S256"
                ):
                    await document({}, 400)
                    return
                code = secrets.token_urlsafe(20)
                self.codes[code] = params
                response = {"state": params["state"], "iss": self.issuer, "code": code}
                if self.fault == "denied":
                    response = {
                        "state": params["state"],
                        "iss": self.issuer,
                        "error": "access_denied",
                    }
                await reply(
                    send,
                    302,
                    b"",
                    [
                        (
                            b"location",
                            (
                                params["redirect_uri"] + "?" + urlencode(response)
                            ).encode(),
                        )
                    ],
                )
            elif path in {"/token", "/revoke"}:
                body = b""
                while True:
                    message = await receive()
                    body += message.get("body", b"")
                    if not message.get("more_body", False):
                        break
                params = {k: v[0] for k, v in parse_qs(body.decode()).items()}
                if path == "/revoke":
                    self.revocations += 1
                    self.refresh_tokens.discard(params["token"])
                    assert self.http.tokens is not None
                    self.http.tokens.discard(params["token"])
                    await document({}, 503 if self.fault == "revocation" else 200)
                    return
                if params.get("resource") != self.url:
                    await document({}, 400)
                    return
                if params.get("grant_type") == "authorization_code":
                    self.exchanges += 1
                    original = self.codes.pop(params["code"], None)
                    challenge = (
                        base64.urlsafe_b64encode(
                            hashlib.sha256(params["code_verifier"].encode()).digest()
                        )
                        .rstrip(b"=")
                        .decode()
                    )
                    if (
                        original is None
                        or original["code_challenge"] != challenge
                        or original["client_id"] != params["client_id"]
                        or original["redirect_uri"] != params["redirect_uri"]
                    ):
                        await document({}, 400)
                        return
                else:
                    self.refreshes += 1
                    await asyncio.sleep(0.05)
                    if (
                        params["refresh_token"] not in self.refresh_tokens
                        or self.fault == "refresh_denied"
                    ):
                        await document({}, 400)
                        return
                    self.refresh_tokens.remove(params["refresh_token"])
                token, refresh = secrets.token_urlsafe(20), secrets.token_urlsafe(20)
                assert self.http.tokens is not None
                self.http.tokens.add(token)
                self.refresh_tokens.add(refresh)
                if self.fault == "refresh_drop":
                    await reply(send, 200, b"", [])
                    return
                await document(
                    {
                        "token_type": "Bearer",
                        "access_token": token,
                        "refresh_token": refresh,
                        "expires_in": 3600,
                        "scope": "admin" if self.fault == "scope" else "read write",
                        "resource": self.url
                        + ("/wrong" if self.fault == "token_resource" else ""),
                    }
                )
            else:
                await document({}, 404)

        return wrapped
