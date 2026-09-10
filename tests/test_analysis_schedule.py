"""Frozen schedule completeness, counterbalancing and recorded-order boundaries."""

import io
import json
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from test_analysis_evaluation import captured, cell
from test_analysis_evaluation import suite as base_suite

from mos_eisley.analysis.artifacts import AnalysisArtifact, load_artifact, save_artifact
from mos_eisley.analysis.evaluation import (
    EvaluationCase,
    EvaluationInputs,
    EvaluationSuite,
    ExpectedOutcome,
    Observation,
)
from mos_eisley.analysis.schedule import (
    ComparisonSchedule,
    assess_schedule,
    make_schedule,
)
from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest

SEED = "d" * 64


def suite(cases: int = 4, arms: int = 2) -> EvaluationSuite:
    base = base_suite()
    variants = tuple(
        base.arms[0].model_copy(update={"id": f"arm-{i}"}) for i in range(arms)
    )
    return EvaluationSuite(
        id="comparison-fixture",
        reviewer=base.reviewer,
        reviewed_at=base.reviewed_at,
        arms=variants,
        cases=tuple(
            EvaluationCase(
                id=f"case-{i}",
                family=f"family-{i}",
                split="development",
                question=f"What is the total for fixture {i}?",
                fixture_sha256="e" * 64,
                expectations=tuple(
                    ExpectedOutcome(arm_id=arm.id, status="answer", cells=(cell(),))
                    for arm in variants
                ),
            )
            for i in range(cases)
        ),
    )


