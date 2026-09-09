"""Opt-in cross-repository checks against data-mcp and disposable sources."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest import IsolatedAsyncioTestCase, skipUnless
from uuid import uuid4

from mos_eisley.analysis.controller import AnalysisConfig, run_analysis
from mos_eisley.analysis.demo import AnalysisFixtureClient
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.core.protocol import ModelRequest, ModelResponse, ToolCallBlock
from mos_eisley.core.registry import fixture_registry
from mos_eisley.tools.mcp import MCPConfig, MCPDispatcher, connect_mcp

DATA_PYTHON = os.environ.get("DATA_MCP_TEST_PYTHON", "")


async def invoke(
    dispatcher: MCPDispatcher, tool_name: str, **args: Any
) -> dict[str, Any]:
    result = await dispatcher.dispatch(
        ToolCallBlock(id=uuid4().hex, name=tool_name, args=args)
    )
    if result.is_error:
        raise AssertionError(result.content)
    return json.loads(result.content)["structured_content"]


@skipUnless(DATA_PYTHON, "Set DATA_MCP_TEST_PYTHON to data-mcp's installed Python")
class DataMCPIntegrationTests(IsolatedAsyncioTestCase):
    async def test_parquet_writes_and_analysis_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            temporary = str(root)
            server_config = root / "data.toml"
            server_config.write_text(f"[parquet.raw]\npath = {json.dumps(temporary)}\n")
            cfg = MCPConfig(
                command=DATA_PYTHON,
                cwd=temporary,
                args=("-m", "data_mcp.cli", "--config", str(server_config)),
                tools={"write_parquet": "write", "query_parquet": "read"},
                allow_writes=True,
            )
            async with connect_mcp(cfg) as dispatcher:
                for mode, rows in (("create", '[{"id":1}]'), ("append", '[{"id":2}]')):
                    await invoke(
                        dispatcher,
                        "write_parquet",
                        root="raw",
                        path="items.parquet",
                        rows_json=rows,
                        mode=mode,
                    )
                result = await invoke(
                    dispatcher,
                    "query_parquet",
                    root="raw",
                    paths=["items.parquet"],
                    sql="SELECT id FROM data ORDER BY id",
                )
                self.assertEqual(result["rows"], [[1], [2]])
                await invoke(
                    dispatcher,
                    "write_parquet",
                    root="raw",
                    path="items.parquet",
                    rows_json='[{"id":3}]',
                    mode="replace",
                )
            ontology = root / "ontology.toml"
            ontology.write_text("""schema_version = 1
[metrics.row_count]
backend = "parquet"
source = "raw"
paths = ["items.parquet"]
description = "Synthetic test count"
grain = "All fixture rows"
units = "rows"
timezone = "UTC"
owner = "fixture"
reviewed_on = 2026-09-09
expected_columns = ["row_count"]
sql = "SELECT COUNT(*) AS row_count FROM data"
""")
            server_config.write_text(
                'access_mode = "analysis"\n'
                f"ontology_file = {json.dumps(str(ontology))}\n"
                f"[parquet.raw]\npath = {json.dumps(temporary)}\n"
            )
            analysis = cfg.model_copy(
                update={
                    "allow_writes": False,
                    "tools": {
                        "get_semantic_context": "read",
                        "list_metrics": "read",
                        "run_metric": "read",
                    },
                }
            )
            async with connect_mcp(analysis) as dispatcher:
                context = await invoke(dispatcher, "get_semantic_context")
                metrics = await invoke(dispatcher, "list_metrics")
                self.assertIn("metrics", metrics)
                result = await invoke(
                    dispatcher,
                    "run_metric",
                    name="row_count",
                    revision=context["revision"],
                )
                self.assertEqual(result["rows"], [[1]])
                denied = await dispatcher.dispatch(
                    ToolCallBlock(id="deny", name="write_parquet", args={})
                )
                self.assertTrue(denied.is_error)

            class MetricClient(AnalysisFixtureClient):
                async def complete(self, request: ModelRequest) -> ModelResponse:
                    response = await super().complete(request)
                    return ModelResponse.model_validate_json(
                        response.model_dump_json()
                        .replace(REVISION, context["revision"])
                        .replace("fixture_total", "row_count")
                        .replace(
                            '\\"column\\": \\"total\\"', '\\"column\\": \\"row_count\\"'
                        )
                        .replace('\\"value\\": 42', '\\"value\\": 1')
                        .replace("42 items", "1 row")
                    )

            answer = await run_analysis(
                AnalysisConfig(
                    provider="fixture",
                    model="tool-reviewer-v1",
                    account="fixture",
                    question="How many fixture rows?",
                ),
                analysis,
                fixture_registry(),
                MetricClient(),
            )
            self.assertEqual(answer.answer.status, "answer")
            self.assertEqual(answer.answer.result_ids, ("result-0002",))
            self.assertEqual(answer.semantic_revision, context["revision"])
            self.assertEqual(answer.answer.claims[0].value, 1)

    @skipUnless(
        os.environ.get("DATA_MCP_TEST_DSN"), "Requires a disposable PostgreSQL DSN"
    )
    async def test_postgres_committed_writes_and_reads(self) -> None:
        schema = "mos_mcp_" + uuid4().hex

        def setup(statement: str) -> None:
            subprocess.run(
                [
                    DATA_PYTHON,
                    "-c",
                    "import os,sys,psycopg; "
                    "c=psycopg.connect("
                    "os.environ['DATA_MCP_TEST_DSN'],autocommit=True); "
                    "c.execute(sys.argv[1]); c.close()",
                    statement,
                ],
                check=True,
                capture_output=True,
            )

        setup(
            f"CREATE SCHEMA {schema}; "
            f"CREATE TABLE {schema}.items (id int PRIMARY KEY, value int)"
        )
        try:
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "data.toml"
                path.write_text(
                    '[postgres.test]\ndsn_env = "DATA_MCP_TEST_DSN"\n'
                    'sslmode = "disable"\n'
                )
                cfg = MCPConfig(
                    command=DATA_PYTHON,
                    cwd=temporary,
                    args=("-m", "data_mcp.cli", "--config", str(path)),
                    env=("DATA_MCP_TEST_DSN",),
                    tools={"query_postgres": "read", "execute_postgres": "write"},
                    allow_writes=True,
                )
                async with connect_mcp(cfg) as dispatcher:
                    for sql in (
                        f"INSERT INTO {schema}.items VALUES (1,2)",
                        f"UPDATE {schema}.items SET value=3 WHERE id=1",
                    ):
                        result = await invoke(
                            dispatcher, "execute_postgres", source="test", sql=sql
                        )
                        self.assertTrue(result["committed"])
                        self.assertEqual(result["affected_rows"], 1)
                # New subprocess/connection proves persistence beyond one session.
                async with connect_mcp(cfg) as dispatcher:
                    result = await invoke(
                        dispatcher,
                        "query_postgres",
                        source="test",
                        sql=f"SELECT id,value FROM {schema}.items",
                    )
                    self.assertEqual(result["rows"], [[1, 3]])
                    await invoke(
                        dispatcher,
                        "execute_postgres",
                        source="test",
                        sql=f"DELETE FROM {schema}.items WHERE id=1",
                    )
                    result = await invoke(
                        dispatcher,
                        "query_postgres",
                        source="test",
                        sql=f"SELECT * FROM {schema}.items",
                    )
                    self.assertEqual(result["rows"], [])
        finally:
            setup(f"DROP SCHEMA {schema} CASCADE")
