"""Runtime preflight rejects control replay and grants no execution authority."""

import io
import json
import sqlite3
import stat
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.evaluation.routing_activation import (
    RoutingActivationControlState,
    RoutingActivationEligibility,
    SignedRoutingActivationControl,
    sign_routing_activation_control,
)
from mos_eisley.run.activation_control import RoutingControlAnchor
from mos_eisley.run.routing_preflight import (
    RoutingRuntimePreflight,
    perform_routing_runtime_preflight,
    verify_routing_runtime_preflight,
)
from mos_eisley.run.store import private_write
from tests.test_routing_activation import RoutingActivationTests


class RoutingRuntimePreflightTests(TestCase):
    def setUp(self) -> None:
        self.source = RoutingActivationTests()
        self.source.setUp()
        self.eligibility = self.source.issue()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.anchor_path = Path(temporary.name) / "control-anchor.sqlite"
        self.anchor = RoutingControlAnchor.create(
            self.anchor_path,
            self.source.control_anchor_policy,
            self.source.authority_policy,
        )
        self.signed_control = self.source.sign_control()
        self.anchor.advance(
            self.signed_control,
            self.source.authority_policy,
            self.source.now,
        )

    def preflight(
        self,
        *,
        signed_control: SignedRoutingActivationControl | None = None,
        eligibility: RoutingActivationEligibility | None = None,
        now: datetime | None = None,
    ) -> RoutingRuntimePreflight:
        activation = self.source
        root = activation.source.source
        return perform_routing_runtime_preflight(
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
            activation.source.report,
            activation.promotion,
            activation.source.authority_policy,
            activation.sign_policy(),
            activation.sign_snapshot(),
            signed_control if signed_control is not None else self.signed_control,
            activation.authority_policy,
            eligibility if eligibility is not None else self.eligibility,
            self.anchor,
            now if now is not None else activation.now,
        )

    def test_preflight_is_short_lived_reverified_and_non_authorizing(self) -> None:
        artifact = self.preflight()
        self.assertEqual(
            artifact.valid_until,
            self.source.now + timedelta(seconds=30),
        )
        self.assertTrue(artifact.preflight_passed)
        self.assertFalse(artifact.allow_model_substitution)
        self.assertFalse(artifact.dispatch_authorized)
        self.assertFalse(artifact.runtime_activation_authorized)
        self.assertFalse(artifact.configuration_mutation_authorized)
        self.assertEqual(
            artifact.eligible_candidate_ids, self.eligibility.eligible_candidate_ids
        )

        activation = self.source
        root = activation.source.source
        verify_routing_runtime_preflight(
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
            activation.source.report,
            activation.promotion,
            activation.source.authority_policy,
            activation.sign_policy(),
            activation.sign_snapshot(),
            self.signed_control,
            activation.authority_policy,
            self.eligibility,
            self.anchor,
            artifact,
            self.source.now + timedelta(seconds=29),
        )
        with self.assertRaisesRegex(ValueError, "outside its validity"):
            verify_routing_runtime_preflight(
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
                activation.source.report,
                activation.promotion,
                activation.source.authority_policy,
                activation.sign_policy(),
                activation.sign_snapshot(),
                self.signed_control,
                activation.authority_policy,
                self.eligibility,
                self.anchor,
                artifact,
                artifact.valid_until,
            )

    def test_older_still_valid_control_is_rejected_after_advance(self) -> None:
        newer = self.source.control.model_copy(
            update={
                "sequence": 8,
                "issued_at": self.source.now + timedelta(seconds=1),
                "valid_until": self.source.now + timedelta(minutes=20),
            }
        )
        signed_newer = self.source.sign_control(newer)
        self.anchor.advance(
            signed_newer,
            self.source.authority_policy,
            self.source.now + timedelta(seconds=1),
        )
        with self.assertRaisesRegex(ValueError, "latest anchored state"):
            self.preflight(now=self.source.now + timedelta(seconds=2))

    def test_anchor_rejects_nonadvancing_time_sequence_and_removed_revocation(
        self,
    ) -> None:
        for changed in (
            self.source.control.model_copy(update={"sequence": 7}),
            self.source.control.model_copy(
                update={
                    "sequence": 8,
                    "issued_at": self.source.control.issued_at,
                }
            ),
        ):
            with self.assertRaisesRegex(ValueError, "did not advance"):
                self.anchor.advance(
                    self.source.sign_control(changed),
                    self.source.authority_policy,
                    self.source.now,
                )

        revoked = self.source.control.model_copy(
            update={
                "sequence": 8,
                "issued_at": self.source.now + timedelta(seconds=1),
                "revoked_candidate_policy_sha256": (
                    self.source.source.source.policy.candidate_policy_sha256,
                ),
            }
        )
        self.anchor.advance(
            self.source.sign_control(revoked),
            self.source.authority_policy,
            self.source.now + timedelta(seconds=1),
        )
        removed = self.source.control.model_copy(
            update={
                "sequence": 9,
                "issued_at": self.source.now + timedelta(seconds=2),
            }
        )
        with self.assertRaisesRegex(ValueError, "revocations cannot be removed"):
            self.anchor.advance(
                self.source.sign_control(removed),
                self.source.authority_policy,
                self.source.now + timedelta(seconds=2),
            )

    def test_anchor_pins_trust_policy_and_control_signer_role(self) -> None:
        changed_policy = self.source.authority_policy.model_copy(
            update={"policy_id": "replacement-authorities"}
        )
        with self.assertRaisesRegex(ValueError, "does not match control anchor"):
            self.anchor.snapshot(changed_policy)

        other_control = self.source.control.model_copy(
            update={
                "sequence": 8,
                "issued_at": self.source.now + timedelta(seconds=1),
            }
        )
        signed_by_ops = sign_routing_activation_control(
            other_control,
            "ops-manager",
            self.source.ops_key.private_bytes_raw(),
        )
        with self.assertRaisesRegex(ValueError, "not authorized by anchor policy"):
            self.anchor.advance(
                signed_by_ops,
                self.source.authority_policy,
                self.source.now + timedelta(seconds=1),
            )

    def test_preflight_rejects_a_replacement_anchor_policy(self) -> None:
        replacement_policy = self.source.control_anchor_policy.model_copy(
            update={"anchor_id": "f" * 64}
        )
        replacement_path = self.anchor_path.with_name("replacement.sqlite")
        replacement = RoutingControlAnchor.create(
            replacement_path,
            replacement_policy,
            self.source.authority_policy,
        )
        replacement.advance(
            self.signed_control,
            self.source.authority_policy,
            self.source.now,
        )
        original = self.anchor
        self.anchor = replacement
        try:
            with self.assertRaisesRegex(ValueError, "not the signed policy"):
                self.preflight()
        finally:
            self.anchor = original

    def test_anchor_rejects_expired_state_and_chain_tampering(self) -> None:
        expired = RoutingActivationControlState(
            sequence=8,
            issued_at=self.source.now - timedelta(minutes=20),
            valid_until=self.source.now,
            emergency_stop=False,
        )
        with self.assertRaisesRegex(ValueError, "only a current"):
            self.anchor.advance(
                self.source.sign_control(expired),
                self.source.authority_policy,
                self.source.now,
            )

        with sqlite3.connect(self.anchor_path) as connection, connection:
            connection.execute(
                "UPDATE control_entries SET entry_sha256 = ? WHERE sequence = 7",
                ("f" * 64,),
            )
        with self.assertRaisesRegex(ValueError, "chain is invalid"):
            self.anchor.snapshot(self.source.authority_policy)

    def test_preflight_rejects_a_future_anchor_timestamp(self) -> None:
        future_path = self.anchor_path.with_name("future.sqlite")
        future = RoutingControlAnchor.create(
            future_path,
            self.source.control_anchor_policy,
            self.source.authority_policy,
        )
        future.advance(
            self.signed_control,
            self.source.authority_policy,
            self.source.now + timedelta(minutes=1),
        )
        original = self.anchor
        self.anchor = future
        try:
            with self.assertRaisesRegex(ValueError, "is not current"):
                self.preflight()
        finally:
            self.anchor = original

    def test_anchor_is_private_nonresettable_and_requires_state(self) -> None:
        self.assertEqual(self.anchor_path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            RoutingControlAnchor.create(
                self.anchor_path,
                self.source.control_anchor_policy,
                self.source.authority_policy,
            )

        empty_path = self.anchor_path.with_name("empty.sqlite")
        empty = RoutingControlAnchor.create(
            empty_path,
            self.source.control_anchor_policy,
            self.source.authority_policy,
        )
        with self.assertRaisesRegex(ValueError, "has no state"):
            empty.require_latest(
                self.signed_control,
                self.source.authority_policy,
                self.source.now,
            )

    def test_schema_cannot_grant_dispatch_or_configuration_authority(self) -> None:
        value = self.preflight().model_dump(mode="json")
        for field in (
            "dispatch_authorized",
            "runtime_activation_authorized",
            "configuration_mutation_authorized",
        ):
            changed = {**value, field: True}
            with self.subTest(field=field), self.assertRaises(ValidationError):
                RoutingRuntimePreflight.model_validate(changed)

    def test_cli_anchors_then_performs_private_current_preflight(self) -> None:
        with TemporaryDirectory() as directory:
            root_path = Path(directory)
            activation = self.source
            root = activation.source.source
            current = datetime.now(UTC)
            policy = activation.activation_policy.model_copy(
                update={
                    "valid_from": current - timedelta(minutes=5),
                    "valid_until": current + timedelta(hours=1),
                }
            )
            signed_policy = activation.sign_policy(policy)
            snapshot_value = activation.snapshot.model_copy(
                update={
                    "activation_policy_sha256": policy.activation_policy_sha256,
                    "routes": tuple(
                        item.model_copy(
                            update={
                                "observed_at": current - timedelta(minutes=1),
                                "valid_until": current + timedelta(minutes=30),
                            }
                        )
                        for item in activation.snapshot.routes
                    ),
                }
            )
            signed_snapshot = activation.sign_snapshot(snapshot_value)
            control_value = activation.control.model_copy(
                update={
                    "issued_at": current - timedelta(minutes=1),
                    "valid_until": current + timedelta(minutes=15),
                }
            )
            signed_control = activation.sign_control(control_value)
            eligibility = activation.issue(
                activation_policy=policy,
                snapshot=signed_snapshot,
                control=signed_control,
                now=current,
            )
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
                "holdout_report": activation.source.report,
                "promotion": activation.promotion,
                "promotion_authorities": activation.source.authority_policy,
                "signed_policy": signed_policy,
                "snapshot": signed_snapshot,
                "control": signed_control,
                "activation_authorities": activation.authority_policy,
                "anchor_policy": activation.control_anchor_policy,
                "eligibility": eligibility,
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

            anchor_path = root_path / "runtime-control.sqlite"
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    main(
                        [
                            "routing-control-anchor-create",
                            str(anchor_path),
                            "--activation-authority-policy",
                            str(paths["activation_authorities"]),
                            "--anchor-policy",
                            str(paths["anchor_policy"]),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(stdout.getvalue())["entries"], 0)
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    main(
                        [
                            "routing-control-anchor-advance",
                            "--anchor",
                            str(anchor_path),
                            "--activation-authority-policy",
                            str(paths["activation_authorities"]),
                            "--signed-control-state",
                            str(paths["control"]),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(stdout.getvalue())["sequence"], 7)
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    main(
                        [
                            "routing-control-anchor-status",
                            "--anchor",
                            str(anchor_path),
                            "--activation-authority-policy",
                            str(paths["activation_authorities"]),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(stdout.getvalue())["latest_sequence"], 7)

            arguments = [
                "eval-routing-runtime-preflight",
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
                str(paths["signed_policy"]),
                "--signed-operational-snapshot",
                str(paths["snapshot"]),
                "--signed-control-state",
                str(paths["control"]),
                "--activation-authority-policy",
                str(paths["activation_authorities"]),
                "--activation-eligibility",
                str(paths["eligibility"]),
                "--control-anchor",
                str(anchor_path),
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
            output = root_path / "runtime-preflight.json"
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main([*arguments, "--output", str(output)]), 0)
            event = json.loads(stdout.getvalue())
            artifact = RoutingRuntimePreflight.model_validate_json(output.read_bytes())
            self.assertEqual(event["preflight_sha256"], artifact.preflight_sha256)
            self.assertFalse(event["dispatch_authorized"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([*arguments, "--output", str(output)]), 2)
