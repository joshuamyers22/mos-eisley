"""Composition root for recorded review, replay, and explicit live requests."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from openai import AsyncOpenAI
from pydantic import ValidationError

from mos_eisley.core.agent import AgentConfig, AgentFailure, AgentResult, run_agent
from mos_eisley.core.models import Brief, Contract, ReviewPolicy, canonical_bytes
from mos_eisley.core.ports import Journal
from mos_eisley.core.protocol import Effort, TextBlock, Turn
from mos_eisley.core.registry import default_registry, fixture_registry, openai_registry
from mos_eisley.demo import demo_inputs
from mos_eisley.demo_agent import agent_demo_inputs
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    GradingBatch,
    compile_observations,
    make_grading_batch,
)
from mos_eisley.evaluation.execution import (
    BlindingMap,
    EvaluationCassette,
    ExecutionBatch,
    RawResultSet,
    make_execution_batch,
    run_recorded_evaluation,
)
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvaluationDataset,
    EvaluationGate,
    ObservationSet,
    Split,
    SweepPlan,
)
from mos_eisley.evaluation.scoring import make_plan, score
from mos_eisley.providers.agent_recorded import RecordedAgentClient
from mos_eisley.providers.openai_responses import (
    OpenAIResponsesClient,
    SDKOpenAITransport,
)
from mos_eisley.providers.recorded import Cassette, RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run.agent_store import begin_agent_run, load_agent_run
from mos_eisley.run.files import read_bounded
from mos_eisley.run.journal import MemoryJournal
from mos_eisley.run.live_store import begin_live_run
from mos_eisley.run.store import index_run, load_run, private_write, save_run
from mos_eisley.tools.fixture import FixtureDispatcher
from mos_eisley.tools.none import NoToolsDispatcher

EXIT_CODES = {"accept": 0, "revise": 1, "reject": 1, "infrastructure_error": 2}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="mos-eisley",
        description=(
            "Mos Eisley: recorded adversarial review, offline evals, and an opt-in "
            "OpenAI preview."
        ),
    )
    command.add_argument("--version", action="version", version="mos-eisley 0.1.0")
    subcommands = command.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("demo", "Run the synthetic recorded example"),
        ("review", "Review an explicit brief using a request-bound cassette"),
    ):
        sub = subcommands.add_parser(name, help=help_text)
        sub.add_argument("--output", type=Path, default=Path(".mos-eisley/runs"))
        sub.add_argument(
            "--json", action="store_true", help="Print NDJSON result events"
        )
        if name == "review":
            sub.add_argument(
                "--brief",
                type=Path,
                required=True,
                help="Brief JSON; no implicit repository reads",
            )
            sub.add_argument("--cassette", type=Path, required=True)
    replay = subcommands.add_parser(
        "replay", help="Verify artifacts and replay recorded responses"
    )
    replay.add_argument("run", type=Path)
    agent_demo = subcommands.add_parser(
        "agent-demo", help="Run a recorded two-turn canonical tool exchange"
    )
    agent_demo.add_argument(
        "--output", type=Path, default=Path(".mos-eisley/agent-runs")
    )
    agent_demo.add_argument("--json", action="store_true")
    agent_replay = subcommands.add_parser(
        "agent-replay", help="Verify and replay a recorded canonical agent run"
    )
    agent_replay.add_argument("run", type=Path)
    openai_run = subcommands.add_parser(
        "openai-run", help="Send one explicit prompt file to the OpenAI Responses API"
    )
    openai_run.add_argument("--prompt", type=Path, required=True)
    openai_run.add_argument("--instructions", type=Path)
    openai_run.add_argument("--model", default="gpt-6-astra")
    openai_run.add_argument(
        "--effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="medium",
    )
    openai_run.add_argument(
        "--output", type=Path, default=Path(".mos-eisley/live-runs")
    )
    openai_run.add_argument(
        "--allow-data-transfer",
        action="store_true",
        help="Acknowledge that prompt content will be sent to OpenAI",
    )
    openai_run.add_argument("--json", action="store_true")
    eval_plan = subcommands.add_parser(
        "eval-plan", help="Create a deterministic backend/model/effort sweep plan"
    )
    eval_plan.add_argument("--dataset", type=Path, required=True)
    eval_plan.add_argument("--candidates", type=Path, required=True)
    eval_plan.add_argument("--gate", type=Path, required=True)
    eval_plan.add_argument("--repetitions", type=int, required=True)
    eval_plan.add_argument("--seed", type=int, required=True)
    eval_plan.add_argument("--output", type=Path, required=True)
    eval_blind = subcommands.add_parser(
        "eval-blind", help="Export a label-blind execution batch and private mapping"
    )
    eval_blind.add_argument("--dataset", type=Path, required=True)
    eval_blind.add_argument("--plan", type=Path, required=True)
    eval_blind.add_argument(
        "--split", choices=("calibration", "holdout"), required=True
    )
    eval_blind.add_argument("--batch-output", type=Path, required=True)
    eval_blind.add_argument("--mapping-output", type=Path, required=True)
    eval_run = subcommands.add_parser(
        "eval-run-recorded", help="Execute a blinded batch from request-bound fixtures"
    )
    eval_run.add_argument("--batch", type=Path, required=True)
    eval_run.add_argument("--cassette", type=Path, required=True)
    eval_run.add_argument("--output", type=Path, required=True)
    eval_grade = subcommands.add_parser(
        "eval-grade-packet", help="Export route-blind material for an adjudicator"
    )
    eval_grade.add_argument("--dataset", type=Path, required=True)
    eval_grade.add_argument("--plan", type=Path, required=True)
    eval_grade.add_argument("--batch", type=Path, required=True)
    eval_grade.add_argument("--mapping", type=Path, required=True)
    eval_grade.add_argument("--raw-results", type=Path, required=True)
    eval_grade.add_argument("--output", type=Path, required=True)
    eval_compile = subcommands.add_parser(
        "eval-compile", help="Compile provenance-bound judgments into observations"
    )
    eval_compile.add_argument("--dataset", type=Path, required=True)
    eval_compile.add_argument("--plan", type=Path, required=True)
    eval_compile.add_argument("--batch", type=Path, required=True)
    eval_compile.add_argument("--mapping", type=Path, required=True)
    eval_compile.add_argument("--raw-results", type=Path, required=True)
    eval_compile.add_argument("--grading-batch", type=Path, required=True)
    eval_compile.add_argument("--adjudication", type=Path, required=True)
    eval_compile.add_argument("--output", type=Path, required=True)
    eval_score = subcommands.add_parser(
        "eval-score", help="Score one exactly covered evaluation split"
    )
    eval_score.add_argument("--dataset", type=Path, required=True)
    eval_score.add_argument("--plan", type=Path, required=True)
    eval_score.add_argument("--observations", type=Path, required=True)
    eval_score.add_argument(
        "--split", choices=("calibration", "holdout"), required=True
    )
    eval_score.add_argument("--output", type=Path, required=True)
    subcommands.add_parser("models", help="Print the configured model registry")
    return command


def _utf8_file(path: Path, limit: int) -> str:
    try:
        value = read_bounded(path, limit).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("input file must be UTF-8") from error
    if not value:
        raise ValueError("input file must not be empty")
    return value


def _write_contract(path: Path, value: Contract) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(path, canonical_bytes(value))


async def _openai_run(
    config: AgentConfig, api_key: str, journal: Journal
) -> AgentResult:
    async with AsyncOpenAI(
        api_key=api_key,
        timeout=config.request_timeout_seconds,
        max_retries=0,
    ) as sdk:
        return await run_agent(
            config,
            openai_registry(),
            OpenAIResponsesClient(SDKOpenAITransport(sdk)),
            NoToolsDispatcher(),
            journal,
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "eval-blind":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            plan = SweepPlan.model_validate_json(
                read_bounded(cast(Path, args.plan), 16_000_000)
            )
            split = cast(Split, args.split)
            batch, mapping = make_execution_batch(
                plan, dataset, split, secrets.token_bytes(32)
            )
            batch_output = cast(Path, args.batch_output)
            mapping_output = cast(Path, args.mapping_output)
            if batch_output == mapping_output:
                raise ValueError("batch and mapping outputs must be different files")
            if batch_output.exists() or mapping_output.exists():
                raise ValueError("evaluation output already exists")
            _write_contract(batch_output, batch)
            _write_contract(mapping_output, mapping)
            print(
                json.dumps(
                    {
                        "type": "evaluation.batch.created",
                        "batch_path": str(batch_output),
                        "mapping_path": str(mapping_output),
                        "batch_sha256": batch.batch_sha256,
                        "mapping_sha256": mapping.mapping_sha256,
                        "requests": len(batch.requests),
                    }
                )
            )
            return 0
        if args.command == "eval-run-recorded":
            batch = ExecutionBatch.model_validate_json(
                read_bounded(cast(Path, args.batch), 16_000_000)
            )
            cassette = EvaluationCassette.model_validate_json(
                read_bounded(cast(Path, args.cassette), 16_000_000)
            )
            raw_results = run_recorded_evaluation(batch, cassette)
            output = cast(Path, args.output)
            _write_contract(output, raw_results)
            print(
                json.dumps(
                    {
                        "type": "evaluation.execution.completed",
                        "path": str(output),
                        "raw_results_sha256": raw_results.raw_results_sha256,
                        "completed": sum(
                            result.status == "completed"
                            for result in raw_results.results
                        ),
                        "errors": sum(
                            result.status == "error" for result in raw_results.results
                        ),
                    }
                )
            )
            return 0
        if args.command == "eval-grade-packet":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            plan = SweepPlan.model_validate_json(
                read_bounded(cast(Path, args.plan), 16_000_000)
            )
            batch = ExecutionBatch.model_validate_json(
                read_bounded(cast(Path, args.batch), 16_000_000)
            )
            mapping = BlindingMap.model_validate_json(
                read_bounded(cast(Path, args.mapping), 16_000_000)
            )
            raw_results = RawResultSet.model_validate_json(
                read_bounded(cast(Path, args.raw_results), 16_000_000)
            )
            grading_batch = make_grading_batch(
                dataset, plan, batch, mapping, raw_results
            )
            output = cast(Path, args.output)
            _write_contract(output, grading_batch)
            print(
                json.dumps(
                    {
                        "type": "evaluation.grading_batch.created",
                        "path": str(output),
                        "grading_batch_sha256": grading_batch.grading_batch_sha256,
                        "items": len(grading_batch.items),
                    }
                )
            )
            return 0
        if args.command == "eval-compile":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            plan = SweepPlan.model_validate_json(
                read_bounded(cast(Path, args.plan), 16_000_000)
            )
            batch = ExecutionBatch.model_validate_json(
                read_bounded(cast(Path, args.batch), 16_000_000)
            )
            mapping = BlindingMap.model_validate_json(
                read_bounded(cast(Path, args.mapping), 16_000_000)
            )
            raw_results = RawResultSet.model_validate_json(
                read_bounded(cast(Path, args.raw_results), 16_000_000)
            )
            grading_batch = GradingBatch.model_validate_json(
                read_bounded(cast(Path, args.grading_batch), 16_000_000)
            )
            adjudication = AdjudicationSet.model_validate_json(
                read_bounded(cast(Path, args.adjudication), 16_000_000)
            )
            observations = compile_observations(
                dataset,
                plan,
                batch,
                mapping,
                raw_results,
                grading_batch,
                adjudication,
            )
            output = cast(Path, args.output)
            _write_contract(output, observations)
            print(
                json.dumps(
                    {
                        "type": "evaluation.observations.compiled",
                        "path": str(output),
                        "observations_sha256": observations.observations_sha256,
                        "observations": len(observations.observations),
                    }
                )
            )
            return 0
        if args.command == "eval-plan":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            candidates = CandidateGrid.model_validate_json(
                read_bounded(cast(Path, args.candidates))
            )
            gate = EvaluationGate.model_validate_json(
                read_bounded(cast(Path, args.gate))
            )
            plan = make_plan(
                dataset,
                candidates,
                cast(int, args.repetitions),
                cast(int, args.seed),
                gate,
            )
            output = cast(Path, args.output)
            _write_contract(output, plan)
            print(
                json.dumps(
                    {
                        "type": "evaluation.plan.created",
                        "path": str(output),
                        "plan_sha256": plan.plan_sha256,
                        "assignments": len(plan.assignments),
                    }
                )
            )
            return 0
        if args.command == "eval-score":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            plan = SweepPlan.model_validate_json(
                read_bounded(cast(Path, args.plan), 16_000_000)
            )
            observations = ObservationSet.model_validate_json(
                read_bounded(cast(Path, args.observations), 16_000_000)
            )
            split = cast(Split, args.split)
            report = score(plan, dataset, observations, split)
            output = cast(Path, args.output)
            _write_contract(output, report)
            print(
                json.dumps(
                    {
                        "type": "evaluation.score.created",
                        "path": str(output),
                        "split": split,
                        "eligible": sum(item.eligible for item in report.scores),
                        "promotion_ready": report.promotion_ready,
                    }
                )
            )
            return 0
        if args.command == "models":
            for model in default_registry().models:
                print(model.model_dump_json())
            return 0
        if args.command == "openai-run":
            if not cast(bool, args.allow_data_transfer):
                raise ValueError("OpenAI data transfer was not acknowledged")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not configured")
            prompt = _utf8_file(cast(Path, args.prompt), 64_000)
            instructions_path = cast(Path | None, args.instructions)
            instructions = (
                _utf8_file(instructions_path, 64_000)
                if instructions_path is not None
                else ""
            )
            config = AgentConfig(
                provider="openai",
                model=cast(str, args.model),
                effort=cast(Effort, args.effort),
                system=instructions,
                initial_turns=(
                    Turn(
                        role="user",
                        blocks=tuple(
                            TextBlock(text=prompt[index : index + 8000])
                            for index in range(0, len(prompt), 8000)
                        ),
                    ),
                ),
                max_iterations=1,
                max_tool_calls=0,
            )
            session = begin_live_run(cast(Path, args.output), config)
            try:
                result = asyncio.run(_openai_run(config, api_key, session.journal))
                session.complete(result)
            except BaseException:
                session.abort()
                raise
            event = {
                "type": "openai.completed",
                "path": str(session.path),
                "model": result.resolved_model.spec.id,
                "input_tokens": result.usage.billed_input,
                "output_tokens": result.usage.billed_output,
                "text": result.final_text,
            }
            if args.json:
                print(json.dumps(event))
            else:
                print(result.final_text)
                print(f"Artifacts: {session.path}")
            return 0
        if args.command == "agent-replay":
            config, fixtures, cassette, expected_events, expected_result = (
                load_agent_run(cast(Path, args.run))
            )
            client = RecordedAgentClient(cassette)
            journal = MemoryJournal()
            actual = asyncio.run(
                run_agent(
                    config,
                    fixture_registry(),
                    client,
                    FixtureDispatcher(fixtures),
                    journal,
                )
            )
            comparable_actual = (
                actual
                if expected_result.responses
                else actual.model_copy(update={"responses": ()})
            )
            if (
                comparable_actual != expected_result
                or tuple(journal.events) != expected_events
                or not client.exhausted
            ):
                raise ValueError("recorded agent replay differs from stored run")
            print(
                json.dumps(
                    {
                        "type": "agent.replay.verified",
                        "requests": actual.usage.requests,
                        "tools": actual.usage.tools,
                    }
                )
            )
            return 0
        if args.command == "agent-demo":
            config, fixtures, cassette = agent_demo_inputs()
            session = begin_agent_run(
                cast(Path, args.output), config, fixtures, cassette
            )
            try:
                client = RecordedAgentClient(cassette)
                result = asyncio.run(
                    run_agent(
                        config,
                        fixture_registry(),
                        client,
                        FixtureDispatcher(fixtures),
                        session.journal,
                    )
                )
                if not client.exhausted:
                    raise ValueError("recorded agent left unused exchanges")
                session.complete(result)
            except BaseException:
                session.abort()
                raise
            event = {
                "type": "agent.completed",
                "mode": "recorded_agent",
                "path": str(session.path),
                "requests": result.usage.requests,
                "tools": result.usage.tools,
                "text": result.final_text,
            }
            if args.json:
                print(json.dumps(event))
            else:
                print(result.final_text)
                print(f"Artifacts: {session.path}")
            return 0
        if args.command == "replay":
            brief, cassette, policy, expected = load_run(cast(Path, args.run))
            actual = asyncio.run(
                review(
                    brief,
                    tuple(r.critic for r in cassette.critics),
                    RecordedReviewer(cassette),
                    policy,
                )
            )
            if actual != expected:
                raise ValueError("recorded replay differs from stored result")
            print(
                json.dumps(
                    {
                        "type": "replay.verified",
                        "brief_id": brief.brief_id,
                        "decision": actual.verdict.decision,
                    }
                )
            )
            return 0
        if args.command == "demo":
            brief, cassette = demo_inputs()
        else:
            brief = Brief.model_validate_json(read_bounded(cast(Path, args.brief)))
            cassette = Cassette.model_validate_json(
                read_bounded(cast(Path, args.cassette), 16_000_000)
            )
        if brief.brief_id != cassette.brief_id:
            raise ValueError("cassette does not match the supplied brief")
        policy = ReviewPolicy()
        result = asyncio.run(
            review(
                brief,
                tuple(r.critic for r in cassette.critics),
                RecordedReviewer(cassette),
                policy,
            )
        )
        root = cast(Path, args.output)
        path = save_run(root, brief, cassette, policy, result)
        try:
            index_run(root, path, result)
        except (OSError, sqlite3.Error):
            print(
                "Index unavailable; complete run artifacts were preserved.",
                file=sys.stderr,
            )
        if args.json:
            print(
                json.dumps({"type": "run.saved", "mode": "recorded", "path": str(path)})
            )
            print(
                json.dumps(
                    {"type": "verdict", **result.verdict.model_dump(mode="json")}
                )
            )
        else:
            print(
                f"Recorded review: {result.verdict.decision} "
                f"({len(result.verdict.findings)} findings)"
            )
            print(f"Artifacts: {path}")
        return EXIT_CODES[result.verdict.decision]
    except ValidationError:
        # Pydantic diagnostics include raw rejected values; do not echo inputs.
        print("mos-eisley: invalid input schema", file=sys.stderr)
        return 2
    except (AgentFailure, OSError, ValueError) as error:
        print(
            f"mos-eisley: {type(error).__name__}: input or artifact validation failed",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
