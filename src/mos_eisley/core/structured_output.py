"""Provider-neutral helpers for strict JSON Schema response contracts."""

from __future__ import annotations

from pydantic import JsonValue


def strict_json_schema(value: JsonValue) -> JsonValue:
    """Return a provider-strict schema without mutating the source schema."""
    if isinstance(value, list):
        return [strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, JsonValue] = {
        key: strict_json_schema(item)
        for key, item in value.items()
        if key not in ("default", "title")
    }
    if result.get("type") == "object":
        if "properties" not in result:
            properties = {}
            result["properties"] = properties
        else:
            properties = result["properties"]
        if not isinstance(properties, dict):
            raise ValueError("object schema properties must be an object")
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result
