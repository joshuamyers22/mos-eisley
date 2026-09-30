"""Signature-domain and scope regressions for initial correction write authority."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import digest
from mos_eisley.reviewer_initial_correction_integration import (
    G4InitialCorrectionIntegrationApproval,
    sign_initial_correction_integration_approval,
)
from mos_eisley.reviewer_provenance import (
    G4ProvenanceTrustPolicy,
    provenance_signer,
    verify_provenance_signature,
)

NOW = datetime(2026, 9, 30, 21, 0, tzinfo=UTC)
CORRECTION_DOMAIN = b"mos-eisley/g4-initial-correction-integration-approval/v1\x00"
INITIAL_DOMAIN = b"mos-eisley/g4-initial-integration-approval/v1\x00"


class InitialCorrectionIntegrationAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = [Ed25519PrivateKey.generate() for _ in range(4)]
        creator, reviewer, vcs, child = self.keys
        self.policy = G4ProvenanceTrustPolicy(
            policy_id="correction-integration-fixture",
            creators=(provenance_signer("creator", creator.public_key()),),
            reviewers=(provenance_signer("reviewer", reviewer.public_key()),),
            vcs_brokers=(provenance_signer("vcs", vcs.public_key()),),
            children=(provenance_signer("child", child.public_key()),),
            valid_from=NOW - timedelta(hours=1),
            valid_until=NOW + timedelta(hours=5),
        )

    def approval(self) -> G4InitialCorrectionIntegrationApproval:
        return G4InitialCorrectionIntegrationApproval(
            integration_id="correction-one",
            policy_sha256=self.policy.policy_sha256,
            admission_sha256=digest(b"admission"),
            child_dispatch_receipt_sha256=digest(b"dispatch"),
            production_receipt_sha256=digest(b"production"),
            source_revision="a" * 40,
            source_root_sha256=digest(b"source-root"),
            integration_store_sha256=digest(b"integration-store"),
            owned_paths=("src/demo.py",),
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=2),
        )

    def test_separate_domain_signs_only_exact_integration_grant(self) -> None:
        approval = self.approval()
        signed = sign_initial_correction_integration_approval(
            approval, "creator", self.keys[0]
        )
        verify_provenance_signature(
            approval, signed.signature, self.policy, "creator", CORRECTION_DOMAIN
        )
        with self.assertRaises(ValueError):
            verify_provenance_signature(
                approval, signed.signature, self.policy, "creator", INITIAL_DOMAIN
            )
        with self.assertRaises(ValueError):
            verify_provenance_signature(
                approval.model_copy(update={"source_revision": "b" * 40}),
                signed.signature,
                self.policy,
                "creator",
                CORRECTION_DOMAIN,
            )

    def test_scope_and_window_are_bounded_before_signing(self) -> None:
        with self.assertRaises(ValueError):
            G4InitialCorrectionIntegrationApproval.model_validate(
                self.approval().model_dump() | {"expires_at": NOW + timedelta(hours=25)}
            )
        with self.assertRaises(ValueError):
            G4InitialCorrectionIntegrationApproval.model_validate(
                self.approval().model_dump()
                | {"owned_paths": ("src/demo.py", "src/demo.py")}
            )


if __name__ == "__main__":
    unittest.main()
