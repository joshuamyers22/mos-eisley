"""Strict response-schema normalization fails closed on unsupported objects."""

from copy import deepcopy
from typing import cast
from unittest import TestCase

from pydantic import JsonValue

from mos_eisley.core.structured_output import strict_json_schema


class StrictJsonSchemaTests(TestCase):
    def test_missing_properties_becomes_an_explicit_empty_strict_object(self) -> None:
        source: JsonValue = {"type": "object", "title": "Result"}
        before = deepcopy(source)
        self.assertEqual(
            strict_json_schema(source),
            {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        )
        self.assertEqual(source, before)

    def test_malformed_properties_rejects_at_every_nested_object(self) -> None:
        properties_values: tuple[JsonValue, ...] = (None, [], "wrong", 1, True)
        for properties in properties_values:
            schema: JsonValue = {
                "type": "object",
                "properties": {"nested": {"type": "object", "properties": properties}},
            }
            with (
                self.subTest(properties=properties),
                self.assertRaisesRegex(ValueError, "properties must be an object"),
            ):
                strict_json_schema(schema)

    def test_every_object_is_recursively_strict(self) -> None:
        source: JsonValue = {
            "type": "object",
            "properties": {
                "empty": {"type": "object"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                    },
                },
            },
        }
        normalized = strict_json_schema(source)
        assert isinstance(normalized, dict)

        def inspect(value: JsonValue) -> None:
            if isinstance(value, list):
                for item in value:
                    inspect(item)
            elif isinstance(value, dict):
                if value.get("type") == "object":
                    properties = value.get("properties")
                    self.assertIsInstance(properties, dict)
                    assert isinstance(properties, dict)
                    required = value.get("required")
                    self.assertIsInstance(required, list)
                    assert isinstance(required, list)
                    self.assertTrue(all(isinstance(item, str) for item in required))
                    self.assertEqual(set(cast(list[str], required)), set(properties))
                    self.assertIs(value["additionalProperties"], False)
                for item in value.values():
                    inspect(item)

        inspect(normalized)
