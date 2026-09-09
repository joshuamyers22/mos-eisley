"""Whole-run spending, cancellation, local admission, and synthetic live CLI."""

import asyncio
import copy
import io
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from pydantic import JsonValue

from mos_eisley.analysis.artifacts import load_artifact
from mos_eisley.analysis.controller import AnalysisConfig
from mos_eisley.analysis.demo import fixture_config
from mos_eisley.analysis.evidence import ContextMode
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.analysis.spending import AnalysisSpending
from mos_eisley.cli import main
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.spend_ledger import SpendLedger


def config(**changes: object) -> AnalysisConfig:
    return AnalysisConfig.model_validate(
        {
            "provider": "openai",
            "model": "gpt-5.6-sol",
            "account": "synthetic-account",
            "question": "What is the total?",
            "max_output_tokens": 100,
            "max_total_input_tokens": 1000,
            "max_total_output_tokens": 300,
            **changes,
        }
    )


def policy(**changes: object) -> SpendPolicy:
    return SpendPolicy.model_validate(
        {
            "schema_version": 2,
            "model": "gpt-5.6-sol",
            "pricing_source": "synthetic fixture rates, not for live use",
            "valid_from": datetime.now(UTC) - timedelta(hours=1),
            "valid_until": datetime.now(UTC) + timedelta(hours=1),
            "input_microusd_per_million": 1000000,
            "cache_write_microusd_per_million": 1250000,
            "output_microusd_per_million": 2000000,
            "max_cost_microusd": 100000,
            **changes,
        }
    )


def request() -> dict[str, JsonValue]:
    return {
        "model": "gpt-5.6-sol",
        "input": [{"role": "user", "content": "synthetic"}],
        "tools": [{"type": "function", "name": "run_metric"}],
        "max_output_tokens": 100,
        "store": False,
        "truncation": "disabled",
    }


class FakeTransport:
    def __init__(self) -> None:
        self.counts = self.calls = 0
        self.tokens = 10
        self.error: BaseException | None = None
        self.response: dict[str, JsonValue] = {
            "model": "gpt-5.6-sol",
            "service_tier": "default",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "input_tokens_details": {"cache_write_tokens": 2},
            },
        }

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        self.counts += 1
        return self.tokens

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.response)


class SpendingTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 1000000)

    def spending(self, settings: AnalysisConfig | None = None) -> AnalysisSpending:
        return AnalysisSpending(
            settings or config(),
            fixture_config(),
            policy(),
            self.ledger,
            self.ledger.policy.ledger_id,
            100000,
        )

    async def test_whole_run_reserves_then_settles_sum(self) -> None:
        spending = self.spending()
        spending.reserve()
        self.assertEqual(self.ledger.snapshot().charged_microusd, spending.reserved)
        fake = FakeTransport()
        transport = spending.transport(fake)
        await transport.create_response(request())
        await transport.create_response(request())
        receipt = spending.finish()
        self.assertEqual(receipt.retained_microusd, 102)
        self.assertEqual(receipt.input_tokens, 20)
        self.assertEqual(self.ledger.snapshot().unresolved_entries, 0)
        self.assertEqual(list(self.root.iterdir()), [self.ledger.path])
        with self.assertRaises(ProviderError):
            await transport.create_response(request())
        with self.assertRaises(ValueError):
            spending.reserve()
        with self.assertRaises(ValueError):
            spending.finish()

    async def test_cancellation_and_unknown_usage_retain_whole_reservation(
        self,
    ) -> None:
        for error in (
            asyncio.CancelledError(),
            RuntimeError("secret provider text"),
            None,
        ):
            with self.subTest(error=type(error)):
                spending = self.spending(config(max_active_runs=4))
                spending.reserve()
                fake = FakeTransport()
                fake.error = error
                fake.response = {}
                with self.assertRaises(
                    (asyncio.CancelledError, RuntimeError, ProviderError)
                ):
                    await spending.transport(fake).create_response(request())
                receipt = spending.finish()
                self.assertEqual(receipt.status, "uncertain")
                self.assertEqual(receipt.retained_microusd, spending.reserved)
                self.assertEqual(fake.calls, 1)

    async def test_invalid_usage_uncertain_and_pricing_violation_blocks_ledger(
        self,
    ) -> None:
        fake = FakeTransport()
        fake.response["usage"] = {"input_tokens": True, "output_tokens": 1}
        spending = self.spending()
        spending.reserve()
        with self.assertRaises(ProviderError):
            await spending.transport(fake).create_response(request())
        self.assertEqual(spending.finish().status, "uncertain")
        next_run = self.spending(config(max_active_runs=2))
        next_run.reserve()
        fake = FakeTransport()
        fake.response["model"] = "unexpected-model"
        with self.assertRaises(ProviderError):
            await next_run.transport(fake).create_response(request())
        self.assertEqual(next_run.finish().status, "violation")
        self.assertTrue(self.ledger.snapshot().blocked)
        with self.assertRaises(ValueError):
            self.spending(config(max_active_runs=4)).reserve()

    async def test_aggregate_input_output_and_turn_limits(self) -> None:
        for settings in (
            config(max_total_input_tokens=15),
            config(max_total_output_tokens=110),
            config(max_model_turns=1),
        ):
            spending = self.spending(settings)
            spending.reserve()
            fake = FakeTransport()
            transport = spending.transport(fake)
            await transport.create_response(request())
            with self.assertRaises(ProviderError):
                await transport.create_response(request())
            self.assertEqual(fake.calls, 1)
            self.assertEqual(spending.finish().status, "settled")

    async def test_scope_rejections_precede_transfer(self) -> None:
        for changes in (
            {"tools": [{"type": "web_search"}]},
            {"model": "wrong-model"},
            {"tools": [{"type": "function", "name": "write_parquet"}]},
            {"store": True},
            {"truncation": "auto"},
            {"stream": True},
            {"service_tier": "priority"},
            {"max_output_tokens": 101},
        ):
            spending = self.spending()
            spending.reserve()
            fake = FakeTransport()
            with self.assertRaises(ProviderError):
                await spending.transport(fake).create_response(
                    cast(dict[str, JsonValue], {**request(), **changes})
                )
            self.assertEqual((fake.counts, fake.calls), (0, 0))
            self.assertEqual(spending.finish().retained_microusd, 0)

    async def test_tool_definitions_cannot_change_between_turns(self) -> None:
        spending = self.spending()
        spending.reserve()
        fake = FakeTransport()
        transport = spending.transport(fake)
        await transport.create_response(request())
        changed = request()
        changed["tools"] = [{"type": "function", "name": "get_semantic_context"}]
        with self.assertRaises(ProviderError):
            await transport.create_response(changed)
        self.assertEqual(fake.calls, 1)
        spending.finish()

    async def test_concurrent_transport_and_finish_rejected_during_dispatch(
        self,
    ) -> None:
        started, release = asyncio.Event(), asyncio.Event()

        class SlowTransport(FakeTransport):
            async def create_response(
                self, payload: dict[str, JsonValue]
            ) -> dict[str, JsonValue]:
                started.set()
                await release.wait()
                return await super().create_response(payload)

        spending = self.spending()
        spending.reserve()
        fake = SlowTransport()
        transport = spending.transport(fake)
        task = asyncio.create_task(transport.create_response(request()))
        await started.wait()
        with self.assertRaises(ProviderError):
            await transport.create_response(request())
        with self.assertRaises(ValueError):
            spending.finish()
        release.set()
        await task
        spending.finish()
        self.assertEqual(fake.calls, 1)

    def test_admission_is_atomic_across_ledger_instances(self) -> None:
        def reserve(_: int) -> bool:
            ledger = SpendLedger(self.ledger.path)
            spending = AnalysisSpending(
                config(),
                fixture_config(),
                policy(),
                ledger,
                ledger.policy.ledger_id,
                100000,
            )
            try:
                spending.reserve()
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(reserve, range(2))), [False, True])
        # A simulated process crash leaves the held entry and its slot intact.
        with self.assertRaises(ValueError):
            self.spending().reserve()
        self.assertEqual(self.ledger.snapshot().unresolved_entries, 1)

    def test_admission_validates_identity_rates_acceptance_and_private_ledger(
        self,
    ) -> None:
        for pricing, ledger_id, accepted in (
            (policy(), "b" * 64, 100000),
            (policy(), self.ledger.policy.ledger_id, 1),
            (
                policy(valid_until=datetime.now(UTC) + timedelta(seconds=1)),
                self.ledger.policy.ledger_id,
                100000,
            ),
            (policy(model="other-model"), self.ledger.policy.ledger_id, 100000),
            (policy(max_cost_microusd=1), self.ledger.policy.ledger_id, 100000),
        ):
            with self.assertRaises(ValueError):
                AnalysisSpending(
                    config(),
                    fixture_config(),
                    pricing,
                    self.ledger,
                    ledger_id,
                    accepted,
                )
        self.ledger.path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.spending()
        self.assertEqual(self.ledger.snapshot().entries, 0)


