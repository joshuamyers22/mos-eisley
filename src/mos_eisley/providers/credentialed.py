"""Additive host transports for existing spend-controlled provider brokers."""

from typing import Literal

from pydantic import JsonValue

from mos_eisley.core.ports import ProviderError
from mos_eisley.run.credential_network import CredentialNetwork


class CredentialedOpenAITransport:
    """Pass to the existing spending wrapper and RequestBoundBroker.

    Trusted endpoint operations: count_input_tokens -> /v1/responses/input_tokens;
    create_response -> /v1/responses. No SDK ever receives the actual key.
    """

    provider: Literal["openai"] = "openai"
    automatic_retries: Literal[0] = 0

    def __init__(self, network: CredentialNetwork) -> None:
        self._network = network

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        result = await self._network.post("count_input_tokens", payload)
        count = result.get("input_tokens")
        if type(count) is not int or count < 0:
            raise ProviderError("Credentialed token count invalid")
        return count

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return await self._network.post("create_response", payload)
