"""Assignment binding prevents cross-sample and cross-route provider calls."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport
from mos_eisley.run.broker_audit import verify_broker_audit
from mos_eisley.run.evaluation_broker import (
    authorize_assignment,
    make_assignment_broker,
)
from mos_eisley.run.spend_ledger import SpendLedger
from tests.test_evaluation_execution import inputs, make_plan
from tests.test_openai_spend import FakeTransport, policy, request


class AssignmentBrokerTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        data, grid, gate = inputs()
        self.plan = make_plan(data, grid, 1, 0, gate)
        self.batch = self._batch()
        self.request = self.batch.requests[0]

    def _batch(self):
        from mos_eisley.evaluation.execution import make_execution_batch

        batch, _ = make_execution_batch(
            self.plan, inputs()[0], "calibration", b"a" * 32
        )
        return batch

    def _transport(self, root: Path) -> tuple[FakeTransport, BudgetedOpenAITransport]:
        fake = FakeTransport(root)
        p = policy().model_copy(update={"model": self.request.route.model})
        fake.response["model"] = self.request.route.model
        ledger = SpendLedger.create(root / "ledger.sqlite", 500)
        return fake, BudgetedOpenAITransport(fake, p, root, ledger)

    async def test_valid_assignment_audits_and_replay_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fake, transport = self._transport(root)
            payload = request()
            payload["model"] = self.request.route.model
            payload["reasoning"] = {"effort": self.request.route.effort}
            broker = make_assignment_broker(
                self._batch(),
                self.request.sample_id,
                payload,
                transport,
                root / "audit",
            )
            await broker.redeem(canonical_bytes(broker.claim()))
            expected = authorize_assignment(
                self.batch, self.request.sample_id, payload, transport
            )
            outcome = verify_broker_audit(root / "audit", expected)
            self.assertEqual(outcome.status, "response_received")
            self.assertEqual(len(fake.calls), 1)
            with self.assertRaises(ProviderError):
                await broker.redeem(canonical_bytes(broker.claim()))

    def test_cross_assignment_and_route_mutation_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, transport = self._transport(root)
            batch = self._batch()
            payload = request()
            payload["model"] = self.request.route.model
            payload["reasoning"] = {"effort": self.request.route.effort}
            other = batch.requests[1]
            cross = authorize_assignment(batch, other.sample_id, payload, transport)
            self.assertNotEqual(cross.sample_id, self.request.sample_id)
            payload["model"] = "different-model"
            with self.assertRaises(ValueError):
                authorize_assignment(batch, self.request.sample_id, payload, transport)

    def test_audit_rejects_tampering_or_partial_write(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, transport = self._transport(root)
            payload = request()
            payload["model"] = self.request.route.model
            payload["reasoning"] = {"effort": self.request.route.effort}
            broker = make_assignment_broker(
                self._batch(),
                self.request.sample_id,
                payload,
                transport,
                root / "audit",
            )
            (root / "audit" / "authorization.json").write_bytes(b"{}")
            with self.assertRaises(ValueError):
                verify_broker_audit(root / "audit", broker._audit.authorization)  # type: ignore[union-attr]
