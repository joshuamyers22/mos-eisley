"""The exact one-human exception cannot fabricate independent human review."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from test_reviewer_provenance import NOW
from test_reviewer_single_operator_review import G4SingleOperatorReviewTests

from mos_eisley.core.models import digest
from mos_eisley.reviewer_g4_one_human_exception import (
    G4OneHumanFormalReviewException,
    sign_one_human_formal_review_exception,
    verify_one_human_formal_review_exception,
)
from mos_eisley.reviewer_single_operator_review import assess_single_operator_review


class G4OneHumanExceptionTests(unittest.TestCase):
    def _case(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        common, case = G4SingleOperatorReviewTests()._case(Path(directory.name))
        record = assess_single_operator_review(*case)
        policy = common["provenance"].policy
        doc_hash = digest(b"specific proposed amendment")
        body = G4OneHumanFormalReviewException(
            integrated_revision=record.subject.source_revision,
            subject_sha256=record.subject.subject_sha256,
            review_record_sha256=record.record_sha256,
            amendment_document_sha256=doc_hash,
            owner_signer_id="creator",
            issued_at=NOW + timedelta(minutes=17),
        )
        signed = sign_one_human_formal_review_exception(body, common["creator_key"])
        return signed, record, policy, doc_hash

    def test_exact_owner_signed_accept_review_passes(self) -> None:
        signed, record, policy, doc_hash = self._case()
        verify_one_human_formal_review_exception(
            signed, record, policy, amendment_document_sha256=doc_hash
        )
        self.assertFalse(signed.exception.independent_human_review_proven)
        self.assertFalse(signed.exception.original_independent_review_gate_passed)
        self.assertFalse(signed.exception.acceptance_authorized)

    def test_changed_review_or_amendment_is_rejected(self) -> None:
        signed, record, policy, doc_hash = self._case()
        with self.assertRaisesRegex(ValueError, "exact accepted review"):
            verify_one_human_formal_review_exception(
                signed,
                record.model_copy(
                    update={"single_operator_review_evidence_passed": False}
                ),
                policy,
                amendment_document_sha256=doc_hash,
            )
        with self.assertRaisesRegex(ValueError, "exact accepted review"):
            verify_one_human_formal_review_exception(
                signed, record, policy, amendment_document_sha256=digest(b"changed ADR")
            )

    def test_foreign_signature_is_rejected(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        signed, record, policy, doc_hash = self._case()
        foreign = sign_one_human_formal_review_exception(
            signed.exception, Ed25519PrivateKey.generate()
        )
        with self.assertRaisesRegex(ValueError, "creator signer is not enrolled"):
            verify_one_human_formal_review_exception(
                foreign, record, policy, amendment_document_sha256=doc_hash
            )


if __name__ == "__main__":
    unittest.main()
