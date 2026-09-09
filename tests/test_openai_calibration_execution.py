"""One-assignment calibration execution decisions remain exact and unused."""

from __future__ import annotations

import base64
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.openai_calibration_campaign import plan_openai_calibration_campaign
from mos_eisley.run.openai_calibration_execution import (
    AuthenticatedOpenAICalibrationExecution,
    OpenAICalibrationExecutionAuthorityPolicy,
    OpenAICalibrationExecutionDecision,
    SignedOpenAICalibrationExecutionDecision,
    authenticate_openai_calibration_execution,
    make_openai_calibration_execution_decision,
    sign_openai_calibration_execution_decision,
    trusted_openai_calibration_execution_authority,
)
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write
from tests.test_openai_conformance_conversion import campaign_inputs


class OpenAICalibrationExecutionTests(TestCase):
    def setUp(self) -> None:
        self.batch, self.seed, self.campaign_policy = campaign_inputs()
        self.manifest = plan_openai_calibration_campaign(
            self.batch, self.seed, self.campaign_policy
        )
        self.assignment = self.manifest.assignments[0]
        self.profile = next(
            item
            for item in self.campaign_policy.profiles
            if item.profile_plan_sha256 == self.assignment.profile_plan_sha256
        )
        self.now = datetime.now(UTC)
        self.key = Ed25519PrivateKey.generate()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ledger = SpendLedger.create(
            self.root / "spending.sqlite", self.profile.max_cost_microusd * 2
        )
        self.spend_policy = SpendPolicy(
            schema_version=2,
            model=self.profile.model,
            pricing_source=self.profile.pricing_source,
            valid_from=self.now - timedelta(minutes=5),
            valid_until=self.now + timedelta(minutes=30),
            input_microusd_per_million=(self.profile.input_microusd_per_million),
            cache_write_microusd_per_million=(
                self.profile.cache_write_microusd_per_million
            ),
            output_microusd_per_million=(self.profile.output_microusd_per_million),
            max_cost_microusd=self.profile.max_cost_microusd,
            max_input_tokens=self.profile.max_input_tokens,
            max_output_tokens=self.profile.max_output_tokens,
        )
        self.authority_policy = OpenAICalibrationExecutionAuthorityPolicy(
            policy_id="calibration-executor-v1",
            campaign_policy_sha256=self.campaign_policy.campaign_policy_sha256,
            campaign_manifest_sha256=self.manifest.campaign_manifest_sha256,
            calibration_seed_sha256=self.seed.calibration_seed_sha256,
            spend_ledger_id=self.ledger.policy.ledger_id,
            spend_ledger_policy_sha256=digest(canonical_bytes(self.ledger.policy)),
            valid_from=self.now - timedelta(minutes=5),
            valid_until=self.now + timedelta(minutes=30),
            max_decision_lifetime_seconds=300,
            max_request_timeout_seconds=60,
            authorities=(
                trusted_openai_calibration_execution_authority(
                    "campaign-authorizer", self.key.public_key().public_bytes_raw()
                ),
            ),
        )
        self.audit_directory = self.root / "audit-001"

    def decision(self) -> OpenAICalibrationExecutionDecision:
        return make_openai_calibration_execution_decision(
            self.batch,
            self.seed,
            self.campaign_policy,
            self.manifest,
            self.spend_policy,
            self.ledger,
            self.authority_policy,
            self.assignment.sequence,
            self.audit_directory,
            30,
            self.now,
            self.now + timedelta(minutes=3),
        )

    def signed(self) -> SignedOpenAICalibrationExecutionDecision:
        return sign_openai_calibration_execution_decision(
            self.decision(), "campaign-authorizer", self.key.private_bytes_raw()
        )

    def write_cli_sources(self) -> dict[str, Path]:
        sources = {
            "batch": self.root / "batch.json",
            "calibration-seed": self.root / "seed.json",
            "campaign-policy": self.root / "campaign-policy.json",
            "campaign-manifest": self.root / "campaign-manifest.json",
            "spend-policy": self.root / "spend-policy.json",
            "spend-ledger": self.ledger.path,
            "execution-authority-policy": self.root / "authority-policy.json",
        }
        values = (
            self.batch,
            self.seed,
            self.campaign_policy,
            self.manifest,
            self.spend_policy,
            self.authority_policy,
        )
        for path, value in zip(
            (item for name, item in sources.items() if name != "spend-ledger"),
            values,
            strict=True,
        ):
            private_write(path, canonical_bytes(value))
        return sources

    @staticmethod
    def source_arguments(sources: dict[str, Path]) -> list[str]:
        arguments: list[str] = []
        for name, path in sources.items():
            arguments.extend((f"--{name}", str(path)))
        return arguments

    def test_derives_and_authenticates_one_exact_unused_assignment(self) -> None:
        before = self.ledger.snapshot()
        decision = self.decision()
        self.assertEqual(decision.sequence, self.assignment.sequence)
        self.assertEqual(decision.batch_position, self.assignment.batch_position)
        self.assertEqual(
            decision.assignment_authorization.evaluation_request_sha256,
            self.assignment.evaluation_request_sha256,
        )
        self.assertEqual(
            decision.assignment_authorization.ledger_entry_id,
            digest(str(self.audit_directory.resolve()).encode()),
        )
        self.assertEqual(decision.max_cost_microusd, self.profile.max_cost_microusd)
        self.assertEqual(
            decision.spend_ledger_policy_sha256,
            digest(canonical_bytes(self.ledger.policy)),
        )
        self.assertEqual(self.ledger.snapshot(), before)

        signed = sign_openai_calibration_execution_decision(
            decision, "campaign-authorizer", self.key.private_bytes_raw()
        )
        authenticated = authenticate_openai_calibration_execution(
            self.batch,
            self.seed,
            self.campaign_policy,
            self.manifest,
            self.spend_policy,
            self.ledger,
            self.authority_policy,
            signed,
            self.audit_directory,
            self.now + timedelta(minutes=1),
        )
        self.assertEqual(authenticated.sequence, self.assignment.sequence)
        self.assertTrue(authenticated.one_exact_attempt_authorized)
        self.assertTrue(authenticated.ledger_entry_absent_verified)
        self.assertTrue(authenticated.explicit_local_consent_still_required)
        self.assertFalse(authenticated.credential_accessed)
        self.assertFalse(authenticated.spend_reserved)
        self.assertFalse(authenticated.provider_request_sent)
        self.assertFalse(authenticated.grading_authorized)
        self.assertEqual(self.ledger.snapshot(), before)

    def test_rejects_source_spend_and_signature_substitution(self) -> None:
        changed_assignment = self.assignment.model_copy(
            update={"candidate_id": digest(b"changed-candidate")}
        )
        changed_manifest = self.manifest.model_copy(
            update={
                "assignments": (
                    changed_assignment,
                    *self.manifest.assignments[1:],
                )
            }
        )
        changed_authority = self.authority_policy.model_copy(
            update={
                "campaign_manifest_sha256": changed_manifest.campaign_manifest_sha256
            }
        )
        with self.assertRaisesRegex(ValueError, "fully reverified"):
            make_openai_calibration_execution_decision(
                self.batch,
                self.seed,
                self.campaign_policy,
                changed_manifest,
                self.spend_policy,
                self.ledger,
                changed_authority,
                1,
                self.audit_directory,
                30,
                self.now,
                self.now + timedelta(minutes=3),
            )

        schema_one = self.spend_policy.model_dump()
        schema_one["schema_version"] = 1
        schema_one.pop("cache_write_microusd_per_million")
        with self.assertRaisesRegex(ValueError, "schema-2 spending"):
            make_openai_calibration_execution_decision(
                self.batch,
                self.seed,
                self.campaign_policy,
                self.manifest,
                SpendPolicy.model_validate(schema_one),
                self.ledger,
                self.authority_policy,
                1,
                self.audit_directory,
                30,
                self.now,
                self.now + timedelta(minutes=3),
            )

        signed = self.signed()
        other_key = Ed25519PrivateKey.generate()
        changed_signature = signed.signature.model_copy(
            update={
                "signature_base64": base64.b64encode(
                    other_key.sign(b"not-this-decision")
                ).decode()
            }
        )
        tampered = signed.model_copy(update={"signature": changed_signature})
        with self.assertRaisesRegex(ValueError, "signature is invalid"):
            authenticate_openai_calibration_execution(
                self.batch,
                self.seed,
                self.campaign_policy,
                self.manifest,
                self.spend_policy,
                self.ledger,
                self.authority_policy,
                tampered,
                self.audit_directory,
                self.now + timedelta(minutes=1),
            )

    def test_rejects_used_or_unfunded_ledger_and_expired_window(self) -> None:
        decision = self.decision()
        self.audit_directory.mkdir()
        with self.assertRaisesRegex(ValueError, "fresh audit"):
            self.decision()
        self.audit_directory.rmdir()
        self.ledger.reserve(
            LedgerEntry(
                entry_id=decision.assignment_authorization.ledger_entry_id,
                reservation_sha256="a" * 64,
                reserved_microusd=1,
            )
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.decision()

        with TemporaryDirectory() as directory:
            poor_ledger = SpendLedger.create(Path(directory) / "poor.sqlite", 1)
            poor_authority = self.authority_policy.model_copy(
                update={
                    "spend_ledger_id": poor_ledger.policy.ledger_id,
                    "spend_ledger_policy_sha256": digest(
                        canonical_bytes(poor_ledger.policy)
                    ),
                }
            )
            with self.assertRaisesRegex(ValueError, "not admissible"):
                make_openai_calibration_execution_decision(
                    self.batch,
                    self.seed,
                    self.campaign_policy,
                    self.manifest,
                    self.spend_policy,
                    poor_ledger,
                    poor_authority,
                    1,
                    Path(directory) / "audit",
                    30,
                    self.now,
                    self.now + timedelta(minutes=3),
                )

        overlarge_ledger = SpendLedger.create(
            self.root / "overlarge.sqlite",
            self.campaign_policy.aggregate_max_cost_microusd + 1,
        )
        overlarge_authority = self.authority_policy.model_copy(
            update={
                "spend_ledger_id": overlarge_ledger.policy.ledger_id,
                "spend_ledger_policy_sha256": digest(
                    canonical_bytes(overlarge_ledger.policy)
                ),
            }
        )
        with self.assertRaisesRegex(ValueError, "not admissible"):
            make_openai_calibration_execution_decision(
                self.batch,
                self.seed,
                self.campaign_policy,
                self.manifest,
                self.spend_policy,
                overlarge_ledger,
                overlarge_authority,
                1,
                self.root / "overlarge-audit",
                30,
                self.now,
                self.now + timedelta(minutes=3),
            )

        fresh_ledger = SpendLedger.create(
            self.root / "fresh.sqlite", self.profile.max_cost_microusd * 2
        )
        fresh_authority = self.authority_policy.model_copy(
            update={
                "spend_ledger_id": fresh_ledger.policy.ledger_id,
                "spend_ledger_policy_sha256": digest(
                    canonical_bytes(fresh_ledger.policy)
                ),
            }
        )
        fresh_decision = make_openai_calibration_execution_decision(
            self.batch,
            self.seed,
            self.campaign_policy,
            self.manifest,
            self.spend_policy,
            fresh_ledger,
            fresh_authority,
            1,
            self.root / "fresh-audit",
            30,
            self.now,
            self.now + timedelta(minutes=3),
        )
        fresh_signed = sign_openai_calibration_execution_decision(
            fresh_decision, "campaign-authorizer", self.key.private_bytes_raw()
        )
        with self.assertRaisesRegex(ValueError, "not current"):
            authenticate_openai_calibration_execution(
                self.batch,
                self.seed,
                self.campaign_policy,
                self.manifest,
                self.spend_policy,
                fresh_ledger,
                fresh_authority,
                fresh_signed,
                self.root / "fresh-audit",
                self.now + timedelta(minutes=4),
            )

    def test_signed_contract_round_trip_is_canonical(self) -> None:
        signed = self.signed()
        self.assertEqual(
            SignedOpenAICalibrationExecutionDecision.model_validate_json(
                canonical_bytes(signed)
            ),
            signed,
        )

    def test_cli_derives_and_authenticates_without_credential_or_spend(self) -> None:
        sources = self.write_cli_sources()
        decision_path = self.root / "decision.json"
        derive = [
            "eval-derive-openai-calibration-execution",
            *self.source_arguments(sources),
            "--sequence",
            "1",
            "--audit-dir",
            str(self.audit_directory),
            "--request-timeout",
            "30",
            "--issued-at",
            self.now.isoformat(),
            "--valid-until",
            (self.now + timedelta(minutes=3)).isoformat(),
            "--allow-offline-decision",
            "--output",
            str(decision_path),
        ]
        with (
            patch.dict("os.environ", {}, clear=True),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(main(derive), 0)
        event = json.loads(stdout.getvalue())
        decision = OpenAICalibrationExecutionDecision.model_validate_json(
            decision_path.read_bytes()
        )
        self.assertEqual(event["decision_sha256"], decision.decision_sha256)
        self.assertFalse(event["credential_accessed"])
        self.assertFalse(event["spend_reserved"])
        self.assertFalse(event["provider_request_sent"])
        self.assertEqual(self.ledger.snapshot().entries, 0)

        signed = sign_openai_calibration_execution_decision(
            decision, "campaign-authorizer", self.key.private_bytes_raw()
        )
        signed_path = self.root / "signed-decision.json"
        private_write(signed_path, canonical_bytes(signed))
        authenticated_path = self.root / "authenticated.json"
        authenticate = [
            "eval-authenticate-openai-calibration-execution",
            *self.source_arguments(sources),
            "--signed-decision",
            str(signed_path),
            "--audit-dir",
            str(self.audit_directory),
            "--allow-offline-authentication",
            "--output",
            str(authenticated_path),
        ]
        with (
            patch.dict("os.environ", {}, clear=True),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(main(authenticate), 0)
        event = json.loads(stdout.getvalue())
        authenticated = AuthenticatedOpenAICalibrationExecution.model_validate_json(
            authenticated_path.read_bytes()
        )
        self.assertEqual(
            event["authorization_sha256"], authenticated.authorization_sha256
        )
        self.assertTrue(event["one_use_ledger_entry_required"])
        self.assertTrue(event["explicit_local_consent_still_required"])
        self.assertFalse(event["credential_accessed"])
        self.assertEqual(self.ledger.snapshot().entries, 0)
        self.assertEqual(authenticated_path.stat().st_mode & 0o777, 0o600)

    def test_cli_requires_acknowledgement_and_refuses_credentials(self) -> None:
        sources = self.write_cli_sources()
        output = self.root / "decision.json"
        options = [
            "eval-derive-openai-calibration-execution",
            *self.source_arguments(sources),
            "--sequence",
            "1",
            "--audit-dir",
            str(self.audit_directory),
            "--request-timeout",
            "30",
            "--issued-at",
            self.now.isoformat(),
            "--valid-until",
            (self.now + timedelta(minutes=3)).isoformat(),
            "--output",
            str(output),
        ]
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(options), 2)
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}, clear=True),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(main([*options, "--allow-offline-decision"]), 2)
        self.assertNotIn("secret", stderr.getvalue())
        self.assertFalse(output.exists())
        self.assertEqual(self.ledger.snapshot().entries, 0)
