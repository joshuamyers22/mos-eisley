"""Qualify the installed client's tool inventory against a synthetic local backend.

This never uses a real provider, account token or subscription quota. It is a
native harness contract check; ChatGPT inference still needs separate admission.
"""

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
from mos_eisley.providers import codex_subscription as adapter

OBJECT = TypeAdapter(dict[str, JsonValue])


async def qualify(client: Path) -> dict[str, JsonValue]:
    observed: dict[str, JsonValue] = {"requests": 0, "auth_is_fixture": False}

    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            count = observed["requests"]
            assert isinstance(count, int)
            observed["requests"] = count + 1
            observed["auth_is_fixture"] = (
                self.headers.get("Authorization") == "Bearer fixture-only"
            )
            size = int(self.headers.get("Content-Length", "0"))
            if (
                self.path != "/v1/responses"
                or count != 0
                or not observed["auth_is_fixture"]
                or not 0 < size <= 1_000_000
            ):
                self.send_error(403)
                return
            request = OBJECT.validate_json(self.rfile.read(size))
            tools = request.get("tools", [])
            observed["empty_tool_inventory"] = tools == []
            observed["requested_model_preserved"] = request.get("model") == "gpt-6-sol"
            reasoning = request.get("reasoning")
            observed["requested_effort_preserved"] = (
                isinstance(reasoning, dict) and reasoning.get("effort") == "medium"
            )
            message: dict[str, JsonValue] = {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Offline fixture response",
                        "annotations": [],
                    }
                ],
            }
            response: dict[str, JsonValue] = {
                "id": "resp_fixture",
                "object": "response",
                "created_at": 0,
                "model": request["model"],
                "status": "completed",
                "output": [message],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 5,
                    "total_tokens": 25,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            }
            events: list[dict[str, JsonValue]] = [
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {**message, "status": "in_progress", "content": []},
                },
                {
                    "type": "response.output_text.delta",
                    "item_id": "msg_fixture",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": "Offline fixture response",
                },
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": message,
                },
                {"type": "response.completed", "response": response},
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(
                "".join(
                    "data: " + json.dumps(event) + "\n\n" for event in events
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    original = adapter.invoke

    async def fixture_invoke(
        executable: Path,
        arguments: tuple[str, ...],
        cwd: Path,
        *,
        data: bytes = b"",
        timeout: float = 15,
        output_limit: int = adapter.MAX_EVENTS,
    ) -> tuple[int, bytes, bytes]:
        if arguments == ("login", "status"):
            return 0, b"Logged in using ChatGPT", b""
        if "exec" in arguments:
            provider = (
                '{name="Fixture",wire_api="responses",requires_openai_auth=false,'
                'env_key="SUBSCRIPTION_FIXTURE_API_KEY",request_max_retries=0,'
                'stream_max_retries=0,base_url="http://127.0.0.1:'
                f'{server.server_port}/v1"}}'
            )
            arguments = (
                *arguments[:-1],
                "-c",
                'forced_login_method="api"',
                "-c",
                'cli_auth_credentials_store="ephemeral"',
                "-c",
                'model_provider="fixture"',
                "-c",
                "model_providers.fixture=" + provider,
                "-",
            )
        return await original(
            executable,
            arguments,
            cwd,
            data=data,
            timeout=timeout,
            output_limit=output_limit,
        )

    try:
        with (
            tempfile.TemporaryDirectory(prefix="mos-native-contract-") as directory,
            patch.dict(
                os.environ,
                {
                    "SUBSCRIPTION_FIXTURE_API_KEY": "fixture-only",
                    "OPENAI_API_KEY": "fixture-only",
                },
            ),
            patch.object(
                adapter,
                "CLIENT_ENVIRONMENT",
                adapter.CLIENT_ENVIRONMENT
                | {"SUBSCRIPTION_FIXTURE_API_KEY", "OPENAI_API_KEY"},
            ),
            patch.object(adapter, "invoke", fixture_invoke),
        ):
            selected = adapter.CodexSubscriptionClient(
                client,
                Path(directory) / "attempt",
                allow_data_transfer=True,
                allow_subscription_usage=True,
                timeout=30,
            )
            result = await selected.complete(
                ModelRequest(
                    provider=adapter.PROVIDER,
                    model="gpt-6-sol",
                    effort="medium",
                    turns=(
                        Turn(
                            role="user",
                            blocks=(TextBlock(text="Offline fixture turn"),),
                        ),
                    ),
                    max_output=4000,
                )
            )
            observed["native_turn_completed"] = result.stop_reason == "end_turn"
        if observed["requests"] != 1 or not all(observed.values()):
            raise ValueError("Native fixture contract failed: " + json.dumps(observed))
        return observed
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(qualify(adapter.select_client(args.client)))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
