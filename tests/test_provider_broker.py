"""Adversarial grant checks composed with the real spending controller/ledger."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport
from mos_eisley.run.provider_broker import RequestBoundBroker
from mos_eisley.run.spend_ledger import SpendLedger
from tests.test_openai_spend import FakeTransport, policy, request


class BrokerTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 300)
        self.fake = FakeTransport(self.root)
        self.transport = BudgetedOpenAITransport(
            self.fake, policy(), self.root, self.ledger
        )
        self.payload = request()
        self.broker = RequestBoundBroker(self.payload, self.transport)
        self.claim = self.broker.claim()
        self.wire = canonical_bytes(self.claim)

    async def test_snapshot_and_single_use(self) -> None:
        self.payload["model"] = "unauthorized"
        self.payload["input"] = []
        self.assertNotIn(self.claim.capability, repr(self.claim))
        await self.broker.redeem(self.wire)
        self.assertEqual(self.fake.calls[0]["model"], "gpt-6-astra")
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)
        with self.assertRaises(ProviderError):
            await self.broker.redeem(self.wire)
        self.assertEqual(len(self.fake.calls), 1)

    async def test_malformed_substituted_and_cross_job_claims(self) -> None:
        other = RequestBoundBroker(request(), self.transport)
        for wire in (
            b"not json",
            b"x" * 1025,
            self.wire.replace(b'"schema_version":1', b'"schema_version":2'),
            self.wire[:-1] + b',"model":"other"}',
            canonical_bytes(self.claim.model_copy(update={"request_sha256": "0" * 64})),
            canonical_bytes(other.claim()),
        ):
            with self.assertRaisesRegex(ProviderError, "broker grant rejected"):
                await self.broker.redeem(wire)
        self.assertEqual(self.fake.counts, [])
        self.assertEqual(self.ledger.snapshot().charged_microusd, 0)
        await self.broker.redeem(self.wire)

    async def test_expired_before_counting(self) -> None:
        with patch("mos_eisley.run.provider_broker.time.monotonic", return_value=0):
            broker = RequestBoundBroker(request(), self.transport, lifetime_seconds=1)
        with self.assertRaises(ProviderError):
            await broker.redeem(canonical_bytes(broker.claim()))
        self.assertEqual(self.fake.counts, [])

    async def test_concurrent_claims_dispatch_once(self) -> None:
        results = await asyncio.gather(
            self.broker.redeem(self.wire),
            self.broker.redeem(self.wire),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(r, ProviderError) for r in results), 1)
        self.assertEqual(len(self.fake.calls), 1)

    async def test_failure_burns_grant_and_retains_reservation(self) -> None:
        self.fake.error = RuntimeError("secret upstream detail")
        with self.assertRaisesRegex(ProviderError, "^broker response unavailable$"):
            await self.broker.redeem(self.wire)
        with self.assertRaises(ProviderError):
            await self.broker.redeem(self.wire)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 210)
        self.assertEqual(len(self.fake.calls), 1)

    async def test_cancellation_burns_grant_and_retains_reservation(self) -> None:
        self.fake.error = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.broker.redeem(self.wire)
        with self.assertRaises(ProviderError):
            await self.broker.redeem(self.wire)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 210)

    async def test_deadline_burns_grant(self) -> None:
        broker = RequestBoundBroker(request(), self.transport, lifetime_seconds=0.1)
        with (
            patch.object(self.transport, "create_response", side_effect=self.slow),
            self.assertRaisesRegex(ProviderError, "broker response unavailable"),
        ):
            await broker.redeem(canonical_bytes(broker.claim()))
        with self.assertRaises(ProviderError):
            await broker.redeem(canonical_bytes(broker.claim()))

    @staticmethod
    async def slow(*_: object) -> None:
        await asyncio.sleep(1)

    def test_rejects_unbounded_or_unledgered_grants(self) -> None:
        for lifetime in (0, -1, 61, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                RequestBoundBroker(request(), self.transport, lifetime_seconds=lifetime)
        with self.assertRaises(ValueError):
            RequestBoundBroker({"input": "x" * 1_048_576}, self.transport)
        with self.assertRaises(ValueError):
            RequestBoundBroker(
                request(), BudgetedOpenAITransport(self.fake, policy(), self.root)
            )
