"""Claude native authority, exact-route and malformed-event refusal."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import JsonValue

from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import JsonSchemaOutput, ModelRequest, TextBlock, Turn
from mos_eisley.providers.claude_subscription import (
    ClaudeProtocolError,
    ClaudeSubscriptionClient,
    parse_result,
    status,
)


def request() -> ModelRequest:
    return ModelRequest(
        provider="anthropic_subscription",
        model="claude-sonnet-5",
        effort="high",
        turns=(Turn(role="user", blocks=(TextBlock(text="Synthetic fixture"),)),),
        max_output=4000,
        max_output_tokens=100,
        max_text_output_bytes=2000,
    )


def events(text: str = "ok") -> list[dict[str, JsonValue]]:
    return [
        {
            "type": "system",
            "subtype": "init",
            "tools": [],
            "mcp_servers": [],
            "model": "claude-sonnet-5",
            "permissionMode": "dontAsk",
            "session_id": "fixture-session",
        },
        {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-5",
                "content": [{"type": "text", "text": text}],
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "num_turns": 1,
            "permission_denials": [],
            "session_id": "fixture-session",
            "result": text,
            "modelUsage": {"claude-sonnet-5": {}},
            "usage": {
                "input_tokens": 5,
                "output_tokens": 3,
                "cache_read_input_tokens": 2,
                "cache_creation_input_tokens": 1,
            },
        },
    ]


def encoded(value: list[dict[str, JsonValue]]) -> bytes:
    return b"\n".join(json.dumps(item).encode() for item in value)


class ClaudeTests(unittest.IsolatedAsyncioTestCase):
    def test_protocol_failure_reason_does_not_retain_native_payload(self) -> None:
        with self.assertRaises(ClaudeProtocolError) as caught:
            parse_result(b'{"private":"fixture-secret",invalid}', request())
        self.assertEqual(caught.exception.reason, "malformed_events")
        self.assertNotIn("fixture-secret", str(caught.exception))
        with self.assertRaises(ClaudeProtocolError) as rate:
            parse_result(encoded([{"type": "rate_limit_event"}, *events()]), request())
        self.assertEqual(rate.exception.observed_event, "rate_limit_event")
        self.assertIsNone(
            ClaudeProtocolError(
                "event_kind", observed_event="fixture-secret"
            ).observed_event
        )

    def test_model_mismatch_metadata_retains_only_model_identifiers(self) -> None:
        for model, expected in (
            ("claude-sonnet-5-20261001", "claude-sonnet-5-20261001"),
            ("fixture-secret", None),
        ):
            value = events()
            value[0]["model"] = model
            with self.assertRaises(ClaudeProtocolError) as caught:
                parse_result(encoded(value), request())
            self.assertEqual(caught.exception.reason, "init_model")
            self.assertEqual(caught.exception.observed_model, expected)

    async def test_failure_receipts_distinguish_exit_and_protocol_without_payload(
        self,
    ) -> None:
        cases = (
            (
                1,
                b"fixture-secret",
                {
                    "phase": "native_exit",
                    "return_code": 1,
                    "diagnostic_hint": "unclassified",
                },
            ),
            (
                1,
                b"unknown option fixture-secret",
                {
                    "phase": "native_exit",
                    "return_code": 1,
                    "diagnostic_hint": "control_options",
                },
            ),
            (0, b"fixture-secret", {"phase": "protocol", "reason": "malformed_events"}),
        )
        for code, raw, expected in cases:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                client = ClaudeSubscriptionClient(
                    root / "claude",
                    root / "attempt",
                    allow_data_transfer=True,
                    allow_subscription_usage=True,
                )
                with (
                    patch(
                        "mos_eisley.providers.claude_subscription.status",
                        new=AsyncMock(
                            return_value={
                                "client_version_supported": True,
                                "subscription_signed_in": True,
                            }
                        ),
                    ),
                    patch(
                        "mos_eisley.providers.claude_subscription.invoke",
                        new=AsyncMock(return_value=(code, raw, b"fixture-secret")),
                    ) as native,
                ):
                    with self.assertRaises(ProviderError):
                        await client.complete(request())
                    receipt = root / "attempt/failure.json"
                    self.assertEqual(
                        json.loads(receipt.read_text()),
                        {**expected, "billing_verified": False},
                    )
                    self.assertNotIn("fixture-secret", receipt.read_text())
                    self.assertFalse((root / "attempt/completion.json").exists())
                    with self.assertRaises(FileExistsError):
                        await client.complete(request())
                    self.assertEqual(native.await_count, 1)

    def test_native_text_and_usage_keep_cache_units(self) -> None:
        result = parse_result(encoded(events()), request())
        self.assertEqual(result.usage.input, 8)
        self.assertEqual(result.usage.cache_read, 2)

    def test_native_tools_permissions_model_substitution_and_extra_turns_refused(
        self,
    ) -> None:
        cases: tuple[tuple[int, dict[str, JsonValue]], ...] = (
            (0, {"tools": ["Bash"]}),
            (0, {"mcp_servers": [{"name": "hostile"}]}),
            (0, {"model": "different"}),
            (0, {"permissionMode": "bypassPermissions"}),
            (2, {"num_turns": 2}),
            (2, {"permission_denials": [{"tool_name": "Read"}]}),
            (2, {"modelUsage": {"different": {}}}),
            (2, {"is_error": True}),
        )
        for index, update in cases:
            value = events()
            value[index].update(update)
            with self.subTest(update=update), self.assertRaises(ProviderError):
                parse_result(encoded(value), request())
        value = events()
        value[1] = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-5",
                "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
            },
        }
        with self.assertRaises(ProviderError):
            parse_result(encoded(value), request())

    def test_incomplete_reordered_or_extra_events_refused(self) -> None:
        value = events()
        cases: tuple[list[dict[str, JsonValue]], ...] = (
            value[:-1],
            value + [value[-1]],
            value[1:],
            [value[1], value[0], value[2]],
            [{"type": "rate_limit_event"}, *value],
        )
        for candidate in cases:
            with self.assertRaises(ProviderError):
                parse_result(encoded(candidate), request())

    def test_malformed_usage_text_caps_and_schema_refused(self) -> None:
        cases: tuple[dict[str, JsonValue], ...] = (
            {},
            {"input_tokens": True},
            {"output_tokens": -1},
        )
        for usage in cases:
            value = events()
            value[2]["usage"] = usage
            with self.assertRaises(ProviderError):
                parse_result(encoded(value), request())
        with self.assertRaises(ProviderError):
            parse_result(
                encoded(events("☃" * 10)),
                request().model_copy(update={"max_text_output_bytes": 29}),
            )
        schema = JsonSchemaOutput(
            name="fixture",
            json_schema={
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
                "additionalProperties": False,
            },
        )
        parse_result(
            encoded(events('{"status":"ok"}')),
            request().model_copy(update={"response_format": schema}),
        )
        with self.assertRaises(ProviderError):
            parse_result(
                encoded(events('{"status":3}')),
                request().model_copy(update={"response_format": schema}),
            )

    async def test_status_rejects_api_and_unknown_client_without_leaking_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory) / "claude"
            for method in ("api_key", "api_key_helper", "third_party", "oauth_token"):
                answers = [
                    (0, b"2.1.283 (Claude Code)", b""),
                    (
                        0,
                        json.dumps(
                            {
                                "loggedIn": True,
                                "authMethod": method,
                                "apiProvider": "firstParty",
                                "email": "private@example.invalid",
                            }
                        ).encode(),
                        b"",
                    ),
                ]
                with patch(
                    "mos_eisley.providers.claude_subscription.invoke",
                    new=AsyncMock(side_effect=answers),
                ):
                    result = await status(client)
                self.assertFalse(result["subscription_signed_in"])
                self.assertNotIn("email", result)
            with patch(
                "mos_eisley.providers.claude_subscription.invoke",
                new=AsyncMock(return_value=(0, b"unreviewed", b"")),
            ) as native:
                self.assertFalse((await status(client))["client_version_supported"])
                self.assertEqual(native.await_count, 1)

    async def test_transport_controls_are_explicit_and_failed_attempt_is_burned(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = ClaudeSubscriptionClient(
                root / "claude",
                root / "attempt",
                allow_data_transfer=True,
                allow_subscription_usage=True,
            )
            with (
                patch(
                    "mos_eisley.providers.claude_subscription.status",
                    new=AsyncMock(
                        return_value={
                            "client_version_supported": True,
                            "subscription_signed_in": True,
                        }
                    ),
                ),
                patch(
                    "mos_eisley.providers.claude_subscription.invoke",
                    new=AsyncMock(return_value=(0, encoded(events()), b"")),
                ) as native,
            ):
                await client.complete(request())
                arguments = native.call_args.args[1]
                for flag in (
                    "--safe-mode",
                    "--restricted",
                    "--strict-mcp-config",
                    "--tools",
                    "--disable-slash-commands",
                    "--no-session-persistence",
                ):
                    self.assertIn(flag, arguments)
                self.assertEqual(arguments[arguments.index("--tools") + 1], "")
                self.assertNotIn("Synthetic fixture", str(arguments))
                with self.assertRaises(FileExistsError):
                    await client.complete(request())
                self.assertEqual(native.await_count, 1)
