"""Request-bound canonical responses for deterministic agent-loop testing."""

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest, ModelResponse


class AgentExchange(Contract):
    request_sha256: Digest
    response: ModelResponse | None


class AgentCassette(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["recorded_agent"] = "recorded_agent"
    exchanges: Annotated[tuple[AgentExchange, ...], Field(min_length=1, max_length=32)]


class RecordedAgentClient:
    def __init__(self, cassette: AgentCassette) -> None:
        self.cassette = cassette
        self._index = 0

    @property
    def exhausted(self) -> bool:
        return self._index == len(self.cassette.exchanges)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self._index >= len(self.cassette.exchanges):
            raise ProviderError("cassette has no remaining exchange")
        exchange = self.cassette.exchanges[self._index]
        self._index += 1
        if exchange.request_sha256 != digest(canonical_bytes(request)):
            raise ProviderError("recorded request mismatch")
        if exchange.response is None:
            raise ProviderError("recorded provider failure")
        return exchange.response
