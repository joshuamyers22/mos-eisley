"""Fail-closed lowering into the canonical provider-neutral schema subset."""

from typing import Any

from jsonschema import Draft202012Validator

from mos_eisley.core.protocol import ToolSchema


def lower_schema(source: dict[str, Any]) -> tuple[ToolSchema, tuple[str, ...]]:
    Draft202012Validator.check_schema(source)
    changes: list[str] = []

    def lower(value: dict[str, Any], path: str, depth: int) -> ToolSchema:
        if depth > 12:
            raise ValueError("MCP input schema is too deep")
        allowed = {
            "type",
            "description",
            "title",
            "default",
            "properties",
            "required",
            "items",
            "enum",
            "additionalProperties",
        }
        if set(value) - allowed:
            raise ValueError("unsupported MCP input schema keyword")
        for key in ("title", "default"):
            if key in value:
                changes.append(f"{path}: omitted {key} metadata")
        if value.get("additionalProperties", False) is not False:
            raise ValueError("open MCP input objects are unsupported")
        if value.get("type") == "object" and "additionalProperties" not in value:
            changes.append(f"{path}: restricted additionalProperties to false")
        fields = {
            key: item
            for key, item in value.items()
            if key
            not in {
                "title",
                "default",
                "additionalProperties",
                "properties",
                "items",
                "required",
                "enum",
            }
        }
        fields["properties"] = {
            key: lower(item, f"{path}.{key}", depth + 1)
            for key, item in value.get("properties", {}).items()
        }
        fields["required"] = tuple(value.get("required", ()))
        fields["enum"] = tuple(value.get("enum", ()))
        if "items" in value:
            fields["items"] = lower(value["items"], f"{path}[]", depth + 1)
        return ToolSchema.model_validate(fields)

    return lower(source, "$", 0), tuple(changes)
