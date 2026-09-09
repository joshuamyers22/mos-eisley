"""Explicit live analysis admission and content-free failure diagnostics."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import cast

from mos_eisley.analysis.controller import AnalysisConfig, run_analysis
from mos_eisley.analysis.demo import Scenario, run_demo
from mos_eisley.analysis.spending import AnalysisSpending
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.providers.openai_responses import OpenAIResponsesClient
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.files import read_bounded
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.tools.mcp import MCPConfig, redacted_sdk_logs


def run_command(args: argparse.Namespace) -> int:
    spending: AnalysisSpending | None = None
    try:
        with redacted_sdk_logs():
            if args.command == "analysis-demo":
                result = asyncio.run(run_demo(cast(Scenario, args.scenario)))
                print(result.model_dump_json())
                return 0
            if not cast(bool, args.allow_data_transfer):
                raise ValueError("analysis data transfer requires explicit opt-in")
            config = AnalysisConfig.model_validate_json(
                read_bounded(cast(Path, args.config), 64_000)
            )
            mcp = MCPConfig.model_validate_json(
                read_bounded(cast(Path, args.mcp_config), 256_000)
            )
            policy = SpendPolicy.model_validate_json(
                read_bounded(cast(Path, args.spend_policy), 64_000)
            )
            openai_registry().resolve(config.provider, config.model, config.effort)
            spending = AnalysisSpending(
                config,
                mcp,
                policy,
                SpendLedger(cast(Path, args.spend_ledger)),
                cast(str, args.ledger_id),
                cast(int, args.accept_max_cost_microusd),
            )
            spending.reserve()
            try:
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OpenAI API key is missing")
                client = OpenAIResponsesClient(
                    spending.transport(
                        EphemeralOpenAITransport(
                            api_key, config.request_timeout_seconds
                        )
                    )
                )
                result = asyncio.run(
                    run_analysis(config, mcp, openai_registry(), client)
                )
            finally:
                spending.finish()
            assert spending.receipt is not None
            print(
                json.dumps(
                    {
                        "type": "analysis.completed",
                        "result": result.model_dump(mode="json"),
                        "spend_receipt": spending.receipt.model_dump(mode="json"),
                    }
                )
            )
            return 0
    except (Exception, KeyboardInterrupt):
        # MCP exception groups and SDK errors can include source values or secrets.
        event: dict[str, object] = {"type": "analysis.failed"}
        if spending is not None and spending.receipt is not None:
            event["spend_receipt"] = spending.receipt.model_dump(mode="json")
        print(json.dumps(event), file=sys.stderr)
        return 2
