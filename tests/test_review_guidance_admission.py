"""Current guidance checks at actual reservation and provider boundaries."""

import asyncio
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import test_project_guidance_review as guidance_fixture
import test_review_broker_admission as broker_fixture
from pydantic import JsonValue

from mos_eisley.core.models import (
    JudgeDecision,
    ReviewPolicy,
    canonical_bytes,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.model_evidence import ModelCompletion
from mos_eisley.run.review_broker import (
    PreparedReviewCall,
    PreparedReviewEnvelope,
    verify_review_broker_audit,
)
from mos_eisley.run.review_evidence import (
    PreparedEvidenceJudgeTransfer,
    verify_evidence_judge_transfer,
)
from mos_eisley.run.review_guidance import ReviewGuidanceAdmission


class GuidedBrokerFixture(TestCase):
    def setUp(self) -> None:
        self.guided = guidance_fixture.GuidedReviewTests()
        self.guided.setUp()
        self.addCleanup(self.guided.doCleanups)
        self.base = broker_fixture.ReviewAdmissionFixture()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.admission = ReviewGuidanceAdmission(
            self.guided.store,
            self.guided.fixture.workspace,
            self.guided.prepared,
            self.guided.fixture.policy_path,
            self.guided.policy_sha,
        )
        self.base.request = self.base.request.model_copy(
            update={"brief": self.guided.prepared.brief}
        )
        self.call = self.prepare()

    def prepare(self) -> PreparedReviewCall:
        return PreparedReviewCall(
            self.base.reviewer,
            self.base.request,
            self.base.policy,
            self.base.ledger,
            critic=self.base.critic,
            guidance=self.admission,
        )

    def invalidate(self) -> None:
        self.guided.fixture.add_requirement()

    def envelope(self) -> PreparedReviewEnvelope:
        return PreparedReviewEnvelope(
            (self.call,),
            self.base.policy,
            self.base.ledger,
            max_total_microusd=650,
            directory=self.base.root / "envelope",
        )

    async def finish_critic(self, envelope: PreparedReviewEnvelope) -> None:
        reserved = envelope.reserve(approved_envelope_sha256=envelope.approval_sha256)
        self.base.fake.directory = (
            self.base.root / "envelope" / self.call.authorization.ledger_entry_id
        )
        client = reserved.issue_critic(
            0, transport=self.base.fake, container=self.base.container
        )
        await client.complete(self.call.model_request)


class GuidedBrokerTests(GuidedBrokerFixture, IsolatedAsyncioTestCase):
    def test_preview_binds_guidance_and_keeps_legacy_authorization_bytes(self) -> None:
        self.assertEqual(
            self.call.authorization.guidance_sha256, self.guided.prepared.sha256
        )
        self.assertNotIn(
            b'"guidance_sha256"', canonical_bytes(self.base.prepared.authorization)
        )
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
        payload = canonical_bytes(self.call.model_request)
        self.assertIn(b"Use batch execution.", payload)
        self.assertNotIn(b"PRIVATE-POLICY-PROSE-CANARY", payload)
        self.assertNotIn(str(self.guided.fixture.policy_path).encode(), payload)

    def test_wrong_brief_rejects_before_reservation(self) -> None:
        self.base.request = self.base.request.model_copy(
            update={"brief": self.guided.source}
        )
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_changed_policy_is_not_replaced_by_retained_policy(self) -> None:
        self.guided.fixture.policy_path.write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "guidance changed"):
            self.base.issue(self.call)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_stale_before_issue_creates_no_reservation_or_audit(self) -> None:
        self.invalidate()
        with self.assertRaises(ValueError):
            self.base.issue(self.call)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
        self.assertFalse(self.base.directory.exists())

    async def test_stale_after_issue_burns_client_without_starting_worker(self) -> None:
        client = self.base.issue(self.call)
        self.invalidate()
        with self.assertRaises(ProviderError):
            await client.complete(self.call.model_request)
        with self.assertRaises(ProviderError):
            await client.complete(self.call.model_request)
        self.assertEqual(self.base.workers, 0)
        self.assertEqual(self.base.fake.counts, [])
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 325)

    async def test_change_during_count_prevents_generation_and_keeps_exposure(
        self,
    ) -> None:
        original = self.base.fake.count_input_tokens

        async def count(payload: dict[str, JsonValue]) -> int:
            value = await original(payload)
            self.invalidate()
            return value

        with patch.object(self.base.fake, "count_input_tokens", side_effect=count):
            client = self.base.issue(self.call)
            with self.assertRaises(ProviderError):
                await client.complete(self.call.model_request)
        self.assertEqual(len(self.base.fake.counts), 1)
        self.assertEqual(self.base.fake.calls, [])
        status = self.base.ledger.entry_status(self.call.ledger_entry.entry_id)
        assert status is not None
        self.assertEqual(status.status, "uncertain")
        self.assertEqual(status.charged_microusd, 325)

    async def test_change_during_response_discards_answer_and_keeps_exposure(
        self,
    ) -> None:
        original = self.base.fake.create_response

        async def respond(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
            value = await original(payload)
            self.invalidate()
            return value

        with patch.object(self.base.fake, "create_response", side_effect=respond):
            client = self.base.issue(self.call)
            with self.assertRaises(ProviderError):
                await client.complete(self.call.model_request)
        self.assertEqual(len(self.base.fake.calls), 1)
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 325)
        self.assertFalse((self.base.directory / "model-response.json").exists())

    async def test_change_during_cleanup_prevents_model_completion(self) -> None:
        async def exchange(
            arguments: tuple[str, ...],
            payload: bytes,
            handler: ExchangeHandler,
            timeout: float,
        ) -> bytes:
            result = await self.base.exchange(arguments, payload, handler, timeout)
            self.invalidate()
            return result

        with patch.object(self.base.container, "exchange_async", side_effect=exchange):
            client = self.base.issue(self.call)
            with self.assertRaises(ProviderError):
                await client.complete(self.call.model_request)
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 20)
        completion = ModelCompletion.model_validate_json(
            (self.base.directory / "model-completion.json").read_bytes()
        )
        self.assertEqual(completion.status, "failed")
        self.assertIsNone(completion.model_response_sha256)

    async def test_change_before_worker_claim_prevents_token_count(self) -> None:
        async def exchange(
            arguments: tuple[str, ...],
            payload: bytes,
            handler: ExchangeHandler,
            timeout: float,
        ) -> bytes:
            self.invalidate()
            return await self.base.exchange(arguments, payload, handler, timeout)

        with patch.object(self.base.container, "exchange_async", side_effect=exchange):
            client = self.base.issue(self.call)
            with self.assertRaises(ProviderError):
                await client.complete(self.call.model_request)
        self.assertEqual(self.base.workers, 1)
        self.assertEqual(self.base.fake.counts, [])
        self.assertEqual(self.base.fake.calls, [])

    def test_workspace_and_expected_policy_must_match_selected_guidance(self) -> None:
        other = self.base.root / "other-workspace"
        other.mkdir()
        for workspace, policy_sha in (
            (other, self.guided.policy_sha),
            (self.guided.fixture.workspace, "a" * 64),
        ):
            with self.subTest(workspace=workspace), self.assertRaises(ValueError):
                ReviewGuidanceAdmission(
                    self.guided.store,
                    workspace,
                    self.guided.prepared,
                    self.guided.fixture.policy_path,
                    policy_sha,
                )

    async def test_cancellation_is_preserved(self) -> None:
        async def cancelled(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
            raise asyncio.CancelledError

        with patch.object(self.base.fake, "create_response", side_effect=cancelled):
            client = self.base.issue(self.call)
            with self.assertRaises(asyncio.CancelledError):
                await client.complete(self.call.model_request)
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 325)

    async def test_history_checks_pinned_guidance_without_opening_current_policy(
        self,
    ) -> None:
        client = self.base.issue(self.call)
        await client.complete(self.call.model_request)
        self.guided.fixture.policy_path.unlink()
        outcome = verify_review_broker_audit(
            self.base.directory, self.call.authorization
        )
        self.assertEqual(outcome.status, "response_received")
        path = self.base.directory / "guidance-review.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        path.write_bytes(b"{}")
        with self.assertRaises(ValueError):
            verify_review_broker_audit(self.base.directory, self.call.authorization)

    def test_envelope_rejects_mixed_guidance_admission(self) -> None:
        other = PreparedReviewCall(
            self.base.reviewer,
            self.base.request,
            self.base.policy,
            self.base.ledger,
            critic=self.base.critic.model_copy(update={"id": "two"}),
        )
        with self.assertRaises(ValueError):
            PreparedReviewEnvelope(
                (self.call, other),
                self.base.policy,
                self.base.ledger,
                max_total_microusd=975,
                directory=self.base.root / "envelope",
            )

    def test_envelope_rechecks_before_reserving(self) -> None:
        envelope = self.envelope()
        self.invalidate()
        with self.assertRaises(ValueError):
            envelope.reserve(approved_envelope_sha256=envelope.approval_sha256)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_reserved_critic_rechecks_before_issuance(self) -> None:
        envelope = self.envelope()
        reserved = envelope.reserve(approved_envelope_sha256=envelope.approval_sha256)
        self.invalidate()
        with self.assertRaises(ValueError):
            reserved.issue_critic(
                0, transport=self.base.fake, container=self.base.container
            )
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 650)
        self.assertFalse(
            (
                self.base.root / "envelope" / self.call.authorization.ledger_entry_id
            ).exists()
        )

    async def test_evidence_judge_inherits_guidance_and_rechecks_before_transfer(
        self,
    ) -> None:
        envelope = self.envelope()
        await self.finish_critic(envelope)
        transfer = PreparedEvidenceJudgeTransfer(
            envelope, self.base.reviewer, ReviewPolicy(min_critics=1, min_providers=1)
        )
        self.invalidate()
        before = self.base.ledger.snapshot()
        with self.assertRaises(ValueError):
            transfer.issue(
                approved_evidence_sha256=transfer.approval_sha256,
                transport=self.base.fake,
                container=self.base.container,
            )
        self.assertEqual(self.base.ledger.snapshot(), before)
        self.assertFalse((self.base.root / "envelope" / "judge-transfer.json").exists())

    async def test_guided_judge_finishes_and_remains_historically_verifiable(
        self,
    ) -> None:
        envelope = self.envelope()
        await self.finish_critic(envelope)
        transfer = PreparedEvidenceJudgeTransfer(
            envelope, self.base.reviewer, ReviewPolicy(min_critics=1, min_providers=1)
        )
        self.base.fake.directory = self.base.root / "envelope" / "judge"
        self.base.fake.response = broker_fixture.output(
            canonical_bytes(JudgeDecision(upheld=(), rationale="Fixture")).decode()
        )
        client = transfer.issue(
            approved_evidence_sha256=transfer.approval_sha256,
            transport=self.base.fake,
            container=self.base.container,
        )
        await client.complete(transfer.model_request)
        self.invalidate()
        self.assertEqual(
            verify_evidence_judge_transfer(
                envelope.envelope,
                self.base.reviewer,
                self.base.ledger,
                transfer.authorization,
            ).status,
            "response_received",
        )
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 40)
