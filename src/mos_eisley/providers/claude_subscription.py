"""Exact-version tool-free Claude subscription transport; native-owned auth only."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock, Turn, Usage
from mos_eisley.providers.codex_subscription import (
    MAX_EVENTS,
    MAX_INPUT,
    NativeProcessError,
    invoke,
    new_attempt,
    write_receipt,
)
from mos_eisley.subscription_authorization import subscription_registry
from mos_eisley.tools.mcp_schema import compile_schema, valid_instance

CLIENT_VERSION = "2.1.283"
PROVIDER = "anthropic_subscription"
_OBJECT = TypeAdapter(dict[str, JsonValue])


class ClaudeProtocolError(ProviderError):
    """Controlled parser reason; never includes a native payload or diagnostic."""

    def __init__(
        self,
        reason: str,
        observed_model: object = None,
        *,
        observed_event: object = None,
        observed_system_subtype: object = None,
        observed_output_bytes: int | None = None,
        observed_output_tokens: int | None = None,
    ) -> None:
        super().__init__("Claude subscription returned an inadmissible turn")
        self.observed_output_bytes = observed_output_bytes
        self.observed_output_tokens = observed_output_tokens
        self.reason = reason
        self.observed_model = (
            observed_model
            if isinstance(observed_model, str)
            and re.fullmatch(
                r"claude-(sonnet|opus|haiku)-[0-9](?:[.-][0-9]+)*", observed_model
            )
            and len(observed_model) <= 120
            else None
        )
        self.observed_event = (
            observed_event
            if observed_event
            in (
                "rate_limit_event",
                "system",
                "assistant",
                "user",
                "stream_event",
                "result",
                "tool_progress",
                "tool_use_summary",
                "auth_status",
                "prompt_suggestion",
            )
            else None
        )
        self.observed_system_subtype = (
            observed_system_subtype
            if observed_system_subtype
            in (
                "agents_killed",
                "api_error",
                "api_retry",
                "away_summary",
                "background_tasks_changed",
                "bridge_state",
                "bridge_status",
                "cloud_session_delta",
                "cloud_session_status",
                "code_change_published",
                "commands_changed",
                "compact_boundary",
                "control_request_progress",
                "dev_intent",
                "elicitation_complete",
                "feedback_draft_queued",
                "file_snapshot",
                "hook_progress",
                "hook_response",
                "hook_started",
                "informational",
                "init",
                "local_command",
                "memory_recall",
                "memory_saved",
                "mirror_error",
                "model_consent_fallback",
                "model_fallback",
                "model_refusal_fallback",
                "model_refusal_no_fallback",
                "notification",
                "peer_message_hold",
                "per_turn_effort_changed",
                "permission_denied",
                "permission_retry",
                "plugin_install",
                "post_turn_summary",
                "scheduled_task_fire",
                "session_metadata",
                "session_state_changed",
                "status",
                "stop_hook_summary",
                "task_notification",
                "task_progress",
                "task_started",
                "task_summary",
                "task_updated",
                "thinking_tokens",
                "tool_host_result",
                "turn_duration",
                "turn_handoff_available",
                "turn_preempted",
                "turn_starting",
                "vcs_state_changed",
                "worker_shutting_down",
            )
            else "unrecognized"
            if observed_event == "system"
            else None
        )


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
    quota_sessions: list[str] = []
    progress_events = 0
    reported: dict[str, JsonValue] | None = None
    try:
        if len(raw) > MAX_EVENTS:
            raise ClaudeProtocolError("event_ceiling")
        for line in raw.splitlines():
            event = _OBJECT.validate_json(line, strict=True)
            kind = event.get("type")
            if completed:
                raise ClaudeProtocolError(
                    "event_order",
                    observed_event=kind,
                    observed_system_subtype=event.get("subtype")
                    if kind == "system"
                    else None,
                )
            if kind == "system" and event.get("subtype") == "thinking_tokens":
                selected = event.get("session_id")
                identifier = event.get("uuid")
                estimates = (
                    event.get("estimated_tokens"),
                    event.get("estimated_tokens_delta"),
                )
                if (
                    not initialized
                    or selected != session
                    or not isinstance(identifier, str)
                    or not 1 <= len(identifier) <= 200
                    or set(event)
                    != {
                        "type",
                        "subtype",
                        "session_id",
                        "uuid",
                        "estimated_tokens",
                        "estimated_tokens_delta",
                    }
                    or progress_events >= 4096
                    or any(
                        not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not math.isfinite(value)
                        or not 0 <= value <= 1_000_000_000
                        for value in estimates
                    )
                ):
                    raise ClaudeProtocolError(
                        "thinking_metadata",
                        observed_event="system",
                        observed_system_subtype="thinking_tokens",
                    )
                progress_events += 1
            elif kind == "rate_limit_event":
                info = event.get("rate_limit_info")
                selected = event.get("session_id")
                identifier = event.get("uuid")
                if (
                    set(event) != {"type", "rate_limit_info", "session_id", "uuid"}
                    or not isinstance(info, dict)
                    or info.get("status") not in ("allowed", "allowed_warning")
                    or not isinstance(selected, str)
                    or not 1 <= len(selected) <= 200
                    or not isinstance(identifier, str)
                    or not 1 <= len(identifier) <= 200
                    or len(quota_sessions) >= 32
                ):
                    raise ClaudeProtocolError(
                        "quota_metadata", observed_event="rate_limit_event"
                    )
                if initialized and selected != session:
                    raise ClaudeProtocolError("session_identity")
                quota_sessions.append(selected)
            elif (
                kind == "system" and event.get("subtype") == "init" and not initialized
            ):
                if event.get("tools") != [] or event.get("mcp_servers") != []:
                    raise ClaudeProtocolError("init_tools")
                if event.get("model") != request.model:
                    raise ClaudeProtocolError("init_model", event.get("model"))
                if event.get("permissionMode") != "dontAsk":
                    raise ClaudeProtocolError("init_permissions")
                selected = event.get("session_id")
                if not isinstance(selected, str) or not 1 <= len(selected) <= 200:
                    raise ClaudeProtocolError("session_identity")
                if any(value != selected for value in quota_sessions):
                    raise ClaudeProtocolError("session_identity")
                session, initialized = selected, True
            elif kind == "assistant" and initialized:
                message = event.get("message")
                if (
                    not isinstance(message, dict)
                    or message.get("model") != request.model
                ):
                    raise ClaudeProtocolError(
                        "assistant_identity",
                        message.get("model") if isinstance(message, dict) else None,
                    )
                blocks = message.get("content")
                if not isinstance(blocks, list):
                    raise ClaudeProtocolError("content_shape")
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") not in {
                        "text",
                        "thinking",
                    }:
                        raise ClaudeProtocolError("content_kind")
                    if block.get("type") == "text":
                        text = block.get("text")
                        if not isinstance(text, str):
                            raise ClaudeProtocolError("text_shape")
                        answer += text
            elif kind == "result" and initialized:
                models = event.get("modelUsage")
                if not isinstance(models, dict) or set(models) != {request.model}:
                    raise ClaudeProtocolError(
                        "result_models",
                        next(iter(models))
                        if isinstance(models, dict) and len(models) == 1
                        else None,
                    )
                if event.get("num_turns") != 1:
                    raise ClaudeProtocolError("result_turns")
                if event.get("permission_denials") != []:
                    raise ClaudeProtocolError("result_permissions")
                if (
                    event.get("subtype") != "success"
                    or event.get("is_error") is not False
                    or event.get("session_id") != session
                ):
                    raise ClaudeProtocolError("result_authority")
                if event.get("result") != answer or not answer:
                    raise ClaudeProtocolError("result_text")
                candidate = event.get("usage")
                if not isinstance(candidate, dict):
                    raise ClaudeProtocolError("usage_shape")
                reported = candidate
                completed = True
            else:
                raise ClaudeProtocolError(
                    "event_kind",
                    observed_event=kind,
                    observed_system_subtype=event.get("subtype")
                    if kind == "system"
                    else None,
                )
        if not initialized or not completed or reported is None:
            raise ClaudeProtocolError("incomplete_turn")
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
            raise ClaudeProtocolError("usage_counters")
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
            raise ClaudeProtocolError(
                "output_ceiling",
                observed_output_bytes=len(answer.encode()),
                observed_output_tokens=outgoing,
            )
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
            raise ClaudeProtocolError("response_ceiling")
        if request.response_format is not None:
            schema, _ = compile_schema(request.response_format.json_schema)
            if not valid_instance(schema, json.loads(answer)):
                raise ClaudeProtocolError("output_schema")
        return result
    except (ValueError, TypeError, RecursionError):
        raise ClaudeProtocolError("malformed_events") from None


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
                write_receipt(
                    directory,
                    "failure.json",
                    {"phase": "auth_preflight", "billing_verified": False},
                )
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
                process_started = time.monotonic()
                try:
                    code, raw, diagnostic = await invoke(
                        self.executable,
                        arguments,
                        cwd,
                        data=payload,
                        timeout=self.timeout,
                    )
                except ProviderError as error:
                    write_receipt(
                        directory,
                        "failure.json",
                        {
                            "phase": "native_process",
                            "billing_verified": False,
                            "process_reason": error.process_reason
                            if isinstance(error, NativeProcessError)
                            else "deadline"
                            if error.failure_kind == "provider_timeout"
                            else "unclassified",
                            "deadline_seconds": self.timeout,
                            "elapsed_ms": min(
                                1_000_000,
                                max(
                                    0, int((time.monotonic() - process_started) * 1000)
                                ),
                            ),
                        },
                    )
                    raise
                if code != 0:
                    hint = "unclassified"
                    native_diagnostic = (raw + diagnostic).lower()
                    for category, markers in (
                        (
                            "control_options",
                            (b"unknown option", b"unrecognized option"),
                        ),
                        (
                            "authentication",
                            (b"not logged in", b"authentication", b"invalid api key"),
                        ),
                        ("quota", (b"credit balance", b"rate limit", b"usage limit")),
                        ("model", (b"model not found", b"unsupported model")),
                    ):
                        if any(marker in native_diagnostic for marker in markers):
                            hint = category
                            break
                    write_receipt(
                        directory,
                        "failure.json",
                        {
                            "phase": "native_exit",
                            "return_code": code,
                            "diagnostic_hint": hint,
                            "billing_verified": False,
                        },
                    )
                    raise ProviderError(
                        "Claude subscription failed; Mos will not repeat the invocation"
                    )
                try:
                    result = parse_result(raw, request)
                except ClaudeProtocolError as error:
                    subtype = error.observed_system_subtype
                    observed_tokens = error.observed_output_tokens
                    write_receipt(
                        directory,
                        "failure.json",
                        {
                            "phase": "protocol",
                            "reason": error.reason,
                            **(
                                {"observed_model": error.observed_model}
                                if error.observed_model is not None
                                else {}
                            ),
                            **(
                                {"observed_event": error.observed_event}
                                if error.observed_event is not None
                                else {}
                            ),
                            **(
                                {"observed_system_subtype": subtype}
                                if subtype is not None
                                else {}
                            ),
                            **(
                                {"native_reported_output_tokens": observed_tokens}
                                if observed_tokens is not None
                                else {}
                            ),
                            **(
                                {"output_text_bytes": error.observed_output_bytes}
                                if error.observed_output_bytes is not None
                                else {}
                            ),
                            "billing_verified": False,
                        },
                    )
                    raise
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
