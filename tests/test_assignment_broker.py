"""Assignment binding prevents cross-sample and cross-route provider calls."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport
from mos_eisley.run.broker_audit import (
    BrokerAudit,
    BrokerOutcome,
    inspect_broker_recovery,
    verify_broker_audit,
)
from mos_eisley.run.evaluation_broker import (
    authorize_assignment,
    make_assignment_broker,
)
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write
from tests.test_evaluation_execution import inputs, make_plan
from tests.test_openai_spend import FakeTransport, policy, request


class AssignmentBrokerTests(IsolatedAsyncioTestCase):
    def test_legacy_outcome_remains_readable_but_has_no_latency(self) -> None:
        outcome = BrokerOutcome.model_validate(
            {
                "schema_version": 1,
                "admission_sha256": "a" * 64,
                "status": "response_received",
                "response_sha256": "b" * 64,
            }
        )
        self.assertIsNone(outcome.latency_ms)

    def test_legacy_outcome_is_recoverable_but_cannot_supply_latency(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, transport = self._transport(root)
            assert transport.ledger is not None
            payload = request()
            payload["model"] = self.request.route.model
            payload["reasoning"] = {"effort": self.request.route.effort}
            binding = authorize_assignment(
                self.batch, self.request.sample_id, payload, transport
            )
            audit = BrokerAudit(root / "audit", binding)
            audit.admit()
            admission = (root / "audit" / "admission.json").read_bytes()
            legacy = BrokerOutcome(
                schema_version=1,
                admission_sha256=digest(admission),
                status="response_received",
                response_sha256="b" * 64,
            )
            private_write(root / "audit" / "outcome.json", canonical_bytes(legacy))
            state = inspect_broker_recovery(root / "audit", binding, transport.ledger)
            self.assertEqual(state.phase, "finished")
            self.assertIsNone(state.latency_ms)

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

    def test_recovery_classifies_prepared_admitted_and_held(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, transport = self._transport(root)
            assert transport.ledger is not None
            payload = request()
            payload["model"] = self.request.route.model
            payload["reasoning"] = {"effort": self.request.route.effort}
            binding = authorize_assignment(
                self.batch, self.request.sample_id, payload, transport
            )
            audit = BrokerAudit(root / "audit", binding)
            state = inspect_broker_recovery(root / "audit", binding, transport.ledger)
            self.assertEqual((state.phase, state.ledger_status), ("prepared", "absent"))
            self.assertFalse(state.retry_permitted)

            audit.admit()
            state = inspect_broker_recovery(root / "audit", binding, transport.ledger)
            self.assertEqual((state.phase, state.ledger_status), ("admitted", "absent"))
            transport.ledger.reserve(
                LedgerEntry(
                    entry_id=binding.ledger_entry_id,
                    reservation_sha256="b" * 64,
                    reserved_microusd=25,
                )
            )
            state = inspect_broker_recovery(root / "audit", binding, transport.ledger)
            self.assertEqual((state.phase, state.ledger_status), ("admitted", "held"))

    async def test_recovery_verifies_finished_response_and_identity(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, transport = self._transport(root)
            assert transport.ledger is not None
            payload = request()
            payload["model"] = self.request.route.model
            payload["reasoning"] = {"effort": self.request.route.effort}
            binding = authorize_assignment(
                self.batch, self.request.sample_id, payload, transport
            )
            broker = make_assignment_broker(
                self.batch,
                self.request.sample_id,
                payload,
                transport,
                root / "audit",
            )
            await broker.redeem(canonical_bytes(broker.claim()))
            state = inspect_broker_recovery(root / "audit", binding, transport.ledger)
            self.assertEqual(
                (state.phase, state.ledger_status), ("finished", "settled")
            )
            self.assertEqual(state.outcome_status, "response_received")
            self.assertIsNotNone(state.response_sha256)

            other_root = root / "other"
            other_root.mkdir()
            other = SpendLedger.create(other_root / "ledger.sqlite", 500)
            with self.assertRaises(ValueError):
                inspect_broker_recovery(root / "audit", binding, other)

    def test_recovery_rejects_outcome_without_admission(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, transport = self._transport(root)
            assert transport.ledger is not None
            payload = request()
            payload["model"] = self.request.route.model
            payload["reasoning"] = {"effort": self.request.route.effort}
            binding = authorize_assignment(
                self.batch, self.request.sample_id, payload, transport
            )
            audit = BrokerAudit(root / "audit", binding)
            audit.finish("failed", latency_ms=1, error="provider_error")
            with self.assertRaises(ValueError):
                inspect_broker_recovery(root / "audit", binding, transport.ledger)
