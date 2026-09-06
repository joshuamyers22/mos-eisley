"""Persona skills earn evidence only through sealed, paired comparisons."""

import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Brief, Critique, Evidence, Finding, canonical_bytes
from mos_eisley.core.skills import PromptAsset, SkillIdentity
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    AdjudicatorProvenance,
    FindingJudgment,
    GradingItem,
    Judgment,
    make_grading_batch,
)
from mos_eisley.evaluation.authentication import (
    AuthenticatedAdjudication,
    GradingTrustPolicy,
    authenticate_adjudication,
    sign_adjudication,
    trusted_adjudicator,
)
from mos_eisley.evaluation.execution import (
    EvaluationCassette,
    RecordedExchange,
    make_execution_batch,
    run_recorded_evaluation,
)
from mos_eisley.evaluation.lineage import compile_dual_graded_observations
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvalCase,
    EvaluationDataset,
    EvaluationGate,
    ExpectedFinding,
    RouteCandidate,
    StatisticalDesign,
)
from mos_eisley.evaluation.resolution import (
    ResolutionTrustPolicy,
    resolve_authenticated_adjudications,
)
from mos_eisley.evaluation.scoring import make_plan
from mos_eisley.evaluation.skill_comparison import (
    SealedSkillComparison,
    SkillComparisonGate,
    SkillComparisonProtocol,
    SkillComparisonReport,
    make_skill_holdout_use_claim,
    score_authenticated_skill_comparison,
    seal_skill_comparison,
    verify_authenticated_skill_comparison_report,
    verify_sealed_skill_comparison,
)
from mos_eisley.run.store import private_write


def _dataset() -> EvaluationDataset:
    expected = ExpectedFinding(
        id="off-by-one",
        category="correctness",
        description="The implementation drops the final item.",
    )
    cases: list[EvalCase] = []
    for split in ("calibration", "holdout"):
        for index in range(2):
            cases.append(
                EvalCase(
                    id=f"{split}-defect-{index}",
                    split=split,
                    independence_group=f"{split}-defect-group-{index}",
                    brief=Brief(
                        spec=f"Return every item for fixture {split} {index}.",
                        diff=f"return items[:-1]  # {split}-{index}",
                    ),
                    expected_findings=(expected,),
                )
            )
            cases.append(
                EvalCase(
                    id=f"{split}-clean-{index}",
                    split=split,
                    independence_group=f"{split}-clean-group-{index}",
                    brief=Brief(
                        spec=f"Return every item cleanly for {split} {index}.",
                        diff=f"return items[:]  # clean-{split}-{index}",
                    ),
                )
            )
    return EvaluationDataset(id="skill-paired-v1", cases=tuple(cases))


def _routes() -> tuple[RouteCandidate, RouteCandidate]:
    baseline = RouteCandidate(
        backend="fixture",
        provider="fixture",
        model="reviewer-v1",
        effort="medium",
        client_version="fixture/1",
        registry_sha256="a" * 64,
        prompt=PromptAsset(mode="inline", instructions="Review this change."),
    )
    candidate = baseline.model_copy(
        update={
            "prompt": PromptAsset(
                mode="skill",
                instructions="Review this change adversarially.",
                skill=SkillIdentity(
                    source="project",
                    name="adversarial-reviewer",
                    version="1.0.0",
                    kind="persona",
                    package_sha256="b" * 64,
                    instructions_sha256=(
                        PromptAsset(
                            mode="inline",
                            instructions="Review this change adversarially.",
                        ).instructions_sha256
                    ),
                ),
            )
        }
    )
    return baseline, candidate


