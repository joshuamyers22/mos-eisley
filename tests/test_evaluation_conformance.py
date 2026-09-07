"""Signed evaluation conformance authenticates one probe, never batch scoring."""

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
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Critique, canonical_bytes, digest
from mos_eisley.core.protocol import Usage
from mos_eisley.run.broker_audit import (
    AssignmentAuthorization,
    BrokerAudit,
    inspect_broker_recovery,
)
from mos_eisley.run.brokered_evaluation import BrokeredEvaluationArtifact
from mos_eisley.run.evaluation_conformance import (
    AuthenticatedEvaluationConformance,
    EvaluationConformanceObservation,
    EvaluationConformancePolicy,
    authenticate_evaluation_conformance,
    make_evaluation_conformance_observation,
    sign_evaluation_conformance_observation,
    trusted_evaluation_conformance_observer,
)
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger
from mos_eisley.run.store import private_write
from tests.test_openai_conformance import conformance_inputs


class EvaluationConformanceTests(TestCase):
    def setUp(self) -> None:
        self.batch, _ = conformance_inputs()
        self.request = self.batch.requests[0]
        self.now = datetime(2026, 9, 6, 12, tzinfo=UTC)
        self.private_key = Ed25519PrivateKey.generate()
        public_key = self.private_key.public_key().public_bytes_raw()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.audit_directory = self.root / "audit"
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 500)
        self.authorization = AssignmentAuthorization(
            plan_sha256=self.batch.plan_sha256,
            batch_sha256=self.batch.batch_sha256,
            sample_id=self.request.sample_id,
            candidate_id=self.request.route.candidate_id,
            evaluation_request_sha256=self.request.request_sha256,
            provider_request_sha256="1" * 64,
            spend_policy_sha256="2" * 64,
            ledger_id=self.ledger.policy.ledger_id,
            ledger_entry_id="4" * 64,
        )
        reservation_sha256 = "3" * 64
        self.ledger.reserve(
            LedgerEntry(
                entry_id=self.authorization.ledger_entry_id,
                reservation_sha256=reservation_sha256,
                reserved_microusd=300,
            )
        )
        self.ledger.settle(
            LedgerSettlement(
                entry_id=self.authorization.ledger_entry_id,
                reservation_sha256=reservation_sha256,
                status="settled",
                charged_microusd=140,
            )
        )
        audit = BrokerAudit(self.audit_directory, self.authorization)
        audit.admit()
        audit.finish("response_received", "6" * 64, 420)
        state = inspect_broker_recovery(
            self.audit_directory, self.authorization, self.ledger
        )
        assert state.outcome_sha256 is not None
        self.artifact = BrokeredEvaluationArtifact(
            authorization=self.authorization,
            authorization_sha256=digest(canonical_bytes(self.authorization)),
            outcome_sha256=state.outcome_sha256,
            provider_response_sha256="6" * 64,
            provider_request_id="resp_probe_1",
            usage=Usage(
                unit="tokens", input=100, output=20, reasoning=10, cache_read=0
            ),
            latency_ms=420,
            cost_microusd=140,
            critique=Critique(),
        )
        self.policy = EvaluationConformancePolicy(
            policy_id="openai-probe-1",
            plan_sha256=self.batch.plan_sha256,
            batch_sha256=self.batch.batch_sha256,
            sample_id=self.request.sample_id,
            candidate_id=self.request.route.candidate_id,
            evaluation_request_sha256=self.request.request_sha256,
            provider_request_sha256=self.authorization.provider_request_sha256,
            spend_policy_sha256=self.authorization.spend_policy_sha256,
            ledger_id=self.authorization.ledger_id,
            ledger_entry_id=self.authorization.ledger_entry_id,
            valid_from=self.now - timedelta(minutes=5),
            valid_until=self.now + timedelta(minutes=5),
            max_observation_age_seconds=120,
            observers=(
                trusted_evaluation_conformance_observer("observer-a", public_key),
            ),
            allowed_sdk_versions=("2.54.0",),
        )

    def observation(self):
        return make_evaluation_conformance_observation(
            self.batch,
            self.artifact,
            self.authorization,
            self.audit_directory,
            self.ledger,
            self.policy,
            self.now,
            "2.54.0",
            "7" * 64,
        )

    def test_authenticates_exact_probe_without_authorizing_conversion(self) -> None:
        observation = self.observation()
        signed = sign_evaluation_conformance_observation(
            observation, "observer-a", self.private_key.private_bytes_raw()
        )
        authenticated = authenticate_evaluation_conformance(
            signed,
            self.policy,
            self.batch,
            self.artifact,
            self.authorization,
            self.audit_directory,
            self.ledger,
            self.now + timedelta(seconds=30),
        )
        self.assertEqual(authenticated.artifact_sha256, self.artifact.artifact_sha256)
        self.assertEqual(authenticated.sample_id, self.request.sample_id)
        self.assertTrue(authenticated.credentialed_exchange_attested)
        self.assertTrue(authenticated.local_batch_and_artifact_reverified)
        self.assertFalse(authenticated.provider_authorship_proven)
        self.assertFalse(authenticated.billing_reconciled)
        self.assertFalse(authenticated.complete_batch_conformance_proven)
        self.assertFalse(authenticated.batch_conversion_authorized)
        self.assertFalse(authenticated.grading_authorized)
        self.assertFalse(authenticated.scoring_authorized)
        self.assertFalse(authenticated.promotion_authorized)
        AuthenticatedEvaluationConformance.model_validate_json(
            canonical_bytes(authenticated)
        )

    def test_route_artifact_and_policy_substitution_fail_closed(self) -> None:
        observation = self.observation()
        changed_artifact = self.artifact.model_copy(update={"outcome_sha256": "8" * 64})
        signed = sign_evaluation_conformance_observation(
            observation, "observer-a", self.private_key.private_bytes_raw()
        )
        with self.assertRaisesRegex(ValueError, "local provenance mismatch"):
            authenticate_evaluation_conformance(
                signed,
                self.policy,
                self.batch,
                changed_artifact,
                self.authorization,
                self.audit_directory,
                self.ledger,
                self.now,
            )

        other_ledger = SpendLedger.create(self.root / "other-ledger.sqlite", 500)
        with self.assertRaisesRegex(ValueError, "recovery identity mismatch"):
            authenticate_evaluation_conformance(
                signed,
                self.policy,
                self.batch,
                self.artifact,
                self.authorization,
                self.audit_directory,
                other_ledger,
                self.now,
            )

        changed_policy = self.policy.model_copy(
            update={"evaluation_request_sha256": "9" * 64}
        )
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            make_evaluation_conformance_observation(
                self.batch,
                self.artifact,
                self.authorization,
                self.audit_directory,
                self.ledger,
                changed_policy,
                self.now,
                "2.54.0",
                "7" * 64,
            )

    def test_stale_untrusted_and_tampered_observations_are_rejected(self) -> None:
        observation = self.observation()
        signed = sign_evaluation_conformance_observation(
            observation, "observer-a", self.private_key.private_bytes_raw()
        )
        with self.assertRaisesRegex(ValueError, "does not match policy"):
            authenticate_evaluation_conformance(
                signed,
                self.policy,
                self.batch,
                self.artifact,
                self.authorization,
                self.audit_directory,
                self.ledger,
                self.now + timedelta(seconds=121),
            )

        untrusted = sign_evaluation_conformance_observation(
            observation, "observer-z", Ed25519PrivateKey.generate().private_bytes_raw()
        )
        with self.assertRaisesRegex(ValueError, "is not trusted"):
            authenticate_evaluation_conformance(
                untrusted,
                self.policy,
                self.batch,
                self.artifact,
                self.authorization,
                self.audit_directory,
                self.ledger,
                self.now,
            )

        tampered = signed.model_copy(
            update={
                "signature": signed.signature.model_copy(
                    update={
                        "signature_base64": base64.b64encode(bytes(64)).decode("ascii")
                    }
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "verification failed"):
            authenticate_evaluation_conformance(
                tampered,
                self.policy,
                self.batch,
                self.artifact,
                self.authorization,
                self.audit_directory,
                self.ledger,
                self.now,
            )

    def test_failure_artifact_and_unsafe_contract_flags_are_rejected(self) -> None:
        failed = BrokeredEvaluationArtifact(
            authorization=self.artifact.authorization,
            authorization_sha256=self.artifact.authorization_sha256,
            outcome_sha256="8" * 64,
            status="error",
            outcome_status="failed",
            ledger_status="uncertain",
            latency_ms=12,
            cost_microusd=300,
            error="provider_error",
        )
        with self.assertRaisesRegex(ValueError, "completed artifact"):
            make_evaluation_conformance_observation(
                self.batch,
                failed,
                self.authorization,
                self.audit_directory,
                self.ledger,
                self.policy,
                self.now,
                "2.54.0",
                "7" * 64,
            )
        signed = sign_evaluation_conformance_observation(
            self.observation(), "observer-a", self.private_key.private_bytes_raw()
        )
        authenticated = authenticate_evaluation_conformance(
            signed,
            self.policy,
            self.batch,
            self.artifact,
            self.authorization,
            self.audit_directory,
            self.ledger,
            self.now,
        )
        with self.assertRaises(ValidationError):
            AuthenticatedEvaluationConformance.model_validate(
                authenticated.model_dump()
                | {"batch_conversion_authorized": True, "grading_authorized": True}
            )

    def test_policy_rejects_noncanonical_observer_and_sdk_sets(self) -> None:
        other = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        policy = self.policy.model_dump()
        policy["observers"] = (
            trusted_evaluation_conformance_observer("z", other),
            self.policy.observers[0],
        )
        with self.assertRaises(ValidationError):
            EvaluationConformancePolicy.model_validate(policy)
        with self.assertRaises(ValidationError):
            EvaluationConformancePolicy.model_validate(
                self.policy.model_dump() | {"allowed_sdk_versions": ("z", "a")}
            )

    def test_cli_derives_and_authenticates_without_accepting_private_keys(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            batch_path = root / "batch.json"
            artifact_path = root / "artifact.json"
            policy_path = root / "policy.json"
            authorization_path = root / "expected-authorization.json"
            observation_path = root / "observation.json"
            signed_path = root / "signed.json"
            authenticated_path = root / "authenticated.json"
            private_write(batch_path, canonical_bytes(self.batch))
            private_write(artifact_path, canonical_bytes(self.artifact))
            private_write(policy_path, canonical_bytes(self.policy))
            private_write(authorization_path, canonical_bytes(self.authorization))
            derive = [
                "eval-derive-brokered-conformance",
                "--batch",
                str(batch_path),
                "--artifact",
                str(artifact_path),
                "--expected-authorization",
                str(authorization_path),
                "--audit-dir",
                str(self.audit_directory),
                "--spend-ledger",
                str(self.ledger.path),
                "--conformance-policy",
                str(policy_path),
                "--observed-at",
                self.now.isoformat(),
                "--sdk-version",
                "2.54.0",
                "--transport-evidence-sha256",
                "7" * 64,
                "--attest-credentialed-exchange",
                "--output",
                str(observation_path),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(derive), 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(
                event["type"], "evaluation.brokered_conformance.observation_derived"
            )
            self.assertFalse(event["batch_conversion_authorized"])
            self.assertNotIn("resp_probe_1", stdout.getvalue())
            observation = EvaluationConformanceObservation.model_validate_json(
                observation_path.read_bytes()
            )
            signed = sign_evaluation_conformance_observation(
                observation, "observer-a", self.private_key.private_bytes_raw()
            )
            private_write(signed_path, canonical_bytes(signed))
            authenticate = [
                "eval-authenticate-brokered-conformance",
                "--signed-observation",
                str(signed_path),
                "--conformance-policy",
                str(policy_path),
                "--batch",
                str(batch_path),
                "--artifact",
                str(artifact_path),
                "--expected-authorization",
                str(authorization_path),
                "--audit-dir",
                str(self.audit_directory),
                "--spend-ledger",
                str(self.ledger.path),
                "--at",
                (self.now + timedelta(seconds=30)).isoformat(),
                "--output",
                str(authenticated_path),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(authenticate), 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(
                event["type"], "evaluation.brokered_conformance.authenticated"
            )
            self.assertFalse(event["grading_authorized"])
            authenticated = AuthenticatedEvaluationConformance.model_validate_json(
                authenticated_path.read_bytes()
            )
            self.assertEqual(event["signer_id"], authenticated.signer_id)

    def test_cli_requires_attestation_before_reads_and_rejects_input_overwrite(
        self,
    ) -> None:
        options = [
            "eval-derive-brokered-conformance",
            "--batch",
            "missing-batch",
            "--artifact",
            "missing-artifact",
            "--expected-authorization",
            "missing-authorization",
            "--audit-dir",
            "missing-audit",
            "--spend-ledger",
            "missing-ledger",
            "--conformance-policy",
            "missing-policy",
            "--observed-at",
            self.now.isoformat(),
            "--sdk-version",
            "2.54.0",
            "--transport-evidence-sha256",
            "7" * 64,
            "--output",
            "output.json",
        ]
        with (
            patch("mos_eisley.cli.read_bounded") as read,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(options), 2)
            read.assert_not_called()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            batch_path = root / "batch.json"
            artifact_path = root / "artifact.json"
            policy_path = root / "policy.json"
            authorization_path = root / "expected-authorization.json"
            private_write(batch_path, canonical_bytes(self.batch))
            private_write(artifact_path, canonical_bytes(self.artifact))
            private_write(policy_path, canonical_bytes(self.policy))
            private_write(authorization_path, canonical_bytes(self.authorization))
            overwrite = options.copy()
            for option, value in (
                ("--batch", batch_path),
                ("--artifact", artifact_path),
                ("--expected-authorization", authorization_path),
                ("--audit-dir", self.audit_directory),
                ("--spend-ledger", self.ledger.path),
                ("--conformance-policy", policy_path),
                ("--output", artifact_path),
            ):
                overwrite[overwrite.index(option) + 1] = str(value)
            overwrite.insert(
                overwrite.index("--output"), "--attest-credentialed-exchange"
            )
            original = artifact_path.read_bytes()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(overwrite), 2)
            self.assertEqual(artifact_path.read_bytes(), original)

            audit_anchor = overwrite.copy()
            audit_anchor[audit_anchor.index("--expected-authorization") + 1] = str(
                self.audit_directory / "authorization.json"
            )
            rejected = root / "audit-anchor-rejected.json"
            audit_anchor[audit_anchor.index("--output") + 1] = str(rejected)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(audit_anchor), 2)
            self.assertFalse(rejected.exists())
