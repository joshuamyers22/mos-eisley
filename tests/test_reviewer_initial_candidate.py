"""Fresh initial-child candidate signature, scope and one-use regressions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import Contract, canonical_bytes, digest
from mos_eisley.reviewer_initial_candidate import (
    G4InitialCandidateApproval,
    G4InitialCandidateInputs,
    G4MetadataCandidateApproval,
    SignedG4InitialCandidateApproval,
    _claim,
    _verify_claim,
    preflight_initial_candidate,
    sign_initial_candidate_approval,
)
from mos_eisley.reviewer_provenance import G4ProvenanceTrustPolicy, provenance_signer
from mos_eisley.reviewer_test_execution import ReviewerTestExecutionRequest

IMAGE = "sha256:" + "a" * 64


class InitialCandidateApprovalTests(unittest.TestCase):
    def test_exact_grant_and_private_one_use_claim(self) -> None:
        with TemporaryDirectory() as temporary:
            owner = Ed25519PrivateKey.generate()
            child = Ed25519PrivateKey.generate()
            foreign = Ed25519PrivateKey.generate()
            now = datetime.now(UTC)
            human = provenance_signer("owner", owner.public_key())
            policy = G4ProvenanceTrustPolicy(
                schema_version=2,
                policy_id="initial-candidate-fixture",
                creators=(human,),
                reviewers=(human,),
                vcs_brokers=(human,),
                children=(provenance_signer("child", child.public_key()),),
                valid_from=now - timedelta(minutes=10),
                valid_until=now + timedelta(hours=1),
                operator_mode="single_operator",
            )
            binding_hash = digest(b"binding")
            controls_hash = digest(b"controls")
            signed_integration_hash = digest(b"signed integration")
            revision = "a" * 40
            request = ReviewerTestExecutionRequest(
                execution_id="initial-candidate-test",
                binding_record_sha256=binding_hash,
                container_image_id=IMAGE,
                role="candidate",
            )
            body = G4InitialCandidateApproval(
                approval_id="initial-candidate-approval",
                policy_sha256=policy.policy_sha256,
                signed_integration_sha256=signed_integration_hash,
                binding_record_sha256=binding_hash,
                known_control_record_sha256=controls_hash,
                request_sha256=request.request_sha256,
                integrated_revision=revision,
                container_image_id=IMAGE,
                issued_at=now,
                expires_at=now + timedelta(minutes=20),
            )
            signed = sign_initial_candidate_approval(body, "owner", owner)
            fake = SimpleNamespace(
                policy=policy,
                signed_integration=SimpleNamespace(
                    record=SimpleNamespace(
                        integrated_at=now - timedelta(minutes=1),
                        integrated_revision=revision,
                    )
                ),
                binding=SimpleNamespace(binding_record_sha256=binding_hash),
                controls=SimpleNamespace(control_record_sha256=controls_hash),
                container=SimpleNamespace(image_id=IMAGE),
                package_path=Path(temporary),
                integrated_root=Path(temporary),
            )
            inputs = cast(G4InitialCandidateInputs, fake)
            changed = sign_initial_candidate_approval(
                body.model_copy(update={"integrated_revision": "b" * 40}),
                "owner",
                owner,
            )
            wrong_key = sign_initial_candidate_approval(body, "owner", foreign)

            def exact_bytes(value: object) -> bytes:
                if value is fake.signed_integration:
                    return b"signed integration"
                return canonical_bytes(cast(Contract, value))

            with (
                patch(
                    "mos_eisley.reviewer_initial_candidate.replay_initial_candidate_inputs"
                ),
                patch(
                    "mos_eisley.reviewer_initial_candidate.build_isolated_reviewer_test_job"
                ),
                patch(
                    "mos_eisley.reviewer_initial_candidate.canonical_bytes",
                    side_effect=exact_bytes,
                ),
            ):
                preflight_initial_candidate(signed, request, inputs, now=now)
                with self.assertRaisesRegex(ValueError, "exact inputs"):
                    preflight_initial_candidate(changed, request, inputs, now=now)
                with self.assertRaisesRegex(ValueError, "not enrolled"):
                    preflight_initial_candidate(wrong_key, request, inputs, now=now)
                fake.signed_metadata = SimpleNamespace(
                    artifact_sha256=digest(b"metadata"),
                    record=SimpleNamespace(
                        revision="b" * 40, amended_at=now - timedelta(seconds=30)
                    ),
                )
                metadata_body = G4MetadataCandidateApproval.model_validate(
                    body.model_dump()
                    | {
                        "integrated_revision": "b" * 40,
                        "signed_metadata_record_sha256": digest(b"metadata"),
                    }
                )
                metadata_signed = sign_initial_candidate_approval(
                    metadata_body, "owner", owner
                )
                decoded = SignedG4InitialCandidateApproval.model_validate_json(
                    metadata_signed.model_dump_json()
                )
                self.assertIsInstance(decoded.approval, G4MetadataCandidateApproval)
                preflight_initial_candidate(decoded, request, inputs, now=now)
                with self.assertRaisesRegex(ValueError, "invalid G4 creator signature"):
                    preflight_initial_candidate(
                        metadata_signed.model_copy(
                            update={"signature": signed.signature}
                        ),
                        request,
                        inputs,
                        now=now,
                    )
                with self.assertRaisesRegex(ValueError, "signed amendment"):
                    preflight_initial_candidate(signed, request, inputs, now=now)
                altered = sign_initial_candidate_approval(
                    metadata_body.model_copy(
                        update={"signed_metadata_record_sha256": digest(b"other")}
                    ),
                    "owner",
                    owner,
                )
                with self.assertRaisesRegex(ValueError, "signed amendment"):
                    preflight_initial_candidate(altered, request, inputs, now=now)
                with self.assertRaisesRegex(ValueError, "exact inputs"):
                    preflight_initial_candidate(
                        sign_initial_candidate_approval(
                            metadata_body.model_copy(
                                update={"integrated_revision": revision}
                            ),
                            "owner",
                            owner,
                        ),
                        request,
                        inputs,
                        now=now,
                    )
                fake.signed_metadata = None
                with self.assertRaisesRegex(ValueError, "lacks signed amendment"):
                    preflight_initial_candidate(decoded, request, inputs, now=now)
            store = Path(temporary) / "claims"
            store.mkdir(mode=0o700)
            _claim(store, signed)
            _verify_claim(store, signed)
            with self.assertRaises(FileExistsError):
                _claim(store, signed)


if __name__ == "__main__":
    unittest.main()
