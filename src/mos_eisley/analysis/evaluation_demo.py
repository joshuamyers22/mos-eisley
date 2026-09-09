"""Synthetic plumbing evidence; not held-out model quality or preregistration proof."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mos_eisley.analysis.artifacts import (
    AnalysisArtifact,
    load_artifact,
    private_directory,
    save_artifact,
)
from mos_eisley.analysis.controller import (
    AnalysisConfig,
    analysis_mcp_config,
    run_analysis,
    run_identity,
)
from mos_eisley.analysis.demo import AnalysisFixtureClient, fixture_config
from mos_eisley.analysis.evaluation import (
    EvaluationArm,
    EvaluationCase,
    EvaluationInputs,
    EvaluationReport,
    EvaluationSuite,
    ExpectedCell,
    ExpectedOutcome,
    Observation,
    evaluate,
    public_plan,
    write_private_json,
)
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.registry import fixture_registry
from mos_eisley.tools.mcp import connect_mcp, redacted_sdk_logs


async def run_demo(root: Path) -> tuple[Path, EvaluationReport]:
    root = private_directory(root)
    path = root / uuid4().hex
    path.mkdir(mode=0o700)
    config = AnalysisConfig(
        provider="fixture",
        model="tool-reviewer-v1",
        account="fixture",
        question="What is the synthetic total?",
        retention="private",
    )
    mcp = analysis_mcp_config(fixture_config())
    with redacted_sdk_logs():
        async with connect_mcp(mcp) as dispatcher:
            identity = run_identity(config, dispatcher.definitions)
        cell = ExpectedCell(
            tool="run_metric",
            arguments={"name": "fixture_total", "revision": REVISION},
            submitted_sql="SELECT 42 AS total",
            source_metadata={
                "backend": "fixture",
                "source": "synthetic",
                "units": "items",
            },
            reviewed_units="items",
            row=0,
            column="total",
            value=42,
        )
        suite = EvaluationSuite(
            id="synthetic-analysis",
            reviewer="fixture-author",
            reviewed_at=datetime.now(UTC),
            arms=(
                EvaluationArm(
                    id="seeded",
                    provider="fixture",
                    model=config.model,
                    run_identity=identity,
                    semantic_revision=REVISION,
                ),
            ),
            cases=tuple(
                EvaluationCase(
                    id=name,
                    family=name,
                    split="development",
                    question=question,
                    fixture_sha256=digest(b"packaged synthetic total: 42"),
                    expectations=(
                        ExpectedOutcome(
                            arm_id="seeded", status="answer", cells=(cell,)
                        ),
                    ),
                )
                for name, question in (
                    ("total", config.question),
                    ("failed-run", "A synthetic failed assignment"),
                    ("missing-run", "A synthetic missing assignment"),
                )
            ),
        )
        # The expected values and suite digest are written before the tested run.
        write_private_json(path / "suite.json", suite)
        write_private_json(path / "tasks.json", public_plan(suite, "development"))
        result = await run_analysis(
            config, mcp, fixture_registry(), AnalysisFixtureClient()
        )
    bundle = save_artifact(path, AnalysisArtifact(result=result), 86400)
    manifest, _ = load_artifact(bundle)
    inputs = EvaluationInputs(
        suite_sha256=digest(canonical_bytes(suite)),
        split="development",
        observations=(
            Observation(
                case_id="total",
                arm_id="seeded",
                artifact_path=str(bundle),
                artifact_sha256=manifest.payload_sha256,
            ),
            Observation(case_id="failed-run", arm_id="seeded", failure="timeout"),
        ),
    )
    write_private_json(path / "inputs.json", inputs)
    report = evaluate(suite, inputs)
    write_private_json(path / "report.json", report)
    return path, report
