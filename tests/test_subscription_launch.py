"""Subscription TUI setup preserves consent, scope identity and private storage."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mos_eisley.subscription_authorization import read_authorization
from mos_eisley.subscription_cli import add_command, run_command


class LaunchTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.client = self.root / "native"
        self.client.write_text("Owner-selected fixture binary")
        self.client.chmod(0o700)
        self.state = self.root / "state"
        self.native = AsyncMock(
            return_value={
                "client_version_supported": True,
                "subscription_signed_in": True,
            }
        )
        self.chat = self.enterContext(patch("mos_eisley.cli.main", return_value=0))
        self.enterContext(patch("mos_eisley.subscription_launch.status", self.native))
        self.enterContext(
            patch("mos_eisley.subscription_launch.claude_status", self.native)
        )
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def arguments(self, provider: str = "openai_subscription") -> list[str]:
        return [
            "chat",
            "--provider",
            provider,
            "--client",
            str(self.client),
            "-C",
            str(self.workspace),
            "--state-dir",
            str(self.state),
            "--allow-data-transfer",
            "--allow-subscription-usage",
            "--accept-unverified-billing-and-native-retries",
        ]

    def run_cli(self, arguments: list[str]) -> int:
        parser = argparse.ArgumentParser()
        add_command(parser.add_subparsers(dest="command", required=True).add_parser)
        return run_command(parser.parse_args(["subscription", *arguments]))

    def authorization(self) -> Path:
        return next(self.state.glob("*/authorization.json"))

    def test_both_routes_create_exact_private_scope_and_delegate_without_prompt(
        self,
    ) -> None:
        for provider, model, effort in (
            ("openai_subscription", "gpt-6-sol", "medium"),
            ("anthropic_subscription", "claude-sonnet-5", "high"),
        ):
            with self.subTest(provider=provider):
                self.state = self.root / provider
                self.assertEqual(self.run_cli(self.arguments(provider)), 0)
                path = self.authorization()
                scope = read_authorization(path)
                self.assertEqual(scope.workspace, self.workspace)
                self.assertEqual(scope.max_invocations, 4)
                self.assertEqual(
                    (
                        scope.grant("chat").provider,
                        scope.grant("chat").model,
                        scope.grant("chat").effort,
                    ),
                    (provider, model, effort),
                )
                self.assertEqual(scope.grant("chat").client, self.client)
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
                for directory in (self.state, path.parent, scope.usage_root):
                    self.assertEqual(os.stat(directory).st_mode & 0o777, 0o700)
                arguments = self.chat.call_args.args[0]
                self.assertEqual(arguments[0], "chat")
                self.assertEqual(
                    arguments[arguments.index("--subscription-authorization") + 1],
                    str(path),
                )
                self.assertNotIn("--live-openai", arguments)
                self.assertFalse(list(scope.usage_root.iterdir()))

    def test_each_missing_consent_refuses_before_native_or_state(self) -> None:
        for flag in (
            "--allow-data-transfer",
            "--allow-subscription-usage",
            "--accept-unverified-billing-and-native-retries",
        ):
            arguments = self.arguments()
            arguments.remove(flag)
            with patch("sys.stdin.isatty", return_value=False):
                self.assertEqual(self.run_cli(arguments), 2)
            self.assertFalse(self.state.exists())
        self.native.assert_not_called()
        self.chat.assert_not_called()

    def test_interactive_consent_decline_and_eof_leave_no_scope(self) -> None:
        args = self.arguments()
        args.remove("--allow-subscription-usage")
        for response in ("n", EOFError()):
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", side_effect=[response]),
            ):
                self.assertEqual(self.run_cli(args), 2)
            self.assertFalse(self.state.exists())

    def test_interactive_confirmation_can_start(self) -> None:
        arguments = self.arguments()
        arguments.remove("--allow-subscription-usage")
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="y"),
        ):
            self.assertEqual(self.run_cli(arguments), 0)
        self.assertTrue(self.authorization().exists())

    def test_missing_sign_in_or_unsupported_client_never_starts_chat(self) -> None:
        for compatible, signed_in in ((True, False), (False, False)):
            self.native.return_value = {
                "client_version_supported": compatible,
                "subscription_signed_in": signed_in,
            }
            self.assertEqual(self.run_cli(self.arguments()), 2)
            self.assertFalse(list(self.state.glob("*/authorization.json")))
        self.chat.assert_not_called()

    def test_resume_preserves_original_authorization_and_ledger(self) -> None:
        self.assertEqual(self.run_cli(self.arguments()), 0)
        path = self.authorization()
        raw = path.read_bytes()
        scope = read_authorization(path)
        marker = scope.usage_root / "retained-fixture"
        marker.write_text("uncertain usage must remain")
        self.assertEqual(
            self.run_cli([*self.arguments(), "--resume", scope.session_id]), 0
        )
        self.assertEqual(self.chat.call_args.args[0][:2], ["resume", scope.session_id])
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(marker.read_text(), "uncertain usage must remain")
        self.assertEqual(len(list(self.state.glob("*/authorization.json"))), 1)

    def test_resume_rejects_changed_route_workspace_binary_or_expiry(self) -> None:
        self.assertEqual(self.run_cli(self.arguments()), 0)
        path = self.authorization()
        raw = path.read_bytes()
        scope = read_authorization(path)
        self.chat.reset_mock()
        self.native.reset_mock()
        self.assertEqual(
            self.run_cli(
                [
                    *self.arguments("anthropic_subscription"),
                    "--resume",
                    scope.session_id,
                ]
            ),
            2,
        )
        other = self.root / "other"
        other.mkdir()
        self.assertEqual(
            self.run_cli(
                [*self.arguments(), "--resume", scope.session_id, "-C", str(other)]
            ),
            2,
        )
        self.client.write_text("Changed binary")
        self.assertEqual(
            self.run_cli([*self.arguments(), "--resume", scope.session_id]), 2
        )
        self.client.write_text("Owner-selected fixture binary")
        value = json.loads(raw)
        value["valid_until"] = "2000-01-01T00:00:00Z"
        path.write_text(json.dumps(value))
        self.assertEqual(
            self.run_cli([*self.arguments(), "--resume", scope.session_id]), 2
        )
        self.chat.assert_not_called()
        self.native.assert_not_called()

    def test_invalid_session_or_limits_refuse_without_dispatch(self) -> None:
        for extra in (
            ["--resume", "../escape"],
            ["--max-invocations", "65"],
            ["--valid-for-seconds", "3601"],
            ["--timeout", "0"],
        ):
            self.assertEqual(self.run_cli([*self.arguments(), *extra]), 2)
        self.native.assert_not_called()
        self.chat.assert_not_called()

    def test_unsafe_or_symlink_state_directory_refused(self) -> None:
        target = self.root / "target"
        target.mkdir(mode=0o700)
        self.state.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.run_cli(self.arguments()), 2)
        self.state.unlink()
        self.state.mkdir(mode=0o755)
        self.assertEqual(self.run_cli(self.arguments()), 2)
        self.native.assert_not_called()
        self.chat.assert_not_called()

    def test_failure_is_returned_without_retry_or_replacing_scope(self) -> None:
        self.chat.return_value = 2
        self.assertEqual(self.run_cli(self.arguments()), 2)
        self.chat.assert_called_once()
        self.assertTrue(self.authorization().exists())
