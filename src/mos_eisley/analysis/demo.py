"""Scripted conversations through a real stdio MCP session; no provider calls."""

import json
import sys
from pathlib import Path
from typing import Literal

from mos_eisley.analysis.controller import AnalysisConfig, AnalysisResult, run_analysis
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    TextBlock,
    ToolCallBlock,
    Turn,
    Usage,
)
from mos_eisley.core.registry import fixture_registry
from mos_eisley.tools.mcp import MCPConfig

Scenario = Literal["answer", "clarify", "unavailable", "injection"]


def fixture_config() -> MCPConfig:
    return MCPConfig(
        command=sys.executable,
        args=("-m", "mos_eisley.analysis.fixture_server"),
        cwd=str(Path.cwd()),
        tools={"get_semantic_context": "read", "run_metric": "read"},
    )


class AnalysisFixtureClient:
    def __init__(self, scenario: Scenario = "answer") -> None:
        self.scenario, self.requests = scenario, 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests += 1
        if (self.requests == 1 and self.scenario in {"answer", "injection"}) or (
            self.requests == 2 and self.scenario == "injection"
        ):
            turn = Turn(
                role="assistant",
                blocks=(
                    ToolCallBlock(
                        id=f"fixture-call-{self.requests}",
                        name="write_parquet"
                        if self.scenario == "injection" and self.requests == 2
                        else "run_metric",
                        args={
                            "arguments_json": json.dumps(
                                {
                                    "name": "fixture_total",
                                    "revision": REVISION,
                                }
                            )
                        },
                    ),
                ),
            )
            stop = "tool_use"
        else:
            status = "unavailable" if self.scenario == "injection" else self.scenario
            texts = {
                "answer": "The synthetic total is 42 items.",
                "clarify": "Which time range should I use?",
                "unavailable": "The requested data or operation is unavailable.",
            }
            turn = Turn(
                role="assistant",
                blocks=(
                    TextBlock(
                        text=json.dumps(
                            {
                                "status": status,
                                "text": texts[status],
                                "claims": [
                                    {
                                        "result_id": "result-0002",
                                        "row": 0,
                                        "column": "total",
                                        "value": 42,
                                    }
                                ]
                                if status == "answer"
                                else [],
                                "result_ids": ["result-0002"]
                                if status == "answer"
                                else [],
                            }
                        )
                    ),
                ),
            )
            stop = "end_turn"
        return ModelResponse(
            turn=turn,
            stop_reason=stop,
            usage=Usage(
                input=len(canonical_bytes(request)), output=len(canonical_bytes(turn))
            ),
        )


async def run_demo(
    scenario: Scenario = "answer", *, retention: Literal["memory", "private"] = "memory"
) -> AnalysisResult:
    return await run_analysis(
        AnalysisConfig(
            provider="fixture",
            model="tool-reviewer-v1",
            account="fixture",
            retention=retention,
            question="What is the synthetic total?",
        ),
        fixture_config(),
        fixture_registry(),
        AnalysisFixtureClient(scenario),
    )
