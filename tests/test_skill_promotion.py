"""Skill evidence promotion requires both splits and independent signed authority."""

import base64
import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import (
    Contract,
    Critique,
    Evidence,
    Finding,
    canonical_bytes,
)
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    AdjudicatorProvenance,
    FindingJudgment,
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
from mos_eisley.evaluation.resolution import (
    ResolutionTrustPolicy,
    resolve_authenticated_adjudications,
)
from mos_eisley.evaluation.skill_comparison import (
    SkillComparisonGate,
    SkillComparisonReport,
    make_skill_holdout_use_claim,
    score_authenticated_skill_comparison,
    seal_skill_comparison,
)
from mos_eisley.evaluation.skill_promotion import (
    AuthenticatedSkillPromotion,
    SignedSkillPromotionDecision,
    SkillEvaluationLineage,
    SkillPromotionAuthorityPolicy,
    SkillPromotionDecision,
    authenticate_skill_promotion,
    make_skill_promotion_decision,
    sign_skill_promotion_decision,
    trusted_skill_promotion_authority,
    verify_authenticated_skill_promotion,
)
from mos_eisley.run.store import private_write
from tests.test_skill_comparison import SkillComparisonTests


class SkillPromotionTests(TestCase):
    def setUp(self) -> None:
        self.source = SkillComparisonTests()
        self.source.setUp()
        self.holdout: SkillEvaluationLineage = (
            self.source.batch,
            self.source.mapping,
            self.source.raw_results,
            self.source.grading_batch,
            self.source.dual_grading,
            self.source.grading_policy,
            self.source.resolution_policy,
            self.source.observations,
        )
        self.calibration = self._make_calibration_lineage()
        self.calibration_report = score_authenticated_skill_comparison(
            self.source.dataset,
            self.source.plan,
            *self.calibration,
            self.source.sealed,
            "calibration",
        )
        self.holdout_report = self.source.score()
        self.issued_at = datetime.now(UTC).replace(microsecond=0)
        self.valid_until = self.issued_at + timedelta(hours=1)
        self.authority_key = Ed25519PrivateKey.generate()
        self.authority_policy = SkillPromotionAuthorityPolicy(
            policy_id="skill-release-authorities-v1",
            valid_from=self.issued_at - timedelta(days=1),
            valid_until=self.issued_at + timedelta(days=1),
            max_decision_lifetime_seconds=3600,
            authorities=(
                trusted_skill_promotion_authority(
                    "skill-release-manager",
                    self.authority_key.public_key().public_bytes_raw(),
                ),
            ),
        )

    def _make_calibration_lineage(self) -> SkillEvaluationLineage:
        dataset = self.source.dataset
        plan = self.source.plan
        batch, mapping = make_execution_batch(plan, dataset, "calibration", b"c" * 32)
        cases = {case.id: case for case in dataset.cases}
        entries = {entry.sample_id: entry for entry in mapping.entries}
        exchanges: list[RecordedExchange] = []
        for request in batch.requests:
            entry = entries[request.sample_id]
            case = cases[entry.case_id]
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
            candidate_arm = entry.candidate_id == self.source.candidate.candidate_id
            exchanges.append(
                RecordedExchange(
                    request_sha256=request.request_sha256,
                    response=Critique(findings=findings),
                    latency_ms=6 if candidate_arm else 5,
                    cost_microusd=12 if candidate_arm else 10,
                )
            )
        raw = run_recorded_evaluation(
            batch,
            EvaluationCassette(
                batch_sha256=batch.batch_sha256,
                exchanges=tuple(exchanges),
            ),
        )
        grading = make_grading_batch(dataset, plan, batch, mapping, raw)
        judgments = tuple(
            Judgment(
                sample_id=item.sample_id,
                findings=tuple(
                    FindingJudgment(
                        finding_index=index,
                        finding_sha256=finding.finding_id,
                        disposition="matched",
                        expected_finding_ids=(item.expected_findings[0].id,),
                        rationale="The grader matched the seeded defect.",
                    )
                    for index, finding in enumerate(item.critique.findings)
                ),
            )
            for item in grading.items
        )
        rubric = "d" * 64
        left_key = Ed25519PrivateKey.generate()
        right_key = Ed25519PrivateKey.generate()
        resolver_key = Ed25519PrivateKey.generate()
        grading_policy = GradingTrustPolicy(
            policy_id="calibration-skill-graders-v1",
            rubric_sha256=rubric,
            adjudicators=(
                trusted_adjudicator(
                    "calibration-grader-left",
                    left_key.public_key().public_bytes_raw(),
                ),
                trusted_adjudicator(
                    "calibration-grader-right",
                    right_key.public_key().public_bytes_raw(),
                ),
            ),
        )
        resolution_policy = ResolutionTrustPolicy(
            policy_id="calibration-skill-resolvers-v1",
            rubric_sha256=rubric,
            resolvers=(
                trusted_adjudicator(
                    "calibration-resolver",
                    resolver_key.public_key().public_bytes_raw(),
                ),
            ),
        )
        authenticated: list[AuthenticatedAdjudication] = []
        for grader_id, completed_at, key in (
            ("calibration-grader-left", "2026-09-06T10:00:00Z", left_key),
            ("calibration-grader-right", "2026-09-06T10:05:00Z", right_key),
        ):
            adjudication = AdjudicationSet(
                grading_batch_sha256=grading.grading_batch_sha256,
                adjudicator=AdjudicatorProvenance(
                    adjudicator_id=grader_id,
                    method="human",
                    rubric_sha256=rubric,
                    completed_at=completed_at,
                ),
                judgments=judgments,
            )
            authenticated.append(
                authenticate_adjudication(
                    grading,
                    sign_adjudication(adjudication, grader_id, key.private_bytes_raw()),
                    grading_policy,
                )
            )
        dual = resolve_authenticated_adjudications(
            grading,
            authenticated[0],
            authenticated[1],
            grading_policy,
            resolution_policy,
        )
        observations = compile_dual_graded_observations(
            dataset,
            plan,
            batch,
            mapping,
            raw,
            grading,
            dual,
            grading_policy,
            resolution_policy,
        )
        return (
            batch,
            mapping,
            raw,
            grading,
            dual,
            grading_policy,
            resolution_policy,
            observations,
        )

    def decision(
        self,
        *,
        calibration_report: SkillComparisonReport | None = None,
        holdout_report: SkillComparisonReport | None = None,
        authority_policy: SkillPromotionAuthorityPolicy | None = None,
        issued_at: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> SkillPromotionDecision:
        return make_skill_promotion_decision(
            self.source.dataset,
            self.source.plan,
            self.source.sealed,
            calibration_report or self.calibration_report,
            holdout_report or self.holdout_report,
            authority_policy or self.authority_policy,
            issued_at or self.issued_at,
            valid_until or self.valid_until,
        )

    def signed(
        self,
        decision: SkillPromotionDecision | None = None,
        signer: Ed25519PrivateKey | None = None,
    ) -> SignedSkillPromotionDecision:
        return sign_skill_promotion_decision(
            decision or self.decision(),
            "skill-release-manager",
            (signer or self.authority_key).private_bytes_raw(),
        )

    def authenticate(
        self,
        *,
        signed: SignedSkillPromotionDecision | None = None,
        authority_policy: SkillPromotionAuthorityPolicy | None = None,
        at: datetime | None = None,
    ) -> AuthenticatedSkillPromotion:
        return authenticate_skill_promotion(
            self.source.dataset,
            self.source.plan,
            self.calibration,
            self.holdout,
            self.source.sealed,
            self.source.holdout_claim,
            self.calibration_report,
            self.holdout_report,
            signed or self.signed(),
            authority_policy or self.authority_policy,
            at or self.issued_at,
        )

    def test_both_split_gates_and_independent_signature_are_required(self) -> None:
        decision = self.decision()
        self.assertTrue(decision.calibration_gate_passed)
        self.assertTrue(decision.holdout_gate_passed)
        self.assertTrue(decision.criteria_satisfied)
        self.assertNotIn("promotion_ready", SkillPromotionDecision.model_fields)
        self.assertFalse(decision.activation_authorized)
        self.assertFalse(decision.configuration_mutation_authorized)

        receipt = self.authenticate()
        self.assertTrue(receipt.promotion_ready)
        self.assertFalse(receipt.activation_authorized)
        self.assertFalse(receipt.configuration_mutation_authorized)
        verify_authenticated_skill_promotion(
            self.source.dataset,
            self.source.plan,
            self.calibration,
            self.holdout,
            self.source.sealed,
            self.source.holdout_claim,
            self.calibration_report,
            self.holdout_report,
            receipt,
            self.authority_policy,
        )

    def test_failed_registered_gate_can_only_receive_denial(self) -> None:
        protocol = self.source.protocol.model_copy(
            update={
                "gate": SkillComparisonGate(
                    max_detection_regression=0,
                    max_false_positive_increase=0,
                    max_completion_regression=0,
                    max_mean_cost_increase_microusd=0,
                    max_p95_latency_increase_ms=0,
                )
            }
        )
        sealed = seal_skill_comparison(self.source.dataset, self.source.plan, protocol)
        calibration_report = score_authenticated_skill_comparison(
            self.source.dataset,
            self.source.plan,
            *self.calibration,
            sealed,
            "calibration",
        )
        claim = make_skill_holdout_use_claim(sealed, *self.holdout)
        holdout_report = score_authenticated_skill_comparison(
            self.source.dataset,
            self.source.plan,
            *self.holdout,
            sealed,
            "holdout",
            claim,
        )
        decision = make_skill_promotion_decision(
            self.source.dataset,
            self.source.plan,
            sealed,
            calibration_report,
            holdout_report,
            self.authority_policy,
            self.issued_at,
            self.valid_until,
        )
        signed = self.signed(decision)
        receipt = authenticate_skill_promotion(
            self.source.dataset,
            self.source.plan,
            self.calibration,
            self.holdout,
            sealed,
            claim,
            calibration_report,
            holdout_report,
            signed,
            self.authority_policy,
            self.issued_at,
        )
        self.assertFalse(decision.criteria_satisfied)
        self.assertFalse(receipt.promotion_ready)

    def test_expiry_wrong_key_and_evaluation_overlap_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "not current"):
            self.authenticate(at=self.valid_until)
        with self.assertRaisesRegex(ValueError, "maximum lifetime"):
            self.decision(valid_until=self.issued_at + timedelta(hours=2))

        replacement = Ed25519PrivateKey.generate()
        with self.assertRaisesRegex(ValueError, "signature key differs"):
            self.authenticate(signed=self.signed(signer=replacement))

        grader = self.calibration[5].adjudicators[0]
        overlapping = SkillPromotionAuthorityPolicy(
            policy_id="overlapping-skill-authority",
            valid_from=self.authority_policy.valid_from,
            valid_until=self.authority_policy.valid_until,
            max_decision_lifetime_seconds=3600,
            authorities=(
                trusted_skill_promotion_authority(
                    grader.adjudicator_id,
                    base64.b64decode(grader.public_key_base64),
                ),
            ),
        )
        signed = self.signed(self.decision(authority_policy=overlapping))
        with self.assertRaisesRegex(ValueError, "independent"):
            self.authenticate(signed=signed, authority_policy=overlapping)

    def test_tampering_and_authority_fields_fail_closed(self) -> None:
        signed = self.signed()
        changed = signed.decision.model_copy(
            update={"calibration_report_sha256": "f" * 64}
        )
        with self.assertRaisesRegex(ValueError, "differs from recomputation"):
            self.authenticate(signed=self.signed(changed))

        receipt = self.authenticate().model_dump(mode="json")
        receipt["activation_authorized"] = True
        with self.assertRaises(ValidationError):
            AuthenticatedSkillPromotion.model_validate_json(json.dumps(receipt))
        receipt = self.authenticate().model_dump(mode="json")
        receipt["promotion_ready"] = False
        with self.assertRaisesRegex(ValidationError, "source mismatch"):
            AuthenticatedSkillPromotion.model_validate_json(json.dumps(receipt))

    def test_cli_derives_and_authenticates_without_private_key_input(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            decision = self.decision()
            values: dict[str, Contract] = {
                "dataset": self.source.dataset,
                "plan": self.source.plan,
                "sealed": self.source.sealed,
                "claim": self.source.holdout_claim,
                "calibration_report": self.calibration_report,
                "holdout_report": self.holdout_report,
                "signed": self.signed(decision),
                "authority_policy": self.authority_policy,
            }
            lineage_names = (
                "batch",
                "mapping",
                "raw",
                "grading",
                "dual",
                "grading_policy",
                "resolution_policy",
                "observations",
            )
            for prefix, lineage in (
                ("calibration", self.calibration),
                ("holdout", self.holdout),
            ):
                values.update(
                    {
                        f"{prefix}_{name}": value
                        for name, value in zip(lineage_names, lineage, strict=True)
                    }
                )
            paths = {name: root / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))

            derived_output = root / "derived.json"
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    main(
                        [
                            "eval-derive-skill-promotion",
                            "--dataset",
                            str(paths["dataset"]),
                            "--plan",
                            str(paths["plan"]),
                            "--sealed-comparison",
                            str(paths["sealed"]),
                            "--calibration-report",
                            str(paths["calibration_report"]),
                            "--holdout-report",
                            str(paths["holdout_report"]),
                            "--authority-policy",
                            str(paths["authority_policy"]),
                            "--issued-at",
                            self.issued_at.isoformat(),
                            "--valid-until",
                            self.valid_until.isoformat(),
                            "--output",
                            str(derived_output),
                        ]
                    ),
                    0,
                )
            event = json.loads(stdout.getvalue())
            self.assertFalse(event["authenticated"])
            self.assertFalse(event["activation_authorized"])
            self.assertEqual(
                SkillPromotionDecision.model_validate_json(derived_output.read_bytes()),
                decision,
            )

            arguments = [
                "eval-authenticate-skill-promotion",
                "--dataset",
                str(paths["dataset"]),
                "--plan",
                str(paths["plan"]),
                "--sealed-comparison",
                str(paths["sealed"]),
                "--holdout-use-claim",
                str(paths["claim"]),
                "--calibration-report",
                str(paths["calibration_report"]),
                "--holdout-report",
                str(paths["holdout_report"]),
                "--signed-promotion",
                str(paths["signed"]),
                "--authority-policy",
                str(paths["authority_policy"]),
            ]
            cli_names = (
                "batch",
                "mapping",
                "raw-results",
                "grading-batch",
                "dual-grading-resolution",
                "grading-trust-policy",
                "resolution-trust-policy",
                "dual-graded-observations",
            )
            for prefix in ("calibration", "holdout"):
                for cli_name, artifact_name in zip(
                    cli_names, lineage_names, strict=True
                ):
                    arguments.extend(
                        (
                            f"--{prefix}-{cli_name}",
                            str(paths[f"{prefix}_{artifact_name}"]),
                        )
                    )
            output = root / "authenticated.json"
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main([*arguments, "--output", str(output)]), 0)
            event = json.loads(stdout.getvalue())
            receipt = AuthenticatedSkillPromotion.model_validate_json(
                output.read_bytes()
            )
            self.assertTrue(event["promotion_ready"])
            self.assertFalse(event["activation_authorized"])
            self.assertFalse(event["configuration_mutation_authorized"])
            self.assertEqual(
                event["promotion_receipt_sha256"], receipt.promotion_receipt_sha256
            )
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([*arguments, "--output", str(output)]), 2)
