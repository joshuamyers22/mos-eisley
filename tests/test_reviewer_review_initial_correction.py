"""The prospective amendment cannot transfer to other evidence or signers."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import test_reviewer_single_operator_review as single_fixture
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_reviewer_provenance import NOW

from mos_eisley.core.models import digest
from mos_eisley.reviewer_final_suites import G4FinalWholeSuiteReceipt
from mos_eisley.reviewer_initial_correction_final import G4InitialCorrectionFinalInputs
from mos_eisley.reviewer_review_initial_correction import (
    G4ConnectedProspectiveReviewAmendment,
    G4InitialCorrectionReviewBundle,
    G4InitialCorrectionReviewContext,
    assess_initial_correction_single_operator_review,
    build_initial_correction_review_subject,
    sign_connected_review_amendment,
    verify_connected_review_amendment,
)


class ConnectedReviewTests(unittest.TestCase):
    def test_changed_document_subject_authority_time_and_key_fail(self) -> None:
        with TemporaryDirectory() as directory:
            common, case = single_fixture.G4SingleOperatorReviewTests()._case(
                Path(directory)
            )
            subject, provenance, authority, critics, judge, decision = case
            context = MagicMock(spec=G4InitialCorrectionReviewContext)
            context.policy = provenance.policy
            context.record_sha256 = provenance.record_sha256
            context.creator_approval = provenance.creator_approval
            context.git_provenance = provenance.git_provenance
            bundle = G4InitialCorrectionReviewBundle(subject, context)
            document = digest(b"prospective amendment")
            body = G4ConnectedProspectiveReviewAmendment(
                integrated_revision=subject.source_revision,
                subject_sha256=subject.subject_sha256,
                review_authority_sha256=authority.artifact_sha256,
                policy_sha256=provenance.policy.policy_sha256,
                amendment_document_sha256=document,
                issued_at=NOW + timedelta(minutes=9, seconds=1),
            )
            key = common["creator_key"]
            signed = sign_connected_review_amendment(body, "creator", key)
            verify_connected_review_amendment(signed, authority, bundle, document)
            self.assertFalse(signed.amendment.independent_human_review_proven)
            self.assertFalse(signed.amendment.acceptance_authorized)
            with self.assertRaises(ValueError):
                verify_connected_review_amendment(
                    signed, authority, bundle, digest(b"changed document")
                )
            for change in (
                {"integrated_revision": "a" * 40},
                {"subject_sha256": digest(b"changed subject")},
                {"review_authority_sha256": digest(b"changed authority")},
                {"issued_at": NOW + timedelta(minutes=8)},
                {"issued_at": authority.authority.expires_at},
            ):
                altered = sign_connected_review_amendment(
                    body.model_copy(update=change), "creator", key
                )
                with self.assertRaises(ValueError):
                    verify_connected_review_amendment(
                        altered, authority, bundle, document
                    )
            foreign = sign_connected_review_amendment(
                body, "creator", Ed25519PrivateKey.generate()
            )
            with self.assertRaises(ValueError):
                verify_connected_review_amendment(foreign, authority, bundle, document)
            document_path = Path(directory) / "amendment.md"
            document_path.write_bytes(b"prospective amendment")
            with patch(
                "mos_eisley.reviewer_review_initial_correction.build_initial_correction_review_subject",
                return_value=bundle,
            ):
                record = assess_initial_correction_single_operator_review(
                    MagicMock(spec=G4FinalWholeSuiteReceipt),
                    MagicMock(spec=G4InitialCorrectionFinalInputs),
                    Path(directory) / "PLAN.md",
                    document_path,
                    signed,
                    authority,
                    critics,
                    judge,
                    decision,
                )
                self.assertTrue(record.single_operator_review_evidence_passed)
                self.assertFalse(record.independent_review_evidence_passed)
                late = sign_connected_review_amendment(
                    body.model_copy(update={"issued_at": NOW + timedelta(minutes=14)}),
                    "creator",
                    key,
                )
                with self.assertRaises(ValueError):
                    assess_initial_correction_single_operator_review(
                        MagicMock(spec=G4FinalWholeSuiteReceipt),
                        MagicMock(spec=G4InitialCorrectionFinalInputs),
                        Path(directory) / "PLAN.md",
                        document_path,
                        late,
                        authority,
                        critics,
                        judge,
                        decision,
                    )

    def test_failed_suites_and_wrong_plan_cannot_build_subject(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "PLAN.md"
            plan.write_bytes(b"changed plan")
            task = root / "task"
            task.mkdir()
            inputs = MagicMock(spec=G4InitialCorrectionFinalInputs)
            inputs.chain = MagicMock()
            inputs.chain.candidate_root = task
            inputs.chain.first_inputs.original_root = task
            inputs.chain.first_inputs.integrated_root = task
            inputs.chain.first_inputs.creator.approval.approved_plan_sha256 = digest(
                b"signed plan"
            )
            final = MagicMock(spec=G4FinalWholeSuiteReceipt)
            # Isolate pure post-replay guards; the owner preflight replays real chain.
            with (
                patch(
                    "mos_eisley.reviewer_review_initial_correction.verify_initial_correction_final_receipt"
                ),
                patch("mos_eisley.reviewer_review_initial_correction._git") as git,
            ):
                final.final_suites_passed = False
                with self.assertRaises(ValueError):
                    build_initial_correction_review_subject(final, inputs, plan)
                final.final_suites_passed = True
                with self.assertRaises(ValueError):
                    build_initial_correction_review_subject(final, inputs, plan)
                git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
