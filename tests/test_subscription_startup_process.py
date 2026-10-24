"""Cold process startup and teardown through both routes without inference."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.capture_startup import capture


class StartupProcessTests(unittest.TestCase):
    def test_fresh_and_resumed_quit_and_eof_exit_cleanly_without_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            home = root / "home"
            home.mkdir(mode=0o700)
            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            for provider, label, client_name in (
                ("openai_subscription", "ChatGPT", "codex"),
                ("anthropic_subscription", "Claude", "claude"),
            ):
                native = root / client_name
                calls = root / (client_name + "-calls.jsonl")
                version = (
                    "codex-cli 0.163.0"
                    if client_name == "codex"
                    else "2.1.283 (Claude Code)"
                )
                # This fixture has no inference implementation. Record all
                # invocations and refuse anything beyond version/auth metadata.
                native.write_text(
                    f"#!{sys.executable}\n"
                    "import json, sys\n"
                    "from pathlib import Path\n"
                    f"with Path({str(calls)!r}).open('a') as log:\n"
                    "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                    "if sys.argv[1:] == ['--version']:\n"
                    f"    print({version!r})\n"
                    "elif sys.argv[1:] == ['login', 'status']:\n"
                    "    print('Logged in using ChatGPT')\n"
                    "elif sys.argv[1:] == ['auth', 'status']:\n"
                    "    print(json.dumps({'loggedIn': True, "
                    "'authMethod': 'claude.ai', 'apiProvider': 'firstParty'}))\n"
                    "else:\n"
                    "    raise SystemExit(99)\n"
                )
                native.chmod(0o700)
                for ending in ("quit", "eof"):
                    state = root / (client_name + "-" + ending)
                    original = None
                    authorization = None
                    for resume in (False, True):
                        with self.subTest(
                            provider=provider, ending=ending, resume=resume
                        ):
                            arguments = [
                                "subscription",
                                "chat",
                                "--provider",
                                provider,
                                "--client",
                                str(native),
                                "-C",
                                str(workspace),
                                "--state-dir",
                                str(state),
                                "--plain",
                                "--max-invocations",
                                "2" if resume else "1",
                                "--valid-for-seconds",
                                "300",
                                "--allow-data-transfer",
                                "--allow-subscription-usage",
                                "--accept-unverified-billing-and-native-retries",
                            ]
                            if resume:
                                assert authorization is not None
                                arguments += ["--resume", authorization.parent.name]
                            output = root / f"{client_name}-{ending}-{resume}"
                            with patch.dict(os.environ, {"HOME": str(home)}):
                                result = capture(
                                    [
                                        sys.executable,
                                        "-c",
                                        "from mos_eisley.cli import main; "
                                        "raise SystemExit(main())",
                                        *arguments,
                                    ],
                                    output,
                                    cwd=workspace,
                                    ending=ending,
                                    timeout=30,
                                )
                            stderr = (output / "stderr").read_bytes()
                            self.assertEqual(
                                result["returncode"],
                                0,
                                f"{result}; stderr={stderr!r}",
                            )
                            self.assertFalse(result["timed_out"])
                            text = (output / "stdout").read_text()
                            self.assertIn("conversation.saved:", text)
                            self.assertIn(f"{label} subscription conversation", text)
                            self.assertIn("original usage authorization", text)
                            paths = list(state.glob("*/authorization.json"))
                            self.assertEqual(len(paths), 1)
                            authorization = paths[0]
                            if original is None:
                                original = authorization.read_bytes()
                            self.assertEqual(authorization.read_bytes(), original)
                            authority = json.loads(original)
                            self.assertEqual(authority["max_invocations"], 1)
                            self.assertEqual(
                                list(Path(authority["usage_root"]).iterdir()), []
                            )
                self.assertEqual(
                    [json.loads(line) for line in calls.read_text().splitlines()],
                    [
                        call
                        for _ in range(4)
                        for call in (
                            ["--version"],
                            ["login", "status"]
                            if client_name == "codex"
                            else ["auth", "status"],
                        )
                    ],
                )
