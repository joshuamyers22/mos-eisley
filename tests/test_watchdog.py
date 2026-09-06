"""Lease EOF, independent deadlines, exact removal and cleanup receipts."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.watchdog import (
    CleanupLease,
    CleanupRecord,
    WatchdogHandle,
    arm_watchdog,
    remove_exact,
    supervise,
)

CID = "c" * 64


class WatchdogTests(TestCase):
    def test_removal_is_exact_and_missing_requires_successful_absence_check(
        self,
    ) -> None:
        for target in ("short", "--all", "name", "A" * 64):
            with self.subTest(target=target), self.assertRaises(ValueError):
                remove_exact("/usr/bin/docker", target)
        with self.assertRaises(ValueError):
            remove_exact("docker", CID)
        with patch(
            "mos_eisley.run.watchdog.bounded_process", return_value=b"removed"
        ) as command:
            remove_exact("/usr/bin/docker", CID)
        self.assertEqual(
            command.call_args.args[0], ["/usr/bin/docker", "rm", "--force", CID]
        )
        for response in (b"", CID.encode(), ValueError("daemon offline")):
            with patch(
                "mos_eisley.run.watchdog.bounded_process",
                side_effect=[ValueError("rm failed"), response],
            ) as command:
                if response == b"":
                    remove_exact("/usr/bin/docker", CID)
                else:
                    with self.assertRaises(ValueError):
                        remove_exact("/usr/bin/docker", CID)
                self.assertEqual(command.call_args.args[0][-1], "id=" + CID)

    def test_eof_retries_are_bounded_and_failures_are_recorded(self) -> None:
        for succeeds in (True, False):
            with self.subTest(succeeds=succeeds), TemporaryDirectory() as directory:
                root = Path(directory)
                reader, writer = os.pipe()
                os.close(writer)
                lease = CleanupLease(container_id=CID, max_runtime_seconds=60)
                ready = MagicMock()
                effects = (
                    [OSError("private error"), None]
                    if succeeds
                    else [OSError("private error")] * 3
                )
                try:
                    with patch(
                        "mos_eisley.run.watchdog.remove_exact", side_effect=effects
                    ) as remove:
                        result = supervise(
                            "/usr/bin/docker", lease, root, reader, ready
                        )
                finally:
                    os.close(reader)
                ready.assert_called_once_with()
                self.assertEqual(result.attempts, 2 if succeeds else 3)
                self.assertEqual(remove.call_count, result.attempts)
                self.assertEqual(
                    result.state, "removed" if succeeds else "cleanup_failed"
                )
                self.assertNotIn(b"private error", (root / "result.json").read_bytes())
                self.assertEqual((root / "result.json").stat().st_mode & 0o777, 0o600)

    def test_live_writer_cannot_extend_deadline(self) -> None:
        with TemporaryDirectory() as directory:
            reader, writer = os.pipe()
            lease = CleanupLease(container_id=CID, max_runtime_seconds=0.02)
            try:
                with patch("mos_eisley.run.watchdog.remove_exact") as remove:
                    result = supervise(
                        "/usr/bin/docker", lease, Path(directory), reader, lambda: None
                    )
                self.assertEqual(result.state, "removed")
                remove.assert_called_once_with("/usr/bin/docker", CID)
            finally:
                os.close(reader)
                os.close(writer)

    def test_real_detached_guardian_has_private_lease_and_no_inherited_key(
        self,
    ) -> None:
        # A harmless executable stands in for the trusted Docker client; no daemon.
        client = shutil.which("true")
        assert client is not None
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "private-test-key"}):
                handle = arm_watchdog(client, CID, root, 60)
            assert handle.writer is not None
            self.assertFalse(os.get_inheritable(handle.writer))
            self.assertNotEqual(os.getsid(handle.process.pid), os.getsid(0))
            start = time.monotonic()
            handle.finish()
            self.assertLess(time.monotonic() - start, 5)
            self.assertIsNone(handle.writer)
            self.assertNotIn(
                b"private-test-key",
                b"".join(p.read_bytes() for p in handle.directory.iterdir()),
            )
            self.assertEqual(handle.directory.stat().st_mode & 0o777, 0o700)

    def test_finish_rejects_wrong_receipt_and_does_not_kill_slow_guardian(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            lease = CleanupLease(container_id=CID, max_runtime_seconds=1)
            result = CleanupRecord(
                lease_sha256=digest(canonical_bytes(lease)),
                container_id="d" * 64,
                state="removed",
                attempts=1,
            )
            (root / "result.json").write_bytes(canonical_bytes(result))
            process = MagicMock()
            process.wait.return_value = 0
            reader, writer = os.pipe()
            os.close(reader)
            handle = WatchdogHandle(process, writer, root, lease)
            with self.assertRaises(ValueError):
                handle.finish()
            process.wait.side_effect = subprocess.TimeoutExpired("watchdog", 25)
            with self.assertRaises(ValueError):
                handle.finish()
            process.kill.assert_not_called()

    def test_guardian_spawn_failure_never_returns_ready(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch(
                "mos_eisley.run.watchdog.subprocess.Popen",
                side_effect=OSError("unavailable"),
            ),
            self.assertRaises(OSError),
        ):
            arm_watchdog("/usr/bin/docker", CID, Path(directory), 1)
