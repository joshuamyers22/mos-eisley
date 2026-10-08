"""Offline preparation/admission regression checks; no model invocation."""

import argparse
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from qualify_subscription_roles import prepare, read_prepared_scope

from mos_eisley.core.models import digest


class PreparedScopeTests(TestCase):
    def setUp(self) -> None:
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        parent = Path(temp.name).resolve()
        client = parent / "fixture-native"
        client.write_text("#!/bin/sh\nexit 99\n")
        client.chmod(0o700)
        self.root = parent / "qualification"
        args = argparse.Namespace(
            root=self.root,
            codex=client,
            claude=client,
            git=Path("/usr/bin/git"),
            docker=Path("/usr/local/bin/docker"),
            image_id="sha256:" + "1" * 64,
            valid_for_seconds=1200,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(args)

    def test_fresh_preparation_admits_exact_file_identity_without_dispatch(
        self,
    ) -> None:
        auth, selection, selection_sha = read_prepared_scope(self.root)
        self.assertEqual(
            selection_sha, digest((self.root / "selection.json").read_bytes())
        )
        self.assertEqual(selection.creator.expected_subscription_sha256, auth.sha256)
        self.assertEqual(auth.max_invocations, 14)
        self.assertEqual(selection.correction_cycles, 0)
        self.assertFalse((self.root / "run-started.json").exists())
        self.assertEqual(tuple((self.root / "usage").iterdir()), ())

    def test_semantically_equal_selection_byte_change_refuses(self) -> None:
        selection = self.root / "selection.json"
        with selection.open("ab") as output:
            output.write(b"\n")
        with self.assertRaisesRegex(ValueError, "Prepared synthetic scope changed"):
            read_prepared_scope(self.root)

    def test_synthetic_source_change_refuses(self) -> None:
        (self.root / "workspace/adder.py").write_text("def add(a,b):\n    return a+b\n")
        with self.assertRaisesRegex(ValueError, "Prepared synthetic scope changed"):
            read_prepared_scope(self.root)

    def test_authority_change_refuses(self) -> None:
        path = self.root / "authorization.json"
        value = json.loads(path.read_text())
        value["max_invocations"] = 15
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "Prepared synthetic scope changed"):
            read_prepared_scope(self.root)
