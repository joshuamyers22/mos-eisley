"""Captured result lineage and deterministic, cell-grounded answer rendering."""

import json
from datetime import datetime
from typing import Annotated, Literal, cast

from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import ToolCallBlock, ToolResultBlock

ContextMode = Literal["promoted", "raw"]
RAW_TOOLS = frozenset(
    {
        "list_sources",
        "list_parquet",
        "describe_parquet",
        "query_parquet",
        "list_postgres_tables",
        "describe_postgres",
        "query_postgres",
    }
)
METADATA_TOOLS = frozenset(
    {
        "get_semantic_context",
        "list_metrics",
        "list_sources",
        "list_parquet",
        "describe_parquet",
        "list_postgres_tables",
        "describe_postgres",
    }
)

Scalar = str | int | float | bool | None


class CellClaim(Contract):
    result_id: Identifier
    row: Annotated[int, Field(ge=0, le=9999)]
    column: Annotated[str, Field(min_length=1, max_length=256)]
    value: Scalar


class AnalysisAnswer(Contract):
    status: Literal["answer", "clarify", "unavailable"]
    text: Annotated[str, Field(min_length=1, max_length=8000)]
    result_ids: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()
    claims: Annotated[tuple[CellClaim, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def unique_sources(self) -> "AnalysisAnswer":
        if len(set(self.result_ids)) != len(self.result_ids):
            raise ValueError("duplicate analytical evidence references")
        return self


class AnalysisEvidence(Contract):
    result_id: Identifier
    tool: Identifier
    result_sha256: Digest
    complete: bool


class ToolTrace(Contract):
    call: ToolCallBlock
    started_at: datetime
    completed_at: datetime
    outcome: Literal["accepted", "error"]
    result_id: Identifier | None = None
    response: ToolResultBlock | None = None

    @model_validator(mode="after")
    def coherent(self) -> "ToolTrace":
        if (
            self.started_at.tzinfo is None
            or self.completed_at.tzinfo is None
            or self.completed_at < self.started_at
        ):
            raise ValueError("invalid trace timestamps")
        if self.outcome == "accepted":
            if (
                self.response is None
                or self.result_id is None
                or self.response.is_error
                or self.response.call_id != self.call.id
                or self.response.name != self.call.name
            ):
                raise ValueError("trace response does not match its call")
        elif self.response is not None or self.result_id is not None:
            raise ValueError("failed trace cannot supply answer evidence")
        return self


def strict_object(payload: str) -> dict[str, JsonValue]:
    def pairs(items: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def constant(_: str) -> JsonValue:
        raise ValueError("non-finite JSON number")

    value = json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return cast(dict[str, JsonValue], value)


def source_data(trace: ToolTrace) -> dict[str, JsonValue]:
    if trace.outcome != "accepted" or trace.response is None:
        raise ValueError("result is not successful evidence")
    raw = strict_object(trace.response.content)
    source = raw.get("structured_content")
    if not isinstance(source, dict):
        raise ValueError("result is not a structured object")
    return cast(dict[str, JsonValue], source)


def complete_table(trace: ToolTrace) -> tuple[list[str], list[list[JsonValue]]]:
    source = source_data(trace)
    if source.get("truncated") is not False:
        raise ValueError("table completeness must be explicit")
    columns, rows = source.get("columns"), source.get("rows")
    if (
        not isinstance(columns, list)
        or not columns
        or len(columns) > 256
        or any(not isinstance(col, str) or not col or len(col) > 256 for col in columns)
        or not isinstance(rows, list)
        or len(rows) > 10000
    ):
        raise ValueError("unsupported tabular result")
    names = cast(list[str], columns)
    if len(set(names)) != len(names) or any(
        not isinstance(row, list) or len(row) != len(names) for row in rows
    ):
        raise ValueError("ambiguous table shape")
    return names, cast(list[list[JsonValue]], rows)


def checked_answer(
    answer: AnalysisAnswer, traces: tuple[ToolTrace, ...]
) -> AnalysisAnswer:
    available = {
        trace.result_id: trace for trace in traces if trace.outcome == "accepted"
    }
    if answer.status != "answer":
        if answer.claims or answer.result_ids:
            raise ValueError(
                "clarification and unavailable answers cannot assert values"
            )
        return answer
    if not answer.claims or set(answer.result_ids) != {
        c.result_id for c in answer.claims
    }:
        raise ValueError("answers require explicit cell claims and matching sources")
    seen: set[tuple[str, int, str]] = set()
    lines: list[str] = []
    for claim in answer.claims:
        trace = available.get(claim.result_id)
        if trace is None or trace.call.name in METADATA_TOOLS:
            raise ValueError("claim refers to unavailable evidence")
        columns, rows = complete_table(trace)
        key = (claim.result_id, claim.row, claim.column)
        if key in seen or claim.row >= len(rows) or claim.column not in columns:
            raise ValueError("claim refers to an ambiguous or absent cell")
        seen.add(key)
        value = rows[claim.row][columns.index(claim.column)]
        if type(value) not in (str, int, float, bool, type(None)) or (
            type(value) is not type(claim.value) or value != claim.value
        ):
            raise ValueError("claimed value differs from the captured cell")
        # All answer text is controller-rendered. Model prose is deliberately not
        # copied into an answer that advertises checked values.
        lines.append(
            f"{claim.result_id}, row {claim.row}, column "
            f"{json.dumps(claim.column, ensure_ascii=False)}: "
            f"{json.dumps(value, ensure_ascii=False, allow_nan=False)}"
        )
    return AnalysisAnswer(
        status="answer",
        text="\n".join(lines),
        result_ids=answer.result_ids,
        claims=answer.claims,
    )


def verify_evidence(
    evidence: tuple[AnalysisEvidence, ...],
    traces: tuple[ToolTrace, ...],
    revision: str | None,
    context_mode: ContextMode = "promoted",
) -> None:
    if (context_mode == "promoted") != (revision is not None):
        raise ValueError("context mode and semantic revision disagree")
    bootstrap = "get_semantic_context" if context_mode == "promoted" else "list_sources"
    if (
        not traces
        or traces[0].call.name != bootstrap
        or traces[0].outcome != "accepted"
    ):
        raise ValueError("evidence trail must start with the configured bootstrap")
    if context_mode == "raw" and any(
        trace.outcome == "accepted" and trace.call.name not in RAW_TOOLS
        for trace in traces
    ):
        raise ValueError("raw evidence includes an out-of-profile tool")
    accepted = [trace for trace in traces if trace.outcome == "accepted"]
    if len({trace.call.id for trace in traces}) != len(traces):
        raise ValueError("duplicate tool trace call IDs")
    if len(accepted) != len(evidence) or len({e.result_id for e in evidence}) != len(
        evidence
    ):
        raise ValueError("evidence set does not match the tool trail")
    for item, trace in zip(evidence, accepted, strict=True):
        assert trace.response is not None
        source = source_data(trace)
        if (
            item.result_id != trace.result_id
            or item.tool != trace.call.name
            or not item.complete
            or item.result_sha256 != digest(canonical_bytes(trace.response))
            or ("truncated" in source and source["truncated"] is not False)
        ):
            raise ValueError("evidence identity or completeness mismatch")
        if (
            trace.call.name in {"get_semantic_context", "run_metric"}
            and source.get("revision") != revision
        ):
            raise ValueError("evidence semantic revision mismatch")
        if trace.call.name == "run_metric":
            args = json.loads(cast(str, trace.call.args.get("arguments_json")))
            if args.get("revision") != revision:
                raise ValueError("metric call revision mismatch")


class SQLRecord(Contract):
    call_id: Identifier
    tool: Identifier
    result_id: Identifier | None
    arguments: dict[str, JsonValue]
    submitted_sql: str | None
    normalized_sql: str | None
    source_reported_metadata: dict[str, JsonValue]
    complete: bool


def sql_records(traces: tuple[ToolTrace, ...]) -> tuple[SQLRecord, ...]:
    records: list[SQLRecord] = []
    for trace in traces:
        if trace.call.name not in {"run_metric", "query_parquet", "query_postgres"}:
            continue
        try:
            arguments = strict_object(cast(str, trace.call.args.get("arguments_json")))
        except (ValueError, TypeError):
            if trace.outcome == "accepted":
                raise ValueError(
                    "accepted query arguments must be a JSON object"
                ) from None
            arguments = {}  # The original rejected bytes remain in the tool trace.
        source = source_data(trace) if trace.outcome == "accepted" else {}
        submitted = arguments.get("sql", source.get("submitted_sql"))
        normalized = source.get("normalized_sql")
        records.append(
            SQLRecord(
                call_id=trace.call.id,
                tool=trace.call.name,
                result_id=trace.result_id,
                arguments=arguments,
                submitted_sql=submitted if isinstance(submitted, str) else None,
                normalized_sql=normalized if isinstance(normalized, str) else None,
                source_reported_metadata={
                    key: source[key]
                    for key in (
                        "metric",
                        "revision",
                        "backend",
                        "source",
                        "paths",
                        "units",
                        "grain",
                        "timezone",
                        "started_at",
                        "completed_at",
                        "data_snapshot",
                    )
                    if key in source
                },
                complete=trace.outcome == "accepted"
                and source.get("truncated") is False,
            )
        )
    return tuple(records)