class SkillComparisonTests(TestCase):
    def setUp(self) -> None:
        self.dataset = _dataset()
        self.baseline, self.candidate = _routes()
        gate = EvaluationGate(
            statistical_design=StatisticalDesign(min_groups_per_metric=2),
            min_detection_lower_bound=0,
            max_false_positive_upper_bound=1,
            min_completion_lower_bound=0,
        )
        self.plan = make_plan(
            self.dataset,
            CandidateGrid(routes=(self.baseline, self.candidate)),
            1,
            17,
            gate,
        )
        self.protocol = SkillComparisonProtocol(
            experiment_id="adversarial-reviewer-v1",
            dataset_sha256=self.dataset.dataset_sha256,
            plan_sha256=self.plan.plan_sha256,
            baseline_candidate_id=self.baseline.candidate_id,
            candidate_candidate_id=self.candidate.candidate_id,
            gate=SkillComparisonGate(
                max_detection_regression=1,
                max_false_positive_increase=1,
                max_completion_regression=1,
                max_mean_cost_increase_microusd=2,
                max_p95_latency_increase_ms=1,
            ),
        )
        self.sealed = seal_skill_comparison(self.dataset, self.plan, self.protocol)
        self.batch, self.mapping = make_execution_batch(
            self.plan, self.dataset, "holdout", b"s" * 32
        )
        case_by_id = {case.id: case for case in self.dataset.cases}
        entry_by_sample = {entry.sample_id: entry for entry in self.mapping.entries}
        exchanges: list[RecordedExchange] = []
        for request in self.batch.requests:
            entry = entry_by_sample[request.sample_id]
            case = case_by_id[entry.case_id]
            findings = ()
            if case.expected_findings:
                findings = (
                    Finding(
                        location="return expression",
                        category="correctness",
                        impact="high",
                        claim="The final item is excluded.",
                        evidence=Evidence(
                            source="diff",
                            quote=request.brief.diff,
                            explanation="The slice ends before the final item.",
                        ),
                    ),
                )
            candidate_arm = entry.candidate_id == self.candidate.candidate_id
            exchanges.append(
                RecordedExchange(
                    request_sha256=request.request_sha256,
                    response=Critique(findings=findings),
                    latency_ms=6 if candidate_arm else 5,
                    cost_microusd=12 if candidate_arm else 10,
                )
            )
        cassette = EvaluationCassette(
            batch_sha256=self.batch.batch_sha256,
            exchanges=tuple(exchanges),
        )
        self.raw_results = run_recorded_evaluation(self.batch, cassette)
        self.grading_batch = make_grading_batch(
            self.dataset,
            self.plan,
            self.batch,
            self.mapping,
            self.raw_results,
        )
        judgments = tuple(self._judgment(item) for item in self.grading_batch.items)
        rubric = "c" * 64
        left_key = Ed25519PrivateKey.generate()
        right_key = Ed25519PrivateKey.generate()
        resolver_key = Ed25519PrivateKey.generate()
        self.grading_policy = GradingTrustPolicy(
            policy_id="skill-graders-v1",
            rubric_sha256=rubric,
            adjudicators=(
                trusted_adjudicator(
                    "grader-left", left_key.public_key().public_bytes_raw()
                ),
                trusted_adjudicator(
                    "grader-right", right_key.public_key().public_bytes_raw()
                ),
            ),
        )
        self.resolution_policy = ResolutionTrustPolicy(
            policy_id="skill-resolvers-v1",
            rubric_sha256=rubric,
            resolvers=(
                trusted_adjudicator(
                    "resolver", resolver_key.public_key().public_bytes_raw()
                ),
            ),
        )
        signed: list[AuthenticatedAdjudication] = []
        for grader_id, completed_at, key in (
            ("grader-left", "2026-09-05T12:00:00Z", left_key),
            ("grader-right", "2026-09-05T12:05:00Z", right_key),
        ):
            adjudication = AdjudicationSet(
                grading_batch_sha256=self.grading_batch.grading_batch_sha256,
                adjudicator=AdjudicatorProvenance(
                    adjudicator_id=grader_id,
                    method="human",
                    rubric_sha256=rubric,
                    completed_at=completed_at,
                ),
                judgments=judgments,
            )
            signed.append(
                authenticate_adjudication(
                    self.grading_batch,
                    sign_adjudication(adjudication, grader_id, key.private_bytes_raw()),
                    self.grading_policy,
                )
            )
        self.dual_grading = resolve_authenticated_adjudications(
            self.grading_batch,
            signed[0],
            signed[1],
            self.grading_policy,
            self.resolution_policy,
        )
        self.observations = compile_dual_graded_observations(
            self.dataset,
            self.plan,
            self.batch,
            self.mapping,
            self.raw_results,
            self.grading_batch,
            self.dual_grading,
            self.grading_policy,
            self.resolution_policy,
        )
        self.holdout_claim = make_skill_holdout_use_claim(
            self.sealed,
            self.batch,
            self.mapping,
            self.raw_results,
            self.grading_batch,
            self.dual_grading,
            self.grading_policy,
            self.resolution_policy,
            self.observations,
        )

    @staticmethod
    def _judgment(item: GradingItem) -> Judgment:
        return Judgment(
            sample_id=item.sample_id,
            findings=tuple(
                FindingJudgment(
                    finding_index=index,
                    finding_sha256=finding.finding_id,
                    disposition="matched",
                    expected_finding_ids=(item.expected_findings[0].id,),
                    rationale="Both human fixture graders matched the seeded defect.",
                )
                for index, finding in enumerate(item.critique.findings)
            ),
        )

    def score(self) -> SkillComparisonReport:
        return score_authenticated_skill_comparison(
            self.dataset,
            self.plan,
            self.batch,
            self.mapping,
            self.raw_results,
            self.grading_batch,
            self.dual_grading,
            self.grading_policy,
            self.resolution_policy,
            self.observations,
            self.sealed,
            "holdout",
            self.holdout_claim,
        )

    def test_seals_only_an_exact_prompt_controlled_skill_arm(self) -> None:
        self.assertEqual(
            self.sealed.candidate_prompt_sha256,
            self.candidate.prompt.prompt_sha256,
        )
        self.assertNotEqual(
            self.sealed.baseline_prompt_sha256,
            self.sealed.candidate_prompt_sha256,
        )
        self.assertFalse(self.sealed.activation_authorized)
        verify_sealed_skill_comparison(self.dataset, self.plan, self.sealed)

        for candidate in (
            self.candidate.model_copy(update={"model": "reviewer-v2"}),
            self.candidate.model_copy(
                update={
                    "prompt": PromptAsset(
                        mode="inline", instructions="Different inline prompt."
                    )
                }
            ),
        ):
            plan = make_plan(
                self.dataset,
                CandidateGrid(routes=(self.baseline, candidate)),
                1,
                17,
                self.plan.gate,
            )
            protocol = self.protocol.model_copy(
                update={
                    "plan_sha256": plan.plan_sha256,
                    "candidate_candidate_id": candidate.candidate_id,
                }
            )
            with (
                self.subTest(candidate=candidate.candidate_id),
                self.assertRaises(ValueError),
            ):
                seal_skill_comparison(self.dataset, plan, protocol)

    def test_rejects_underpowered_or_changed_sealed_inputs(self) -> None:
        grouped = self.dataset.model_copy(
            update={
                "cases": tuple(
                    case.model_copy(
                        update={
                            "independence_group": (
                                f"{case.split}-defect"
                                if case.expected_findings
                                else f"{case.split}-clean"
                            )
                        }
                    )
                    for case in self.dataset.cases
                )
            }
        )
        plan = make_plan(
            grouped,
            CandidateGrid(routes=(self.baseline, self.candidate)),
            1,
            17,
            self.plan.gate,
        )
        protocol = self.protocol.model_copy(
            update={
                "dataset_sha256": grouped.dataset_sha256,
                "plan_sha256": plan.plan_sha256,
            }
        )
        with self.assertRaisesRegex(ValueError, "too few independent groups"):
            seal_skill_comparison(grouped, plan, protocol)
        changed = self.sealed.model_copy(update={"candidate_prompt_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            verify_sealed_skill_comparison(self.dataset, self.plan, changed)

    def test_scores_paired_group_deltas_but_cannot_promote_or_activate(self) -> None:
        report = self.score()
        self.assertEqual(report.detection_delta.estimate, 0)
        self.assertEqual(report.clean_false_positive_delta.estimate, 0)
        self.assertEqual(report.completion_delta.estimate, 0)
        self.assertEqual(report.mean_cost_delta_microusd, 2)
        self.assertEqual(report.paired_cost_coverage, 1)
        self.assertEqual(report.p95_latency_delta_ms, 1)
        self.assertTrue(report.passes_registered_gate)
        self.assertFalse(report.promotion_ready)
        self.assertFalse(report.activation_authorized)
        verify_authenticated_skill_comparison_report(
            self.dataset,
            self.plan,
            self.batch,
            self.mapping,
            self.raw_results,
            self.grading_batch,
            self.dual_grading,
            self.grading_policy,
            self.resolution_policy,
            self.observations,
            self.sealed,
            self.holdout_claim,
            report,
        )

        serialized = json.loads(canonical_bytes(report))
        serialized["passes_registered_gate"] = False
        with self.assertRaisesRegex(ValidationError, "gate result is inconsistent"):
            SkillComparisonReport.model_validate(serialized)
        serialized = json.loads(canonical_bytes(report))
        serialized["passes_detection_noninferiority"] = False
        with self.assertRaisesRegex(ValidationError, "component gate"):
            SkillComparisonReport.model_validate(serialized)

    def test_full_lineage_tampering_fails_before_comparison(self) -> None:
        changed = self.raw_results.model_copy(update={"batch_sha256": "f" * 64})
        with self.assertRaises(ValueError):
            score_authenticated_skill_comparison(
                self.dataset,
                self.plan,
                self.batch,
                self.mapping,
                changed,
                self.grading_batch,
                self.dual_grading,
                self.grading_policy,
                self.resolution_policy,
                self.observations,
                self.sealed,
                "holdout",
                self.holdout_claim,
            )

    def test_cli_seals_and_scores_private_nonactivating_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            values = {
                "dataset": self.dataset,
                "plan": self.plan,
                "protocol": self.protocol,
                "batch": self.batch,
                "mapping": self.mapping,
                "raw": self.raw_results,
                "grading": self.grading_batch,
                "dual": self.dual_grading,
                "observations": self.observations,
                "grading-policy": self.grading_policy,
                "resolution-policy": self.resolution_policy,
            }
            paths = {name: root / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))
            sealed_path = root / "sealed.json"
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    main(
                        [
                            "eval-seal-skill-comparison",
                            "--dataset",
                            str(paths["dataset"]),
                            "--plan",
                            str(paths["plan"]),
                            "--protocol",
                            str(paths["protocol"]),
                            "--output",
                            str(sealed_path),
                        ]
                    ),
                    0,
                )
            seal_event = json.loads(stdout.getvalue())
            self.assertFalse(seal_event["activation_authorized"])
            sealed = SealedSkillComparison.model_validate_json(sealed_path.read_bytes())
            self.assertEqual(sealed, self.sealed)

            output = root / "report.json"
            claim_directory = root / "claims"
            claim_directory.mkdir(mode=0o700)
            arguments = [
                "eval-score-skill-comparison",
                "--dataset",
                str(paths["dataset"]),
                "--plan",
                str(paths["plan"]),
                "--batch",
                str(paths["batch"]),
                "--mapping",
                str(paths["mapping"]),
                "--raw-results",
                str(paths["raw"]),
                "--grading-batch",
                str(paths["grading"]),
                "--dual-grading-resolution",
                str(paths["dual"]),
                "--dual-graded-observations",
                str(paths["observations"]),
                "--grading-trust-policy",
                str(paths["grading-policy"]),
                "--resolution-trust-policy",
                str(paths["resolution-policy"]),
                "--sealed-comparison",
                str(sealed_path),
                "--holdout-use-directory",
                str(claim_directory),
                "--split",
                "holdout",
                "--output",
                str(output),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            report = SkillComparisonReport.model_validate_json(output.read_bytes())
            self.assertEqual(
                event["skill_comparison_report_sha256"],
                report.skill_comparison_report_sha256,
            )
            self.assertFalse(event["promotion_ready"])
            self.assertFalse(event["activation_authorized"])
            self.assertTrue(Path(event["claim_path"]).is_file())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            output.unlink()
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)
