"""Skill installation authority is exact, independent, expiring, and one-use."""

import io
import json
import os
import sqlite3
import stat
from contextlib import AbstractContextManager, redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.skill_installation import (
    AuthenticatedSkillInstallation,
    SignedSkillInstallationDecision,
    SkillInstallationAuthorityPolicy,
    SkillInstallationClaim,
    SkillInstallationClaimStore,
    SkillInstallationClaimStorePolicy,
    SkillInstallationDecision,
    authenticate_skill_installation,
    guard_and_claim_skill_installation,
    make_skill_installation_decision,
    sign_skill_installation_decision,
    trusted_skill_installation_authority,
    verify_authenticated_skill_installation,
    verify_signed_skill_installation_decision,
)
from mos_eisley.run.store import private_write
from tests import test_skill_staging as staging_module


class SkillInstallationTests(TestCase):
    def setUp(self) -> None:
        self.source = staging_module.SkillStagingTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.staged = self.source.stage()
        self.signer = Ed25519PrivateKey.generate()
        self.issued_at = self.source.stage_at + timedelta(minutes=1)
        self.valid_until = self.issued_at + timedelta(minutes=5)
        self.policy = SkillInstallationAuthorityPolicy(
            policy_id="skill-installation-authorities-v1",
            staging_store_policy_sha256=self.source.store.policy.policy_sha256,
            control_anchor_policy_sha256=self.source.anchor.policy.policy_sha256,
            claim_store_id="a" * 64,
            installation_target_id="b" * 64,
            valid_from=self.issued_at - timedelta(minutes=1),
            valid_until=self.source.source.valid_until,
            max_decision_lifetime_seconds=600,
            authorities=(
                trusted_skill_installation_authority(
                    "skill-installer",
                    self.signer.public_key().public_bytes_raw(),
                ),
            ),
        )
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.claim_policy = SkillInstallationClaimStorePolicy(
            store_id=self.policy.claim_store_id,
            authority_policy_sha256=self.policy.policy_sha256,
            max_claims=4,
        )
        self.claim_store = SkillInstallationClaimStore.create(
            self.root / "installation-claims.sqlite",
            self.claim_policy,
            self.policy,
        )

    def decision(
        self,
        *,
        policy: SkillInstallationAuthorityPolicy | None = None,
        action: Literal["candidate", "rollback"] = "rollback",
    ) -> SkillInstallationDecision:
        control = self.source.source
        fixture = control.source.promotion
        return make_skill_installation_decision(
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            control.source.receipt,
            fixture.authority_policy,
            control.source.archive,
            control.evidence,
            self.source.control,
            control.policy,
            self.source.anchor,
            self.source.store,
            policy or self.policy,
            action,
            self.issued_at,
            self.valid_until,
        )

    def signed(self) -> SignedSkillInstallationDecision:
        return sign_skill_installation_decision(
            self.decision(),
            "skill-installer",
            self.signer.private_bytes_raw(),
        )

    def authenticate(
        self,
        signed: SignedSkillInstallationDecision | None = None,
        *,
        action: Literal["candidate", "rollback"] = "rollback",
        now_offset: timedelta = timedelta(minutes=1),
    ) -> AuthenticatedSkillInstallation:
        control = self.source.source
        fixture = control.source.promotion
        return authenticate_skill_installation(
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            control.source.receipt,
            fixture.authority_policy,
            control.source.archive,
            control.evidence,
            self.source.control,
            control.policy,
            self.source.anchor,
            self.source.store,
            signed or self.signed(),
            self.policy,
            action,
            self.issued_at + now_offset,
        )

    def guard(
        self,
        authorization: AuthenticatedSkillInstallation,
        *,
        now_offset: timedelta = timedelta(minutes=2),
    ) -> AbstractContextManager[SkillInstallationClaim]:
        control = self.source.source
        fixture = control.source.promotion
        return guard_and_claim_skill_installation(
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            control.source.receipt,
            fixture.authority_policy,
            control.source.archive,
            control.evidence,
            self.source.control,
            control.policy,
            self.source.anchor,
            self.source.store,
            authorization,
            self.policy,
            self.claim_store,
            "rollback",
            self.issued_at + now_offset,
        )

    def test_authenticates_exact_installation_without_activation(self) -> None:
        decision = self.decision()
        signed = sign_skill_installation_decision(
            decision,
            "skill-installer",
            self.signer.private_bytes_raw(),
        )
        authorization = self.authenticate(signed)

        self.assertTrue(decision.installation_authorized)
        self.assertTrue(authorization.installation_authorized)
        self.assertTrue(authorization.one_use_required)
        self.assertFalse(authorization.installation_performed)
        self.assertFalse(authorization.activation_authorized)
        self.assertFalse(authorization.configuration_mutation_authorized)
        self.assertEqual(
            decision.staging_manifest_sha256,
            self.staged.manifest.manifest_sha256,
        )
        self.assertEqual(
            decision.archive_sha256, self.source.source.rollback.archive_sha256
        )
        self.assertEqual(
            verify_signed_skill_installation_decision(signed, self.policy).authority_id,
            "skill-installer",
        )
        control = self.source.source
        fixture = control.source.promotion
        verify_authenticated_skill_installation(
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            control.source.receipt,
            fixture.authority_policy,
            control.source.archive,
            control.evidence,
            self.source.control,
            control.policy,
            self.source.anchor,
            self.source.store,
            authorization,
            self.policy,
            "rollback",
            self.issued_at + timedelta(minutes=2),
        )

    def test_authority_policy_action_expiry_and_latest_state_fail_closed(self) -> None:
        control = self.source.source
        overlapping = self.policy.model_copy(
            update={
                "authorities": (
                    trusted_skill_installation_authority(
                        "skill-release-controller",
                        control.key.public_key().public_bytes_raw(),
                    ),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "must be independent"):
            self.decision(policy=overlapping)

        changed = self.decision().model_copy(update={"action": "candidate"})
        signed_changed = sign_skill_installation_decision(
            changed,
            "skill-installer",
            self.signer.private_bytes_raw(),
        )
        with self.assertRaisesRegex(ValueError, "candidate installation requires"):
            self.authenticate(signed_changed, action="candidate")

        authorization = self.authenticate()
        with self.assertRaisesRegex(ValueError, "not current"):
            authorization.check_current(self.valid_until)

        newer = control.signed(
            control.decision(
                sequence=8,
                rollback=control.rollback,
                issued_offset=timedelta(minutes=1),
            )
        )
        self.source.anchor.advance(
            newer,
            control.policy,
            self.issued_at + timedelta(minutes=2),
        )
        with self.assertRaisesRegex(ValueError, "latest anchored state"):
            self.authenticate(now_offset=timedelta(minutes=3))

    def test_one_use_claim_is_durable_and_guard_blocks_revocation_commit(self) -> None:
        signed = self.signed()
        authorization = self.authenticate(signed)
        reauthenticated = self.authenticate(
            signed,
            now_offset=timedelta(minutes=2),
        )
        control = self.source.source
        newer = control.signed(
            control.decision(
                sequence=8,
                rollback=control.rollback,
                issued_offset=timedelta(minutes=1),
            )
        )
        at = self.issued_at + timedelta(minutes=2)
        with self.guard(authorization) as claim:
            self.assertTrue(claim.authorization_consumed)
            self.assertFalse(claim.installation_performed)
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                self.source.anchor.advance(newer, control.policy, at)

        snapshot = self.claim_store.snapshot(self.policy)
        self.assertEqual(snapshot.claims, (claim,))
        self.assertEqual(stat.S_IMODE(self.claim_store.path.stat().st_mode), 0o600)
        with (
            self.assertRaisesRegex(ValueError, "already consumed"),
            self.guard(
                reauthenticated,
                now_offset=timedelta(minutes=3),
            ),
        ):
            self.fail("reauthentication must not create a second use")

        advanced = self.source.anchor.advance(
            newer,
            control.policy,
            at + timedelta(seconds=1),
        )
        self.assertEqual(advanced.latest.signed_control, newer)  # type: ignore[union-attr]

    def test_failed_install_attempt_remains_conservatively_consumed(self) -> None:
        authorization = self.authenticate()
        with (
            self.assertRaisesRegex(RuntimeError, "simulated install failure"),
            self.guard(authorization),
        ):
            raise RuntimeError("simulated install failure")
        self.assertEqual(len(self.claim_store.snapshot(self.policy).claims), 1)
        with (
            self.assertRaisesRegex(ValueError, "already consumed"),
            self.guard(authorization),
        ):
            self.fail("failed installation claim cannot be retried")

    def test_claim_store_rejects_substitution_tampering_and_limits(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            SkillInstallationClaimStore.create(
                self.root / "wrong-claims.sqlite",
                self.claim_policy.model_copy(update={"store_id": "c" * 64}),
                self.policy,
            )
        public_parent = self.root / "public"
        public_parent.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError, "parent must be private"):
            SkillInstallationClaimStore.create(
                public_parent / "claims.sqlite",
                self.claim_policy,
                self.policy,
            )

        authorization = self.authenticate()
        with self.guard(authorization):
            pass
        with sqlite3.connect(self.claim_store.path) as connection:
            connection.execute(
                "UPDATE claims SET authorization_sha256 = ?",
                ("d" * 64,),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "entry is invalid"):
            self.claim_store.snapshot(self.policy)

        os.chmod(self.claim_store.path, 0o644)
        with self.assertRaisesRegex(ValueError, "mode 0600"):
            SkillInstallationClaimStore(self.claim_store.path)

    def test_cli_derives_authenticates_and_inspects_claim_store(self) -> None:
        control_source = self.source.source
        fixture = control_source.source.promotion
        loaded_sources = (
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            control_source.source.receipt,
            fixture.authority_policy,
            control_source.source.archive,
            control_source.evidence,
            control_source.policy,
            control_source.rollback,
        )
        control_path = self.root / "authenticated-control.json"
        authority_path = self.root / "installation-authorities.json"
        private_write(control_path, canonical_bytes(self.source.control))
        private_write(authority_path, canonical_bytes(self.policy))
        dummy = str(self.root / "unused.json")

        def common(command: str, output: Path) -> list[str]:
            arguments = [command]
            for option in (
                "dataset",
                "plan",
                "sealed-comparison",
                "holdout-use-claim",
                "calibration-report",
                "holdout-report",
                "promotion-receipt",
                "promotion-authority-policy",
                "archive",
                "release-evidence",
                "control-authority-policy",
            ):
                arguments.extend((f"--{option}", dummy))
            for prefix in ("calibration", "holdout"):
                for option in (
                    "batch",
                    "mapping",
                    "raw-results",
                    "grading-batch",
                    "dual-grading-resolution",
                    "dual-graded-observations",
                    "grading-trust-policy",
                    "resolution-trust-policy",
                ):
                    arguments.extend((f"--{prefix}-{option}", dummy))
            arguments.extend(
                (
                    "--authenticated-control",
                    str(control_path),
                    "--control-anchor",
                    str(self.source.anchor.path),
                    "--staging-store",
                    str(self.source.store.root),
                    "--installation-authority-policy",
                    str(authority_path),
                    "--action",
                    "rollback",
                    "--output",
                    str(output),
                )
            )
            return arguments

        decision_path = self.root / "installation-decision.json"
        with (
            patch(
                "mos_eisley.cli._load_skill_release_control_sources",
                return_value=loaded_sources,
            ),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(
                main(
                    [
                        *common("eval-derive-skill-installation", decision_path),
                        "--issued-at",
                        self.issued_at.isoformat(),
                        "--valid-until",
                        self.valid_until.isoformat(),
                    ]
                ),
                0,
            )
        decision = SkillInstallationDecision.model_validate_json(
            decision_path.read_bytes()
        )
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_installation.derived",
        )

        signed = sign_skill_installation_decision(
            decision,
            "skill-installer",
            self.signer.private_bytes_raw(),
        )
        signed_path = self.root / "signed-installation.json"
        private_write(signed_path, canonical_bytes(signed))
        authorization_path = self.root / "installation-authorization.json"
        with (
            patch(
                "mos_eisley.cli._load_skill_release_control_sources",
                return_value=loaded_sources,
            ),
            patch("mos_eisley.cli.datetime") as clock,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            clock.now.return_value = self.issued_at + timedelta(minutes=1)
            self.assertEqual(
                main(
                    [
                        *common(
                            "eval-authenticate-skill-installation",
                            authorization_path,
                        ),
                        "--signed-installation",
                        str(signed_path),
                    ]
                ),
                0,
            )
        authorization = AuthenticatedSkillInstallation.model_validate_json(
            authorization_path.read_bytes()
        )
        event = json.loads(stdout.getvalue())
        self.assertEqual(
            event["authorization_sha256"], authorization.authorization_sha256
        )
        self.assertTrue(event["installation_authorized"])
        self.assertFalse(event["installation_performed"])

        claim_policy_path = self.root / "claim-store-policy.json"
        cli_claim_path = self.root / "cli-claims.sqlite"
        private_write(claim_policy_path, canonical_bytes(self.claim_policy))
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-installation-claim-store-create",
                        str(cli_claim_path),
                        "--store-policy",
                        str(claim_policy_path),
                        "--installation-authority-policy",
                        str(authority_path),
                    ]
                ),
                0,
            )
        self.assertEqual(json.loads(stdout.getvalue())["claims"], 0)
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-installation-claim-store-status",
                        "--store",
                        str(cli_claim_path),
                        "--installation-authority-policy",
                        str(authority_path),
                    ]
                ),
                0,
            )
        self.assertEqual(json.loads(stdout.getvalue())["claims"], [])
        self.assertEqual(stat.S_IMODE(authorization_path.stat().st_mode), 0o600)
