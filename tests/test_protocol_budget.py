"""Canonical protocol, model registry, and budget invariants."""

from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.core.budget import BudgetPolicy, resolve_budget
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import (
    Block,
    ModelRequest,
    ModelResponse,
    StopReason,
    TextBlock,
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolSchema,
    Turn,
    Usage,
)
from mos_eisley.core.registry import (
    ModelRegistry,
    ModelSpec,
    fixture_registry,
    openai_registry,
)


class ProtocolTests(TestCase):
    def test_canonical_json_sorts_nested_mapping_keys(self) -> None:
        left = ToolCallBlock(id="call", name="tool", args={"b": 2, "a": 1})
        right = ToolCallBlock(id="call", name="tool", args={"a": 1, "b": 2})
        self.assertEqual(canonical_bytes(left), canonical_bytes(right))

    def test_new_provider_fields_do_not_change_legacy_fixture_hashes(self) -> None:
        request = ModelRequest(
            provider="fixture",
            model="model",
            effort="low",
            turns=(Turn(role="user", blocks=(TextBlock(text="hello"),)),),
            max_output=100,
        )
        self.assertNotIn(b"max_output_tokens", canonical_bytes(request))
        call = ToolCallBlock(id="call", name="tool", args={})
        self.assertNotIn(b"provider_call_id", canonical_bytes(call))

    def test_tool_schema_rejects_unsupported_shapes(self) -> None:
        invalid = (
            {"type": "object", "required": ("missing",)},
            {"type": "array"},
            {"type": "string", "properties": {"x": ToolSchema(type="string")}},
            {"type": "object", "items": ToolSchema(type="string")},
            {"type": "object", "enum": ("x",)},
            {"type": "array", "items": ToolSchema(type="string"), "enum": ("x",)},
            {"type": "integer", "enum": (True,)},
            {"type": "boolean", "enum": (1,)},
            {"type": "string", "enum": ("same", "same")},
            {"type": "object", "properties": {"": ToolSchema(type="string")}},
        )
        for payload in invalid:
            with self.assertRaises(ValidationError):
                ToolSchema.model_validate(payload)
        with self.assertRaises(ValidationError):
            ToolDefinition(
                name="bad",
                description="Bad schema.",
                input_schema=ToolSchema(type="string"),
            )

    def test_turn_roles_and_tool_history_are_structurally_validated(self) -> None:
        call = ToolCallBlock(id="call", name="lookup", args={})
        result = ToolResultBlock(call_id="call", name="lookup", content="value")
        for role, blocks in (
            ("assistant", (result,)),
            ("user", (call,)),
        ):
            with self.assertRaises(ValidationError):
                Turn.model_validate({"role": role, "blocks": blocks})

        invalid_histories = (
            (
                Turn(role="user", blocks=(TextBlock(text="start"),)),
                Turn(role="user", blocks=(TextBlock(text="again"),)),
            ),
            (
                Turn(role="user", blocks=(TextBlock(text="start"),)),
                Turn(role="assistant", blocks=(call,)),
                Turn(role="user", blocks=(TextBlock(text="missing result"),)),
            ),
            (Turn(role="user", blocks=(result,)),),
        )
        for turns in invalid_histories:
            with self.assertRaises(ValidationError):
                ModelRequest(
                    provider="fixture",
                    model="model",
                    effort="low",
                    turns=turns,
                    max_output=100,
                )

    def test_request_rejects_duplicate_tools(self) -> None:
        tool = ToolDefinition(
            name="lookup",
            description="Look up a value.",
            input_schema=ToolSchema(type="object"),
        )
        with self.assertRaises(ValidationError):
            ModelRequest(
                provider="fixture",
                model="model",
                effort="low",
                tools=(tool, tool),
                turns=(Turn(role="user", blocks=(TextBlock(text="hello"),)),),
                max_output=100,
            )

    def test_response_requires_stop_reason_to_match_tool_calls(self) -> None:
        call = ToolCallBlock(id="call", name="lookup", args={})
        cases: tuple[tuple[StopReason, tuple[Block, ...]], ...] = (
            ("tool_use", (TextBlock(text="no call"),)),
            ("end_turn", (call,)),
            ("tool_use", (call, call)),
        )
        for stop, blocks in cases:
            with self.assertRaises(ValidationError):
                ModelResponse(
                    turn=Turn(role="assistant", blocks=blocks),
                    stop_reason=stop,
                    usage=Usage(input=1, output=1),
                )
        with self.assertRaises(ValidationError):
            ModelResponse(
                turn=Turn(role="user", blocks=(TextBlock(text="wrong role"),)),
                stop_reason="end_turn",
                usage=Usage(input=1, output=1),
            )


class RegistryBudgetTests(TestCase):
    def test_effort_exact_fallback_and_errors(self) -> None:
        registry = fixture_registry()
        exact = registry.resolve("fixture", "tool-reviewer-v1", "medium")
        self.assertEqual(exact.effort, "medium")
        self.assertFalse(exact.substituted)
        fallback = registry.resolve("fixture", "tool-reviewer-v1", "xhigh")
        self.assertEqual(fallback.effort, "high")
        self.assertTrue(fallback.substituted)
        default = registry.resolve("fixture", "tool-reviewer-v1", None)
        self.assertEqual(default.effort, "medium")
        with self.assertRaisesRegex(ValueError, "unknown model"):
            registry.resolve("fixture", "missing", "low")
        with self.assertRaisesRegex(ValueError, "unsupported effort"):
            registry.resolve("fixture", "tool-reviewer-v1", "none")

    def test_registry_rejects_invalid_or_duplicate_models(self) -> None:
        model = fixture_registry().models[0]
        with self.assertRaises(ValidationError):
            ModelRegistry(models=(model, model))
        for update in (
            {"efforts": ("low", "low")},
            {"default_effort": "max"},
            {"max_output_bytes": model.context_bytes},
            {"context_tokens": 1000},
            {"context_tokens": 1000, "max_output_tokens": 1000},
        ):
            with self.assertRaises(ValidationError):
                ModelSpec.model_validate(model.model_copy(update=update).model_dump())

    def test_budget_reserves_output_and_headroom(self) -> None:
        model = fixture_registry().models[0]
        budget = resolve_budget(
            model,
            "high",
            BudgetPolicy(session_cap_bytes=20_000, headroom_pct=0.1),
        )
        self.assertEqual(budget.cap, 20_000)
        self.assertEqual(budget.output_reserve, 12_000)
        self.assertEqual(budget.usable_input, 7_200)
        self.assertEqual(budget.headroom, 800)
        openai = openai_registry().models[0]
        openai_budget = resolve_budget(openai, "medium", BudgetPolicy())
        self.assertEqual(openai_budget.max_output_tokens, 4096)
        tiny = model.model_copy(update={"context_bytes": 100, "max_output_bytes": 99})
        with self.assertRaisesRegex(ValueError, "reserve"):
            resolve_budget(
                tiny,
                "low",
                BudgetPolicy(session_cap_bytes=99, reserve_low_bytes=100),
            )
