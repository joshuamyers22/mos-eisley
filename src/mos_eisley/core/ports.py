"""The review use case owns this boundary; vendor SDKs remain outside it."""

from typing import Protocol

from mos_eisley.core.models import (
    CriticRequest,
    CriticSpec,
    Critique,
    JudgeDecision,
    JudgeRequest,
)
from mos_eisley.core.protocol import (
    JournalEvent,
    ModelRequest,
    ModelResponse,
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
)


class ProviderError(Exception):
    """An expected adapter failure; details must not enter public diagnostics."""


class Reviewer(Protocol):
    async def critique(
        self, critic: CriticSpec, request: CriticRequest
    ) -> Critique: ...

    async def judge(self, request: JudgeRequest) -> JudgeDecision: ...


class ModelClient(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...


class ToolDispatcher(Protocol):
    @property
    def definitions(self) -> tuple[ToolDefinition, ...]: ...

    async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock: ...


class Journal(Protocol):
    def record(self, event: JournalEvent) -> None: ...
