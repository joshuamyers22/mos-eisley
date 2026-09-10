"""Runtime conformance attestations bind one exact verified publication."""

import base64
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.skill_runtime_conformance import (
    AuthenticatedSkillRuntimeConformance,
    SignedSkillRuntimeConformanceObservation,
    SkillRuntimeConformanceObservation,
    SkillRuntimeConformancePolicy,
    authenticate_skill_runtime_conformance,
    make_skill_runtime_conformance_observation,
    sign_skill_runtime_conformance_observation,
    trusted_skill_runtime_conformance_observer,
)
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_response as response_module


class SkillRuntimeConformanceTests(TestCase):
    def setUp(self) -> None:
        self.response_fixture = response_module.SkillRuntimeResponsePublicationTests()
        self.response_fixture.setUp()
        self.addCleanup(self.response_fixture.doCleanups)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        _, _, self.publication, self.result = self.response_fixture.publish()
        self.observed_at = self.response_fixture.publish_at + timedelta(seconds=1)
        self.authenticate_at = self.observed_at + timedelta(seconds=1)
        self.private_key = bytes(range(32))
        public_key = (
            Ed25519PrivateKey.from_private_bytes(self.private_key)
            .public_key()
            .public_bytes_raw()
        )
        self.policy = SkillRuntimeConformancePolicy(
            policy_id="openai-runtime-conformance",
            response_store_policy_sha256=(
                self.response_fixture.store.policy.policy_sha256
            ),
            valid_from=self.observed_at - timedelta(minutes=1),
            valid_until=self.observed_at + timedelta(hours=1),
            max_observation_age_seconds=60,
            observers=(
                trusted_skill_runtime_conformance_observer(
                    "runtime-observer", public_key
                ),
            ),
            allowed_sdk_versions=("2.54.0",),
        )
        self.observation = make_skill_runtime_conformance_observation(
            self.publication,
            self.result,
            self.policy,
            self.observed_at,
            "2.54.0",
            digest(b"redacted transport evidence"),
        )
        self.signed = sign_skill_runtime_conformance_observation(
            self.observation, "runtime-observer", self.private_key
        )

    def authenticate(
        self,
        signed: SignedSkillRuntimeConformanceObservation | None = None,
        *,
        policy: SkillRuntimeConformancePolicy | None = None,
        now: datetime | None = None,
    ) -> AuthenticatedSkillRuntimeConformance:
        return authenticate_skill_runtime_conformance(
            signed or self.signed,
            policy or self.policy,
            self.response_fixture.store,
            now or self.authenticate_at,
        )

    def test_authenticates_exact_publication_without_broadening_claims(self) -> None:
        authenticated = self.authenticate()

        self.assertEqual(authenticated.publication_id, self.publication.publication_id)
        self.assertEqual(
            authenticated.publication_sha256,
            self.publication.publication_sha256,
        )
        self.assertEqual(authenticated.result_sha256, self.result.result_sha256)
        self.assertEqual(authenticated.signer_id, "runtime-observer")
        self.assertTrue(authenticated.credentialed_exchange_attested)
        self.assertTrue(authenticated.local_publication_reverified)
        self.assertFalse(authenticated.provider_authorship_proven)
        self.assertFalse(authenticated.billing_reconciled)
        self.assertFalse(authenticated.quality_claimed)
        self.assertFalse(authenticated.promotion_authorized)
        self.assertFalse(authenticated.routing_activation_authorized)
        self.assertNotIn(b"Published answer", canonical_bytes(authenticated))
        self.assertNotIn(b"private-encrypted-reasoning", canonical_bytes(authenticated))

    def test_publication_substitution_is_rejected_after_valid_signature(self) -> None:
        changed = self.observation.model_copy(update={"publication_id": "f" * 64})
        signed = sign_skill_runtime_conformance_observation(
            changed, "runtime-observer", self.private_key
        )
        with self.assertRaisesRegex(ValueError, "publication is absent"):
            self.authenticate(signed)

    def test_observation_tampering_breaks_signature(self) -> None:
        changed = self.signed.model_copy(
            update={
                "observation": self.observation.model_copy(
                    update={"sdk_version": "9.9.9"}
                )
            }
        )
        with self.assertRaises(ValidationError):
            self.authenticate(changed)

    def test_cryptographic_signature_substitution_is_rejected(self) -> None:
        changed_signature = self.signed.signature.model_copy(
            update={"signature_base64": base64.b64encode(bytes(64)).decode("ascii")}
        )
        changed = self.signed.model_copy(update={"signature": changed_signature})
        with self.assertRaisesRegex(ValueError, "signature verification failed"):
            self.authenticate(changed)

    def test_stale_observation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match policy"):
            self.authenticate(now=self.observed_at + timedelta(seconds=61))

    def test_policy_substitution_is_rejected(self) -> None:
        changed = self.policy.model_copy(update={"policy_id": "substituted-policy"})
        with self.assertRaisesRegex(ValueError, "does not match policy"):
            self.authenticate(policy=changed)

    def test_unapproved_sdk_version_is_rejected_before_signing(self) -> None:
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            make_skill_runtime_conformance_observation(
                self.publication,
                self.result,
                self.policy,
                self.observed_at,
                "9.9.9",
                self.observation.transport_evidence_sha256,
            )

    def test_literal_non_authority_claims_cannot_be_escalated(self) -> None:
        payload = self.observation.model_dump(mode="json")
        for field in (
            "provider_authorship_proven",
            "billing_reconciled",
            "quality_claimed",
            "promotion_authorized",
            "routing_activation_authorized",
        ):
            changed = {**payload, field: True}
            with self.subTest(field=field), self.assertRaises(ValidationError):
                SkillRuntimeConformanceObservation.model_validate(changed)

    def test_authenticated_receipt_index_tampering_is_rejected(self) -> None:
        payload = self.authenticate().model_dump(mode="json")
        payload["publication_id"] = "f" * 64
        with self.assertRaisesRegex(ValidationError, "does not match observation"):
            AuthenticatedSkillRuntimeConformance.model_validate_json(
                json.dumps(payload)
            )

    def test_cli_derives_and_authenticates_without_keys_or_response_content(
        self,
    ) -> None:
        policy_path = self.root / "conformance-policy.json"
        observation_path = self.root / "conformance-observation.json"
        signed_path = self.root / "signed-conformance-observation.json"
        authenticated_path = self.root / "authenticated-conformance.json"
        private_write(policy_path, canonical_bytes(self.policy))

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "eval-derive-skill-runtime-conformance",
                        "--response-store",
                        str(self.response_fixture.store.path),
                        "--publication-id",
                        self.publication.publication_id,
                        "--conformance-policy",
                        str(policy_path),
                        "--observed-at",
                        self.observed_at.isoformat(),
                        "--sdk-version",
                        "2.54.0",
                        "--transport-evidence-sha256",
                        self.observation.transport_evidence_sha256,
                        "--attest-credentialed-exchange",
                        "--output",
                        str(observation_path),
                    ]
                ),
                0,
            )
        derived_event = json.loads(stdout.getvalue())
        self.assertEqual(
            derived_event["type"],
            "evaluation.skill_runtime.conformance_observation_derived",
        )
        derived = SkillRuntimeConformanceObservation.model_validate_json(
            observation_path.read_bytes()
        )
        self.assertEqual(derived, self.observation)
        signed = sign_skill_runtime_conformance_observation(
            derived, "runtime-observer", self.private_key
        )
        private_write(signed_path, canonical_bytes(signed))

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "eval-authenticate-skill-runtime-conformance",
                        "--signed-observation",
                        str(signed_path),
                        "--conformance-policy",
                        str(policy_path),
                        "--response-store",
                        str(self.response_fixture.store.path),
                        "--at",
                        self.authenticate_at.isoformat(),
                        "--output",
                        str(authenticated_path),
                    ]
                ),
                0,
            )
        output = stdout.getvalue()
        event = json.loads(output)
        self.assertEqual(
            event["type"], "evaluation.skill_runtime.conformance_authenticated"
        )
        authenticated = AuthenticatedSkillRuntimeConformance.model_validate_json(
            authenticated_path.read_bytes()
        )
        self.assertEqual(authenticated.publication_id, self.publication.publication_id)
        self.assertNotIn("Published answer", output)
        self.assertNotIn("private-encrypted-reasoning", output)
        self.assertNotIn(base64.b64encode(self.private_key).decode("ascii"), output)

    def test_cli_requires_explicit_credentialed_exchange_attestation(self) -> None:
        policy_path = self.root / "conformance-policy.json"
        output = self.root / "should-not-exist.json"
        private_write(policy_path, canonical_bytes(self.policy))
        with redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(
                main(
                    [
                        "eval-derive-skill-runtime-conformance",
                        "--response-store",
                        str(self.response_fixture.store.path),
                        "--publication-id",
                        self.publication.publication_id,
                        "--conformance-policy",
                        str(policy_path),
                        "--observed-at",
                        self.observed_at.isoformat(),
                        "--sdk-version",
                        "2.54.0",
                        "--transport-evidence-sha256",
                        self.observation.transport_evidence_sha256,
                        "--output",
                        str(output),
                    ]
                ),
                2,
            )
        self.assertIn("input or artifact validation failed", stderr.getvalue())
        self.assertFalse(output.exists())
