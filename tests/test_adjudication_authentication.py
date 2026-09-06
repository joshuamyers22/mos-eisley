"""Human grading identity is cryptographically bound to exact adjudication."""

import base64
import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.evaluation.authentication import (
    AdjudicationSignature,
    AuthenticatedAdjudication,
    GradingTrustPolicy,
    SignedAdjudication,
    authenticate_adjudication,
    sign_adjudication,
    trusted_adjudicator,
    verify_authenticated_adjudication,
)
from mos_eisley.run.store import private_write
from tests.test_adjudication_agreement import packet, ratings, replace_decision


class AdjudicationAuthenticationTests(TestCase):
    def setUp(self) -> None:
        self.batch = packet()
        self.adjudication = ratings(self.batch, "grader-a")
        self.left = Ed25519PrivateKey.generate()
        self.right = Ed25519PrivateKey.generate()
        self.policy = GradingTrustPolicy(
            policy_id="human-grading-v1",
            rubric_sha256=self.adjudication.adjudicator.rubric_sha256,
            adjudicators=(
                trusted_adjudicator(
                    "grader-a", self.left.public_key().public_bytes_raw()
                ),
                trusted_adjudicator(
                    "grader-b", self.right.public_key().public_bytes_raw()
                ),
            ),
        )

    def signed(self) -> SignedAdjudication:
        return sign_adjudication(
            self.adjudication, "grader-a", self.left.private_bytes_raw()
        )

    def test_exact_human_adjudication_authenticates_and_reverifies(self) -> None:
        signed = self.signed()
        authenticated = authenticate_adjudication(self.batch, signed, self.policy)
        self.assertEqual(
            authenticated.grading_batch_sha256, self.batch.grading_batch_sha256
        )
        self.assertEqual(authenticated.trust_policy_sha256, self.policy.policy_sha256)
        self.assertEqual(
            authenticated.signed_adjudication.signature.public_key_sha256,
            self.policy.adjudicators[0].public_key_sha256,
        )
        self.assertEqual(len(authenticated.authenticated_adjudication_sha256), 64)
        verify_authenticated_adjudication(self.batch, authenticated, self.policy)

    def test_changed_content_identity_key_or_domain_is_rejected(self) -> None:
        signed = self.signed()
        first = self.adjudication.judgments[0].findings[0]
        changed_adjudication = replace_decision(
            self.adjudication,
            first.model_copy(update={"rationale": "Changed after signing."}),
        )
        changed_content = signed.model_copy(
            update={"adjudication": changed_adjudication}
        )
        changed_identity = signed.model_copy(
            update={
                "signature": signed.signature.model_copy(
                    update={"signer_id": "grader-b"}
                )
            }
        )
        replacement = Ed25519PrivateKey.generate()
        wrong_key = GradingTrustPolicy(
            policy_id="substituted-key",
            rubric_sha256=self.policy.rubric_sha256,
            adjudicators=(
                trusted_adjudicator(
                    "grader-a", replacement.public_key().public_bytes_raw()
                ),
                self.policy.adjudicators[1],
            ),
        )
        raw_signature = self.left.sign(canonical_bytes(self.adjudication))
        wrong_domain = SignedAdjudication(
            adjudication=self.adjudication,
            signature=AdjudicationSignature(
                signer_id="grader-a",
                public_key_sha256=self.policy.adjudicators[0].public_key_sha256,
                adjudication_sha256=self.adjudication.adjudication_sha256,
                signature_base64=base64.b64encode(raw_signature).decode("ascii"),
            ),
        )
        for candidate, policy in (
            (changed_content, self.policy),
            (changed_identity, self.policy),
            (signed, wrong_key),
            (wrong_domain, self.policy),
        ):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                authenticate_adjudication(self.batch, candidate, policy)

    def test_only_complete_trusted_human_artifacts_are_accepted(self) -> None:
        fixture = self.adjudication.model_copy(
            update={
                "adjudicator": self.adjudication.adjudicator.model_copy(
                    update={"method": "fixture"}
                )
            }
        )
        unresolved_decision = (
            self.adjudication.judgments[0]
            .findings[0]
            .model_copy(
                update={"disposition": "unresolved", "expected_finding_ids": ()}
            )
        )
        unresolved = replace_decision(self.adjudication, unresolved_decision)
        authenticated = authenticate_adjudication(
            self.batch,
            sign_adjudication(unresolved, "grader-a", self.left.private_bytes_raw()),
            self.policy,
        )
        self.assertEqual(
            authenticated.signed_adjudication.adjudication,
            unresolved,
        )
        with self.assertRaisesRegex(ValueError, "human"):
            authenticate_adjudication(
                self.batch,
                sign_adjudication(fixture, "grader-a", self.left.private_bytes_raw()),
                self.policy,
            )
        with self.assertRaises(ValidationError):
            GradingTrustPolicy(
                policy_id="duplicate-key",
                rubric_sha256=self.policy.rubric_sha256,
                adjudicators=(
                    self.policy.adjudicators[0],
                    self.policy.adjudicators[0].model_copy(
                        update={"adjudicator_id": "grader-b"}
                    ),
                ),
            )

    def test_receipt_rejects_substituted_batch_or_policy(self) -> None:
        authenticated = authenticate_adjudication(
            self.batch, self.signed(), self.policy
        )
        changed = authenticated.model_copy(update={"grading_batch_sha256": "0" * 64})
        with self.assertRaises(ValueError):
            verify_authenticated_adjudication(self.batch, changed, self.policy)
        changed_policy = self.policy.model_copy(update={"policy_id": "changed"})
        with self.assertRaises(ValueError):
            verify_authenticated_adjudication(self.batch, authenticated, changed_policy)

    def test_cli_writes_private_reverifiable_receipt_without_private_key(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "batch": root / "grading.json",
                "signed": root / "signed.json",
                "policy": root / "trust.json",
                "output": root / "authenticated.json",
            }
            private_write(paths["batch"], canonical_bytes(self.batch))
            private_write(paths["signed"], canonical_bytes(self.signed()))
            private_write(paths["policy"], canonical_bytes(self.policy))
            arguments = [
                "eval-authenticate-adjudication",
                "--grading-batch",
                str(paths["batch"]),
                "--signed-adjudication",
                str(paths["signed"]),
                "--trust-policy",
                str(paths["policy"]),
                "--output",
                str(paths["output"]),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            authenticated = AuthenticatedAdjudication.model_validate_json(
                paths["output"].read_bytes()
            )
            self.assertEqual(
                event["authenticated_adjudication_sha256"],
                authenticated.authenticated_adjudication_sha256,
            )
            self.assertEqual(stat.S_IMODE(paths["output"].stat().st_mode), 0o600)
            verify_authenticated_adjudication(self.batch, authenticated, self.policy)
            private_key = self.left.private_bytes_raw()
            self.assertNotIn(private_key, paths["output"].read_bytes())
            self.assertNotIn(
                base64.b64encode(private_key), paths["output"].read_bytes()
            )

            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)


class AuthenticationEncodingTests(TestCase):
    def test_noncanonical_keys_and_signatures_fail_closed(self) -> None:
        with self.assertRaises((ValidationError, ValueError)):
            trusted_adjudicator("grader-a", b"short")
        with self.assertRaisesRegex(ValueError, "private key"):
            sign_adjudication(ratings(packet()), "grader-a", b"short")
        with self.assertRaisesRegex(ValueError, "identity"):
            sign_adjudication(
                ratings(packet()),
                "grader-b",
                Ed25519PrivateKey.generate().private_bytes_raw(),
            )
        value = {
            "signer_id": "grader-a",
            "public_key_sha256": digest(b"key"),
            "adjudication_sha256": "a" * 64,
            "signature_base64": "!" * 88,
        }
        with self.assertRaises(ValidationError):
            AdjudicationSignature.model_validate(value)
