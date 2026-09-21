"""G3 policy sealing uses independently signed metadata, never held-out sessions."""

import io
import json
import stat
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.evaluation.authentication import (
    GradingTrustPolicy,
    trusted_adjudicator,
)
from mos_eisley.evaluation.context_study import (
    BaselineAblationPolicy,
    ContextPolicyArm,
    EligibleLabelInventory,
    IndependentLabelCatalog,
    IndependentLabelClaim,
    IndependentLabelEvidence,
    SealedBaselineAblationPolicy,
    inventory_independent_labels,
    seal_baseline_ablation_policy,
    sign_independent_label_claim,
    verify_eligible_label_inventory,
    verify_sealed_baseline_ablation_policy,
)

RUBRIC = "a" * 64
TARGET_COMPONENTS = (
    "bounded_work_units",
    "explicit_checkpoints",
    "narrow_tool_views",
    "task_profiles",
)


def trust_inputs() -> tuple[GradingTrustPolicy, bytes, bytes]:
    left_key = bytes(range(32))
    right_key = bytes(range(1, 33))
    policy = GradingTrustPolicy(
        policy_id="g3-label-graders",
        rubric_sha256=RUBRIC,
        adjudicators=(
            trusted_adjudicator(
                "grader-left",
                Ed25519PrivateKey.from_private_bytes(left_key)
                .public_key()
                .public_bytes_raw(),
            ),
            trusted_adjudicator(
                "grader-right",
                Ed25519PrivateKey.from_private_bytes(right_key)
                .public_key()
                .public_bytes_raw(),
            ),
        ),
    )
    return policy, left_key, right_key


def label_claim(
    case_id: str,
    grader_id: str,
    *,
    split: str,
    label_class: str,
    source: str,
    sampling_frame: str,
    selection_probability_ppm: int | None = 500_000,
    label_observation_probability_ppm: int | None = 900_000,
) -> IndependentLabelClaim:
    opaque_case_id = digest(case_id.encode())
    return IndependentLabelClaim.model_validate(
        {
            "case_id": opaque_case_id,
            "split": split,
            "case_artifact_sha256": digest(f"artifact-{case_id}".encode()),
            "independence_group": digest(f"group-{case_id}".encode()),
            "label_class": label_class,
            "expected_finding_count": 0 if label_class == "clean" else 1,
            "source": source,
            "sampling_frame": sampling_frame,
            "sampling_manifest_sha256": "d" * 64,
            "selection_probability_ppm": selection_probability_ppm,
            "label_observation_probability_ppm": (label_observation_probability_ppm),
            "rubric_sha256": RUBRIC,
            "grader_id": grader_id,
            "completed_at": "2026-09-21T12:00:00Z",
        }
    )


def evidence_pair(
    case_id: str,
    *,
    split: str,
    label_class: str,
    source: str,
    sampling_frame: str,
    selection_probability_ppm: int | None = 500_000,
    label_observation_probability_ppm: int | None = 900_000,
) -> IndependentLabelEvidence:
    _, left_key, right_key = trust_inputs()
    left = label_claim(
        case_id,
        "grader-left",
        split=split,
        label_class=label_class,
        source=source,
        sampling_frame=sampling_frame,
        selection_probability_ppm=selection_probability_ppm,
        label_observation_probability_ppm=label_observation_probability_ppm,
    )
    right = left.model_copy(update={"grader_id": "grader-right"})
    return IndependentLabelEvidence(
        left=sign_independent_label_claim(left, left_key),
        right=sign_independent_label_claim(right, right_key),
    )


def complete_catalog(policy: GradingTrustPolicy) -> IndependentLabelCatalog:
    evidence = (
        evidence_pair(
            "cal-clean",
            split="calibration",
            label_class="clean",
            source="ordinary_task",
            sampling_frame="random_ordinary_audit",
        ),
        evidence_pair(
            "cal-defect",
            split="calibration",
            label_class="defective",
            source="seeded_mutant",
            sampling_frame="selected_challenge",
        ),
        evidence_pair(
            "hold-clean",
            split="holdout",
            label_class="clean",
            source="ordinary_task",
            sampling_frame="random_ordinary_audit",
        ),
        evidence_pair(
            "hold-defect",
            split="holdout",
            label_class="defective",
            source="historical_bug",
            sampling_frame="historical_case",
        ),
    )
    return IndependentLabelCatalog(
        grading_trust_policy_sha256=policy.policy_sha256,
        evidence=tuple(sorted(evidence, key=lambda item: item.left.claim.case_id)),
    )


