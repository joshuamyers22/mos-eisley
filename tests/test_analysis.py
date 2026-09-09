"""Real MCP fixture conversations and adversarial analytical boundary checks."""

import asyncio
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from mos_eisley.analysis.controller import (
    AnalysisAnswer,
    AnalysisConfig,
    AnalysisFailure,
    AnalysisTools,
    analysis_mcp_config,
    run_analysis,
)
from mos_eisley.analysis.demo import AnalysisFixtureClient, fixture_config, run_demo
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.cli import main
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    ToolCallBlock,
    ToolResultBlock,
)
from mos_eisley.core.registry import fixture_registry
from mos_eisley.tools.mcp import MCPDispatcher


def config(**changes: object) -> AnalysisConfig:
    return AnalysisConfig.model_validate(
        {
            "provider": "fixture",
            "model": "tool-reviewer-v1",
            "account": "fixture",
            "question": "What is the synthetic total?",
            **changes,
        }
    )


class StubDispatcher:
    def __init__(self, source: object, *, error: bool = False) -> None:
        self.source, self.error, self.calls = source, error, 0

    async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
        self.calls += 1
        return ToolResultBlock(
            call_id=call.id,
            name=call.name,
            is_error=self.error,
            content=json.dumps({"structured_content": self.source}),
        )


def call(name: str = "run_metric", revision: str = REVISION) -> ToolCallBlock:
    return ToolCallBlock(
        id="test-call",
        name=name,
        args={
            "arguments_json": json.dumps(
                {"name": "fixture_total", "revision": revision}
            )
        },
    )


class AnalysisTests(IsolatedAsyncioTestCase):
    async def test_real_mcp_answer_clarify_unavailable(self) -> None:
        for scenario in ("answer", "clarify", "unavailable"):
            with self.subTest(scenario=scenario):
                result = await run_demo(scenario)
                self.assertEqual(result.answer.status, scenario)
                self.assertEqual(result.semantic_revision, REVISION)
                self.assertFalse(result.claims_independently_verified)
                self.assertFalse(result.source_snapshot_verified)
                self.assertEqual(result.tool_calls, 2 if scenario == "answer" else 1)

    async def test_source_injection_cannot_dispatch_a_write(self) -> None:
        result = await run_demo("injection")
        self.assertEqual(result.answer.status, "unavailable")
        self.assertEqual(
            [item.tool for item in result.evidence],
            ["get_semantic_context", "run_metric"],
        )

    async def test_budgets_stop_conversation(self) -> None:
        for limits in (
            {"max_model_turns": 1},
            {"max_tool_calls": 1},
            {"max_total_input_bytes": 1024},
            {"max_total_output_bytes": 1024},
        ):
            with self.subTest(limits=limits), self.assertRaises(AnalysisFailure):
                await run_analysis(
                    config(**limits),
                    fixture_config(),
                    fixture_registry(),
                    AnalysisFixtureClient(),
                )

    async def test_deadline_cancels_waiting_model(self) -> None:
        cancelled = asyncio.Event()

        class SlowClient:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                try:
                    await asyncio.sleep(30)
                    raise AssertionError("deadline did not fire")
                finally:
                    cancelled.set()

        with self.assertRaises((AnalysisFailure, TimeoutError)):
            await run_analysis(
                config(run_timeout_seconds=3.0),
                fixture_config(),
                fixture_registry(),
                SlowClient(),
            )
        self.assertTrue(cancelled.is_set())

    async def test_pending_tool_limit_precedes_dispatch(self) -> None:
        class ManyCalls(AnalysisFixtureClient):
            async def complete(self, request: ModelRequest) -> ModelResponse:
                response = await super().complete(request)
                block = call().model_copy(update={"id": "second-call"})
                return response.model_copy(
                    update={
                        "turn": response.turn.model_copy(
                            update={"blocks": (*response.turn.blocks, block)}
                        )
                    }
                )

        with self.assertRaises(AnalysisFailure):
            await run_analysis(
                config(max_pending_tool_calls=1),
                fixture_config(),
                fixture_registry(),
                ManyCalls(),
            )

    async def test_citations_must_reference_complete_non_context_result(self) -> None:
        class WrongCitation(AnalysisFixtureClient):
            async def complete(self, request: ModelRequest) -> ModelResponse:
                response = await super().complete(request)
                if response.stop_reason == "end_turn":
                    return ModelResponse.model_validate_json(
                        response.model_dump_json().replace("result-0002", "result-0001")
                    )
                return response

        with self.assertRaises(AnalysisFailure):
            await run_analysis(
                config(), fixture_config(), fixture_registry(), WrongCitation()
            )

    async def test_result_contract_and_semantic_revision(self) -> None:
        for source in (
            None,
            {"truncated": "false"},
            {"revision": "b" * 64},
            {"revision": REVISION, "rows": ["x" * 5000]},
        ):
            dispatcher = StubDispatcher(source)
            tools = AnalysisTools(cast(MCPDispatcher, dispatcher), config())
            tools.revision = REVISION
            with (
                self.subTest(source_type=type(source)),
                self.assertRaises(AnalysisFailure),
            ):
                await tools.dispatch(call())
        dispatcher = StubDispatcher({"revision": REVISION, "truncated": True})
        tools = AnalysisTools(cast(MCPDispatcher, dispatcher), config())
        tools.revision = REVISION
        self.assertTrue((await tools.dispatch(call())).is_error)
        self.assertEqual(tools.evidence, [])

    async def test_metric_revision_rejected_before_mcp(self) -> None:
        dispatcher = StubDispatcher({})
        tools = AnalysisTools(cast(MCPDispatcher, dispatcher), config())
        tools.revision = REVISION
        self.assertTrue((await tools.dispatch(call(revision="b" * 64))).is_error)
        self.assertEqual(dispatcher.calls, 0)

    async def test_context_unavailable_invalid_and_drift(self) -> None:
        for source in ({}, {"revision": "x" * 64}, {"revision": "b" * 64}):
            tools = AnalysisTools(cast(MCPDispatcher, StubDispatcher(source)), config())
            tools.revision = REVISION
            with self.assertRaises(AnalysisFailure):
                await tools.dispatch(call("get_semantic_context"))
        tools = AnalysisTools(
            cast(MCPDispatcher, StubDispatcher({}, error=True)), config()
        )
        self.assertTrue((await tools.dispatch(call("get_semantic_context"))).is_error)

    async def test_tool_budget_counts_rejected_attempts(self) -> None:
        tools = AnalysisTools(
            cast(MCPDispatcher, StubDispatcher({})), config(max_tool_calls=1)
        )
        await tools.dispatch(call(revision="wrong"))
        with self.assertRaises(AnalysisFailure):
            await tools.dispatch(call())


