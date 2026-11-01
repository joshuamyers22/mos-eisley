"""Real offline process failures retain bounded metadata without native content."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from mos_eisley.core.protocol import ModelRequest, TextBlock, Turn
from mos_eisley.providers.claude_subscription import ClaudeSubscriptionClient
from mos_eisley.providers.codex_subscription import NativeProcessError, invoke
from mos_eisley.providers.native_progress import (
    PROGRESS_CAP,
    NativeProgress,
    NativeProgressReceipt,
)

SECRET = "private-native-token-/private/fixture.txt"
CHILD = """import json,os,subprocess,sys,time
from pathlib import Path
root=Path(__file__).parent
mode=(root/'mode').read_text()
record={'leader':os.getpid()}
(root/'pids.json').write_text(json.dumps(record))
if mode=='block_input': time.sleep(20)
sys.stdin.buffer.read()
if mode in ('clean','output_hang','descendant','overflow','stderr_overflow'):
    value=b'private-native-token-/private/fixture.txt\\n'
    if mode=='overflow': value*=1000
    if mode=='stderr_overflow':
        sys.stderr.buffer.write(value*1000)
        sys.stderr.buffer.flush()
    else:
        sys.stdout.buffer.write(value)
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(b'private-native-token-/private/fixture.txt\\n')
        sys.stderr.buffer.flush()
if mode=='clean': sys.exit(0)
if mode=='closed_streams':
    os.close(1)
    os.close(2)
if mode=='descendant':
    child=subprocess.Popen([sys.executable,'-c',
        'import signal,time; '
        'signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)'])
    record['descendant']=child.pid
    (root/'pids.json').write_text(json.dumps(record))
    os._exit(0)
