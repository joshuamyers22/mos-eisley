"""The review use case owns this boundary; vendor SDKs remain outside it."""

from typing import Protocol

from mos_eisley.core.models import (
    CriticRequest,
    CriticSpec,
    Critique,
    JudgeDecision,
    JudgeRequest,
)


class ProviderError(Exception):
    """An expected adapter failure; details must not enter public diagnostics."""


class Reviewer(Protocol):
    async def critique(
        self, critic: CriticSpec, request: CriticRequest
    ) -> Critique: ...

    async def judge(self, request: JudgeRequest) -> JudgeDecision: ...
