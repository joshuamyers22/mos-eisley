"""Signed runtime-publication checkpoints detect rollback or divergent history."""

import base64
import io
import json
import sqlite3
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.skill_runtime_response import (
    SkillRuntimeResponseStore,
    publish_skill_runtime_response,
)
from mos_eisley.run.skill_runtime_witness import (
    SignedSkillRuntimePublicationCheckpoint,
    SkillRuntimePublicationWitnessPolicy,
    VerifiedSkillRuntimePublicationCheckpoint,
    make_skill_runtime_publication_checkpoint,
    sign_skill_runtime_publication_checkpoint,
    trusted_skill_runtime_publication_witness,
    verify_skill_runtime_publication_checkpoint,
)
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_response as response_module


class SkillRuntimePublicationWitnessTests(TestCase):
    def setUp(self) -> None:
        self.response_fixture = response_module.SkillRuntimeResponsePublicationTests()
        self.response_fixture.setUp()
        self.addCleanup(self.response_fixture.doCleanups)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.response_fixture.publish()
        self.witnessed_at = self.response_fixture.publish_at + timedelta(seconds=1)
        self.verified_at = self.witnessed_at + timedelta(seconds=1)
        self.private_key = bytes(reversed(range(32)))
        public_key = (
            Ed25519PrivateKey.from_private_bytes(self.private_key)
            .public_key()
            .public_bytes_raw()
        )
        self.policy = SkillRuntimePublicationWitnessPolicy(
            policy_id="runtime-publication-witness",
            response_store_policy_sha256=(
                self.response_fixture.store.policy.policy_sha256
            ),
            valid_from=self.witnessed_at - timedelta(minutes=1),
            valid_until=self.witnessed_at + timedelta(hours=1),
            max_checkpoint_age_seconds=60,
            witnesses=(
                trusted_skill_runtime_publication_witness(
                    "publication-witness", public_key
                ),
            ),
        )
        self.checkpoint = make_skill_runtime_publication_checkpoint(
            self.response_fixture.store,
            self.policy,
            self.witnessed_at,
        )
        self.signed = sign_skill_runtime_publication_checkpoint(
            self.checkpoint,
            "publication-witness",
            self.private_key,
        )

    def verify(
        self,
        signed: SignedSkillRuntimePublicationCheckpoint | None = None,
        *,
        policy: SkillRuntimePublicationWitnessPolicy | None = None,
        now: datetime | None = None,
    ) -> VerifiedSkillRuntimePublicationCheckpoint:
        return verify_skill_runtime_publication_checkpoint(
            signed or self.signed,
            policy or self.policy,
            self.response_fixture.store,
            now or self.verified_at,
        )

    def test_verifies_exact_hash_only_history_prefix(self) -> None:
        verified = self.verify()

        self.assertEqual(self.checkpoint.history.publications, 1)
        self.assertEqual(verified.current_history, self.checkpoint.history)
        self.assertTrue(verified.checkpoint_is_verified_prefix)
        self.assertFalse(verified.rollback_or_divergence_observed)
        self.assertFalse(verified.external_retention_proven)
        self.assertFalse(verified.latest_external_checkpoint_proven)
        self.assertFalse(verified.provider_retry_authorized)
        self.assertFalse(verified.budget_release_authorized)
        self.assertNotIn(b"Published answer", canonical_bytes(verified))
        self.assertNotIn(b"private-encrypted-reasoning", canonical_bytes(verified))

    def test_validly_signed_divergent_history_is_rejected(self) -> None:
        changed_history = self.checkpoint.history.model_copy(
            update={"history_sha256": "f" * 64}
        )
        changed = self.checkpoint.model_copy(update={"history": changed_history})
        signed = sign_skill_runtime_publication_checkpoint(
            changed,
            "publication-witness",
            self.private_key,
        )
        with self.assertRaisesRegex(ValueError, "checkpoint does not match"):
            self.verify(signed)

    def test_sequence_gap_is_rejected_before_history_is_computed(self) -> None:
        with sqlite3.connect(self.response_fixture.store.path) as connection:
            connection.execute("UPDATE publications SET sequence = 2")
            connection.commit()
        with self.assertRaisesRegex(ValueError, "record is invalid"):
            self.response_fixture.store.history()

    def test_checkpoint_remains_valid_prefix_after_later_publication(self) -> None:
        later = response_module.SkillRuntimeResponsePublicationTests()
        later.setUp()
        self.addCleanup(later.doCleanups)
        capability, reply = later.execute(
            later.response(response_id="resp_skill_runtime_2")
        )
        publish_skill_runtime_response(
            later.provider.grant.dispatch.admission_fixture.prepared,
            capability.issuance,
            reply,
            later.provider.grant.store,
            later.provider.store,
            later.provider.runtime.ledger,
            self.response_fixture.store,
            later.publish_at,
        )

        verified = self.verify()
        self.assertEqual(verified.signed_checkpoint.checkpoint.history.publications, 1)
        self.assertEqual(verified.current_history.publications, 2)
        self.assertTrue(verified.checkpoint_is_verified_prefix)

    def test_signature_substitution_is_rejected(self) -> None:
        changed_signature = self.signed.signature.model_copy(
            update={"signature_base64": base64.b64encode(bytes(64)).decode("ascii")}
        )
        changed = self.signed.model_copy(update={"signature": changed_signature})
        with self.assertRaisesRegex(ValueError, "signature verification failed"):
            self.verify(changed)

    def test_stale_checkpoint_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match witness policy"):
            self.verify(now=self.witnessed_at + timedelta(seconds=61))

    def test_policy_substitution_is_rejected(self) -> None:
        changed = self.policy.model_copy(update={"policy_id": "different-policy"})
        with self.assertRaisesRegex(ValueError, "does not match witness policy"):
            self.verify(policy=changed)

    def test_empty_store_cannot_satisfy_minimum_publications(self) -> None:
        empty = SkillRuntimeResponseStore.create(
            self.root / "empty-responses.sqlite",
            self.response_fixture.provider.grant.dispatch.response_policy,
            self.response_fixture.provider.store,
        )
        with self.assertRaisesRegex(ValueError, "does not match witness policy"):
            make_skill_runtime_publication_checkpoint(
                empty,
                self.policy,
                self.witnessed_at,
            )

    def test_verified_receipt_index_tampering_is_rejected(self) -> None:
        payload = self.verify().model_dump(mode="json")
        payload["signer_id"] = "substituted-witness"
        with self.assertRaisesRegex(ValidationError, "is inconsistent"):
            VerifiedSkillRuntimePublicationCheckpoint.model_validate_json(
                json.dumps(payload)
            )

    def test_cli_derives_and_verifies_without_private_content_or_key(self) -> None:
        policy_path = self.root / "witness-policy.json"
        checkpoint_path = self.root / "publication-checkpoint.json"
        signed_path = self.root / "signed-publication-checkpoint.json"
        verified_path = self.root / "verified-publication-checkpoint.json"
        private_write(policy_path, canonical_bytes(self.policy))

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "eval-derive-skill-runtime-publication-checkpoint",
                        "--response-store",
                        str(self.response_fixture.store.path),
                        "--witness-policy",
                        str(policy_path),
                        "--witnessed-at",
                        self.witnessed_at.isoformat(),
                        "--output",
                        str(checkpoint_path),
                    ]
                ),
                0,
            )
        derived_event = json.loads(stdout.getvalue())
        self.assertEqual(
            derived_event["type"],
            "evaluation.skill_runtime.publication_checkpoint_derived",
        )
        self.assertFalse(derived_event["external_retention_proven"])
        derived = self.checkpoint.model_validate_json(checkpoint_path.read_bytes())
        self.assertEqual(derived, self.checkpoint)
        signed = sign_skill_runtime_publication_checkpoint(
            derived,
            "publication-witness",
            self.private_key,
        )
        private_write(signed_path, canonical_bytes(signed))

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "eval-verify-skill-runtime-publication-checkpoint",
                        "--signed-checkpoint",
                        str(signed_path),
                        "--witness-policy",
                        str(policy_path),
                        "--response-store",
                        str(self.response_fixture.store.path),
                        "--at",
                        self.verified_at.isoformat(),
                        "--output",
                        str(verified_path),
                    ]
                ),
                0,
            )
        output = stdout.getvalue()
        event = json.loads(output)
        self.assertEqual(
            event["type"],
            "evaluation.skill_runtime.publication_checkpoint_verified",
        )
        self.assertFalse(event["rollback_or_divergence_observed"])
        verified = VerifiedSkillRuntimePublicationCheckpoint.model_validate_json(
            verified_path.read_bytes()
        )
        self.assertEqual(verified.current_history, self.checkpoint.history)
        self.assertNotIn("Published answer", output)
        self.assertNotIn("private-encrypted-reasoning", output)
        self.assertNotIn(base64.b64encode(self.private_key).decode("ascii"), output)
