"""Raw-data control arm isolation, evidence compatibility and offline comparison."""

import io
import json
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase

from test_analysis import StubDispatcher, config
from test_analysis_evidence import artifact as legacy_artifact

from mos_eisley.analysis.artifacts import (
    AnalysisArtifact,
    export_csv,
    load_artifact,
    save_artifact,
    verify_export,
)
from mos_eisley.analysis.controller import (
    AnalysisFailure,
    AnalysisResult,
    AnalysisTools,
    analysis_mcp_config,
    analysis_system,
    run_analysis,
    run_identity,
)
from mos_eisley.analysis.demo import AnalysisFixtureClient, fixture_config, run_demo
from mos_eisley.analysis.evaluation import (
    EvaluationArm,
    EvaluationCase,
    EvaluationInputs,
    EvaluationSuite,
    ExpectedCell,
    ExpectedOutcome,
    Observation,
    evaluate,
    public_plan,
)
from mos_eisley.analysis.evidence import RAW_TOOLS, ContextMode, checked_answer
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse, ToolCallBlock
from mos_eisley.core.registry import fixture_registry
from mos_eisley.tools.mcp import MCPDispatcher


class RawAnalysisTests(IsolatedAsyncioTestCase):
    async def test_raw_model_requests_exclude_catalog_and_results_keep_sql(
        self,
    ) -> None:
        requests: list[ModelRequest] = []

        class RecordingClient(AnalysisFixtureClient):
            async def complete(self, request: ModelRequest) -> ModelResponse:
                requests.append(request)
                return await super().complete(request)

        result = await run_analysis(
            config(context_mode="raw"),
            fixture_config("raw"),
            fixture_registry(),
            RecordingClient(context_mode="raw"),
        )
        for request in requests:
            self.assertLessEqual({tool.name for tool in request.tools}, RAW_TOOLS)
            encoded = canonical_bytes(request)
            self.assertNotIn(REVISION.encode(), encoded)
            self.assertNotIn(b"fixture_total", encoded)
        self.assertEqual(result.context_mode, "raw")
        self.assertIsNone(result.semantic_revision)
        self.assertEqual(result.answer.claims[0].value, 42)
        self.assertEqual(
            [e.tool for e in result.evidence], ["list_sources", "query_parquet"]
        )
        self.assertEqual(
            result.sql_trail[0].submitted_sql, "SELECT SUM(quantity) AS total FROM data"
        )
        self.assertEqual(result.tool_calls, 2)
        self.assertEqual(result.model_turns, 2)
        self.assertFalse(result.source_snapshot_verified)

    async def test_forbidden_attempts_stop_before_dispatch_and_count(self) -> None:
        dispatcher = StubDispatcher({})
        tools = AnalysisTools(
            cast(MCPDispatcher, dispatcher), config(context_mode="raw")
        )
        for name in (
            "get_semantic_context",
            "list_metrics",
            "run_metric",
            "write_parquet",
            "custom_summary",
        ):
            response = await tools.dispatch(ToolCallBlock(id=name, name=name, args={}))
            self.assertTrue(response.is_error)
        self.assertEqual(dispatcher.calls, 0)
        self.assertEqual(tools.calls, 5)
        self.assertEqual(len(tools.trace), 5)
        self.assertEqual(tools.evidence, [])
        injected = await run_demo("injection", context_mode="raw")
        self.assertEqual(injected.answer.status, "unavailable")
        self.assertEqual(injected.tool_trace[-1].outcome, "error")
        self.assertIsNone(injected.semantic_revision)

    async def test_raw_budgets_and_nonanswers(self) -> None:
        for changes in (
            {"max_model_turns": 1},
            {"max_tool_calls": 1},
            {"max_total_input_bytes": 1024},
        ):
            with self.assertRaises(AnalysisFailure):
                await run_analysis(
                    config(context_mode="raw", **changes),
                    fixture_config("raw"),
                    fixture_registry(),
                    AnalysisFixtureClient(context_mode="raw"),
                )
        for scenario in ("clarify", "unavailable"):
            result = await run_demo(scenario, context_mode="raw")
            self.assertEqual(result.answer.status, scenario)
            self.assertEqual(result.tool_calls, 1)

    async def test_raw_bundle_roundtrip_export_and_context_tampering(self) -> None:
        result = await run_demo(retention="private", context_mode="raw")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = save_artifact(root, AnalysisArtifact(result=result), 3600)
            _, recorded = load_artifact(bundle)
            self.assertEqual(recorded.result, result)
            exported = export_csv(bundle, "result-0002", root)
            verify_export(exported, bundle)
        for changes in ({"context_mode": "promoted"}, {"semantic_revision": REVISION}):
            with self.assertRaises(ValueError):
                AnalysisResult.model_validate_json(
                    result.model_copy(update=changes).model_dump_json()
                )
        # Metadata cannot become answer cells, even if shaped as a table.
        metadata = result.tool_trace[1].model_copy(
            update={
                "call": result.tool_trace[1].call.model_copy(
                    update={"name": "describe_parquet"}
                ),
            }
        )
        with self.assertRaises(ValueError):
            checked_answer(result.answer, (metadata,))

    async def test_promoted_and_raw_artifacts_score_in_one_suite(self) -> None:
        reviewed_at = datetime.now(UTC)
        modes: tuple[ContextMode, ...] = ("promoted", "raw")
        results = [
            await run_demo(retention="private", context_mode=mode) for mode in modes
        ]
        arms = tuple(
            EvaluationArm(
                id=result.context_mode,
                provider="fixture",
                model=result.model,
                run_identity=result.run_identity,
                context_mode=result.context_mode,
                semantic_revision=result.semantic_revision,
            )
            for result in results
            if result.run_identity is not None
        )
        expectations = tuple(
            ExpectedOutcome(
                arm_id=result.context_mode,
                status="answer",
                cells=(
                    ExpectedCell(
                        tool="run_metric"
                        if result.context_mode == "promoted"
                        else "query_parquet",
                        arguments=result.sql_trail[0].arguments,
                        submitted_sql=cast(str, result.sql_trail[0].submitted_sql),
                        source_metadata={
                            "backend": "fixture",
                            "source": "synthetic",
                            "units": "items",
                        }
                        if result.context_mode == "promoted"
                        else {},
                        reviewed_units="items",
                        row=0,
                        column="total",
                        value=42,
                    ),
                ),
            )
            for result in results
        )
        suite = EvaluationSuite(
            id="comparison-fixture",
            reviewer="synthetic-reviewer",
            reviewed_at=reviewed_at,
            arms=arms,
            cases=(
                EvaluationCase(
                    id="total",
                    family="totals",
                    split="development",
                    question=results[0].question,
                    fixture_sha256="b" * 64,
                    expectations=expectations,
                ),
            ),
        )
        impossible_case = suite.cases[0].model_copy(
            update={
                "expectations": (
                    expectations[0],
                    expectations[0].model_copy(update={"arm_id": "raw"}),
                ),
            }
        )
        with self.assertRaises(ValueError):
            EvaluationSuite.model_validate_json(
                suite.model_copy(update={"cases": (impossible_case,)}).model_dump_json()
            )
        with TemporaryDirectory() as directory:
            observations: list[Observation] = []
            for result in results:
                bundle = save_artifact(
                    Path(directory), AnalysisArtifact(result=result), 3600
                )
                manifest, _ = load_artifact(bundle)
                observations.append(
                    Observation(
                        case_id="total",
                        arm_id=result.context_mode,
                        artifact_path=str(bundle),
                        artifact_sha256=manifest.payload_sha256,
                    )
                )
            report = evaluate(
                suite,
                EvaluationInputs(
                    suite_sha256=digest(canonical_bytes(suite)),
                    split="development",
                    observations=tuple(observations),
                ),
            )
            self.assertEqual(
                [case.outcome for case in report.cases], ["match", "match"]
            )
            self.assertFalse(report.controlled_comparison_verified)
            self.assertFalse(report.promotion_ready)
            swapped = tuple(
                item.model_copy(
                    update={
                        "arm_id": "raw" if item.arm_id == "promoted" else "promoted"
                    }
                )
                for item in observations
            )
            wrong = evaluate(
                suite,
                EvaluationInputs(
                    suite_sha256=digest(canonical_bytes(suite)),
                    split="development",
                    observations=swapped,
                ),
            )
            self.assertTrue(
                all("context_mode_mismatch" in case.reasons for case in wrong.cases)
            )
        tasks = json.dumps(public_plan(suite, "development"))
        self.assertNotIn("SELECT", tasks)
        self.assertIn('"context_mode": "raw"', tasks)


