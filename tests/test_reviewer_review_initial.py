"""Review subject includes the authorized metadata descendant and full patch."""

# pyright: reportPrivateUsage=false
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from test_reviewer_provenance import NOW, G4ProvenanceFixture

from mos_eisley.core.models import digest
from mos_eisley.reviewer_final_suites import G4FinalWholeSuiteReceipt
from mos_eisley.reviewer_initial_final import G4InitialFinalInputs
from mos_eisley.reviewer_review_initial import (
    G4MetadataReviewLineageRecord,
    build_initial_review_subject,
)


class MetadataReviewSubjectTests(unittest.TestCase):
    def test_full_diff_and_lineage_identify_metadata_without_replacing_initial(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            fixture = G4ProvenanceFixture(folder, single_operator=True)
            root = folder / "amended"
            root.mkdir()
            plan = folder / "PLAN.md"
            plan.write_bytes(b"approved plan")
            # Fixture creator plan identity is unrelated to the task below; replace only
            # this test fixture's subject metadata, with upstream replay mocked.
            creator = fixture.creator.model_copy(
                update={
                    "approval": fixture.creator.approval.model_copy(
                        update={"approved_plan_sha256": digest(plan.read_bytes())}
                    )
                }
            )
            inputs = MagicMock(spec=G4InitialFinalInputs)
            inputs.chain = MagicMock()
            inputs.candidate = MagicMock()
            chain = inputs.chain
            chain.integrated_root = root
            chain.original_root = fixture.repository
            chain.creator = creator
            chain.policy = fixture.policy
            chain.assignment.assignment.base_revision = fixture.base_revision
            original = MagicMock()
            original.record.integrated_revision = fixture.child_revision
            chain.signed_integration = original
            chain.dispatch.receipt_sha256 = digest(b"dispatch")
            chain.production.receipt_sha256 = digest(b"production")
            chain.binding.binding_record_sha256 = digest(b"binding")
            inputs.candidate.receipt_sha256 = digest(b"candidate")
            final = MagicMock(spec=G4FinalWholeSuiteReceipt)
            final.final_suites_passed = True
            final.receipt_sha256 = digest(b"final")
            final.started_at = NOW
            metadata = MagicMock()
            metadata.record.revision = "b" * 40
            metadata.artifact_sha256 = digest(b"metadata")
            chain.signed_metadata = metadata
            prefix = "mos_eisley.reviewer_review_initial."
            with (
                patch(prefix + "verify_initial_final_receipt"),
                patch(
                    prefix + "_verified_evidence_packet",
                    return_value="verified evidence",
                ),
                patch(prefix + "_git", return_value=b"complete patch") as git,
                patch(prefix + "canonical_bytes", return_value=b"original record"),
            ):
                bundle = build_initial_review_subject(final, inputs, plan)
                self.assertEqual(bundle.subject.source_revision, "b" * 40)
                self.assertIn("b" * 40, git.call_args.args[2])
                self.assertIsInstance(
                    bundle.context.lineage, G4MetadataReviewLineageRecord
                )
                lineage = bundle.context.lineage
                assert isinstance(lineage, G4MetadataReviewLineageRecord)
                self.assertEqual(
                    lineage.signed_metadata_record_sha256, digest(b"metadata")
                )
                self.assertEqual(
                    lineage.signed_integration_sha256, digest(b"original record")
                )
                chain.signed_metadata = None
                legacy = build_initial_review_subject(final, inputs, plan)
                self.assertEqual(legacy.subject.source_revision, fixture.child_revision)
                self.assertNotIn(
                    "signed_metadata_record_sha256", legacy.context.lineage.model_dump()
                )
                final.final_suites_passed = False
                with self.assertRaisesRegex(ValueError, "two passing final suites"):
                    build_initial_review_subject(final, inputs, plan)
