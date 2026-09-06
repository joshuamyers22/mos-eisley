"""Bound decoded OpenAI HTTP bodies before SDK JSON model construction."""

from __future__ import annotations

from typing import Any

import httpx

MAX_OPENAI_RESPONSE_BYTES = 1_000_000


class BoundedOpenAIHttpClient(httpx.AsyncClient):
    """Non-streaming client with an application-owned decoded body ceiling.

    OpenAI authentication and request serialization remain owned by the official
    SDK. This client is deliberately unsuitable for streaming API operations.
    """

    def __init__(
        self,
        *,
        response_limit: int = MAX_OPENAI_RESPONSE_BYTES,
        **kwargs: Any,
    ) -> None:
        if not 1024 <= response_limit <= MAX_OPENAI_RESPONSE_BYTES:
            raise ValueError("invalid OpenAI response byte limit")
        self.response_limit = response_limit
        super().__init__(**kwargs)

    async def send(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: Any = httpx.USE_CLIENT_DEFAULT,
        follow_redirects: Any = httpx.USE_CLIENT_DEFAULT,
    ) -> httpx.Response:
        if stream:
            raise httpx.NetworkError(
                "streaming responses are disabled by the bounded client",
                request=request,
            )
        response = await super().send(
            request,
            stream=True,
            auth=auth,
            follow_redirects=follow_redirects,
        )
        try:
            # Content-Length is encoded size and only an early rejection. Counting
            # aiter_bytes below bounds decoded bytes, including compressed bodies.
            header = response.headers.get("content-length")
            if header is not None:
                try:
                    encoded_size = int(header)
                except ValueError:
                    encoded_size = 0
                if encoded_size > self.response_limit:
                    raise httpx.NetworkError(
                        "OpenAI response exceeds byte limit", request=request
                    )
            content = bytearray()
            async for block in response.aiter_bytes():
                if len(content) + len(block) > self.response_limit:
                    raise httpx.NetworkError(
                        "OpenAI response exceeds byte limit", request=request
                    )
                content.extend(block)
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=bytes(content),
                request=request,
                extensions=response.extensions,
                history=response.history,
                default_encoding=response.default_encoding,
            )
        finally:
            await response.aclose()
