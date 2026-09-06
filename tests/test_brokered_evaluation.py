"""Only fully validated broker responses become conformance artifacts."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from mos_eisley.core.models import Critique, canonical_bytes
from mos_eisley.evaluation.execution import make_execution_batch
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.brokered_evaluation import compile_brokered_evaluation
from mos_eisley.run.evaluation_broker import (
    authorize_assignment,
    make_assignment_broker,
)
from mos_eisley.run.spend_ledger import SpendLedger
from tests.test_evaluation_execution import inputs, make_plan
from tests.test_openai_provider import response_payload
from tests.test_openai_spend import FakeTransport, policy, request


class BrokeredEvaluationTests(IsolatedAsyncioTestCase):
    def _context(self, root: Path, text: str, *, status: str = "completed"):
        data, grid, gate = inputs()
        plan = make_plan(data, grid, 1, 0, gate)
        batch, _ = make_execution_batch(plan, data, "calibration", b"a" * 32)
        evaluation_request = batch.requests[0]
        payload = request()
        payload["model"] = evaluation_request.route.model
        payload["reasoning"] = {"effort": evaluation_request.route.effort}
        fake = FakeTransport(root)
        fake.tokens = 100
        fake.response = response_payload(
            [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            status=status,
            incomplete_reason=("max_output_tokens" if status == "incomplete" else None),
        )
        fake.response["model"] = evaluation_request.route.model
        fake.response["service_tier"] = "default"
        ledger = SpendLedger.create(root / "ledger.sqlite", 500)
        transport = BudgetedOpenAITransport(
            fake,
            policy().model_copy(update={"model": evaluation_request.route.model}),
            root,
            ledger,
        )
        expected = authorize_assignment(
            batch, evaluation_request.sample_id, payload, transport
        )
        broker = make_assignment_broker(
            batch,
            evaluation_request.sample_id,
            payload,
            transport,
            root / "audit",
        )
        return broker, expected, ledger

    async def test_complete_text_becomes_non_scoreable_bound_artifact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            critique = Critique(findings=())
            broker, expected, ledger = self._context(root, critique.model_dump_json())
            reply = BrokerReply(
                response=await broker.redeem(canonical_bytes(broker.claim()))
            )
            artifact = compile_brokered_evaluation(
                reply, expected, root / "audit", ledger
            )
            self.assertEqual(artifact.critique, critique)
            self.assertEqual(artifact.authorization, expected)
            self.assertEqual(artifact.usage.unit, "tokens")
            self.assertEqual(artifact.cost_microusd, 140)
            self.assertFalse(artifact.promotion_eligible)
            self.assertEqual(len(artifact.artifact_sha256), 64)

    async def test_changed_reply_and_wrong_ledger_fail_before_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            broker, expected, ledger = self._context(
                root, Critique(findings=()).model_dump_json()
            )
            reply = BrokerReply(
                response=await broker.redeem(canonical_bytes(broker.claim()))
            )
            changed = reply.model_copy(update={"response": {"changed": True}})
            with self.assertRaises(ValueError):
                compile_brokered_evaluation(changed, expected, root / "audit", ledger)
            other_root = root / "other"
            other_root.mkdir()
            other = SpendLedger.create(other_root / "ledger.sqlite", 500)
            with self.assertRaises(ValueError):
                compile_brokered_evaluation(reply, expected, root / "audit", other)

    async def test_invalid_critique_or_incomplete_response_is_not_evidence(
        self,
    ) -> None:
        for index, (text, status) in enumerate(
            (("not json", "completed"), (Critique().model_dump_json(), "incomplete"))
        ):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                broker, expected, ledger = self._context(root, text, status=status)
                reply = BrokerReply(
                    response=await broker.redeem(canonical_bytes(broker.claim()))
                )
                with (
                    self.subTest(index=index),
                    self.assertRaisesRegex(
                        ValueError, "brokered critique validation failed"
                    ),
                ):
                    compile_brokered_evaluation(reply, expected, root / "audit", ledger)

    def test_unredeemed_grant_cannot_mint_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, expected, ledger = self._context(
                root, Critique(findings=()).model_dump_json()
            )
            with self.assertRaisesRegex(ValueError, "provenance is incomplete"):
                compile_brokered_evaluation(
                    BrokerReply(response={}), expected, root / "audit", ledger
                )
