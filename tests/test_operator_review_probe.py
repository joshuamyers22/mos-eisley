"""Operator exact approvals run distinct author, critic and judge models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, patch

from test_anthropic_review_conformance import FakeClaude
from test_review_approval_flow import ScriptedUser
from test_review_guidance_admission import GuidedBrokerFixture

from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import (
    CriticSpec,
    Critique,
    JudgeDecision,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.registry import anthropic_registry
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.operator_review_probe import (
    OperatorReviewIdentity,
    OperatorReviewProbe,
)
from mos_eisley.run.review_broker import PreparedReviewCall, PreparedReviewEnvelope
from mos_eisley.run.spend_ledger import SpendLedger


class OperatorReviewTests(GuidedBrokerFixture, IsolatedAsyncioTestCase):
    async def test_distinct_models_complete_under_two_exact_local_approvals(self):
        now = datetime.now(UTC)
        self.base.ledger = SpendLedger.create(
            self.base.root / "operator.sqlite", 10_000
        )

        def spending(model: str, input_rate: int, output_rate: int, cache_rate: int):
            return SpendPolicy(
                schema_version=2,
                provider="anthropic",
                model=model,
                pricing_source=("https://platform.claude.com/docs/en/models/overview"),
                valid_from=now - timedelta(minutes=1),
                valid_until=now + timedelta(minutes=5),
                input_microusd_per_million=input_rate,
                cache_write_microusd_per_million=cache_rate,
                output_microusd_per_million=output_rate,
                max_cost_microusd=10_000,
                max_input_tokens=1000,
                max_output_tokens=32,
            )

        critic_policy = spending("claude-sonnet-5", 2_000_000, 10_000_000, 2_500_000)
        judge_policy = spending("claude-opus-5-5", 4_000_000, 20_000_000, 5_000_000)
        reviewer = ModelReviewer(
            self.base.client,
            anthropic_registry(),
            judge_provider="anthropic",
            judge_model="claude-opus-5-5",
            effort="medium",
            budget=BudgetPolicy(max_output_tokens=32),
        )
        critic = CriticSpec(
            id="sonnet",
            provider="anthropic",
            model="claude-sonnet-5",
            persona="correctness",
        )
        call = PreparedReviewCall(
            reviewer,
            self.base.request,
            critic_policy,
            self.base.ledger,
            critic=critic,
            guidance=self.admission,
        )
        envelope = PreparedReviewEnvelope(
            (call,),
            judge_policy,
            self.base.ledger,
            max_total_microusd=10_000,
            directory=self.base.root / "operator-review",
        )
        identity = OperatorReviewIdentity(
            author_provider="openai",
            author_model="gpt-6",
            author_artifact_sha256=digest(self.base.request.brief.diff.encode()),
            max_total_microusd=1_000_000,
        )
        ui = ScriptedUser(("approve", "approve"))
        key_loader = Mock(return_value="synthetic-test-key")
        sonnet = FakeClaude(canonical_bytes(Critique()).decode(), "msg_sonnet")
        opus = FakeClaude(
            canonical_bytes(JudgeDecision(upheld=(), rationale="Fixture")).decode(),
            "msg_opus",
            model="claude-opus-5-5",
        )

        def transport(api_key: str, timeout_seconds: float) -> FakeClaude:
            return opus if probe.controller.phase == "judge_running" else sonnet

        with patch(
            "mos_eisley.run.operator_review_probe.EphemeralAnthropicTransport",
            side_effect=transport,
        ) as sdk:
            probe = OperatorReviewProbe(
                identity,
                envelope,
                reviewer,
                ReviewPolicy(min_critics=1, min_providers=1),
                ui,
                critic_containers=(self.base.container,),
                judge_container=self.base.container,
                load_api_key=key_loader,
            )
            key_loader.assert_not_called()
            result = await probe.run()
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(
            (sonnet.counts, sonnet.calls, opus.counts, opus.calls), (1, 1, 1, 1)
        )
        self.assertEqual(key_loader.call_count, 4)
        self.assertEqual(sdk.call_count, 4)
        self.assertEqual(len(ui.previews), 2)
        self.assertEqual(self.base.ledger.snapshot().unresolved_entries, 0)
        self.assertLess(self.base.ledger.snapshot().charged_microusd, 1_000_000)

    def test_operator_cap_cannot_exceed_one_dollar(self):
        with self.assertRaises(ValueError):
            OperatorReviewIdentity(
                author_provider="openai",
                author_model="gpt-6",
                author_artifact_sha256="f" * 64,
                max_total_microusd=1_000_001,
            )
