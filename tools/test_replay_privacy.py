"""Admission guards must refuse before creating disposable OS accounts."""

import argparse
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import qualify_replay_privacy as qualifier


class ReplayQualificationTests(unittest.TestCase):
    def test_local_account_creation_is_refused(self) -> None:
        with (
            patch.object(os, "getuid", return_value=0),
            patch.object(os, "geteuid", return_value=0),
            patch.dict(
                os.environ, {"GITHUB_ACTIONS": "false", "RUNNER_ENVIRONMENT": "local"}
            ),
            patch.object(qualifier, "add_user") as create,
            self.assertRaisesRegex(AssertionError, "local account creation forbidden"),
        ):
            qualifier.qualify(argparse.Namespace(), {})
        create.assert_not_called()

    def test_mismatched_or_nonroot_setup_refuses(self) -> None:
        for real, effective in ((501, 501), (501, 0), (0, 501)):
            with (
                self.subTest(real=real, effective=effective),
                patch.object(os, "getuid", return_value=real),
                patch.object(os, "geteuid", return_value=effective),
                patch.object(qualifier, "add_user") as create,
                self.assertRaisesRegex(AssertionError, "root setup required"),
            ):
                qualifier.qualify(argparse.Namespace(), {})
            create.assert_not_called()

    def test_wrong_signed_candidate_refuses_before_account_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "release.json").write_bytes(b"{}")
            for version, source in (("wrong", "expected"), ("expected", "wrong")):
                with (
                    self.subTest(version=version, source=source),
                    patch.object(os, "getuid", return_value=0),
                    patch.object(os, "geteuid", return_value=0),
                    patch.dict(
                        os.environ,
                        {
                            "GITHUB_ACTIONS": "true",
                            "RUNNER_ENVIRONMENT": "github-hosted",
                        },
                    ),
                    patch(
                        "mos_eisley.app_release.parse_release",
                        return_value=SimpleNamespace(
                            version=version, source_commit=source
                        ),
                    ),
                    patch.object(qualifier, "add_user") as create,
                    self.assertRaisesRegex(
                        AssertionError, "candidate identity mismatch"
                    ),
                ):
                    qualifier.qualify(
                        argparse.Namespace(
                            assets=root,
                            expected_version="expected",
                            expected_source="expected",
                        ),
                        {},
                    )
                create.assert_not_called()

    def test_signature_and_size_refusal_precede_account_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for payload in (b"{}", b"x" * 128_001):
                (root / "release.json").write_bytes(payload)
                with (
                    self.subTest(size=len(payload)),
                    patch.object(os, "getuid", return_value=0),
                    patch.object(os, "geteuid", return_value=0),
                    patch.dict(
                        os.environ,
                        {
                            "GITHUB_ACTIONS": "true",
                            "RUNNER_ENVIRONMENT": "github-hosted",
                        },
                    ),
                    patch.object(qualifier, "add_user") as create,
                    self.assertRaises((ValueError, AssertionError)),
                ):
                    qualifier.qualify(argparse.Namespace(assets=root), {})
                create.assert_not_called()
