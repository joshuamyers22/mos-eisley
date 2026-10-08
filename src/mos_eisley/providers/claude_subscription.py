"""Exact-version tool-free Claude subscription transport; native-owned auth only."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock, Turn, Usage
from mos_eisley.providers.codex_subscription import (
    MAX_EVENTS,
    MAX_INPUT,
    invoke,
    new_attempt,
    write_receipt,
)
from mos_eisley.subscription_authorization import subscription_registry
from mos_eisley.tools.mcp_schema import compile_schema, valid_instance

CLIENT_VERSION = "2.1.283"
PROVIDER = "anthropic_subscription"
_OBJECT = TypeAdapter(dict[str, JsonValue])


async def status(executable: Path) -> dict[str, JsonValue]:
    with tempfile.TemporaryDirectory(prefix="mos-claude-status-") as directory:
        cwd = Path(directory)
        code, raw, _ = await invoke(executable, ("--version",), cwd, output_limit=4096)
        if code != 0 or raw.strip() != f"{CLIENT_VERSION} (Claude Code)".encode():
            return {"client_version_supported": False, "subscription_signed_in": False}
        code, raw, _ = await invoke(
            executable, ("auth", "status"), cwd, output_limit=4096
        )
        try:
            value = _OBJECT.validate_json(raw, strict=True)
            signed_in = (
                code == 0
                and value.get("loggedIn") is True
                and value.get("authMethod") == "claude.ai"
                and value.get("apiProvider") == "firstParty"
            )
        except ValueError:
            signed_in = False
        return {"client_version_supported": True, "subscription_signed_in": signed_in}


def parse_result(raw: bytes, request: ModelRequest) -> ModelResponse:
    initialized = completed = False
    answer = ""
    session = ""
    reported: dict[str, JsonValue] | None = None
    try:
        if len(raw) > MAX_EVENTS:
            raise ValueError("oversized events")
        for line in raw.splitlines():
            event = _OBJECT.validate_json(line, strict=True)
            kind = event.get("type")
            if completed:
                raise ValueError("events after completion")
            if kind == "system" and event.get("subtype") == "init" and not initialized:
                if (
                    event.get("tools") != []
                    or event.get("mcp_servers") != []
                    or event.get("model") != request.model
                    or event.get("permissionMode") != "dontAsk"
                ):
                    raise ValueError("native authority or route mismatch")
                selected = event.get("session_id")
                if not isinstance(selected, str) or not 1 <= len(selected) <= 200:
                    raise ValueError("missing session identity")
                session, initialized = selected, True
            elif kind == "assistant" and initialized:
                message = event.get("message")
                if (
                    not isinstance(message, dict)
                    or message.get("model") != request.model
                ):
                    raise ValueError("assistant route mismatch")
                blocks = message.get("content")
                if not isinstance(blocks, list):
                    raise ValueError("invalid content")
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") not in {
                        "text",
                        "thinking",
                    }:
                        raise ValueError("native tool or unknown content")
                    if block.get("type") == "text":
                        text = block.get("text")
                        if not isinstance(text, str):
                            raise ValueError("invalid text")
                        answer += text
            elif kind == "result" and initialized:
                models = event.get("modelUsage")
                if (
                    event.get("subtype") != "success"
                    or event.get("is_error") is not False
                    or event.get("num_turns") != 1
                    or event.get("permission_denials") != []
                    or event.get("session_id") != session
                    or not isinstance(models, dict)
                    or set(models) != {request.model}
                ):
                    raise ValueError("failed, repeated or substituted turn")
                if event.get("result") != answer or not answer:
                    raise ValueError("result text mismatch")
                candidate = event.get("usage")
                if not isinstance(candidate, dict):
                    raise ValueError("missing usage")
                reported = candidate
                completed = True
            else:
                raise ValueError("unsupported native event")
        if not initialized or not completed or reported is None:
            raise ValueError("incomplete turn")
        names = (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
        values = tuple(reported.get(name) for name in names)
        if any(
            type(value) is not int or not 0 <= value <= 1_000_000_000
            for value in values
        ):
            raise ValueError("invalid usage")
        incoming, outgoing, cached, created = values
        assert (
            isinstance(incoming, int)
            and isinstance(outgoing, int)
            and isinstance(cached, int)
            and isinstance(created, int)
        )
        if len(answer.encode()) > (
            request.max_text_output_bytes or request.max_output
        ) or (
            request.max_output_tokens is not None
            and outgoing > request.max_output_tokens
        ):
            raise ValueError("output ceiling exceeded")
        result = ModelResponse(
            turn=Turn(role="assistant", blocks=(TextBlock(text=answer),)),
            stop_reason="end_turn",
            usage=Usage(
                unit="tokens",
                input=incoming + cached + created,
                output=outgoing,
                cache_read=cached,
                cache_write=created,
            ),
            provider_request_id=session,
        )
        if len(canonical_bytes(result)) > request.max_output:
            raise ValueError("response ceiling exceeded")
        if request.response_format is not None:
            schema, _ = compile_schema(request.response_format.json_schema)
            if not valid_instance(schema, json.loads(answer)):
                raise ValueError("invalid structured output")
        return result
    except (ValueError, TypeError, RecursionError):
        raise ProviderError(
            "Claude subscription returned an inadmissible turn"
        ) from None


class ClaudeSubscriptionClient:
    def __init__(
        self,
        executable: Path,
        attempt: Path,
        *,
        allow_data_transfer: bool,
        allow_subscription_usage: bool,
        timeout: float = 60,
        dispatch_guard: Callable[[], None] | None = None,
    ) -> None:
        if (
            allow_data_transfer is not True
            or allow_subscription_usage is not True
            or not 1 <= timeout <= 120
        ):
            raise ValueError(
                "Claude subscription requires explicit consent and finite deadline"
            )
        self.executable, self.attempt, self.timeout, self.dispatch_guard = (
            executable,
            attempt,
            timeout,
            dispatch_guard,
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        resolved = subscription_registry().resolve(
            request.provider, request.model, request.effort
        )
        if (
            request.provider != PROVIDER
            or resolved.substituted
            or request.tools
            or any(
                not isinstance(block, TextBlock)
                for turn in request.turns
                for block in turn.blocks
            )
        ):
            raise ProviderError(
                "Claude subscription requires its exact tool-free route"
            )
        output_schema = None
        if request.response_format is not None:
            output_schema, _ = compile_schema(request.response_format.json_schema)
        payload = json.dumps(
            {
                "instructions": request.system,
                "messages": [turn.model_dump(mode="json") for turn in request.turns],
                **(
                    {
                        "response_schema": output_schema,
                        "response_instructions": (
                            "Return only JSON matching response_schema, "
                            "without code fences."
                        ),
                    }
                    if output_schema is not None
                    else {}
                ),
            },
            ensure_ascii=False,
        ).encode()
        if len(payload) > MAX_INPUT:
            raise ProviderError("Claude subscription input exceeds its bound")
        with new_attempt(self.attempt) as directory:
            write_receipt(
                directory,
                "request.json",
                {
                    "provider": PROVIDER,
                    "client_version": CLIENT_VERSION,
                    "request_sha256": hashlib.sha256(
                        canonical_bytes(request)
                    ).hexdigest(),
                    "billing_verified": False,
                },
            )
            readiness = await status(self.executable)
            if not all(readiness.values()):
                raise ProviderError(
                    "Supported Claude client with subscription sign-in required"
                )
            with tempfile.TemporaryDirectory(prefix="mos-claude-turn-") as temporary:
                cwd = Path(temporary)
                arguments = (
                    "--print",
                    "--safe-mode",
                    "--restricted",
                    "--setting-sources",
                    "",
                    "--settings",
                    '{"disableAllHooks":true,"autoUpdatesChannel":"stable","env":{}}',
                    "--strict-mcp-config",
                    "--mcp-config",
                    '{"mcpServers":{}}',
                    "--tools",
                    "",
                    "--disable-slash-commands",
                    "--permission-mode",
                    "dontAsk",
                    "--no-session-persistence",
                    "--max-turns",
                    "1",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                    "--model",
                    request.model,
                    "--effort",
                    resolved.effort,
                )
                if self.dispatch_guard is not None:
                    self.dispatch_guard()
                write_receipt(directory, "dispatch.json", {"state": "dispatch_started"})
                code, raw, _ = await invoke(
                    self.executable, arguments, cwd, data=payload, timeout=self.timeout
                )
                if code != 0:
                    raise ProviderError(
                        "Claude subscription failed; Mos will not repeat the invocation"
                    )
                result = parse_result(raw, request)
                write_receipt(
                    directory,
                    "completion.json",
                    {
                        "state": "completed",
                        "response_sha256": hashlib.sha256(
                            canonical_bytes(result)
                        ).hexdigest(),
                        "usage": result.usage.model_dump(mode="json"),
                        "billing_verified": False,
                    },
                )
                return result
