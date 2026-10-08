"""Subscription identity, authority, parsing and native process boundaries."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import JsonValue, TypeAdapter

from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import JsonSchemaOutput, ModelRequest, TextBlock, Turn
from mos_eisley.platform.storage import StorageAdmissionError
from mos_eisley.providers.codex_subscription import (
    CLIENT_VERSION,
    PROVIDER,
    CodexSubscriptionClient,
    NativeProcessError,
    invoke,
    parse_result,
    select_client,
    status,
)
from mos_eisley.subscription_cli import add_command, run_command


def events(answer: str = "Fixture answer") -> list[dict[str, JsonValue]]:
    return [
        {"type": "thread.started", "thread_id": "fixture-thread"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "message-1",
                "type": "agent_message",
                "text": answer,
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 20,
                "output_tokens": 5,
                "cached_input_tokens": 2,
                "cache_write_input_tokens": 0,
                "reasoning_output_tokens": 0,
            },
        },
    ]


def encoded(value: list[dict[str, JsonValue]]) -> bytes:
    return b"\n".join(json.dumps(item).encode() for item in value)


def request() -> ModelRequest:
    return ModelRequest(
        provider=PROVIDER,
        model="gpt-6-sol",
        effort="medium",
        turns=(Turn(role="user", blocks=(TextBlock(text="Fixture question"),)),),
        max_output=4000,
        max_text_output_bytes=2000,
    )


class ResultTests(unittest.TestCase):
    def test_complete_turn_preserves_text_and_real_token_units(self) -> None:
        result = parse_result(encoded(events()), 2000)
        self.assertEqual(result.turn.blocks, (TextBlock(text="Fixture answer"),))
        self.assertEqual(result.usage.unit, "tokens")
        self.assertEqual(result.usage.cache_read, 2)

    def test_native_tool_events_are_rejected(self) -> None:
        for kind in ("command_execution", "file_change", "mcp_tool_call", "web_search"):
            value = events()
            value.insert(2, {"type": "item.started", "item": {"type": kind}})
            with self.subTest(kind=kind), self.assertRaises(ProviderError):
                parse_result(encoded(value), 2000)

    def test_failed_missing_duplicate_or_out_of_order_turn_rejected(self) -> None:
        complete = events()
        cases: list[list[dict[str, JsonValue]]] = [
            complete[:-1],
            complete + [complete[-1]],
            complete[1:],
            [complete[0], complete[2], complete[1], complete[3]],
            [
                *complete[:2],
                {"type": "turn.failed", "error": {"message": "private-fixture"}},
            ],
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ProviderError) as raised:
                parse_result(encoded(value), 2000)
            self.assertNotIn("private-fixture", str(raised.exception))

    def test_invalid_usage_never_becomes_zero_cost(self) -> None:
        usage_cases: tuple[dict[str, JsonValue], ...] = (
            {"input_tokens": True, "output_tokens": 5, "cached_input_tokens": 0},
            {"input_tokens": 20, "output_tokens": -1, "cached_input_tokens": 0},
            {"input_tokens": 20, "output_tokens": 5, "cached_input_tokens": 21},
            {"input_tokens": 20, "output_tokens": 5},
        )
        for values in usage_cases:
            values["cache_write_input_tokens"] = 0
            values["reasoning_output_tokens"] = 0
            value = events()
            value[-1]["usage"] = values
            with self.subTest(values=values), self.assertRaises(ProviderError):
                parse_result(encoded(value), 2000)

    def test_output_byte_ceiling_applies_to_utf8(self) -> None:
        with self.assertRaises(ProviderError):
            parse_result(encoded(events("☃" * 10)), 29)

    def test_expected_disabled_code_mode_warning_is_not_a_failed_turn(self) -> None:
        value = events()
        value.insert(
            1,
            {
                "type": "item.completed",
                "item": {
                    "type": "error",
                    "message": (
                        "Code Mode is unavailable because code-mode host is disabled. "
                        "Code mode will fail closed; enable `features.code_mode_host` "
                        "and install `codex-code-mode-host`."
                    ),
                },
            },
        )
        self.assertEqual(parse_result(encoded(value), 2000).stop_reason, "end_turn")
        value[1] = {
            "type": "item.completed",
            "item": {
                "type": "error",
                "message": "Different startup failure",
            },
        }
        with self.assertRaises(ProviderError):
            parse_result(encoded(value), 2000)

    def test_native_usage_keeps_cache_write_and_reasoning(self) -> None:
        value = events()
        usage = value[-1]["usage"]
        assert isinstance(usage, dict)
        usage["cache_write_input_tokens"] = 3
        usage["reasoning_output_tokens"] = 2
        result = parse_result(encoded(value), 2000)
        self.assertEqual(result.usage.cache_write, 3)
        self.assertEqual(result.usage.reasoning, 2)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.client = self.root / "codex"
        self.config = self.root / "fixture.json"
        self.log = self.root / "invocation.json"
        self.config.write_text(json.dumps({"events": events(), "auth": "ChatGPT"}))
        self.client.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys, time\n"
            f"config=json.load(open({str(self.config)!r}))\n"
            f"log={str(self.log)!r}\n"
            "if '--version' in sys.argv:\n"
            f" print('codex-cli '+config.get('version', {CLIENT_VERSION!r}))\n"
            "elif sys.argv[1:] == ['login', 'status']:\n"
            " print('Logged in using '+config['auth'], file=sys.stderr)\n"
            "else:\n"
            " data=sys.stdin.read()\n"
            " observed={'args':sys.argv[1:],'cwd':os.getcwd(),"
            "'env':sorted(os.environ),'data':data}\n"
            " json.dump(observed,open(log,'w'))\n"
            " if config.get('sleep'): time.sleep(30)\n"
            " if config.get('large'): print('x'*100000)\n"
            " for event in config['events']: print(json.dumps(event))\n"
            " sys.exit(config.get('exit_code',0))\n"
        )
        self.client.chmod(0o700)

    def adapter(self, attempt: str = "attempt") -> CodexSubscriptionClient:
        return CodexSubscriptionClient(
            self.client,
            self.root / attempt,
            allow_data_transfer=True,
            allow_subscription_usage=True,
        )

    def configure(self, **values: object) -> None:
        config: dict[str, object] = json.loads(self.config.read_text())
        config.update(values)
        self.config.write_text(json.dumps(config))

    def run_cli(
        self, arguments: list[str], prompt: bytes = b"Fixture question"
    ) -> tuple[int, str, str]:
        parser = argparse.ArgumentParser()
        add_command(parser.add_subparsers(dest="command", required=True).add_parser)
        selected = parser.parse_args(["subscription", *arguments])
        output, diagnostic = io.StringIO(), io.StringIO()
        with (
            io.TextIOWrapper(io.BytesIO(prompt)) as incoming,
            patch("sys.stdin", incoming),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(diagnostic),
        ):
            code = run_command(selected)
        return code, output.getvalue(), diagnostic.getvalue()

    def ask_arguments(self) -> list[str]:
        return [
            "ask",
            "--client",
            str(self.client),
            "--attempt",
            str(self.root / "cli-attempt"),
            "--model",
            "gpt-6-sol",
            "--effort",
            "medium",
            "--allow-data-transfer",
            "--allow-subscription-usage",
            "--json",
        ]

    async def test_cli_status_never_consumes_stdin_or_dispatches(self) -> None:
        code, output, _ = await asyncio.to_thread(
            self.run_cli, ["status", "--client", str(self.client)], b""
        )
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["subscription_signed_in"])
        self.assertFalse(self.log.exists())

    async def test_cli_consent_refusal_is_before_native_client(self) -> None:
        arguments = self.ask_arguments()
        arguments.remove("--allow-subscription-usage")
        code, _, _ = await asyncio.to_thread(self.run_cli, arguments)
        self.assertEqual(code, 2)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / "cli-attempt").exists())

    async def test_cli_single_turn_reports_subscription_usage_without_billing_claim(
        self,
    ) -> None:
        code, output, _ = await asyncio.to_thread(self.run_cli, self.ask_arguments())
        self.assertEqual(code, 0)
        result: dict[str, JsonValue] = TypeAdapter(dict[str, JsonValue]).validate_json(
            output
        )
        self.assertEqual(result["provider"], PROVIDER)
        self.assertFalse(result["billing_verified"])
        code, _, _ = await asyncio.to_thread(self.run_cli, self.ask_arguments())
        self.assertEqual(code, 2)

    async def test_cli_invalid_input_refuses_before_native_client(self) -> None:
        for prompt in (b"", b"\xff", b"x" * 128_001):
            code, _, _ = await asyncio.to_thread(
                self.run_cli, self.ask_arguments(), prompt
            )
            self.assertEqual(code, 2)
            self.assertFalse(self.log.exists())

    async def test_status_sends_no_prompt_and_exposes_no_raw_account_metadata(
        self,
    ) -> None:
        result = await status(self.client)
        self.assertEqual(
            result,
            {
                "client_version_supported": True,
                "subscription_signed_in": True,
            },
        )
        self.assertFalse(self.log.exists())

    async def test_unknown_client_version_rejects_before_authentication(self) -> None:
        self.configure(version="unreviewed-version")
        result = await status(self.client)
        self.assertFalse(result["client_version_supported"])
        self.assertFalse(self.log.exists())

    async def test_api_key_sign_in_never_dispatches(self) -> None:
        self.configure(auth="API key")
        with self.assertRaises(ProviderError):
            await self.adapter().complete(request())
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / "attempt" / "dispatch.json").exists())

    async def test_native_dispatch_is_isolated_and_secrets_are_not_inherited(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "fixture-secret",
                "ANTHROPIC_API_KEY": "fixture-secret",
                "UNRELATED_TOKEN": "fixture-secret",
            },
        ):
            result = await self.adapter().complete(request())
        self.assertEqual(result.stop_reason, "end_turn")
        logged = TypeAdapter(dict[str, JsonValue]).validate_json(self.log.read_text())
        environment = logged["env"]
        assert isinstance(environment, list)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("UNRELATED_TOKEN", environment)
        self.assertNotEqual(logged["cwd"], str(Path.cwd()))
        args = logged["args"]
        assert isinstance(args, list)
        for required in (
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--no-daemon",
        ):
            self.assertIn(required, args)
        self.assertIn('forced_login_method="chatgpt"', args)
        self.assertIn('web_search="disabled"', args)
        self.assertIn("shell_tool", args)
        self.assertIn("hooks", args)
        self.assertTrue((self.root / "attempt" / "completion.json").exists())
        for receipt in (self.root / "attempt").iterdir():
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("Fixture question", receipt.read_text())

    async def test_completed_attempt_is_not_replayed(self) -> None:
        adapter = self.adapter()
        await adapter.complete(request())
        with self.assertRaises(FileExistsError):
            await adapter.complete(request())

    async def test_failed_attempt_is_not_replayed_or_completed(self) -> None:
        self.configure(exit_code=1)
        adapter = self.adapter()
        with self.assertRaises(ProviderError):
            await adapter.complete(request())
        self.assertFalse((self.root / "attempt" / "completion.json").exists())
        with self.assertRaises(FileExistsError):
            await adapter.complete(request())

    async def test_provider_identity_rejected_before_native_client(self) -> None:
        with self.assertRaises(ProviderError):
            await self.adapter().complete(
                request().model_copy(update={"provider": "openai"})
            )
        self.assertFalse((self.root / "attempt").exists())

    async def test_unadmitted_profile_refuses_before_native_client(self) -> None:
        for model, effort in (("unqualified-model", "medium"), ("gpt-6-sol", "low")):
            with (
                self.subTest(model=model, effort=effort),
                self.assertRaises(ProviderError),
            ):
                await self.adapter().complete(
                    request().model_copy(update={"model": model, "effort": effort})
                )
            self.assertFalse((self.root / "attempt").exists())

    async def test_symlink_attempt_parent_refuses_before_native_client(self) -> None:
        linked = self.root / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        selected = CodexSubscriptionClient(
            self.client,
            linked / "attempt",
            allow_data_transfer=True,
            allow_subscription_usage=True,
        )
        with self.assertRaises(ProviderError):
            await selected.complete(request())
        self.assertFalse(self.log.exists())

    async def test_permission_ceiling_rejected_before_native_client(self) -> None:
        self.root.chmod(0o755)
        with self.assertRaises(ProviderError):
            await self.adapter().complete(request())
        self.assertFalse(self.log.exists())

    async def test_extended_parent_acl_refuses_before_native_client(self) -> None:
        with (
            patch(
                "mos_eisley.providers.codex_subscription.NativeRootQueries.protection",
                side_effect=StorageAdmissionError("extended ACL"),
            ),
            self.assertRaises(ProviderError),
        ):
            await self.adapter().complete(request())
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / "attempt").exists())

    async def test_inherited_attempt_acl_burns_attempt_before_authentication(
        self,
    ) -> None:
        with (
            patch(
                "mos_eisley.providers.codex_subscription.NativeRootQueries.protection",
                side_effect=[None, StorageAdmissionError("inherited ACL")],
            ),
            self.assertRaises(ProviderError),
        ):
            await self.adapter().complete(request())
        self.assertFalse(self.log.exists())
        self.assertTrue((self.root / "attempt").is_dir())
        with self.assertRaises(FileExistsError):
            await self.adapter().complete(request())

    async def test_receipt_writes_keep_opened_directory_after_path_replacement(
        self,
    ) -> None:
        parent, moved = self.root / "receipts", self.root / "moved"
        parent.mkdir(mode=0o700)
        selected = CodexSubscriptionClient(
            self.client,
            parent / "attempt",
            allow_data_transfer=True,
            allow_subscription_usage=True,
        )

        async def exchange(*args: object, **kwargs: object) -> tuple[int, bytes, bytes]:
            parent.rename(moved)
            parent.mkdir(mode=0o700)
            return 0, encoded(events()), b""

        with (
            patch(
                "mos_eisley.providers.codex_subscription.status",
                new=AsyncMock(
                    return_value={
                        "client_version_supported": True,
                        "subscription_signed_in": True,
                    }
                ),
            ),
            patch("mos_eisley.providers.codex_subscription.invoke", new=exchange),
        ):
            await selected.complete(request())
        self.assertTrue((moved / "attempt" / "completion.json").is_file())
        self.assertFalse((parent / "attempt").exists())

    async def test_strict_structured_output_and_token_rejection(self) -> None:
        output = JsonSchemaOutput(
            name="fixture",
            json_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        self.configure(events=events('{"value":"ok"}'))
        await self.adapter("structured").complete(
            request().model_copy(update={"response_format": output})
        )
        self.configure(events=events('{"value":3}'))
        with self.assertRaises(ProviderError):
            await self.adapter("invalid").complete(
                request().model_copy(update={"response_format": output})
            )
        with self.assertRaises(ProviderError):
            await self.adapter("tokens").complete(
                request().model_copy(update={"max_output_tokens": 4})
            )

    async def test_output_is_bounded_before_event_parsing(self) -> None:
        self.configure(large=True)
        with self.assertRaises(NativeProcessError) as caught:
            await invoke(self.client, ("exec",), self.root, output_limit=100)
        self.assertEqual(caught.exception.process_reason, "output_limit")

    async def test_cancellation_burns_attempt_without_completion(self) -> None:
        self.configure(sleep=True)
        task = asyncio.create_task(self.adapter().complete(request()))
        async with asyncio.timeout(3):
            while not self.log.exists():
                await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse((self.root / "attempt" / "completion.json").exists())
        with self.assertRaises(FileExistsError):
            await self.adapter().complete(request())

    async def test_timeout_is_finite_and_does_not_retry(self) -> None:
        self.configure(sleep=True)
        with self.assertRaises(NativeProcessError) as raised:
            await invoke(self.client, ("exec",), self.root, timeout=0.05)
        self.assertEqual(raised.exception.failure_kind, "provider_timeout")
        self.assertEqual(raised.exception.process_reason, "deadline")

    async def test_missing_native_client_has_controlled_start_reason(self) -> None:
        with self.assertRaises(NativeProcessError) as caught:
            await invoke(self.root / "missing", (), self.root)
        self.assertEqual(caught.exception.process_reason, "start")

    def test_absolute_project_local_client_is_rejected(self) -> None:
        with (
            patch(
                "mos_eisley.providers.codex_subscription.Path.cwd",
                return_value=self.root,
            ),
            self.assertRaises(ProviderError),
        ):
            select_client(self.client)

    def test_explicit_transfer_and_usage_consent_are_both_required(self) -> None:
        for transfer, usage in ((False, True), (True, False), (False, False)):
            with (
                self.subTest(transfer=transfer, usage=usage),
                self.assertRaises(ValueError),
            ):
                CodexSubscriptionClient(
                    self.client,
                    self.root / "attempt",
                    allow_data_transfer=transfer,
                    allow_subscription_usage=usage,
                )


if __name__ == "__main__":
    unittest.main()
