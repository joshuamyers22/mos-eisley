"""Offline preparation/admission regression checks; no model invocation."""

import argparse
import asyncio
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from qualify_claude_subscription import main as diagnostic_main
from qualify_claude_subscription import prepare as prepare_diagnostic
from qualify_claude_subscription import read_diagnostic_request
from qualify_claude_subscription import read_scope as read_diagnostic_scope
from qualify_claude_subscription import run as run_diagnostic
from qualify_subscription_roles import prepare, read_prepared_scope

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest, TextBlock, Turn


class PreparedScopeTests(TestCase):
    def test_exact_synthetic_critic_request_is_bound_and_capped(self) -> None:
        request = ModelRequest(
            provider="anthropic_subscription",
            model="claude-sonnet-5",
            effort="high",
            turns=(
                Turn(role="user", blocks=(TextBlock(text="Synthetic plan review"),)),
            ),
            max_output=500000,
        )
        raw = canonical_bytes(request)
        path = self.root.parent / "synthetic-request.json"
        path.write_bytes(raw)
        bounded = read_diagnostic_request(path, digest(raw))
        self.assertEqual(bounded.turns, request.turns)
        self.assertEqual(
            (
                bounded.max_output,
                bounded.max_text_output_bytes,
                bounded.max_output_tokens,
            ),
            (18000, 16000, 2048),
        )
        path.write_bytes(raw + b"\n")
        with self.assertRaisesRegex(ValueError, "identity changed"):
            read_diagnostic_request(path, digest(raw))

    def test_synthetic_request_refuses_other_profile_and_oversize_input(self) -> None:
        path = self.root.parent / "synthetic-request.json"
        for model in ("other",):
            request = ModelRequest(
                provider="anthropic_subscription",
                model=model,
                effort="high",
                turns=(
                    Turn(
                        role="user",
                        blocks=(TextBlock(text="Synthetic plan review"),),
                    ),
                ),
                max_output=18000,
            )
            raw = canonical_bytes(request)
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                read_diagnostic_request(path, digest(raw))
        raw = b" " * 128001
        path.write_bytes(raw)
        with self.assertRaises(ValueError):
            read_diagnostic_request(path, digest(raw))

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

    def test_claude_diagnostic_has_only_one_exact_role_invocation(self) -> None:
        root = self.root.parent / "diagnostic"
        with contextlib.redirect_stdout(io.StringIO()):
            prepare_diagnostic(root, self.root.parent / "fixture-native")
        auth = read_diagnostic_scope(root)
        self.assertEqual(auth.max_invocations, 1)
        self.assertEqual(len(auth.grants), 1)
        self.assertEqual(auth.grants[0].role, "critic_anthropic")
        self.assertEqual(tuple(auth.usage_root.iterdir()), ())

    def test_combined_diagnostic_prepares_current_scope_and_runs_once(self) -> None:
        root = self.root.parent / "diagnostic"

        async def inspect_scope(path: Path) -> dict[str, str]:
            auth = read_diagnostic_scope(path)
            self.assertEqual(auth.max_invocations, 1)
            self.assertFalse((path / "run-started.json").exists())
            return {"result": "passed"}

        with (
            patch(
                "sys.argv",
                [
                    "diagnostic",
                    "prepare-run",
                    "--root",
                    str(root),
                    "--client",
                    str(self.root.parent / "fixture-native"),
                    "--approve-live-claude-diagnostic",
                ],
            ),
            patch("qualify_claude_subscription.run", side_effect=inspect_scope) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            diagnostic_main()
            run.assert_called_once_with(root)

    def test_combined_diagnostic_without_approval_never_prepares(self) -> None:
        root = self.root.parent / "diagnostic"
        with (
            patch(
                "sys.argv",
                [
                    "diagnostic",
                    "prepare-run",
                    "--root",
                    str(root),
                    "--client",
                    str(self.root.parent / "fixture-native"),
                ],
            ),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            diagnostic_main()
        self.assertFalse(root.exists())

    def test_claude_diagnostic_refuses_expanded_invocation_budget(self) -> None:
        root = self.root.parent / "diagnostic"
        with contextlib.redirect_stdout(io.StringIO()):
            prepare_diagnostic(root, self.root.parent / "fixture-native")
        path = root / "authorization.json"
        value = json.loads(path.read_text())
        value["max_invocations"] = 2
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "one-invocation limits"):
            read_diagnostic_scope(root)

    def test_claude_diagnostic_failure_report_never_replays_or_retains_error_text(
        self,
    ) -> None:
        root = self.root.parent / "diagnostic"
        with contextlib.redirect_stdout(io.StringIO()):
            prepare_diagnostic(root, self.root.parent / "fixture-native")
        with patch(
            "qualify_claude_subscription.AuthorizedSubscriptionClient.complete",
            new=AsyncMock(side_effect=ProviderError("fixture-secret")),
        ) as native:
            report = asyncio.run(run_diagnostic(root))
            self.assertEqual(report["result"], "stopped_on_first_failure")
            self.assertNotIn("fixture-secret", (root / "diagnostic.json").read_text())
            with self.assertRaises(FileExistsError):
                asyncio.run(run_diagnostic(root))
            self.assertEqual(native.await_count, 1)
