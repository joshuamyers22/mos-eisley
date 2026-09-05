"""Exercise real subprocess pipes without credentials or network access."""

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport
from mos_eisley.run.broker_wire import BrokerAck, BrokerReply
from mos_eisley.run.duplex import bounded_exchange
from mos_eisley.run.isolated_broker import run_isolated_broker
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import MAX_WIRE_BYTES
from mos_eisley.run.provider_broker import RequestBoundBroker
from mos_eisley.run.spend_ledger import SpendLedger
from tests.test_openai_spend import FakeTransport, policy, request

PREFIX = "import sys; offer=sys.stdin.buffer.readline(); "
CLAIM = "sys.stdout.buffer.write(offer); sys.stdout.buffer.flush(); "


class DuplexTests(IsolatedAsyncioTestCase):
    async def test_deadline_preserves_inflight_spending_reservation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = SpendLedger.create(root / "ledger.sqlite", 300)
            fake = FakeTransport(root)
            broker = RequestBoundBroker(
                request(), BudgetedOpenAITransport(fake, policy(), root, ledger)
            )

            async def slow(*_: object) -> None:
                await asyncio.sleep(10)

            async def handle(wire: bytes) -> bytes:
                return canonical_bytes(BrokerReply(response=await broker.redeem(wire)))

            with (
                patch.object(fake, "create_response", side_effect=slow),
                self.assertRaises(ValueError),
            ):
                await bounded_exchange(
                    [sys.executable, "-m", "mos_eisley.run.broker_worker"],
                    canonical_bytes(broker.claim()),
                    handle,
                    timeout=1,
                )
            self.assertEqual(ledger.snapshot().charged_microusd, 210)
            with self.assertRaises(ProviderError):
                await broker.redeem(canonical_bytes(broker.claim()))

    async def test_real_worker_roundtrip_and_filtered_environment(self) -> None:
        reply = canonical_bytes(BrokerReply(response={"text": "fixture"}))
        claims: list[bytes] = []

        async def handle(wire: bytes) -> bytes:
            claims.append(wire)
            return reply

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-canary"}):
            result = await bounded_exchange(
                [sys.executable, "-m", "mos_eisley.run.broker_worker"], b"grant", handle
            )
            probe = PREFIX + "import os; assert 'OPENAI_API_KEY' not in os.environ; "
            probe += CLAIM + "sys.stdin.buffer.readline(); print('ok')"
            self.assertEqual(
                await bounded_exchange([sys.executable, "-c", probe], b"grant", handle),
                b"ok",
            )
        self.assertEqual(claims, [b"grant", b"grant"])
        self.assertEqual(
            BrokerAck.model_validate_json(result).response_sha256, digest(reply)
        )

    async def test_resource_and_protocol_failures(self) -> None:
        async def handle(_: bytes) -> bytes:
            return b"reply"

        for code in (
            "print('x'*5000)",
            "import sys; sys.stderr.write('x'*70000)",
            "import time; time.sleep(10)",
            "import sys; sys.exit(2)",
            PREFIX + "sys.stdout.write('partial'); sys.stdout.flush()",
            PREFIX + CLAIM + "sys.stdin.buffer.readline(); print('ok'); print('extra')",
            PREFIX + CLAIM + "sys.stdin.buffer.readline(); print('x'*5000)",
            PREFIX + CLAIM + "sys.stdin.buffer.readline(); print('ok'); sys.exit(2)",
        ):
            with self.subTest(code=code), self.assertRaises(ValueError):
                await bounded_exchange(
                    [sys.executable, "-c", code], b"grant", handle, timeout=0.3
                )

    async def test_pipelined_claim_never_dispatches(self) -> None:
        calls = 0

        async def handle(_: bytes) -> bytes:
            nonlocal calls
            calls += 1
            return b"reply"

        code = PREFIX + "sys.stdout.buffer.write(offer*2); sys.stdout.buffer.flush()"
        with self.assertRaises(ValueError):
            await bounded_exchange([sys.executable, "-c", code], b"grant", handle)
        self.assertEqual(calls, 0)

    async def test_disconnect_cancels_inflight_handler(self) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def handle(_: bytes) -> bytes:
            started.set()
            try:
                await asyncio.sleep(10)
                return b"unreachable"
            finally:
                cancelled.set()

        code = PREFIX + CLAIM + "import time; time.sleep(0.2)"
        with self.assertRaises(ValueError):
            await bounded_exchange([sys.executable, "-c", code], b"grant", handle)
        self.assertTrue(started.is_set())
        self.assertTrue(cancelled.is_set())

    async def test_caller_cancellation_reaches_handler(self) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def handle(_: bytes) -> bytes:
            started.set()
            try:
                await asyncio.sleep(10)
                return b"unreachable"
            finally:
                cancelled.set()

        task = asyncio.create_task(
            bounded_exchange(
                [sys.executable, "-c", PREFIX + CLAIM + "sys.stdin.buffer.readline()"],
                b"grant",
                handle,
            )
        )
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cancelled.is_set())

    async def test_invalid_host_frames_and_deadlines(self) -> None:
        async def handle(_: bytes) -> bytes:
            return b"reply"

        for offer, timeout in (
            (b"x" * 1025, 1),
            (b"a\nb", 1),
            (b"a", 0),
            (b"a", float("nan")),
            (b"a", 61),
        ):
            with self.assertRaises(ValueError):
                await bounded_exchange([sys.executable], offer, handle, timeout)
        for reply in (b"a\nb", b"x" * (MAX_WIRE_BYTES + 1)):

            async def invalid(_: bytes, reply: bytes = reply) -> bytes:
                return reply

            with self.assertRaises(ValueError):
                await bounded_exchange(
                    [
                        sys.executable,
                        "-c",
                        PREFIX + CLAIM + "sys.stdin.buffer.readline()",
                    ],
                    b"grant",
                    invalid,
                )


class BrokerIntegrationTests(TestCase):
    def test_host_held_response_and_bad_ack(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeTransport(root)
            transport = BudgetedOpenAITransport(
                fake, policy(), root, SpendLedger.create(root / "ledger.sqlite", 300)
            )
            broker = RequestBoundBroker(request(), transport)
            container = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)

            def execute(*args: object, **kwargs: object) -> bytes:
                # Run actual worker and exchange, substituting only Docker launch.
                from typing import cast

                from mos_eisley.run.duplex import ExchangeHandler

                return asyncio.run(
                    bounded_exchange(
                        [sys.executable, "-m", "mos_eisley.run.broker_worker"],
                        cast(bytes, args[1]),
                        cast(ExchangeHandler, kwargs["exchange_handler"]),
                    )
                )

            with patch.object(container, "execute", side_effect=execute):
                self.assertEqual(
                    run_isolated_broker(broker, container).response, fake.response
                )
            with (
                patch.object(
                    container,
                    "execute",
                    return_value=canonical_bytes(BrokerAck(response_sha256="0" * 64)),
                ),
                self.assertRaises(ValueError),
            ):
                run_isolated_broker(broker, container)
