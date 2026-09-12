"""Explicit exact-request approval consumes the existing judge allowance once."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from test_openai_spend import FakeTransport, cache_write_policy
from test_review_broker_admission import BoundClient, output

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
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.run.duplex import ExchangeHandler, bounded_exchange
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_broker import (
    PreparedJudgeTransfer,
    PreparedReviewCall,
    PreparedReviewEnvelope,
    verify_judge_transfer,
)
from mos_eisley.run.spend_ledger import LedgerSettlement, SpendLedger


class JudgeReservationTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "review"
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 650)
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
        self.brief = Brief(spec="Return one", diff="return 1")
        self.critic_spec = CriticSpec(
            id="one", provider="openai", model="gpt-6-astra", persona="correctness"
        )
        self.critic = PreparedReviewCall(
            self.reviewer,
            CriticRequest(brief=self.brief, persona="correctness"),
            self.policy,
            self.ledger,
            critic=self.critic_spec,
        )
        self.envelope = PreparedReviewEnvelope(
            (self.critic,),
            self.policy,
            self.ledger,
            max_total_microusd=650,
            directory=self.directory,
        )
        self.reserved = self.envelope.reserve(
            approved_envelope_sha256=self.envelope.approval_sha256
        )
        self.request = JudgeRequest(brief=self.brief, findings=())
        self.fake = FakeTransport(self.directory / "judge")
        self.answer = JudgeDecision(upheld=(), rationale="Fixture")
        self.fake.response = output(canonical_bytes(self.answer).decode())
        self.container = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)
        patcher = patch.object(
            self.container, "exchange_async", side_effect=self.exchange
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    async def exchange(
        self,
        arguments: tuple[str, ...],
        payload: bytes,
        handler: ExchangeHandler,
        timeout: float,
    ) -> bytes:
        return await bounded_exchange(
            [sys.executable, *arguments], payload, handler, timeout
        )

    def terminal_critic(self) -> None:
        # Accounting fixture only; this boundary does not assert finding lineage.
        entry = self.critic.ledger_entry
        self.ledger.settle(
            LedgerSettlement(
                entry_id=entry.entry_id,
                reservation_sha256=entry.reservation_sha256,
                status="settled",
                charged_microusd=20,
            )
        )

    def prepare(self) -> PreparedJudgeTransfer:
        return PreparedJudgeTransfer(self.envelope, self.reviewer, self.request)

    def issue(self, prepared: PreparedJudgeTransfer) -> None:
        self.client.target = prepared.issue(
            approved_transfer_sha256=prepared.approval_sha256,
            transport=self.fake,
            container=self.container,
        )

    def test_judge_waits_for_terminal_critic_spending(self) -> None:
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.ledger.snapshot().charged_microusd, 650)

    def test_preview_uses_existing_capacity_without_reserving_twice(self) -> None:
        self.terminal_critic()
        before = self.ledger.snapshot()
        self.assertEqual(before.available_microusd, 305)
        prepared = self.prepare()
        self.assertEqual(self.ledger.snapshot(), before)
        self.assertEqual(prepared.authorization.call.reserved_microusd, 325)
        self.assertEqual(
            prepared.model_request, self.reviewer.judge_request(self.request)
        )
        self.assertEqual(self.fake.counts, [])
        self.assertFalse((self.directory / "judge-transfer.json").exists())

    def test_single_call_or_envelope_hash_cannot_authorize_judge_transfer(self) -> None:
        self.terminal_critic()
        prepared = self.prepare()
        for approval in (self.envelope.approval_sha256, "0" * 64):
            with self.subTest(approval=approval), self.assertRaises(ValueError):
                prepared.issue(
                    approved_transfer_sha256=approval,
                    transport=self.fake,
                    container=self.container,
                )
        call = PreparedReviewCall(
            self.reviewer,
            self.request,
            self.policy,
            self.ledger,
            reserved_allowance=self.envelope.envelope.judge,
        )
        with self.assertRaises(ValueError):
            call.issue(
                approved_transfer_sha256=call.approval_sha256,
                transport=self.fake,
                container=self.container,
                directory=self.directory / "bypass",
            )
        self.assertEqual(self.ledger.snapshot().entries, 2)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 345)

    async def test_actual_critic_then_judge_preserves_total_and_audit_chain(
        self,
    ) -> None:
        fake = FakeTransport(self.directory / self.critic.authorization.ledger_entry_id)
        fake.response = output(canonical_bytes(Critique()).decode())
        client = self.reserved.issue_critic(0, transport=fake, container=self.container)
        await client.complete(self.critic.model_request)
        prepared = self.prepare()
        self.issue(prepared)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 345)
        self.assertEqual(self.ledger.snapshot().entries, 3)
        self.assertEqual(self.fake.counts, [])
        self.assertEqual(await self.reviewer.judge(self.request), self.answer)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 40)
        self.assertEqual(
            verify_judge_transfer(
                self.directory, prepared.authorization, self.ledger
            ).status,
            "response_received",
        )
        self.assertEqual(
            (self.directory / "judge-transfer.json").stat().st_mode & 0o777, 0o600
        )

    def test_changed_brief_or_judge_budget_cannot_consume_allowance(self) -> None:
        self.terminal_critic()
        with self.assertRaises(ValueError):
            PreparedJudgeTransfer(
                self.envelope,
                self.reviewer,
                JudgeRequest(brief=Brief(spec="Other", diff="return 2"), findings=()),
            )
        reviewer = ModelReviewer(
            BoundClient(),
            openai_registry(),
            judge_provider="openai",
            judge_model="gpt-6-astra",
            budget=BudgetPolicy(max_output_tokens=99),
        )
        with self.assertRaises(ValueError):
            PreparedJudgeTransfer(self.envelope, reviewer, self.request)
        self.assertEqual(self.ledger.snapshot().entries, 2)

    def test_different_findings_need_a_different_exact_approval(self) -> None:
        self.terminal_critic()
        first = self.prepare()
        finding = Finding(
            location="diff",
            category="correctness",
            impact="low",
            claim="Fixture",
            evidence=Evidence(source="diff", quote="return 1", explanation="Fixture"),
        )
        other = PreparedJudgeTransfer(
            self.envelope,
            self.reviewer,
            JudgeRequest(brief=self.brief, findings=(finding,)),
        )
        self.assertNotEqual(
            first.authorization.call.model_request_sha256,
            other.authorization.call.model_request_sha256,
        )
        self.assertIn(finding.finding_id, canonical_bytes(other.model_request).decode())
        with self.assertRaises(ValueError):
            other.issue(
                approved_transfer_sha256=first.approval_sha256,
                transport=self.fake,
                container=self.container,
            )

    def test_two_previews_cannot_transfer_the_same_allowance_twice(self) -> None:
        self.terminal_critic()
        first, second = self.prepare(), self.prepare()
        self.issue(first)
        for prepared in (first, second):
            with self.subTest(prepared=prepared), self.assertRaises(ValueError):
                self.issue(prepared)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 345)
        self.assertEqual(self.ledger.snapshot().entries, 3)

    def test_post_transfer_storage_failure_retains_destination_and_blocks_retry(
        self,
    ) -> None:
        self.terminal_critic()
        prepared = self.prepare()
        (self.directory / "judge-transfer.json").write_bytes(b"occupied")
        with self.assertRaises(FileExistsError):
            self.issue(prepared)
        with self.assertRaises(ValueError):
            self.issue(prepared)
        target = self.ledger.entry_status(prepared.authorization.call.ledger_entry_id)
        assert target is not None
        self.assertEqual((target.status, target.charged_microusd), ("held", 325))
        self.assertEqual(self.fake.counts, [])

    async def test_cancelled_judge_keeps_full_transferred_reservation(self) -> None:
        self.terminal_critic()
        prepared = self.prepare()
        started = asyncio.Event()

        async def count(_: object) -> int:
            started.set()
            await asyncio.sleep(10)
            return 10

        with patch.object(self.fake, "count_input_tokens", side_effect=count):
            self.issue(prepared)
            task = asyncio.create_task(self.reviewer.judge(self.request))
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.ledger.snapshot().charged_microusd, 345)
        self.assertEqual(
            verify_judge_transfer(
                self.directory, prepared.authorization, self.ledger
            ).status,
            "cancelled",
        )

    async def test_transfer_verifier_rejects_artifact_and_ledger_substitution(
        self,
    ) -> None:
        self.terminal_critic()
        prepared = self.prepare()
        self.issue(prepared)
        await self.reviewer.judge(self.request)
        for name in (
            "envelope.json",
            "judge-transfer.json",
            "judge/model-request.json",
            "judge/outcome.json",
        ):
            path = self.directory / name
            original = path.read_bytes()
            path.write_bytes(b"{}")
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_judge_transfer(
                    self.directory, prepared.authorization, self.ledger
                )
            path.write_bytes(original)
        other = SpendLedger.create(self.root / "other.sqlite", 650)
        with self.assertRaises(ValueError):
            verify_judge_transfer(self.directory, prepared.authorization, other)

    def test_terminal_critic_must_match_approved_reservation(
        self,
    ) -> None:
        self.terminal_critic()
        with closing(sqlite3.connect(self.ledger.path)) as connection, connection:
            connection.execute(
                "UPDATE entries SET reservation_sha256 = ? WHERE entry_id = ?",
                ("f" * 64, self.critic.authorization.ledger_entry_id),
            )
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.ledger.snapshot().entries, 2)

    def test_expiry_after_preview_keeps_original_allowance(self) -> None:
        self.terminal_critic()
        prepared = self.prepare()
        with patch("mos_eisley.run.review_broker.datetime") as clock:
            clock.now.return_value = self.envelope.envelope.expires_at + timedelta(
                seconds=1
            )
            with self.assertRaises(ValueError):
                self.issue(prepared)
        with self.ledger.guard_held(self.envelope.envelope.judge.ledger_entry):
            pass
        self.assertEqual(self.ledger.snapshot().entries, 2)

    def test_changed_spending_policy_cannot_borrow_allowance_capacity(self) -> None:
        self.terminal_critic()
        changed = self.policy.model_copy(update={"pricing_source": "different"})
        with self.assertRaises(ValueError):
            PreparedReviewCall(
                self.reviewer,
                self.request,
                changed,
                self.ledger,
                reserved_allowance=self.envelope.envelope.judge,
            )
        self.assertEqual(self.ledger.snapshot().entries, 2)

    async def test_malformed_judge_output_does_not_refund_transferred_cost(
        self,
    ) -> None:
        self.terminal_critic()
        prepared = self.prepare()
        self.fake.response = output("invalid JSON")
        self.issue(prepared)
        with self.assertRaises(ProviderError):
            await self.reviewer.judge(self.request)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 40)
        self.assertEqual(
            verify_judge_transfer(
                self.directory, prepared.authorization, self.ledger
            ).status,
            "response_received",
        )
