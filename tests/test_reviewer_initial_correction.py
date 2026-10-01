"""The initial-candidate correction bridge requires two exact failed runs."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import Contract, digest
from mos_eisley.reviewer_correction import (
    G4CorrectionCycleApproval,
    G4CorrectionFinding,
    G4CorrectionReservations,
    G4CorrectionReviewPolicy,
    G4CorrectionTaskBudget,
    G4CorrectionTriage,
    SignedG4CorrectionCycleApproval,
    sign_correction_cycle_approval,
    sign_correction_triage,
)
from mos_eisley.reviewer_initial_candidate import (
    G4InitialCandidateInputs,
    G4InitialCandidateReceipt,
)
from mos_eisley.reviewer_initial_correction import (
    G4InitialCorrectionCycleAdmission,
    admit_initial_correction_cycle,
)
from mos_eisley.reviewer_provenance import G4ProvenanceTrustPolicy, provenance_signer

NOW = datetime(2026, 9, 30, 2, 0, tzinfo=UTC)
FAILED_ID = "test_order_reviewer.DependencyOrderReviewerTests.test_exact_string"


class _IntegrationRecord(Contract):
    integrated_revision: str


class _SignedIntegration(Contract):
    record: _IntegrationRecord


def _receipt(
    name: str, minute: int, *, failed_id: str = FAILED_ID
) -> G4InitialCandidateReceipt:
    observation = SimpleNamespace(
        schema_version=2,
        failures=1,
        errors=0,
        unexpected_successes=0,
        failed_test_ids=(failed_id,),
        collected_test_ids_sha256=digest(b"collected"),
        executed_test_ids_sha256=digest(b"executed"),
    )
    execution = SimpleNamespace(
        observation=observation,
        collection_contract_satisfied=True,
        binding_record_sha256=digest(b"binding"),
        frozen_reviewer_test_package_sha256=digest(b"package"),
        implementation_tree_sha256=digest(b"tree"),
        adapter_sha256=digest(b"adapter"),
        collection_sha256=digest(b"collection"),
    )
    return cast(
        G4InitialCandidateReceipt,
        SimpleNamespace(
            candidate_tests_passed=False,
            ran_at=NOW + timedelta(minutes=minute),
            approval=SimpleNamespace(artifact_sha256=digest(name.encode())),
            request=SimpleNamespace(
                execution_id=name, container_image_id="sha256:" + "a" * 64
            ),
            execution=execution,
            receipt_sha256=digest((name + " receipt").encode()),
        ),
    )


class InitialCorrectionBridgeTests(unittest.TestCase):
    def test_signed_pair_is_claimed_once_and_changed_evidence_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original"
            integrated = root / "integrated"
            original.mkdir()
            integrated.mkdir()
            first_store = root / "candidate-1"
            second_store = root / "candidate-2"
            claim_store = root / "correction"
            for store in (first_store, second_store, claim_store):
                store.mkdir(mode=0o700)
            owner = Ed25519PrivateKey.generate()
            child = Ed25519PrivateKey.generate()
            human = provenance_signer("owner", owner.public_key())
            policy = G4ProvenanceTrustPolicy(
                schema_version=2,
                policy_id="initial-correction-fixture",
                creators=(human,),
                reviewers=(human,),
                vcs_brokers=(human,),
                children=(provenance_signer("child", child.public_key()),),
                valid_from=NOW - timedelta(hours=1),
                valid_until=NOW + timedelta(hours=4),
                operator_mode="single_operator",
            )
            review_policy = G4CorrectionReviewPolicy(
                provenance_policy_sha256=policy.policy_sha256,
                judges=(human,),
                valid_from=NOW - timedelta(hours=1),
                valid_until=NOW + timedelta(hours=4),
                operator_mode="single_operator",
                independent_human_review_claimed=False,
            )
            assignment_limit = G4CorrectionReservations(
                input_tokens=1000,
                output_tokens=500,
                tool_calls=1,
                seconds=300,
                microusd=50000,
            )
            assignment = SimpleNamespace(
                child_signer_id="child",
                owned_paths=("src/dependency_lab/order.py",),
                creator_test_paths=("tests/test_order.py",),
                max_input_tokens=1000,
                max_output_tokens=500,
                max_tool_calls=1,
                max_seconds=300,
                max_microusd=50000,
            )
            source_revision = "a" * 40
            signed_integration = _SignedIntegration(
                record=_IntegrationRecord(integrated_revision=source_revision)
            )
            common = dict(
                original_root=original,
                integrated_root=integrated,
                policy=policy,
                creator=SimpleNamespace(
                    approval=SimpleNamespace(
                        approved_plan_sha256=digest(b"plan"),
                        creator_test_suite_sha256=digest(b"creator tests"),
                    )
                ),
                custody=SimpleNamespace(custody_id="custody"),
                assignment=SimpleNamespace(
                    assignment=assignment, artifact_sha256=digest(b"assignment")
                ),
                signed_integration=signed_integration,
                binding=SimpleNamespace(binding_record_sha256=digest(b"binding")),
                controls=SimpleNamespace(control_record_sha256=digest(b"controls")),
                package=SimpleNamespace(frozen_package_sha256=digest(b"package")),
            )
            first_inputs = cast(
                G4InitialCandidateInputs,
                SimpleNamespace(**common, candidate_store=first_store),
            )
            second_inputs = cast(
                G4InitialCandidateInputs,
                SimpleNamespace(**common, candidate_store=second_store),
            )
            first = _receipt("first", 0)
            second = _receipt("second", 5)
            finding = G4CorrectionFinding(
                failed_test_id=FAILED_ID,
                disposition="implementation_defect",
                applicable_clause_sha256=digest(b"clause"),
                citation_evidence_sha256=digest(b"citation"),
                violation_evidence_sha256=digest(b"violation"),
            )
            triage = sign_correction_triage(
                G4CorrectionTriage(
                    task_id="dependency-ordering",
                    cycle=1,
                    review_policy_sha256=review_policy.policy_sha256,
                    candidate_receipt_sha256=first.receipt_sha256,
                    reproduction_receipt_sha256=second.receipt_sha256,
                    critic_review_sha256=digest(b"critic review"),
                    issued_at=NOW + timedelta(minutes=6),
                    findings=(finding,),
                ),
                "owner",
                owner,
            )
            approval = sign_correction_cycle_approval(
                G4CorrectionCycleApproval(
                    approval_id="dependency-correction-1",
                    task_id="dependency-ordering",
                    cycle=1,
                    provenance_policy_sha256=policy.policy_sha256,
                    triage_artifact_sha256=triage.artifact_sha256,
                    source_revision=source_revision,
                    approved_plan_sha256=digest(b"plan"),
                    creator_test_suite_sha256=digest(b"creator tests"),
                    frozen_reviewer_test_package_sha256=digest(b"package"),
                    task_budget=G4CorrectionTaskBudget(
                        initial_assignment_sha256=digest(b"assignment"),
                        deadline=NOW + timedelta(hours=2),
                        ceiling=G4CorrectionReservations(
                            input_tokens=2000,
                            output_tokens=1000,
                            tool_calls=2,
                            seconds=600,
                            microusd=100000,
                        ),
                    ),
                    reserved_before=assignment_limit,
                    child_signer_id="child",
                    owned_paths=("src/dependency_lab/order.py",),
                    max_input_tokens=1000,
                    max_output_tokens=500,
                    max_tool_calls=1,
                    max_seconds=300,
                    max_microusd=50000,
                    issued_at=NOW + timedelta(minutes=7),
                    expires_at=NOW + timedelta(hours=1),
                ),
                "owner",
                owner,
            )

            def invoke(
                candidate: G4InitialCandidateReceipt = second,
                inputs: G4InitialCandidateInputs = second_inputs,
                signed_grant: SignedG4CorrectionCycleApproval = approval,
            ) -> G4InitialCorrectionCycleAdmission:
                return admit_initial_correction_cycle(
                    first=first,
                    reproduction=candidate,
                    first_inputs=first_inputs,
                    reproduction_inputs=inputs,
                    triage=triage,
                    approval=signed_grant,
                    review_policy=review_policy,
                    correction_store=claim_store,
                    now=NOW + timedelta(minutes=8),
                )

            with patch(
                "mos_eisley.reviewer_initial_correction.verify_initial_candidate_receipt"
            ) as verify:
                admission = invoke()
                self.assertEqual(verify.call_count, 2)
                self.assertEqual(
                    admission.candidate_receipt_sha256, first.receipt_sha256
                )
                self.assertFalse(admission.child_dispatch_authorized)
                with self.assertRaises(FileExistsError):
                    invoke()
                changed = _receipt("second-changed", 5, failed_id="other.test")
                with self.assertRaisesRegex(ValueError, "matching assertion failures"):
                    invoke(changed)
                with self.assertRaisesRegex(ValueError, "changed source or tests"):
                    changed_inputs = cast(
                        G4InitialCandidateInputs,
                        SimpleNamespace(
                            **{
                                **common,
                                "package": SimpleNamespace(
                                    frozen_package_sha256=digest(b"different")
                                ),
                            },
                            candidate_store=second_store,
                        ),
                    )
                    invoke(inputs=changed_inputs)
                forged = sign_correction_cycle_approval(
                    approval.approval, "owner", Ed25519PrivateKey.generate()
                )
                with self.assertRaisesRegex(ValueError, "not enrolled"):
                    invoke(signed_grant=forged)
                over_budget = sign_correction_cycle_approval(
                    approval.approval.model_copy(update={"max_microusd": 50001}),
                    "owner",
                    owner,
                )
                with self.assertRaisesRegex(ValueError, "scope or budget"):
                    invoke(signed_grant=over_budget)


if __name__ == "__main__":
    unittest.main()
