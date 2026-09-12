"""Response provenance, failed-critic handling and fresh judge admission."""

from __future__ import annotations

import asyncio
import json
import sys
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
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelResponse
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.run.duplex import ExchangeHandler, bounded_exchange
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.model_evidence import ModelCompletion
from mos_eisley.run.review_broker import PreparedReviewCall, PreparedReviewEnvelope
from mos_eisley.run.review_evidence import (
    PreparedEvidenceJudgeTransfer,
    ReviewEvidence,
    verify_evidence_judge_transfer,
    verify_review_evidence,
)
from mos_eisley.run.spend_ledger import LedgerSettlement, SpendLedger


def finding(claim: str = "Check return", quote: str = "return 1") -> Finding:
    return Finding(
        location="diff",
        category="correctness",
        impact="low",
        claim=claim,
        evidence=Evidence(source="diff", quote=quote, explanation="Fixture"),
    )


def critique_text(*findings: Finding) -> str:
    return canonical_bytes(Critique(findings=findings)).decode()


class ReviewEvidenceTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "review"
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 2000)
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
        self.request = CriticRequest(brief=self.brief, persona="correctness")
        self.calls = tuple(
            PreparedReviewCall(
                self.reviewer,
                self.request,
                self.policy,
                self.ledger,
                critic=CriticSpec(
                    id=name,
                    provider="openai",
                    model="gpt-6-astra",
                    persona="correctness",
                ),
            )
            for name in ("one", "two", "three")
        )
        self.prepared = PreparedReviewEnvelope(
            self.calls,
            self.policy,
            self.ledger,
            max_total_microusd=1300,
            directory=self.directory,
        )
        self.reserved = self.prepared.reserve(
            approved_envelope_sha256=self.prepared.approval_sha256
        )
        self.review_policy = ReviewPolicy(min_critics=2, min_providers=1)
        self.container = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)
        self.cleanup_error = False
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
        result = await bounded_exchange(
            [sys.executable, *arguments], payload, handler, timeout
        )
        if self.cleanup_error:
            raise ValueError("fixture cleanup failure")
        return result

    def child(self, index: int) -> Path:
        return self.directory / self.calls[index].authorization.ledger_entry_id

    async def run_critic(
        self, index: int, text: str = "", *, fail: bool = False
    ) -> None:
        fake = FakeTransport(self.child(index))
        fake.response = output(text if text else critique_text())
        if fail:
            fake.error = ProviderError("fixture provider failure")
        client = self.reserved.issue_critic(
            index, transport=fake, container=self.container
        )
        if fail:
            with self.assertRaises(ProviderError):
                await client.complete(self.calls[index].model_request)
        else:
            await client.complete(self.calls[index].model_request)

    async def finish(self) -> None:
        for index in range(3):
            await self.run_critic(index, critique_text(finding()))

    def verify(self, policy: ReviewPolicy | None = None) -> ReviewEvidence:
        return verify_review_evidence(
            self.prepared.envelope,
            self.reviewer,
            self.ledger,
            self.review_policy if policy is None else policy,
        )

    async def test_retention_is_private_and_binds_raw_canonical_and_request_hashes(
        self,
    ) -> None:
        await self.finish()
        for index in range(3):
            directory = self.child(index)
            completion = ModelCompletion.model_validate_json(
                (directory / "model-completion.json").read_bytes()
            )
            self.assertEqual(completion.status, "received")
            self.assertEqual(
                completion.request_sha256,
                self.calls[index].authorization.model_request_sha256,
            )
            self.assertEqual(
                completion.broker_response_sha256,
                digest((directory / "broker-response.json").read_bytes()),
            )
            self.assertEqual(
                completion.model_response_sha256,
                digest((directory / "model-response.json").read_bytes()),
            )
            for name in (
                "broker-response.json",
                "model-response.json",
                "model-completion.json",
            ):
                self.assertEqual((directory / name).stat().st_mode & 0o777, 0o600)
        before = self.ledger.snapshot()
        evidence = self.verify()
        self.assertEqual(self.ledger.snapshot(), before)
        self.assertEqual(len(evidence.judge_request.findings), 1)
        self.assertFalse((self.directory / "judge-transfer.json").exists())

    async def test_dedupe_keeps_conflicts_and_hash_order_without_critic_identity(
        self,
    ) -> None:
        first, second = finding(), finding("Conflicting finding")
        await self.run_critic(0, critique_text(second, first))
        await self.run_critic(1, critique_text(first))
        await self.run_critic(2, critique_text(second))
        evidence = self.verify()
        self.assertEqual(
            tuple(item.finding_id for item in evidence.judge_request.findings),
            tuple(sorted((first.finding_id, second.finding_id))),
        )
        self.assertEqual(
            len(evidence.critics[0].result.critique.findings)
            if evidence.critics[0].result.critique
            else 0,
            2,
        )
        transfer = PreparedEvidenceJudgeTransfer(
            self.prepared, self.reviewer, self.review_policy
        )
        self.assertNotIn("persona", canonical_bytes(transfer.model_request).decode())

    async def test_full_evidence_judge_flow_and_read_only_historical_verification(
        self,
    ) -> None:
        await self.finish()
        prepared = PreparedEvidenceJudgeTransfer(
            self.prepared, self.reviewer, self.review_policy
        )
        fake = FakeTransport(self.directory / "judge")
        fake.response = output(
            canonical_bytes(
                JudgeDecision(upheld=(finding().finding_id,), rationale="Fixture")
            ).decode()
        )
        before = self.ledger.snapshot()
        with self.assertRaises(ValueError):
            prepared.issue(
                approved_evidence_sha256=self.prepared.approval_sha256,
                transport=fake,
                container=self.container,
            )
        self.assertEqual(self.ledger.snapshot(), before)
        self.client.target = prepared.issue(
            approved_evidence_sha256=prepared.approval_sha256,
            transport=fake,
            container=self.container,
        )
        decision = await self.reviewer.judge(prepared.evidence.judge_request)
        self.assertEqual(decision.upheld, (finding().finding_id,))
        self.assertEqual(self.ledger.snapshot().charged_microusd, 80)
        with patch("mos_eisley.run.review_broker.datetime") as clock:
            clock.now.return_value = self.prepared.envelope.expires_at + timedelta(
                days=1
            )
            outcome = verify_evidence_judge_transfer(
                self.prepared.envelope,
                self.reviewer,
                self.ledger,
                prepared.authorization,
            )
        self.assertEqual(outcome.status, "response_received")
        self.assertEqual(
            (self.directory / "review-evidence.json").read_bytes(),
            canonical_bytes(prepared.evidence),
        )
        with self.assertRaises(ValueError):
            prepared.issue(
                approved_evidence_sha256=prepared.approval_sha256,
                transport=fake,
                container=self.container,
            )
        self.assertEqual(len(fake.calls), 1)
        # Historical verification binds every approval, finding and judge artifact.
        for name in (
            "review-evidence.json",
            "review-evidence-approval.json",
            "judge-transfer.json",
            "judge/review-input.json",
        ):
            path = self.directory / name
            original = path.read_bytes()
            with self.subTest(artifact=name):
                path.write_bytes(b"{}")
                try:
                    with self.assertRaises(ValueError):
                        verify_evidence_judge_transfer(
                            self.prepared.envelope,
                            self.reviewer,
                            self.ledger,
                            prepared.authorization,
                        )
                finally:
                    path.write_bytes(original)
        self.assertEqual(len(fake.calls), 1)

    async def test_missing_receipt_cannot_be_treated_as_a_failed_vote(self) -> None:
        await self.finish()
        (self.child(0) / "model-completion.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.verify()
        self.assertEqual(self.ledger.snapshot().charged_microusd, 385)

    async def test_tampered_or_partial_artifacts_block_verification(self) -> None:
        await self.finish()
        for name in (
            "broker-response.json",
            "model-response.json",
            "model-completion.json",
            "critic.json",
            "model-request.json",
            "outcome.json",
        ):
            path = self.child(0) / name
            original = path.read_bytes()
            path.write_bytes(b"{}")
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.verify()
            path.write_bytes(original)

    async def test_rehashed_canonical_response_cannot_diverge_from_raw_reply(
        self,
    ) -> None:
        await self.finish()
        directory = self.child(0)
        data = json.loads((directory / "model-response.json").read_bytes())
        data["turn"]["blocks"][0]["text"] = critique_text(finding("forged"))
        response = ModelResponse.model_validate_json(json.dumps(data))
        encoded = canonical_bytes(response)
        (directory / "model-response.json").write_bytes(encoded)
        completion = ModelCompletion.model_validate_json(
            (directory / "model-completion.json").read_bytes()
        )
        (directory / "model-completion.json").write_bytes(
            canonical_bytes(
                completion.model_copy(update={"model_response_sha256": digest(encoded)})
            )
        )
        with self.assertRaises(ValueError):
            self.verify()

    async def test_rehashed_raw_reply_still_requires_original_broker_outcome(
        self,
    ) -> None:
        await self.finish()
        directory = self.child(0)
        raw = (
            (directory / "broker-response.json")
            .read_bytes()
            .replace(b"Check return", b"Changed claim")
        )
        (directory / "broker-response.json").write_bytes(raw)
        completion = ModelCompletion.model_validate_json(
            (directory / "model-completion.json").read_bytes()
        )
        (directory / "model-completion.json").write_bytes(
            canonical_bytes(
                completion.model_copy(update={"broker_response_sha256": digest(raw)})
            )
        )
        with self.assertRaises(ValueError):
            self.verify()

    async def test_judge_issue_rechecks_evidence_even_when_findings_do_not_change(
        self,
    ) -> None:
        await self.finish()
        prepared = PreparedEvidenceJudgeTransfer(
            self.prepared, self.reviewer, self.review_policy
        )
        path = self.child(0) / "outcome.json"
        data = json.loads(path.read_bytes())
        data["latency_ms"] += 1
        path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")))
        self.assertEqual(self.verify().judge_request, prepared.evidence.judge_request)
        with self.assertRaises(ValueError):
            prepared.issue(
                approved_evidence_sha256=prepared.approval_sha256,
                transport=FakeTransport(self.directory / "judge"),
                container=self.container,
            )
        self.assertEqual(self.ledger.snapshot().entries, 4)
        self.assertFalse((self.directory / "judge-transfer.json").exists())

    async def test_invalid_json_does_not_count_but_other_critics_can_meet_quorum(
        self,
    ) -> None:
        await self.run_critic(0, "not JSON")
        await self.run_critic(1, critique_text(finding()))
        await self.run_critic(2)
        evidence = self.verify()
        self.assertEqual(evidence.critics[0].result.error, "provider_error")
        self.assertEqual(evidence.judge_request.findings, (finding(),))

    async def test_invalid_citation_cannot_reach_judge(self) -> None:
        await self.run_critic(0, critique_text(finding("Invented", "not present")))
        await self.run_critic(1, critique_text(finding()))
        await self.run_critic(2)
        evidence = self.verify()
        self.assertEqual(evidence.critics[0].result.error, "invalid_evidence")
        self.assertEqual(evidence.judge_request.findings, (finding(),))

    async def test_provider_failure_is_retained_and_excluded_from_quorum(self) -> None:
        await self.run_critic(0, fail=True)
        await self.run_critic(1)
        await self.run_critic(2)
        self.assertEqual(self.verify().critics[0].result.status, "error")
        completion = ModelCompletion.model_validate_json(
            (self.child(0) / "model-completion.json").read_bytes()
        )
        self.assertEqual(completion.status, "failed")
        self.assertFalse((self.child(0) / "broker-response.json").exists())

    async def test_cancelled_exchange_is_retained_without_inventing_a_response(
        self,
    ) -> None:
        fake = FakeTransport(self.child(0))
        started = asyncio.Event()

        async def count(_: object) -> int:
            started.set()
            await asyncio.sleep(10)
            return 10

        with patch.object(fake, "count_input_tokens", side_effect=count):
            client = self.reserved.issue_critic(
                0, transport=fake, container=self.container
            )
            task = asyncio.create_task(client.complete(self.calls[0].model_request))
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        await self.run_critic(1)
        await self.run_critic(2)
        self.assertEqual(self.verify().critics[0].result.status, "error")
        completion = ModelCompletion.model_validate_json(
            (self.child(0) / "model-completion.json").read_bytes()
        )
        self.assertEqual(completion.status, "cancelled")

    async def test_cleanup_failure_cannot_be_counted_as_a_usable_reply(self) -> None:
        self.cleanup_error = True
        with self.assertRaises(ProviderError):
            await self.run_critic(0)
        self.cleanup_error = False
        await self.run_critic(1)
        await self.run_critic(2)
        self.assertEqual(self.verify().critics[0].result.status, "error")
        self.assertFalse((self.child(0) / "broker-response.json").exists())

    async def test_usable_response_requires_settled_matching_accounting(self) -> None:
        await self.finish()
        import sqlite3
        from contextlib import closing

        with closing(sqlite3.connect(self.ledger.path)) as connection, connection:
            connection.execute(
                "UPDATE entries SET status='uncertain', charged=reserved "
                "WHERE entry_id=?",
                (self.calls[0].ledger_entry.entry_id,),
            )
        with self.assertRaises(ValueError):
            self.verify()

    async def test_quorum_and_default_provider_diversity_are_not_weakened(self) -> None:
        await self.run_critic(0, "invalid")
        await self.run_critic(1, "invalid")
        await self.run_critic(2)
        with self.assertRaises(ValueError):
            self.verify()
        with self.assertRaises(ValueError):
            PreparedEvidenceJudgeTransfer(self.prepared, self.reviewer)

    async def test_judge_byte_budget_is_checked_after_deduplication(self) -> None:
        for index in range(3):
            await self.run_critic(index, critique_text(finding(str(index) + "x" * 800)))
        with self.assertRaisesRegex(ValueError, "judge request"):
            self.verify(
                self.review_policy.model_copy(update={"max_request_bytes": 1024})
            )

    def test_terminal_accounting_alone_does_not_provide_critic_evidence(self) -> None:
        for call in self.calls:
            self.ledger.settle(
                LedgerSettlement(
                    entry_id=call.ledger_entry.entry_id,
                    reservation_sha256=call.ledger_entry.reservation_sha256,
                    status="settled",
                    charged_microusd=20,
                )
            )
        with self.assertRaises(FileNotFoundError):
            self.verify()

    async def test_retention_write_failure_never_releases_incurred_cost(self) -> None:
        fake = FakeTransport(self.child(0))
        fake.response = output(critique_text())
        client = self.reserved.issue_critic(0, transport=fake, container=self.container)
        (self.child(0) / "model-completion.json").write_bytes(b"occupied")
        with self.assertRaises(ProviderError):
            await client.complete(self.calls[0].model_request)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 995)
        with self.assertRaises(ProviderError):
            await client.complete(self.calls[0].model_request)
        self.assertEqual(len(fake.calls), 1)

    async def test_changed_decoder_projection_is_rejected_without_new_requests(
        self,
    ) -> None:
        await self.finish()
        changed = ModelReviewer(
            BoundClient(),
            openai_registry(),
            judge_provider="openai",
            judge_model="gpt-6-astra",
            budget=BudgetPolicy(max_output_tokens=99),
        )
        with self.assertRaises(ValueError):
            verify_review_evidence(
                self.prepared.envelope, changed, self.ledger, self.review_policy
            )