class ScheduleTests(TestCase):
    def setUp(self) -> None:
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.labels = suite()
        self.created = datetime.now(UTC) - timedelta(minutes=10)
        self.schedule = make_schedule(
            self.labels, "development", SEED, created_at=self.created
        )

    def observations(
        self, intervals: list[tuple[int, int]] | None = None
    ) -> tuple[Observation, ...]:
        observations: list[Observation] = []
        questions = {case.id: case.question for case in self.labels.cases}
        for index, assignment in enumerate(self.schedule.assignments):
            start, end = (
                intervals[index] if intervals else (index * 3 + 1, index * 3 + 2)
            )
            started = self.created + timedelta(seconds=start)
            completed = self.created + timedelta(seconds=end)
            artifact = captured()
            result = artifact.result
            traces = tuple(
                trace.model_copy(
                    update={"started_at": started, "completed_at": completed}
                )
                for trace in result.tool_trace
            )
            question = questions[assignment.case_id]
            result = result.model_copy(
                update={
                    "question": question,
                    "question_sha256": digest(question.encode()),
                    "started_at": started,
                    "completed_at": completed,
                    "tool_trace": traces,
                }
            )
            bundle = save_artifact(self.root, AnalysisArtifact(result=result), 3600)
            manifest, _ = load_artifact(bundle)
            observations.append(
                Observation(
                    case_id=assignment.case_id,
                    arm_id=assignment.arm_id,
                    artifact_path=str(bundle),
                    artifact_sha256=manifest.payload_sha256,
                )
            )
        return tuple(observations)

    def inputs(self, observations: tuple[Observation, ...]) -> EvaluationInputs:
        return EvaluationInputs(
            suite_sha256=digest(canonical_bytes(self.labels)),
            split="development",
            observations=observations,
        )

    def test_deterministic_complete_blocks_and_balanced_positions(self) -> None:
        for arm_count in (2, 3, 8):
            for count in (1, 7, 16):
                labels = suite(count, arm_count)
                schedule = make_schedule(
                    labels, "development", SEED, created_at=self.created
                )
                self.assertEqual(
                    schedule,
                    make_schedule(labels, "development", SEED, created_at=self.created),
                )
                assignments = schedule.assignments
                self.assertEqual(len(assignments), count * arm_count)
                self.assertEqual(
                    len({(a.case_id, a.arm_id) for a in assignments}), len(assignments)
                )
                positions: dict[str, Counter[int]] = {
                    arm.id: Counter() for arm in labels.arms
                }
                for index in range(count):
                    block = assignments[index * arm_count : (index + 1) * arm_count]
                    self.assertEqual(len({a.case_id for a in block}), 1)
                    self.assertEqual({a.arm_id for a in block}, set(positions))
                    for position, assignment in enumerate(block):
                        positions[assignment.arm_id][position] += 1
                for values in positions.values():
                    counts = [values[index] for index in range(arm_count)]
                    self.assertLessEqual(max(counts) - min(counts), 1)
        changed = make_schedule(
            self.labels, "development", "f" * 64, created_at=self.created
        )
        self.assertNotEqual(changed.assignments, self.schedule.assignments)

    def test_schedule_excludes_labels_and_unselected_holdout(self) -> None:
        extra = self.labels.cases[0].model_copy(
            update={
                "id": "holdout",
                "family": "unseen",
                "split": "holdout",
                "question": "Held-out question",
            }
        )
        labels = self.labels.model_copy(update={"cases": (*self.labels.cases, extra)})
        schedule = make_schedule(labels, "development", SEED, created_at=self.created)
        text = schedule.model_dump_json()
        for forbidden in (
            "SELECT",
            "expectations",
            "reviewed_units",
            "Held-out question",
        ):
            self.assertNotIn(forbidden, text)
        holdout = make_schedule(labels, "holdout", SEED, created_at=self.created)
        self.assertEqual({a.case_id for a in holdout.assignments}, {"holdout"})

    def test_mutated_omitted_duplicate_order_seed_and_tasks_reject(self) -> None:
        for update in (
            {"assignments": tuple(reversed(self.schedule.assignments))},
            {"assignments": self.schedule.assignments[:-1]},
            {
                "assignments": (
                    *self.schedule.assignments[:-1],
                    self.schedule.assignments[0],
                )
            },
            {"seed": "f" * 64},
            {"created_at": datetime.now()},
        ):
            with self.assertRaises(ValueError):
                ComparisonSchedule.model_validate_json(
                    self.schedule.model_copy(update=update).model_dump_json()
                )
        changed_case = self.schedule.tasks.cases[0].model_copy(
            update={"question": "Substituted task"}
        )
        tampered = self.schedule.model_copy(
            update={
                "tasks": self.schedule.tasks.model_copy(
                    update={
                        "cases": (changed_case, *self.schedule.tasks.cases[1:]),
                    }
                )
            }
        )
        with self.assertRaises(ValueError):
            assess_schedule(self.labels, tampered, self.inputs(()))
        with self.assertRaises(ValueError):
            make_schedule(suite(1, 1), "development", SEED)
        with self.assertRaises(ValueError):
            make_schedule(
                self.labels,
                "development",
                SEED,
                created_at=self.labels.reviewed_at - timedelta(seconds=1),
            )
        with self.assertRaises(ValueError):
            make_schedule(self.labels, "holdout", SEED)

    def test_recorded_order_matches_independently_of_input_list_order(self) -> None:
        report = assess_schedule(
            self.labels,
            self.schedule,
            self.inputs(tuple(reversed(self.observations()))),
        )
        self.assertTrue(report.recorded_order_matches)
        self.assertEqual(report.timing_unknown_assignments, 0)
        self.assertTrue(
            all(case.outcome == "match" for case in report.evaluation.cases)
        )
        self.assertFalse(report.controlled_comparison_verified)
        self.assertFalse(report.execution_authorship_verified)
        self.assertFalse(report.promotion_ready)
        encoded = report.model_dump_json()
        self.assertNotIn("SELECT", encoded)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("What is the total", encoded)

    def test_before_freeze_reversed_and_overlapping_runs_are_reported(self) -> None:
        default = [(i * 3 + 1, i * 3 + 2) for i in range(8)]
        for intervals, reason in (
            ([(-2, -1), *default[1:]], "run_predates_schedule"),
            ([(5, 6), (1, 2), *default[2:]], "out_of_order"),
            ([(1, 8), (4, 5), *default[2:]], "overlap"),
        ):
            report = assess_schedule(
                self.labels, self.schedule, self.inputs(self.observations(intervals))
            )
            self.assertFalse(report.recorded_order_matches)
            self.assertTrue(any(reason in timing.reasons for timing in report.timings))
            self.assertEqual(report.timing_unknown_assignments, 0)
            # Correct values alone cannot establish the scheduled execution order.
            self.assertTrue(
                all(case.outcome == "match" for case in report.evaluation.cases)
            )

    def test_missing_failed_invalid_and_changed_evidence_keep_unknown_timing(
        self,
    ) -> None:
        obs = list(self.observations())
        obs[0] = Observation(
            case_id=obs[0].case_id, arm_id=obs[0].arm_id, failure="timeout"
        )
        obs[1] = obs[1].model_copy(update={"artifact_sha256": "a" * 64})
        report = assess_schedule(
            self.labels, self.schedule, self.inputs(tuple(obs[:-1]))
        )
        self.assertFalse(report.recorded_order_matches)
        self.assertEqual(report.timing_unknown_assignments, 3)
        self.assertEqual(len(report.timings), 8)
        self.assertEqual(sum(arm.planned_cases for arm in report.evaluation.arms), 8)
        with patch(
            "mos_eisley.analysis.schedule.load_artifact",
            side_effect=ValueError("private details"),
        ):
            unavailable = assess_schedule(
                self.labels, self.schedule, self.inputs(self.observations())
            )
        self.assertEqual(unavailable.timing_unknown_assignments, 8)
        self.assertNotIn("private details", unavailable.model_dump_json())

    def test_cli_freezes_digest_requires_pin_and_refuses_overwrite(self) -> None:
        labels_path, schedule_path = (
            self.root / "suite.json",
            self.root / "schedule.json",
        )
        labels_path.write_bytes(canonical_bytes(self.labels))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(
                    [
                        "analysis-eval-schedule",
                        "--suite",
                        str(labels_path),
                        "--split",
                        "development",
                        "--seed",
                        SEED,
                        "--output",
                        str(schedule_path),
                    ]
                ),
                0,
            )
        self.assertEqual(schedule_path.stat().st_mode & 0o777, 0o600)
        event = json.loads(output.getvalue())
        schedule = ComparisonSchedule.model_validate_json(schedule_path.read_bytes())
        self.assertEqual(event["schedule_sha256"], digest(canonical_bytes(schedule)))
        inputs_path = self.root / "inputs.json"
        inputs_path.write_bytes(canonical_bytes(self.inputs(())))
        args = [
            "analysis-eval-assess",
            "--suite",
            str(labels_path),
            "--schedule",
            str(schedule_path),
            "--schedule-sha256",
            event["schedule_sha256"],
            "--inputs",
            str(inputs_path),
            "--output",
            str(self.root / "report.json"),
        ]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                main(args), 1
            )  # Missing assignments remain an unsuccessful assessment.
        self.assertEqual((self.root / "report.json").stat().st_mode & 0o777, 0o600)
        wrong_pin = args.copy()
        wrong_pin[wrong_pin.index("--schedule-sha256") + 1] = "b" * 64
        wrong_pin[-1] = str(self.root / "wrong-pin-report.json")
        for arguments in (args, wrong_pin):
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertEqual(main(arguments), 2)
            self.assertEqual(
                json.loads(error.getvalue()), {"type": "analysis.schedule.failed"}
            )

        self.assertFalse((self.root / "wrong-pin-report.json").exists())
        schedule_path.write_bytes(canonical_bytes(self.schedule))
        inputs_path.write_bytes(canonical_bytes(self.inputs(self.observations())))
        correct = args.copy()
        correct[correct.index("--schedule-sha256") + 1] = digest(
            canonical_bytes(self.schedule)
        )
        correct[-1] = str(self.root / "successful-report.json")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(correct), 0)

    def test_synthetic_comparison_cli_runs_both_arms_in_frozen_order(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["analysis-comparison-demo", "--result-root", str(self.root)])
        self.assertEqual(code, 0)
        event = json.loads(out.getvalue())
        self.assertTrue(event["recorded_order_matches"])
        self.assertEqual([arm["matched_cases"] for arm in event["arms"]], [2, 2])
        root = Path(event["path"])
        schedule = ComparisonSchedule.model_validate_json(
            (root / "schedule.json").read_bytes()
        )
        inputs = EvaluationInputs.model_validate_json(
            (root / "inputs.json").read_bytes()
        )
        labels = EvaluationSuite.model_validate_json((root / "suite.json").read_bytes())
        report = assess_schedule(labels, schedule, inputs)
        self.assertTrue(report.recorded_order_matches)
        self.assertFalse(report.controlled_comparison_verified)
        self.assertEqual(len(report.timings), 4)
        self.assertEqual((root / "assessment.json").stat().st_mode & 0o777, 0o600)

    def test_synthetic_failures_remain_in_completed_assessment(self) -> None:
        out = io.StringIO()
        with (
            patch(
                "mos_eisley.analysis.comparison_demo.run_analysis",
                side_effect=ValueError("private failure"),
            ),
            redirect_stdout(out),
        ):
            code = main(["analysis-comparison-demo", "--result-root", str(self.root)])
        self.assertEqual(code, 1)
        event = json.loads(out.getvalue())
        self.assertFalse(event["recorded_order_matches"])
        self.assertEqual([arm["failed_cases"] for arm in event["arms"]], [2, 2])
        report = json.loads((Path(event["path"]) / "assessment.json").read_bytes())
        self.assertEqual(report["timing_unknown_assignments"], 4)
        self.assertNotIn("private failure", json.dumps(report))
