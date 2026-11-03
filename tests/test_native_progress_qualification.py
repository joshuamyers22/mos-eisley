"""Offline qualification harness cannot admit missing or substituted identities."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mos_eisley.core.protocol import ModelRequest, TextBlock, Turn
from mos_eisley.providers.claude_subscription import parse_result
from tools.qualify_native_progress import (
    MARKER,
    probe,
    qualify,
    review_contract,
    terminal_events,
)


@unittest.skipUnless(os.name == "posix", "native progress qualification")
class ProgressQualificationTests(unittest.TestCase):
    def test_terminal_fixture_is_valid_under_the_real_protocol_parser(self) -> None:
        request = ModelRequest(
            provider="anthropic_subscription",
            model="claude-sonnet-5",
            effort="high",
            turns=(Turn(role="user", blocks=(TextBlock(text=MARKER),)),),
            max_output=1000,
            max_text_output_bytes=1000,
        )
        result = parse_result(terminal_events().encode(), request)
        self.assertEqual(result.turn.blocks, (TextBlock(text=MARKER),))

    def test_source_cli_probe_checks_six_waits_and_no_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            home, path = root / "home", root / "path"
            home.mkdir(mode=0o700)
            path.mkdir(mode=0o700)
            result = probe(
                Path(sys.executable).parent / "mos",
                root,
                {"HOME": str(home), "PATH": str(path), "LANG": "en_US.UTF-8"},
            )
            self.assertEqual(
                set(result),
                {
                    "silent",
                    "output_wait",
                    "exit_wait",
                    "inherited_pipe",
                    "valid_result_wait",
                    "invalid_result_wait",
                },
            )

    def test_review_contract_is_explicitly_source_level_and_redacted(self) -> None:
        result = review_contract()
        self.assertEqual(
            result["scope"], "exact_candidate_source_not_installed_model_review_path"
        )
        self.assertTrue(result["valid_bound_review"])
        self.assertTrue(result["redacted_bounded_receipts"])

    def test_invalid_signature_refuses_before_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "release.json").write_text("{}")
            with patch("tools.qualify_native_progress.subprocess.run") as run:
                with self.assertRaises(ValueError):
                    qualify(root, root / "report.json", "a" * 40, "0.1.0-rc.13")
                run.assert_not_called()
            self.assertFalse((root / "report.json").exists())

    def test_mismatched_signed_subject_refuses_before_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "release.json").write_text("{}")
            with (
                patch(
                    "tools.qualify_native_progress.parse_release",
                    return_value=SimpleNamespace(
                        source_commit="b" * 40, version="0.1.0-rc.13", storage_epoch=2
                    ),
                ),
                patch("tools.qualify_native_progress.subprocess.run") as run,
            ):
                with self.assertRaises(ValueError):
                    qualify(root, root / "report.json", "a" * 40, "0.1.0-rc.13")
                run.assert_not_called()
            self.assertFalse((root / "report.json").exists())
