"""Claude critic calls use the existing held review ledger and private broker."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pydantic import JsonValue

from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import Brief, CriticRequest, CriticSpec, Critique
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.core.registry import anthropic_registry
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.duplex import ExchangeHandler, bounded_exchange
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_broker import PreparedReviewCall, verify_review_broker_audit
from mos_eisley.run.review_evidence import verify_model_completion
from mos_eisley.run.spend_ledger import SpendLedger


class ProjectionClient:
    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise AssertionError("projection client must not receive the live call")


class FakeClaude:
    def __init__(self) -> None:
        self.counts = 0
        self.calls = 0

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        self.counts += 1
        return 300

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        return {
            "id": "msg_synthetic_critic",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5",
            "stop_reason": "end_turn",
            "content": cast(
                JsonValue,
                [{"type": "text", "text": '{"schema_version":1,"findings":[]}'}],
            ),
            "usage": {
                "input_tokens": 300,
                "output_tokens": 20,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        }


class AnthropicReviewBrokerTests(IsolatedAsyncioTestCase):
    async def test_critic_round_trip_uses_one_grant_and_settles_spend(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = datetime.now(UTC)
            policy = SpendPolicy(
                schema_version=2,
                provider="anthropic",
                model="claude-sonnet-5",
                pricing_source=(
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview"
                ),
                valid_from=now - timedelta(minutes=1),
                valid_until=now + timedelta(hours=1),
                input_microusd_per_million=2_000_000,
                cache_write_microusd_per_million=2_500_000,
                output_microusd_per_million=10_000_000,
                max_cost_microusd=10_000,
                max_input_tokens=1000,
                max_output_tokens=32,
            )
            ledger = SpendLedger.create(root / "ledger.sqlite", 10_000)
            reviewer = ModelReviewer(
                ProjectionClient(),
                anthropic_registry(),
                judge_provider="anthropic",
                judge_model="claude-sonnet-5",
                effort="high",
                budget=BudgetPolicy(max_output_tokens=32),
            )
            critic = CriticSpec(
                id="claude-critic",
                provider="anthropic",
                model="claude-sonnet-5",
                persona="correctness",
            )
            request = CriticRequest(
                brief=Brief(spec="Return one", diff="+ return 1"),
                persona="correctness",
            )
            call = PreparedReviewCall(reviewer, request, policy, ledger, critic=critic)
            self.assertEqual(call.authorization.provider, "anthropic")
            self.assertEqual(ledger.snapshot().entries, 0)
            directory = root / "audit"
            container = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)

            async def exchange(
                arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                timeout: float,
            ) -> bytes:
                return await bounded_exchange(
                    [sys.executable, *arguments], payload, handler, timeout
                )

            fake = FakeClaude()
            with patch.object(container, "exchange_async", side_effect=exchange):
                client = call.issue(
                    approved_transfer_sha256=call.approval_sha256,
                    transport=fake,
                    directory=directory,
                    container=container,
                )
                response = await client.complete(call.model_request)
            self.assertEqual((fake.counts, fake.calls), (1, 1))
            self.assertEqual(
                reviewer.parse_critique(critic, request, response), Critique()
            )
            outcome = verify_review_broker_audit(directory, call.authorization)
            completion, retained = verify_model_completion(
                directory, call.model_request, outcome
            )
            self.assertEqual(completion.status, "received")
            self.assertEqual(retained, response)
            entry = ledger.entry_status(call.authorization.ledger_entry_id)
            assert entry is not None
            self.assertEqual(entry.status, "settled")
