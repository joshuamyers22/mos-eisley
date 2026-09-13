"""Exact canonical/provider binding through real worker pipes and spending."""

from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pydantic import JsonValue
from test_openai_spend import FakeTransport, policy

from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import (
    Brief,
    CriticSpec,
    Critique,
    JudgeDecision,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    TextBlock,
    ToolDefinition,
    ToolSchema,
    Turn,
)
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.brokered_openai import BrokeredOpenAIClient
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_responses import request_payload
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport, SpendReceipt
from mos_eisley.review.pipeline import review
from mos_eisley.run.broker_wire import BrokerAck, BrokerReply
from mos_eisley.run.duplex import ExchangeHandler, bounded_exchange
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.provider_broker import ApprovedRequest, RequestBoundBroker
from mos_eisley.run.spend_ledger import SpendLedger


def model_request() -> ModelRequest:
    return ModelRequest(
        provider="openai",
        model="gpt-6-astra",
        effort="medium",
        system="Only text.",
        turns=(Turn(role="user", blocks=(TextBlock(text="Review."),)),),
        max_output=8000,
        max_output_tokens=100,
    )


def output(text: str = "fixture") -> dict[str, JsonValue]:
    return {
        "id": "response-fixture",
        "model": "gpt-6-astra",
        "service_tier": "default",
        "status": "completed",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


class BrokeredModelTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 1000)
        self.request = model_request()
        self.fake = FakeTransport(self.root)
        self.fake.response = output()
        self.payload = request_payload(self.request)
        self.broker = RequestBoundBroker(
            self.payload,
            BudgetedOpenAITransport(self.fake, policy(), self.root, self.ledger),
        )
        self.container = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)
        self.calls = 0
        self.finished = False
        self.exit_error = False
        self.patch = patch.object(
            self.container, "exchange_async", side_effect=self.exchange
        )
        self.mock_exchange = self.patch.start()
        self.addCleanup(self.patch.stop)
        self.client = BrokeredOpenAIClient(self.request, self.broker, self.container)

    async def exchange(
        self,
        arguments: tuple[str, ...],
        payload: bytes,
        handler: ExchangeHandler,
        timeout: float,
    ) -> bytes:
        self.calls += 1
        try:
            result = await bounded_exchange(
                [sys.executable, *arguments], payload, handler, timeout
            )
            if self.exit_error:
                raise ValueError("fixture cleanup failure")
            return result
        finally:
            self.finished = True

    async def test_real_pipe_response_spend_and_exact_identity(self) -> None:
        result = await self.client.complete(self.request)
        self.assertEqual(result.turn.blocks, (TextBlock(text="fixture"),))
        self.assertEqual(result.provider_request_id, "response-fixture")
        self.assertEqual(result.usage.output, 5)
        self.assertEqual(
            self.client.request_sha256, digest(canonical_bytes(self.request))
        )
        self.assertEqual(
            self.broker.request_sha256,
            digest(canonical_bytes(ApprovedRequest(payload=self.payload))),
        )
        self.assertTrue(self.finished)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)
        self.assertEqual(len(self.fake.calls), 1)

    async def test_replay_and_concurrent_call_permit_one_attempt(self) -> None:
        outcomes = await asyncio.gather(
            self.client.complete(self.request),
            self.client.complete(self.request),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(value, ModelResponse) for value in outcomes), 1)
        self.assertEqual(sum(isinstance(value, ProviderError) for value in outcomes), 1)
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)
        self.assertEqual(self.calls, 1)

    async def test_changed_local_limit_rejects_even_with_same_provider_payload(
        self,
    ) -> None:
        changed = self.request.model_copy(update={"max_output": 9000})
        self.assertEqual(request_payload(changed), self.payload)
        with self.assertRaises(ProviderError):
            await self.client.complete(changed)
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.fake.counts, [])

    async def test_changed_prompt_model_effort_and_token_limit_reject_before_worker(
        self,
    ) -> None:
        for update in (
            {"system": "different"},
            {"model": "other"},
            {"effort": "low"},
            {"max_output_tokens": 101},
        ):
            client = BrokeredOpenAIClient(self.request, self.broker, self.container)
            with self.subTest(update=update), self.assertRaises(ProviderError):
                await client.complete(self.request.model_copy(update=update))
        self.assertEqual(self.calls, 0)

    def test_broker_for_different_payload_rejected_at_construction(self) -> None:
        for key, value in (
            ("store", True),
            ("instructions", "changed"),
            ("max_output_tokens", 99),
        ):
            payload = copy.deepcopy(self.payload)
            payload[key] = value
            broker = RequestBoundBroker(
                payload,
                BudgetedOpenAITransport(self.fake, policy(), self.root, self.ledger),
            )
            with self.subTest(key=key), self.assertRaises(ValueError):
                BrokeredOpenAIClient(self.request, broker, self.container)
        self.assertEqual(self.fake.counts, [])

    def test_nontext_history_tools_and_missing_token_cap_rejected(self) -> None:
        tool = ToolDefinition(
            name="write", description="write", input_schema=ToolSchema(type="object")
        )
        requests = (
            self.request.model_copy(update={"provider": "other"}),
            self.request.model_copy(update={"max_output_tokens": None}),
            self.request.model_copy(update={"max_output": 16_000_001}),
            self.request.model_copy(update={"tools": (tool,)}),
            self.request.model_copy(
                update={
                    "turns": (
                        self.request.turns[0],
                        Turn(role="assistant", blocks=(TextBlock(text="old"),)),
                        self.request.turns[0],
                    )
                }
            ),
        )
        for request in requests:
            with self.subTest(request=request), self.assertRaises(ValueError):
                BrokeredOpenAIClient(request, self.broker, self.container)

    def test_invalid_timeout_rejected(self) -> None:
        for timeout in (0, 61, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                BrokeredOpenAIClient(
                    self.request, self.broker, self.container, timeout=timeout
                )

    def test_canonical_unicode_byte_limit_rejected_before_broker_claim(self) -> None:
        request = self.request.model_copy(
            update={
                "turns": (
                    Turn(role="user", blocks=(TextBlock(text="🌍" * 8000),) * 40),
                )
            }
        )
        with patch.object(self.broker, "claim") as claim, self.assertRaises(ValueError):
            BrokeredOpenAIClient(request, self.broker, self.container)
        claim.assert_not_called()

    def test_binding_inspection_does_not_read_bearer_secret(self) -> None:
        with patch.object(self.broker, "claim") as claim:
            BrokeredOpenAIClient(self.request, self.broker, self.container)
        claim.assert_not_called()

    async def test_frozen_provider_payload_survives_original_dict_mutation(
        self,
    ) -> None:
        self.payload["instructions"] = "mutated after issue"
        await self.client.complete(self.request)
        self.assertEqual(self.fake.calls[0]["instructions"], "Only text.")

    async def test_expired_broker_does_not_count_or_send(self) -> None:
        broker = RequestBoundBroker(
            request_payload(self.request),
            BudgetedOpenAITransport(self.fake, policy(), self.root, self.ledger),
            lifetime_seconds=0.001,
        )
        client = BrokeredOpenAIClient(self.request, broker, self.container)
        await asyncio.sleep(0.01)
        with self.assertRaises(ProviderError):
            await client.complete(self.request)
        self.assertEqual(self.fake.counts, [])
        self.assertEqual(self.ledger.snapshot().charged_microusd, 0)

    async def test_malformed_output_remains_charged_and_cannot_retry(self) -> None:
        self.fake.response["output"] = []
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)
        self.assertEqual(self.calls, 1)

    async def test_tool_response_rejected_without_tool_execution(self) -> None:
        self.fake.response["output"] = [
            {
                "type": "function_call",
                "id": "native",
                "call_id": "call",
                "name": "write",
                "arguments": "{}",
            }
        ]
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)

    async def test_canonical_response_budget_includes_envelope(self) -> None:
        request = self.request.model_copy(update={"max_output": 100})
        client = BrokeredOpenAIClient(request, self.broker, self.container)
        with self.assertRaises(ProviderError):
            await client.complete(request)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)

    async def test_excess_usage_is_a_spending_violation(self) -> None:
        self.fake.response["usage"] = {"input_tokens": 10, "output_tokens": 101}
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)
        receipt = SpendReceipt.model_validate_json(
            (self.root / "spend-receipt.json").read_bytes()
        )
        self.assertEqual(receipt.status, "violation")
        self.assertEqual(self.ledger.snapshot().charged_microusd, 210)

    async def test_host_reply_model_and_token_limit_are_rechecked(self) -> None:
        wrong_model = output()
        wrong_model["model"] = "another-model"
        excess_tokens = output()
        excess_tokens["usage"] = {"input_tokens": 10, "output_tokens": 101}
        for body in (wrong_model, excess_tokens):
            client = BrokeredOpenAIClient(self.request, self.broker, self.container)
            with (
                patch(
                    "mos_eisley.providers.brokered_openai.run_isolated_broker_async",
                    return_value=BrokerReply(response=body),
                ),
                self.assertRaises(ProviderError),
            ):
                await client.complete(self.request)

    async def test_noncompleted_statuses_are_preserved_for_caller(
        self,
    ) -> None:
        for status, expected in (("incomplete", "max_output"), ("failed", "error")):
            body = output()
            body["status"] = status
            body["incomplete_details"] = {"reason": "max_output_tokens"}
            client = BrokeredOpenAIClient(self.request, self.broker, self.container)
            with patch(
                "mos_eisley.providers.brokered_openai.run_isolated_broker_async",
                return_value=BrokerReply(response=body),
            ):
                response = await client.complete(self.request)
            self.assertEqual(response.stop_reason, expected)

    async def test_cleanup_failure_discards_received_response(self) -> None:
        self.exit_error = True
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)
        self.assertTrue(self.finished)
        self.assertEqual(len(self.fake.calls), 1)

    async def test_missing_dispatch_or_bad_ack_never_returns_response(self) -> None:
        self.mock_exchange.side_effect = None
        self.mock_exchange.return_value = canonical_bytes(
            BrokerAck(response_sha256="0" * 64)
        )
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)
        self.assertEqual(self.fake.calls, [])

    async def test_cancel_keeps_uncertain_charge_and_consumes_attempt(self) -> None:
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def slow(_: object) -> dict[str, JsonValue]:
            started.set()
            try:
                await asyncio.sleep(10)
                return {}
            finally:
                stopped.set()

        with patch.object(self.fake, "create_response", side_effect=slow):
            task = asyncio.create_task(self.client.complete(self.request))
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(stopped.is_set())
        self.assertTrue(self.finished)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 210)
        with self.assertRaises(ProviderError):
            await self.client.complete(self.request)

    async def test_provider_failure_is_coarse(self) -> None:
        self.fake.error = ValueError("SECRET BODY")
        with self.assertRaises(ProviderError) as raised:
            await self.client.complete(self.request)
        self.assertNotIn("SECRET", str(raised.exception))
        self.assertEqual(len(self.fake.calls), 1)

    async def test_wire_response_bound_is_checked_before_adapter(self) -> None:
        reply = BrokerReply(response={"padding": "x" * 16_000_001})
        with (
            patch(
                "mos_eisley.providers.brokered_openai.run_isolated_broker_async",
                return_value=reply,
            ),
            patch(
                "mos_eisley.providers.brokered_openai.response_from_payload"
            ) as parse,
            self.assertRaises(ProviderError),
        ):
            await self.client.complete(self.request)
        parse.assert_not_called()

    async def test_model_reviewer_critic_and_judge_use_bound_brokers(self) -> None:
        outer = self
        seen: list[ModelRequest] = []

        class FixtureAdmission:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                # Synthetic fixture issuance only; product admission is separate.
                index = len(seen)
                seen.append(request)
                directory = outer.root / str(index)
                directory.mkdir()
                fake = FakeTransport(directory)
                is_judge = request.system.startswith("Adjudicate")
                answer = (
                    JudgeDecision(upheld=(), rationale="Fixture")
                    if is_judge
                    else Critique()
                )
                fake.response = output(canonical_bytes(answer).decode())
                broker = RequestBoundBroker(
                    request_payload(request),
                    BudgetedOpenAITransport(
                        fake,
                        policy(),
                        directory,
                        outer.ledger,
                    ),
                )
                return await BrokeredOpenAIClient(
                    request, broker, outer.container
                ).complete(request)

        reviewer = ModelReviewer(
            FixtureAdmission(),
            openai_registry(),
            judge_provider="openai",
            judge_model="gpt-6-astra",
            budget=BudgetPolicy(max_output_tokens=100),
        )
        roster = (
            CriticSpec(
                id="one", provider="openai", model="gpt-6-astra", persona="correctness"
            ),
        )
        result = await review(
            Brief(spec="Return one", diff="return 1"),
            roster,
            reviewer,
            ReviewPolicy(min_critics=1, min_providers=1),
        )
        self.assertEqual(result.verdict.decision, "accept")
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 40)
        self.assertNotIn("persona", canonical_bytes(seen[1]).decode())
