"""Activation eligibility is fresh, revocable, exact-route, and non-executing."""

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
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.evaluation.routing_activation import (
    RouteOperationalEvidence,
    RouteOperationalRequirement,
    RoutingActivationAuthorityPolicy,
    RoutingActivationControlState,
    RoutingActivationEligibility,
    RoutingActivationPolicy,
    RoutingOperationalSnapshot,
    SignedRoutingActivationControl,
    SignedRoutingActivationPolicy,
    SignedRoutingOperationalSnapshot,
    issue_routing_activation_eligibility,
    sign_routing_activation_control,
    sign_routing_activation_policy,
    sign_routing_operational_snapshot,
    trusted_activation_authority,
    verify_routing_activation_eligibility,
)
from mos_eisley.run.activation_control import RoutingControlAnchorPolicy
from mos_eisley.run.store import private_write
from tests.test_routing_promotion import RoutingPromotionTests


class RoutingActivationTests(TestCase):
    def setUp(self) -> None:
        self.source = RoutingPromotionTests()
        self.source.setUp()
        self.promotion = self.source.authenticate()
        self.now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
        self.policy_key = Ed25519PrivateKey.generate()
        self.ops_key = Ed25519PrivateKey.generate()
        self.control_key = Ed25519PrivateKey.generate()
        self.authority_policy = RoutingActivationAuthorityPolicy(
            policy_id="routing-activation-authorities-v1",
            authorities=tuple(
                sorted(
                    (
                        trusted_activation_authority(
                            "activation-policy-manager",
                            self.policy_key.public_key().public_bytes_raw(),
                        ),
                        trusted_activation_authority(
                            "ops-manager",
                            self.ops_key.public_key().public_bytes_raw(),
                        ),
                        trusted_activation_authority(
                            "control-manager",
                            self.control_key.public_key().public_bytes_raw(),
                        ),
                    ),
                    key=lambda item: item.authority_id,
                )
            ),
        )
        self.control_anchor_policy = RoutingControlAnchorPolicy(
            anchor_id="e" * 64,
            activation_authority_policy_sha256=self.authority_policy.policy_sha256,
            control_authority_ids=("control-manager",),
        )
        routes = {route.candidate_id: route for route in self.source.source.plan.routes}
        required_ids = {
            item.selected_candidate_id
            for item in self.source.source.policy.decisions
            if item.selected_candidate_id is not None
        } | {item.fallback_candidate_id for item in self.source.source.policy.decisions}
        self.requirements = tuple(
            RouteOperationalRequirement(
                candidate_id=candidate_id,
                route=routes[candidate_id],
                pricing_basis="normalized-evaluation-request-v1",
                max_normalized_cost_microusd=10,
            )
            for candidate_id in sorted(required_ids)
        )
        self.activation_policy = RoutingActivationPolicy(
            policy_id="routing-activation-v1",
            candidate_policy_sha256=(self.source.source.policy.candidate_policy_sha256),
            promotion_receipt_sha256=self.promotion.promotion_receipt_sha256,
            control_anchor_policy_sha256=self.control_anchor_policy.policy_sha256,
            valid_from=self.now - timedelta(minutes=5),
            valid_until=self.now + timedelta(hours=1),
            max_evidence_age_seconds=900,
            max_eligibility_lifetime_seconds=600,
            max_runtime_preflight_age_seconds=30,
            minimum_control_sequence=7,
            unavailable_action="role_fallback",
            route_requirements=self.requirements,
        )
        evidence = tuple(
            RouteOperationalEvidence(
                candidate_id=item.candidate_id,
                route=item.route,
                pricing_basis=item.pricing_basis,
                normalized_cost_microusd=5,
                catalog_status="available",
                catalog_evidence_sha256="a" * 64,
                pricing_evidence_sha256="b" * 64,
                conformance_status="passed",
                conformance_evidence_sha256="c" * 64,
                drift_status="passed",
                drift_evidence_sha256="d" * 64,
                observed_at=self.now - timedelta(minutes=1),
                valid_until=self.now + timedelta(minutes=30),
            )
            for item in self.requirements
        )
        self.snapshot = RoutingOperationalSnapshot(
            candidate_policy_sha256=(self.source.source.policy.candidate_policy_sha256),
            promotion_receipt_sha256=self.promotion.promotion_receipt_sha256,
            activation_policy_sha256=self.activation_policy.activation_policy_sha256,
            routes=evidence,
        )
        self.control = RoutingActivationControlState(
            sequence=7,
            issued_at=self.now - timedelta(minutes=1),
            valid_until=self.now + timedelta(minutes=15),
            emergency_stop=False,
        )

    def sign_snapshot(
        self, snapshot: RoutingOperationalSnapshot | None = None
    ) -> SignedRoutingOperationalSnapshot:
        return sign_routing_operational_snapshot(
            snapshot if snapshot is not None else self.snapshot,
            "ops-manager",
            self.ops_key.private_bytes_raw(),
        )

    def sign_policy(
        self, policy: RoutingActivationPolicy | None = None
    ) -> SignedRoutingActivationPolicy:
        return sign_routing_activation_policy(
            policy if policy is not None else self.activation_policy,
            "activation-policy-manager",
            self.policy_key.private_bytes_raw(),
        )

    def sign_control(
        self, control: RoutingActivationControlState | None = None
    ) -> SignedRoutingActivationControl:
        return sign_routing_activation_control(
            control if control is not None else self.control,
            "control-manager",
            self.control_key.private_bytes_raw(),
        )

    def issue(
        self,
        activation_policy: RoutingActivationPolicy | None = None,
        signed_policy: SignedRoutingActivationPolicy | None = None,
        snapshot: SignedRoutingOperationalSnapshot | None = None,
        control: SignedRoutingActivationControl | None = None,
        authorities: RoutingActivationAuthorityPolicy | None = None,
        now: datetime | None = None,
    ) -> RoutingActivationEligibility:
        root = self.source.source
        return issue_routing_activation_eligibility(
            root.dataset,
            root.plan,
            root.calibration,
            root.holdout,
            root.manifest,
            root.sealed,
            root.calibration_report,
            root.policy,
            root.promotion_policy,
            root.claim(root.holdout),
            self.source.report,
            self.promotion,
            self.source.authority_policy,
            signed_policy
            if signed_policy is not None
            else self.sign_policy(activation_policy),
            snapshot if snapshot is not None else self.sign_snapshot(),
            control if control is not None else self.sign_control(),
            authorities if authorities is not None else self.authority_policy,
            now if now is not None else self.now,
        )

    def test_issues_short_lived_non_executing_exact_route_eligibility(self) -> None:
        artifact = self.issue()
        self.assertEqual(
            artifact.valid_until,
            self.now + timedelta(seconds=600),
        )
        self.assertEqual(
            artifact.eligible_candidate_ids,
            tuple(item.candidate_id for item in self.requirements),
        )
        self.assertEqual(artifact.unavailable_action, "role_fallback")
        self.assertTrue(artifact.activation_eligible)
        self.assertFalse(artifact.allow_model_substitution)
        self.assertFalse(artifact.runtime_activation_authorized)
        self.assertFalse(artifact.configuration_mutation_authorized)
        self.assertEqual(
            RoutingActivationEligibility.model_validate_json(canonical_bytes(artifact)),
            artifact,
        )
        root = self.source.source
        verify_routing_activation_eligibility(
            root.dataset,
            root.plan,
            root.calibration,
            root.holdout,
            root.manifest,
            root.sealed,
            root.calibration_report,
            root.policy,
            root.promotion_policy,
            root.claim(root.holdout),
            self.source.report,
            self.promotion,
            self.source.authority_policy,
            self.sign_policy(),
            self.sign_snapshot(),
            self.sign_control(),
            self.authority_policy,
            artifact,
            self.now + timedelta(minutes=1),
        )

    def test_unavailable_expensive_nonconforming_or_drifted_route_fails(self) -> None:
        for update in (
            {"catalog_status": "unavailable"},
            {"normalized_cost_microusd": 11},
            {"conformance_status": "failed"},
            {"drift_status": "failed"},
        ):
            changed = self.snapshot.routes[0].model_copy(update=update)
            snapshot = self.snapshot.model_copy(
                update={"routes": (changed, *self.snapshot.routes[1:])}
            )
            with (
                self.subTest(update=update),
                self.assertRaisesRegex(ValueError, "did not pass every gate"),
            ):
                self.issue(snapshot=self.sign_snapshot(snapshot))

    def test_missing_extra_or_substituted_route_fails(self) -> None:
        missing = self.snapshot.model_copy(update={"routes": self.snapshot.routes[1:]})
        with self.assertRaisesRegex(ValueError, "snapshot provenance"):
            self.issue(snapshot=self.sign_snapshot(missing))

        first = self.snapshot.routes[0]
        changed_route = first.route.model_copy(update={"effort": "medium"})
        substituted = first.model_copy(
            update={
                "route": changed_route,
                "candidate_id": changed_route.candidate_id,
            }
        )
        routes = tuple(
            sorted(
                (substituted, *self.snapshot.routes[1:]),
                key=lambda item: item.candidate_id,
            )
        )
        snapshot = self.snapshot.model_copy(update={"routes": routes})
        with self.assertRaisesRegex(ValueError, "snapshot provenance"):
            self.issue(snapshot=self.sign_snapshot(snapshot))

    def test_stale_future_or_expired_evidence_fails(self) -> None:
        stale_item = self.snapshot.routes[0].model_copy(
            update={
                "observed_at": self.now - timedelta(hours=1),
                "valid_until": self.now + timedelta(minutes=1),
            }
        )
        stale_snapshot = self.snapshot.model_copy(
            update={"routes": (stale_item, *self.snapshot.routes[1:])}
        )
        with self.assertRaisesRegex(ValueError, "evidence is stale"):
            self.issue(snapshot=self.sign_snapshot(stale_snapshot))

        future = self.control.model_copy(
            update={"issued_at": self.now + timedelta(seconds=1)}
        )
        with self.assertRaisesRegex(ValueError, "control state is stale"):
            self.issue(control=self.sign_control(future))

        expired_policy = self.activation_policy.model_copy(
            update={"valid_until": self.now}
        )
        with self.assertRaisesRegex(ValueError, "policy is outside"):
            self.issue(activation_policy=expired_policy)

    def test_lax_activation_policy_cannot_reuse_an_existing_signature(self) -> None:
        signed = self.sign_policy()
        lax_policy = self.activation_policy.model_copy(
            update={
                "max_evidence_age_seconds": 604_800,
                "max_eligibility_lifetime_seconds": 86_400,
                "route_requirements": tuple(
                    item.model_copy(update={"max_normalized_cost_microusd": 1_000_000})
                    for item in self.requirements
                ),
            }
        )
        substituted = signed.model_copy(update={"policy": lax_policy})
        with self.assertRaisesRegex(ValueError, "signature verification failed"):
            self.issue(signed_policy=substituted)

        legitimately_signed = self.sign_policy(lax_policy)
        with self.assertRaisesRegex(ValueError, "snapshot provenance"):
            self.issue(signed_policy=legitimately_signed)

    def test_emergency_stop_revocation_and_control_sequence_fail(self) -> None:
        candidates = (
            self.control.model_copy(update={"emergency_stop": True}),
            self.control.model_copy(
                update={
                    "revoked_candidate_policy_sha256": (
                        self.source.source.policy.candidate_policy_sha256,
                    )
                }
            ),
            self.control.model_copy(
                update={
                    "revoked_promotion_receipt_sha256": (
                        self.promotion.promotion_receipt_sha256,
                    )
                }
            ),
            self.control.model_copy(update={"sequence": 6}),
        )
        for control in candidates:
            with (
                self.subTest(control=control),
                self.assertRaisesRegex(ValueError, "stopped, revoked, or below"),
            ):
                self.issue(control=self.sign_control(control))

    def test_readiness_and_control_require_distinct_independent_signers(self) -> None:
        same_signer_control = sign_routing_activation_control(
            self.control,
            "ops-manager",
            self.ops_key.private_bytes_raw(),
        )
        with self.assertRaisesRegex(ValueError, "distinct signers"):
            self.issue(control=same_signer_control)

        promoter = self.source.authority_policy.authorities[0]
        overlapping = RoutingActivationAuthorityPolicy(
            policy_id="overlapping-activation-authorities",
            authorities=tuple(
                sorted(
                    (
                        trusted_activation_authority(
                            promoter.authority_id,
                            base64.b64decode(promoter.public_key_base64),
                        ),
                        trusted_activation_authority(
                            "ops-manager",
                            self.ops_key.public_key().public_bytes_raw(),
                        ),
                        trusted_activation_authority(
                            "control-manager",
                            self.control_key.public_key().public_bytes_raw(),
                        ),
                    ),
                    key=lambda item: item.authority_id,
                )
            ),
        )
        with self.assertRaisesRegex(ValueError, "independent"):
            self.issue(authorities=overlapping)

    def test_expired_or_tampered_receipt_fails_verification(self) -> None:
        artifact = self.issue()
        root = self.source.source
        with self.assertRaisesRegex(ValueError, "outside its validity"):
            verify_routing_activation_eligibility(
                root.dataset,
                root.plan,
                root.calibration,
                root.holdout,
                root.manifest,
                root.sealed,
                root.calibration_report,
                root.policy,
                root.promotion_policy,
                root.claim(root.holdout),
                self.source.report,
                self.promotion,
                self.source.authority_policy,
                self.sign_policy(),
                self.sign_snapshot(),
                self.sign_control(),
                self.authority_policy,
                artifact,
                artifact.valid_until,
            )
        changed = artifact.model_copy(update={"activation_policy_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "provenance"):
            verify_routing_activation_eligibility(
                root.dataset,
                root.plan,
                root.calibration,
                root.holdout,
                root.manifest,
                root.sealed,
                root.calibration_report,
                root.policy,
                root.promotion_policy,
                root.claim(root.holdout),
                self.source.report,
                self.promotion,
                self.source.authority_policy,
                self.sign_policy(),
                self.sign_snapshot(),
                self.sign_control(),
                self.authority_policy,
                changed,
                self.now,
            )

    def test_schema_cannot_authorize_runtime_or_configuration_mutation(self) -> None:
        value = self.issue().model_dump(mode="json")
        value["runtime_activation_authorized"] = True
        with self.assertRaises(ValidationError):
            RoutingActivationEligibility.model_validate(value)
        value["runtime_activation_authorized"] = False
        value["configuration_mutation_authorized"] = True
        with self.assertRaises(ValidationError):
            RoutingActivationEligibility.model_validate(value)

    def test_cli_reverifies_and_writes_private_short_lived_eligibility(self) -> None:
        with TemporaryDirectory() as directory:
            root_path = Path(directory)
            root = self.source.source
            current = datetime.now(UTC)
            activation_policy = self.activation_policy.model_copy(
                update={
                    "valid_from": current - timedelta(minutes=5),
                    "valid_until": current + timedelta(hours=1),
                }
            )
            snapshot_value = self.snapshot.model_copy(
                update={
                    "activation_policy_sha256": (
                        activation_policy.activation_policy_sha256
                    ),
                    "routes": tuple(
                        item.model_copy(
                            update={
                                "observed_at": current - timedelta(minutes=1),
                                "valid_until": current + timedelta(minutes=30),
                            }
                        )
                        for item in self.snapshot.routes
                    ),
                }
            )
            control_value = self.control.model_copy(
                update={
                    "issued_at": current - timedelta(minutes=1),
                    "valid_until": current + timedelta(minutes=15),
                }
            )
            signed_snapshot = self.sign_snapshot(snapshot_value)
            signed_control = self.sign_control(control_value)
            signed_activation_policy = self.sign_policy(activation_policy)
            claim = root.claim(root.holdout)
            values: dict[str, Contract] = {
                "dataset": root.dataset,
                "plan": root.plan,
                "manifest": root.manifest,
                "sealed": root.sealed,
                "calibration_report": root.calibration_report,
                "candidate_policy": root.policy,
                "promotion_policy": root.promotion_policy,
                "claim": claim,
                "holdout_report": self.source.report,
                "promotion": self.promotion,
                "promotion_authorities": self.source.authority_policy,
                "signed_activation_policy": signed_activation_policy,
                "snapshot": signed_snapshot,
                "control": signed_control,
                "activation_authorities": self.authority_policy,
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
                ("calibration", root.calibration),
                ("holdout", root.holdout),
            ):
                values.update(
                    {
                        f"{prefix}_{name}": value
                        for name, value in zip(lineage_names, lineage, strict=True)
                    }
                )
            paths = {name: root_path / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))
            arguments = [
                "eval-issue-routing-activation-eligibility",
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
                "--promotion-receipt",
                str(paths["promotion"]),
                "--promotion-authority-policy",
                str(paths["promotion_authorities"]),
                "--signed-activation-policy",
                str(paths["signed_activation_policy"]),
                "--signed-operational-snapshot",
                str(paths["snapshot"]),
                "--signed-control-state",
                str(paths["control"]),
                "--activation-authority-policy",
                str(paths["activation_authorities"]),
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
            output = root_path / "eligibility.json"
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main([*arguments, "--output", str(output)]), 0)
            event = json.loads(stdout.getvalue())
            artifact = RoutingActivationEligibility.model_validate_json(
                output.read_bytes()
            )
            self.assertTrue(event["activation_eligible"])
            self.assertFalse(event["runtime_activation_authorized"])
            self.assertFalse(event["configuration_mutation_authorized"])
            self.assertEqual(event["eligibility_sha256"], artifact.eligibility_sha256)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([*arguments, "--output", str(output)]), 2)
