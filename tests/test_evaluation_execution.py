"""Blinded execution keeps labels out of requests and binds later judgments."""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.cli import main
from mos_eisley.core.models import Brief, Critique, Evidence, Finding, canonical_bytes
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    AdjudicatorProvenance,
    GradingBatch,
    Judgment,
    compile_observations,
    make_grading_batch,
)
from mos_eisley.evaluation.execution import (
    BlindingMap,
    EvaluationCassette,
    ExecutionBatch,
    RawResultSet,
    RecordedExchange,
    make_execution_batch,
    run_recorded_evaluation,
)
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvalCase,
    EvaluationDataset,
    EvaluationGate,
    ExpectedFinding,
    ObservationSet,
    RouteCandidate,
)
from mos_eisley.evaluation.scoring import make_plan, score


def inputs() -> tuple[EvaluationDataset, CandidateGrid, EvaluationGate]:
    defect = ExpectedFinding(
        id="secret-defect-label",
        category="correctness",
        description="private expected description",
    )
    data = EvaluationDataset(
        id="blind-v1",
        cases=(
            EvalCase(
                id="private-cal-defect",
                split="calibration",
                brief=Brief(spec="Return the limit.", diff="return limit - 1"),
                expected_findings=(defect,),
                risk_tags=("private-risk-tag",),
            ),
            EvalCase(
                id="private-cal-clean",
                split="calibration",
                brief=Brief(spec="Return the limit.", diff="return limit"),
            ),
            EvalCase(
                id="private-hold-defect",
                split="holdout",
                brief=Brief(spec="Include the last item.", diff="items[:-1]"),
                expected_findings=(defect,),
                risk_tags=("private-risk-tag",),
            ),
            EvalCase(
                id="private-hold-clean",
                split="holdout",
                brief=Brief(spec="Include the last item.", diff="items[:]"),
            ),
        ),
    )
    grid = CandidateGrid(
        routes=(
            RouteCandidate(
                backend="fixture",
                provider="fixture",
                model="reviewer-v1",
                effort="low",
                client_version="fixture/1",
                registry_sha256="a" * 64,
            ),
        )
    )
    gate = EvaluationGate(
        min_detection_lower_bound=0,
        max_false_positive_upper_bound=1,
        min_completion_lower_bound=0,
    )
    return data, grid, gate


def complete_cassette(
    batch_sha256: str, request_hashes: tuple[str, ...]
) -> EvaluationCassette:
    return EvaluationCassette(
        batch_sha256=batch_sha256,
        exchanges=tuple(
            RecordedExchange(
                request_sha256=request_hash,
                response=Critique(
                    findings=(
                        Finding(
                            location="last item",
                            category="correctness",
                            impact="high",
                            claim="The last item is excluded.",
                            evidence=Evidence(
                                source="diff",
                                quote="items[:-1]",
                                explanation="The slice excludes the last item.",
                            ),
                        ),
                    )
                ),
                latency_ms=12,
                cost_microusd=3,
            )
            for request_hash in request_hashes
        ),
    )


