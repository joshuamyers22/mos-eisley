"""Anthropic review sends only fixed, bounded, one-attempt API requests."""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx2
from pydantic import JsonValue

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.anthropic_review import (
    ANTHROPIC_COUNT_URL,
    ANTHROPIC_MESSAGES_URL,
    CRITIQUE_SCHEMA,
    MAX_ANTHROPIC_RESPONSE_BYTES,
    AnthropicReviewHTTPTransport,
    normalized_payload,
    payload_bytes,
)
from mos_eisley.providers.anthropic_review_spend import (
    PreReservedAnthropicReviewTransport,
    prepare_anthropic_reservation,
)
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger


def _payload() -> dict[str, JsonValue]:
    return {
        "model": "claude-sonnet-5",
        "max_tokens": 4096,
        "service_tier": "standard_only",
        "inference_geo": "global",
        "system": "Review the exact supplied JSON.",
        "messages": [{"role": "user", "content": '{"brief":"synthetic"}'}],
        "output_config": {"format": {"type": "json_schema", "schema": CRITIQUE_SCHEMA}},
    }


def _policy() -> SpendPolicy:
    now = datetime.now(UTC)
    return SpendPolicy(
        schema_version=2,
        model="claude-sonnet-5",
        pricing_source="https://platform.claude.com/docs/en/about-claude/pricing",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
        input_microusd_per_million=2_000_000,
        cache_write_microusd_per_million=4_000_000,
        output_microusd_per_million=10_000_000,
        max_cost_microusd=200_000,
        max_input_tokens=16_000,
        max_output_tokens=4096,
    )


class AnthropicReviewTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_count_and_message_use_fixed_endpoints_and_no_retry(self) -> None:
        seen: list[tuple[str, dict[str, object]]] = []

        def respond(request: httpx2.Request) -> httpx2.Response:
            body = json.loads(request.content)
            self.assertEqual(request.content, payload_bytes(body))
            seen.append((str(request.url), body))
            self.assertEqual(request.headers["x-api-key"], "fixture-key")
            self.assertEqual(request.headers["anthropic-version"], "2023-06-01")
            if str(request.url) == ANTHROPIC_COUNT_URL:
                return httpx2.Response(200, json={"input_tokens": 123})
            if str(request.url) == ANTHROPIC_MESSAGES_URL:
                return httpx2.Response(200, json={"type": "message"})
            self.fail("unexpected Anthropic endpoint")

        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(respond)
        ) as client:
            transport = AnthropicReviewHTTPTransport("fixture-key", client)
            payload = normalized_payload(_payload(), _policy())
            self.assertEqual(await transport.count_input_tokens(payload), 123)
            self.assertEqual(
                await transport.create_response(payload), {"type": "message"}
            )
        self.assertEqual(len(seen), 2)
        self.assertNotIn("max_tokens", seen[0][1])
        self.assertNotIn("service_tier", seen[0][1])
        self.assertNotIn("inference_geo", seen[0][1])
        self.assertEqual(seen[1][1]["max_tokens"], 4096)
        self.assertEqual(seen[1][1]["service_tier"], "standard_only")
        self.assertEqual(seen[1][1]["inference_geo"], "global")

    async def test_redirect_is_rejected_without_following(self) -> None:
        urls: list[str] = []

        def respond(request: httpx2.Request) -> httpx2.Response:
            urls.append(str(request.url))
            return httpx2.Response(307, headers={"location": "https://elsewhere.test"})

        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(respond)
        ) as client:
            transport = AnthropicReviewHTTPTransport("fixture-key", client)
            with self.assertRaises(ProviderError):
                await transport.create_response(
                    normalized_payload(_payload(), _policy())
                )
        self.assertEqual(urls, [ANTHROPIC_MESSAGES_URL])

    async def test_oversize_body_is_rejected(self) -> None:
        def respond(_request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                200, content=b"x" * (MAX_ANTHROPIC_RESPONSE_BYTES + 1)
            )

        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(respond)
        ) as client:
            transport = AnthropicReviewHTTPTransport("fixture-key", client)
            with self.assertRaisesRegex(ProviderError, "byte limit"):
                await transport.create_response(
                    normalized_payload(_payload(), _policy())
                )

    async def test_unapproved_tools_are_rejected_before_network(self) -> None:
        payload = _payload()
        payload["tools"] = [{"name": "browser"}]
        with self.assertRaises(ProviderError):
            normalized_payload(payload, _policy())

    async def test_priority_or_regional_price_change_is_rejected(self) -> None:
        for field, value in (("service_tier", "auto"), ("inference_geo", "us")):
            with self.subTest(field=field):
                payload = _payload()
                payload[field] = value
                with self.assertRaises(ProviderError):
                    normalized_payload(payload, _policy())

    async def test_cancellation_propagates_with_one_attempt(self) -> None:
        sends = 0

        async def respond(_request: httpx2.Request) -> httpx2.Response:
            nonlocal sends
            sends += 1
            raise asyncio.CancelledError

        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(respond)
        ) as client:
            transport = AnthropicReviewHTTPTransport("fixture-key", client)
            with self.assertRaises(asyncio.CancelledError):
                await transport.create_response(
                    normalized_payload(_payload(), _policy())
                )
        self.assertEqual(sends, 1)


