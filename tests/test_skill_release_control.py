"""Skill release revocation is independent, expiring, exact, and monotonic."""

import base64
import io
import json
import sqlite3
import stat
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.cli import main
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.core.skills import SkillPackageArchive
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SignedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAnchorPolicy,
    SkillReleaseControlAuthorityPolicy,
    SkillReleaseControlDecision,
    authenticate_skill_release_control,
    make_skill_release_control_decision,
    sign_skill_release_control,
    trusted_skill_release_control_authority,
    verify_signed_skill_release_control,
)
from mos_eisley.run.skills import discover_skills
from mos_eisley.run.store import private_write
from tests import test_skill_release as release_module
from tests.test_skills import write_skill


class SkillReleaseControlTests(TestCase):
    def setUp(self) -> None:
        self.source = release_module.SkillReleaseEvidenceTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.evidence = self.source.bind()
        self.key = Ed25519PrivateKey.generate()
        self.issued_at = self.source.checked_at + timedelta(minutes=1)
        self.valid_until = self.issued_at + timedelta(minutes=20)
        self.policy = SkillReleaseControlAuthorityPolicy(
            policy_id="skill-release-control-v1",
            valid_from=self.issued_at - timedelta(hours=1),
            valid_until=self.evidence.valid_until,
            max_decision_lifetime_seconds=1800,
            authorities=(
                trusted_skill_release_control_authority(
                    "skill-release-controller",
                    self.key.public_key().public_bytes_raw(),
                ),
            ),
        )
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        rollback_root = self.root / "rollback"
        write_skill(
            rollback_root,
            "adversarial-reviewer",
            "Review this change adversarially using the prior stable rubric.",
            sidecar="version: 0.9.0\nkind: persona\n",
        )
        catalog = discover_skills(project_roots=(rollback_root,))
        identity = catalog.descriptors[0].identity
        self.rollback = catalog.archive(
            identity.qualified_reference,
            allow_project=True,
        )

    def decision(
        self,
        *,
        sequence: int = 7,
        disposition: str = "revoked",
        rollback: SkillPackageArchive | None = None,
        issued_offset: timedelta = timedelta(0),
    ) -> SkillReleaseControlDecision:
        issued = self.issued_at + issued_offset
        return make_skill_release_control_decision(
            self.source.promotion.source.dataset,
            self.source.promotion.source.plan,
            self.source.promotion.calibration,
            self.source.promotion.holdout,
            self.source.promotion.source.sealed,
            self.source.promotion.source.holdout_claim,
            self.source.promotion.calibration_report,
            self.source.promotion.holdout_report,
            self.source.receipt,
            self.source.promotion.authority_policy,
            self.source.archive,
            self.evidence,
            self.policy,
            sequence,
            disposition,  # type: ignore[arg-type]
            rollback,
            issued,
            self.valid_until,
        )

    def signed(
        self,
        decision: SkillReleaseControlDecision | None = None,
        signer: Ed25519PrivateKey | None = None,
        signer_id: str = "skill-release-controller",
    ) -> SignedSkillReleaseControl:
        return sign_skill_release_control(
            decision or self.decision(rollback=self.rollback),
            signer_id,
            (signer or self.key).private_bytes_raw(),
        )

    def authenticate(
        self,
        *,
        signed: SignedSkillReleaseControl | None = None,
        rollback: SkillPackageArchive | None = None,
    ) -> AuthenticatedSkillReleaseControl:
        return authenticate_skill_release_control(
            self.source.promotion.source.dataset,
            self.source.promotion.source.plan,
            self.source.promotion.calibration,
            self.source.promotion.holdout,
            self.source.promotion.source.sealed,
            self.source.promotion.source.holdout_claim,
            self.source.promotion.calibration_report,
            self.source.promotion.holdout_report,
            self.source.receipt,
            self.source.promotion.authority_policy,
            self.source.archive,
            self.evidence,
            signed or self.signed(),
            self.policy,
            rollback if rollback is not None else self.rollback,
            self.issued_at + timedelta(minutes=1),
        )

    def test_authenticates_exact_revocation_and_rollback_without_authority(
        self,
    ) -> None:
        signed = self.signed()
        receipt = self.authenticate(signed=signed)

        self.assertTrue(receipt.release_revoked)
        self.assertFalse(receipt.release_allowed)
        self.assertEqual(receipt.rollback_archive, self.rollback)
        self.assertEqual(
            receipt.release_evidence_sha256,
            self.evidence.release_evidence_sha256,
        )
        self.assertFalse(receipt.installation_authorized)
        self.assertFalse(receipt.activation_authorized)
        self.assertFalse(receipt.configuration_mutation_authorized)
        self.assertEqual(len(receipt.control_receipt_sha256), 64)
        self.assertEqual(
            verify_signed_skill_release_control(signed, self.policy).authority_id,
            "skill-release-controller",
        )

    def test_allowed_control_cannot_smuggle_rollback_bytes(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed release"):
            self.decision(disposition="allowed", rollback=self.rollback)

        decision = self.decision(disposition="allowed")
        signed = self.signed(decision)
        receipt = authenticate_skill_release_control(
            self.source.promotion.source.dataset,
            self.source.promotion.source.plan,
            self.source.promotion.calibration,
            self.source.promotion.holdout,
            self.source.promotion.source.sealed,
            self.source.promotion.source.holdout_claim,
            self.source.promotion.calibration_report,
            self.source.promotion.holdout_report,
            self.source.receipt,
            self.source.promotion.authority_policy,
            self.source.archive,
            self.evidence,
            signed,
            self.policy,
            None,
            self.issued_at + timedelta(minutes=1),
        )
        self.assertTrue(receipt.release_allowed)
        self.assertFalse(receipt.release_revoked)
        self.assertIsNone(receipt.rollback_archive)

    def test_rollback_must_be_exact_prior_bytes_for_the_same_skill(self) -> None:
        other_root = self.root / "other"
        write_skill(
            other_root,
            "different-reviewer",
            "Review this change adversarially.",
            sidecar="version: 0.9.0\nkind: persona\n",
        )
        catalog = discover_skills(project_roots=(other_root,))
        other = catalog.archive(
            catalog.descriptors[0].identity.qualified_reference,
            allow_project=True,
        )
        with self.assertRaisesRegex(ValueError, "does not match this skill release"):
            self.decision(rollback=other)
        with self.assertRaisesRegex(ValueError, "does not match this skill release"):
            self.decision(rollback=self.source.archive)

        signed = self.signed()
        changed = self.rollback.model_copy(update={"activation_authorized": True})
        with self.assertRaisesRegex(ValueError, "deployment authority"):
            self.authenticate(signed=signed, rollback=changed)

    def test_signature_policy_source_time_and_independence_fail_closed(self) -> None:
        signed = self.signed()
        tampered_signature = signed.signature.model_copy(
            update={"signature_base64": base64.b64encode(b"x" * 64).decode("ascii")}
        )
        with self.assertRaisesRegex(ValueError, "signature verification failed"):
            verify_signed_skill_release_control(
                signed.model_copy(update={"signature": tampered_signature}),
                self.policy,
            )
        with self.assertRaisesRegex(ValueError, "not current"):
            authenticate_skill_release_control(
                self.source.promotion.source.dataset,
                self.source.promotion.source.plan,
                self.source.promotion.calibration,
                self.source.promotion.holdout,
                self.source.promotion.source.sealed,
                self.source.promotion.source.holdout_claim,
                self.source.promotion.calibration_report,
                self.source.promotion.holdout_report,
                self.source.receipt,
                self.source.promotion.authority_policy,
                self.source.archive,
                self.evidence,
                signed,
                self.policy,
                self.rollback,
                signed.decision.valid_until,
            )

        promotion_authority = self.source.promotion.authority_policy.authorities[0]
        overlapping = self.policy.model_copy(
            update={
                "authorities": (
                    trusted_skill_release_control_authority(
                        promotion_authority.authority_id,
                        self.source.promotion.authority_key.public_key().public_bytes_raw(),
                    ),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "independent of promotion"):
            make_skill_release_control_decision(
                self.source.promotion.source.dataset,
                self.source.promotion.source.plan,
                self.source.promotion.calibration,
                self.source.promotion.holdout,
                self.source.promotion.source.sealed,
                self.source.promotion.source.holdout_claim,
                self.source.promotion.calibration_report,
                self.source.promotion.holdout_report,
                self.source.receipt,
                self.source.promotion.authority_policy,
                self.source.archive,
                self.evidence,
                overlapping,
                7,
                "revoked",
                self.rollback,
                self.issued_at,
                self.valid_until,
            )

    def test_anchor_rejects_replay_revocation_removal_and_tampering(self) -> None:
        path = self.root / "release-control.sqlite"
        anchor_policy = SkillReleaseControlAnchorPolicy(
            anchor_id="a" * 64,
            release_evidence_sha256=self.evidence.release_evidence_sha256,
            control_authority_policy_sha256=self.policy.policy_sha256,
            minimum_sequence=7,
            control_authority_ids=("skill-release-controller",),
        )
        anchor = SkillReleaseControlAnchor.create(path, anchor_policy, self.policy)
        allowed = self.signed(self.decision(disposition="allowed"))
        first = anchor.advance(
            allowed,
            self.policy,
            self.issued_at + timedelta(seconds=1),
        )
        self.assertEqual(first.entries, 1)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, "sequence did not advance"):
            anchor.advance(
                allowed,
                self.policy,
                self.issued_at + timedelta(seconds=2),
            )

        revoked_decision = self.decision(
            sequence=8,
            rollback=self.rollback,
            issued_offset=timedelta(minutes=1),
        )
        revoked = self.signed(revoked_decision)
        anchor.advance(
            revoked,
            self.policy,
            self.issued_at + timedelta(minutes=2),
        )
        reopened = self.signed(
            self.decision(
                sequence=9,
                disposition="allowed",
                issued_offset=timedelta(minutes=2),
            )
        )
        with self.assertRaisesRegex(ValueError, "revocation cannot be removed"):
            anchor.advance(
                reopened,
                self.policy,
                self.issued_at + timedelta(minutes=3),
            )

        receipt = self.authenticate(signed=revoked)
        latest = anchor.require_latest(
            receipt,
            self.policy,
            self.issued_at + timedelta(minutes=3),
        )
        self.assertEqual(latest.signed_control, revoked)
        with self.assertRaisesRegex(ValueError, "latest anchored state"):
            allowed_receipt = authenticate_skill_release_control(
                self.source.promotion.source.dataset,
                self.source.promotion.source.plan,
                self.source.promotion.calibration,
                self.source.promotion.holdout,
                self.source.promotion.source.sealed,
                self.source.promotion.source.holdout_claim,
                self.source.promotion.calibration_report,
                self.source.promotion.holdout_report,
                self.source.receipt,
                self.source.promotion.authority_policy,
                self.source.archive,
                self.evidence,
                allowed,
                self.policy,
                None,
                self.issued_at + timedelta(minutes=1),
            )
            anchor.require_latest(
                allowed_receipt,
                self.policy,
                self.issued_at + timedelta(minutes=3),
            )

        with sqlite3.connect(path) as connection, connection:
            connection.execute(
                "UPDATE control_entries SET entry_json = ? WHERE sequence = 8",
                (canonical_bytes(first.latest) if first.latest is not None else b"",),
            )
        with self.assertRaisesRegex(ValueError, "anchor chain is invalid"):
            anchor.snapshot(self.policy)

    def test_anchor_pins_sequence_scope_policy_and_signer(self) -> None:
        path = self.root / "release-control-floor.sqlite"
        anchor_policy = SkillReleaseControlAnchorPolicy(
            anchor_id="b" * 64,
            release_evidence_sha256=self.evidence.release_evidence_sha256,
            control_authority_policy_sha256=self.policy.policy_sha256,
            minimum_sequence=8,
            control_authority_ids=("skill-release-controller",),
        )
        anchor = SkillReleaseControlAnchor.create(path, anchor_policy, self.policy)
        with self.assertRaisesRegex(ValueError, "below anchor sequence floor"):
            anchor.advance(
                self.signed(),
                self.policy,
                self.issued_at + timedelta(minutes=1),
            )

        other_key = Ed25519PrivateKey.generate()
        expanded = self.policy.model_copy(
            update={
                "authorities": tuple(
                    sorted(
                        (
                            *self.policy.authorities,
                            trusted_skill_release_control_authority(
                                "unanchored-controller",
                                other_key.public_key().public_bytes_raw(),
                            ),
                        ),
                        key=lambda item: item.authority_id,
                    )
                )
            }
        )
        replacement_path = self.root / "replacement.sqlite"
        replacement_policy = anchor_policy.model_copy(
            update={"control_authority_policy_sha256": expanded.policy_sha256}
        )
        replacement = SkillReleaseControlAnchor.create(
            replacement_path,
            replacement_policy,
            expanded,
        )
        decision = self.decision(sequence=8, rollback=self.rollback).model_copy(
            update={"authority_policy_sha256": expanded.policy_sha256}
        )
        unauthorized = self.signed(
            decision,
            signer=other_key,
            signer_id="unanchored-controller",
        )
        with self.assertRaisesRegex(ValueError, "not authorized by anchor policy"):
            replacement.advance(
                unauthorized,
                expanded,
                self.issued_at + timedelta(minutes=1),
            )

    def test_cli_derives_authenticates_and_anchors_without_private_keys(self) -> None:
        fixture = self.source.promotion
        values: dict[str, Contract] = {
            "dataset": fixture.source.dataset,
            "plan": fixture.source.plan,
            "sealed": fixture.source.sealed,
            "claim": fixture.source.holdout_claim,
            "calibration_report": fixture.calibration_report,
            "holdout_report": fixture.holdout_report,
            "promotion": self.source.receipt,
            "promotion_policy": fixture.authority_policy,
            "archive": self.source.archive,
            "evidence": self.evidence,
            "control_policy": self.policy,
            "rollback": self.rollback,
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
            ("calibration", fixture.calibration),
            ("holdout", fixture.holdout),
        ):
            values.update(
                {
                    f"{prefix}_{name}": value
                    for name, value in zip(lineage_names, lineage, strict=True)
                }
            )
        paths = {name: self.root / f"{name}.json" for name in values}
        for name, value in values.items():
            private_write(paths[name], canonical_bytes(value))

        def source_arguments(command: str) -> list[str]:
            arguments = [
                command,
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
                "--promotion-receipt",
                str(paths["promotion"]),
                "--promotion-authority-policy",
                str(paths["promotion_policy"]),
                "--archive",
                str(paths["archive"]),
                "--release-evidence",
                str(paths["evidence"]),
                "--control-authority-policy",
                str(paths["control_policy"]),
                "--rollback-archive",
                str(paths["rollback"]),
            ]
            cli_names = (
                "batch",
                "mapping",
                "raw-results",
                "grading-batch",
                "dual-grading-resolution",
                "dual-graded-observations",
                "grading-trust-policy",
                "resolution-trust-policy",
            )
            artifact_names = (
                "batch",
                "mapping",
                "raw",
                "grading",
                "dual",
                "observations",
                "grading_policy",
                "resolution_policy",
            )
            for prefix in ("calibration", "holdout"):
                for cli_name, artifact_name in zip(
                    cli_names, artifact_names, strict=True
                ):
                    arguments.extend(
                        (
                            f"--{prefix}-{cli_name}",
                            str(paths[f"{prefix}_{artifact_name}"]),
                        )
                    )
            return arguments

        decision_path = self.root / "release-control-decision.json"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        *source_arguments("eval-derive-skill-release-control"),
                        "--sequence",
                        "7",
                        "--disposition",
                        "revoked",
                        "--issued-at",
                        self.issued_at.isoformat(),
                        "--valid-until",
                        self.valid_until.isoformat(),
                        "--output",
                        str(decision_path),
                    ]
                ),
                0,
            )
        event = json.loads(stdout.getvalue())
        decision = SkillReleaseControlDecision.model_validate_json(
            decision_path.read_bytes()
        )
        self.assertEqual(event["decision_sha256"], decision.decision_sha256)
        self.assertFalse(event["installation_authorized"])

        signed_path = self.root / "signed-release-control.json"
        private_write(signed_path, canonical_bytes(self.signed(decision)))
        receipt_path = self.root / "authenticated-release-control.json"
        authenticate_args = [
            *source_arguments("eval-authenticate-skill-release-control"),
            "--signed-control",
            str(signed_path),
            "--output",
            str(receipt_path),
        ]
        with patch("mos_eisley.cli.datetime") as clock:
            clock.now.return_value = self.issued_at + timedelta(minutes=1)
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(authenticate_args), 0)
        receipt_event = json.loads(stdout.getvalue())
        receipt = AuthenticatedSkillReleaseControl.model_validate_json(
            receipt_path.read_bytes()
        )
        self.assertEqual(
            receipt_event["control_receipt_sha256"],
            receipt.control_receipt_sha256,
        )
        self.assertTrue(receipt_event["release_revoked"])
        self.assertEqual(stat.S_IMODE(receipt_path.stat().st_mode), 0o600)

        anchor_policy = SkillReleaseControlAnchorPolicy(
            anchor_id="c" * 64,
            release_evidence_sha256=self.evidence.release_evidence_sha256,
            control_authority_policy_sha256=self.policy.policy_sha256,
            minimum_sequence=7,
            control_authority_ids=("skill-release-controller",),
        )
        anchor_policy_path = self.root / "release-control-anchor-policy.json"
        private_write(anchor_policy_path, canonical_bytes(anchor_policy))
        anchor_path = self.root / "cli-release-control.sqlite"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "skill-release-control-anchor-create",
                        str(anchor_path),
                        "--anchor-policy",
                        str(anchor_policy_path),
                        "--control-authority-policy",
                        str(paths["control_policy"]),
                    ]
                ),
                0,
            )
        with patch("mos_eisley.cli.datetime") as clock:
            clock.now.return_value = self.issued_at + timedelta(minutes=1)
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    main(
                        [
                            "skill-release-control-anchor-advance",
                            "--anchor",
                            str(anchor_path),
                            "--signed-control",
                            str(signed_path),
                            "--control-authority-policy",
                            str(paths["control_policy"]),
                        ]
                    ),
                    0,
                )
        anchor_event = json.loads(stdout.getvalue())
        self.assertEqual(anchor_event["sequence"], 7)
        self.assertFalse(anchor_event["activation_authorized"])
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-release-control-anchor-status",
                        "--anchor",
                        str(anchor_path),
                        "--control-authority-policy",
                        str(paths["control_policy"]),
                    ]
                ),
                0,
            )
        self.assertEqual(json.loads(stdout.getvalue())["latest_sequence"], 7)