class EvaluationExecutionTests(TestCase):
    def test_grading_rejects_incomplete_or_misassigned_plans(self) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        batch, mapping = make_execution_batch(plan, data, "holdout", b"n" * 32)
        raw_results = run_recorded_evaluation(
            batch,
            complete_cassette(
                batch.batch_sha256,
                tuple(request.request_sha256 for request in batch.requests),
            ),
        )
        first = plan.assignments[0]
        variants = (
            plan.model_copy(update={"assignments": plan.assignments[1:]}),
            plan.model_copy(
                update={
                    "assignments": (
                        first.model_copy(update={"case_id": "nonexistent-case"}),
                        *plan.assignments[1:],
                    )
                }
            ),
            plan.model_copy(
                update={
                    "assignments": (
                        first.model_copy(
                            update={
                                "split": "holdout"
                                if first.split == "calibration"
                                else "calibration"
                            }
                        ),
                        *plan.assignments[1:],
                    )
                }
            ),
        )
        for variant in variants:
            with self.subTest(plan=variant.plan_sha256):
                # Validate the serialized input as the CLI would.
                modified = type(plan).model_validate_json(canonical_bytes(variant))
                with self.assertRaisesRegex(ValueError, "complete evaluation matrix"):
                    make_grading_batch(data, modified, batch, mapping, raw_results)
                with self.assertRaisesRegex(ValueError, "complete evaluation matrix"):
                    make_execution_batch(modified, data, "holdout", b"n" * 32)

    def test_grading_rejects_each_tampered_artifact_boundary(self) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        batch, mapping = make_execution_batch(plan, data, "holdout", b"n" * 32)
        raw = run_recorded_evaluation(
            batch,
            complete_cassette(
                batch.batch_sha256,
                tuple(request.request_sha256 for request in batch.requests),
            ),
        )
        variants = (
            (batch.model_copy(update={"plan_sha256": "f" * 64}), mapping, raw),
            (batch, mapping.model_copy(update={"dataset_sha256": "f" * 64}), raw),
            (batch, mapping, raw.model_copy(update={"batch_sha256": "f" * 64})),
            (batch, mapping.model_copy(update={"entries": mapping.entries[1:]}), raw),
            (batch, mapping, raw.model_copy(update={"results": raw.results[1:]})),
            (
                batch,
                mapping.model_copy(
                    update={
                        "entries": (
                            mapping.entries[0].model_copy(
                                update={"request_sha256": "f" * 64}
                            ),
                            *mapping.entries[1:],
                        )
                    }
                ),
                raw,
            ),
            (
                batch,
                mapping,
                raw.model_copy(
                    update={
                        "results": (
                            raw.results[0].model_copy(
                                update={"candidate_id": "f" * 64}
                            ),
                            *raw.results[1:],
                        )
                    }
                ),
            ),
        )
        for index, (changed_batch, changed_map, changed_raw) in enumerate(variants):
            with self.subTest(boundary=index), self.assertRaises(ValueError):
                make_grading_batch(data, plan, changed_batch, changed_map, changed_raw)

    def test_empty_critique_cannot_be_graded_as_a_detection_or_false_positive(
        self,
    ) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        batch, mapping = make_execution_batch(plan, data, "holdout", b"n" * 32)
        cassette = EvaluationCassette(
            batch_sha256=batch.batch_sha256,
            exchanges=tuple(
                RecordedExchange(
                    request_sha256=request.request_sha256,
                    response=Critique(),
                    latency_ms=1,
                )
                for request in batch.requests
            ),
        )
        raw = run_recorded_evaluation(batch, cassette)
        grading = make_grading_batch(data, plan, batch, mapping, raw)
        for detection, false_positives, message in (
            (True, 0, "empty critique"),
            (False, 1, "false-positive count"),
        ):
            adjudication = AdjudicationSet(
                grading_batch_sha256=grading.grading_batch_sha256,
                adjudicator=AdjudicatorProvenance(
                    adjudicator_id="fixture-grader",
                    method="fixture",
                    rubric_sha256="b" * 64,
                    completed_at="2026-09-05T12:00:00Z",
                ),
                judgments=tuple(
                    Judgment(
                        sample_id=item.sample_id,
                        detected_finding_ids=tuple(
                            finding.id for finding in item.expected_findings
                        )
                        if detection
                        else (),
                        false_positive_count=false_positives,
                    )
                    for item in grading.items
                ),
            )
            with (
                self.subTest(kind=message),
                self.assertRaisesRegex(ValueError, message),
            ):
                compile_observations(
                    data, plan, batch, mapping, raw, grading, adjudication
                )

    def test_batch_excludes_labels_and_compiles_provenanced_observations(self) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        batch, mapping = make_execution_batch(plan, data, "holdout", b"n" * 32)

        exposed = canonical_bytes(batch)
        for secret in (
            b"private-hold-defect",
            b"private-hold-clean",
            b"secret-defect-label",
            b"private expected description",
            b"private-risk-tag",
            b"independence_group",
            b"holdout",
        ):
            self.assertNotIn(secret, exposed)
        private = canonical_bytes(mapping)
        self.assertIn(b"private-hold-defect", private)
        self.assertIn(b"holdout", private)

        request_hashes = tuple(request.request_sha256 for request in batch.requests)
        cassette = complete_cassette(batch.batch_sha256, request_hashes)
        raw_results = run_recorded_evaluation(batch, cassette)
        self.assertNotIn(b"private-hold-defect", canonical_bytes(raw_results))

        case_by_sample = {entry.sample_id: entry.case_id for entry in mapping.entries}
        grading_batch = make_grading_batch(data, plan, batch, mapping, raw_results)
        grading_bytes = canonical_bytes(grading_batch)
        self.assertIn(b"secret-defect-label", grading_bytes)
        for hidden in (
            b"private-hold-defect",
            b"holdout",
            b"reviewer-v1",
            b"fixture/1",
        ):
            self.assertNotIn(hidden, grading_bytes)
        adjudication = AdjudicationSet(
            grading_batch_sha256=grading_batch.grading_batch_sha256,
            adjudicator=AdjudicatorProvenance(
                adjudicator_id="reviewer-01",
                method="human",
                rubric_sha256="b" * 64,
                completed_at="2026-09-05T12:00:00Z",
            ),
            judgments=tuple(
                Judgment(
                    sample_id=result.sample_id,
                    detected_finding_ids=("secret-defect-label",)
                    if case_by_sample[result.sample_id] == "private-hold-defect"
                    else (),
                )
                for result in grading_batch.items
            ),
        )
        observations = compile_observations(
            data, plan, batch, mapping, raw_results, grading_batch, adjudication
        )

        self.assertEqual(
            observations.raw_results_sha256, raw_results.raw_results_sha256
        )
        self.assertEqual(
            observations.adjudication_sha256, adjudication.adjudication_sha256
        )
        report = score(plan, data, observations, "holdout")
        self.assertFalse(report.scores[0].eligible)
        self.assertEqual(report.raw_results_sha256, raw_results.raw_results_sha256)
        self.assertEqual(report.adjudication_sha256, adjudication.adjudication_sha256)

    def test_nonce_changes_opaque_ids_without_changing_requests(self) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        first, first_map = make_execution_batch(plan, data, "holdout", b"a" * 32)
        second, second_map = make_execution_batch(plan, data, "holdout", b"b" * 32)

        self.assertNotEqual(first.batch_sha256, second.batch_sha256)
        self.assertNotEqual(
            {request.sample_id for request in first.requests},
            {request.sample_id for request in second.requests},
        )
        self.assertEqual(
            tuple(request.brief for request in first.requests),
            tuple(request.brief for request in second.requests),
        )
        self.assertNotEqual(first_map.nonce_sha256, second_map.nonce_sha256)

    def test_recorded_execution_requires_exact_request_coverage(self) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        batch, _ = make_execution_batch(plan, data, "holdout", b"n" * 32)
        incomplete = complete_cassette(
            batch.batch_sha256, (batch.requests[0].request_sha256,)
        )
        with self.assertRaisesRegex(ValueError, "exactly cover"):
            run_recorded_evaluation(batch, incomplete)

    def test_adjudication_must_bind_and_cover_completed_outputs(self) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        batch, mapping = make_execution_batch(plan, data, "holdout", b"n" * 32)
        cassette = complete_cassette(
            batch.batch_sha256,
            tuple(request.request_sha256 for request in batch.requests),
        )
        raw_results = run_recorded_evaluation(batch, cassette)
        grading_batch = make_grading_batch(data, plan, batch, mapping, raw_results)
        missing = AdjudicationSet(
            grading_batch_sha256=grading_batch.grading_batch_sha256,
            adjudicator=AdjudicatorProvenance(
                adjudicator_id="fixture-grader",
                method="fixture",
                rubric_sha256="b" * 64,
                completed_at="2026-09-05T12:00:00Z",
            ),
            judgments=(),
        )
        with self.assertRaisesRegex(ValueError, "exactly cover completed"):
            compile_observations(
                data, plan, batch, mapping, raw_results, grading_batch, missing
            )

        wrong_source = missing.model_copy(update={"grading_batch_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "grading batch"):
            compile_observations(
                data,
                plan,
                batch,
                mapping,
                raw_results,
                grading_batch,
                wrong_source,
            )

    def test_failed_execution_needs_no_content_judgment(self) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        batch, mapping = make_execution_batch(plan, data, "holdout", b"n" * 32)
        cassette = EvaluationCassette(
            batch_sha256=batch.batch_sha256,
            exchanges=tuple(
                RecordedExchange(
                    request_sha256=request.request_sha256,
                    error="timeout",
                    latency_ms=50,
                )
                for request in batch.requests
            ),
        )
        raw_results = run_recorded_evaluation(batch, cassette)
        grading_batch = make_grading_batch(data, plan, batch, mapping, raw_results)
        self.assertEqual(grading_batch.items, ())
        adjudication = AdjudicationSet(
            grading_batch_sha256=grading_batch.grading_batch_sha256,
            adjudicator=AdjudicatorProvenance(
                adjudicator_id="fixture-grader",
                method="fixture",
                rubric_sha256="b" * 64,
                completed_at="2026-09-05T12:00:00Z",
            ),
            judgments=(),
        )
        observations = compile_observations(
            data, plan, batch, mapping, raw_results, grading_batch, adjudication
        )
        self.assertTrue(
            all(item.status == "error" for item in observations.observations)
        )
        self.assertTrue(
            all(item.error == "timeout" for item in observations.observations)
        )

    def test_cli_runs_the_blind_recorded_adjudication_chain(self) -> None:
        data, grid, quality_gate = inputs()
        plan = make_plan(data, grid, 1, 7, quality_gate)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "dataset.json"
            plan_path = root / "plan.json"
            batch_path = root / "batch.json"
            mapping_path = root / "mapping.json"
            cassette_path = root / "cassette.json"
            raw_path = root / "raw.json"
            grading_path = root / "grading.json"
            adjudication_path = root / "adjudication.json"
            observations_path = root / "observations.json"
            dataset_path.write_bytes(canonical_bytes(data))
            plan_path.write_bytes(canonical_bytes(plan))

            with redirect_stdout(io.StringIO()) as output:
                exit_code = main(
                    [
                        "eval-blind",
                        "--dataset",
                        str(dataset_path),
                        "--plan",
                        str(plan_path),
                        "--split",
                        "holdout",
                        "--batch-output",
                        str(batch_path),
                        "--mapping-output",
                        str(mapping_path),
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["requests"], 2)
            batch = ExecutionBatch.model_validate_json(batch_path.read_bytes())
            mapping = BlindingMap.model_validate_json(mapping_path.read_bytes())
            self.assertNotIn(b"secret-defect-label", batch_path.read_bytes())

            cassette = complete_cassette(
                batch.batch_sha256,
                tuple(request.request_sha256 for request in batch.requests),
            )
            cassette_path.write_bytes(canonical_bytes(cassette))
            with redirect_stdout(io.StringIO()) as output:
                exit_code = main(
                    [
                        "eval-run-recorded",
                        "--batch",
                        str(batch_path),
                        "--cassette",
                        str(cassette_path),
                        "--output",
                        str(raw_path),
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["completed"], 2)
            self.assertEqual(
                len(RawResultSet.model_validate_json(raw_path.read_bytes()).results),
                2,
            )

            with redirect_stdout(io.StringIO()) as output:
                exit_code = main(
                    [
                        "eval-grade-packet",
                        "--dataset",
                        str(dataset_path),
                        "--plan",
                        str(plan_path),
                        "--batch",
                        str(batch_path),
                        "--mapping",
                        str(mapping_path),
                        "--raw-results",
                        str(raw_path),
                        "--output",
                        str(grading_path),
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["items"], 2)
            grading_batch = GradingBatch.model_validate_json(grading_path.read_bytes())
            self.assertNotIn(b"reviewer-v1", grading_path.read_bytes())

            case_by_sample = {
                entry.sample_id: entry.case_id for entry in mapping.entries
            }
            adjudication = AdjudicationSet(
                grading_batch_sha256=grading_batch.grading_batch_sha256,
                adjudicator=AdjudicatorProvenance(
                    adjudicator_id="reviewer-01",
                    method="human",
                    rubric_sha256="b" * 64,
                    completed_at="2026-09-05T12:00:00Z",
                ),
                judgments=tuple(
                    Judgment(
                        sample_id=result.sample_id,
                        detected_finding_ids=("secret-defect-label",)
                        if case_by_sample[result.sample_id] == "private-hold-defect"
                        else (),
                    )
                    for result in grading_batch.items
                ),
            )
            adjudication_path.write_bytes(canonical_bytes(adjudication))
            with redirect_stdout(io.StringIO()) as output:
                exit_code = main(
                    [
                        "eval-compile",
                        "--dataset",
                        str(dataset_path),
                        "--plan",
                        str(plan_path),
                        "--batch",
                        str(batch_path),
                        "--mapping",
                        str(mapping_path),
                        "--raw-results",
                        str(raw_path),
                        "--grading-batch",
                        str(grading_path),
                        "--adjudication",
                        str(adjudication_path),
                        "--output",
                        str(observations_path),
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["observations"], 2)
            observations = ObservationSet.model_validate_json(
                observations_path.read_bytes()
            )
            self.assertEqual(
                observations.adjudication_sha256,
                adjudication.adjudication_sha256,
            )