def baseline_policy(inventory: EligibleLabelInventory) -> BaselineAblationPolicy:
    arms = [
        ContextPolicyArm(
            arm_id="arm-baseline",
            kind="baseline",
            implementation_sha256="1" * 64,
            enabled_components=("existing_selection",),
        ),
        ContextPolicyArm(
            arm_id="arm-full",
            kind="full_candidate",
            implementation_sha256="2" * 64,
            enabled_components=TARGET_COMPONENTS,
        ),
    ]
    for index, component in enumerate(TARGET_COMPONENTS, start=3):
        unavailable = component == "task_profiles"
        arms.append(
            ContextPolicyArm(
                arm_id=f"arm-without-{component.replace('_', '-')}",
                kind="ablation",
                availability="unavailable" if unavailable else "available",
                implementation_sha256=None if unavailable else str(index) * 64,
                enabled_components=tuple(
                    item for item in TARGET_COMPONENTS if item != component
                ),
                parent_arm_id="arm-full",
                ablated_component=component,
                unavailable_reason="not-yet-instrumented" if unavailable else None,
            )
        )
    return BaselineAblationPolicy(
        study_id="g3-context-policy-v1",
        model_routes_sha256="b" * 64,
        rubric_sha256=RUBRIC,
        quality_gate_sha256="e" * 64,
        resource_plan_sha256="c" * 64,
        label_inventory_sha256=inventory.inventory_sha256,
        randomization_seed=21,
        follow_up_window_days=30,
        baseline_arm_id="arm-baseline",
        full_candidate_arm_id="arm-full",
        arms=tuple(sorted(arms, key=lambda item: item.arm_id)),
    )


