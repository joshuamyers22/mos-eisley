"""Every emitted finding must be attributed; agreement never erases conflicts."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Brief, Critique, Evidence, Finding, canonical_bytes
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    AdjudicatorProvenance,
    FindingJudgment,
    GradingBatch,
    GradingItem,
    Judgment,
    validate_adjudication,
)
from mos_eisley.evaluation.agreement import AgreementReport, compare_adjudications
from mos_eisley.evaluation.models import ExpectedFinding


def packet() -> GradingBatch:
    return GradingBatch(
        dataset_sha256="a" * 64,
        mapping_sha256="b" * 64,
        raw_results_sha256="c" * 64,
        items=(
            GradingItem(
                sample_id="d" * 64,
                brief=Brief(spec="Include all items.", diff="items[:-1]"),
                expected_findings=(
                    ExpectedFinding(
                        id="boundary", category="correctness", description="Last item"
                    ),
                    ExpectedFinding(
                        id="empty", category="correctness", description="Empty input"
                    ),
                ),
                critique=Critique(
                    findings=tuple(
                        Finding(
                            location=f"line-{index}",
                            category="correctness",
                            impact="high",
                            claim=f"Claim {index}",
                            evidence=Evidence(
                                source="diff", quote="items[:-1]", explanation="Slice"
                            ),
                        )
                        for index in range(2)
                    )
                ),
            ),
        ),
    )


def ratings(batch: GradingBatch, reviewer: str = "grader-a") -> AdjudicationSet:
    return AdjudicationSet(
        grading_batch_sha256=batch.grading_batch_sha256,
        adjudicator=AdjudicatorProvenance(
            adjudicator_id=reviewer,
            method="human",
            rubric_sha256="e" * 64,
            completed_at="2026-09-05T12:00:00Z",
        ),
        judgments=tuple(
            Judgment(
                sample_id=item.sample_id,
                findings=tuple(
                    FindingJudgment(
                        finding_index=index,
                        finding_sha256=finding.finding_id,
                        disposition="matched",
                        expected_finding_ids=("boundary",),
                        rationale="Matches the boundary defect.",
                    )
                    for index, finding in enumerate(item.critique.findings)
                ),
            )
            for item in batch.items
        ),
    )


def replace_decision(
    source: AdjudicationSet, decision: FindingJudgment
) -> AdjudicationSet:
    return source.model_copy(
        update={
            "judgments": (
                source.judgments[0].model_copy(
                    update={
                        "findings": tuple(
                            decision
                            if old.finding_index == decision.finding_index
                            else old
                            for old in source.judgments[0].findings
                        )
                    }
                ),
            )
        }
    )


class FindingAdjudicationTests(TestCase):
    def test_detections_are_derived_and_duplicate_matches_do_not_double_count(
        self,
    ) -> None:
        batch = packet()
        source = ratings(batch)
        validate_adjudication(batch, source)
        self.assertEqual(source.judgments[0].detected_finding_ids, ("boundary",))
        self.assertEqual(source.judgments[0].false_positive_count, 0)
        second = (
            source.judgments[0]
            .findings[1]
            .model_copy(
                update={
                    "disposition": "duplicate",
                    "duplicate_of": 0,
                    "expected_finding_ids": (),
                }
            )
        )
        duplicate = replace_decision(source, second)
        validate_adjudication(batch, duplicate)
        self.assertEqual(duplicate.judgments[0].detected_finding_ids, ("boundary",))
        self.assertEqual(duplicate.judgments[0].false_positive_count, 0)
        false_positive = replace_decision(
            source,
            second.model_copy(
                update={"disposition": "false_positive", "duplicate_of": None}
            ),
        )
        validate_adjudication(batch, false_positive)
        self.assertEqual(false_positive.judgments[0].false_positive_count, 1)

    def test_missing_extra_changed_and_unknown_attributions_fail(self) -> None:
        batch = packet()
        source = ratings(batch)
        first = source.judgments[0].findings[0]
        variants = (
            source.model_copy(
                update={
                    "judgments": (
                        source.judgments[0].model_copy(update={"findings": (first,)}),
                    )
                }
            ),
            replace_decision(
                source, first.model_copy(update={"finding_sha256": "f" * 64})
            ),
            replace_decision(
                source, first.model_copy(update={"expected_finding_ids": ("unknown",)})
            ),
            source.model_copy(
                update={
                    "judgments": (
                        source.judgments[0].model_copy(
                            update={
                                "findings": (
                                    *source.judgments[0].findings,
                                    first.model_copy(update={"finding_index": 2}),
                                )
                            }
                        ),
                    )
                }
            ),
        )
        for index, changed in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_adjudication(batch, changed)

    def test_unresolved_cannot_compile_but_can_be_compared(self) -> None:
        batch = packet()
        source = ratings(batch)
        unresolved = replace_decision(
            source,
            source.judgments[0]
            .findings[0]
            .model_copy(
                update={"disposition": "unresolved", "expected_finding_ids": ()}
            ),
        )
        with self.assertRaisesRegex(ValueError, "unresolved"):
            validate_adjudication(batch, unresolved)
        validate_adjudication(batch, unresolved, allow_unresolved=True)
        result = compare_adjudications(batch, unresolved, ratings(batch, "grader-b"))
        self.assertEqual(result.unresolved_findings, 1)
        self.assertEqual(result.finding_agreement_rate, 0.5)
        self.assertEqual(len(result.conflicts), 1)

    def test_duplicate_cannot_point_to_an_unmatched_finding(self) -> None:
        batch = packet()
        source = ratings(batch)
        first, second = source.judgments[0].findings
        changed = replace_decision(
            source,
            first.model_copy(
                update={"disposition": "false_positive", "expected_finding_ids": ()}
            ),
        )
        changed = replace_decision(
            changed,
            second.model_copy(
                update={
                    "disposition": "duplicate",
                    "expected_finding_ids": (),
                    "duplicate_of": 0,
                }
            ),
        )
        with self.assertRaisesRegex(ValueError, "matched finding"):
            validate_adjudication(batch, changed)

    def test_schema_rejects_unbound_totals_and_contradictory_decisions(self) -> None:
        source = ratings(packet())
        value = source.model_dump(mode="json")
        value["schema_version"] = 1
        with self.assertRaises(ValidationError):
            AdjudicationSet.model_validate_json(json.dumps(value))
        with self.assertRaises(ValidationError):
            Judgment.model_validate_json(
                json.dumps(
                    {
                        "sample_id": "d" * 64,
                        "detected_finding_ids": ["boundary"],
                        "false_positive_count": 0,
                    }
                )
            )
        first = source.judgments[0].findings[0]
        variants = (
            first.model_copy(update={"expected_finding_ids": ()}),
            first.model_copy(update={"expected_finding_ids": ("boundary", "boundary")}),
            first.model_copy(update={"duplicate_of": 0}),
            first.model_copy(
                update={
                    "disposition": "duplicate",
                    "expected_finding_ids": (),
                    "duplicate_of": 0,
                }
            ),
        )
        for item in variants:
            with self.subTest(item=item), self.assertRaises(ValidationError):
                FindingJudgment.model_validate_json(canonical_bytes(item))
        with self.assertRaises(ValidationError):
            Judgment(sample_id="d" * 64, findings=(first, first))


class AgreementTests(TestCase):
    def test_agreement_ignores_rationale_but_preserves_both_sources(self) -> None:
        batch = packet()
        left, right = ratings(batch), ratings(batch, "grader-b")
        right = replace_decision(
            right,
            right.judgments[0]
            .findings[0]
            .model_copy(
                update={"rationale": "Different explanation of the same decision."}
            ),
        )
        report = compare_adjudications(batch, left, right)
        self.assertEqual(report.finding_agreement_rate, 1.0)
        self.assertEqual(report.agreed_samples, 1)
        self.assertEqual(report.conflicts, ())
        self.assertEqual(report.left_adjudication_sha256, left.adjudication_sha256)
        self.assertEqual(report.right_adjudication_sha256, right.adjudication_sha256)
        self.assertFalse(report.independence_verified)
        self.assertFalse(report.promotion_ready)
        self.assertEqual(
            AgreementReport.model_validate_json(canonical_bytes(report)), report
        )

    def test_same_disposition_with_different_defect_mapping_is_a_conflict(self) -> None:
        batch = packet()
        left, right = ratings(batch), ratings(batch, "grader-b")
        right = replace_decision(
            right,
            right.judgments[0]
            .findings[0]
            .model_copy(update={"expected_finding_ids": ("empty",)}),
        )
        report = compare_adjudications(batch, left, right)
        self.assertEqual(report.finding_agreement_rate, 0.5)
        self.assertEqual(report.agreed_samples, 0)
        self.assertEqual(report.conflicts[0].finding_index, 0)
        self.assertEqual(report.conflicts[0].right.expected_finding_ids, ("empty",))

    def test_same_grader_mixed_method_or_changed_rubric_cannot_claim_agreement(
        self,
    ) -> None:
        batch = packet()
        left = ratings(batch)
        other = ratings(batch, "grader-b")
        variants = (
            left,
            other.model_copy(
                update={
                    "adjudicator": other.adjudicator.model_copy(
                        update={"rubric_sha256": "f" * 64}
                    )
                }
            ),
            other.model_copy(
                update={
                    "adjudicator": other.adjudicator.model_copy(
                        update={"method": "fixture"}
                    )
                }
            ),
            other.model_copy(update={"grading_batch_sha256": "f" * 64}),
        )
        for right in variants:
            with self.subTest(right=right), self.assertRaises(ValueError):
                compare_adjudications(batch, left, right)

    def test_empty_outputs_do_not_claim_perfect_finding_agreement(self) -> None:
        original = packet()
        batch = original.model_copy(
            update={
                "items": (
                    original.items[0].model_copy(update={"critique": Critique()}),
                )
            }
        )
        report = compare_adjudications(
            batch, ratings(batch), ratings(batch, "grader-b")
        )
        self.assertEqual(report.compared_findings, 0)
        self.assertIsNone(report.finding_agreement_rate)
        self.assertEqual(report.agreed_samples, 1)

    def test_cli_writes_bound_report_and_refuses_overwrite(self) -> None:
        batch = packet()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("batch", batch),
                ("left", ratings(batch)),
                ("right", ratings(batch, "grader-b")),
            ):
                (root / f"{name}.json").write_bytes(canonical_bytes(value))
            args = [
                "eval-agreement",
                "--grading-batch",
                str(root / "batch.json"),
                "--left",
                str(root / "left.json"),
                "--right",
                str(root / "right.json"),
                "--output",
                str(root / "report.json"),
            ]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(args), 0)
            event = json.loads(output.getvalue())
            report = AgreementReport.model_validate_json(
                (root / "report.json").read_bytes()
            )
            self.assertEqual(event["report_sha256"], report.report_sha256)
            self.assertEqual(event["conflicts"], 0)
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 2)
