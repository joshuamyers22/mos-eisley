"""Routing promotion requires pre-pinned thresholds and an independent signature."""

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
from mos_eisley.evaluation.routing_holdout import (
    FrozenPolicyHoldoutReport,
    make_holdout_use_claim,
)
from mos_eisley.evaluation.routing_promotion import (
    AuthenticatedRoutingPromotion,
    RoutingPromotionAuthorityPolicy,
    RoutingPromotionDecision,
    SignedRoutingPromotionDecision,
    authenticate_routing_promotion,
    make_routing_promotion_decision,
    sign_routing_promotion_decision,
    trusted_promotion_authority,
    verify_authenticated_routing_promotion,
)
from mos_eisley.run.store import private_write
from tests.test_routing_holdout import FrozenPolicyHoldoutTests


class RoutingPromotionTests(TestCase):
    def setUp(self) -> None:
        self.source = FrozenPolicyHoldoutTests()
        self.source.setUp()
        self.report = self.source.evaluate()
        self.authority_key = Ed25519PrivateKey.generate()
        self.authority_policy = RoutingPromotionAuthorityPolicy(
            policy_id="routing-promotion-authorities-v1",
            authorities=(
                trusted_promotion_authority(
                    "release-manager",
                    self.authority_key.public_key().public_bytes_raw(),
                ),
            ),
        )

    def signed(
        self, report: FrozenPolicyHoldoutReport | None = None
    ) -> SignedRoutingPromotionDecision:
        decision = make_routing_promotion_decision(
            report if report is not None else self.report,
            self.source.promotion_policy,
        )
        return sign_routing_promotion_decision(
            decision, "release-manager", self.authority_key.private_bytes_raw()
        )

    def authenticate(
        self, report: FrozenPolicyHoldoutReport | None = None
    ) -> AuthenticatedRoutingPromotion:
        selected = report if report is not None else self.report
        return self.authenticate_signed(self.signed(selected), report=selected)

    def authenticate_signed(
        self,
        signed: SignedRoutingPromotionDecision,
        authority_policy: RoutingPromotionAuthorityPolicy | None = None,
        report: FrozenPolicyHoldoutReport | None = None,
    ) -> AuthenticatedRoutingPromotion:
        selected = report if report is not None else self.report
        return authenticate_routing_promotion(
            self.source.dataset,
            self.source.plan,
            self.source.calibration,
            self.source.holdout,
            self.source.manifest,
            self.source.sealed,
            self.source.calibration_report,
            self.source.policy,
            self.source.claim(self.source.holdout),
            selected,
            self.source.promotion_policy,
            signed,
            authority_policy if authority_policy is not None else self.authority_policy,
        )

    def test_satisfied_thresholds_need_independent_signature_for_promotion(
        self,
    ) -> None:
        decision = make_routing_promotion_decision(
            self.report, self.source.promotion_policy
        )
        self.assertEqual(
            self.source.promotion_policy.population_unit,
            "sealed_profiles_equal_weight",
        )
        self.assertTrue(decision.criteria_satisfied)
        self.assertEqual(decision.threshold_result, "satisfied")
        self.assertFalse(decision.activation_authorized)
        self.assertNotIn("promotion_ready", RoutingPromotionDecision.model_fields)

        authenticated = self.authenticate()
        self.assertTrue(authenticated.promotion_ready)
        self.assertFalse(authenticated.activation_authorized)
        self.assertEqual(
            AuthenticatedRoutingPromotion.model_validate_json(
                canonical_bytes(authenticated)
            ),
            authenticated,
        )
        verify_authenticated_routing_promotion(
            self.source.dataset,
            self.source.plan,
            self.source.calibration,
            self.source.holdout,
            self.source.manifest,
            self.source.sealed,
            self.source.calibration_report,
            self.source.policy,
            self.source.claim(self.source.holdout),
            self.report,
            self.source.promotion_policy,
            authenticated,
            self.authority_policy,
        )

    def test_failed_or_incomplete_regret_evidence_denies_promotion(self) -> None:
        expensive = self.source.source.make_lineage(
            "holdout",
            cost_microusd_by_model={"economy": 5, "fallback": 1},
        )
        expensive_report = self.source.evaluate(expensive)
        expensive_decision = make_routing_promotion_decision(
            expensive_report, self.source.promotion_policy
        )
        self.assertFalse(expensive_decision.criteria_satisfied)
        self.assertFalse(
            next(
                item
                for item in expensive_decision.checks
                if item.name == "mean_cost_regret_microusd"
            ).passed
        )

        incomplete = self.source.source.make_lineage("holdout", "fallback")
        incomplete_report = self.source.evaluate(incomplete)
        incomplete_decision = make_routing_promotion_decision(
            incomplete_report, self.source.promotion_policy
        )
        self.assertFalse(incomplete_decision.criteria_satisfied)
        self.assertTrue(
            all(
                not item.passed and item.observed is None
                for item in incomplete_decision.checks[-2:]
            )
        )

    def test_post_holdout_threshold_change_breaks_pinned_provenance(self) -> None:
        changed = self.source.promotion_policy.model_copy(
            update={"max_mean_cost_regret_microusd": 5}
        )
        with self.assertRaisesRegex(ValueError, "decision provenance"):
            make_routing_promotion_decision(self.report, changed)
        changed_claim = make_holdout_use_claim(
            self.source.policy, changed, *self.source.holdout
        )
        self.assertNotEqual(
            changed_claim.claim_sha256,
            self.source.claim(self.source.holdout).claim_sha256,
        )

    def test_tampered_decision_signature_and_receipt_fail_closed(self) -> None:
        signed = self.signed()
        changed_check = signed.decision.checks[0].model_copy(update={"passed": False})
        changed_decision = signed.decision.model_copy(
            update={
                "checks": (changed_check, *signed.decision.checks[1:]),
                "threshold_result": "failed",
                "criteria_satisfied": False,
            }
        )
        changed_signed = sign_routing_promotion_decision(
            changed_decision,
            "release-manager",
            self.authority_key.private_bytes_raw(),
        )
        with self.assertRaisesRegex(ValueError, "differs from recomputation"):
            self.authenticate_signed(changed_signed)

        replacement = Ed25519PrivateKey.generate()
        wrong_signature = sign_routing_promotion_decision(
            signed.decision, "release-manager", replacement.private_bytes_raw()
        )
        with self.assertRaisesRegex(ValueError, "public key differs"):
            self.authenticate_signed(wrong_signature)

        receipt = self.authenticate()
        changed_receipt = receipt.model_copy(
            update={"authority_policy_sha256": "f" * 64}
        )
        with self.assertRaisesRegex(ValueError, "provenance"):
            verify_authenticated_routing_promotion(
                self.source.dataset,
                self.source.plan,
                self.source.calibration,
                self.source.holdout,
                self.source.manifest,
                self.source.sealed,
                self.source.calibration_report,
                self.source.policy,
                self.source.claim(self.source.holdout),
                self.report,
                self.source.promotion_policy,
                changed_receipt,
                self.authority_policy,
            )

    def test_promotion_authority_must_be_independent_of_evaluation(self) -> None:
        grader = self.source.calibration[5].adjudicators[0]
        overlapping = RoutingPromotionAuthorityPolicy(
            policy_id="overlapping-authority",
            authorities=(
                trusted_promotion_authority(
                    grader.adjudicator_id,
                    base64.b64decode(grader.public_key_base64),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "independent"):
            self.authenticate_signed(self.signed(), overlapping)

    def test_schema_cannot_turn_unsigned_decision_into_authorization(self) -> None:
        decision = make_routing_promotion_decision(
            self.report, self.source.promotion_policy
        )
        value = decision.model_dump(mode="json")
        value["promotion_ready"] = True
        with self.assertRaises(ValidationError):
            RoutingPromotionDecision.model_validate(value)
        receipt = self.authenticate().model_dump(mode="json")
        receipt["activation_authorized"] = True
        with self.assertRaises(ValidationError):
            AuthenticatedRoutingPromotion.model_validate(receipt)

    def test_cli_derives_then_authenticates_without_private_key_input(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            claim = self.source.claim(self.source.holdout)
            signed = self.signed()
            values: dict[str, Contract] = {
                "dataset": self.source.dataset,
                "plan": self.source.plan,
                "manifest": self.source.manifest,
                "sealed": self.source.sealed,
                "calibration_report": self.source.calibration_report,
                "candidate_policy": self.source.policy,
                "promotion_policy": self.source.promotion_policy,
                "claim": claim,
                "holdout_report": self.report,
                "signed": signed,
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
                ("calibration", self.source.calibration),
                ("holdout", self.source.holdout),
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
                            "eval-derive-routing-promotion",
                            "--promotion-policy",
                            str(paths["promotion_policy"]),
                            "--holdout-report",
                            str(paths["holdout_report"]),
                            "--output",
                            str(derived_output),
                        ]
                    ),
                    0,
                )
            self.assertFalse(json.loads(stdout.getvalue())["authenticated"])
            self.assertEqual(stat.S_IMODE(derived_output.stat().st_mode), 0o600)

            arguments = [
                "eval-authenticate-routing-promotion",
                "--dataset",
                str(paths["dataset"]),
                "--plan",
                str(paths["plan"]),
                "--feature-manifest",
                str(paths["manifest"]),
                "--sealed-study",
                str(paths["sealed"]),
                "--calibration-report",
                str(paths["calibration_report"]),
                "--candidate-policy",
                str(paths["candidate_policy"]),
                "--promotion-policy",
                str(paths["promotion_policy"]),
                "--holdout-use-claim",
                str(paths["claim"]),
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
            receipt = AuthenticatedRoutingPromotion.model_validate_json(
                output.read_bytes()
            )
            self.assertTrue(event["promotion_ready"])
            self.assertFalse(event["activation_authorized"])
            self.assertEqual(
                event["promotion_receipt_sha256"], receipt.promotion_receipt_sha256
            )
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([*arguments, "--output", str(output)]), 2)
