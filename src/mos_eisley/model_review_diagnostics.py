"""Strict review validation with fixed, bounded, content-free failure reasons."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, cast

from pydantic import Field, ValidationError

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest

MAX_REVIEW_BYTES = 64_000
MAX_ISSUES = 16
Count = Annotated[int, Field(ge=0, le=1_000_000)]
Shape = Literal["missing", "object", "array", "string", "number", "boolean", "null"]
FieldName = Literal["root", "subject_sha256", "decision", "findings", "unrecognized"]
Reason = Literal[
    "input_limit",
    "invalid_encoding",
    "invalid_json",
    "duplicate_keys",
    "nesting_limit",
    "wrong_root",
    "missing_field",
    "extra_field",
    "wrong_type",
    "invalid_digest",
    "invalid_decision",
    "finding_too_long",
    "too_many_findings",
    "decision_findings_conflict",
    "subject_mismatch",
    "schema_error",
]


class ReviewIssue(Contract):
    code: Reason
    field: FieldName


class ModelReviewReceipt(Contract):
    schema_version: Literal[1] = 1
    status: Literal["valid", "invalid"]
    stage: Literal["input", "json", "schema", "binding", "complete"]
    artifact_sha256: Digest | None
    input_characters: Count
    input_bytes: Count | None
    json_prefix: Literal["empty", "object", "array", "markdown_fence", "other"]
    json_root: Shape = "missing"
    decision_token: Literal[
        "missing", "accept", "revise", "approve", "reject", "other"
    ] = "missing"
    findings_shape: Shape = "missing"
    finding_count: Count | None = None
    finding_item_shapes: Annotated[tuple[Shape, ...], Field(max_length=MAX_ISSUES)] = ()
    extra_fields: Count = 0
    subject_matches: bool | None = None
    error_count: Count = 0
    issues_truncated: bool = False
    issues: Annotated[tuple[ReviewIssue, ...], Field(max_length=MAX_ISSUES)] = ()


class ModelReviewArtifactError(ValueError):
    def __init__(self, receipt: ModelReviewReceipt) -> None:
        super().__init__(
            "Review adjudicated a different frozen subject."
            if receipt.stage == "binding"
            else "Live coding model returned an invalid frozen artifact."
        )
        self.receipt = receipt


class _DuplicateKey(ValueError):
    pass


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    try:
        return unique_object(pairs)
    except ValueError:
        raise _DuplicateKey from None


def _shape(value: object) -> Shape:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _issue(
    kind: str, location: tuple[str | int, ...], receipt: ModelReviewReceipt
) -> ReviewIssue:
    first = location[0] if location else "root"
    field: FieldName = (
        "subject_sha256"
        if first == "subject_sha256"
        else "decision"
        if first == "decision"
        else "findings"
        if first == "findings"
        else "root"
        if not location
        else "unrecognized"
    )
    code: Reason = (
        "missing_field"
        if kind == "missing"
        else "extra_field"
        if kind == "extra_forbidden"
        else "invalid_digest"
        if kind == "string_pattern_mismatch" and field == "subject_sha256"
        else "invalid_decision"
        if kind == "literal_error" and field == "decision"
        else "finding_too_long"
        if kind == "string_too_long" and field == "findings"
        else "too_many_findings"
        if kind == "too_long" and field == "findings"
        else "wrong_type"
        if kind in ("string_type", "tuple_type", "list_type", "model_type")
        else "decision_findings_conflict"
        if kind == "value_error"
        and field == "root"
        and (
            (receipt.decision_token == "accept" and (receipt.finding_count or 0) > 0)
            or (
                receipt.decision_token == "revise"
                and receipt.findings_shape in ("missing", "array")
                and not receipt.finding_count
            )
        )
        else "schema_error"
    )
    return ReviewIssue(code=code, field=field)


def validate_model_review[T: Contract](
    model: type[T], text: str, *, expected_subject: str | None = None
) -> tuple[T, ModelReviewReceipt]:
    """Never coerce, strip fences, repair JSON or weaken subject/decision gates."""
    prefix = text[:MAX_REVIEW_BYTES].lstrip()
    framing: Literal["empty", "object", "array", "markdown_fence", "other"] = (
        "empty"
        if not prefix
        else "markdown_fence"
        if prefix.startswith("```")
        else "object"
        if prefix.startswith("{")
        else "array"
        if prefix.startswith("[")
        else "other"
    )
    receipt = ModelReviewReceipt(
        status="invalid",
        stage="input",
        artifact_sha256=None,
        input_characters=min(len(text), 1_000_000),
        input_bytes=None,
        json_prefix=framing,
    )

    def fail(
        code: Reason, stage: Literal["input", "json", "schema", "binding"]
    ) -> ModelReviewArtifactError:
        return ModelReviewArtifactError(
            receipt.model_copy(
                update={
                    "stage": stage,
                    "error_count": 1,
                    "issues": (
                        ReviewIssue(
                            code=code,
                            field="subject_sha256"
                            if code == "subject_mismatch"
                            else "root",
                        ),
                    ),
                }
            )
        )

    if len(text) > MAX_REVIEW_BYTES:
        raise fail("input_limit", "input")
    try:
        raw = text.encode("utf-8")
    except UnicodeError:
        raise fail("invalid_encoding", "input") from None
    receipt = receipt.model_copy(
        update={
            "input_bytes": len(raw),
            "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    if len(raw) > MAX_REVIEW_BYTES:
        raise fail("input_limit", "input")
    try:
        parsed: object = json.loads(text, object_pairs_hook=_unique_pairs)
    except _DuplicateKey:
        raise fail("duplicate_keys", "json") from None
    except RecursionError:
        raise fail("nesting_limit", "json") from None
    except ValueError:
        raise fail("invalid_json", "json") from None
    receipt = receipt.model_copy(update={"json_root": _shape(parsed)})
    if not isinstance(parsed, dict):
        raise fail("wrong_root", "schema")
    fields = cast(dict[str, object], parsed)
    decision = fields.get("decision")
    token: Literal["missing", "accept", "revise", "approve", "reject", "other"] = (
        "missing"
        if "decision" not in fields
        else "accept"
        if decision == "accept"
        else "revise"
        if decision == "revise"
        else "approve"
        if decision == "approve"
        else "reject"
        if decision == "reject"
        else "other"
    )
    findings = fields.get("findings")
    items: list[object] = (
        cast(list[object], findings) if isinstance(findings, list) else []
    )
    receipt = receipt.model_copy(
        update={
            "decision_token": token,
            "findings_shape": _shape(fields.get("findings"))
            if "findings" in fields
            else "missing",
            "finding_count": min(len(items), 1_000_000)
            if isinstance(findings, list)
            else None,
            "finding_item_shapes": tuple(_shape(v) for v in items[:MAX_ISSUES]),
            "extra_fields": min(
                len(set(fields) - {"subject_sha256", "decision", "findings"}), 1_000_000
            ),
        }
    )
    try:
        value = model.model_validate_json(text)
    except ValidationError as error:
        errors = error.errors(
            include_input=False, include_context=False, include_url=False
        )
        issues = tuple(
            _issue(e["type"], e["loc"], receipt) for e in errors[:MAX_ISSUES]
        )
        raise ModelReviewArtifactError(
            receipt.model_copy(
                update={
                    "stage": "schema",
                    "issues": issues,
                    "error_count": min(len(errors), 1_000_000),
                    "issues_truncated": len(errors) > MAX_ISSUES,
                }
            )
        ) from None
    if expected_subject is not None:
        actual: object = value.model_dump(mode="json").get("subject_sha256")
        matches = actual == expected_subject
        receipt = receipt.model_copy(update={"subject_matches": matches})
        if not matches:
            raise fail("subject_mismatch", "binding")
    return value, receipt.model_copy(update={"status": "valid", "stage": "complete"})
