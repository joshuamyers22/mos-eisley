"""Process outcomes survive failure, signals and deadline termination."""

from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path

from tools.capture_startup import capture


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "capture"

    def run_child(self, source: str, *, timeout: float = 5) -> dict[str, object]:
        result = capture(
            [sys.executable, "-c", source],
            self.output,
            cwd=self.root,
            ending="quit",
            timeout=timeout,
        )
        self.assertEqual(json.loads((self.output / "status.json").read_text()), result)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        return result

    def test_nonzero_exit_retains_exact_status_and_binary_output(self) -> None:
        result = self.run_child(
            "import sys; assert sys.stdin.buffer.read() == b'/quit\\n'; "
            "sys.stdout.buffer.write(b'\\xffsaved\\n'); "
            "sys.stderr.write('diagnostic'); sys.exit(7)"
        )
        self.assertEqual(result["returncode"], 7)
        self.assertIsNone(result["signal"])
        self.assertFalse(result["timed_out"])
        self.assertEqual((self.output / "stdout").read_bytes(), b"\xffsaved\n")
        self.assertEqual((self.output / "stderr").read_bytes(), b"diagnostic")

    def test_signal_is_distinguished_from_application_exit(self) -> None:
        result = self.run_child(
            "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
        )
        self.assertEqual(result["returncode"], -signal.SIGTERM)
        self.assertEqual(result["signal"], "SIGTERM")
        self.assertFalse(result["timed_out"])

    def test_timeout_keeps_partial_output_and_reaps_child(self) -> None:
        result = self.run_child(
            "import time; print('started', flush=True); time.sleep(30)", timeout=0.5
        )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["signal"], "SIGKILL")
        self.assertEqual((self.output / "stdout").read_bytes(), b"started\n")
        with self.assertRaises(ProcessLookupError):
            os.kill(int(str(result["pid"])), 0)

    def test_spawn_failure_is_persisted_and_prior_evidence_cannot_be_replaced(
        self,
    ) -> None:
        result = capture(
            [str(self.root / "missing")], self.output, cwd=self.root, ending="eof"
        )
        self.assertIsNone(result["returncode"])
        self.assertEqual(result["spawn_error"], "FileNotFoundError")
        original = (self.output / "status.json").read_bytes()
        with self.assertRaises(FileExistsError):
            capture([sys.executable], self.output, cwd=self.root, ending="eof")
        self.assertEqual((self.output / "status.json").read_bytes(), original)