class AnalysisCLITests(TestCase):
    def test_profile_cannot_enable_mutations(self) -> None:
        for update in (
            {"allow_writes": True},
            {"tools": {"run_metric": "write"}},
            {"tools": {"write_parquet": "read", "get_semantic_context": "read"}},
            {"tools": {"run_metric": "read"}},
        ):
            with self.assertRaises(ValueError):
                analysis_mcp_config(fixture_config().model_copy(update=update))
        self.assertEqual(
            analysis_mcp_config(fixture_config()).schema_mode, "json_object"
        )

    def test_duplicate_citations_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisAnswer(status="answer", text="42", result_ids=("a", "a"))

    def test_demo_cli_no_content_artifacts(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch("os.getcwd", return_value=directory),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["analysis-demo"]), 0)
            self.assertEqual(json.loads(out.getvalue())["answer"]["status"], "answer")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_live_refuses_before_config_or_credentials_without_transfer_opt_in(
        self,
    ) -> None:
        err = io.StringIO()
        with (
            redirect_stderr(err),
            patch("mos_eisley.analysis.cli.read_bounded") as read,
        ):
            code = main(
                [
                    "analysis-run",
                    "--config",
                    "missing",
                    "--mcp-config",
                    "missing",
                    "--spend-policy",
                    "missing",
                    "--spend-ledger",
                    "missing",
                    "--ledger-id",
                    "x",
                    "--accept-max-cost-microusd",
                    "1",
                ]
            )
        self.assertEqual(code, 2)
        read.assert_not_called()
        self.assertEqual(json.loads(err.getvalue()), {"type": "analysis.failed"})