time.sleep(20)
"""


class ProgressContractTests(unittest.TestCase):
    def test_counts_and_times_saturate_and_serialized_shape_is_fixed(self) -> None:
        observed = NativeProgress(started_at=0)
        with patch(
            "mos_eisley.providers.native_progress.time.monotonic", return_value=1e9
        ):
            elapsed = observed.elapsed_ms()
        observed.stdout.observe(PROGRESS_CAP * 100, elapsed)
        observed.stdout.observe(1, elapsed)
        receipt = observed.receipt(
            elapsed_ms=elapsed, leader_exited=False, cleanup_completed=True
        )
        self.assertEqual(receipt.stdout.bytes_observed, PROGRESS_CAP)
        self.assertEqual(receipt.stdout.first_read_ms, PROGRESS_CAP)
        self.assertEqual(receipt.stdout.last_read_ms, PROGRESS_CAP)
        self.assertEqual(receipt.elapsed_ms, PROGRESS_CAP)
        self.assertEqual(
            set(receipt.model_dump()),
            {
                "schema_version",
                "phase",
                "elapsed_ms",
                "stdin_drained",
                "stdout",
                "stderr",
                "leader_exited_before_cleanup",
                "cleanup_completed",
            },
        )
        self.assertLess(len(receipt.model_dump_json().encode()), 768)
        with patch(
            "mos_eisley.providers.native_progress.time.monotonic", return_value=-1
        ):
            self.assertEqual(observed.elapsed_ms(), 0)

    def test_schema_refuses_content_extra_fields_and_invalid_counter_types(
        self,
    ) -> None:
        value = (
            NativeProgress()
            .receipt(elapsed_ms=0, leader_exited=False, cleanup_completed=False)
            .model_dump()
        )
        for field, replacement in (
            ("elapsed_ms", True),
            ("elapsed_ms", -1),
            ("elapsed_ms", PROGRESS_CAP + 1),
            ("phase", SECRET),
            ("stdout", {"text": SECRET}),
            ("stderr", SECRET),
            ("stdin_drained", "yes"),
            ("schema_version", 2),
        ):
            with (
                self.subTest(field=field, replacement=replacement),
                self.assertRaises(ValidationError),
            ):
                NativeProgressReceipt.model_validate({**value, field: replacement})
        with self.assertRaises(ValidationError):
            NativeProgressReceipt.model_validate({**value, "native_output": SECRET})
        receipt = NativeProgressReceipt.model_validate(value)
        with self.assertRaises(ValidationError):
            receipt.phase = "exit"


@unittest.skipUnless(os.name == "posix", "native subscription process boundary")
class NativeProgressTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.child = self.root / "fake-native"
        self.child.write_text(f"#!{sys.executable}\n" + CHILD)
        self.child.chmod(0o700)

    def configure(self, mode: str) -> None:
        (self.root / "mode").write_text(mode)

    def assert_processes_stopped(self) -> None:
        pids = json.loads((self.root / "pids.json").read_text())
        for pid in pids.values():
            state = subprocess.run(
                ["ps", "-p", str(pid), "-o", "stat="],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            self.assertTrue(not state or state.startswith("Z"), state)

    async def failure(
        self, *, data: bytes = b"synthetic", output_limit: int = 1_000_000
    ) -> NativeProgressReceipt:
        with self.assertRaises(NativeProcessError) as caught:
            await invoke(
                self.child,
                (),
                self.root,
                data=data,
                timeout=1,
                output_limit=output_limit,
            )
        error = caught.exception
        self.assertNotIn(SECRET, str(error))
        progress = error.progress
        assert progress is not None
        self.assertNotIn(SECRET, progress.model_dump_json())
        self.assertNotIn(str(self.child), progress.model_dump_json())
        self.assertLess(len(progress.model_dump_json().encode()), 768)
        self.assert_processes_stopped()
        return progress

    async def test_silent_deadline_observes_no_output_and_cleanup(self) -> None:
        self.configure("silent")
        progress = await self.failure()
        self.assertEqual(progress.phase, "output")
        self.assertTrue(progress.stdin_drained)
        self.assertEqual(progress.stdout.bytes_observed, 0)
        self.assertIsNone(progress.stdout.first_read_ms)
        self.assertIsNone(progress.stderr.last_read_ms)
        self.assertFalse(progress.stdout.eof)
        self.assertFalse(progress.leader_exited_before_cleanup)
        self.assertTrue(progress.cleanup_completed)

    async def test_output_then_hang_retains_counts_not_content(self) -> None:
        self.configure("output_hang")
        progress = await self.failure()
        self.assertEqual(progress.stdout.bytes_observed, len(SECRET) + 1)
        self.assertEqual(progress.stderr.bytes_observed, len(SECRET) + 1)
        self.assertIsNotNone(progress.stdout.first_read_ms)
        self.assertIsNotNone(progress.stderr.last_read_ms)
        self.assertFalse(progress.stdout.eof)
        self.assertFalse(progress.leader_exited_before_cleanup)
        self.assertTrue(progress.cleanup_completed)

    async def test_exited_leader_with_inherited_pipe_is_distinct(self) -> None:
        self.configure("descendant")
        progress = await self.failure()
        self.assertEqual(progress.phase, "output")
        self.assertTrue(progress.leader_exited_before_cleanup)
        self.assertFalse(progress.stdout.eof)
        self.assertTrue(progress.cleanup_completed)

    async def test_eof_without_exit_records_exit_phase(self) -> None:
        self.configure("closed_streams")
        progress = await self.failure()
        self.assertEqual(progress.phase, "exit")
        self.assertTrue(progress.stdout.eof)
        self.assertTrue(progress.stderr.eof)
        self.assertFalse(progress.leader_exited_before_cleanup)

    async def test_stdin_backpressure_records_input_phase(self) -> None:
        self.configure("block_input")
        progress = await self.failure(data=b"x" * 2_000_000)
        self.assertEqual(progress.phase, "input")
        self.assertFalse(progress.stdin_drained)

    async def test_output_limits_remain_enforced_on_both_streams(self) -> None:
        for mode in ("overflow", "stderr_overflow"):
            with self.subTest(mode=mode):
                self.configure(mode)
                with self.assertRaises(NativeProcessError) as caught:
                    await invoke(self.child, (), self.root, timeout=2, output_limit=64)
                self.assertEqual(caught.exception.process_reason, "output_limit")
                progress = caught.exception.progress
                assert progress is not None
                self.assertTrue(progress.cleanup_completed)
                self.assert_processes_stopped()

    async def test_exchange_failure_is_redacted_and_cleaned(self) -> None:
        self.configure("silent")
        with (
            patch(
                "asyncio.StreamWriter.drain", new=AsyncMock(side_effect=OSError(SECRET))
            ),
            self.assertRaises(NativeProcessError) as caught,
        ):
            await invoke(self.child, (), self.root, data=b"x", timeout=2)
        self.assertEqual(caught.exception.process_reason, "exchange")
        progress = caught.exception.progress
        assert progress is not None
        self.assertEqual(progress.phase, "input")
        self.assertTrue(progress.cleanup_completed)
        self.assertNotIn(SECRET, str(caught.exception))

    async def test_cleanup_failure_overrides_reason_and_never_claims_completion(
        self,
    ) -> None:
        self.configure("clean")
        with patch(
            "mos_eisley.providers.codex_subscription.os.killpg",
            side_effect=OSError(SECRET),
        ):
            progress = await self.failure()
        self.assertFalse(progress.cleanup_completed)
        self.assertTrue(progress.leader_exited_before_cleanup)
        self.assertEqual(progress.phase, "exit")

    async def test_cancellation_propagates_and_stops_owned_process(self) -> None:
        self.configure("silent")
        task = asyncio.create_task(invoke(self.child, (), self.root, timeout=5))
        async with asyncio.timeout(3):
            while not (self.root / "pids.json").exists():
                await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_processes_stopped()

    async def test_clean_exchange_returns_original_bytes(self) -> None:
        self.configure("clean")
        code, stdout, stderr = await invoke(self.child, (), self.root, timeout=2)
        self.assertEqual(code, 0)
        self.assertEqual(stdout, (SECRET + "\n").encode())
        self.assertEqual(stderr, stdout)
        self.assert_processes_stopped()

    async def test_claude_receipt_persists_only_bounded_metadata_and_refuses_replay(
        self,
    ) -> None:
        self.configure("output_hang")
        client = ClaudeSubscriptionClient(
            self.child,
            self.root / "attempt",
            allow_data_transfer=True,
            allow_subscription_usage=True,
            timeout=1,
        )
        request = ModelRequest(
            provider="anthropic_subscription",
            model="claude-sonnet-5",
            effort="high",
            turns=(Turn(role="user", blocks=(TextBlock(text=SECRET),)),),
            max_output=4000,
            max_output_tokens=100,
        )
        with patch(
            "mos_eisley.providers.claude_subscription.status",
            new=AsyncMock(
                return_value={
                    "client_version_supported": True,
                    "subscription_signed_in": True,
                }
            ),
        ):
            with self.assertRaises(NativeProcessError):
                await client.complete(request)
            path = self.root / "attempt/failure.json"
            raw = path.read_bytes()
            receipt = json.loads(raw)
            self.assertNotIn(SECRET.encode(), raw)
            self.assertNotIn(str(self.child).encode(), raw)
            self.assertEqual(receipt["process_reason"], "deadline")
            self.assertEqual(
                receipt["progress"]["stdout"]["bytes_observed"], len(SECRET) + 1
            )
            self.assertTrue(receipt["progress"]["cleanup_completed"])
            self.assertLess(len(raw), 1024)
            self.assertFalse((self.root / "attempt/completion.json").exists())
            with self.assertRaises(FileExistsError):
                await client.complete(request)
            self.assertEqual(path.read_bytes(), raw)
        self.assert_processes_stopped()
