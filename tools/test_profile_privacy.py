"""Failure-oriented checks for the disposable real-user controller."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qualify_profile_privacy as controller


class ControllerTests(unittest.TestCase):
    def test_local_execution_is_refused_before_account_provisioning(self) -> None:
        with (
            patch.object(controller.os, "geteuid", return_value=0),
            patch.dict(
                os.environ, {"GITHUB_ACTIONS": "false", "RUNNER_ENVIRONMENT": "local"}
            ),
            patch.object(controller, "add_user") as create,
        ):
            with self.assertRaisesRegex(
                AssertionError, "local account creation forbidden"
            ):
                controller.qualify(argparse.Namespace(), {})
            create.assert_not_called()

    def test_nonroot_setup_is_refused(self) -> None:
        with (
            patch.object(controller.os, "geteuid", return_value=501),
            self.assertRaisesRegex(AssertionError, "root setup required"),
        ):
            controller.qualify(argparse.Namespace(), {})

    def test_enrollment_mismatch_is_refused_before_parsing_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "release.json").write_text("{}")
            with patch.object(controller, "parse_release") as parse:
                with self.assertRaisesRegex(AssertionError, "enrollment mismatch"):
                    controller.authenticate(root, "linux-x86_64")
                parse.assert_not_called()

    def test_output_limit_kills_and_reaps_process(self) -> None:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import os,time;os.write(1,b'x'*200000);time.sleep(60)",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        with self.assertRaisesRegex(AssertionError, "output limit"):
            controller.finish(process)
        self.assertIsNotNone(process.poll())

    def test_drain_both_streams_and_preserve_nonzero_status(self) -> None:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import os;os.write(1,b'ok');os.write(2,b'failed');exit(3)",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        code, output = controller.finish(process)
        self.assertEqual(code, 3)
        self.assertIn(b"ok", output)
        self.assertIn(b"failed", output)

    def test_actor_positive_cases_on_both_backends_and_sdk_canary_controls(
        self,
    ) -> None:
        # Development test only. Two actual user evidence is produced by CI, not
        # by pretending this process has a second identity.
        actor = Path(__file__).with_name("privacy_actor.py").resolve()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for backend in ("snapshot", "sqlite"):
                for operation in ("seed", "owner"):
                    result = subprocess.run(
                        [sys.executable, str(actor), operation, str(root), backend],
                        capture_output=True,
                        timeout=120,
                        check=True,
                    )
                    self.assertTrue(json.loads(result.stdout)["passed"])
            result = subprocess.run(
                [sys.executable, str(actor), "outbound", str(root), "snapshot"],
                capture_output=True,
                timeout=120,
                check=True,
            )
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["sdk_request_cases"], 2)
            self.assertTrue(receipt["contaminated_and_empty_controls_rejected"])
            self.assertNotIn(b"SYNTHETIC-OWNER", result.stdout)


if __name__ == "__main__":
    unittest.main()
