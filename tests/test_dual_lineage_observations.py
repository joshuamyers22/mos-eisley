"""Dual-grade observations retain a reverified source chain and cannot score."""

import base64
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
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    AdjudicatorProvenance,
    make_grading_batch,
)
from mos_eisley.evaluation.agreement import compare_adjudications
from mos_eisley.evaluation.authentication import (
    GradingTrustPolicy,
    authenticate_adjudication,
    sign_adjudication,
    trusted_adjudicator,
)
from mos_eisley.evaluation.execution import (
    make_execution_batch,
    run_recorded_evaluation,
)
from mos_eisley.evaluation.lineage import (
    DualGradedObservationSet,
    compile_dual_graded_observations,
    verify_dual_graded_observations,
)
from mos_eisley.evaluation.models import ObservationSet
from mos_eisley.evaluation.resolution import (
    ResolutionSet,
    ResolutionTrustPolicy,
    ResolvedFinding,
    resolve_authenticated_adjudications,
    sign_resolution_set,
)
from mos_eisley.evaluation.scoring import make_plan
from mos_eisley.run.store import private_write
from tests.test_evaluation_execution import (
    complete_cassette,
    grade_item,
    inputs,
)


class DualLineageObservationTests(TestCase):
    def setUp(self) -> None:
        self.dataset, grid, quality_gate = inputs()
        self.plan = make_plan(self.dataset, grid, 1, 7, quality_gate)
        self.batch, self.mapping = make_execution_batch(
            self.plan, self.dataset, "holdout", b"n" * 32
        )
        self.raw_results = run_recorded_evaluation(
            self.batch,
            complete_cassette(
                self.batch.batch_sha256,
                tuple(request.request_sha256 for request in self.batch.requests),
            ),
        )
        self.grading_batch = make_grading_batch(
            self.dataset,
            self.plan,
            self.batch,
            self.mapping,
            self.raw_results,
        )
        rubric = "b" * 64
        left_judgments = tuple(grade_item(item) for item in self.grading_batch.items)
        right_judgments = list(left_judgments)
        defect_index = next(
            index
            for index, item in enumerate(self.grading_batch.items)
            if item.expected_findings
        )
        defect = right_judgments[defect_index]
        first = defect.findings[0].model_copy(
            update={
                "disposition": "false_positive",
                "expected_finding_ids": (),
                "rationale": "Second grader considers this a false positive.",
            }
        )
        right_judgments[defect_index] = defect.model_copy(update={"findings": (first,)})
        left_grade = AdjudicationSet(
            grading_batch_sha256=self.grading_batch.grading_batch_sha256,
            adjudicator=AdjudicatorProvenance(
                adjudicator_id="grader-a",
                method="human",
                rubric_sha256=rubric,
                completed_at="2026-09-05T12:00:00Z",
            ),
            judgments=left_judgments,
        )
        right_grade = AdjudicationSet(
            grading_batch_sha256=self.grading_batch.grading_batch_sha256,
            adjudicator=AdjudicatorProvenance(
                adjudicator_id="grader-b",
                method="human",
                rubric_sha256=rubric,
                completed_at="2026-09-05T12:05:00Z",
            ),
            judgments=tuple(right_judgments),
        )
        self.left_signer = Ed25519PrivateKey.generate()
        self.right_signer = Ed25519PrivateKey.generate()
        self.resolution_signer = Ed25519PrivateKey.generate()
        self.grading_policy = GradingTrustPolicy(
            policy_id="human-grading-v1",
            rubric_sha256=rubric,
            adjudicators=(
                trusted_adjudicator(
                    "grader-a", self.left_signer.public_key().public_bytes_raw()
                ),
                trusted_adjudicator(
                    "grader-b", self.right_signer.public_key().public_bytes_raw()
                ),
            ),
        )
        self.resolution_policy = ResolutionTrustPolicy(
            policy_id="independent-resolution-v1",
            rubric_sha256=rubric,
            resolvers=(
                trusted_adjudicator(
                    "resolver-a",
                    self.resolution_signer.public_key().public_bytes_raw(),
                ),
            ),
        )
        left = authenticate_adjudication(
            self.grading_batch,
            sign_adjudication(
                left_grade, "grader-a", self.left_signer.private_bytes_raw()
            ),
            self.grading_policy,
        )
        right = authenticate_adjudication(
            self.grading_batch,
            sign_adjudication(
                right_grade, "grader-b", self.right_signer.private_bytes_raw()
            ),
            self.grading_policy,
        )
        agreement = compare_adjudications(self.grading_batch, left_grade, right_grade)
        resolution = ResolutionSet(
            grading_batch_sha256=self.grading_batch.grading_batch_sha256,
            grading_trust_policy_sha256=self.grading_policy.policy_sha256,
            resolution_trust_policy_sha256=self.resolution_policy.policy_sha256,
            left_authenticated_adjudication_sha256=(
                left.authenticated_adjudication_sha256
            ),
            right_authenticated_adjudication_sha256=(
                right.authenticated_adjudication_sha256
            ),
            agreement_report_sha256=agreement.report_sha256,
            resolver_id="resolver-a",
            rubric_sha256=rubric,
            completed_at="2026-09-05T12:10:00Z",
            resolutions=tuple(
                ResolvedFinding(
                    sample_id=conflict.sample_id,
                    judgment=conflict.left.model_copy(
                        update={"rationale": "Resolver confirms the matched defect."}
                    ),
                )
                for conflict in agreement.conflicts
            ),
        )
        self.dual_grading = resolve_authenticated_adjudications(
            self.grading_batch,
            left,
            right,
            self.grading_policy,
            self.resolution_policy,
            sign_resolution_set(
                resolution,
                "resolver-a",
                self.resolution_signer.private_bytes_raw(),
            ),
        )

    def compile(self) -> DualGradedObservationSet:
        return compile_dual_graded_observations(
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

    def verify(self, artifact: DualGradedObservationSet) -> None:
        verify_dual_graded_observations(
            self.dataset,
            self.plan,
            self.batch,
            self.mapping,
            self.raw_results,
            self.grading_batch,
            self.dual_grading,
            self.grading_policy,
            self.resolution_policy,
            artifact,
        )

    def test_compiles_resolved_labels_and_reverifies_full_lineage(self) -> None:
        artifact = self.compile()
        self.assertEqual(artifact.dataset_sha256, self.dataset.dataset_sha256)
        self.assertEqual(artifact.plan_sha256, self.plan.plan_sha256)
        self.assertEqual(artifact.execution_batch_sha256, self.batch.batch_sha256)
        self.assertEqual(artifact.mapping_sha256, self.mapping.mapping_sha256)
        self.assertEqual(
            artifact.dual_grading_resolution_sha256,
            self.dual_grading.dual_grading_resolution_sha256,
        )
        self.assertEqual(len(artifact.observations), len(self.raw_results.results))
        self.assertTrue(
            all(item.adjudication == "human" for item in artifact.observations)
        )
        defect_ids = {
            item.case_id: item.detected_finding_ids for item in artifact.observations
        }
        self.assertEqual(defect_ids["private-hold-defect"], ("secret-defect-label",))
        self.assertFalse(artifact.promotion_eligible)
        self.verify(artifact)

    def test_separate_schema_cannot_enter_the_legacy_scorer(self) -> None:
        artifact = self.compile()
        with self.assertRaises(ValidationError):
            ObservationSet.model_validate_json(canonical_bytes(artifact))

    def test_changed_source_policy_or_dual_result_fails_closed(self) -> None:
        changed_mapping = self.mapping.model_copy(update={"dataset_sha256": "f" * 64})
        changed_policy = self.resolution_policy.model_copy(
            update={"policy_id": "changed-resolution-policy"}
        )
        first = self.dual_grading.resolved_judgments[0]
        changed_dual = self.dual_grading.model_copy(
            update={
                "resolved_judgments": (
                    first.model_copy(update={"findings": ()}),
                    *self.dual_grading.resolved_judgments[1:],
                )
            }
        )
        cases = (
            (changed_mapping, self.dual_grading, self.resolution_policy),
            (self.mapping, self.dual_grading, changed_policy),
            (self.mapping, changed_dual, self.resolution_policy),
        )
        for mapping, dual, policy in cases:
            with self.subTest(policy=policy.policy_id), self.assertRaises(ValueError):
                compile_dual_graded_observations(
                    self.dataset,
                    self.plan,
                    self.batch,
                    mapping,
                    self.raw_results,
                    self.grading_batch,
                    dual,
                    self.grading_policy,
                    policy,
                )

    def test_stored_observations_are_recomputed_not_trusted(self) -> None:
        artifact = self.compile()
        first = artifact.observations[0]
        changed = artifact.model_copy(
            update={
                "observations": (
                    first.model_copy(update={"latency_ms": first.latency_ms + 1}),
                    *artifact.observations[1:],
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            self.verify(changed)
        with self.assertRaises(ValidationError):
            DualGradedObservationSet(
                dataset_sha256=self.dataset.dataset_sha256,
                plan_sha256=self.plan.plan_sha256,
                execution_batch_sha256=self.batch.batch_sha256,
                mapping_sha256=self.mapping.mapping_sha256,
                raw_results_sha256=self.raw_results.raw_results_sha256,
                grading_batch_sha256=self.grading_batch.grading_batch_sha256,
                grading_trust_policy_sha256=self.grading_policy.policy_sha256,
                resolution_trust_policy_sha256=self.resolution_policy.policy_sha256,
                dual_grading_resolution_sha256=(
                    self.dual_grading.dual_grading_resolution_sha256
                ),
                observations=(first, first),
            )

    def test_cli_writes_private_linked_artifact_without_signing_keys(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            values: dict[str, Contract] = {
                "dataset": self.dataset,
                "plan": self.plan,
                "batch": self.batch,
                "mapping": self.mapping,
                "raw": self.raw_results,
                "grading": self.grading_batch,
                "dual": self.dual_grading,
                "grading_policy": self.grading_policy,
                "resolution_policy": self.resolution_policy,
            }
            paths = {name: root / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))
            output = root / "dual-observations.json"
            arguments = [
                "eval-compile-dual",
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
                "--grading-trust-policy",
                str(paths["grading_policy"]),
                "--resolution-trust-policy",
                str(paths["resolution_policy"]),
                "--output",
                str(output),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            artifact = DualGradedObservationSet.model_validate_json(output.read_bytes())
            self.assertEqual(
                event["dual_graded_observations_sha256"],
                artifact.dual_graded_observations_sha256,
            )
            self.assertFalse(event["promotion_eligible"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.verify(artifact)
            for signer in (
                self.left_signer,
                self.right_signer,
                self.resolution_signer,
            ):
                private_key = signer.private_bytes_raw()
                self.assertNotIn(private_key, output.read_bytes())
                self.assertNotIn(base64.b64encode(private_key), output.read_bytes())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)
