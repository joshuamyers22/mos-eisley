"""Loop-local, fail-closed OpenAI SDK transport for one conformance exchange."""

from typing import Literal

from openai import AsyncOpenAI
from pydantic import JsonValue

from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
from mos_eisley.providers.openai_responses import SDKOpenAITransport


class EphemeralOpenAITransport:
    """Create and close each SDK client on the broker callback's event loop.

    The spending controller counts input before dispatch, so the two operations use
    separate short-lived clients. Neither client, its credential, nor its endpoint
    crosses the worker boundary.
    """

    provider: Literal["openai"] = "openai"
    automatic_retries: Literal[0] = 0

    def __init__(self, api_key: str, timeout_seconds: float) -> None:
        if not api_key:
            raise ValueError("OpenAI API key must not be empty")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("OpenAI timeout must be between zero and 60 seconds")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def _client(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            max_retries=0,
            base_url="https://api.openai.com/v1",
            http_client=BoundedOpenAIHttpClient(
                trust_env=False, follow_redirects=False
            ),
        )

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        async with self._client() as sdk:
            return await SDKOpenAITransport(sdk).count_input_tokens(payload)

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        async with self._client() as sdk:
            return await SDKOpenAITransport(sdk).create_response(payload)
