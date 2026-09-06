"""OpenAI Responses translation, agent integration, and live artifact storage."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic import JsonValue

from mos_eisley.core.agent import AgentConfig, build_request, run_agent
from mos_eisley.core.budget import resolve_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import (
    ModelRequest,
    TextBlock,
    ToolDefinition,
    ToolSchema,
    Turn,
)
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.openai_responses import (
    OpenAIResponsesClient,
    request_payload,
    response_from_payload,
)
from mos_eisley.run.live_store import LiveManifest, begin_live_run, load_live_run
from mos_eisley.tools.fixture import FixtureDispatcher, FixtureValues


def openai_request() -> tuple[ModelRequest, FixtureDispatcher]:
    config = AgentConfig(
        provider="openai",
        model="gpt-6-astra",
        effort="high",
        initial_turns=(
            Turn(role="user", blocks=(TextBlock(text="Look up the boundary."),)),
        ),
    )
    dispatcher = FixtureDispatcher(FixtureValues(values={"boundary": ">= 10"}))
    registry = openai_registry()
    resolved = registry.resolve(config.provider, config.model, config.effort)
    budget = resolve_budget(resolved.spec, resolved.effort, config.budget)
    return (
        build_request(config, resolved, budget, dispatcher, config.initial_turns),
        dispatcher,
    )


def response_payload(
    output: list[dict[str, JsonValue]],
    *,
    response_id: str = "resp_1",
    status: str = "completed",
    incomplete_reason: str | None = None,
) -> dict[str, JsonValue]:
    return {
        "id": response_id,
        "status": status,
        "output": cast(JsonValue, output),
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {
                "cached_tokens": 10,
                "cache_write_tokens": 2,
            },
            "output_tokens_details": {"reasoning_tokens": 5},
        },
        "incomplete_details": (
            {"reason": incomplete_reason} if incomplete_reason is not None else None
        ),
    }


class OpenAITranslationTests(TestCase):
    def test_request_is_private_bounded_and_strict(self) -> None:
        request, _ = openai_request()
        payload = request_payload(request)
        self.assertEqual(payload["model"], "gpt-6-astra")
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertEqual(payload["max_output_tokens"], 4096)
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["truncation"], "disabled")
        self.assertEqual(payload["include"], ["reasoning.encrypted_content"])
        tools = payload["tools"]
        assert isinstance(tools, list)
        tool = tools[0]
        assert isinstance(tool, dict)
        self.assertIs(tool["strict"], True)
        parameters = tool["parameters"]
        assert isinstance(parameters, dict)
        self.assertIs(parameters["additionalProperties"], False)
        self.assertEqual(parameters["required"], ["key"])

    def test_request_rejects_wrong_provider_missing_limit_and_optional_schema(
        self,
    ) -> None:
        request, _ = openai_request()
        invalid = (
            request.model_copy(update={"provider": "fixture"}),
            request.model_copy(update={"max_output_tokens": None}),
            request.model_copy(
                update={
                    "tools": (
                        ToolDefinition(
                            name="optional",
                            description="Contains an optional property.",
                            input_schema=ToolSchema(
                                type="object",
                                properties={"value": ToolSchema(type="string")},
                            ),
                        ),
                    )
                }
            ),
        )
        for item in invalid:
            with self.assertRaises(ProviderError):
                request_payload(item)

    def test_response_parses_reasoning_call_text_refusal_and_incomplete(self) -> None:
        tool_response = response_from_payload(
            response_payload(
                [
                    {
                        "type": "reasoning",
                        "id": "rs_1",
                        "summary": [{"type": "summary_text", "text": "Need data."}],
                        "encrypted_content": "encrypted",
                    },
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "provider/call/1",
                        "name": "fixture_lookup",
                        "arguments": '{"key":"boundary"}',
                    },
                ]
            )
        )
        self.assertEqual(tool_response.stop_reason, "tool_use")
        self.assertEqual(tool_response.usage.unit, "tokens")
        call = tool_response.turn.blocks[1]
        self.assertEqual(call.kind, "tool_call")
        assert call.kind == "tool_call"
        self.assertTrue(call.id.startswith("openai-"))
        self.assertEqual(call.provider_call_id, "provider/call/1")

        refusal = response_from_payload(
            response_payload(
                [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "refusal", "refusal": "Cannot help."}],
                    }
                ]
            )
        )
        self.assertEqual(refusal.stop_reason, "filtered")
        incomplete = response_from_payload(
            response_payload(
                [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Partial"}],
                    }
                ],
                status="incomplete",
                incomplete_reason="max_output_tokens",
            )
        )
        self.assertEqual(incomplete.stop_reason, "max_output")

    def test_response_rejects_invalid_or_non_stateless_output(self) -> None:
        invalid_outputs: tuple[list[dict[str, JsonValue]], ...] = (
            [{"type": "reasoning", "id": "rs_1", "summary": []}],
            [{"type": "unknown"}],
            [
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "fixture_lookup",
                    "arguments": "not json",
                }
            ],
            [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "output_text", "text": "wrong"}],
                }
            ],
        )
        for output in invalid_outputs:
            with self.assertRaises(ProviderError):
                response_from_payload(response_payload(output))


class OpenAIAgentTests(IsolatedAsyncioTestCase):
    async def test_two_turn_live_translation_and_storage(self) -> None:
        request, dispatcher = openai_request()
        config = AgentConfig(
            provider=request.provider,
            model=request.model,
            effort=request.effort,
            initial_turns=request.turns,
        )
        responses = [
            response_payload(
                [
                    {
                        "type": "reasoning",
                        "id": "rs_1",
                        "summary": [],
                        "encrypted_content": "encrypted",
                    },
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "fixture_lookup",
                        "arguments": '{"key":"boundary"}',
                    },
                ]
            ),
            response_payload(
                [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Boundary is >= 10."}
                        ],
                    }
                ],
                response_id="resp_2",
            ),
        ]

        class FakeTransport:
            def __init__(self) -> None:
                self.payloads: list[dict[str, JsonValue]] = []

            async def create_response(
                self, payload: dict[str, JsonValue]
            ) -> dict[str, JsonValue]:
                self.payloads.append(payload)
                return responses[len(self.payloads) - 1]

        transport = FakeTransport()
        with TemporaryDirectory() as directory:
            session = begin_live_run(Path(directory), config)
            result = await run_agent(
                config,
                openai_registry(),
                OpenAIResponsesClient(transport),
                dispatcher,
                session.journal,
            )
            session.complete(result)
            loaded_config, events, loaded_result = load_live_run(session.path)
            changed_response = result.responses[0].model_copy(
                update={"provider_request_id": "resp_changed"}
            )
            changed_result = result.model_copy(
                update={"responses": (changed_response,) + result.responses[1:]}
            )
            result_path = session.path / "result.json"
            changed_payload = canonical_bytes(changed_result)
            result_path.write_bytes(changed_payload)
            manifest_path = session.path / "manifest.json"
            manifest = LiveManifest.model_validate_json(manifest_path.read_bytes())
            artifacts = tuple(
                artifact.model_copy(update={"sha256": digest(changed_payload)})
                if artifact.name == "result.json"
                else artifact
                for artifact in manifest.artifacts
            )
            manifest_path.write_bytes(
                canonical_bytes(manifest.model_copy(update={"artifacts": artifacts}))
            )
            with self.assertRaisesRegex(ValueError, "journal does not match"):
                load_live_run(session.path)

        self.assertEqual(loaded_config, config)
        self.assertEqual(loaded_result, result)
        self.assertEqual(len(events), 5)
        self.assertEqual(result.final_text, "Boundary is >= 10.")
        self.assertEqual(result.usage.unit, "tokens")
        self.assertEqual(
            (result.usage.billed_input, result.usage.billed_output), (200, 40)
        )
        self.assertEqual(len(result.responses), 2)
        second_input = transport.payloads[1]["input"]
        assert isinstance(second_input, list)
        function_output = next(
            item
            for item in second_input
            if isinstance(item, dict) and item.get("type") == "function_call_output"
        )
        self.assertEqual(function_output["call_id"], "call_1")
        reasoning = next(
            item
            for item in second_input
            if isinstance(item, dict) and item.get("type") == "reasoning"
        )
        self.assertEqual(reasoning["encrypted_content"], "encrypted")