class _CountedFixture:
    def __init__(self) -> None:
        self.count = 123
        self.calls = 0
        self.cancel = False
        self.tier = "standard"

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        del payload
        return self.count

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        del payload
        self.calls += 1
        if self.cancel:
            raise asyncio.CancelledError
        return {
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": '{"findings":[]}'}],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 123,
                "output_tokens": 20,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "service_tier": self.tier,
                "inference_geo": "global",
                "server_tool_use": {
                    "web_search_requests": 0,
                    "web_fetch_requests": 0,
                },
            },
        }


class AnthropicSpendTests(unittest.IsolatedAsyncioTestCase):
    def _case(
        self, root: Path, fixture: _CountedFixture
    ) -> tuple[PreReservedAnthropicReviewTransport, SpendLedger]:
        policy = _policy()
        payload = normalized_payload(_payload(), policy)
        reservation = prepare_anthropic_reservation(payload, policy)
        self.assertEqual(reservation.reserved_microusd, 104_960)
        ledger = SpendLedger.create(root / "ledger.sqlite", 10_000_000)
        entry = LedgerEntry(
            entry_id=digest(b"anthropic-review-once"),
            reservation_sha256=digest(canonical_bytes(reservation)),
            reserved_microusd=reservation.reserved_microusd,
        )
        ledger.reserve(entry)
        directory = root / "attempt"
        directory.mkdir(mode=0o700)
        return (
            PreReservedAnthropicReviewTransport(
                fixture, policy, directory, ledger, reservation, entry
            ),
            ledger,
        )

    async def test_settles_actual_usage_and_rejects_reuse(self) -> None:
        with TemporaryDirectory() as temp:
            fixture = _CountedFixture()
            controller, ledger = self._case(Path(temp), fixture)
            response = await controller.create_response(_payload())
            self.assertEqual(response["model"], "claude-sonnet-5")
            self.assertEqual(fixture.calls, 1)
            self.assertEqual(ledger.snapshot().unresolved_entries, 0)
            self.assertEqual(ledger.snapshot().charged_microusd, 446)
            with self.assertRaises(ProviderError):
                await controller.create_response(_payload())

    async def test_cancellation_retains_full_hold(self) -> None:
        with TemporaryDirectory() as temp:
            fixture = _CountedFixture()
            fixture.cancel = True
            controller, ledger = self._case(Path(temp), fixture)
            with self.assertRaises(asyncio.CancelledError):
                await controller.create_response(_payload())
            self.assertEqual(ledger.snapshot().charged_microusd, 104_960)
            self.assertEqual(ledger.snapshot().unresolved_entries, 1)

    async def test_wrong_tier_blocks_ledger(self) -> None:
        with TemporaryDirectory() as temp:
            fixture = _CountedFixture()
            fixture.tier = "priority"
            controller, ledger = self._case(Path(temp), fixture)
            with self.assertRaisesRegex(ProviderError, "pricing"):
                await controller.create_response(_payload())
            self.assertTrue(ledger.snapshot().blocked)

    async def test_excess_input_blocks_without_generation(self) -> None:
        with TemporaryDirectory() as temp:
            fixture = _CountedFixture()
            fixture.count = 16_001
            controller, ledger = self._case(Path(temp), fixture)
            with self.assertRaisesRegex(ProviderError, "input count"):
                await controller.create_response(_payload())
            self.assertEqual(fixture.calls, 0)
            self.assertTrue(ledger.snapshot().blocked)

    async def test_grant_expiring_after_count_prevents_generation(self) -> None:
        with TemporaryDirectory() as temp:
            fixture = _CountedFixture()
            controller, ledger = self._case(Path(temp), fixture)
            expiry = datetime.now(UTC) + timedelta(minutes=1)
            controller.grant_expires_at = expiry

            class Clock(datetime):
                calls = 0

                @classmethod
                def now(cls, tz: object = None) -> datetime:
                    cls.calls += 1
                    return expiry - timedelta(seconds=1) if cls.calls == 1 else expiry

            with (
                patch("mos_eisley.providers.anthropic_review_spend.datetime", Clock),
                self.assertRaisesRegex(ValueError, "grant expired"),
            ):
                await controller.create_response(_payload())
            self.assertEqual(fixture.calls, 0)
            self.assertEqual(ledger.snapshot().charged_microusd, 104_960)
            self.assertEqual(ledger.snapshot().unresolved_entries, 1)
