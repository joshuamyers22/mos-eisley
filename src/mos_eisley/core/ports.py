"""The review use case owns this boundary; vendor SDKs remain outside it."""

from typing import Literal, Protocol

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

ProviderFailureKind = Literal[
    "provider_error",
    "authentication_error",
    "permission_error",
    "quota_error",
    "rate_limit_error",
    "not_found_error",
    "invalid_request_error",
    "transport_error",
    "provider_timeout",
]
ProviderFailureStage = Literal["token_count", "response", "exchange"]


class ProviderError(Exception):
    """An expected adapter failure with optional, allowlisted safe diagnostics."""

    failure_kind: ProviderFailureKind
    failure_stage: ProviderFailureStage | None

    def __init__(
        self,
        message: str,
        *,
        failure_kind: ProviderFailureKind = "provider_error",
        failure_stage: ProviderFailureStage | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.failure_stage = failure_stage


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
