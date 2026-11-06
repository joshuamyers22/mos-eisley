"""Actual disposable process challenges for redacted startup diagnostics."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import diagnose_staged_startup as subject


class StartupDiagnosticsTests(unittest.TestCase):
    def observe(
        self, code: str, *, deadline: float = 2, limit: float = 3
    ) -> dict[str, object]:
        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(subject, "process_state", return_value={"state": "S"}),
        ):
            return subject.observe(
                [sys.executable, "-c", code],
                Path(root),
                {"PATH": os.defpath},
                b"version",
                deadline=deadline,
                limit=limit,
            )

    def test_early_exact_version_is_observed_without_raw_content(self) -> None:
        record = self.observe("print('version')")
        self.assertTrue(record["contract_passed"])
        self.assertTrue(record["cleanup_completed"])
        self.assertFalse(record["original_deadline_exceeded"])
        text = json.dumps(record)
        self.assertNotIn(sys.executable, text)
        self.assertNotIn('"pid"', text)
        self.assertNotIn('"stdout"', text)

    def test_late_result_never_rewrites_original_deadline_as_pass(self) -> None:
        record = self.observe(
            "import time; time.sleep(.3); print('version')", deadline=0.1, limit=0.8
        )
        self.assertTrue(record["original_deadline_exceeded"])
        self.assertTrue(record["version_matches"])
        self.assertEqual(record["exit_code"], 0)
        self.assertFalse(record["contract_passed"])

    def test_silent_process_is_killed_and_reaped_at_observation_bound(self) -> None:
        record = self.observe("import time; time.sleep(20)", deadline=0.1, limit=0.3)
        self.assertTrue(record["original_deadline_exceeded"])
        self.assertTrue(record["cleanup_completed"])
        self.assertFalse(record["contract_passed"])
        self.assertLess(record["elapsed_ms"], 2000)  # type: ignore[operator]

    def test_invalid_exit_and_output_do_not_pass_or_escape_receipt(self) -> None:
        for code in ("print('private-output-marker')", "raise SystemExit(7)"):
            record = self.observe(code)
            self.assertFalse(record["contract_passed"])
            self.assertNotIn("private-output-marker", json.dumps(record))

    def test_large_output_is_capped_and_process_cleaned(self) -> None:
        record = self.observe("import os,time; os.write(1,b'x'*100000); time.sleep(20)")
        self.assertTrue(record["output_limit_exceeded"])
        self.assertEqual(record["stdout_bytes"], subject.OUTPUT_LIMIT)
        self.assertTrue(record["cleanup_completed"])
        self.assertFalse(record["contract_passed"])

    def test_owned_child_holding_pipe_is_killed_at_bound(self) -> None:
        record = self.observe(
            "import os,time; child=os.fork(); "
            "time.sleep(20) if child==0 else print('version')",
            deadline=0.1,
            limit=0.3,
        )
        self.assertTrue(record["cleanup_completed"])
        self.assertTrue(record["original_deadline_exceeded"])
        self.assertFalse(record["contract_passed"])
        self.assertLess(record["elapsed_ms"], 2000)  # type: ignore[operator]

    def test_process_state_excludes_identifiers_and_arguments(self) -> None:
        record = subject.process_state(os.getpid())
        self.assertIn(
            record["state"], {"R", "S", "D", "I", "Z", "T", "U", "X", "unavailable"}
        )
        self.assertTrue(
            set(record) <= {"state", "cpu_percent", "cpu_seconds", "rss_kib"}
        )

    def test_unbounded_or_reversed_profile_refused_before_spawn(self) -> None:
        with patch.object(subject.subprocess, "Popen") as spawn:
            for deadline, limit in ((0, 1), (2, 1), (30, 121)):
                with self.assertRaises(ValueError):
                    subject.observe(
                        [], Path.cwd(), {}, b"", deadline=deadline, limit=limit
                    )
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
