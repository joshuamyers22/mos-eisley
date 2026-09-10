"""Skill bytes stage transactionally into quarantine without becoming active."""

import io
import json
import os
import sqlite3
import stat
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run import skill_staging as staging_module
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAnchorPolicy,
    authenticate_skill_release_control,
)
from mos_eisley.run.skill_staging import (
    SkillStagingResult,
    SkillStagingStore,
    SkillStagingStorePolicy,
    stage_authenticated_skill_release,
)
from mos_eisley.run.store import private_write
from tests import test_skill_release_control as control_module


class SkillStagingTests(TestCase):
    def setUp(self) -> None:
        self.source = control_module.SkillReleaseControlTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.anchor_policy = SkillReleaseControlAnchorPolicy(
            anchor_id="d" * 64,
            release_evidence_sha256=self.source.evidence.release_evidence_sha256,
            control_authority_policy_sha256=self.source.policy.policy_sha256,
            minimum_sequence=7,
            control_authority_ids=("skill-release-controller",),
        )
        self.anchor = SkillReleaseControlAnchor.create(
            self.root / "release-control.sqlite",
            self.anchor_policy,
            self.source.policy,
        )
        self.signed = self.source.signed()
        self.anchor.advance(
            self.signed,
            self.source.policy,
            self.source.issued_at + timedelta(minutes=1),
        )
        self.control = self.source.authenticate(signed=self.signed)
        self.store_policy = SkillStagingStorePolicy(
            store_id="e" * 64,
            control_anchor_policy_sha256=self.anchor_policy.policy_sha256,
            max_packages=4,
            max_incomplete_transactions=4,
        )
        self.store = SkillStagingStore.create(
            self.root / "staging",
            self.store_policy,
            self.anchor_policy,
        )
        self.stage_at = self.source.issued_at + timedelta(minutes=2)

    def stage(
        self,
        *,
        control: AuthenticatedSkillReleaseControl | None = None,
        anchor: SkillReleaseControlAnchor | None = None,
        store: SkillStagingStore | None = None,
        action: str = "rollback",
    ) -> staging_module.SkillStagingResult:
        fixture = self.source.source.promotion
        return stage_authenticated_skill_release(
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            self.source.source.receipt,
            fixture.authority_policy,
            self.source.source.archive,
            self.source.evidence,
            control or self.control,
            self.source.policy,
            anchor or self.anchor,
            store or self.store,
            action,  # type: ignore[arg-type]
            self.stage_at,
        )

    def _allowed_control(
        self,
    ) -> tuple[AuthenticatedSkillReleaseControl, SkillReleaseControlAnchor]:
        decision = self.source.decision(disposition="allowed")
        signed = self.source.signed(decision)
        fixture = self.source.source.promotion
        control = authenticate_skill_release_control(
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            self.source.source.receipt,
            fixture.authority_policy,
            self.source.source.archive,
            self.source.evidence,
            signed,
            self.source.policy,
            None,
            self.source.issued_at + timedelta(minutes=1),
        )
        anchor = SkillReleaseControlAnchor.create(
            self.root / "allowed-control.sqlite",
            self.anchor_policy.model_copy(update={"anchor_id": "f" * 64}),
            self.source.policy,
        )
        anchor.advance(
            signed,
            self.source.policy,
            self.source.issued_at + timedelta(minutes=1),
        )
        return control, anchor

    def test_stages_exact_nominated_rollback_in_private_atomic_package(self) -> None:
        result = self.stage()
        package_path = Path(result.package_path)

        self.assertFalse(result.already_present)
        self.assertEqual(result.manifest.intent.action, "rollback")
        self.assertEqual(
            result.manifest.intent.archive_sha256,
            self.source.rollback.archive_sha256,
        )
        self.assertTrue(result.manifest.quarantine_staged)
        self.assertFalse(result.installation_authorized)
        self.assertFalse(result.activation_authorized)
        self.assertFalse(result.configuration_mutation_authorized)
        self.assertEqual(package_path.parent, self.store.packages_path)
        self.assertEqual(package_path.name, self.source.rollback.archive_sha256)
        self.assertEqual(stat.S_IMODE(package_path.stat().st_mode), 0o700)
        self.assertEqual(
            (package_path / "payload" / "SKILL.md").read_bytes(),
            self.source.rollback.files[0].payload,
        )
        self.assertEqual(
            stat.S_IMODE((package_path / "payload" / "SKILL.md").stat().st_mode),
            0o600,
        )
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot.packages, (self.source.rollback.archive_sha256,))
        self.assertEqual(snapshot.incomplete, ())
        self.assertEqual(len(snapshot.snapshot_sha256), 64)
        loaded_manifest, loaded_archive = self.store.load(
            self.source.rollback.archive_sha256
        )
        self.assertEqual(loaded_manifest, result.manifest)
        self.assertEqual(loaded_archive, self.source.rollback)

        repeated = self.stage()
        self.assertTrue(repeated.already_present)
        self.assertEqual(repeated.manifest, result.manifest)

    def test_allowed_candidate_staging_remains_quarantine_only(self) -> None:
        control, anchor = self._allowed_control()
        policy = self.store_policy.model_copy(
            update={"control_anchor_policy_sha256": anchor.policy.policy_sha256}
        )
        store = SkillStagingStore.create(
            self.root / "candidate-staging",
            policy,
            anchor.policy,
        )
        result = self.stage(
            control=control,
            anchor=anchor,
            store=store,
            action="candidate",
        )
        self.assertEqual(result.manifest.intent.action, "candidate")
        self.assertEqual(
            result.manifest.intent.archive_sha256,
            self.source.source.archive.archive_sha256,
        )
        self.assertFalse(result.manifest.installation_authorized)
        self.assertFalse(result.manifest.activation_authorized)
        self.assertFalse(result.manifest.configuration_mutation_authorized)

    def test_action_source_policy_and_latest_anchor_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate staging requires"):
            self.stage(action="candidate")

        control, anchor = self._allowed_control()
        policy = self.store_policy.model_copy(
            update={"control_anchor_policy_sha256": anchor.policy.policy_sha256}
        )
        store = SkillStagingStore.create(
            self.root / "action-staging",
            policy,
            anchor.policy,
        )
        with self.assertRaisesRegex(ValueError, "no rollback archive"):
            self.stage(control=control, anchor=anchor, store=store)

        replacement_policy = self.store_policy.model_copy(
            update={"control_anchor_policy_sha256": "1" * 64}
        )
        replacement_root = self.root / "replacement-staging"
        replacement_root.mkdir(mode=0o700)
        staging_module.private_write(
            replacement_root / "policy.json",
            staging_module.canonical_bytes(replacement_policy),
        )
        (replacement_root / "packages").mkdir(mode=0o700)
        (replacement_root / "transactions").mkdir(mode=0o700)
        replacement = SkillStagingStore(replacement_root)
        with self.assertRaisesRegex(
            ValueError, "does not match release control anchor"
        ):
            self.stage(store=replacement)

        newer = self.source.signed(
            self.source.decision(
                sequence=8,
                rollback=self.source.rollback,
                issued_offset=timedelta(minutes=1),
            )
        )
        self.anchor.advance(
            newer,
            self.source.policy,
            self.source.issued_at + timedelta(minutes=2),
        )
        with self.assertRaisesRegex(ValueError, "latest anchored state"):
            self.stage_at = self.source.issued_at + timedelta(minutes=3)
            self.stage()

    def test_latest_control_guard_blocks_a_concurrent_anchor_commit(self) -> None:
        newer = self.source.signed(
            self.source.decision(
                sequence=8,
                rollback=self.source.rollback,
                issued_offset=timedelta(minutes=1),
            )
        )
        at = self.source.issued_at + timedelta(minutes=2)
        with (
            self.anchor.guard_latest(
                self.control,
                self.source.policy,
                at,
            ),
            self.assertRaisesRegex(sqlite3.OperationalError, "locked"),
        ):
            self.anchor.advance(newer, self.source.policy, at)
        snapshot = self.anchor.advance(
            newer,
            self.source.policy,
            at + timedelta(seconds=1),
        )
        self.assertIsNotNone(snapshot.latest)
        assert snapshot.latest is not None
        self.assertEqual(snapshot.latest.signed_control, newer)

    def test_tampered_or_ambient_package_content_breaks_store_verification(
        self,
    ) -> None:
        result = self.stage()
        package_path = Path(result.package_path)
        skill_path = package_path / "payload" / "SKILL.md"
        os.chmod(skill_path, 0o600)
        skill_path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "differs from completion manifest"):
            self.store.snapshot()

        extra_store = SkillStagingStore.create(
            self.root / "extra-staging",
            self.store_policy,
            self.anchor_policy,
        )
        (extra_store.root / "ambient.txt").write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "root inventory is invalid"):
            extra_store.snapshot()

    def test_interrupted_write_is_inventoried_and_never_finalized(self) -> None:
        real_write = staging_module.private_write
        writes = 0

        def fail_during_payload(path: Path, payload: bytes) -> None:
            nonlocal writes
            writes += 1
            if writes == 3:
                raise OSError("simulated storage failure")
            real_write(path, payload)

        with (
            patch.object(
                staging_module,
                "private_write",
                side_effect=fail_during_payload,
            ),
            self.assertRaisesRegex(OSError, "simulated storage failure"),
        ):
            self.stage()
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot.packages, ())
        self.assertEqual(len(snapshot.incomplete), 1)
        self.assertTrue(snapshot.incomplete[0].intent_present)
        self.assertFalse(snapshot.incomplete[0].completion_manifest_present)

    def test_store_creation_and_limits_reject_substitution_or_unbounded_state(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "does not match control anchor"):
            SkillStagingStore.create(
                self.root / "wrong-policy-staging",
                self.store_policy.model_copy(
                    update={"control_anchor_policy_sha256": "2" * 64}
                ),
                self.anchor_policy,
            )

        limited_policy = SkillStagingStorePolicy(
            store_id="3" * 64,
            control_anchor_policy_sha256=self.anchor_policy.policy_sha256,
            max_packages=1,
            max_incomplete_transactions=1,
        )
        limited = SkillStagingStore.create(
            self.root / "limited-staging",
            limited_policy,
            self.anchor_policy,
        )
        (limited.transactions_path / ("a" * 32)).mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "transaction limit reached"):
            self.stage(store=limited)

        os.chmod(limited.root / "policy.json", 0o644)
        with self.assertRaisesRegex(ValueError, "mode 0600"):
            SkillStagingStore(limited.root)

    def test_cli_creates_stages_and_reports_quarantine_store(self) -> None:
        create_policy = self.store_policy.model_copy(update={"store_id": "4" * 64})
        policy_path = self.root / "cli-store-policy.json"
        anchor_policy_path = self.root / "cli-anchor-policy.json"
        private_write(policy_path, canonical_bytes(create_policy))
        private_write(anchor_policy_path, canonical_bytes(self.anchor_policy))
        cli_store_path = self.root / "cli-staging"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-staging-store-create",
                        str(cli_store_path),
                        "--store-policy",
                        str(policy_path),
                        "--anchor-policy",
                        str(anchor_policy_path),
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_staging.store_created",
        )

        control_path = self.root / "authenticated-control.json"
        private_write(control_path, canonical_bytes(self.control))
        output = self.root / "staging-result.json"
        dummy = str(self.root / "unused.json")
        arguments = ["eval-stage-skill-release"]
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
        fixture = self.source.source.promotion
        loaded_sources = (
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            self.source.source.receipt,
            fixture.authority_policy,
            self.source.source.archive,
            self.source.evidence,
            self.source.policy,
            self.source.rollback,
        )
        with (
            patch(
                "mos_eisley.cli._load_skill_release_control_sources",
                return_value=loaded_sources,
            ),
            patch("mos_eisley.cli.datetime") as clock,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            clock.now.return_value = self.stage_at
            self.assertEqual(
                main(
                    [
                        *arguments,
                        "--authenticated-control",
                        str(control_path),
                        "--control-anchor",
                        str(self.anchor.path),
                        "--staging-store",
                        str(cli_store_path),
                        "--action",
                        "rollback",
                        "--output",
                        str(output),
                    ]
                ),
                0,
            )
        event = json.loads(stdout.getvalue())
        result = SkillStagingResult.model_validate_json(output.read_bytes())
        self.assertEqual(event["type"], "evaluation.skill_staging.completed")
        self.assertEqual(event["manifest_sha256"], result.manifest.manifest_sha256)
        self.assertFalse(event["installation_authorized"])
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-staging-store-status",
                        "--store",
                        str(cli_store_path),
                    ]
                ),
                0,
            )
        status = json.loads(stdout.getvalue())
        self.assertEqual(status["packages"], [self.source.rollback.archive_sha256])
        self.assertEqual(status["incomplete_transactions"], [])
        self.assertFalse(status["activation_authorized"])
