"""Short-lived, zero-retry Claude SDK transport for admitted host calls."""

from __future__ import annotations

from typing import Literal

from anthropic import AsyncAnthropic
from pydantic import JsonValue

from mos_eisley.providers.anthropic_http import BoundedAnthropicHttpClient
from mos_eisley.providers.anthropic_messages import SDKAnthropicTransport


class EphemeralAnthropicTransport:
    provider: Literal["anthropic"] = "anthropic"
    automatic_retries: Literal[0] = 0

    def __init__(self, api_key: str, timeout_seconds: float) -> None:
        if not api_key:
            raise ValueError("Anthropic API key must not be empty")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("Anthropic timeout must be between zero and 60 seconds")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def _client(self) -> AsyncAnthropic:
        return AsyncAnthropic(
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            max_retries=0,
            base_url="https://api.anthropic.com",
            http_client=BoundedAnthropicHttpClient(
                trust_env=False, follow_redirects=False
            ),
        )

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        async with self._client() as sdk:
            return await SDKAnthropicTransport(sdk).count_input_tokens(payload)

    async def create_message(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        async with self._client() as sdk:
            return await SDKAnthropicTransport(sdk).create_message(payload)

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return await self.create_message(payload)
