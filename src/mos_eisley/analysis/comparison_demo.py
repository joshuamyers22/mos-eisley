"""Two synthetic arms following a frozen schedule; not a domain quality study."""

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
    EvaluationSuite,
    ExpectedCell,
    ExpectedOutcome,
    Observation,
    write_private_json,
)
from mos_eisley.analysis.evidence import ContextMode
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.analysis.schedule import (
    ComparisonAssessment,
    assess_schedule,
    make_schedule,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.registry import fixture_registry
from mos_eisley.tools.mcp import connect_mcp, redacted_sdk_logs


async def run_demo(root: Path) -> tuple[Path, ComparisonAssessment]:
    path = private_directory(root) / uuid4().hex
    path.mkdir(mode=0o700)
    modes: tuple[ContextMode, ...] = ("raw", "promoted")
    configs = {
        mode: AnalysisConfig(
            provider="fixture",
            model="tool-reviewer-v1",
            account="fixture",
            question="Filled from frozen tasks",
            context_mode=mode,
            retention="private",
        )
        for mode in modes
    }
    profiles = {mode: analysis_mcp_config(fixture_config(mode), mode) for mode in modes}
    arms: list[EvaluationArm] = []
    with redacted_sdk_logs():
        for mode in modes:
            async with connect_mcp(profiles[mode]) as dispatcher:
                arms.append(
                    EvaluationArm(
                        id=mode,
                        provider="fixture",
                        model=configs[mode].model,
                        run_identity=run_identity(
                            configs[mode], dispatcher.definitions
                        ),
                        context_mode=mode,
                        semantic_revision=REVISION if mode == "promoted" else None,
                    )
                )
        outcomes = tuple(
            ExpectedOutcome(
                arm_id=mode,
                status="answer",
                cells=(
                    ExpectedCell(
                        tool="run_metric" if mode == "promoted" else "query_parquet",
                        arguments={"name": "fixture_total", "revision": REVISION}
                        if mode == "promoted"
                        else {
                            "root": "synthetic",
                            "paths": ["items.parquet"],
                            "sql": "SELECT SUM(quantity) AS total FROM data",
                        },
                        submitted_sql="SELECT 42 AS total"
                        if mode == "promoted"
                        else "SELECT SUM(quantity) AS total FROM data",
                        source_metadata={
                            "backend": "fixture",
                            "source": "synthetic",
                            "units": "items",
                        }
                        if mode == "promoted"
                        else {},
                        reviewed_units="items",
                        row=0,
                        column="total",
                        value=42,
                    ),
                ),
            )
            for mode in modes
        )
        suite = EvaluationSuite(
            id="synthetic-comparison",
            reviewer="fixture-author",
            reviewed_at=datetime.now(UTC),
            arms=tuple(arms),
            cases=tuple(
                EvaluationCase(
                    id=f"total-{index}",
                    family="synthetic-total",
                    split="development",
                    question=question,
                    fixture_sha256=digest(b"packaged synthetic total: 42"),
                    expectations=outcomes,
                )
                for index, question in enumerate(
                    (
                        "What is the synthetic total?",
                        "Return the synthetic total quantity in items.",
                    )
                )
            ),
        )
        schedule = make_schedule(suite, "development", "a" * 64)
        write_private_json(path / "suite.json", suite)
        write_private_json(path / "schedule.json", schedule)
        questions = {case.id: case.question for case in schedule.tasks.cases}
        observations: list[Observation] = []
        for assignment in schedule.assignments:
            mode = next(mode for mode in modes if mode == assignment.arm_id)
            config = configs[mode].model_copy(
                update={"question": questions[assignment.case_id]}
            )
            try:
                result = await run_analysis(
                    config,
                    profiles[mode],
                    fixture_registry(),
                    AnalysisFixtureClient(context_mode=config.context_mode),
                )
                bundle = save_artifact(path, AnalysisArtifact(result=result), 86400)
                manifest, _ = load_artifact(bundle)
                observations.append(
                    Observation(
                        case_id=assignment.case_id,
                        arm_id=assignment.arm_id,
                        artifact_path=str(bundle),
                        artifact_sha256=manifest.payload_sha256,
                    )
                )
            except Exception:
                observations.append(
                    Observation(
                        case_id=assignment.case_id,
                        arm_id=assignment.arm_id,
                        failure="validation_error",
                    )
                )
        inputs = EvaluationInputs(
            suite_sha256=digest(canonical_bytes(suite)),
            split="development",
            observations=tuple(observations),
        )
        write_private_json(path / "inputs.json", inputs)
        report = assess_schedule(suite, schedule, inputs)
        write_private_json(path / "assessment.json", report)
        return path, report
