"""Synthetic two-provider review exercises signed dispatch and key separation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue
from test_brokered_model_client import output as openai_output
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
from mos_eisley.core.registry import default_registry
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.operator_review_probe import OperatorReviewIdentity
from mos_eisley.run.review_broker import PreparedReviewCall, PreparedReviewEnvelope
from mos_eisley.run.review_conformance_admission import review_sdk_version
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


class FakeOpenAI:
    def __init__(self) -> None:
        self.counts = 0
        self.calls = 0

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        self.counts += 1
        return 10

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        response = openai_output(canonical_bytes(Critique()).decode())
        response["usage"] = {
            "input_tokens": 10,
            "output_tokens": 5,
            "input_tokens_details": {"cache_write_tokens": 0},
        }
        return response


class FakeAnthropic:
    def __init__(self, text: str, model: str) -> None:
        self.text = text
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
            "id": f"msg_{self.model}_{self.calls}",
            "type": "message",
            "role": "assistant",
            "model": self.model,
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": self.text}],
            "usage": {
                "input_tokens": 300,
                "output_tokens": 20,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        }


class MixedReviewConformanceTests(GuidedBrokerFixture, IsolatedAsyncioTestCase):
    async def test_default_quorum_uses_both_credentials_and_signed_mixed_scope(
        self,
    ) -> None:
        now = datetime.now(UTC)
        self.base.ledger = SpendLedger.create(self.base.root / "mixed.sqlite", 20_000)
        self.base.reviewer = ModelReviewer(
            self.base.client,
            default_registry(),
            judge_provider="anthropic",
            judge_model="claude-opus-5-5",
            effort="high",
            budget=BudgetPolicy(max_output_tokens=32),
        )
        openai_policy = self.base.policy.model_copy(
            update={
                "max_input_tokens": 1000,
                "max_output_tokens": 32,
                "max_cost_microusd": 10_000,
            }
        )
        anthropic_policy = SpendPolicy(
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
        openai_critic = CriticSpec(
            id="openai", provider="openai", model="gpt-6-astra", persona="correctness"
        )
        anthropic_critic = CriticSpec(
            id="anthropic",
            provider="anthropic",
            model="claude-sonnet-5",
            persona="correctness",
        )
        calls = tuple(
            PreparedReviewCall(
                self.base.reviewer,
                self.base.request,
                spending,
                self.base.ledger,
                critic=critic,
                guidance=self.admission,
            )
            for critic, spending in (
                (openai_critic, openai_policy),
                (anthropic_critic, anthropic_policy),
            )
        )
        judge_policy = anthropic_policy.model_copy(
            update={
                "model": "claude-opus-5-5",
                "pricing_source": "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                "input_microusd_per_million": 4_000_000,
                "cache_write_microusd_per_million": 5_000_000,
                "output_microusd_per_million": 20_000_000,
                "max_cost_microusd": 10_000,
            }
        )
        envelope = PreparedReviewEnvelope(
            calls,
            judge_policy,
            self.base.ledger,
            max_total_microusd=20_000,
            directory=self.base.root / "mixed-envelope",
        )
        openai, anthropic, judge = (
            FakeOpenAI(),
            FakeAnthropic(canonical_bytes(Critique()).decode(), "claude-sonnet-5"),
            FakeAnthropic(
                canonical_bytes(JudgeDecision(upheld=(), rationale="Fixture")).decode(),
                "claude-opus-5-5",
            ),
        )
        signer = Ed25519PrivateKey.from_private_bytes(b"a" * 32)
        observer = Ed25519PrivateKey.from_private_bytes(b"b" * 32)
        policy = ReviewConformanceAuthorityPolicy(
            policy_id="synthetic-mixed",
            authorities=(review_conformance_signer("authority", signer.public_key()),),
            observers=(review_conformance_signer("observer", observer.public_key()),),
            valid_from=now - timedelta(minutes=1),
            valid_until=now + timedelta(minutes=5),
            max_authorization_seconds=60,
            max_reserved_microusd=20_000,
        )
        seen_scopes: list[ReviewConformanceScope] = []

        async def load(scope: ReviewConformanceScope):
            seen_scopes.append(scope)
            issued = datetime.now(UTC)
            authorization = make_review_conformance_authorization(
                scope, policy, issued, issued + timedelta(seconds=20)
            )
            return sign_review_conformance_authorization(
                authorization, "authority", signer
            )

        lifecycles: list[Path] = []

        async def exchange(
            container: OfflineContainer,
            arguments: tuple[str, ...],
            payload: bytes,
            handler: ExchangeHandler,
            timeout: float,
        ) -> bytes:
            directory = self.base.root / f"mixed-lifecycle-{len(lifecycles)}"
            directory.mkdir(mode=0o700)
            lease = CleanupLease(
                container_id=digest(str(directory).encode()), max_runtime_seconds=35
            )
            private_write(directory / "lease.json", canonical_bytes(lease))
            container.lifecycle_path = directory
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

        containers = tuple(
            OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)
            for _ in range(3)
        )
        for container in containers:

            async def worker(
                arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                timeout: float,
                selected: OfflineContainer = container,
            ) -> bytes:
                return await exchange(selected, arguments, payload, handler, timeout)

            self.enterContext(
                patch.object(
                    container,
                    "exchange_async",
                    side_effect=worker,
                )
            )
        openai_loader = Mock(return_value="openai-test-key")
        anthropic_loader = Mock(return_value="anthropic-test-key")
        self.enterContext(
            patch(
                "mos_eisley.run.review_conformance_probe.EphemeralOpenAITransport",
                return_value=openai,
            )
        )

        def anthropic_transport(key: str, timeout: float) -> FakeAnthropic:
            return judge if probe.controller.phase == "judge_running" else anthropic

        self.enterContext(
            patch(
                "mos_eisley.run.review_conformance_probe.EphemeralAnthropicTransport",
                side_effect=anthropic_transport,
            )
        )
        with self.assertRaisesRegex(ValueError, "separate loader"):
            BrokeredReviewConformanceProbe(
                envelope,
                self.base.reviewer,
                ReviewPolicy(),
                ScriptedUser(("approve", "approve")),
                critic_containers=containers[:2],
                judge_container=containers[2],
                authority_policy=lambda: policy,
                load_authorization=load,
                load_api_key=anthropic_loader,
            )
        probe = BrokeredReviewConformanceProbe(
            envelope,
            self.base.reviewer,
            ReviewPolicy(),
            ScriptedUser(("approve", "approve")),
            critic_containers=containers[:2],
            judge_container=containers[2],
            authority_policy=lambda: policy,
            load_authorization=load,
            load_api_key=anthropic_loader,
            load_api_keys={"openai": openai_loader, "anthropic": anthropic_loader},
            operator_identity=OperatorReviewIdentity(
                author_provider="openai",
                author_model="gpt-6",
                author_artifact_sha256=digest(
                    self.base.request.brief.diff.encode("utf-8")
                ),
                max_total_microusd=20_000,
            ),
        )
        result = await probe.run()
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(
            [(s.phase, s.provider) for s in seen_scopes],
            [("critics", "mixed"), ("judge", "anthropic")],
        )
        self.assertEqual(
            {scope.sdk_version for scope in seen_scopes},
            {review_sdk_version({"openai", "anthropic"})},
        )
        self.assertEqual((openai.counts, openai.calls), (1, 1))
        self.assertEqual((anthropic.counts, anthropic.calls), (1, 1))
        self.assertEqual((judge.counts, judge.calls), (1, 1))
        self.assertEqual(openai_loader.call_count, 2)
        self.assertEqual(anthropic_loader.call_count, 4)
        self.assertEqual(self.base.ledger.snapshot().unresolved_entries, 0)
        start, judge_preview = probe.controller.start, probe.judge_preview
        assert start is not None and judge_preview is not None
        authorizations = probe.approval_ui.authorizations
        observed = tuple(
            collect_review_runtime_exchange(
                directory,
                lifecycle,
                request,
                authorizations[1 if index == len(calls) else 0].authorization,
            )
            for index, (directory, lifecycle, request) in enumerate(
                zip(
                    (
                        *(
                            Path(envelope.envelope.artifact_directory)
                            / call.authorization.ledger_entry_id
                            for call in calls
                        ),
                        Path(envelope.envelope.artifact_directory) / "judge",
                    ),
                    lifecycles,
                    (*probe.controller.preview.requests, judge_preview.model_request),
                    strict=True,
                )
            )
        )
        observation_policy = ReviewObservationPolicy(
            policy_id="synthetic-mixed-observer",
            authority_policy_sha256=policy.sha256,
            critic_preview_sha256=digest(canonical_bytes(probe.controller.preview)),
            valid_from=policy.valid_from,
            valid_until=policy.valid_until,
            max_observation_age_seconds=600,
        )
        signed_observation = sign_review_probe_observation(
            make_review_probe_observation(
                observation_policy,
                policy,
                probe.controller.preview,
                start,
                judge_preview,
                (authorizations[0], authorizations[1]),
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
            probe.controller.preview,
            start,
            judge_preview,
            (authorizations[0], authorizations[1]),
            self.base.reviewer,
            self.base.ledger,
            expected_result_sha256=digest(canonical_bytes(result)),
            now=datetime.now(UTC),
        )
        self.assertTrue(authenticated.local_artifacts_verified)
        for path in Path(envelope.envelope.artifact_directory).rglob("*"):
            if path.is_file():
                self.assertNotIn(b"openai-test-key", path.read_bytes())
                self.assertNotIn(b"anthropic-test-key", path.read_bytes())
