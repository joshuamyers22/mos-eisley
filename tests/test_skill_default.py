"""Default selection is independently signed, atomic, and not runtime activation."""

import io
import json
import os
import sqlite3
import stat
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.skill_default import (
    AuthenticatedSkillDefault,
    SignedSkillDefaultDecision,
    SkillDefaultAuthorityPolicy,
    SkillDefaultDecision,
    SkillDefaultSelectionResult,
    SkillDefaultStore,
    SkillDefaultStorePolicy,
    authenticate_skill_default,
    make_skill_default_decision,
    select_authenticated_skill_default,
    sign_skill_default_decision,
    trusted_skill_default_authority,
    verify_signed_skill_default_decision,
)
from mos_eisley.run.skill_installed_store import (
    InstalledSkillFile,
    InstalledSkillManifest,
)
from mos_eisley.run.store import private_write
from tests import test_skill_installed_store as installed_module


class SkillDefaultTests(TestCase):
    def setUp(self) -> None:
        self.source = installed_module.SkillInstalledStoreTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.installation = self.source.install()
        self.signer = Ed25519PrivateKey.generate()
        self.issued_at = self.source.install_at + timedelta(seconds=10)
        self.valid_until = self.issued_at + timedelta(minutes=2)
        control_fixture = self.source.source.source.source
        self.policy = SkillDefaultAuthorityPolicy(
            policy_id="skill-default-authorities-v1",
            installed_store_policy_sha256=self.source.store.policy.policy_sha256,
            installation_authority_policy_sha256=self.source.source.policy.policy_sha256,
            control_anchor_policy_sha256=(
                self.source.source.source.anchor.policy.policy_sha256
            ),
            default_store_id="1" * 64,
            valid_from=self.issued_at - timedelta(minutes=1),
            valid_until=control_fixture.valid_until,
            max_decision_lifetime_seconds=300,
            authorities=(
                trusted_skill_default_authority(
                    "skill-default-selector",
                    self.signer.public_key().public_bytes_raw(),
                ),
            ),
        )
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store_policy = SkillDefaultStorePolicy(
            store_id=self.policy.default_store_id,
            authority_policy_sha256=self.policy.policy_sha256,
            installed_store_policy_sha256=self.source.store.policy.policy_sha256,
            max_revisions=4,
            max_history_bytes=1_000_000,
        )
        self.store = SkillDefaultStore.create(
            self.root / "skill-default.sqlite",
            self.store_policy,
            self.policy,
            self.source.store,
        )

    def _arguments(self) -> tuple[object, ...]:
        staging = self.source.source.source
        control = staging.source
        fixture = control.source.promotion
        return (
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
            self.source.store,
            self.source.source.policy,
        )

    def decision(
        self,
        *,
        policy: SkillDefaultAuthorityPolicy | None = None,
    ) -> SkillDefaultDecision:
        call = cast(Any, make_skill_default_decision)
        return call(
            *self._arguments(),
            self.store,
            policy or self.policy,
            "rollback",
            self.issued_at,
            self.valid_until,
        )

    def signed(self) -> SignedSkillDefaultDecision:
        return sign_skill_default_decision(
            self.decision(),
            "skill-default-selector",
            self.signer.private_bytes_raw(),
        )

    def authenticate(
        self,
        signed: SignedSkillDefaultDecision | None = None,
        *,
        offset: timedelta = timedelta(seconds=10),
    ) -> AuthenticatedSkillDefault:
        call = cast(Any, authenticate_skill_default)
        return call(
            *self._arguments(),
            self.store,
            signed or self.signed(),
            self.policy,
            "rollback",
            self.issued_at + offset,
        )

    def select(
        self,
        authorization: AuthenticatedSkillDefault,
        *,
        offset: timedelta = timedelta(seconds=20),
    ) -> SkillDefaultSelectionResult:
        call = cast(Any, select_authenticated_skill_default)
        return call(
            *self._arguments(),
            self.store,
            authorization,
            self.policy,
            "rollback",
            self.issued_at + offset,
        )

    def test_selects_exact_installed_default_atomically_without_activation(
        self,
    ) -> None:
        decision = self.decision()
        signed = sign_skill_default_decision(
            decision,
            "skill-default-selector",
            self.signer.private_bytes_raw(),
        )
        authorization = self.authenticate(signed)
        result = self.select(authorization)
        snapshot = self.store.snapshot(
            self.policy,
            self.source.store,
            self.source.source.policy,
        )

        self.assertEqual(snapshot.revisions, 1)
        self.assertEqual(snapshot.current, result.pointer)
        self.assertEqual(
            result.pointer.archive_sha256,
            self.installation.manifest.intent.archive_sha256,
        )
        self.assertEqual(
            result.pointer.installed_manifest_sha256,
            self.installation.manifest.manifest_sha256,
        )
        self.assertTrue(result.default_changed)
        self.assertTrue(result.authorization_consumed)
        self.assertTrue(result.atomic_commit)
        self.assertFalse(result.other_configuration_mutation_authorized)
        self.assertFalse(result.activation_authorized)
        self.assertFalse(result.runtime_lookup_authorized)
        self.assertFalse(snapshot.runtime_lookup_authorized)
        self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode), 0o600)
        self.assertEqual(
            verify_signed_skill_default_decision(signed, self.policy).authority_id,
            "skill-default-selector",
        )
        with self.assertRaisesRegex(ValueError, "already the default"):
            self.select(authorization, offset=timedelta(seconds=30))

    def test_atomic_failure_rolls_back_consumption_and_pointer(self) -> None:
        authorization = self.authenticate()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_current BEFORE INSERT ON current_pointer "
                "BEGIN SELECT RAISE(ABORT, 'simulated pointer failure'); END"
            )
            connection.commit()
        with self.assertRaisesRegex(
            sqlite3.IntegrityError, "simulated pointer failure"
        ):
            self.select(authorization)
        snapshot = self.store.snapshot(
            self.policy,
            self.source.store,
            self.source.source.policy,
        )
        self.assertEqual(snapshot.revisions, 0)
        self.assertIsNone(snapshot.current)
        with sqlite3.connect(self.store.path) as connection:
            connection.execute("DROP TRIGGER fail_current")
            connection.commit()
        result = self.select(authorization, offset=timedelta(seconds=30))
        self.assertEqual(result.pointer.sequence, 1)

    def test_authority_independence_signature_state_and_expiry_fail_closed(
        self,
    ) -> None:
        installation_policy = self.source.source.policy
        overlapping = self.policy.model_copy(
            update={
                "authorities": (
                    trusted_skill_default_authority(
                        "skill-installer",
                        self.source.source.signer.public_key().public_bytes_raw(),
                    ),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "must be independent"):
            self.decision(policy=overlapping)

        signed = self.signed()
        changed = signed.model_copy(
            update={
                "decision": signed.decision.model_copy(
                    update={"archive_sha256": "2" * 64}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "does not identify"):
            verify_signed_skill_default_decision(changed, self.policy)

        authorization = self.authenticate(signed)
        with self.assertRaisesRegex(ValueError, "not current"):
            authorization.check_current(self.valid_until)
        self.assertEqual(
            self.policy.installation_authority_policy_sha256,
            installation_policy.policy_sha256,
        )

    def test_release_guard_blocks_concurrent_revocation_while_pointer_commits(
        self,
    ) -> None:
        authorization = self.authenticate()
        staging = self.source.source.source
        control = staging.source
        newer = control.signed(
            control.decision(
                sequence=8,
                rollback=control.rollback,
                issued_offset=timedelta(minutes=1),
            )
        )
        real_select = self.store._select_under_guard  # pyright: ignore[reportPrivateUsage]

        def guarded_select(
            *args: object, **kwargs: object
        ) -> SkillDefaultSelectionResult:
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                staging.anchor.advance(
                    newer,
                    control.policy,
                    self.issued_at + timedelta(seconds=20),
                )
            return real_select(*args, **kwargs)  # type: ignore[arg-type]

        with patch.object(
            self.store, "_select_under_guard", side_effect=guarded_select
        ):
            result = self.select(authorization)
        self.assertEqual(result.pointer.sequence, 1)

    def test_revision_chain_advances_and_rejects_stale_compare_and_swap(self) -> None:
        first_decision = self.decision()
        first_signed = sign_skill_default_decision(
            first_decision,
            "skill-default-selector",
            self.signer.private_bytes_raw(),
        )
        first_authorization = self.authenticate(first_signed)
        first_result = self.select(first_authorization)
        first_loaded = self.source.store.load(
            first_result.pointer.archive_sha256,
            self.source.source.policy,
        )

        control = self.source.source.source.source
        candidate = control.source.archive
        candidate_intent = self.installation.manifest.intent.model_copy(
            update={
                "transaction_id": "candidate-default-test",
                "action": "candidate",
                "archive_sha256": candidate.archive_sha256,
                "skill": candidate.descriptor.identity,
            }
        )
        candidate_manifest = InstalledSkillManifest(
            intent=candidate_intent,
            descriptor=candidate.descriptor,
            files=tuple(
                InstalledSkillFile(
                    path=item.path,
                    content_sha256=item.content_sha256,
                    byte_count=item.byte_count,
                )
                for item in candidate.files
            ),
            installed_at=self.issued_at + timedelta(seconds=21),
        )
        second_decision = first_decision.model_copy(
            update={
                "installed_manifest_sha256": candidate_manifest.manifest_sha256,
                "sequence": 2,
                "expected_previous_pointer_sha256": (
                    first_result.pointer.pointer_sha256
                ),
                "action": "candidate",
                "archive_sha256": candidate.archive_sha256,
                "skill": candidate.descriptor.identity,
                "issued_at": self.issued_at + timedelta(seconds=22),
            }
        )
        second_signed = sign_skill_default_decision(
            second_decision,
            "skill-default-selector",
            self.signer.private_bytes_raw(),
        )
        second_authorization = AuthenticatedSkillDefault(
            authority_policy_sha256=self.policy.policy_sha256,
            installed_manifest_sha256=candidate_manifest.manifest_sha256,
            archive_sha256=candidate.archive_sha256,
            skill=candidate.descriptor.identity,
            default_store_id=self.store.policy.store_id,
            signed_decision=second_signed,
            authenticated_at=self.issued_at + timedelta(seconds=23),
            valid_until=second_decision.valid_until,
        )

        def load(archive_sha256: str, _: object) -> tuple[object, ...]:
            if archive_sha256 == candidate.archive_sha256:
                return (
                    candidate_manifest,
                    candidate,
                    first_loaded[2],
                    first_loaded[3],
                )
            return first_loaded

        with patch.object(self.source.store, "load", side_effect=load):
            second_result = self.store._select_under_guard(  # pyright: ignore[reportPrivateUsage]
                second_authorization,
                candidate_manifest,
                self.policy,
                self.source.store,
                self.source.source.policy,
                self.issued_at + timedelta(seconds=24),
            )
            snapshot = self.store.snapshot(
                self.policy,
                self.source.store,
                self.source.source.policy,
            )
            with self.assertRaisesRegex(ValueError, "stale or mismatched"):
                self.store._select_under_guard(  # pyright: ignore[reportPrivateUsage]
                    first_authorization,
                    first_loaded[0],
                    self.policy,
                    self.source.store,
                    self.source.source.policy,
                    self.issued_at + timedelta(seconds=25),
                )
        self.assertEqual(snapshot.revisions, 2)
        self.assertEqual(snapshot.current, second_result.pointer)
        self.assertEqual(
            second_result.pointer.previous_pointer_sha256,
            first_result.pointer.pointer_sha256,
        )

    def test_store_rejects_policy_substitution_tampering_and_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            SkillDefaultStore.create(
                self.root / "wrong-default.sqlite",
                self.store_policy.model_copy(update={"store_id": "3" * 64}),
                self.policy,
                self.source.store,
            )
        result = self.select(self.authenticate())
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "UPDATE selections SET pointer_sha256 = ? WHERE sequence = 1",
                ("4" * 64,),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "history is invalid"):
            self.store.snapshot(
                self.policy,
                self.source.store,
                self.source.source.policy,
            )
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "UPDATE selections SET pointer_sha256 = ?, "
                "record = zeroblob(1000001) WHERE sequence = 1",
                (result.pointer.pointer_sha256,),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "exceeds policy"):
            self.store.snapshot(
                self.policy,
                self.source.store,
                self.source.source.policy,
            )
        self.assertEqual(result.pointer.sequence, 1)
        os.chmod(self.store.path, 0o644)
        with self.assertRaisesRegex(ValueError, "mode 0600"):
            SkillDefaultStore(self.store.path)

    def test_cli_derives_authenticates_selects_and_reports_pointer(self) -> None:
        default_policy_path = self.root / "default-authorities.json"
        default_store_policy_path = self.root / "default-store-policy.json"
        installation_policy_path = self.root / "installation-authorities.json"
        control_path = self.root / "authenticated-control.json"
        private_write(default_policy_path, canonical_bytes(self.policy))
        private_write(default_store_policy_path, canonical_bytes(self.store_policy))
        private_write(
            installation_policy_path, canonical_bytes(self.source.source.policy)
        )
        staging = self.source.source.source
        private_write(control_path, canonical_bytes(staging.control))
        cli_store_path = self.root / "cli-default.sqlite"

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-default-store-create",
                        str(cli_store_path),
                        "--store-policy",
                        str(default_store_policy_path),
                        "--default-authority-policy",
                        str(default_policy_path),
                        "--installed-store",
                        str(self.source.store.root),
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_default.store_created",
        )

        control = staging.source
        fixture = control.source.promotion
        loaded_sources = (
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
            control.policy,
            control.rollback,
        )
        dummy = str(self.root / "unused.json")
        common: list[str] = []
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
            common.extend((f"--{option}", dummy))
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
                common.extend((f"--{prefix}-{option}", dummy))
        common.extend(
            (
                "--authenticated-control",
                str(control_path),
                "--control-anchor",
                str(staging.anchor.path),
                "--installed-store",
                str(self.source.store.root),
                "--installation-authority-policy",
                str(installation_policy_path),
                "--default-store",
                str(cli_store_path),
                "--default-authority-policy",
                str(default_policy_path),
                "--action",
                "rollback",
            )
        )

        decision_path = self.root / "default-decision.json"
        derive = ["eval-derive-skill-default", *common]
        derive.extend(
            (
                "--issued-at",
                self.issued_at.isoformat(),
                "--valid-until",
                self.valid_until.isoformat(),
                "--output",
                str(decision_path),
            )
        )
        with (
            patch(
                "mos_eisley.cli._load_skill_release_control_sources",
                return_value=loaded_sources,
            ),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(main(derive), 0)
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_default.derived",
        )
        decision = SkillDefaultDecision.model_validate_json(decision_path.read_bytes())
        signed = sign_skill_default_decision(
            decision,
            "skill-default-selector",
            self.signer.private_bytes_raw(),
        )
        signed_path = self.root / "signed-default.json"
        private_write(signed_path, canonical_bytes(signed))

        authorization_path = self.root / "default-authorization.json"
        authenticate = ["eval-authenticate-skill-default", *common]
        authenticate.extend(
            (
                "--signed-default",
                str(signed_path),
                "--output",
                str(authorization_path),
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
            clock.now.return_value = self.issued_at + timedelta(seconds=10)
            self.assertEqual(main(authenticate), 0)
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_default.authenticated",
        )

        result_path = self.root / "default-result.json"
        select = ["eval-select-skill-default", *common]
        select.extend(
            (
                "--authenticated-default",
                str(authorization_path),
                "--output",
                str(result_path),
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
            clock.now.return_value = self.issued_at + timedelta(seconds=20)
            self.assertEqual(main(select), 0)
        event = json.loads(stdout.getvalue())
        self.assertEqual(event["type"], "evaluation.skill_default.selected")
        self.assertTrue(event["default_changed"])
        self.assertFalse(event["runtime_lookup_authorized"])

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-default-store-status",
                        "--store",
                        str(cli_store_path),
                        "--default-authority-policy",
                        str(default_policy_path),
                        "--installed-store",
                        str(self.source.store.root),
                        "--installation-authority-policy",
                        str(installation_policy_path),
                    ]
                ),
                0,
            )
        status = json.loads(stdout.getvalue())
        self.assertEqual(status["revisions"], 1)
        self.assertEqual(status["current"]["archive_sha256"], decision.archive_sha256)
        self.assertFalse(status["default_changed"])
        self.assertFalse(status["other_configuration_mutation_authorized"])
        self.assertFalse(status["runtime_lookup_authorized"])
        self.assertEqual(stat.S_IMODE(result_path.stat().st_mode), 0o600)
