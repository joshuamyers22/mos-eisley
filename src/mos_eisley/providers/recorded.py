"""Fixtures are bound to exact requests and are never represented as live reviews."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    CriticSpec,
    Critique,
    Digest,
    JudgeDecision,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ProviderError


class CriticRecording(Contract):
    critic: CriticSpec
    request_sha256: Digest
    response: Critique | None = None


class Cassette(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["recorded"] = "recorded"
    brief_id: Digest
    critics: Annotated[tuple[CriticRecording, ...], Field(min_length=1, max_length=8)]
    judge_request_sha256: Digest | None = None
    judge_response: JudgeDecision | None = None

    @model_validator(mode="after")
    def unique_critics(self) -> Self:
        if len({r.critic.id for r in self.critics}) != len(self.critics):
            raise ValueError("duplicate cassette critic ID")
        return self


class RecordedReviewer:
    def __init__(self, cassette: Cassette) -> None:
        self.cassette = cassette

    async def critique(self, critic: CriticSpec, request: CriticRequest) -> Critique:
        if request.brief.brief_id != self.cassette.brief_id:
            raise ProviderError("brief mismatch")
        for recording in self.cassette.critics:
            if recording.critic == critic:
                if recording.request_sha256 != digest(canonical_bytes(request)):
                    raise ProviderError("request mismatch")
                if recording.response is None:
                    raise ProviderError("recorded failure")
                return recording.response
        raise ProviderError("unknown critic")

    async def judge(self, request: JudgeRequest) -> JudgeDecision:
        if self.cassette.judge_request_sha256 != digest(canonical_bytes(request)):
            raise ProviderError("judge request mismatch")
        if self.cassette.judge_response is None:
            raise ProviderError("recorded judge failure")
        return self.cassette.judge_response
