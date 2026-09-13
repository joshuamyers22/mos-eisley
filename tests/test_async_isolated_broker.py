"""Real worker pipes with controlled Docker lifecycle and shared spending."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch

from pydantic import JsonValue
from test_openai_spend import FakeTransport, policy, request

from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport, SpendReceipt
from mos_eisley.run.broker_wire import BrokerAck
from mos_eisley.run.duplex import ExchangeHandler, bounded_exchange
from mos_eisley.run.isolated_broker import run_isolated_broker_async
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.provider_broker import RequestBoundBroker
from mos_eisley.run.spend_ledger import SpendLedger

IMAGE = "sha256:" + "a" * 64
CONTAINER_ID = "b" * 64


class AsyncBrokerTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.container = OfflineContainer(Path("/usr/bin/docker"), IMAGE)
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 300)
        self.transport = FakeTransport(self.root)
        self.broker = RequestBoundBroker(
            request(),
            BudgetedOpenAITransport(self.transport, policy(), self.root, self.ledger),
        )
        self.guard = MagicMock()
        self.guard.directory = self.root / "guardian"
        self.guard.finish.side_effect = lambda: self.stage("finish")
        self.events: list[str] = []
        self.commands: list[list[str]] = []
        self.hold: str | None = None
        self.entered = threading.Event()
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        self.fail_stage: str | None = None
        self.metadata = json.dumps([{"Id": IMAGE, "Config": {}}]).encode()
        self.created = CONTAINER_ID.encode()
        self.exit_code = b"0"
        self.worker = [sys.executable, "-m", "mos_eisley.run.broker_worker"]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(
            patch(
                "mos_eisley.run.async_isolation.bounded_process",
                side_effect=self.process,
            )
        )
        self.stack.enter_context(
            patch("mos_eisley.run.async_isolation.arm_watchdog", side_effect=self.arm)
        )
        self.remove = self.stack.enter_context(
            patch(
                "mos_eisley.run.async_isolation.remove_exact",
                side_effect=self.remove_container,
            )
        )
        self.exchange = self.stack.enter_context(
            patch(
                "mos_eisley.run.async_isolation.bounded_exchange",
                side_effect=self.real_exchange,
            )
        )

    def stage(self, name: str) -> None:
        self.events.append(name)
        if self.hold == name:
            self.entered.set()
            if not self.release.wait(5):
                raise ValueError("test barrier timeout")
        if self.fail_stage == name:
            raise ValueError("fixture lifecycle failure")

    def process(self, command: list[str], **_: object) -> bytes:
        self.commands.append(command)
        if command[1:3] == ["image", "inspect"]:
            self.stage("metadata")
            return self.metadata
        if command[1] == "create":
            self.stage("create")
            return self.created
        if command[1] == "inspect":
            self.stage("exit")
            return self.exit_code
        if command[1:3] == ["rm", "--force"]:
            self.stage("remove-name")
            return b""
        raise AssertionError(command)

    def remove_container(self, *_: object) -> None:
        self.stage("remove")

    def arm(self, *_: object) -> MagicMock:
        self.stage("arm")
        return self.guard

    async def real_exchange(
        self, command: list[str], offer: bytes, handler: ExchangeHandler, timeout: float
    ) -> bytes:
        self.commands.append(command)
        self.stage("exchange")
        return await bounded_exchange(self.worker, offer, handler, timeout)

    async def wait_for_stage(self) -> None:
        async with asyncio.timeout(3):
            while not self.entered.is_set():
                await asyncio.sleep(0.005)

    async def run_broker(self, timeout: float = 3) -> object:
        return await run_isolated_broker_async(
            self.broker, self.container, timeout=timeout
        )

    async def test_real_worker_roundtrip_uses_exact_host_response_and_cleanup(
        self,
    ) -> None:
        result = await run_isolated_broker_async(self.broker, self.container)
        self.assertEqual(result.response, self.transport.response)
        self.assertEqual(
            self.events,
            ["metadata", "create", "arm", "exchange", "exit", "remove", "finish"],
        )
        self.remove.assert_called_once_with("/usr/bin/docker", CONTAINER_ID)
        self.assertEqual(self.container.lifecycle_path, self.guard.directory)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)
        self.assertEqual(len(self.transport.calls), 1)
        with self.assertRaises(ProviderError):
            await self.broker.redeem(canonical_bytes(self.broker.claim()))

    async def test_same_confinement_flags_as_sync_path(self) -> None:
        await self.run_broker()
        command = next(c for c in self.commands if c[1] == "create")
        self.assertEqual(
            command,
            self.container.create_command(
                command[3], ("-m", "mos_eisley.run.broker_worker")
            ),
        )
        for forbidden in ("--volume", "--mount", "--privileged", "--env"):
            self.assertNotIn(forbidden, command)
        for option, value in (
            ("--network", "none"),
            ("--user", "10001:10001"),
            ("--cap-drop", "ALL"),
            ("--log-driver", "none"),
        ):
            self.assertEqual(command[command.index(option) + 1], value)
        self.assertIn("--read-only", command)
        self.assertEqual(
            next(c for c in self.commands if c[1] == "start")[-1], CONTAINER_ID
        )

    async def test_invalid_bounds_do_not_start_host_operations(self) -> None:
        async def handler(_: bytes) -> bytes:
            return b"reply"

        for payload, timeout in (
            (b"x" * 1025, 1),
            (b"x\ny", 1),
            (b"x", 0),
            (b"x", 61),
            (b"x", float("nan")),
        ):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                await self.container.exchange_async((), payload, handler, timeout)
        self.assertEqual(self.events, [])

    async def test_image_mismatch_and_implicit_volumes_never_create(self) -> None:
        cases: tuple[JsonValue, ...] = (
            [],
            [{"Id": "wrong", "Config": {}}],
            [{"Id": IMAGE, "Config": {"Volumes": {"/data": {}}}}],
            [{"Id": IMAGE, "Config": None}],
        )
        for metadata in cases:
            self.metadata = json.dumps(metadata).encode()
            with self.assertRaises(ValueError):
                await self.run_broker()
        self.assertEqual(self.events, ["metadata"] * 4)

    async def test_malformed_container_id_removes_generated_name(self) -> None:
        self.created = b"not-an-id"
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.assertEqual(self.events, ["metadata", "create", "remove-name"])
        name = self.commands[-1][-1]
        self.assertRegex(name, r"^mos-eval-[0-9a-f]{32}$")
        self.assertEqual(name, self.commands[1][3])

    async def test_create_failure_cleans_invocation_name_without_dispatch(self) -> None:
        self.fail_stage = "create"
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.assertEqual(self.events, ["metadata", "create", "remove-name"])
        self.assertEqual(self.commands[-1][-1], self.commands[1][3])
        self.assertEqual(self.transport.counts, [])

    async def test_failed_guardian_prevents_worker_and_cleans_exact_id(self) -> None:
        self.fail_stage = "arm"
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.assertEqual(self.events, ["metadata", "create", "arm", "remove"])
        self.remove.assert_called_once_with("/usr/bin/docker", CONTAINER_ID)
        self.assertEqual(self.transport.counts, [])

    async def test_cancel_during_metadata_waits_without_blocking_loop(self) -> None:
        self.hold = "metadata"
        task = asyncio.create_task(self.run_broker())
        try:
            await self.wait_for_stage()
            task.cancel()
            await asyncio.sleep(0.02)
            self.assertFalse(task.done())
        finally:
            self.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.events, ["metadata"])

    async def test_cancel_during_create_captures_id_before_exact_cleanup(self) -> None:
        self.hold = "create"
        task = asyncio.create_task(self.run_broker())
        try:
            await self.wait_for_stage()
            task.cancel()
            await asyncio.sleep(0.02)
            task.cancel()
            self.assertFalse(task.done())
        finally:
            self.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.events, ["metadata", "create", "remove"])
        self.remove.assert_called_once_with("/usr/bin/docker", CONTAINER_ID)
        self.assertEqual(self.transport.calls, [])

    async def test_cancel_during_guardian_setup_captures_and_finishes_guardian(
        self,
    ) -> None:
        self.hold = "arm"
        task = asyncio.create_task(self.run_broker())
        try:
            await self.wait_for_stage()
            task.cancel()
        finally:
            self.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.events, ["metadata", "create", "arm", "remove", "finish"])
        self.assertEqual(self.transport.calls, [])

    async def test_inflight_cancellation_keeps_uncertain_spend_and_consumes_grant(
        self,
    ) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow(_: object) -> dict[str, object]:
            started.set()
            try:
                await asyncio.sleep(10)
                return {}
            finally:
                cancelled.set()

        with patch.object(self.transport, "create_response", side_effect=slow):
            task = asyncio.create_task(self.run_broker())
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.events[-2:], ["remove", "finish"])
        receipt = SpendReceipt.model_validate_json(
            (self.root / "spend-receipt.json").read_bytes()
        )
        self.assertEqual(receipt.status, "uncertain")
        self.assertEqual(self.ledger.snapshot().charged_microusd, 210)
        with self.assertRaises(ProviderError):
            await self.broker.redeem(canonical_bytes(self.broker.claim()))

    async def test_repeated_cancel_waits_for_handler_teardown(self) -> None:
        started, finishing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def slow(_: object) -> dict[str, object]:
            started.set()
            try:
                await asyncio.sleep(10)
                return {}
            finally:
                finishing.set()
                await release.wait()

        with patch.object(self.transport, "create_response", side_effect=slow):
            task = asyncio.create_task(self.run_broker())
            try:
                await asyncio.wait_for(started.wait(), 3)
                task.cancel()
                await asyncio.wait_for(finishing.wait(), 3)
                task.cancel()
                await asyncio.sleep(0.02)
                self.assertFalse(task.done())
                self.assertNotIn("remove", self.events)
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.events[-2:], ["remove", "finish"])

    async def test_cancellation_during_cleanup_cannot_return_success_or_skip_guardian(
        self,
    ) -> None:
        self.hold = "remove"
        task = asyncio.create_task(self.run_broker())
        try:
            await self.wait_for_stage()
            task.cancel()
            await asyncio.sleep(0.02)
            task.cancel()
            self.assertFalse(task.done())
        finally:
            self.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.events[-2:], ["remove", "finish"])

    async def test_cleanup_failure_never_returns_success_and_still_finishes_guardian(
        self,
    ) -> None:
        self.fail_stage = "remove"
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.assertEqual(self.events[-2:], ["remove", "finish"])

    async def test_guardian_failure_never_returns_success(self) -> None:
        self.fail_stage = "finish"
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.assertEqual(self.events[-2:], ["remove", "finish"])

    async def test_timeout_cancels_provider_and_cleans_worker(self) -> None:
        cancelled = asyncio.Event()

        async def slow(_: object) -> dict[str, object]:
            try:
                await asyncio.sleep(10)
                return {}
            finally:
                cancelled.set()

        with (
            patch.object(self.transport, "create_response", side_effect=slow),
            self.assertRaises(ValueError),
        ):
            await self.run_broker(timeout=0.5)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.ledger.snapshot().charged_microusd, 210)
        self.assertEqual(self.events[-2:], ["remove", "finish"])

    async def test_simultaneous_reuse_of_container_rejected_before_dispatch(
        self,
    ) -> None:
        self.hold = "create"
        task = asyncio.create_task(self.run_broker())
        try:
            await self.wait_for_stage()
            with self.assertRaises(ValueError):
                await self.run_broker()
        finally:
            self.release.set()
        await task
        self.assertEqual(self.events.count("create"), 1)

    async def test_ack_without_dispatch_is_rejected_after_cleanup(self) -> None:
        self.exchange.side_effect = None
        self.exchange.return_value = canonical_bytes(
            BrokerAck(response_sha256="0" * 64)
        )
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.events[-2:], ["remove", "finish"])

    async def test_wrong_ack_after_dispatch_cannot_replace_host_response(self) -> None:
        async def wrong(
            command: list[str], offer: bytes, handler: ExchangeHandler, timeout: float
        ) -> bytes:
            await self.real_exchange(command, offer, handler, timeout)
            return canonical_bytes(BrokerAck(response_sha256="0" * 64))

        self.exchange.side_effect = wrong
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.events[-2:], ["remove", "finish"])

    async def test_nonzero_container_exit_fails_after_cleanup(self) -> None:
        self.exit_code = b"1"
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.assertEqual(self.events[-3:], ["exit", "remove", "finish"])

    async def test_cancel_during_exit_inspection_discards_response_and_cleans(
        self,
    ) -> None:
        self.hold = "exit"
        task = asyncio.create_task(self.run_broker())
        try:
            await self.wait_for_stage()
            task.cancel()
        finally:
            self.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.events[-3:], ["exit", "remove", "finish"])
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)

    async def test_pre_dispatch_failure_allows_later_use_with_same_instance(
        self,
    ) -> None:
        self.fail_stage = "metadata"
        with self.assertRaises(ValueError):
            await self.run_broker()
        self.fail_stage = None
        await self.run_broker()
        self.assertEqual(len(self.transport.calls), 1)