class RawContractTests(TestCase):
    def test_raw_profile_requires_discovery_and_rejects_nonraw_tools(self) -> None:
        raw = fixture_config("raw")
        self.assertEqual(analysis_mcp_config(raw, "raw").schema_mode, "json_object")
        variants: tuple[dict[str, object], ...] = (
            {"allow_writes": True},
            {"tools": {"list_sources": "write"}},
            {"tools": {"query_parquet": "read"}},
        )
        for update in variants:
            with self.assertRaises(ValueError):
                analysis_mcp_config(raw.model_copy(update=update), "raw")
        for tool in (
            "get_semantic_context",
            "list_metrics",
            "run_metric",
            "execute_postgres",
            "custom_read",
        ):
            with self.assertRaises(ValueError):
                analysis_mcp_config(
                    raw.model_copy(update={"tools": {**raw.tools, tool: "read"}}), "raw"
                )
        with self.assertRaises(ValueError):
            analysis_mcp_config(
                raw
            )  # No silent fallback when promoted context is missing.

    def test_legacy_canonical_fields_and_mode_identity(self) -> None:
        legacy = legacy_artifact()
        self.assertNotIn(b'"context_mode"', canonical_bytes(legacy))
        old = json.loads(config().model_dump_json())
        self.assertNotIn("context_mode", old)
        self.assertNotEqual(
            run_identity(config(), ()), run_identity(config(context_mode="raw"), ())
        )
        self.assertNotEqual(analysis_system("raw"), analysis_system("promoted"))
        for mode, revision in (("raw", REVISION), ("promoted", None)):
            with self.assertRaises(ValueError):
                EvaluationArm.model_validate(
                    {
                        "id": "invalid",
                        "provider": "fixture",
                        "model": "tool-reviewer-v1",
                        "run_identity": run_identity(config(), ()),
                        "context_mode": mode,
                        "semantic_revision": revision,
                    }
                )

    def test_raw_cli_demo(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["analysis-demo", "--context-mode", "raw"]), 0)
        event = json.loads(out.getvalue())
        self.assertEqual(event["context_mode"], "raw")
        self.assertIsNone(event["semantic_revision"])
        self.assertEqual(event["answer"]["claims"][0]["value"], 42)
