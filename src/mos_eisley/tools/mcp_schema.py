"""Bounded offline schema compilation and explicit canonical argument adapters."""

import json
from dataclasses import dataclass
from typing import Any, Literal, cast
from urllib.parse import unquote

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import JsonValue

from mos_eisley.core.protocol import ToolSchema

MAX_SCHEMA_BYTES = 65536
MAX_SCHEMA_NODES = 512
MAX_VALUE_NODES = 8192
FORMATS = {"date", "uuid", "ipv4", "ipv6"}
ANNOTATIONS = {
    "title",
    "default",
    "examples",
    "$comment",
    "deprecated",
    "readOnly",
    "writeOnly",
}
CONSTRAINTS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "minProperties",
    "maxProperties",
    "format",
}
BASE = {
    "type",
    "description",
    "properties",
    "required",
    "items",
    "enum",
    "additionalProperties",
}
COMBINATORS = {"anyOf", "oneOf", "allOf"}
ALLOWED = (
    BASE
    | ANNOTATIONS
    | CONSTRAINTS
    | COMBINATORS
    | {"$ref", "$defs", "definitions", "$schema", "const"}
)


def compact(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def bounded_value(value: Any, *, limit: int = MAX_VALUE_NODES) -> None:
    count = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > limit or depth > 24:
            raise ValueError("MCP JSON value exceeds structural limits")
        if isinstance(item, dict):
            for key, child in cast(dict[Any, Any], item).items():
                if not isinstance(key, str):
                    raise ValueError("MCP JSON object keys must be strings")
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in cast(list[Any], item):
                visit(child, depth + 1)

    visit(value, 0)


def compile_schema(source: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Validate only supported keywords, then inline acyclic local JSON pointers."""
    bounded_value(source)
    if len(compact(source).encode()) > MAX_SCHEMA_BYTES:
        raise ValueError("MCP schema exceeds byte limit")
    source = json.loads(compact(source))  # Own the immutable session snapshot.
    changes: list[str] = []
    nodes = 0

    def audit(value: Any, depth: int) -> None:
        if depth > 12 or not isinstance(value, (dict, bool)):
            raise ValueError("unsupported MCP schema shape or depth")
        if isinstance(value, bool):
            return
        value = cast(dict[str, Any], value)
        if set(value) - ALLOWED:
            raise ValueError("unsupported MCP schema keyword")
        if (
            "$schema" in value
            and value["$schema"] != "https://json-schema.org/draft/2020-12/schema"
        ):
            raise ValueError("only JSON Schema 2020-12 is supported")
        if "format" in value and value["format"] not in FORMATS:
            raise ValueError("unsupported MCP schema format")
        if "$ref" in value:
            ref = value["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise ValueError("only local JSON Pointer references are supported")
        for key in ("enum", "required"):
            if key in value and (
                not isinstance(value[key], list) or len(value[key]) > 64
            ):
                raise ValueError("MCP schema collection exceeds limit")
        for key in ("properties", "$defs", "definitions"):
            group = value.get(key, {})
            if not isinstance(group, dict) or len(cast(dict[str, Any], group)) > 64:
                raise ValueError("MCP schema property collection exceeds limit")
            for item in cast(dict[str, Any], group).values():
                audit(item, depth + 1)
        for key in ("items", "additionalProperties"):
            if key in value:
                audit(value[key], depth + 1)
        for key in COMBINATORS:
            branches = value.get(key, [])
            if not isinstance(branches, list) or len(cast(list[Any], branches)) > 16:
                raise ValueError("MCP schema branch collection exceeds limit")
            for item in cast(list[Any], branches):
                audit(item, depth + 1)

    # Meta-schema validation does not fetch schemas. Audit additionally rejects
    # executable/unknown vocabularies and all network-capable reference forms.
    audit(source, 0)
    Draft202012Validator.check_schema(source)

    def target(ref: str) -> Any:
        current: Any = source
        for raw in unquote(ref[2:]).split("/"):
            # RFC 6901 permits only ~0/~1 escapes.
            if "~" in raw.replace("~0", "").replace("~1", ""):
                raise ValueError("invalid local schema reference")
            key = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict):
                if key not in current:
                    raise ValueError("missing local schema reference")
                current = cast(dict[str, Any], current)[key]
            elif (
                isinstance(current, list)
                and key.isdecimal()
                and str(int(key)) == key
                and int(key) < len(cast(list[Any], current))
            ):
                current = cast(list[Any], current)[int(key)]
            else:
                raise ValueError("invalid local schema reference target")
        audit(current, 0)
        return current

    def expand(value: Any, path: str, depth: int, active: tuple[str, ...]) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_SCHEMA_NODES or depth > 12:
            raise ValueError("expanded MCP schema exceeds structural limits")
        if isinstance(value, bool):
            return value
        result: dict[str, Any] = {}
        for key in sorted(value):
            item = value[key]
            if key in {"$defs", "definitions", "$schema", "$ref"}:
                continue
            if key == "properties":
                result[key] = {
                    name: expand(child, f"{path}.{name}", depth + 1, active)
                    for name, child in sorted(item.items())
                }
            elif key in {"items", "additionalProperties"}:
                result[key] = expand(item, f"{path}/{key}", depth + 1, active)
            elif key in COMBINATORS:
                result[key] = [
                    expand(child, f"{path}/{key}/{index}", depth + 1, active)
                    for index, child in enumerate(item)
                ]
            else:
                result[key] = item
        if "$ref" in value:
            ref = value["$ref"]
            if ref in active:
                raise ValueError("recursive MCP schema references are unsupported")
            resolved = expand(target(ref), path, depth + 1, (*active, ref))
            changes.append(f"{path}: inlined local reference {ref}")
            # $ref siblings are conjunctions in 2020-12; never overwrite them.
            if result:
                return {"allOf": [resolved, result]}
            return resolved
        return result

    compiled = expand(source, "$", 0, ())
    if (
        not isinstance(compiled, dict)
        or len(compact(compiled).encode()) > MAX_SCHEMA_BYTES
    ):
        raise ValueError("expanded MCP schema exceeds byte limit or root shape")
    return cast(dict[str, Any], compiled), tuple(changes)


def valid_instance(schema: dict[str, Any], value: Any) -> bool:
    try:
        bounded_value(value)
        compact(value)  # Reject NaN/Infinity and non-JSON values before validation.
        validator = Draft202012Validator(schema, format_checker=FormatChecker(FORMATS))
        return validator.is_valid(value)  # pyright: ignore[reportUnknownMemberType]
    except Exception:
        return False


@dataclass(frozen=True)
class PreparedSchema:
    schema: ToolSchema
    validation: dict[str, Any]
    changes: tuple[str, ...]
    encoding: Literal["direct", "json_object"] = "direct"
    instructions: str = ""

    def arguments(self, supplied: dict[str, Any]) -> dict[str, JsonValue]:
        value: Any = supplied
        if self.encoding == "json_object":
            if set(supplied) != {"arguments_json"} or not isinstance(
                supplied["arguments_json"], str
            ):
                raise ValueError("wrapped MCP arguments require arguments_json")

            def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, item in pairs:
                    if key in result:
                        raise ValueError("duplicate JSON object key")
                    result[key] = item
                return result

            value = json.loads(supplied["arguments_json"], object_pairs_hook=unique)
        if not isinstance(value, dict) or not valid_instance(self.validation, value):
            raise ValueError("invalid MCP arguments")
        return cast(dict[str, JsonValue], value)


def prepare_schema(
    source: dict[str, Any], *, force_wrapper: bool = False
) -> PreparedSchema:
    compiled, references = compile_schema(source)

    def permits_object(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        kind = value.get("type")
        if (
            kind is not None
            and kind != "object"
            and not (isinstance(kind, list) and "object" in kind)
        ):
            return False
        if "const" in value and not isinstance(value["const"], dict):
            return False
        if "enum" in value and not any(
            isinstance(item, dict) for item in value["enum"]
        ):
            return False
        if not all(permits_object(item) for item in value.get("allOf", [])):
            return False
        return all(
            any(permits_object(item) for item in value[key])
            for key in ("anyOf", "oneOf")
            if key in value
        )

    if not permits_object(compiled):
        raise ValueError("MCP input must permit an object")
    changes = list(references)

    def lower(value: Any, path: str, depth: int) -> ToolSchema:
        if depth > 12 or not isinstance(value, dict):
            raise ValueError("MCP schema requires an argument wrapper")
        value = cast(dict[str, Any], value)
        if set(value) - (BASE | ANNOTATIONS | CONSTRAINTS | {"const"}):
            raise ValueError("MCP schema requires an argument wrapper")
        for key in sorted(ANNOTATIONS):
            if key in value:
                changes.append(f"{path}: omitted {key} metadata")
        if value.get("additionalProperties", False) is not False:
            raise ValueError("open MCP objects require an argument wrapper")
        if value.get("type") == "object" and "additionalProperties" not in value:
            changes.append(f"{path}: restricted additionalProperties to false")
        fields = {
            key: item for key, item in value.items() if key in {"type", "description"}
        }
        constraints = {key: value[key] for key in sorted(CONSTRAINTS & set(value))}
        if constraints:
            hint = "Validated by client: " + compact(constraints)
            fields["description"] = (
                fields.get("description", "") + "\n" + hint
            ).strip()
            changes.append(
                f"{path}: retained local validation for {compact(constraints)}; "
                "added description hint"
            )
        fields["properties"] = {
            key: lower(item, f"{path}.{key}", depth + 1)
            for key, item in sorted(value.get("properties", {}).items())
        }
        fields["required"] = tuple(value.get("required", ()))
        fields["enum"] = tuple(value.get("enum", ()))
        if "const" in value:
            if "enum" in value and value["const"] not in value["enum"]:
                raise ValueError("inconsistent enum/const")
            fields["enum"] = (value["const"],)
            changes.append(f"{path}: lowered const to single-value enum")
        if "items" in value:
            fields["items"] = lower(value["items"], f"{path}[]", depth + 1)
        return ToolSchema.model_validate(fields)

    if not force_wrapper:
        try:
            schema = lower(compiled, "$", 0)
            return PreparedSchema(schema, compiled, tuple(changes))
        except ValueError:
            pass
    instructions = (
        "Pass exactly one arguments_json string containing the original JSON object. "
        "The client decodes it and validates every constraint "
        "before calling the server. "
        "Original input schema: " + compact(compiled)
    )
    if len(instructions.encode()) > 6000:
        raise ValueError("wrapped MCP schema instructions exceed limit")
    wrapper = ToolSchema(
        type="object",
        properties={
            "arguments_json": ToolSchema(
                type="string",
                description="JSON object matching the schema in the tool description",
            )
        },
        required=("arguments_json",),
    )
    return PreparedSchema(
        wrapper,
        compiled,
        (
            *references,
            "$: encoded original object as arguments_json; "
            "all source constraints remain locally enforced",
        ),
        "json_object",
        instructions,
    )


def lower_schema(source: dict[str, Any]) -> tuple[ToolSchema, tuple[str, ...]]:
    prepared = prepare_schema(source)
    return prepared.schema, prepared.changes
