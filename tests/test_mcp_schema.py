"""Semantic preservation, bounded schemas and real wrapped MCP roundtrips."""

import itertools
import json
import sys
from pathlib import Path
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase, TestCase

from fixtures.mcp_http_server import MCPHTTPFixture
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.types import CallToolResult, ListToolsResult, Tool

from mos_eisley.core.protocol import ToolCallBlock
from mos_eisley.tools.mcp import MCPConfig, MCPDispatcher, MCPFailure, connect_mcp
from mos_eisley.tools.mcp_http import MCPHTTPSettings
from mos_eisley.tools.mcp_schema import prepare_schema, valid_instance


def object_schema(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"value": value},
        "required": ["value"],
        "additionalProperties": False,
    }


class SchemaTests(TestCase):
    def test_local_references_keep_native_shape_and_validation(self) -> None:
        source = {
            **object_schema({"$ref": "#/$defs/Count"}),
            "$defs": {"Count": {"type": "integer", "minimum": 0, "maximum": 10}},
        }
        prepared = prepare_schema(source)
        self.assertEqual(prepared.encoding, "direct")
        self.assertEqual(prepared.schema.properties["value"].type, "integer")
        self.assertIn("minimum", prepared.schema.properties["value"].description)
        self.assertTrue(any("inlined" in change for change in prepared.changes))
        self.assertEqual(prepared.arguments({"value": 3}), {"value": 3})
        with self.assertRaises(ValueError):
            prepared.arguments({"value": -1})
        source["$defs"]["Count"]["minimum"] = -100
        with self.assertRaises(ValueError):
            prepared.arguments({"value": -1})

    def test_ref_siblings_remain_conjunctions(self) -> None:
        source = {
            **object_schema({"$ref": "#/$defs/Word", "minLength": 3}),
            "$defs": {"Word": {"type": "string", "maxLength": 5}},
        }
        prepared = prepare_schema(source)
        self.assertEqual(prepared.encoding, "json_object")
        for value, allowed in (
            ("ab", False),
            ("abcd", True),
            ("abcdef", False),
            (4, False),
        ):
            self.assertEqual(
                valid_instance(prepared.validation, {"value": value}), allowed
            )

    def test_escaped_local_pointer_and_reordered_schema_are_deterministic(self) -> None:
        source = {
            **object_schema({"$ref": "#/$defs/a~1b~0c"}),
            "$defs": {"a/b~c": {"type": "integer"}},
        }
        one = prepare_schema(source)
        two = prepare_schema(dict(reversed(list(source.items()))))
        self.assertEqual(one, two)
        self.assertEqual(one.arguments({"value": 1}), {"value": 1})

    def test_nullable_unions_maps_and_const_preserve_source_truth_table(self) -> None:
        schemas = [
            object_schema({"type": ["integer", "null"]}),
            object_schema(
                {"anyOf": [{"type": "string", "minLength": 2}, {"type": "null"}]}
            ),
            object_schema({"oneOf": [{"type": "integer"}, {"type": "number"}]}),
            object_schema(
                {"allOf": [{"type": "number", "minimum": 0}, {"maximum": 5}]}
            ),
            object_schema(
                {"type": "object", "additionalProperties": {"type": "integer"}}
            ),
            object_schema({"const": {"key": [1, None]}}),
        ]
        values: list[Any] = [
            None,
            False,
            -1,
            0,
            2.5,
            10,
            "a",
            "abc",
            [],
            {},
            {"key": 3},
            {"key": [1, None]},
        ]
        for source, value in itertools.product(schemas, values):
            prepared = prepare_schema(source)
            self.assertEqual(prepared.encoding, "json_object")
            expected = Draft202012Validator(source).is_valid({"value": value})  # pyright: ignore[reportUnknownMemberType]
            with self.subTest(source=source, value=value):
                self.assertEqual(
                    valid_instance(prepared.validation, {"value": value}), expected
                )
                if expected:
                    self.assertEqual(
                        prepared.arguments(
                            {"arguments_json": json.dumps({"value": value})}
                        ),
                        {"value": value},
                    )
                else:
                    with self.assertRaises(ValueError):
                        prepared.arguments(
                            {"arguments_json": json.dumps({"value": value})}
                        )

    def test_native_constraints_and_const_are_reported_and_enforced(self) -> None:
        source = object_schema(
            {
                "type": "array",
                "items": {"type": "string", "const": "yes"},
                "minItems": 1,
                "maxItems": 2,
            }
        )
        prepared = prepare_schema(source)
        self.assertEqual(prepared.encoding, "direct")
        self.assertTrue(any("const" in value for value in prepared.changes))
        for value in ([], ["no"], ["yes"] * 3):
            with self.assertRaises(ValueError):
                prepared.arguments({"value": value})
        self.assertEqual(prepared.arguments({"value": ["yes"]}), {"value": ["yes"]})

    def test_formats_are_locally_enforced(self) -> None:
        for name, good, bad in (
            ("date", "2026-09-09", "2026-02-30"),
            ("uuid", "550e8400-e29b-41d4-a716-446655440000", "not-a-uuid"),
            ("ipv4", "192.0.2.1", "999.0.0.1"),
            ("ipv6", "2001:db8::1", "not-ipv6"),
        ):
            prepared = prepare_schema(object_schema({"type": "string", "format": name}))
            self.assertEqual(prepared.arguments({"value": good}), {"value": good})
            with self.assertRaises(ValueError):
                prepared.arguments({"value": bad})

    def test_external_recursive_unknown_and_expensive_schemas_rejected(self) -> None:
        for source in (
            object_schema({"$ref": "https://example.invalid/schema"}),
            object_schema({"$ref": "file:///secret"}),
            object_schema({"$ref": "#/$defs/missing"}),
            {
                **object_schema({"$ref": "#/$defs/loop"}),
                "$defs": {"loop": {"$ref": "#/$defs/loop"}},
            },
            object_schema({"type": "string", "pattern": "(a+)+$"}),
            object_schema({"type": "string", "format": "custom"}),
            object_schema({"$dynamicRef": "#node"}),
            {"type": "object", "unevaluatedProperties": False},
            object_schema({"type": "array", "prefixItems": [{"type": "integer"}]}),
            object_schema({"enum": list(range(65))}),
            object_schema({"anyOf": [{"type": "integer"}] * 17}),
            {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"},
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                prepare_schema(source)

    def test_reference_expansion_and_wrapper_description_are_bounded(self) -> None:
        definitions: dict[str, Any] = {"n0": {"type": "integer"}}
        for index in range(1, 11):
            definitions[f"n{index}"] = {
                "anyOf": [{"$ref": f"#/$defs/n{index - 1}"}] * 8
            }
        with self.assertRaises(ValueError):
            prepare_schema(
                {**object_schema({"$ref": "#/$defs/n10"}), "$defs": definitions}
            )
        with self.assertRaises(ValueError):
            prepare_schema(
                {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "x" * 6100,
                }
            )

    def test_strict_wrapper_json_rejects_duplicates_nonfinite_and_nonobjects(
        self,
    ) -> None:
        prepared = prepare_schema({"type": "object", "additionalProperties": True})
        for value in (
            '{"x":1,"x":2}',
            '{"nested":{"a":1,"a":2}}',
            '{"x":NaN}',
            '{"x":1e999}',
            "[]",
            "null",
            "not-json",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepared.arguments({"arguments_json": value})
        for args in ({}, {"arguments_json": 1}, {"arguments_json": "{}", "extra": 1}):
            with self.assertRaises(ValueError):
                prepared.arguments(args)

    def test_force_wrapper_keeps_optional_arguments_and_open_source_shape(self) -> None:
        source = {"type": "object", "properties": {"value": {"type": "string"}}}
        prepared = prepare_schema(source, force_wrapper=True)
        self.assertEqual(prepared.schema.required, ("arguments_json",))
        self.assertEqual(prepared.arguments({"arguments_json": "{}"}), {})
        self.assertEqual(
            prepared.arguments({"arguments_json": '{"other":2}'}), {"other": 2}
        )
        self.assertFalse(
            any(
                "restricted additionalProperties" in change
                for change in prepared.changes
            )
        )


class ResultClient:
    def __init__(self, output: dict[str, Any], value: dict[str, Any]) -> None:
        self.output, self.value = output, value
        self.session = self
        self.calls = 0

    async def list_tools(self, **_: Any) -> ListToolsResult:
        return ListToolsResult(
            tools=[
                Tool(
                    name="read",
                    input_schema={"type": "object"},
                    output_schema=self.output,
                )
            ]
        )

    async def call_tool(self, *_: Any) -> CallToolResult:
        self.calls += 1
        return CallToolResult(content=[], structured_content=self.value)


class SchemaRoundtripTests(IsolatedAsyncioTestCase):
    async def test_wrapped_arguments_and_nested_output_over_stdio_and_http(
        self,
    ) -> None:
        server = MCPHTTPFixture(schema_tools=True)
        server.tokens = None
        server.start()
        self.addCleanup(server.close)
        options = [
            {
                "command": sys.executable,
                "args": ("-m", "fixtures.mcp_schema_server"),
                "cwd": str(Path(__file__).parent),
            },
            {
                "transport": "streamable_http",
                "http": MCPHTTPSettings(
                    url=server.url, authentication="none", allow_loopback_http=True
                ),
            },
        ]
        for transport in options:
            config = MCPConfig.model_validate(
                {
                    **transport,
                    "tools": {"save_record": "write", "schema_write_count": "read"},
                    "allow_writes": True,
                }
            )
            async with connect_mcp(config) as dispatcher:
                self.assertEqual(
                    dispatcher.argument_encodings["save_record"], "json_object"
                )
                for number, value in enumerate((-1, 101, "wrong")):
                    result = await dispatcher.dispatch(
                        ToolCallBlock(
                            id=f"bad-{number}",
                            name="save_record",
                            args={
                                "arguments_json": json.dumps(
                                    {"record": {"kind": "fixture", "value": value}}
                                )
                            },
                        )
                    )
                    self.assertTrue(result.is_error)
                count = await dispatcher.dispatch(
                    ToolCallBlock(id="before", name="schema_write_count", args={})
                )
                self.assertEqual(
                    json.loads(count.content)["structured_content"]["writes"], 0
                )
                result = await dispatcher.dispatch(
                    ToolCallBlock(
                        id="save",
                        name="save_record",
                        args={
                            "arguments_json": json.dumps(
                                {
                                    "record": {"kind": "fixture", "value": None},
                                    "labels": {"source": "fixture"},
                                }
                            )
                        },
                    )
                )
                self.assertFalse(result.is_error)
                value = json.loads(result.content)["structured_content"]
                self.assertIsNone(value["record"]["value"])
                self.assertEqual(value["writes"], 1)
                self.assertEqual(value["labels"], {"source": "fixture"})

    async def test_invalid_structured_output_stops_session_without_retry(self) -> None:
        output = {
            **object_schema({"$ref": "#/$defs/Date"}),
            "$defs": {"Date": {"type": "string", "format": "date"}},
        }
        client = ResultClient(output, {"value": "2026-02-30"})
        config = MCPConfig(
            command=sys.executable,
            cwd=str(Path(__file__).parent),
            tools={"read": "read"},
        )
        dispatcher = MCPDispatcher(cast(Client, client), config)
        await dispatcher.discover()
        for identity in ("first", "second"):
            with self.assertRaises(MCPFailure):
                await dispatcher.dispatch(
                    ToolCallBlock(id=identity, name="read", args={})
                )
        self.assertEqual(client.calls, 1)

    async def test_force_wrapper_sends_decoded_original_arguments(self) -> None:
        config = MCPConfig(
            command=sys.executable,
            args=(str(Path(__file__).parent / "fixtures/mcp_server.py"),),
            cwd=str(Path(__file__).parent),
            tools={"echo": "read"},
            schema_mode="json_object",
        )
        async with connect_mcp(config) as dispatcher:
            result = await dispatcher.dispatch(
                ToolCallBlock(id="default", name="echo", args={"arguments_json": "{}"})
            )
            self.assertEqual(
                json.loads(result.content)["structured_content"], {"value": "default"}
            )
