"""Critics consume one atomic allowance while the future judge remains funded."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
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
    canonical_bytes,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.run.duplex import ExchangeHandler, bounded_exchange
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_broker import (
    PreparedReviewCall,
    PreparedReviewEnvelope,
    ReservedReviewEnvelope,
    ReviewSpendingEnvelope,
    verify_review_broker_audit,
)
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger


class ReviewEnvelopeTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "review"
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 1000)
        self.policy = cache_write_policy().model_copy(
            update={"max_input_tokens": 100, "max_output_tokens": 100}
        )
        self.reviewer = ModelReviewer(
            BoundClient(),
            openai_registry(),
            judge_provider="openai",
            judge_model="gpt-6-astra",
            budget=BudgetPolicy(max_output_tokens=100),
        )
        self.request = CriticRequest(
            brief=Brief(spec="Return one", diff="return 1"), persona="correctness"
        )
        self.critics = tuple(self.call(name) for name in ("one", "two"))
        self.prepared = self.prepare()
        self.container = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)
        patcher = patch.object(
            self.container, "exchange_async", side_effect=self.exchange
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.workers = 0

    def call(
        self, name: str, request: CriticRequest | None = None
    ) -> PreparedReviewCall:
        return PreparedReviewCall(
            self.reviewer,
            self.request if request is None else request,
            self.policy,
            self.ledger,
            critic=CriticSpec(
                id=name, provider="openai", model="gpt-6-astra", persona="correctness"
            ),
        )

    def prepare(
        self, critics: tuple[PreparedReviewCall, ...] | None = None, cap: int = 1000
    ) -> PreparedReviewEnvelope:
        return PreparedReviewEnvelope(
            self.critics if critics is None else critics,
            self.policy,
            self.ledger,
            max_total_microusd=cap,
            directory=self.directory,
        )

    def reserve(self) -> ReservedReviewEnvelope:
        return self.prepared.reserve(
            approved_envelope_sha256=self.prepared.approval_sha256
        )

    def fake(self, index: int) -> FakeTransport:
        fake = FakeTransport(
            self.directory / self.critics[index].authorization.ledger_entry_id
        )
        fake.response = output(canonical_bytes(Critique()).decode())
        return fake

    async def exchange(
        self,
        arguments: tuple[str, ...],
        payload: bytes,
        handler: ExchangeHandler,
        timeout: float,
    ) -> bytes:
        self.workers += 1
        return await bounded_exchange(
            [sys.executable, *arguments], payload, handler, timeout
        )

    def test_preview_binds_all_calls_cap_directory_and_deferred_judge_without_effects(
        self,
    ) -> None:
        envelope = self.prepared.envelope
        self.assertEqual(envelope.total_reserved_microusd, 975)
        self.assertEqual(envelope.max_total_microusd, 1000)
        self.assertFalse(envelope.judge.transfer_authorized)
        self.assertEqual(envelope.artifact_directory, str(self.directory.resolve()))
        self.assertEqual(
            envelope.critics, tuple(call.authorization for call in self.critics)
        )
        self.assertEqual(self.ledger.snapshot().entries, 0)
        self.assertFalse(self.directory.exists())
        self.assertNotEqual(
            self.prepared.approval_sha256, self.critics[0].approval_sha256
        )

    def test_explicit_aggregate_confirmation_is_required(self) -> None:
        for approval in ("", "0" * 64, self.critics[0].approval_sha256):
            with self.subTest(approval=approval), self.assertRaises(ValueError):
                self.prepared.reserve(approved_envelope_sha256=approval)
        self.assertEqual(self.ledger.snapshot().entries, 0)
        self.assertFalse(self.directory.exists())

    async def test_all_holds_precede_dispatch_and_only_known_savings_release(
        self,
    ) -> None:
        reserved = self.reserve()
        self.assertEqual(self.ledger.snapshot().charged_microusd, 975)
        self.assertEqual(self.ledger.snapshot().entries, 3)
        for index in (0, 1):
            fake = self.fake(index)
            client = reserved.issue_critic(
                index, transport=fake, container=self.container
            )
            self.assertEqual(fake.counts, [])
            await client.complete(self.critics[index].model_request)
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(
                self.ledger.snapshot().charged_microusd, 975 - 305 * (index + 1)
            )
            directory = (
                self.directory / self.critics[index].authorization.ledger_entry_id
            )
            self.assertEqual(
                verify_review_broker_audit(
                    directory, self.critics[index].authorization
                ).status,
                "response_received",
            )
        judge = self.ledger.entry_status(self.prepared.envelope.judge.ledger_entry_id)
        assert judge is not None
        self.assertEqual(judge.status, "held")
        self.assertEqual(judge.charged_microusd, 325)
        self.assertEqual(self.ledger.snapshot().unresolved_entries, 1)
        self.assertEqual(self.workers, 2)

    def test_aggregate_limit_and_current_headroom_reject_without_partial_admission(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.prepare(cap=974)
        self.ledger.reserve(
            LedgerEntry(
                entry_id="a" * 64, reservation_sha256="b" * 64, reserved_microusd=100
            )
        )
        with self.assertRaises(ValueError):
            self.reserve()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.ledger.snapshot().entries, 1)
        self.assertFalse(self.directory.exists())

    def test_late_duplicate_rolls_back_other_critic_and_judge_holds(self) -> None:
        second = self.critics[1].ledger_entry.model_copy(
            update={"reserved_microusd": 0}
        )
        self.ledger.reserve(second)
        with self.assertRaises(sqlite3.IntegrityError):
            self.reserve()
        self.assertEqual(self.ledger.snapshot().entries, 1)
        self.assertIsNone(
            self.ledger.entry_status(self.critics[0].authorization.ledger_entry_id)
        )
        self.assertIsNone(
            self.ledger.entry_status(self.prepared.envelope.judge.ledger_entry_id)
        )

    def test_scope_duplicates_and_different_briefs_are_rejected(self) -> None:
        other = self.call(
            "three",
            self.request.model_copy(
                update={"brief": Brief(spec="Other", diff="return 2")}
            ),
        )
        for critics in (
            (),
            (self.critics[0],) * 9,
            (self.critics[0], self.critics[0]),
            (self.critics[0], self.call("one")),
            (self.critics[0], other),
        ):
            with self.subTest(count=len(critics)), self.assertRaises(ValueError):
                self.prepare(critics=critics)
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_different_ledger_path_is_rejected_even_with_copied_identity(self) -> None:
        import shutil

        copy = self.root / "copy.sqlite"
        shutil.copyfile(self.ledger.path, copy)
        with self.assertRaises(ValueError):
            PreparedReviewEnvelope(
                self.critics,
                self.policy,
                SpendLedger(copy),
                max_total_microusd=1000,
                directory=self.directory,
            )
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_failed_artifact_creation_keeps_every_hold_and_blocks_retry(self) -> None:
        self.directory.mkdir()
        with self.assertRaises(FileExistsError):
            self.reserve()
        self.assertEqual(self.ledger.snapshot().charged_microusd, 975)
        with self.assertRaises((ValueError, sqlite3.Error)):
            self.reserve()
        self.assertEqual(self.ledger.snapshot().entries, 3)

    def test_critic_grants_are_exclusive_even_with_reconstructed_host_handle(
        self,
    ) -> None:
        reserved = self.reserve()
        fake = self.fake(0)
        reserved.issue_critic(0, transport=fake, container=self.container)
        with self.assertRaises(FileExistsError):
            ReservedReviewEnvelope(self.prepared).issue_critic(
                0, transport=fake, container=self.container
            )
        self.assertEqual(fake.counts, [])
        self.assertEqual(self.ledger.snapshot().entries, 3)

    def test_approval_expiry_and_changed_envelope_block_issuance(self) -> None:
        reserved = self.reserve()
        path = self.directory / "envelope.json"
        original = path.read_bytes()
        path.write_bytes(b"{}")
        with self.assertRaises(ValueError):
            reserved.issue_critic(0, transport=self.fake(0), container=self.container)
        path.write_bytes(original)
        future = self.prepared.envelope.expires_at + timedelta(seconds=1)
        with patch("mos_eisley.run.review_broker.datetime") as clock:
            clock.now.return_value = future
            with self.assertRaises(ValueError):
                reserved.issue_critic(
                    0, transport=self.fake(0), container=self.container
                )
        self.assertEqual(self.workers, 0)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 975)

    def test_expired_judge_policy_denies_entire_reservation(self) -> None:
        with patch("mos_eisley.providers.openai_spend.datetime") as clock:
            clock.now.return_value = self.policy.valid_until + timedelta(seconds=1)
            with self.assertRaises(ValueError):
                self.reserve()
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_changed_judge_hold_prevents_any_critic_issuance(self) -> None:
        reserved = self.reserve()
        judge = self.prepared.envelope.judge.ledger_entry
        self.ledger.settle(
            LedgerSettlement(
                entry_id=judge.entry_id,
                reservation_sha256=judge.reservation_sha256,
                status="settled",
                charged_microusd=0,
            )
        )
        with self.assertRaises(ValueError):
            reserved.issue_critic(0, transport=self.fake(0), container=self.container)
        self.assertEqual(self.workers, 0)

    async def test_pricing_violation_blocks_an_already_issued_other_critic(
        self,
    ) -> None:
        reserved = self.reserve()
        fake0, fake1 = self.fake(0), self.fake(1)
        client0 = reserved.issue_critic(0, transport=fake0, container=self.container)
        client1 = reserved.issue_critic(1, transport=fake1, container=self.container)
        fake0.tokens = 101
        with self.assertRaises(ProviderError):
            await client0.complete(self.critics[0].model_request)
        self.assertTrue(self.ledger.snapshot().blocked)
        with self.assertRaises(ProviderError):
            await client1.complete(self.critics[1].model_request)
        self.assertEqual(fake1.counts, [])
        self.assertEqual(fake1.calls, [])
        self.assertEqual(self.ledger.snapshot().charged_microusd, 975)

    async def test_cancelled_critic_retains_its_allowance_and_judge_funds(self) -> None:
        reserved = self.reserve()
        fake = self.fake(0)
        started = asyncio.Event()

        async def count(_: object) -> int:
            started.set()
            await asyncio.sleep(10)
            return 10

        with patch.object(fake, "count_input_tokens", side_effect=count):
            task = asyncio.create_task(
                reserved.issue_critic(
                    0, transport=fake, container=self.container
                ).complete(self.critics[0].model_request)
            )
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.ledger.snapshot().charged_microusd, 975)
        status = self.ledger.entry_status(self.critics[0].authorization.ledger_entry_id)
        assert status is not None
        self.assertEqual(status.status, "uncertain")

    def test_nonselected_indices_do_not_issue_grants(self) -> None:
        reserved = self.reserve()
        for index in (-1, 2, True):
            with self.subTest(index=index), self.assertRaises(ValueError):
                reserved.issue_critic(
                    index, transport=self.fake(0), container=self.container
                )
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_envelope_contract_rejects_tampered_total_expiry_and_judge_transfer(
        self,
    ) -> None:
        envelope = self.prepared.envelope
        for update in (
            {"total_reserved_microusd": 974},
            {"max_total_microusd": 974},
            {"expires_at": datetime.now(UTC) + timedelta(days=1)},
            {"judge": envelope.judge.model_copy(update={"transfer_authorized": True})},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                ReviewSpendingEnvelope.model_validate_json(
                    canonical_bytes(envelope.model_copy(update=update))
                )
