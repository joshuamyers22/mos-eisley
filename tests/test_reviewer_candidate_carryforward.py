"""Authority and one-use checks for post-deadline G4 candidate execution."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError
from test_reviewer_provenance import IMAGE, NOW, G4ProvenanceFixture

from mos_eisley.reviewer_candidate_carryforward import (
    _DOMAIN,
    G4CarryForwardCandidateAdmission,
    G4CarryForwardCandidateApproval,
    _claim,
    _verify_claim,
    sign_carryforward_candidate_approval,
)
from mos_eisley.reviewer_provenance import verify_provenance_signature
from mos_eisley.reviewer_test_execution import ReviewerTestExecutionRequest


class CarryForwardCandidateAuthorityTests(unittest.TestCase):
    def _approval(self) -> G4CarryForwardCandidateApproval:
        return G4CarryForwardCandidateApproval(
            approval_id="integrated-candidate-one",
            historical_provenance_sha256="a" * 64,
            signed_integration_sha256="b" * 64,
            renewed_policy_sha256="c" * 64,
            binding_record_sha256="d" * 64,
            known_control_record_sha256="e" * 64,
            request_sha256="f" * 64,
            repository_id="fixture-repository",
            integrated_revision="a" * 40,
            container_image_id=IMAGE,
            issued_at=NOW + timedelta(minutes=4),
            expires_at=NOW + timedelta(minutes=20),
        )

    def test_separate_signature_domain_and_exact_body(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = G4ProvenanceFixture(Path(directory))
            approval = self._approval()
            signed = sign_carryforward_candidate_approval(
                approval, "creator", fixture.creator_key
            )
            verify_provenance_signature(
                approval, signed.signature, fixture.policy, "creator", _DOMAIN
            )
            with self.assertRaisesRegex(ValueError, "invalid G4 creator signature"):
                verify_provenance_signature(
                    approval,
                    signed.signature,
                    fixture.policy,
                    "creator",
                    b"mos-eisley/g4-candidate-execution-approval/v1\x00",
                )
            with self.assertRaisesRegex(ValueError, "invalid G4 creator signature"):
                verify_provenance_signature(
                    approval.model_copy(update={"integrated_revision": "b" * 40}),
                    signed.signature,
                    fixture.policy,
                    "creator",
                    _DOMAIN,
                )

    def test_window_and_forbidden_authority_are_rejected(self) -> None:
        approval = self._approval()
        with self.assertRaises(ValidationError):
            G4CarryForwardCandidateApproval.model_validate(
                {**approval.model_dump(), "expires_at": NOW + timedelta(hours=25)}
            )
        with self.assertRaises(ValidationError):
            G4CarryForwardCandidateApproval.model_validate(
                {**approval.model_dump(), "provider_dispatch_authorized": True}
            )

    def test_private_claim_is_exclusive_and_replay_checked(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = G4ProvenanceFixture(root)
            store = root / "claims"
            store.mkdir(mode=0o700)
            approval = sign_carryforward_candidate_approval(
                self._approval(), "creator", fixture.creator_key
            )
            request = ReviewerTestExecutionRequest(
                execution_id="integrated-candidate-one",
                binding_record_sha256="d" * 64,
                container_image_id=IMAGE,
                role="candidate",
                timeout_seconds=10,
            )
            admission = G4CarryForwardCandidateAdmission(
                approval=approval,
                request=request,
                integrated_git_provenance_sha256="1" * 64,
                admitted_at=NOW + timedelta(minutes=5),
            )
            _claim(store, admission)
            _verify_claim(store, admission)
            with self.assertRaises(FileExistsError):
                _claim(store, admission)
            claim = store / f"{approval.artifact_sha256}.claim"
            claim.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "differs from admission"):
                _verify_claim(store, admission)


if __name__ == "__main__":
    unittest.main()
