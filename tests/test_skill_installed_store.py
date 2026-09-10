"""Authorized skill installation is atomic, inert, and crash-conservative."""

import io
import json
import os
import stat
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run import skill_installed_store as installed_module
from mos_eisley.run.skill_installation import AuthenticatedSkillInstallation
from mos_eisley.run.skill_installed_store import (
    SkillInstalledStore,
    SkillInstalledStorePolicy,
    SkillInstallResult,
    inspect_skill_install_recovery,
    install_authenticated_skill_release,
)
from mos_eisley.run.store import private_write
from tests import test_skill_installation as installation_module


class SkillInstalledStoreTests(TestCase):
    def setUp(self) -> None:
        self.source = installation_module.SkillInstallationTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.authorization = self.source.authenticate()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store_policy = SkillInstalledStorePolicy(
            store_id=self.source.policy.installation_target_id,
            installation_authority_policy_sha256=self.source.policy.policy_sha256,
            staging_store_policy_sha256=self.source.source.store.policy.policy_sha256,
            claim_store_policy_sha256=self.source.claim_policy.policy_sha256,
            max_packages=4,
            max_incomplete_transactions=4,
        )
        self.store = SkillInstalledStore.create(
            self.root / "installed",
            self.store_policy,
            self.source.policy,
            self.source.source.store,
            self.source.claim_policy,
        )
        self.install_at = self.source.issued_at + timedelta(minutes=2)

    def install(
        self,
        *,
        store: SkillInstalledStore | None = None,
        authorization: AuthenticatedSkillInstallation | None = None,
    ) -> SkillInstallResult:
        staging = self.source.source
        control = staging.source
        fixture = control.source.promotion
        return install_authenticated_skill_release(
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
            staging.control,
            control.policy,
            staging.anchor,
            staging.store,
            authorization or self.authorization,
            self.source.policy,
            self.source.claim_store,
            store or self.store,
            "rollback",
            self.install_at,
        )

    def test_installs_exact_bytes_atomically_without_default_or_runtime(self) -> None:
        result = self.install()
        package_path = Path(result.package_path)

        self.assertTrue(result.installation_performed)
        self.assertFalse(result.default_changed)
        self.assertFalse(result.configuration_mutation_authorized)
        self.assertFalse(result.activation_authorized)
        self.assertFalse(result.runtime_lookup_authorized)
        self.assertEqual(package_path.parent, self.store.packages_path)
        self.assertEqual(
            package_path.name,
            self.source.source.source.rollback.archive_sha256,
        )
        self.assertEqual(stat.S_IMODE(package_path.stat().st_mode), 0o700)
        self.assertEqual(
            (package_path / "payload" / "SKILL.md").read_bytes(),
            self.source.source.source.rollback.files[0].payload,
        )
        self.assertEqual(
            stat.S_IMODE((package_path / "payload" / "SKILL.md").stat().st_mode),
            0o600,
        )
        manifest, archive, authorization, claim = self.store.load(
            result.manifest.intent.archive_sha256,
            self.source.policy,
        )
        self.assertEqual(manifest, result.manifest)
        self.assertEqual(archive, self.source.source.source.rollback)
        self.assertEqual(authorization, self.authorization)
        self.assertEqual(claim, result.claim)
        self.assertEqual(self.store.snapshot(self.source.policy).incomplete, ())
        recovery = inspect_skill_install_recovery(
            self.store,
            self.source.policy,
            self.source.claim_store,
        )
        self.assertEqual(len(recovery.entries), 1)
        self.assertEqual(recovery.entries[0].state, "completed")
        self.assertEqual(recovery.unbound_transactions, ())
        self.assertFalse(recovery.automatic_recovery_authorized)
        self.assertFalse(recovery.default_mutation_authorized)
        self.assertFalse(recovery.configuration_mutation_authorized)

    def test_existing_package_fails_before_consuming_another_authorization(
        self,
    ) -> None:
        self.install()
        claims_before = self.source.claim_store.snapshot(self.source.policy).claims
        with self.assertRaisesRegex(ValueError, "already installed"):
            self.install()
        self.assertEqual(
            self.source.claim_store.snapshot(self.source.policy).claims,
            claims_before,
        )

    def test_write_failure_leaves_claimed_incomplete_transaction(self) -> None:
        real_write = installed_module.private_write
        writes = 0

        def fail_after_intent(path: Path, payload: bytes) -> None:
            nonlocal writes
            writes += 1
            if writes == 3:
                raise OSError("simulated install storage failure")
            real_write(path, payload)

        with (
            patch.object(
                installed_module, "private_write", side_effect=fail_after_intent
            ),
            self.assertRaisesRegex(OSError, "simulated install storage failure"),
        ):
            self.install()
        snapshot = self.store.snapshot(self.source.policy)
        self.assertEqual(snapshot.packages, ())
        self.assertEqual(len(snapshot.incomplete), 1)
        self.assertTrue(snapshot.incomplete[0].intent_present)
        self.assertFalse(snapshot.incomplete[0].completion_manifest_present)
        recovery = inspect_skill_install_recovery(
            self.store,
            self.source.policy,
            self.source.claim_store,
        )
        self.assertEqual(recovery.entries[0].state, "incomplete")
        with self.assertRaisesRegex(ValueError, "already consumed"):
            self.install()

    def test_failure_between_claim_and_intent_is_reported_as_claim_only(self) -> None:
        with (
            patch.object(
                self.store,
                "_install_under_guard",
                side_effect=OSError("simulated pre-intent failure"),
            ),
            self.assertRaisesRegex(OSError, "simulated pre-intent failure"),
        ):
            self.install()
        snapshot = self.store.snapshot(self.source.policy)
        self.assertEqual(snapshot.packages, ())
        self.assertEqual(snapshot.incomplete, ())
        unbound = "f" * 32
        (self.store.transactions_path / unbound).mkdir(mode=0o700)
        recovery = inspect_skill_install_recovery(
            self.store,
            self.source.policy,
            self.source.claim_store,
        )
        self.assertEqual(recovery.entries[0].state, "claim_only")
        self.assertEqual(recovery.unbound_transactions, (unbound,))

    def test_store_rejects_policy_substitution_tampering_and_limits(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            SkillInstalledStore.create(
                self.root / "wrong-installed",
                self.store_policy.model_copy(update={"store_id": "c" * 64}),
                self.source.policy,
                self.source.source.store,
                self.source.claim_policy,
            )

        limited_policy = self.store_policy.model_copy(
            update={
                "store_id": "d" * 64,
                "max_incomplete_transactions": 1,
            }
        )
        limited_authority = self.source.policy.model_copy(
            update={"installation_target_id": "d" * 64}
        )
        limited_policy = limited_policy.model_copy(
            update={
                "installation_authority_policy_sha256": (
                    limited_authority.policy_sha256
                )
            }
        )
        limited_claim_policy = self.source.claim_policy.model_copy(
            update={"authority_policy_sha256": limited_authority.policy_sha256}
        )
        limited_policy = limited_policy.model_copy(
            update={"claim_store_policy_sha256": limited_claim_policy.policy_sha256}
        )
        limited = SkillInstalledStore.create(
            self.root / "limited-installed",
            limited_policy,
            limited_authority,
            self.source.source.store,
            limited_claim_policy,
        )
        (limited.transactions_path / ("e" * 32)).mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "transaction limit reached"):
            limited.preflight_absent(
                self.authorization.archive_sha256,
                limited_authority,
            )

        dangling = self.store.transactions_path / ("a" * 32)
        dangling.mkdir(mode=0o700)
        (dangling / "intent.json").symlink_to(dangling / "missing.json")
        with self.assertRaisesRegex(ValueError, "non-symlink regular file"):
            self.store.snapshot(self.source.policy)
        (dangling / "intent.json").unlink()
        dangling.rmdir()

        result = self.install()
        manifest = Path(result.package_path) / "manifest.json"
        canonical_manifest = manifest.read_bytes()
        manifest.write_bytes(canonical_manifest + b"\n")
        with self.assertRaisesRegex(ValueError, "provenance or inventory"):
            self.store.snapshot(self.source.policy)
        manifest.write_bytes(canonical_manifest)
        payload = Path(result.package_path) / "payload" / "SKILL.md"
        payload.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "payload differs"):
            self.store.snapshot(self.source.policy)

        os.chmod(self.store.root / "install.lock", 0o644)
        with self.assertRaisesRegex(ValueError, "mode 0600"):
            SkillInstalledStore(self.store.root)

    def test_cli_creates_installs_and_reports_recovery(self) -> None:
        authority_path = self.root / "installation-authorities.json"
        claim_policy_path = self.root / "claim-policy.json"
        store_policy_path = self.root / "installed-store-policy.json"
        authorization_path = self.root / "installation-authorization.json"
        control_path = self.root / "authenticated-control.json"
        private_write(authority_path, canonical_bytes(self.source.policy))
        private_write(claim_policy_path, canonical_bytes(self.source.claim_policy))
        private_write(store_policy_path, canonical_bytes(self.store_policy))
        private_write(authorization_path, canonical_bytes(self.authorization))
        private_write(control_path, canonical_bytes(self.source.source.control))
        cli_store_path = self.root / "cli-installed"

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-installed-store-create",
                        str(cli_store_path),
                        "--store-policy",
                        str(store_policy_path),
                        "--installation-authority-policy",
                        str(authority_path),
                        "--staging-store",
                        str(self.source.source.store.root),
                        "--claim-store-policy",
                        str(claim_policy_path),
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_installation.store_created",
        )

        control_source = self.source.source.source
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
        dummy = str(self.root / "unused.json")
        output = self.root / "install-result.json"
        arguments = ["eval-install-skill-release"]
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
                str(self.source.source.anchor.path),
                "--staging-store",
                str(self.source.source.store.root),
                "--authenticated-installation",
                str(authorization_path),
                "--installation-authority-policy",
                str(authority_path),
                "--claim-store",
                str(self.source.claim_store.path),
                "--installed-store",
                str(cli_store_path),
                "--action",
                "rollback",
                "--output",
                str(output),
            )
        )
        with (
            patch(
                "mos_eisley.cli._load_skill_release_control_sources",
                return_value=loaded_sources,
            ),
            patch("mos_eisley.cli.datetime") as clock,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            clock.now.return_value = self.install_at
            self.assertEqual(main(arguments), 0)
        event = json.loads(stdout.getvalue())
        result = SkillInstallResult.model_validate_json(output.read_bytes())
        self.assertEqual(event["manifest_sha256"], result.manifest.manifest_sha256)
        self.assertTrue(event["installation_performed"])
        self.assertFalse(event["default_changed"])
        self.assertFalse(event["configuration_mutation_authorized"])

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-installed-store-status",
                        "--store",
                        str(cli_store_path),
                        "--installation-authority-policy",
                        str(authority_path),
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(stdout.getvalue())["packages"],
            [self.authorization.archive_sha256],
        )

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-install-recovery-status",
                        "--installed-store",
                        str(cli_store_path),
                        "--claim-store",
                        str(self.source.claim_store.path),
                        "--installation-authority-policy",
                        str(authority_path),
                    ]
                ),
                0,
            )
        recovery = json.loads(stdout.getvalue())
        self.assertEqual(recovery["entries"][0]["state"], "completed")
        self.assertEqual(recovery["unbound_transactions"], [])
        self.assertFalse(recovery["automatic_recovery_authorized"])
        self.assertFalse(recovery["configuration_mutation_authorized"])
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
