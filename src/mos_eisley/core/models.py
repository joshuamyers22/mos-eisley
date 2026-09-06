"""Versioned, immutable contracts shared by adapters and review policy."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=8000)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False
    )


def canonical_bytes(value: Contract) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Brief(Contract):
    schema_version: Literal[1] = 1
    spec: Annotated[str, Field(min_length=1, max_length=128_000)]
    diff: Annotated[str, Field(min_length=1, max_length=256_000)]
    constraints: Annotated[str, Field(max_length=32_000)] = ""

    @property
    def brief_id(self) -> str:
        return digest(canonical_bytes(self))


class Evidence(Contract):
    kind: Literal["citation"] = "citation"
    source: Literal["spec", "diff", "constraints"]
    quote: Annotated[str, Field(min_length=1, max_length=4000)]
    explanation: Text


class Finding(Contract):
    location: Text
    category: Literal[
        "correctness", "spec_violation", "security", "performance", "preference"
    ]
    impact: Literal["blocker", "high", "medium", "low"]
    claim: Text
    evidence: Evidence
    suggested_fix: Text | None = None

    @property
    def finding_id(self) -> str:
        return digest(canonical_bytes(self))


class CriticSpec(Contract):
    id: Identifier
    provider: Identifier
    model: Identifier
    persona: Text


class CriticRequest(Contract):
    schema_version: Literal[1] = 1
    brief: Brief
    persona: Text


class Critique(Contract):
    schema_version: Literal[1] = 1
    findings: Annotated[tuple[Finding, ...], Field(max_length=50)] = ()


class CriticResult(Contract):
    critic: CriticSpec
    status: Literal["completed", "error"]
    critique: Critique | None = None
    error: (
        Literal["provider_error", "timeout", "invalid_evidence", "budget_exceeded"]
        | None
    ) = None

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.status == "completed" and (
            self.critique is None or self.error is not None
        ):
            raise ValueError("completed critic requires a critique and no error")
        if self.status == "error" and (self.critique is not None or self.error is None):
            raise ValueError("failed critic requires an error and no critique")
        return self


class JudgeRequest(Contract):
    schema_version: Literal[1] = 1
    brief: Brief
    findings: tuple[Finding, ...]


class JudgeDecision(Contract):
    schema_version: Literal[1] = 1
    upheld: tuple[Digest, ...] = ()
    rationale: Text


class ReviewPolicy(Contract):
    schema_version: Literal[1] = 1
    min_critics: Annotated[int, Field(ge=1, le=8)] = 2
    min_providers: Annotated[int, Field(ge=1, le=8)] = 2
    max_request_bytes: Annotated[int, Field(ge=1024, le=2_000_000)] = 512_000
    timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 10.0

    @model_validator(mode="after")
    def valid_quorum(self) -> Self:
        if self.min_providers > self.min_critics:
            raise ValueError("provider quorum cannot exceed critic quorum")
        return self


class Verdict(Contract):
    schema_version: Literal[1] = 1
    brief_id: Digest
    decision: Literal["accept", "revise", "reject", "infrastructure_error"]
    findings: tuple[Finding, ...] = ()
    required_changes: tuple[Digest, ...] = ()
    rationale: Text


class ReviewResult(Contract):
    schema_version: Literal[1] = 1
    critics: tuple[CriticResult, ...]
    judge_request: JudgeRequest | None = None
    judge_decision: JudgeDecision | None = None
    verdict: Verdict
