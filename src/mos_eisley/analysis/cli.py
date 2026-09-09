"""Explicit live analysis admission and content-free failure diagnostics."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import cast

from mos_eisley.analysis.artifacts import (
    AnalysisArtifact,
    delete_expired,
    export_csv,
    load_artifact,
    private_directory,
    read_bundle,
    save_artifact,
    verify_export,
)
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


def _retention_root(args: argparse.Namespace, config: AnalysisConfig) -> Path | None:
    root = cast(Path | None, args.result_root)
    allowed = cast(bool, args.allow_result_retention)
    if config.retention == "memory":
        if root is not None or allowed:
            raise ValueError("retention flags do not match memory-only configuration")
        return None
    if not allowed or root is None:
        raise ValueError("private retention requires explicit destination and consent")
    return private_directory(root)


def run_command(args: argparse.Namespace) -> int:
    spending: AnalysisSpending | None = None
    try:
        with redacted_sdk_logs():
            if args.command == "analysis-verify":
                path = cast(Path, args.path)
                source = cast(Path | None, args.source)
                manifest, _ = read_bundle(path)
                if manifest.kind == "csv":
                    if source is None:
                        raise ValueError("CSV verification requires its source bundle")
                    manifest = verify_export(path, source)
                else:
                    manifest, _ = load_artifact(path)
                print(
                    json.dumps(
                        {
                            "type": "analysis.artifact.verified",
                            "kind": manifest.kind,
                            "run_id": manifest.run_id,
                        }
                    )
                )
                return 0
            if args.command == "analysis-export":
                path = export_csv(
                    cast(Path, args.path),
                    cast(str, args.result_id),
                    cast(Path, args.result_root),
                )
                print(json.dumps({"type": "analysis.exported", "path": str(path)}))
                return 0
            if args.command == "analysis-delete-expired":
                delete_expired(cast(Path, args.path))
                print(json.dumps({"type": "analysis.artifact.deleted"}))
                return 0
            if args.command == "analysis-demo":
                config = AnalysisConfig(
                    provider="fixture",
                    model="tool-reviewer-v1",
                    account="fixture",
                    question="Synthetic demo",
                    retention="private" if args.allow_result_retention else "memory",
                    artifact_ttl_seconds=cast(int, args.artifact_ttl_seconds),
                )
                root = _retention_root(args, config)
                result = asyncio.run(
                    run_demo(cast(Scenario, args.scenario), retention=config.retention)
                )
                if root is None:
                    print(result.model_dump_json())
                else:
                    path = save_artifact(
                        root,
                        AnalysisArtifact(result=result),
                        config.artifact_ttl_seconds,
                    )
                    print(
                        json.dumps(
                            {
                                "type": "analysis.completed",
                                "result": result.model_dump(mode="json"),
                                "artifact_path": str(path),
                            }
                        )
                    )
                return 0
            if not cast(bool, args.allow_data_transfer):
                raise ValueError("analysis data transfer requires explicit opt-in")
            config = AnalysisConfig.model_validate_json(
                read_bounded(cast(Path, args.config), 64_000)
            )
            root = _retention_root(args, config)
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
            event: dict[str, object] = {
                "type": "analysis.completed",
                "result": result.model_dump(mode="json"),
                "spend_receipt": spending.receipt.model_dump(mode="json"),
            }
            if root is not None:
                path = save_artifact(
                    root,
                    AnalysisArtifact(result=result, spend_receipt=spending.receipt),
                    config.artifact_ttl_seconds,
                )
                event["artifact_path"] = str(path)
            print(json.dumps(event))
            return 0
    except (Exception, KeyboardInterrupt):
        # MCP exception groups and SDK errors can include source values or secrets.
        failure: dict[str, object] = {"type": "analysis.failed"}
        if spending is not None and spending.receipt is not None:
            failure["spend_receipt"] = spending.receipt.model_dump(mode="json")
        print(json.dumps(failure), file=sys.stderr)
        return 2
