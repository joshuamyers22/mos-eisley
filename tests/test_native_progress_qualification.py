"""Offline qualification harness cannot admit missing or substituted identities."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.qualify_native_progress import probe, qualify


@unittest.skipUnless(os.name == "posix", "native progress qualification")
class ProgressQualificationTests(unittest.TestCase):
    def test_source_cli_probe_checks_four_waits_and_no_replay(self) -> None:
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
                set(result), {"silent", "output_wait", "exit_wait", "inherited_pipe"}
            )

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
