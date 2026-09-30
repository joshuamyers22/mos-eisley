"""Final authority stays bound to its store, requests and deadline."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import Contract, digest
from mos_eisley.reviewer_final_suites import sign_final_whole_suite_approval
from mos_eisley.reviewer_initial_correction_final import (
    G4InitialCorrectionFinalInputs,
    _claim,
    _save_stage,
    _verify_creator_collection,
    _verify_stage,
    initial_correction_final_approval,
    preflight_initial_correction_final,
    run_initial_correction_final,
)
from mos_eisley.reviewer_provenance import G4ProvenanceTrustPolicy, provenance_signer
from mos_eisley.reviewer_test_execution import ReviewerTestExecutionRequest
from mos_eisley.reviewer_test_package import (
    FrozenReviewerTestPackage,
    TestCollectionContract,
)

NOW = datetime(2026, 9, 30, 22, 0, tzinfo=UTC)


class RevisionFixture(Contract):
    integrated_revision: str = "a" * 40


class IntegrationFixture(Contract):
    record: RevisionFixture = RevisionFixture()


class CorrectionFinalAuthorityTests(unittest.TestCase):
    def test_retained_stage_receipts_cannot_be_replaced_or_overwritten(self) -> None:
        receipt = IntegrationFixture()
        with TemporaryDirectory() as temporary:
            store = Path(temporary)
            _save_stage(store, "stage.json", receipt)
            _verify_stage(store, "stage.json", receipt)
            with self.assertRaises(FileExistsError):
                _save_stage(store, "stage.json", receipt)
            (store / "stage.json").write_bytes(b"substituted")
            with self.assertRaises(ValueError):
                _verify_stage(store, "stage.json", receipt)

    def test_creator_discovery_requires_initializer_in_frozen_inventory(self) -> None:
        package = MagicMock(spec=FrozenReviewerTestPackage)
        package.payload = MagicMock()
        declaration = MagicMock()
        declaration.declaration.path = "tests/test_order.py"
        package.payload.files = (declaration,)
        package.payload.manifest.collection = TestCollectionContract(
            start_directory="tests",
            top_level_directory=".",
            expected_collected_tests=13,
            expected_executed_tests=13,
        )
        with self.assertRaises(ValueError):
            _verify_creator_collection(package)
        package.payload.manifest.collection = (
            package.payload.manifest.collection.model_copy(
                update={"top_level_directory": "tests"}
            )
        )
        _verify_creator_collection(package)

    def test_deadline_and_store_or_request_substitution_are_denied(self) -> None:
        keys = [Ed25519PrivateKey.generate() for _ in range(4)]
        policy = G4ProvenanceTrustPolicy(
            policy_id="correction-final-fixture",
            creators=(provenance_signer("creator", keys[0].public_key()),),
            reviewers=(provenance_signer("reviewer", keys[1].public_key()),),
            vcs_brokers=(provenance_signer("vcs", keys[2].public_key()),),
            children=(provenance_signer("child", keys[3].public_key()),),
            valid_from=NOW - timedelta(hours=1),
            valid_until=NOW + timedelta(hours=4),
        )
        inputs = MagicMock(spec=G4InitialCorrectionFinalInputs)
        inputs.chain = MagicMock()
        inputs.candidate = MagicMock()
        inputs.creator_package = MagicMock()
        inputs.chain.first_inputs.policy = policy
        inputs.chain.signed_integration = IntegrationFixture()
        inputs.chain.first_inputs.creator.approval.creator_test_suite_sha256 = digest(
            b"creator"
        )
        inputs.chain.first_inputs.package.frozen_package_sha256 = digest(b"reviewer")
        inputs.chain.first_inputs.container.image_id = "sha256:" + "b" * 64
        inputs.chain.binding.binding_record_sha256 = digest(b"binding")
        inputs.chain.admission.approval.approval.expires_at = NOW + timedelta(hours=3)
        inputs.chain.admission.approval.approval.task_budget.deadline = NOW + timedelta(
            hours=3
        )
        inputs.candidate.receipt_sha256 = digest(b"passing candidate")
        inputs.candidate.ran_at = NOW - timedelta(minutes=1)
        inputs.creator_package.frozen_package_sha256 = digest(b"creator package")
        inputs.creator_request = ReviewerTestExecutionRequest(
            execution_id="creator-final",
            binding_record_sha256=digest(b"binding"),
            container_image_id="sha256:" + "b" * 64,
            role="candidate",
            timeout_seconds=30,
        )
        inputs.reviewer_request = inputs.creator_request.model_copy(
            update={"execution_id": "reviewer-final"}
        )
        with TemporaryDirectory() as temporary:
            inputs.final_store = Path(temporary)
            approval = initial_correction_final_approval(inputs, NOW)
            signed = sign_final_whole_suite_approval(approval, "creator", keys[0])
            # The real subject replay is separately exercised by owner-local preflight.
            with patch(
                "mos_eisley.reviewer_initial_correction_final.replay_initial_correction_final_inputs"
            ):
                preflight_initial_correction_final(signed, inputs, now=NOW)
                _claim(inputs.final_store, inputs.candidate.receipt_sha256, signed)
                with (
                    patch(
                        "mos_eisley.reviewer_initial_correction_final.datetime"
                    ) as clock,
                    patch(
                        "mos_eisley.reviewer_initial_correction_final.execute_isolated_creator_tests_in_trusted_host"
                    ) as creator_run,
                    patch(
                        "mos_eisley.reviewer_initial_correction_final.execute_isolated_reviewer_tests_in_trusted_host"
                    ) as reviewer_run,
                ):
                    clock.now.return_value = NOW
                    with self.assertRaises(FileExistsError):
                        run_initial_correction_final(signed, inputs)
                    creator_run.assert_not_called()
                    reviewer_run.assert_not_called()
                with self.assertRaises(ValueError):
                    preflight_initial_correction_final(
                        signed, inputs, now=approval.expires_at
                    )
                old_request = inputs.reviewer_request
                inputs.reviewer_request = old_request.model_copy(
                    update={"execution_id": "substituted"}
                )
                with self.assertRaises(ValueError):
                    preflight_initial_correction_final(signed, inputs, now=NOW)
                inputs.reviewer_request = old_request
                with TemporaryDirectory() as other:
                    inputs.final_store = Path(other)
                    with self.assertRaises(ValueError):
                        preflight_initial_correction_final(signed, inputs, now=NOW)


if __name__ == "__main__":
    unittest.main()
