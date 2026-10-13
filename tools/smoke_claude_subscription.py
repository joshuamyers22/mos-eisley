"""Native Claude protocol/control fixture, with synthetic API auth and loopback only."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from pydantic import JsonValue, TypeAdapter

from mos_eisley.core.protocol import ModelRequest, TextBlock, Turn
from mos_eisley.providers import claude_subscription as adapter
from mos_eisley.providers import codex_subscription as native


async def qualify(client: Path) -> dict[str, JsonValue]:
    observed: dict[str, JsonValue] = {"requests": 0, "auth_is_fixture": False}

    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            count = observed["requests"]
            assert isinstance(count, int)
            observed["requests"] = count + 1
            auth = (
                self.headers.get("x-api-key") == "fixture-only"
                and self.headers.get("Authorization") is None
            )
            observed["auth_is_fixture"] = auth
            size = int(self.headers.get("Content-Length", "0"))
            if (
                self.path.split("?")[0] != "/v1/messages"
                or count != 0
                or not auth
                or not 0 < size <= 1_000_000
            ):
                self.send_error(403)
                return
            request = TypeAdapter[dict[str, JsonValue]](
                dict[str, JsonValue]
            ).validate_json(self.rfile.read(size))
            observed["empty_tool_inventory"] = request.get("tools", []) == []
            observed["requested_model_preserved"] = (
                request.get("model") == "claude-sonnet-5"
            )
            config = request.get("output_config")
            observed["requested_effort_preserved"] = (
                isinstance(config, dict) and config.get("effort") == "high"
            )
            message: dict[str, JsonValue] = {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            }
            events: list[dict[str, JsonValue]] = [
                {"type": "message_start", "message": message},
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Offline fixture response"},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 5},
                },
                {"type": "message_stop"},
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(
                "".join(
                    "event: "
                    + str(event["type"])
                    + "\ndata: "
                    + json.dumps(event)
                    + "\n\n"
                    for event in events
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    original = native.invoke

    async def fixture_invoke(
        executable: Path,
        arguments: tuple[str, ...],
        cwd: Path,
        *,
        data: bytes = b"",
        timeout: float = 15,
        output_limit: int = native.MAX_EVENTS,
    ) -> tuple[int, bytes, bytes]:
        if arguments == ("auth", "status"):
            return (
                0,
                b'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty"}',
                b"",
            )
        if "--print" in arguments:
            arguments = (*arguments, "--bare")
        code, raw, diagnostic = await original(
            executable,
            arguments,
            cwd,
            data=data,
            timeout=timeout,
            output_limit=output_limit,
        )
        # On failure report event types/keys only, never native text or headers.
        if code != 0:
            observed["native_exit"] = code
        kinds: list[JsonValue] = []
        for line in raw.splitlines():
            try:
                event = json.loads(line)
                kinds.append(str(event.get("type")))
            except ValueError:
                pass
        observed["event_types"] = kinds
        return code, raw, diagnostic

    try:
        with (
            tempfile.TemporaryDirectory(prefix="mos-claude-contract-") as directory,
            patch.dict(
                os.environ,
                {
                    "ANTHROPIC_API_KEY": "fixture-only",
                    "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "DISABLE_AUTOUPDATER": "1",
                },
            ),
            patch.object(
                native,
                "CLIENT_ENVIRONMENT",
                native.CLIENT_ENVIRONMENT
                | {
                    "ANTHROPIC_API_KEY",
                    "ANTHROPIC_BASE_URL",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
                    "DISABLE_AUTOUPDATER",
                },
            ),
            patch.object(adapter, "invoke", fixture_invoke),
        ):
            client_adapter = adapter.ClaudeSubscriptionClient(
                client,
                Path(directory) / "attempt",
                allow_data_transfer=True,
                allow_subscription_usage=True,
                timeout=30,
            )
            result = await client_adapter.complete(
                ModelRequest(
                    provider=adapter.PROVIDER,
                    model="claude-sonnet-5",
                    effort="high",
                    turns=(
                        Turn(
                            role="user",
                            blocks=(TextBlock(text="Offline fixture request"),),
                        ),
                    ),
                    max_output=4000,
                )
            )
            observed["native_turn_completed"] = result.stop_reason == "end_turn"
        checks = (
            "auth_is_fixture",
            "empty_tool_inventory",
            "requested_model_preserved",
            "requested_effort_preserved",
            "native_turn_completed",
        )
        if observed["requests"] != 1 or not all(observed.get(key) for key in checks):
            raise ValueError("Claude native fixture assertions failed")
        return observed
    except Exception:
        print(json.dumps(observed))
        raise
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(qualify(native.select_client(args.client)))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
