"""Consume an existing exact-request broker through the canonical model port."""

from __future__ import annotations

import math
import threading

from mos_eisley.core.models import canonical_bytes, canonical_fingerprint, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    TextBlock,
    ToolCallBlock,
)
from mos_eisley.providers.openai_responses import request_payload, response_from_payload
from mos_eisley.run.isolated_broker import run_isolated_broker_async
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import MAX_WIRE_BYTES
from mos_eisley.run.provider_broker import (
    MAX_REQUEST_BYTES,
    ApprovedRequest,
    RequestBoundBroker,
)


class BrokeredOpenAIClient:
    """One attempt for one frozen text request and a previously issued host broker.

    Construction does not issue authority. The trusted host must independently
    admit transfer, spending and audit policy before constructing the broker.
    """

    def __init__(
        self,
        request: ModelRequest,
        broker: RequestBoundBroker,
        container: OfflineContainer,
        *,
        timeout: float = 30,
    ) -> None:
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("invalid brokered model timeout")
        if canonical_fingerprint(request).bytes > MAX_REQUEST_BYTES:
            raise ValueError("canonical broker request exceeds byte limit")
        frozen = canonical_bytes(request)
        request = ModelRequest.model_validate_json(frozen)
        if (
            request.provider != "openai"
            or request.tools
            or len(request.turns) != 1
            or request.turns[0].role != "user"
            or any(
                not isinstance(block, TextBlock) for block in request.turns[0].blocks
            )
            or request.max_output > MAX_WIRE_BYTES
            or request.max_output_tokens is None
        ):
            raise ValueError("brokered model client requires one bounded text request")
        payload = ApprovedRequest(payload=request_payload(request))
        fingerprint = canonical_fingerprint(payload)
        if (
            fingerprint.bytes > MAX_REQUEST_BYTES
            or fingerprint.sha256 != broker.request_sha256
        ):
            raise ValueError("canonical request does not match the issued broker")
        self._request = frozen
        self._broker = broker
        self._container = container
        self._timeout = timeout
        self._used = False
        self._lock = threading.Lock()

    @property
    def request_sha256(self) -> str:
        """Canonical identity includes local limits omitted from provider payloads."""
        return digest(self._request)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        with self._lock:
            if self._used:
                raise ProviderError("Brokered model attempt already consumed")
            # Burn the client attempt before validation or any asynchronous work.
            self._used = True
        try:
            if (
                canonical_fingerprint(request).bytes > MAX_REQUEST_BYTES
                or canonical_bytes(request) != self._request
            ):
                raise ValueError("canonical request changed")
            frozen = ModelRequest.model_validate_json(self._request)
            assert frozen.max_output_tokens is not None
            reply = await run_isolated_broker_async(
                self._broker, self._container, timeout=self._timeout
            )
            # The broker/transport bound wire allocation. This separately rejects
            # oversize host envelopes before the provider adapter parses output.
            if canonical_fingerprint(reply).bytes > MAX_WIRE_BYTES:
                raise ValueError("broker reply exceeds wire budget")
            if reply.response.get("model") != frozen.model:
                raise ValueError("brokered response model does not match request")
            response = response_from_payload(reply.response)
            if (
                canonical_fingerprint(response).bytes > frozen.max_output
                or response.usage.output > frozen.max_output_tokens
                or any(
                    isinstance(block, ToolCallBlock) for block in response.turn.blocks
                )
            ):
                raise ValueError("brokered response violated the text request limits")
            return response
        except Exception:
            raise ProviderError("Brokered model exchange failed") from None
