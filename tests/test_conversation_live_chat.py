"""Offline checks for live TUI dispatch, saved identity and uncertain turns."""

import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from pydantic import JsonValue

from mos_eisley.conversation import ConversationController, conversation_config
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_live_chat import LiveChatRuntime
from mos_eisley.conversation_state import ConversationState, LiveChatIdentity
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.agent import AgentConfig, AgentResult, run_agent
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    TextBlock,
    Turn,
    Usage,
)
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.conversation_resume import inspect_sqlite_resume
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.tools.none import NoToolsDispatcher


class AnswerClient:
    def __init__(self, requests: list[ModelRequest]) -> None:
        self.requests = requests

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            turn=Turn(role="assistant", blocks=(TextBlock(text="Live answer"),)),
            stop_reason="end_turn",
            usage=Usage(unit="tokens", input=12, output=4),
        )


class CountedAnswerTransport:
    def __init__(self) -> None:
        self.calls = 0

    async def count_input_tokens(self, _payload: dict[str, JsonValue]) -> int:
        return 10

    async def create_response(
        self, _payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        return {
            "id": "resp_offline",
            "model": "gpt-5.6-luna",
            "service_tier": "default",
            "status": "completed",
            "output": [
                {
                    "type": "reasoning",
                    "id": "rsn_offline",
                    "summary": [],
                    "encrypted_content": "x" * 12_000,
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Live answer"}],
                },
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "input_tokens_details": {"cache_write_tokens": 0},
            },
        }


class LiveConversationTests(IsolatedAsyncioTestCase):
    async def test_cli_opens_live_tui_session_without_dispatching(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir(mode=0o700)
            policy = SpendPolicy(
                schema_version=2,
                model="gpt-5.6-luna",
                pricing_source="offline test rates",
                valid_from=datetime.now(UTC) - timedelta(minutes=1),
                valid_until=datetime.now(UTC) + timedelta(minutes=5),
                input_microusd_per_million=1_000_000,
                cache_write_microusd_per_million=1_000_000,
                output_microusd_per_million=1_000_000,
                max_cost_microusd=200,
                max_output_tokens=128,
            )
            policy_path = root / "policy.json"
            policy_path.write_bytes(canonical_bytes(policy))
            ledger = SpendLedger.create(root / "spend.sqlite", 200)
            args = (
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "chat",
                "--json",
                "--live-openai",
                "--allow-data-transfer",
                "--spend-policy",
                str(policy_path),
                "--spend-ledger",
                str(root / "spend.sqlite"),
                "--live-artifacts",
                str(artifacts),
                "-C",
                str(root),
            )
            result = subprocess.run(
                args,
                input="",
                text=True,
                capture_output=True,
                cwd=root,
                env={**os.environ, "HOME": str(root), "OPENAI_API_KEY": "offline-key"},
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = ConversationSnapshot.model_validate_json(
                next((root / ".mos-eisley-sessions").glob("*.json")).read_bytes()
            )
            self.assertEqual(snapshot.state.mode, "openai_live_conversation")
            self.assertEqual(snapshot.state.entries, ())
            self.assertEqual(ledger.snapshot().entries, 0)
            resumed = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "resume",
                    "--last",
                    *args[4:],
                ),
                input="",
                text=True,
                capture_output=True,
                cwd=root,
                env={**os.environ, "HOME": str(root), "OPENAI_API_KEY": "offline-key"},
                timeout=15,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(ledger.snapshot().entries, 0)

            legacy_path = root / "legacy-policy.json"
            legacy_path.write_bytes(
                canonical_bytes(
                    policy.model_copy(
                        update={
                            "schema_version": 1,
                            "cache_write_microusd_per_million": None,
                        }
                    )
                )
            )
            legacy_args = list(args)
            legacy_args[legacy_args.index(str(policy_path))] = str(legacy_path)
            rejected = subprocess.run(
                legacy_args,
                input="",
                text=True,
                capture_output=True,
                cwd=root,
                env={**os.environ, "HOME": str(root), "OPENAI_API_KEY": "offline-key"},
                timeout=15,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("input or artifact validation failed", rejected.stderr)
            self.assertEqual(ledger.snapshot().entries, 0)

    async def test_runtime_reserves_before_dispatch_and_records_receipt(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o700)
            policy = SpendPolicy(
                schema_version=2,
                model="gpt-5.6-luna",
                pricing_source="offline test rates",
                valid_from=datetime.now(UTC) - timedelta(minutes=1),
                valid_until=datetime.now(UTC) + timedelta(minutes=5),
                input_microusd_per_million=1_000_000,
                cache_write_microusd_per_million=1_000_000,
                output_microusd_per_million=1_000_000,
                max_cost_microusd=5_000,
                max_output_tokens=4_096,
            )
            ledger = SpendLedger.create(root / "spend.sqlite", 5_000)
            identity = LiveChatIdentity(
                model=policy.model,
                effort="medium",
                max_output_tokens=4_096,
                spend_policy_sha256=policy.policy_sha256,
                spend_ledger_id=ledger.policy.ledger_id,
                artifacts_root=str(root.resolve()),
            )
            runtime = LiveChatRuntime(identity, policy, ledger, "offline-key", "a" * 32)
            legacy = policy.model_copy(
                update={
                    "schema_version": 1,
                    "cache_write_microusd_per_million": None,
                }
            )
            with self.assertRaisesRegex(ValueError, "schema-2 spending policy"):
                LiveChatRuntime(identity, legacy, ledger, "offline-key", "a" * 32)
            transport = CountedAnswerTransport()
            config = conversation_config(
                (Turn(role="user", blocks=(TextBlock(text="Question"),)),),
                live_chat=identity,
            )
            with patch(
                "mos_eisley.conversation_live_chat.EphemeralOpenAITransport",
                return_value=transport,
            ):
                result = await runtime.run(config, 0)
            self.assertEqual(result.final_text, "Live answer")
            self.assertEqual(transport.calls, 1)
            self.assertEqual(ledger.snapshot().charged_microusd, 15)
            attempt = root / ("a" * 32) / "attempt-0000"
            self.assertTrue((attempt / "spend-reservation.json").is_file())
            self.assertTrue((attempt / "spend-receipt.json").is_file())

    async def test_live_followups_resume_and_identity(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            identity = LiveChatIdentity(
                model="gpt-5.6-luna",
                effort="medium",
                max_output_tokens=128,
                spend_policy_sha256="1" * 64,
                spend_ledger_id="2" * 64,
                artifacts_root=str(root),
            )
            cassette = demo_cassette()
            requests: list[ModelRequest] = []
            attempts: list[int] = []

            async def run_live(config: AgentConfig, attempt: int) -> AgentResult:
                attempts.append(attempt)
                return await run_agent(
                    config,
                    openai_registry(),
                    AnswerClient(requests),
                    NoToolsDispatcher(),
                )

            state = ConversationController.fresh(root, cassette, live_chat=identity)
            controller = ConversationController(
                state, cassette, lambda _: None, run_live_chat=run_live
            )
            with create_pipe_input() as terminal_input:
                ui = ConversationTUI(
                    controller, input=terminal_input, output=DummyOutput()
                )
                self.assertIn("openai/gpt-5.6-luna", ui.status())
                self.assertIn("live OpenAI chat", ui.header())
            for text in ("First", "Second", "Third"):
                controller.submit(text)
                self.assertTrue(await controller.step())
            self.assertEqual(attempts, [0, 1, 2])
            self.assertEqual(len(requests), 3)
            self.assertEqual(requests[2].provider, "openai")
            self.assertEqual(requests[2].tools, ())
            self.assertEqual(
                [turn.role for turn in requests[2].turns],
                ["user", "assistant", "user", "assistant", "user"],
            )
            saved = ConversationState.model_validate_json(
                controller.state.model_dump_json()
            )
            self.assertEqual(saved.mode, "openai_live_conversation")
            self.assertEqual(saved.live_chat, identity)
            with self.assertRaisesRegex(ValueError, "explicit live runner"):
                ConversationController(saved, cassette, lambda _: None)
            resumed = ConversationController(
                saved, cassette, lambda _: None, run_live_chat=run_live
            )
            self.assertEqual(resumed.state.exchanges_consumed, 3)
            storage = root / "sqlite-sessions"
            sqlite_state = ConversationController.fresh(
                root, cassette, live_chat=identity
            )
            with SQLiteConversationStore(
                storage, sqlite_state.session_id, root
            ) as store:
                store.save(sqlite_state)
            inspection = inspect_sqlite_resume(storage, sqlite_state.session_id, root)
            self.assertEqual(inspection.header.mode, "openai_live_conversation")
            self.assertEqual(inspection.header.live_chat, identity)

    async def test_cancelled_live_turn_is_not_replayed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            identity = LiveChatIdentity(
                model="gpt-5.6-luna",
                effort="medium",
                max_output_tokens=128,
                spend_policy_sha256="1" * 64,
                spend_ledger_id="2" * 64,
                artifacts_root=str(root),
            )
            cassette = demo_cassette()
            started = asyncio.Event()

            async def waiting(_config: AgentConfig, _attempt: int) -> AgentResult:
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

            controller = ConversationController(
                ConversationController.fresh(root, cassette, live_chat=identity),
                cassette,
                lambda _: None,
                run_live_chat=waiting,
            )
            controller.submit("Question")
            work = asyncio.create_task(controller.step())
            await started.wait()
            work.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await work
            self.assertEqual(controller.state.entries[0].status, "cancelled")
            self.assertEqual(controller.state.exchanges_consumed, 1)
            self.assertFalse(await controller.step())
