"""Real HTTP/TLS MCP fixture with controlled failures and synthetic tokens."""

import asyncio
import json
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server import MCPServer
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class MCPHTTPFixture:
    def __init__(
        self,
        *,
        sse: bool = False,
        cert: Path | None = None,
        key: Path | None = None,
        middleware: Callable[[ASGIApp], ASGIApp] | None = None,
    ) -> None:
        self.fault = ""
        self.legacy_version: str | None = None
        self.tokens: set[str] | None = {"fixture-A", "fixture-B"}
        self.requests: list[tuple[str, str]] = []
        self.writes = 0
        self.value = 0
        self.redirect = "https://unapproved.invalid/mcp"
        self.cancelled = threading.Event()
        server: MCPServer[Any] = MCPServer("remote-fixture", log_level="ERROR")

        def read_value() -> dict[str, int]:
            return {"value": self.value, "writes": self.writes}

        def write_value(value: int) -> dict[str, int]:
            self.writes += 1
            self.value = value
            return {"value": value}

        async def slow() -> str:
            try:
                await asyncio.sleep(20)
                return "late"
            finally:
                self.cancelled.set()

        server.add_tool(read_value)
        server.add_tool(write_value)
        server.add_tool(slow)
        app = server.streamable_http_app(json_response=not sse)

        async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await app(scope, receive, send)
                return
            headers = dict(scope["headers"])
            auth = headers.get(b"authorization", b"").decode()
            body = b""
            while True:
                message = await receive()
                body += message.get("body", b"")
                if not message.get("more_body", False):
                    break
            request: dict[str, Any] = json.loads(body) if body else {}
            method = request.get("method", scope["method"])
            self.requests.append((method, auth))
            if self.tokens is not None and auth not in {
                "Bearer " + token for token in self.tokens
            }:
                await reply(
                    send, 401, b"unauthorized", [(b"www-authenticate", b"Bearer")]
                )
                return
            if self.legacy_version is not None:
                if method == "server/discover":
                    await reply(send, 404, b"missing")
                    return
                if method == "initialize":
                    request["params"]["protocolVersion"] = self.legacy_version
                    body = json.dumps(request).encode()
            if self.fault == "redirect":
                await reply(send, 307, b"", [(b"location", self.redirect.encode())])
                return
            if self.fault.startswith("version"):
                if method == "server/discover":
                    await reply(send, 404, b"missing")
                    return
                if method == "initialize":
                    version = self.fault.removeprefix("version-")
                    result: dict[str, Any] = {
                        "protocolVersion": version,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fixture", "version": "1"},
                    }
                    await reply(
                        send,
                        200,
                        json.dumps(
                            {"jsonrpc": "2.0", "id": request["id"], "result": result}
                        ).encode(),
                    )
                    return
            if method == "tools/call":
                if self.fault == "oversized_json":
                    await reply(send, 200, b"x" * 300000)
                    return
                if self.fault == "oversized_sse":
                    await reply(
                        send,
                        200,
                        b"data: " + b"x" * 300000,
                        [(b"content-type", b"text/event-stream")],
                        length=False,
                    )
                    return
                if self.fault == "compressed":
                    await reply(
                        send,
                        200,
                        b"invalid compressed bytes",
                        [(b"content-encoding", b"gzip")],
                    )
                    return
                if self.fault == "malformed":
                    await reply(send, 200, b"PRIVATE_REMOTE_FIXTURE_VALUE")
                    return
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body}
                return await receive()

            async def output(message: Message) -> None:
                if self.fault == "commit_drop" and method == "tools/call":
                    if message["type"] == "http.response.start":
                        message = {
                            **message,
                            "headers": [(b"content-type", b"application/json")],
                        }
                    if message["type"] == "http.response.body":
                        message = {**message, "body": b""}
                await send(message)

            await app(scope, replay, output)

        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.url = f"{'https' if cert else 'http'}://127.0.0.1:{self.socket.getsockname()[1]}/mcp"
        self.server = uvicorn.Server(
            uvicorn.Config(
                middleware(wrapped) if middleware else wrapped,
                log_level="critical",
                lifespan="on",
                timeout_graceful_shutdown=1,
                ssl_certfile=str(cert) if cert else None,
                ssl_keyfile=str(key) if key else None,
            )
        )
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True
        )

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                self.close()
                raise RuntimeError("MCP fixture failed to start")
            time.sleep(0.01)

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(5)
        self.socket.close()
        if self.thread.is_alive():
            raise RuntimeError("MCP fixture failed to stop")


async def reply(
    send: Send,
    status: int,
    body: bytes,
    headers: list[tuple[bytes, bytes]] | None = None,
    *,
    length: bool = True,
) -> None:
    values = headers or []
    if not any(key == b"content-type" for key, _ in values):
        values = [*values, (b"content-type", b"application/json")]
    if length:
        values = [*values, (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": values})
    # Separate chunks exercise bounds without trusting Content-Length.
    for offset in range(0, len(body), 1024):
        await send(
            {
                "type": "http.response.body",
                "body": body[offset : offset + 1024],
                "more_body": True,
            }
        )
    await send({"type": "http.response.body", "body": b""})
