"""Nested reference, nullable and dictionary tools used only by fixtures."""

from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from pydantic import BaseModel, Field


class Record(BaseModel):
    kind: Literal["fixture"]
    value: Annotated[int, Field(ge=0, le=100)] | None


class SavedRecord(BaseModel):
    record: Record
    labels: dict[str, str]
    writes: int


def add_schema_tools(server: MCPServer[Any]) -> None:
    writes = 0

    def save_record(
        record: Record, labels: dict[str, str] | None = None
    ) -> SavedRecord:
        nonlocal writes
        writes += 1
        return SavedRecord(record=record, labels=labels or {}, writes=writes)

    def schema_write_count() -> dict[str, int]:
        return {"writes": writes}

    server.add_tool(save_record)
    server.add_tool(schema_write_count)
