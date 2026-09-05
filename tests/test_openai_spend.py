"""Spend is reserved before generation and never released on an unknown outcome."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from openai import OpenAIError
from pydantic import JsonValue, ValidationError

from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_responses import SDKOpenAITransport
from mos_eisley.providers.openai_spend import (
    BudgetedOpenAITransport,
    SpendPolicy,
    SpendReceipt,
    SpendReservation,
)


def policy() -> SpendPolicy:
    return SpendPolicy(
        model="gpt-6-astra",
        pricing_source="synthetic test rates",
        valid_from=datetime.now(UTC) - timedelta(hours=1),
        valid_until=datetime.now(UTC) + timedelta(hours=1),
        input_microusd_per_million=1_000_000,
        output_microusd_per_million=2_000_000,
        max_cost_microusd=1000,
    )


def request() -> dict[str, JsonValue]:
    return {
        "model": "gpt-6-astra",
        "input": [{"role": "user", "content": "Review."}],
        "instructions": "Only text.",
        "tools": [],
        "reasoning": {"effort": "medium"},
        "max_output_tokens": 100,
        "store": False,
        "truncation": "disabled",
    }


class FakeTransport:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.counts: list[dict[str, JsonValue]] = []
        self.calls: list[dict[str, JsonValue]] = []
        self.tokens = 10
        self.error: BaseException | None = None
        self.response: dict[str, JsonValue] = {
            "model": "gpt-6-astra",
            "service_tier": "default",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        self.counts.append(payload)
        return self.tokens

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        SpendReservation.model_validate_json(
            (self.directory / "spend-reservation.json").read_bytes()
        )
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return self.response


class SpendingTests(IsolatedAsyncioTestCase):
    async def test_concurrent_caller_cannot_share_reservation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            transport = FakeTransport(root)
            entered, release = asyncio.Event(), asyncio.Event()

            async def count(payload: dict[str, JsonValue]) -> int:
                entered.set()
                await release.wait()
                return 10

            with patch.object(transport, "count_input_tokens", side_effect=count):
                controller = BudgetedOpenAITransport(transport, policy(), root)
                first = asyncio.create_task(controller.create_response(request()))
                try:
                    await asyncio.wait_for(entered.wait(), timeout=1)
                    with self.assertRaises(ProviderError):
                        await controller.create_response(request())
                finally:
                    release.set()
                    await first
            self.assertEqual(len(transport.calls), 1)

    async def test_expiry_during_count_prevents_generation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            transport = FakeTransport(root)
            with (
                patch.object(
                    SpendPolicy,
                    "check_current",
                    side_effect=[None, ValueError("expired")],
                ),
                self.assertRaises(ValueError),
            ):
                await BudgetedOpenAITransport(
                    transport, policy(), root
                ).create_response(request())
            self.assertEqual(len(transport.counts), 1)
            self.assertEqual(transport.calls, [])
            self.assertFalse((root / "spend-reservation.json").exists())

    async def test_reserves_before_call_and_reconciles_without_cache_discount(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            transport = FakeTransport(root)
            controller = BudgetedOpenAITransport(transport, policy(), root)
            payload = request()
            await controller.create_response(payload)
            self.assertNotIn("service_tier", payload)
            self.assertEqual(transport.calls[0]["service_tier"], "default")
            self.assertNotIn("max_output_tokens", transport.counts[0])
            self.assertNotIn("store", transport.counts[0])
            self.assertEqual(transport.counts[0]["input"], transport.calls[0]["input"])
            receipt = SpendReceipt.model_validate_json(
                (root / "spend-receipt.json").read_bytes()
            )
            reservation = SpendReservation.model_validate_json(
                (root / "spend-reservation.json").read_bytes()
            )
            self.assertEqual(reservation.reserved_microusd, 210)
            self.assertEqual(receipt.retained_microusd, 20)
            self.assertEqual(receipt.status, "settled")
            with self.assertRaises(ProviderError):
                await controller.create_response(payload)
            self.assertEqual(len(transport.calls), 1)

    async def test_insufficient_budget_or_token_limit_never_generates(self) -> None:
        for updates in ({"max_cost_microusd": 209}, {"max_input_tokens": 9}):
            with self.subTest(updates=updates), TemporaryDirectory() as directory:
                root = Path(directory)
                transport = FakeTransport(root)
                with self.assertRaises(ProviderError):
                    await BudgetedOpenAITransport(
                        transport, policy().model_copy(update=updates), root
                    ).create_response(request())
                self.assertEqual(len(transport.counts), 1)
                self.assertEqual(transport.calls, [])
                self.assertFalse((root / "spend-reservation.json").exists())

    async def test_failure_cancellation_and_missing_usage_retain_full_reservation(
        self,
    ) -> None:
        for error in (
            RuntimeError("secret-provider-detail"),
            asyncio.CancelledError(),
            None,
        ):
            with self.subTest(error=error), TemporaryDirectory() as directory:
                root = Path(directory)
                transport = FakeTransport(root)
                transport.error = error
                transport.response = {}
                controller = BudgetedOpenAITransport(transport, policy(), root)
                with self.assertRaises(
                    (RuntimeError, asyncio.CancelledError, ProviderError)
                ):
                    await controller.create_response(request())
                receipt_bytes = (root / "spend-receipt.json").read_bytes()
                receipt = SpendReceipt.model_validate_json(receipt_bytes)
                self.assertEqual(receipt.status, "uncertain")
                self.assertEqual(receipt.retained_microusd, 210)
                self.assertNotIn(b"secret-provider-detail", receipt_bytes)
                with self.assertRaises(ProviderError):
                    await controller.create_response(request())
                self.assertEqual(len(transport.calls), 1)

    async def test_response_cannot_release_reservation_after_assumption_violation(
        self,
    ) -> None:
        cases: tuple[dict[str, JsonValue], ...] = (
            {"model": "another-model"},
            {"service_tier": "priority"},
            {"usage": {"input_tokens": 11, "output_tokens": 5}},
            {"usage": {"input_tokens": 10, "output_tokens": 101}},
            {"usage": {"input_tokens": True, "output_tokens": -1}},
        )
        for changes in cases:
            with self.subTest(changes=changes), TemporaryDirectory() as directory:
                root = Path(directory)
                transport = FakeTransport(root)
                transport.response.update(changes)
                with self.assertRaises(ProviderError):
                    await BudgetedOpenAITransport(
                        transport, policy(), root
                    ).create_response(request())
                receipt = SpendReceipt.model_validate_json(
                    (root / "spend-receipt.json").read_bytes()
                )
                self.assertNotEqual(receipt.status, "settled")
                self.assertEqual(receipt.retained_microusd, 210)

    async def test_expired_policy_or_unsupported_request_never_contacts_provider(
        self,
    ) -> None:
        cases: tuple[dict[str, JsonValue], ...] = (
            {"model": "wrong"},
            {"tools": [{"type": "web_search"}]},
            {"previous_response_id": "resp_hidden"},
            {"max_output_tokens": 4097},
            {"input": [{"role": "user", "content": [{"type": "input_image"}]}]},
            {"input": []},
        )
        for changes in cases:
            with self.subTest(changes=changes), TemporaryDirectory() as directory:
                root = Path(directory)
                transport = FakeTransport(root)
                payload = request()
                payload.update(changes)
                with self.assertRaises(ProviderError):
                    await BudgetedOpenAITransport(
                        transport, policy(), root
                    ).create_response(payload)
                self.assertEqual(transport.counts, [])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            transport = FakeTransport(root)
            expired = policy().model_copy(
                update={"valid_until": datetime.now(UTC) - timedelta(seconds=1)}
            )
            with self.assertRaises(ValueError):
                await BudgetedOpenAITransport(transport, expired, root).create_response(
                    request()
                )
            self.assertEqual(transport.counts, [])

    async def test_reservation_write_failure_prevents_generation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "spend-reservation.json").write_text("existing evidence")
            transport = FakeTransport(root)
            with self.assertRaises(FileExistsError):
                await BudgetedOpenAITransport(
                    transport, policy(), root
                ).create_response(request())
            self.assertEqual(transport.calls, [])

    async def test_sdk_token_count_contract_and_generic_error(self) -> None:
        sdk = MagicMock()
        sdk.responses.input_tokens.count = AsyncMock(
            return_value=MagicMock(input_tokens=42)
        )
        transport = SDKOpenAITransport(sdk)
        self.assertEqual(await transport.count_input_tokens({"model": "example"}), 42)
        sdk.responses.input_tokens.count.assert_awaited_once_with(model="example")
        sdk.responses.input_tokens.count.side_effect = OpenAIError("private error")
        with self.assertRaisesRegex(ProviderError, "token count failed"):
            await transport.count_input_tokens({})


class PolicyTests(TestCase):
    def test_dates_rounding_and_round_trip(self) -> None:
        original = policy()
        self.assertEqual(
            SpendPolicy.model_validate_json(canonical_bytes(original)), original
        )
        self.assertEqual(original.cost(10, 5), 20)
        tiny = original.model_copy(
            update={"input_microusd_per_million": 1, "output_microusd_per_million": 1}
        )
        self.assertEqual(tiny.cost(1, 1), 1)
        for update in (
            {"valid_from": datetime.now()},
            {"valid_until": original.valid_from},
        ):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                SpendPolicy.model_validate_json(
                    canonical_bytes(original.model_copy(update=update))
                )
