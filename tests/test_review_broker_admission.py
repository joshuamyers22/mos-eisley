"""Review approval, durable issuance and real-pipe dispatch without paid calls."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pydantic import JsonValue
from test_brokered_model_client import output as model_output
from test_openai_spend import FakeTransport, cache_write_policy

from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import (
    Brief,
    CriticRequest,
    CriticSpec,
    Critique,
    Evidence,
    Finding,
    JudgeDecision,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.brokered_openai import BrokeredOpenAIClient
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.broker_audit import (
    AssignmentAuthorization,
    verify_broker_audit,
)
from mos_eisley.run.duplex import ExchangeHandler, bounded_exchange
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_broker import (
    PreparedReviewCall,
    ReviewAuthorization,
    verify_review_broker_audit,
)
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger


def output(text: str) -> dict[str, JsonValue]:
    body = model_output(text)
    body["usage"] = {
        "input_tokens": 10,
        "output_tokens": 5,
        "input_tokens_details": {"cache_write_tokens": 0},
    }
    return body


class BoundClient:
    target: BrokeredOpenAIClient | None = None

    async def complete(self, request: ModelRequest) -> ModelResponse:
        assert self.target is not None, "preview must not invoke the model client"
        return await self.target.complete(request)


class ReviewAdmissionTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "call"
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 1000)
        self.policy = cache_write_policy().model_copy(
            update={"max_input_tokens": 100, "max_output_tokens": 100}
        )
        self.client = BoundClient()
        self.reviewer = ModelReviewer(
            self.client,
            openai_registry(),
            judge_provider="openai",
            judge_model="gpt-6-astra",
            budget=BudgetPolicy(max_output_tokens=100),
        )
        self.critic = CriticSpec(
            id="one", provider="openai", model="gpt-6-astra", persona="correctness"
        )
        self.request = CriticRequest(
            brief=Brief(spec="Return one", diff="return 1"), persona="correctness"
        )
        self.prepared = self.prepare()
        self.fake = FakeTransport(self.directory)
        self.fake.response = output(canonical_bytes(Critique()).decode())
        self.container = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)
        self.workers = 0
        self.finished = False
        patcher = patch.object(
            self.container, "exchange_async", side_effect=self.exchange
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def prepare(self, policy: SpendPolicy | None = None) -> PreparedReviewCall:
        return PreparedReviewCall(
            self.reviewer,
            self.request,
            self.policy if policy is None else policy,
            self.ledger,
            critic=self.critic,
        )

    def issue(self, prepared: PreparedReviewCall | None = None) -> BrokeredOpenAIClient:
        prepared = self.prepared if prepared is None else prepared
        return prepared.issue(
            approved_transfer_sha256=prepared.approval_sha256,
            transport=self.fake,
            directory=self.directory,
            container=self.container,
        )

    async def exchange(
        self,
        arguments: tuple[str, ...],
        payload: bytes,
        handler: ExchangeHandler,
        timeout: float,
    ) -> bytes:
        self.workers += 1
        try:
            return await bounded_exchange(
                [sys.executable, *arguments], payload, handler, timeout
            )
        finally:
            self.finished = True

    def test_preview_has_no_dispatch_storage_or_reservation(self) -> None:
        self.assertEqual(self.fake.counts, [])
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.ledger.snapshot().entries, 0)
        self.assertFalse(self.directory.exists())
        self.assertEqual(
            self.prepared.model_request,
            self.reviewer.critic_request(self.critic, self.request),
        )
        self.assertEqual(self.prepared.authorization.reserved_microusd, 325)
        self.assertEqual(
            self.prepared.authorization.brief_sha256, self.request.brief.brief_id
        )

    def test_exact_confirmation_required_before_any_effect(self) -> None:
        for confirmation in (
            "",
            "0" * 64,
            self.prepared.authorization.model_request_sha256,
        ):
            with self.subTest(confirmation=confirmation), self.assertRaises(ValueError):
                self.prepared.issue(
                    approved_transfer_sha256=confirmation,
                    transport=self.fake,
                    directory=self.directory,
                    container=self.container,
                )
        self.assertEqual(self.ledger.snapshot().entries, 0)
        self.assertFalse(self.directory.exists())

    async def test_critic_pipeline_projection_dispatches_and_verifies_private_audit(
        self,
    ) -> None:
        self.client.target = self.issue()
        self.assertEqual(self.ledger.snapshot().charged_microusd, 325)
        self.assertEqual(self.fake.counts, [])
        self.assertFalse((self.directory / "admission.json").exists())
        with self.assertRaises(FileNotFoundError):
            verify_review_broker_audit(self.directory, self.prepared.authorization)
        answer = await self.reviewer.critique(self.critic, self.request)
        self.assertEqual(answer, Critique())
        self.assertTrue(self.finished)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)
        self.assertEqual(len(self.fake.calls), 1)
        outcome = verify_review_broker_audit(
            self.directory, self.prepared.authorization
        )
        self.assertEqual(outcome.status, "response_received")
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        for artifact in self.directory.iterdir():
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(b'"capability"', artifact.read_bytes())

    async def test_judge_exact_findings_use_same_projection_and_separate_approval(
        self,
    ) -> None:
        finding = Finding(
            location="diff",
            category="correctness",
            impact="low",
            claim="Fixture",
            evidence=Evidence(source="diff", quote="return 1", explanation="Fixture"),
        )
        request = JudgeRequest(brief=self.request.brief, findings=(finding,))
        prepared = PreparedReviewCall(self.reviewer, request, self.policy, self.ledger)
        self.assertEqual(prepared.authorization.role, "judge")
        self.assertIsNone(prepared.authorization.critic_sha256)
        self.assertIn(
            finding.finding_id, canonical_bytes(prepared.model_request).decode()
        )
        self.assertNotIn("persona", canonical_bytes(prepared.model_request).decode())
        changed = PreparedReviewCall(
            self.reviewer,
            request.model_copy(update={"findings": ()}),
            self.policy,
            self.ledger,
        )
        self.assertNotEqual(
            prepared.authorization.model_request_sha256,
            changed.authorization.model_request_sha256,
        )
        answer = JudgeDecision(upheld=(finding.finding_id,), rationale="Fixture")
        self.fake.response = output(canonical_bytes(answer).decode())
        self.client.target = self.issue(prepared)
        self.assertEqual(await self.reviewer.judge(request), answer)
        self.assertEqual(
            verify_review_broker_audit(self.directory, prepared.authorization).status,
            "response_received",
        )
        self.assertFalse((self.directory / "critic.json").exists())

    def test_role_pairing_and_persona_mismatch_reject_without_spend(self) -> None:
        with self.assertRaises(ValueError):
            PreparedReviewCall(self.reviewer, self.request, self.policy, self.ledger)
        with self.assertRaises(ValueError):
            PreparedReviewCall(
                self.reviewer,
                JudgeRequest(brief=self.request.brief, findings=()),
                self.policy,
                self.ledger,
                critic=self.critic,
            )
        with self.assertRaises(ValueError):
            PreparedReviewCall(
                self.reviewer,
                self.request.model_copy(update={"persona": "different"}),
                self.policy,
                self.ledger,
                critic=self.critic,
            )
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_full_envelope_model_and_output_cap_must_match_policy(self) -> None:
        for update in (
            {"model": "different"},
            {"max_output_tokens": 99},
            {"max_output_tokens": 101},
            {"max_cost_microusd": 324},
            {"max_input_tokens": 1000},
        ):
            with (
                self.subTest(update=update),
                self.assertRaises((ValueError, ProviderError)),
            ):
                self.prepare(self.policy.model_copy(update=update))
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_expired_pricing_and_approval_reject_before_reservation(self) -> None:
        with self.assertRaises(ValueError):
            self.prepare(
                self.policy.model_copy(
                    update={"valid_until": datetime.now(UTC) - timedelta(seconds=1)}
                )
            )
        future = self.prepared.authorization.expires_at + timedelta(seconds=1)
        with patch("mos_eisley.run.review_broker.datetime") as clock:
            clock.now.return_value = future
            with self.assertRaises(ValueError):
                self.issue()
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_policy_must_still_be_current_at_issue(self) -> None:
        future = self.policy.valid_until + timedelta(seconds=1)
        with patch("mos_eisley.providers.openai_spend.datetime") as clock:
            clock.now.return_value = future
            with self.assertRaises(ValueError):
                self.issue()
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_ledger_identity_or_ceiling_change_denies_issue(self) -> None:
        self.ledger.policy = self.ledger.policy.model_copy(
            update={"ceiling_microusd": 2000}
        )
        with self.assertRaises(ValueError):
            self.issue()
        self.assertFalse(self.directory.exists())

    def test_intervening_spend_is_rechecked_atomically(self) -> None:
        self.ledger.reserve(
            LedgerEntry(
                entry_id="a" * 64, reservation_sha256="b" * 64, reserved_microusd=800
            )
        )
        with self.assertRaises(ValueError):
            self.issue()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.ledger.snapshot().entries, 1)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.fake.counts, [])

    def test_concurrent_issuers_with_different_paths_burn_one_approval(self) -> None:
        def issue(index: int) -> bool:
            try:
                self.prepared.issue(
                    approved_transfer_sha256=self.prepared.approval_sha256,
                    transport=self.fake,
                    directory=self.root / str(index),
                    container=self.container,
                )
            except sqlite3.Error:
                return False
            return True

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(issue, (0, 1))), [False, True])
        self.assertEqual(self.ledger.snapshot().entries, 1)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 325)
        self.assertEqual(self.fake.counts, [])

    def test_failed_artifact_creation_keeps_hold_and_prevents_reissue(self) -> None:
        self.directory.mkdir()
        with self.assertRaises(FileExistsError):
            self.issue()
        with self.assertRaises(sqlite3.IntegrityError):
            self.issue()
        self.assertEqual(self.ledger.snapshot().charged_microusd, 325)
        self.assertEqual(self.fake.counts, [])

    async def test_consumed_approval_and_client_cannot_retry(self) -> None:
        client = self.issue()
        await client.complete(self.prepared.model_request)
        with self.assertRaises(sqlite3.IntegrityError):
            self.issue()
        with self.assertRaises(ProviderError):
            await client.complete(self.prepared.model_request)
        self.assertEqual(self.workers, 1)

    async def test_local_request_change_does_not_send_or_release_hold(self) -> None:
        client = self.issue()
        with self.assertRaises(ProviderError):
            await client.complete(
                self.prepared.model_request.model_copy(update={"max_output": 9000})
            )
        self.assertEqual(self.fake.counts, [])
        self.assertEqual(self.workers, 0)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 325)

    async def test_audit_checks_all_retained_artifacts_and_expected_binding(
        self,
    ) -> None:
        await self.issue().complete(self.prepared.model_request)
        for name in (
            "model-request.json",
            "review-input.json",
            "critic.json",
            "spend-policy.json",
            "spend-plan.json",
            "authorization.json",
            "admission.json",
            "outcome.json",
        ):
            path = self.directory / name
            original = path.read_bytes()
            path.write_bytes(b"{}")
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_review_broker_audit(self.directory, self.prepared.authorization)
            path.write_bytes(original)
        with self.assertRaises(ValueError):
            verify_review_broker_audit(self.directory, self.prepare().authorization)

    async def test_research_reader_rejects_review_mode(self) -> None:
        await self.issue().complete(self.prepared.model_request)
        binding = self.prepared.authorization
        assignment = AssignmentAuthorization(
            plan_sha256="0" * 64,
            batch_sha256="1" * 64,
            sample_id="2" * 64,
            candidate_id="3" * 64,
            evaluation_request_sha256="4" * 64,
            provider_request_sha256=binding.provider_request_sha256,
            spend_policy_sha256=binding.spend_policy_sha256,
            ledger_id=binding.ledger_id,
            ledger_entry_id=binding.ledger_entry_id,
        )
        with self.assertRaises(ValueError):
            verify_broker_audit(self.directory, assignment)
        (self.directory / "authorization.json").write_bytes(canonical_bytes(assignment))
        with self.assertRaises(ValueError):
            verify_review_broker_audit(self.directory, binding)

    async def test_cancel_after_dispatch_retains_uncertain_full_envelope(self) -> None:
        started = asyncio.Event()

        async def slow(_: object) -> dict[str, JsonValue]:
            started.set()
            await asyncio.sleep(10)
            return {}

        with patch.object(self.fake, "create_response", side_effect=slow):
            task = asyncio.create_task(
                self.issue().complete(self.prepared.model_request)
            )
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        status = self.ledger.entry_status(self.prepared.authorization.ledger_entry_id)
        assert status is not None
        self.assertEqual(status.status, "uncertain")
        self.assertEqual(status.charged_microusd, 325)
        self.assertEqual(
            verify_review_broker_audit(
                self.directory, self.prepared.authorization
            ).status,
            "cancelled",
        )
        self.assertTrue(self.finished)

    async def test_token_count_failure_keeps_reservation_without_generation(
        self,
    ) -> None:
        with (
            patch.object(
                self.fake, "count_input_tokens", side_effect=ProviderError("SECRET")
            ),
            self.assertRaises(ProviderError) as raised,
        ):
            await self.issue().complete(self.prepared.model_request)
        self.assertNotIn("SECRET", str(raised.exception))
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.ledger.snapshot().charged_microusd, 325)
        self.assertEqual(
            verify_review_broker_audit(
                self.directory, self.prepared.authorization
            ).status,
            "failed",
        )

    async def test_invalid_review_response_keeps_actual_charge(self) -> None:
        self.fake.response = output("not JSON")
        self.client.target = self.issue()
        with self.assertRaises(ProviderError):
            await self.reviewer.critique(self.critic, self.request)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)
        # Host receipt is deliberately distinct from successful review parsing.
        self.assertEqual(
            verify_review_broker_audit(
                self.directory, self.prepared.authorization
            ).status,
            "response_received",
        )

    def test_review_rejects_legacy_spending_without_cache_write_envelope(self) -> None:
        with self.assertRaises(ValueError):
            self.prepare(
                self.policy.model_copy(
                    update={
                        "schema_version": 1,
                        "cache_write_microusd_per_million": None,
                    }
                )
            )
        self.assertEqual(self.ledger.snapshot().entries, 0)

    async def test_review_rejects_downgraded_outcome(self) -> None:
        import json

        await self.issue().complete(self.prepared.model_request)
        path = self.directory / "outcome.json"
        value = json.loads(path.read_bytes())
        value["schema_version"] = 1
        value["error"] = None
        value.pop("failure_stage", None)
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            verify_review_broker_audit(self.directory, self.prepared.authorization)

    def test_invalid_timeout_does_not_reserve(self) -> None:
        for timeout in (0, 61, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.prepared.issue(
                    approved_transfer_sha256=self.prepared.approval_sha256,
                    transport=self.fake,
                    directory=self.directory,
                    container=self.container,
                    timeout=timeout,
                )
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_authorization_schema_rejects_role_and_timezone_confusion(self) -> None:
        for update in (
            {"role": "judge"},
            {"critic_sha256": None},
            {"expires_at": datetime.now()},
            {"mode": "broker_conformance"},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                ReviewAuthorization.model_validate_json(
                    canonical_bytes(
                        self.prepared.authorization.model_copy(update=update)
                    )
                )
        self.assertEqual(
            self.prepared.authorization.model_request_sha256,
            digest(canonical_bytes(self.prepared.model_request)),
        )
