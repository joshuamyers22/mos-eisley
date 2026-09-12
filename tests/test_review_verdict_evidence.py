"""Retained final verdicts require complete judge and critic provenance."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import patch

import test_review_response_evidence as fixtures
from pydantic import JsonValue
from test_openai_spend import FakeTransport
from test_review_broker_admission import output

from mos_eisley.core.models import Finding, JudgeDecision, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelResponse
from mos_eisley.run.model_evidence import ModelCompletion
from mos_eisley.run.review_evidence import PreparedEvidenceJudgeTransfer
from mos_eisley.run.review_verdict import (
    reconstruct_review_result,
    retain_review_result,
    verify_retained_review_result,
)


class VerdictEvidenceTests(fixtures.ReviewEvidenceFixture):
    async def asyncSetUp(self) -> None:
        self.fake = FakeTransport(self.directory / "judge")

    async def judge(
        self,
        text: str | None = None,
        *,
        failure: bool = False,
        vote: Finding | None = None,
    ) -> None:
        vote = fixtures.finding() if vote is None else vote
        for index in range(3):
            await self.run_critic(index, fixtures.critique_text(vote))
        self.transfer = PreparedEvidenceJudgeTransfer(
            self.prepared, self.reviewer, self.review_policy
        )
        self.fake.response = output(
            text
            if text is not None
            else canonical_bytes(
                JudgeDecision(upheld=(vote.finding_id,), rationale="Fixture")
            ).decode()
        )
        if failure:
            self.fake.error = ProviderError("fixture failure")
        client = self.transfer.issue(
            approved_evidence_sha256=self.transfer.approval_sha256,
            transport=self.fake,
            container=self.container,
        )
        if failure:
            with self.assertRaises(ProviderError):
                await client.complete(self.transfer.model_request)
        else:
            await client.complete(self.transfer.model_request)

    def reconstruct(self):
        return reconstruct_review_result(
            self.prepared.envelope,
            self.reviewer,
            self.ledger,
            self.transfer.authorization,
        )

    def retain(self):
        return retain_review_result(
            self.prepared.envelope,
            self.reviewer,
            self.ledger,
            self.transfer.authorization,
        )

    def verify_result(self, expected: str):
        return verify_retained_review_result(
            self.prepared.envelope,
            self.reviewer,
            self.ledger,
            self.transfer.authorization,
            expected,
        )

    async def test_valid_result_is_private_pinned_and_recomputed_after_expiry(self):
        await self.judge()
        before = self.ledger.snapshot()
        result = self.reconstruct()
        self.assertFalse((self.directory / "review-result.json").exists())
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(result.result.verdict.findings, (fixtures.finding(),))
        self.assertEqual(self.retain(), result)
        path = self.directory / "review-result.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with patch("mos_eisley.run.review_broker.datetime") as clock:
            clock.now.return_value = self.prepared.envelope.expires_at + timedelta(
                days=1
            )
            self.assertEqual(
                self.verify_result(digest(canonical_bytes(result))), result
            )
        with self.assertRaises(FileExistsError):
            self.retain()
        self.assertEqual(self.ledger.snapshot(), before)
        self.assertEqual(len(self.fake.calls), 1)

    async def test_upheld_medium_finding_requires_revision(self):
        vote = fixtures.finding().model_copy(update={"impact": "medium"})
        await self.judge(vote=vote)
        verdict = self.reconstruct().result.verdict
        self.assertEqual(verdict.decision, "revise")
        self.assertEqual(verdict.required_changes, (vote.finding_id,))

    async def test_upheld_blocker_rejects(self):
        vote = fixtures.finding().model_copy(update={"impact": "blocker"})
        await self.judge(vote=vote)
        self.assertEqual(self.reconstruct().result.verdict.decision, "reject")

    async def test_preference_cannot_block_acceptance(self):
        vote = fixtures.finding().model_copy(
            update={"impact": "blocker", "category": "preference"}
        )
        await self.judge(vote=vote)
        verdict = self.reconstruct().result.verdict
        self.assertEqual(verdict.decision, "accept")
        self.assertEqual(verdict.required_changes, ())

    async def test_received_judge_requires_settled_accounting(self):
        import sqlite3
        from contextlib import closing

        await self.judge()
        with closing(sqlite3.connect(self.ledger.path)) as connection, connection:
            connection.execute(
                "UPDATE entries SET status='uncertain', charged=reserved "
                "WHERE entry_id=?",
                (self.client_entry(),),
            )
        with self.assertRaises(ValueError):
            self.reconstruct()

    def client_entry(self) -> str:
        from mos_eisley.run.review_broker import JudgeTransferAuthorization

        return JudgeTransferAuthorization.model_validate_json(
            (self.directory / "judge-transfer.json").read_bytes()
        ).call.ledger_entry_id

    async def test_unknown_finding_is_infrastructure_error(self):
        await self.judge(
            canonical_bytes(JudgeDecision(upheld=("a" * 64,), rationale="No")).decode()
        )
        result = self.reconstruct().result
        self.assertEqual(result.verdict.decision, "infrastructure_error")
        self.assertIsNone(result.judge_decision)
        self.assertEqual(result.verdict.findings, ())
        self.assertEqual(self.ledger.snapshot().charged_microusd, 80)

    async def test_duplicate_finding_is_infrastructure_error(self):
        identifier = fixtures.finding().finding_id
        await self.judge(
            canonical_bytes(
                JudgeDecision(upheld=(identifier, identifier), rationale="No")
            ).decode()
        )
        self.assertEqual(
            self.reconstruct().result.verdict.decision, "infrastructure_error"
        )

    async def test_invalid_json_is_retained_failure_without_refund(self):
        await self.judge(
            '{"schema_version":1,"upheld":[],"upheld":[],"rationale":"No"}'
        )
        result = self.retain()
        self.assertEqual(result.result.verdict.decision, "infrastructure_error")
        self.assertEqual(self.verify_result(digest(canonical_bytes(result))), result)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 80)

    async def test_provider_failure_is_explicit_and_keeps_uncertain_spend(self):
        await self.judge(failure=True)
        self.assertEqual(self.retain().result.verdict.decision, "infrastructure_error")
        self.assertEqual(self.ledger.snapshot().charged_microusd, 385)

    async def test_deeply_nested_json_is_retained_failure_without_refund(self):
        await self.judge("[" * 1500 + "]" * 1500)
        result = self.retain()
        self.assertEqual(result.result.verdict.decision, "infrastructure_error")
        self.assertEqual(self.verify_result(digest(canonical_bytes(result))), result)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 80)

    async def test_cancelled_judge_is_explicit_and_never_reissued(self):
        async def cancelled(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
            raise asyncio.CancelledError

        with (
            patch.object(self.fake, "create_response", side_effect=cancelled),
            self.assertRaises(asyncio.CancelledError),
        ):
            await self.judge()
        self.assertEqual(self.retain().result.verdict.decision, "infrastructure_error")
        self.assertEqual(self.ledger.snapshot().charged_microusd, 385)

    async def test_missing_or_tampered_judge_records_block_even_failure_results(self):
        await self.judge()
        for name in (
            "model-completion.json",
            "broker-response.json",
            "model-response.json",
            "model-request.json",
            "outcome.json",
        ):
            path = self.directory / "judge" / name
            original = path.read_bytes()
            with self.subTest(artifact=name):
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    self.reconstruct()
                path.write_bytes(b"{}")
                with self.assertRaises(ValueError):
                    self.reconstruct()
                path.write_bytes(original)

    async def test_rehashed_model_response_must_match_original_broker_reply(self):
        await self.judge()
        directory = self.directory / "judge"
        path = directory / "model-response.json"
        data = json.loads(path.read_bytes())
        data["turn"]["blocks"][0]["text"] = canonical_bytes(
            JudgeDecision(upheld=(), rationale="Forged")
        ).decode()
        raw = canonical_bytes(ModelResponse.model_validate_json(json.dumps(data)))
        path.write_bytes(raw)
        path = directory / "model-completion.json"
        completion = ModelCompletion.model_validate_json(path.read_bytes())
        path.write_bytes(
            canonical_bytes(
                completion.model_copy(update={"model_response_sha256": digest(raw)})
            )
        )
        with self.assertRaises(ValueError):
            self.reconstruct()

    async def test_cached_result_cannot_override_reconstructed_verdict(self):
        await self.judge()
        result = self.retain()
        with self.assertRaises(ValueError):
            self.verify_result("a" * 64)
        data = json.loads(canonical_bytes(result))
        data["result"]["verdict"]["decision"] = "reject"
        raw = canonical_bytes(type(result).model_validate_json(json.dumps(data)))
        (self.directory / "review-result.json").write_bytes(raw)
        with self.assertRaises(ValueError):
            self.verify_result(digest(raw))

    async def test_later_critic_tampering_invalidates_saved_verdict(self):
        await self.judge()
        result = self.retain()
        (self.child(0) / "model-response.json").write_bytes(b"{}")
        with self.assertRaises(ValueError):
            self.verify_result(digest(canonical_bytes(result)))

    async def test_result_storage_failure_preserves_cost_and_allows_only_local_retry(
        self,
    ):
        await self.judge()
        before = self.ledger.snapshot()
        with (
            patch(
                "mos_eisley.run.review_verdict.private_write",
                side_effect=OSError("disk"),
            ),
            self.assertRaises(OSError),
        ):
            self.retain()
        self.assertEqual(self.retain().result.verdict.decision, "accept")
        self.assertEqual(self.ledger.snapshot(), before)
        self.assertEqual(len(self.fake.calls), 1)
