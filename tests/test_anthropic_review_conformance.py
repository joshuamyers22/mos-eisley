"""Synthetic signed approval exercises the entire Claude review probe route."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue
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
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.operator_review_probe import OperatorReviewIdentity
from mos_eisley.run.review_broker import PreparedReviewCall, PreparedReviewEnvelope
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    ReviewConformanceScope,
    make_review_conformance_authorization,
    review_conformance_signer,
    sign_review_conformance_authorization,
)
from mos_eisley.run.review_conformance_observation import (
    ReviewObservationPolicy,
    authenticate_review_probe,
    make_review_probe_observation,
    sign_review_probe_observation,
)
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_runtime_evidence import collect_review_runtime_exchange
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write
from mos_eisley.run.watchdog import CleanupLease, CleanupRecord


class FakeClaude:
    def __init__(
        self, text: str, request_id: str, model: str = "claude-sonnet-5"
    ) -> None:
        self.text = text
        self.request_id = request_id
        self.model = model
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
            "id": self.request_id,
            "type": "message",
            "role": "assistant",
            "model": self.model,
            "stop_reason": "end_turn",
            "content": cast(JsonValue, [{"type": "text", "text": self.text}]),
            "usage": {
                "input_tokens": 300,
                "output_tokens": 20,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        }


class AnthropicReviewConformanceTests(GuidedBrokerFixture, IsolatedAsyncioTestCase):
    async def test_signed_critic_and_judge_complete_with_private_brokers(self) -> None:
        now = datetime.now(UTC)
        self.base.ledger = SpendLedger.create(
            self.base.root / "anthropic.sqlite", 10_000
        )
        self.base.policy = SpendPolicy(
            schema_version=2,
            provider="anthropic",
            model="claude-sonnet-5",
            pricing_source="https://platform.claude.com/docs/en/models/sonnet-5/overview",
            valid_from=now - timedelta(minutes=1),
            valid_until=now + timedelta(minutes=5),
            input_microusd_per_million=2_000_000,
            cache_write_microusd_per_million=2_500_000,
            output_microusd_per_million=10_000_000,
            max_cost_microusd=5_000,
            max_input_tokens=1000,
            max_output_tokens=32,
        )
        self.base.reviewer = ModelReviewer(
            self.base.client,
            anthropic_registry(),
            judge_provider="anthropic",
            judge_model="claude-opus-5-5",
            effort="high",
            budget=BudgetPolicy(max_output_tokens=32),
        )
        self.base.critic = CriticSpec(
            id="claude",
            provider="anthropic",
            model="claude-sonnet-5",
            persona="correctness",
        )
        self.call = PreparedReviewCall(
            self.base.reviewer,
            self.base.request,
            self.base.policy,
            self.base.ledger,
            critic=self.base.critic,
            guidance=self.admission,
        )
        envelope = PreparedReviewEnvelope(
            (self.call,),
            self.base.policy.model_copy(
                update={
                    "model": "claude-opus-5-5",
                    "pricing_source": "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "input_microusd_per_million": 4_000_000,
                    "cache_write_microusd_per_million": 5_000_000,
                    "output_microusd_per_million": 20_000_000,
                    "max_cost_microusd": 10_000,
                }
            ),
            self.base.ledger,
            max_total_microusd=10_000,
            directory=self.base.root / "anthropic-envelope",
        )
        critic = FakeClaude(canonical_bytes(Critique()).decode(), "msg_critic")
        judge = FakeClaude(
            canonical_bytes(JudgeDecision(upheld=(), rationale="Fixture")).decode(),
            "msg_judge",
            model="claude-opus-5-5",
        )
        signer = Ed25519PrivateKey.from_private_bytes(b"a" * 32)
        observer = Ed25519PrivateKey.from_private_bytes(b"b" * 32)
        policy = ReviewConformanceAuthorityPolicy(
            policy_id="synthetic-claude",
            authorities=(review_conformance_signer("authority", signer.public_key()),),
            observers=(review_conformance_signer("observer", observer.public_key()),),
            valid_from=now - timedelta(minutes=1),
            valid_until=now + timedelta(minutes=5),
            max_authorization_seconds=60,
            max_reserved_microusd=10_000,
        )

        async def load(scope: ReviewConformanceScope):
            self.assertEqual(scope.provider, "anthropic")
            self.assertEqual(scope.api_family, "messages")
            self.assertEqual(scope.sdk_version, version("anthropic"))
            issued = datetime.now(UTC)
            authorization = make_review_conformance_authorization(
                scope, policy, issued, issued + timedelta(seconds=20)
            )
            return sign_review_conformance_authorization(
                authorization, "authority", signer
            )

        key_loader = Mock(return_value="synthetic-test-key")
        lifecycles: list[Path] = []

        async def exchange(
            arguments: tuple[str, ...],
            payload: bytes,
            handler: ExchangeHandler,
            timeout: float,
        ) -> bytes:
            directory = self.base.root / f"claude-lifecycle-{len(lifecycles)}"
            directory.mkdir(mode=0o700)
            lease = CleanupLease(
                container_id=digest(str(directory).encode()), max_runtime_seconds=35
            )
            private_write(directory / "lease.json", canonical_bytes(lease))
            self.base.container.lifecycle_path = directory
            lifecycles.append(directory)
            try:
                return await self.base.exchange(arguments, payload, handler, timeout)
            finally:
                private_write(
                    directory / "result.json",
                    canonical_bytes(
                        CleanupRecord(
                            lease_sha256=digest(canonical_bytes(lease)),
                            container_id=lease.container_id,
                            state="removed",
                            attempts=1,
                        )
                    ),
                )

        self.enterContext(
            patch.object(self.base.container, "exchange_async", side_effect=exchange)
        )

        def transport(api_key: str, timeout_seconds: float) -> FakeClaude:
            return judge if probe.controller.phase == "judge_running" else critic

        sdk = self.enterContext(
            patch(
                "mos_eisley.run.review_conformance_probe.EphemeralAnthropicTransport",
                side_effect=transport,
            )
        )
        identity = OperatorReviewIdentity(
            author_provider="openai",
            author_model="gpt-6",
            author_artifact_sha256=digest(self.base.request.brief.diff.encode()),
            max_total_microusd=1_000_000,
        )
        with self.assertRaisesRegex(ValueError, "distinct author, critic and judge"):
            BrokeredReviewConformanceProbe(
                envelope,
                self.base.reviewer,
                ReviewPolicy(min_critics=1, min_providers=1),
                ScriptedUser(("approve", "approve")),
                critic_containers=(self.base.container,),
                judge_container=self.base.container,
                authority_policy=lambda: policy,
                load_authorization=load,
                load_api_key=key_loader,
                operator_identity=identity.model_copy(
                    update={
                        "author_provider": "anthropic",
                        "author_model": "claude-sonnet-5",
                    }
                ),
            )
        key_loader.assert_not_called()
        probe = BrokeredReviewConformanceProbe(
            envelope,
            self.base.reviewer,
            ReviewPolicy(min_critics=1, min_providers=1),
            ScriptedUser(("approve", "approve")),
            critic_containers=(self.base.container,),
            judge_container=self.base.container,
            authority_policy=lambda: policy,
            load_authorization=load,
            load_api_key=key_loader,
            operator_identity=identity,
        )
        result = await probe.run()
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(
            (critic.counts, critic.calls, judge.counts, judge.calls), (1, 1, 1, 1)
        )
        self.assertEqual(key_loader.call_count, 4)
        self.assertEqual(sdk.call_count, 4)
        self.assertEqual(len(probe.approval_ui.authorizations), 2)
        critic_signed, judge_signed = probe.approval_ui.authorizations
        authorizations = (critic_signed, judge_signed)
        self.assertEqual(self.base.ledger.snapshot().unresolved_entries, 0)
        preview = probe.controller.preview
        start = probe.controller.start
        judge_preview = probe.judge_preview
        assert start is not None and judge_preview is not None
        observed = tuple(
            collect_review_runtime_exchange(
                directory, lifecycle, request, signed.authorization
            )
            for directory, lifecycle, request, signed in zip(
                (
                    Path(envelope.envelope.artifact_directory)
                    / self.call.authorization.ledger_entry_id,
                    Path(envelope.envelope.artifact_directory) / "judge",
                ),
                lifecycles,
                (*preview.requests, judge_preview.model_request),
                authorizations,
                strict=True,
            )
        )
        observation_policy = ReviewObservationPolicy(
            policy_id="synthetic-claude-observer",
            authority_policy_sha256=policy.sha256,
            critic_preview_sha256=digest(canonical_bytes(preview)),
            valid_from=policy.valid_from,
            valid_until=policy.valid_until,
            max_observation_age_seconds=600,
        )
        signed_observation = sign_review_probe_observation(
            make_review_probe_observation(
                observation_policy,
                policy,
                preview,
                start,
                judge_preview,
                authorizations,
                self.base.reviewer,
                self.base.ledger,
                expected_result_sha256=digest(canonical_bytes(result)),
                exchanges=observed,
                observed_at=datetime.now(UTC),
            ),
            "observer",
            observer,
        )
        authenticated = authenticate_review_probe(
            signed_observation,
            observation_policy,
            policy,
            preview,
            start,
            judge_preview,
            authorizations,
            self.base.reviewer,
            self.base.ledger,
            expected_result_sha256=digest(canonical_bytes(result)),
            now=datetime.now(UTC),
        )
        self.assertTrue(authenticated.local_artifacts_verified)
        self.assertFalse(authenticated.live_review_activation_authorized)
        for path in Path(envelope.envelope.artifact_directory).rglob("*"):
            if path.is_file():
                self.assertNotIn(b"synthetic-test-key", path.read_bytes())