class ContextStudyTests(TestCase):
    def setUp(self) -> None:
        self.trust_policy, _, _ = trust_inputs()
        self.catalog = complete_catalog(self.trust_policy)
        self.inventory = inventory_independent_labels(self.catalog, self.trust_policy)

    def test_inventory_is_metadata_only_and_counts_both_splits(self) -> None:
        inventory = self.inventory
        self.assertEqual(len(inventory.eligible), 4)
        self.assertEqual(len(inventory.excluded), 0)
        self.assertEqual(inventory.calibration_clean, 1)
        self.assertEqual(inventory.calibration_defective, 1)
        self.assertEqual(inventory.holdout_clean, 1)
        self.assertEqual(inventory.holdout_defective, 1)
        self.assertEqual(inventory.calibration_random_ordinary_audit, 1)
        self.assertEqual(inventory.holdout_random_ordinary_audit, 1)
        self.assertFalse(inventory.holdout_sessions_inspected)
        self.assertFalse(inventory.session_outcomes_included)
        self.assertFalse(inventory.study_execution_authorized)
        payload = json.loads(canonical_bytes(inventory))
        self.assertNotIn("brief", json.dumps(payload))
        self.assertNotIn("expected_findings", json.dumps(payload))

    def test_disagreement_and_unknown_probabilities_are_ineligible(self) -> None:
        pair = evidence_pair(
            "cal-clean",
            split="calibration",
            label_class="clean",
            source="ordinary_task",
            sampling_frame="random_ordinary_audit",
        )
        _, _, right_key = trust_inputs()
        disagreeing = pair.right.claim.model_copy(
            update={"label_class": "defective", "expected_finding_count": 1}
        )
        disagreement = pair.model_copy(
            update={"right": sign_independent_label_claim(disagreeing, right_key)}
        )
        unknown = evidence_pair(
            "hold-clean",
            split="holdout",
            label_class="clean",
            source="ordinary_task",
            sampling_frame="random_ordinary_audit",
            selection_probability_ppm=None,
            label_observation_probability_ppm=None,
        )
        catalog = IndependentLabelCatalog(
            grading_trust_policy_sha256=self.trust_policy.policy_sha256,
            evidence=tuple(
                sorted(
                    (disagreement, unknown),
                    key=lambda item: item.left.claim.case_id,
                )
            ),
        )
        inventory = inventory_independent_labels(catalog, self.trust_policy)
        self.assertEqual(inventory.eligible, ())
        exclusions = {item.case_id: item.reasons for item in inventory.excluded}
        self.assertEqual(
            exclusions[disagreement.left.claim.case_id], ("grader_disagreement",)
        )
        self.assertEqual(
            exclusions[unknown.left.claim.case_id],
            (
                "label_observation_probability_unknown",
                "selection_probability_unknown",
            ),
        )

    def test_untrusted_or_tampered_receipts_fail_closed(self) -> None:
        first, second, *rest = self.catalog.evidence
        changed_left = first.left.model_copy(
            update={"signature": second.left.signature}
        )
        changed = first.model_copy(update={"left": changed_left})
        catalog = self.catalog.model_copy(update={"evidence": (changed, second, *rest)})
        with self.assertRaisesRegex(ValueError, "signature"):
            inventory_independent_labels(catalog, self.trust_policy)

        with self.assertRaisesRegex(ValidationError, "distinct grader"):
            IndependentLabelEvidence(left=first.left, right=first.left)

    def test_claim_catalog_inventory_and_arm_invariants_fail_closed(self) -> None:
        clean = label_claim(
            "cal-clean",
            "grader-left",
            split="calibration",
            label_class="clean",
            source="ordinary_task",
            sampling_frame="random_ordinary_audit",
        ).model_dump()
        variants = (
            ({**clean, "expected_finding_count": 1}, "zero expected"),
            ({**clean, "completed_at": "2026-02-30T00:00:00Z"}, "valid UTC"),
            (
                {**clean, "sampling_frame": "historical_case"},
                "ordinary-task sampling",
            ),
            (
                {
                    **clean,
                    "source": "seeded_mutant",
                    "sampling_frame": "random_ordinary_audit",
                },
                "selected-challenge",
            ),
            (
                {
                    **clean,
                    "source": "historical_bug",
                    "sampling_frame": "selected_challenge",
                },
                "historical sampling",
            ),
            (
                {
                    **clean,
                    "source": "seeded_mutant",
                    "sampling_frame": "selected_challenge",
                },
                "must be defective",
            ),
        )
        for values, message in variants:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValidationError, message),
            ):
                IndependentLabelClaim.model_validate(values)

        first, second, *_ = self.catalog.evidence
        with self.assertRaisesRegex(ValidationError, "unique"):
            IndependentLabelCatalog(
                grading_trust_policy_sha256=self.trust_policy.policy_sha256,
                evidence=(first, first),
            )
        with self.assertRaisesRegex(ValidationError, "sorted"):
            IndependentLabelCatalog(
                grading_trust_policy_sha256=self.trust_policy.policy_sha256,
                evidence=(second, first),
            )
        inventory_values = self.inventory.model_dump()
        inventory_values["holdout_clean"] = 2
        with self.assertRaisesRegex(ValidationError, "counts"):
            EligibleLabelInventory.model_validate(inventory_values)

        arm_values = baseline_policy(self.inventory).arms[0].model_dump()
        arm_values["implementation_sha256"] = None
        with self.assertRaisesRegex(ValidationError, "available arms"):
            ContextPolicyArm.model_validate(arm_values)
        arm_values = baseline_policy(self.inventory).arms[-1].model_dump()
        arm_values["availability"] = "unavailable"
        arm_values["unavailable_reason"] = None
        with self.assertRaisesRegex(ValidationError, "unavailable arms"):
            ContextPolicyArm.model_validate(arm_values)

    def test_policy_seals_complete_arms_without_granting_authority(self) -> None:
        policy = baseline_policy(self.inventory)
        sealed = seal_baseline_ablation_policy(
            policy, self.catalog, self.trust_policy, self.inventory
        )
        self.assertEqual(sealed.eligible_label_count, 4)
        self.assertIn("arm-without-task-profiles", sealed.unavailable_arm_ids)
        self.assertFalse(sealed.holdout_sessions_inspected)
        self.assertFalse(sealed.study_execution_authorized)
        self.assertFalse(sealed.promotion_ready)
        verify_sealed_baseline_ablation_policy(
            self.catalog, self.trust_policy, self.inventory, sealed
        )
        self.assertEqual(
            SealedBaselineAblationPolicy.model_validate_json(canonical_bytes(sealed)),
            sealed,
        )

        changed = sealed.model_copy(update={"eligible_label_count": 5})
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            verify_sealed_baseline_ablation_policy(
                self.catalog, self.trust_policy, self.inventory, changed
            )

    def test_seal_rejects_incomplete_label_coverage_or_wrong_inventory(self) -> None:
        partial_catalog = self.catalog.model_copy(
            update={"evidence": self.catalog.evidence[:-1]}
        )
        partial = inventory_independent_labels(partial_catalog, self.trust_policy)
        policy = baseline_policy(partial)
        with self.assertRaisesRegex(ValueError, "both splits"):
            seal_baseline_ablation_policy(
                policy, partial_catalog, self.trust_policy, partial
            )
        with self.assertRaisesRegex(ValueError, "does not match"):
            seal_baseline_ablation_policy(
                baseline_policy(self.inventory),
                partial_catalog,
                self.trust_policy,
                partial,
            )

    def test_inventory_must_replay_signed_provenance_before_sealing(self) -> None:
        changed = self.inventory.model_copy(update={"catalog_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            verify_eligible_label_inventory(self.catalog, self.trust_policy, changed)
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            seal_baseline_ablation_policy(
                baseline_policy(changed), self.catalog, self.trust_policy, changed
            )

    def test_policy_requires_every_single_component_ablation(self) -> None:
        policy = baseline_policy(self.inventory)
        values = policy.model_dump()
        values["arms"][-1]["ablated_component"] = "bounded_work_units"
        values["arms"][-1]["enabled_components"] = tuple(
            item for item in TARGET_COMPONENTS if item != "bounded_work_units"
        )
        with self.assertRaisesRegex(ValidationError, "one ablation per component"):
            BaselineAblationPolicy.model_validate(values)

        values = policy.model_dump()
        values["outcome_metrics"] = values["outcome_metrics"][:-1]
        with self.assertRaisesRegex(ValidationError, "complete outcome"):
            BaselineAblationPolicy.model_validate(values)

        values = policy.model_dump()
        ablation = next(item for item in values["arms"] if item["kind"] == "ablation")
        ablation["parent_arm_id"] = "arm-baseline"
        with self.assertRaisesRegex(ValidationError, "remove exactly one"):
            BaselineAblationPolicy.model_validate(values)

    def test_cli_writes_private_inventory_and_seal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "catalog.json"
            trust_path = root / "trust.json"
            inventory_path = root / "private" / "inventory.json"
            catalog_path.write_bytes(canonical_bytes(self.catalog))
            trust_path.write_bytes(canonical_bytes(self.trust_policy))
            with redirect_stdout(io.StringIO()) as stdout:
                result = main(
                    [
                        "eval-inventory-labels",
                        "--catalog",
                        str(catalog_path),
                        "--grading-trust-policy",
                        str(trust_path),
                        "--output",
                        str(inventory_path),
                    ]
                )
            self.assertEqual(result, 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["eligible"], 4)
            self.assertFalse(event["holdout_sessions_inspected"])
            self.assertEqual(stat.S_IMODE(inventory_path.stat().st_mode), 0o600)

            policy = baseline_policy(self.inventory)
            policy_path = root / "policy.json"
            sealed_path = root / "private" / "sealed.json"
            policy_path.write_bytes(canonical_bytes(policy))
            with redirect_stdout(io.StringIO()) as stdout:
                result = main(
                    [
                        "eval-seal-context-policy",
                        "--policy",
                        str(policy_path),
                        "--catalog",
                        str(catalog_path),
                        "--grading-trust-policy",
                        str(trust_path),
                        "--label-inventory",
                        str(inventory_path),
                        "--output",
                        str(sealed_path),
                    ]
                )
            self.assertEqual(result, 0)
            event = json.loads(stdout.getvalue())
            sealed = SealedBaselineAblationPolicy.model_validate_json(
                sealed_path.read_bytes()
            )
            self.assertEqual(event["sealed_policy_sha256"], sealed.sealed_policy_sha256)
            self.assertFalse(event["study_execution_authorized"])
            self.assertEqual(stat.S_IMODE(sealed_path.stat().st_mode), 0o600)