class ConversationalTransport(FakeTransport):
    def __init__(self, context_mode: ContextMode = "promoted") -> None:
        super().__init__()
        self.context_mode = context_mode

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        response = await super().create_response(payload)
        if self.calls == 1:
            output: list[JsonValue] = [
                {
                    "type": "function_call",
                    "id": "fc-1",
                    "call_id": "metric-call",
                    "name": "query_parquet"
                    if self.context_mode == "raw"
                    else "run_metric",
                    "arguments": json.dumps(
                        {
                            "arguments_json": json.dumps(
                                {
                                    "name": "fixture_total",
                                    "revision": REVISION,
                                }
                                if self.context_mode == "promoted"
                                else {
                                    "root": "synthetic",
                                    "paths": ["items.parquet"],
                                    "sql": "SELECT SUM(quantity) AS total FROM data",
                                }
                            )
                        }
                    ),
                }
            ]
        else:
            output = [
                {
                    "type": "message",
                    "id": "message-1",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "status": "answer",
                                    "text": "Synthetic total: 42.",
                                    "claims": [
                                        {
                                            "result_id": "result-0002",
                                            "row": 0,
                                            "column": "total",
                                            "value": 42,
                                        }
                                    ],
                                    "result_ids": ["result-0002"],
                                }
                            ),
                        }
                    ],
                }
            ]
        response.update({"id": "response-1", "status": "completed", "output": output})
        response["usage"] = {
            "input_tokens": 10,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
        return response


class LiveCLITests(TestCase):
    def test_synthetic_live_path_and_missing_key_settlement(self) -> None:
        cases: tuple[tuple[str, str, ContextMode], ...] = (
            ("synthetic-not-a-real-key", "memory", "promoted"),
            ("synthetic-not-a-real-key", "private", "promoted"),
            ("", "memory", "promoted"),
            ("synthetic-not-a-real-key", "private", "raw"),
        )
        for key, retention, mode in cases:
            with TemporaryDirectory() as directory:
                root = Path(directory)
                ledger = SpendLedger.create(root / "ledger.sqlite", 1000000)
                for name, value in (
                    ("config", config(retention=retention, context_mode=mode)),
                    ("mcp", fixture_config(mode)),
                    ("policy", policy()),
                ):
                    (root / name).write_text(value.model_dump_json())
                arguments = [
                    "analysis-run",
                    "--config",
                    str(root / "config"),
                    "--mcp-config",
                    str(root / "mcp"),
                    "--spend-policy",
                    str(root / "policy"),
                    "--spend-ledger",
                    str(ledger.path),
                    "--ledger-id",
                    ledger.policy.ledger_id,
                    "--accept-max-cost-microusd",
                    "100000",
                    "--allow-data-transfer",
                ]
                if retention == "private":
                    arguments.extend(
                        ["--allow-result-retention", "--result-root", str(root)]
                    )
                fake = ConversationalTransport(mode)
                out, err = io.StringIO(), io.StringIO()
                with (
                    patch.dict("os.environ", {"OPENAI_API_KEY": key}),
                    patch(
                        "mos_eisley.analysis.cli.EphemeralOpenAITransport",
                        return_value=fake,
                    ),
                    redirect_stdout(out),
                    redirect_stderr(err),
                ):
                    code = main(arguments)
                self.assertEqual(code, 0 if key else 2, err.getvalue())
                self.assertEqual(ledger.snapshot().unresolved_entries, 0)
                self.assertEqual(fake.calls, 2 if key else 0)
                self.assertEqual(
                    len(list(root.iterdir())), 5 if retention == "private" else 4
                )
                event = json.loads(out.getvalue() if key else err.getvalue())
                self.assertEqual(event["spend_receipt"]["status"], "settled")
                if retention == "private":
                    _, artifact = load_artifact(Path(event["artifact_path"]))
                    self.assertEqual(artifact.result.answer.claims[0].value, 42)
                    self.assertIsNotNone(artifact.spend_receipt)
                    self.assertEqual(artifact.result.context_mode, mode)
                self.assertNotIn(
                    "synthetic-not-a-real-key", out.getvalue() + err.getvalue()
                )
