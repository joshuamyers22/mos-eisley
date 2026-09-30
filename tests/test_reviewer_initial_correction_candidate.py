"""Correction test authority cannot be substituted or broadened."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import digest
from mos_eisley.reviewer_initial_correction_candidate import (
    G4InitialCorrectionCandidateApproval,
    sign_initial_correction_candidate_approval,
)
from mos_eisley.reviewer_provenance import (
    G4ProvenanceTrustPolicy,
    provenance_signer,
    verify_provenance_signature,
)

NOW = datetime(2026, 9, 30, 22, 0, tzinfo=UTC)
DOMAIN = b"mos-eisley/g4-initial-correction-candidate-approval/v1\x00"


class CorrectionCandidateAuthorityTests(unittest.TestCase):
    def test_exact_request_signature_cannot_authorize_initial_candidate(self) -> None:
        keys = [Ed25519PrivateKey.generate() for _ in range(4)]
        policy = G4ProvenanceTrustPolicy(
            policy_id="corrected-candidate-fixture",
            creators=(provenance_signer("creator", keys[0].public_key()),),
            reviewers=(provenance_signer("reviewer", keys[1].public_key()),),
            vcs_brokers=(provenance_signer("vcs", keys[2].public_key()),),
            children=(provenance_signer("child", keys[3].public_key()),),
            valid_from=NOW - timedelta(hours=1),
            valid_until=NOW + timedelta(hours=4),
        )
        approval = G4InitialCorrectionCandidateApproval(
            approval_id="corrected-candidate",
            policy_sha256=policy.policy_sha256,
            admission_sha256=digest(b"admission"),
            signed_integration_sha256=digest(b"vcs"),
            binding_record_sha256=digest(b"binding"),
            known_control_record_sha256=digest(b"controls"),
            reviewer_package_sha256=digest(b"package"),
            request_sha256=digest(b"request"),
            candidate_store_sha256=digest(b"store"),
            integrated_revision="a" * 40,
            container_image_id="sha256:" + "b" * 64,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=2),
        )
        signed = sign_initial_correction_candidate_approval(
            approval, "creator", keys[0]
        )
        verify_provenance_signature(
            approval, signed.signature, policy, "creator", DOMAIN
        )
        with self.assertRaises(ValueError):
            verify_provenance_signature(
                approval,
                signed.signature,
                policy,
                "creator",
                b"mos-eisley/g4-initial-candidate-approval/v1\x00",
            )
        with self.assertRaises(ValueError):
            verify_provenance_signature(
                approval.model_copy(
                    update={"request_sha256": digest(b"other request")}
                ),
                signed.signature,
                policy,
                "creator",
                DOMAIN,
            )
        with self.assertRaises(ValueError):
            G4InitialCorrectionCandidateApproval.model_validate(
                approval.model_dump() | {"final_suite_authorized": True}
            )
        with self.assertRaises(ValueError):
            G4InitialCorrectionCandidateApproval.model_validate(
                approval.model_dump() | {"expires_at": NOW}
            )


if __name__ == "__main__":
    unittest.main()
