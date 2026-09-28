"""Claude Messages translation preserves native tool and thinking state."""

from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic import JsonValue

from mos_eisley.core.models import Brief, CriticRequest, CriticSpec, Critique
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import (
    ModelRequest,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolSchema,
    Turn,
)
from mos_eisley.core.registry import default_registry
from mos_eisley.providers.anthropic_messages import (
    AnthropicMessagesClient,
    request_payload,
    response_from_payload,
)
from mos_eisley.providers.model_reviewer import ModelReviewer


def _request() -> ModelRequest:
    return ModelRequest(
        provider="anthropic",
        model="claude-sonnet-5",
        effort="high",
        system="Answer using the tool when needed.",
        tools=(
            ToolDefinition(
                name="lookup",
                description="Look up a value",
                input_schema=ToolSchema(
                    type="object",
                    properties={"key": ToolSchema(type="string")},
                    required=("key",),
                ),
            ),
        ),
        turns=(Turn(role="user", blocks=(TextBlock(text="Look up alpha"),)),),
        max_output=16_000,
        max_output_tokens=1024,
    )


def _response(
    content: list[dict[str, JsonValue]], stop_reason: str = "tool_use"
) -> dict[str, JsonValue]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "stop_reason": stop_reason,
        "content": cast(JsonValue, content),
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_input_tokens": 3,
            "cache_creation_input_tokens": 2,
        },
    }


class AnthropicTranslationTests(TestCase):
    def test_request_projects_bounded_tools_and_explicit_effort(self) -> None:
        payload = request_payload(_request())
        self.assertEqual(payload["model"], "claude-sonnet-5")
        self.assertEqual(payload["output_config"], {"effort": "high"})
        self.assertEqual(payload["thinking"], {"type": "adaptive"})
        self.assertEqual(payload["service_tier"], "standard_only")
        self.assertIs(payload["stream"], False)
        tools = payload["tools"]
        assert isinstance(tools, list)
        tool = tools[0]
        assert isinstance(tool, dict)
        schema = tool["input_schema"]
        assert isinstance(schema, dict)
        self.assertEqual(schema["required"], ["key"])
        self.assertIs(schema["additionalProperties"], False)

    def test_thinking_tool_result_round_trip_preserves_signed_native_block(
        self,
    ) -> None:
        native_thinking: dict[str, JsonValue] = {
            "type": "thinking",
            "thinking": "Look up alpha.",
            "signature": "signed-state",
        }
        response = response_from_payload(
            _response(
                [
                    native_thinking,
                    {"type": "redacted_thinking", "data": "opaque"},
                    {
                        "type": "tool_use",
                        "id": "toolu/call/1",
                        "name": "lookup",
                        "input": {"key": "alpha"},
                    },
                ]
            )
        )
        self.assertEqual(response.stop_reason, "tool_use")
        self.assertEqual(response.usage.input, 15)
        self.assertEqual(response.usage.cache_write, 2)
        thinking, redacted, call = response.turn.blocks
        assert isinstance(thinking, ReasoningBlock)
        assert isinstance(redacted, ReasoningBlock)
        assert isinstance(call, ToolCallBlock)
        self.assertEqual(thinking.opaque, native_thinking)
        self.assertEqual(redacted.opaque["data"], "opaque")
        self.assertTrue(call.id.startswith("anthropic-"))
        request = _request().model_copy(
            update={
                "turns": (
                    _request().turns[0],
                    response.turn,
                    Turn(
                        role="user",
                        blocks=(
                            ToolResultBlock(
                                call_id=call.id,
                                name="lookup",
                                content="value",
                            ),
                        ),
                    ),
                )
            }
        )
        payload = request_payload(request)
        messages = payload["messages"]
        assert isinstance(messages, list)
        assistant = messages[1]
        user = messages[2]
        assert isinstance(assistant, dict) and isinstance(user, dict)
        assistant_content = assistant["content"]
        user_content = user["content"]
        assert isinstance(assistant_content, list)
        assert isinstance(user_content, list)
        self.assertEqual(assistant_content[0], native_thinking)
        user_result = user_content[0]
        assert isinstance(user_result, dict)
        self.assertEqual(user_result["tool_use_id"], "toolu/call/1")

    def test_rejects_invalid_content_and_mismatched_stop(self) -> None:
        invalid = (
            _response([{"type": "thinking", "thinking": "x"}]),
            _response([{"type": "image", "data": "x"}]),
            _response(
                [{"type": "tool_use", "id": "a", "name": "lookup", "input": {}}],
                "end_turn",
            ),
        )
        for payload in invalid:
            with self.assertRaises(ProviderError):
                response_from_payload(payload)

    def test_default_registry_exposes_documented_model_only(self) -> None:
        spec = default_registry().resolve("anthropic", "claude-sonnet-5", "high")
        self.assertEqual(spec.spec.verification, "documented")


class AnthropicClientTests(IsolatedAsyncioTestCase):
    async def test_client_rejects_wrong_model_and_oversize_usage(self) -> None:
        class Stub:
            def __init__(self, response: dict[str, JsonValue]) -> None:
                self.response = response

            async def create_message(
                self, payload: dict[str, JsonValue]
            ) -> dict[str, JsonValue]:
                return self.response

            async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
                return 10

        response = _response([{"type": "text", "text": "done"}], "end_turn")
        client = AnthropicMessagesClient(Stub(response))
        self.assertEqual((await client.complete(_request())).stop_reason, "end_turn")
        with self.assertRaises(ProviderError):
            await AnthropicMessagesClient(
                Stub({**response, "model": "claude-opus-5-5"})
            ).complete(_request())
        with self.assertRaises(ProviderError):
            await client.complete(
                _request().model_copy(update={"max_output_tokens": 1})
            )

    async def test_canonical_critic_projection_accepts_typed_claude_answer(
        self,
    ) -> None:
        class Stub:
            async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
                return 50

            async def create_message(
                self, payload: dict[str, JsonValue]
            ) -> dict[str, JsonValue]:
                assert payload["model"] == "claude-sonnet-5"
                return _response(
                    [{"type": "text", "text": '{"schema_version":1,"findings":[]}'}],
                    "end_turn",
                )

        reviewer = ModelReviewer(
            AnthropicMessagesClient(Stub()),
            default_registry(),
            judge_provider="anthropic",
            judge_model="claude-sonnet-5",
            effort="high",
        )
        critic = CriticSpec(
            id="claude-critic",
            provider="anthropic",
            model="claude-sonnet-5",
            persona="correctness",
        )
        request = CriticRequest(
            brief=Brief(spec="Reject bad input", diff="+ reject(bad_input)"),
            persona="correctness",
        )
        self.assertEqual(await reviewer.critique(critic, request), Critique())
