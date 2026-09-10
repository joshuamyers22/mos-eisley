"""Aggregate billing evidence remains narrow, authenticated, and non-authorizing."""

import base64
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.skill_runtime_billing import (
    AuthenticatedSkillRuntimeBillingEvidence,
    SignedSkillRuntimeBillingObservation,
    SkillRuntimeBillingObservation,
    SkillRuntimeBillingPolicy,
    authenticate_skill_runtime_billing_evidence,
    make_skill_runtime_billing_observation,
    sign_skill_runtime_billing_observation,
    trusted_skill_runtime_billing_auditor,
)
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_conformance as conformance_module


class SkillRuntimeBillingTests(TestCase):
    def setUp(self) -> None:
        self.conformance_fixture = conformance_module.SkillRuntimeConformanceTests()
        self.conformance_fixture.setUp()
        self.addCleanup(self.conformance_fixture.doCleanups)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.conformance = self.conformance_fixture.authenticate()
        self.publication = self.conformance_fixture.publication
        self.result = self.conformance_fixture.result
        published_at = self.publication.committed_at
        self.usage_start = published_at.replace(second=0, microsecond=0)
        self.usage_end = self.usage_start + timedelta(minutes=1)
        self.costs_start = datetime(
            published_at.year,
            published_at.month,
            published_at.day,
            tzinfo=UTC,
        )
        self.costs_end = self.costs_start + timedelta(days=1)
        self.retrieved_at = self.costs_end + timedelta(minutes=1)
        self.authenticate_at = self.retrieved_at + timedelta(seconds=1)
        self.private_key = bytes(range(32, 64))
        public_key = (
            Ed25519PrivateKey.from_private_bytes(self.private_key)
            .public_key()
            .public_bytes_raw()
        )
        self.policy = SkillRuntimeBillingPolicy(
            policy_id="openai-runtime-billing",
            response_store_policy_sha256=(
                self.conformance_fixture.response_fixture.store.policy.policy_sha256
            ),
            conformance_policy_sha256=self.conformance_fixture.policy.policy_sha256,
            valid_from=self.retrieved_at - timedelta(hours=1),
            valid_until=self.retrieved_at + timedelta(hours=1),
            max_evidence_age_seconds=60,
            auditors=(
                trusted_skill_runtime_billing_auditor("billing-auditor", public_key),
            ),
        )
        self.observation = self.make_observation()
        self.signed = sign_skill_runtime_billing_observation(
            self.observation, "billing-auditor", self.private_key
        )

    @property
    def response_store(self):
        return self.conformance_fixture.response_fixture.store

    def make_observation(self, **changes: object) -> SkillRuntimeBillingObservation:
        arguments: dict[str, object] = {
            "external_input_tokens": self.result.usage.input,
            "external_output_tokens": self.result.usage.output,
            "external_cost_microusd": self.result.charged_microusd,
            "usage_bucket_start": self.usage_start,
            "usage_bucket_end": self.usage_end,
            "costs_bucket_start": self.costs_start,
            "costs_bucket_end": self.costs_end,
            "project_id_sha256": digest(b"project-id"),
            "api_key_id_sha256": digest(b"api-key-id"),
            "usage_evidence_sha256": digest(b"complete usage pages"),
            "costs_evidence_sha256": digest(b"complete costs pages"),
            "evidence_retrieved_at": self.retrieved_at,
        }
        arguments.update(changes)
        return make_skill_runtime_billing_observation(
            self.conformance,
            self.conformance_fixture.policy,
            self.response_store,
            self.policy,
            **arguments,  # type: ignore[arg-type]
        )

    def authenticate(
        self,
        signed: SignedSkillRuntimeBillingObservation | None = None,
        *,
        policy: SkillRuntimeBillingPolicy | None = None,
        now: datetime | None = None,
    ) -> AuthenticatedSkillRuntimeBillingEvidence:
        return authenticate_skill_runtime_billing_evidence(
            signed or self.signed,
            policy or self.policy,
            self.conformance,
            self.conformance_fixture.policy,
            self.response_store,
            now or self.authenticate_at,
        )

    def test_authenticates_matching_aggregate_without_broadening_claims(self) -> None:
        authenticated = self.authenticate()

        self.assertEqual(authenticated.publication_id, self.publication.publication_id)
        self.assertEqual(authenticated.signer_id, "billing-auditor")
        self.assertTrue(authenticated.conformance_reauthenticated)
        self.assertTrue(authenticated.local_publication_reverified)
        self.assertTrue(authenticated.billing_evidence_authenticated)
        self.assertTrue(authenticated.exclusive_aggregate_billing_reconciled)
        self.assertFalse(authenticated.exact_request_cost_attribution_proven)
        self.assertFalse(authenticated.provider_authorship_proven)
        self.assertFalse(authenticated.invoice_finality_proven)
        self.assertFalse(authenticated.ledger_mutation_authorized)
        self.assertFalse(authenticated.automatic_budget_release_authorized)
        self.assertFalse(authenticated.provider_retry_authorized)
        self.assertFalse(authenticated.quality_claimed)
        self.assertFalse(authenticated.promotion_authorized)
        self.assertFalse(authenticated.routing_activation_authorized)
        payload = canonical_bytes(authenticated)
        self.assertNotIn(b"Published answer", payload)
        self.assertNotIn(b"private-encrypted-reasoning", payload)

    def test_token_or_cost_mismatch_is_rejected_before_signing(self) -> None:
        for field, value in (
            ("external_input_tokens", self.result.usage.input + 1),
            ("external_output_tokens", self.result.usage.output + 1),
            ("external_cost_microusd", self.result.charged_microusd + 1),
        ):
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValidationError, "does not exactly match"),
            ):
                self.make_observation(**{field: value})

    def test_incomplete_or_nonexclusive_claim_cannot_be_encoded(self) -> None:
        payload = self.observation.model_dump(mode="json")
        for field in (
            "official_admin_api_evidence_attested",
            "complete_pagination_attested",
            "exclusive_one_request_scope_attested",
            "usage_aggregate_matches_local",
            "cost_aggregate_matches_local",
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                SkillRuntimeBillingObservation.model_validate({**payload, field: False})

    def test_bucket_width_and_completed_day_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValidationError, "exactly one minute"):
            self.make_observation(
                usage_bucket_end=self.usage_end + timedelta(seconds=1)
            )
        with self.assertRaisesRegex(ValidationError, "predates a completed bucket"):
            self.make_observation(
                evidence_retrieved_at=self.costs_end - timedelta(seconds=1)
            )
        with self.assertRaisesRegex(ValidationError, "align to a UTC minute"):
            self.make_observation(
                usage_bucket_start=self.usage_start + timedelta(seconds=1),
                usage_bucket_end=self.usage_end + timedelta(seconds=1),
            )
        with self.assertRaisesRegex(ValidationError, "align to a UTC day"):
            self.make_observation(
                costs_bucket_start=self.costs_start + timedelta(hours=1),
                costs_bucket_end=self.costs_end + timedelta(hours=1),
                evidence_retrieved_at=self.costs_end + timedelta(hours=2),
            )

    def test_valid_signature_over_substituted_publication_is_rejected(self) -> None:
        changed = self.observation.model_copy(
            update={"provider_request_id": "substitute"}
        )
        signed = sign_skill_runtime_billing_observation(
            changed, "billing-auditor", self.private_key
        )
        with self.assertRaisesRegex(ValueError, "publication provenance mismatch"):
            self.authenticate(signed)

    def test_cryptographic_signature_substitution_is_rejected(self) -> None:
        changed_signature = self.signed.signature.model_copy(
            update={"signature_base64": base64.b64encode(bytes(64)).decode("ascii")}
        )
        changed = self.signed.model_copy(update={"signature": changed_signature})
        with self.assertRaisesRegex(ValueError, "signature verification failed"):
            self.authenticate(changed)

    def test_stale_evidence_and_policy_substitution_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match policy"):
            self.authenticate(now=self.retrieved_at + timedelta(seconds=61))
        changed = self.policy.model_copy(update={"policy_id": "substituted-policy"})
        with self.assertRaisesRegex(ValueError, "does not match policy"):
            self.authenticate(policy=changed)

    def test_billing_auditor_must_be_independent_from_conformance(self) -> None:
        conformance_public_key = (
            Ed25519PrivateKey.from_private_bytes(self.conformance_fixture.private_key)
            .public_key()
            .public_bytes_raw()
        )
        changed_policy = self.policy.model_copy(
            update={
                "auditors": (
                    trusted_skill_runtime_billing_auditor(
                        "billing-auditor", conformance_public_key
                    ),
                )
            }
        )
        changed_observation = self.observation.model_copy(
            update={"billing_policy_sha256": changed_policy.policy_sha256}
        )
        signed = sign_skill_runtime_billing_observation(
            changed_observation,
            "billing-auditor",
            self.conformance_fixture.private_key,
        )
        with self.assertRaisesRegex(ValueError, "must be independent"):
            self.authenticate(signed, policy=changed_policy)

    def test_authenticated_receipt_index_tampering_is_rejected(self) -> None:
        payload = self.authenticate().model_dump(mode="json")
        payload["publication_id"] = "f" * 64
        with self.assertRaisesRegex(ValidationError, "does not match source"):
            AuthenticatedSkillRuntimeBillingEvidence.model_validate_json(
                json.dumps(payload)
            )

    def paths(self) -> dict[str, Path]:
        paths = {
            "conformance": self.root / "authenticated-conformance.json",
            "conformance_policy": self.root / "conformance-policy.json",
            "billing_policy": self.root / "billing-policy.json",
            "observation": self.root / "billing-observation.json",
            "signed": self.root / "signed-billing-observation.json",
            "authenticated": self.root / "authenticated-billing.json",
        }
        private_write(paths["conformance"], canonical_bytes(self.conformance))
        private_write(
            paths["conformance_policy"],
            canonical_bytes(self.conformance_fixture.policy),
        )
        private_write(paths["billing_policy"], canonical_bytes(self.policy))
        return paths

    def derive_cli_args(self, paths: dict[str, Path]) -> list[str]:
        return [
            "eval-derive-skill-runtime-billing-evidence",
            "--authenticated-conformance",
            str(paths["conformance"]),
            "--conformance-policy",
            str(paths["conformance_policy"]),
            "--response-store",
            str(self.response_store.path),
            "--billing-policy",
            str(paths["billing_policy"]),
            "--external-input-tokens",
            str(self.result.usage.input),
            "--external-output-tokens",
            str(self.result.usage.output),
            "--external-cost-microusd",
            str(self.result.charged_microusd),
            "--usage-bucket-start",
            self.usage_start.isoformat(),
            "--usage-bucket-end",
            self.usage_end.isoformat(),
            "--costs-bucket-start",
            self.costs_start.isoformat(),
            "--costs-bucket-end",
            self.costs_end.isoformat(),
            "--project-id-sha256",
            self.observation.project_id_sha256,
            "--api-key-id-sha256",
            self.observation.api_key_id_sha256,
            "--usage-evidence-sha256",
            self.observation.usage_evidence_sha256,
            "--costs-evidence-sha256",
            self.observation.costs_evidence_sha256,
            "--evidence-retrieved-at",
            self.retrieved_at.isoformat(),
            "--output",
            str(paths["observation"]),
        ]

    def test_cli_derives_and_authenticates_without_secrets_or_content(self) -> None:
        paths = self.paths()
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        *self.derive_cli_args(paths),
                        "--attest-complete-exclusive-billing-evidence",
                    ]
                ),
                0,
            )
        derived_event = json.loads(stdout.getvalue())
        self.assertEqual(
            derived_event["type"],
            "evaluation.skill_runtime.billing_observation_derived",
        )
        derived = SkillRuntimeBillingObservation.model_validate_json(
            paths["observation"].read_bytes()
        )
        signed = sign_skill_runtime_billing_observation(
            derived, "billing-auditor", self.private_key
        )
        private_write(paths["signed"], canonical_bytes(signed))

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "eval-authenticate-skill-runtime-billing-evidence",
                        "--signed-observation",
                        str(paths["signed"]),
                        "--billing-policy",
                        str(paths["billing_policy"]),
                        "--authenticated-conformance",
                        str(paths["conformance"]),
                        "--conformance-policy",
                        str(paths["conformance_policy"]),
                        "--response-store",
                        str(self.response_store.path),
                        "--at",
                        self.authenticate_at.isoformat(),
                        "--output",
                        str(paths["authenticated"]),
                    ]
                ),
                0,
            )
        output = stdout.getvalue()
        event = json.loads(output)
        self.assertEqual(
            event["type"],
            "evaluation.skill_runtime.billing_evidence_authenticated",
        )
        authenticated = AuthenticatedSkillRuntimeBillingEvidence.model_validate_json(
            paths["authenticated"].read_bytes()
        )
        self.assertEqual(authenticated.publication_id, self.publication.publication_id)
        for secret in (
            "Published answer",
            "private-encrypted-reasoning",
            base64.b64encode(self.private_key).decode("ascii"),
        ):
            self.assertNotIn(secret, output)

    def test_cli_requires_explicit_complete_exclusive_attestation(self) -> None:
        paths = self.paths()
        with redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(main(self.derive_cli_args(paths)), 2)
        self.assertIn("input or artifact validation failed", stderr.getvalue())
        self.assertFalse(paths["observation"].exists())
