"""The SDK-facing HTTP client bounds decoded bodies without network calls."""

import gzip
from unittest import IsolatedAsyncioTestCase

import httpx
from openai import AsyncOpenAI

from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
from mos_eisley.providers.openai_responses import SDKOpenAITransport


class OpenAIHTTPTests(IsolatedAsyncioTestCase):
    async def test_small_body_is_materialized_for_sdk(self) -> None:
        async def reply(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True}, request=request)

        async with BoundedOpenAIHttpClient(
            response_limit=1024, transport=httpx.MockTransport(reply)
        ) as client:
            response = await client.get("https://api.openai.com/v1/responses")
        self.assertEqual(response.json(), {"ok": True})

    async def test_declared_oversize_rejected_before_body_read(self) -> None:
        closed = False

        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"should not be read"

            async def aclose(self) -> None:
                nonlocal closed
                closed = True

        async def reply(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-length": "1025"},
                stream=Body(),
                request=request,
            )

        async with BoundedOpenAIHttpClient(
            response_limit=1024, transport=httpx.MockTransport(reply)
        ) as client:
            with self.assertRaises(httpx.NetworkError):
                await client.get("https://api.openai.com/v1/responses")
        self.assertTrue(closed)

    async def test_chunked_and_decompressed_oversize_rejected(self) -> None:
        class Body(httpx.AsyncByteStream):
            def __init__(self, parts: tuple[bytes, ...]) -> None:
                self.parts = parts

            async def __aiter__(self):
                for block in self.parts:
                    yield block

        cases: tuple[tuple[dict[str, str], tuple[bytes, ...]], ...] = (
            ({}, (b"x" * 700, b"y" * 325)),
            (
                {"content-encoding": "gzip"},
                (gzip.compress(b"z" * 1025),),
            ),
        )
        for headers, blocks in cases:

            async def reply(
                request: httpx.Request,
                headers: dict[str, str] = headers,
                blocks: tuple[bytes, ...] = blocks,
            ) -> httpx.Response:
                return httpx.Response(
                    200, headers=headers, stream=Body(blocks), request=request
                )

            async with BoundedOpenAIHttpClient(
                response_limit=1024, transport=httpx.MockTransport(reply)
            ) as client:
                with (
                    self.subTest(headers=headers),
                    self.assertRaises(httpx.NetworkError),
                ):
                    await client.get("https://api.openai.com/v1/responses")

    async def test_exact_limit_allowed_and_streaming_refused(self) -> None:
        calls = 0

        async def reply(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, content=b"x" * 1024, request=request)

        async with BoundedOpenAIHttpClient(
            response_limit=1024, transport=httpx.MockTransport(reply)
        ) as client:
            response = await client.get("https://api.openai.com/v1/responses")
            self.assertEqual(len(response.content), 1024)
            request = client.build_request("GET", "https://api.openai.com/v1/responses")
            with self.assertRaises(httpx.NetworkError):
                await client.send(request, stream=True)
        self.assertEqual(calls, 1)

    async def test_official_sdk_maps_oversize_to_generic_provider_error(self) -> None:
        async def reply(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "resp_test",
                    "object": "response",
                    "created_at": 0,
                    "status": "completed",
                    "model": "gpt-6-astra",
                    "output": [{"opaque": "x" * 2000}],
                    "parallel_tool_calls": False,
                    "tool_choice": "auto",
                    "tools": [],
                },
                request=request,
            )

        async with BoundedOpenAIHttpClient(
            response_limit=1024, transport=httpx.MockTransport(reply)
        ) as http_client:
            sdk = AsyncOpenAI(
                api_key="synthetic-test-key",
                base_url="https://api.openai.com/v1",
                max_retries=0,
                http_client=http_client,
            )
            with self.assertRaisesRegex(ProviderError, "^OpenAI request failed$"):
                await SDKOpenAITransport(sdk).create_response(
                    {"model": "gpt-6-astra", "input": "fixture"}
                )

    def test_invalid_limits_rejected(self) -> None:
        for limit in (0, 1023, 1_000_001):
            with self.assertRaises(ValueError):
                BoundedOpenAIHttpClient(response_limit=limit)
