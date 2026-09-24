"""Offline G4 correction triage, bounded cycle and renewed-chain regressions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import base64
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from test_reviewer_provenance import IMAGE, NOW, G4ProvenanceFixture

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import (
    G4CandidateDispatchReceipt,
    G4CandidateExecutionApproval,
    admit_candidate_execution,
    dispatch_candidate_execution,
    sign_candidate_execution_approval,
)
from mos_eisley.reviewer_correction import (
    Disposition,
    G4CorrectionCycleAdmission,
    G4CorrectionCycleApproval,
    G4CorrectionCycleCompletion,
    G4CorrectionFinding,
    G4CorrectionReservations,
    G4CorrectionReviewPolicy,
    G4CorrectionTaskBudget,
    G4CorrectionTriage,
    SignedG4CorrectionCycleApproval,
    SignedG4CorrectionTriage,
    admit_correction_cycle,
    complete_correction_cycle,
    decode_correction_artifact,
    sign_correction_cycle_approval,
    sign_correction_triage,
)
from mos_eisley.reviewer_correction_dispatch import (
    G4CorrectionChildDispatchApproval,
    G4CorrectionChildDispatchReceipt,
    G4CorrectionChildJob,
    G4CorrectionChildOffer,
    G4CorrectionChildProposal,
    G4CorrectionChildSourceFile,
    G4CorrectionChildUsage,
    SignedG4CorrectionChildDispatchApproval,
    SignedG4CorrectionChildProposal,
    creator_test_bundle_sha256,
    dispatch_correction_child,
    sign_correction_child_dispatch_approval,
    sign_correction_child_proposal,
    validate_correction_child_job,
    verify_correction_child_dispatch_receipt,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ChildAssignment,
    G4ChildResult,
    G4CreatorApproval,
    G4ReviewerCustody,
    provenance_signer,
    sign_child_assignment,
    sign_child_result,
    sign_creator_approval,
    sign_reviewer_custody,
)
from mos_eisley.reviewer_test_execution import (
    KnownControlValidationRecord,
    ReviewerTestExecutionRequest,
    build_isolated_reviewer_test_job,
    decode_execution_observation,
)
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.isolation import OfflineContainer


class _CandidateArgs(TypedDict):
    provenance: AuthenticatedG4ProvenanceRecord
    controls: KnownControlValidationRecord
    binding: ImmutableImplementationBindingRecord
    package: FrozenReviewerTestPackage
    reviewer_package_path: Path
    repository_root: Path
    implementation_root: Path
    git_executable: Path


class _CorrectionArgs(_CandidateArgs):
    first: G4CandidateDispatchReceipt
    reproduction: G4CandidateDispatchReceipt
    triage: SignedG4CorrectionTriage
    approval: SignedG4CorrectionCycleApproval
    review_policy: G4CorrectionReviewPolicy
    dispatch_store: Path
    correction_store: Path
    now: datetime


class CorrectionCycleTests(unittest.TestCase):
    def _dispatch(
        self,
        fixture: G4ProvenanceFixture,
        provenance: AuthenticatedG4ProvenanceRecord,
        store: Path,
        name: str,
        minute: int,
        *,
        failed: bool,
    ) -> G4CandidateDispatchReceipt:
        request = ReviewerTestExecutionRequest(
            execution_id=name,
            binding_record_sha256=fixture.binding.binding_record_sha256,
            container_image_id=IMAGE,
            role="candidate",
            timeout_seconds=10,
        )
        approval = sign_candidate_execution_approval(
            G4CandidateExecutionApproval(
                approval_id=name,
                policy_sha256=fixture.policy.policy_sha256,
                authenticated_provenance_sha256=provenance.record_sha256,
                known_control_record_sha256=fixture.controls.control_record_sha256,
                request_sha256=request.request_sha256,
                repository_id="fixture-repository",
                source_revision=fixture.source_revision,
                container_image_id=IMAGE,
                issued_at=NOW + timedelta(minutes=minute),
                expires_at=NOW + timedelta(minutes=minute + 15),
            ),
            "creator",
            fixture.creator_key,
        )
        kwargs: _CandidateArgs = {
            "provenance": provenance,
            "controls": fixture.controls,
            "binding": fixture.binding,
            "package": fixture.package,
            "reviewer_package_path": fixture.package_path,
            "repository_root": fixture.repository,
            "implementation_root": fixture.repository,
            "git_executable": fixture.git,
        }
        admission = admit_candidate_execution(
            approval=approval,
            request=request,
            now=NOW + timedelta(minutes=minute + 1),
            **kwargs,
        )
        job = build_isolated_reviewer_test_job(
            request, fixture.binding, fixture.package_path, fixture.repository
        )
        process = subprocess.run(
            [sys.executable, "-m", "mos_eisley.run.reviewer_test_worker"],
            input=canonical_bytes(job),
            capture_output=True,
            timeout=15,
            check=True,
        )
        observation = decode_execution_observation(process.stdout)
        if failed:
            observation = observation.model_copy(
                update={
                    "failures": 1,
                    "failed_test_ids": ("test_add.TestAdd.test_add",),
                    "suite_successful": False,
                }
            )
        container = OfflineContainer(
            Path("/usr/bin/docker"), IMAGE, fixture.root / f"{name}-lifecycle"
        )
        with patch.object(
            container, "execute", return_value=canonical_bytes(observation)
        ):
            return dispatch_candidate_execution(
                admission,
                container=container,
                dispatch_store=store,
                now=NOW + timedelta(minutes=minute + 2),
                **kwargs,
            )

    def _decision(
        self,
        fixture: G4ProvenanceFixture,
        first: G4CandidateDispatchReceipt,
        replay: G4CandidateDispatchReceipt,
        judge_key: Ed25519PrivateKey,
        *,
        disposition: Disposition = "implementation_defect",
        cycle: int = 1,
        previous_completion_sha256: str | None = None,
        minute: int = 10,
        task_budget: G4CorrectionTaskBudget | None = None,
        reserved_before: G4CorrectionReservations | None = None,
    ):
        if task_budget is None:
            task_budget = G4CorrectionTaskBudget(
                initial_assignment_sha256=fixture.assignment.artifact_sha256,
                deadline=NOW + timedelta(minutes=55),
                ceiling=G4CorrectionReservations(
                    input_tokens=20_000,
                    output_tokens=5_000,
                    tool_calls=25,
                    seconds=2_000,
                    microusd=20_000,
                ),
            )
        if reserved_before is None:
            initial = fixture.assignment.assignment
            reserved_before = G4CorrectionReservations(
                input_tokens=initial.max_input_tokens,
                output_tokens=initial.max_output_tokens,
                tool_calls=initial.max_tool_calls,
                seconds=initial.max_seconds,
                microusd=initial.max_microusd,
            )
        policy = G4CorrectionReviewPolicy(
            provenance_policy_sha256=fixture.policy.policy_sha256,
            judges=(provenance_signer("judge", judge_key.public_key()),),
            valid_from=NOW - timedelta(minutes=1),
            valid_until=NOW + timedelta(hours=1),
            operator_mode="separated",
            independent_human_review_claimed=True,
        )
        finding = G4CorrectionFinding(
            failed_test_id="test_add.TestAdd.test_add",
            disposition=disposition,
            applicable_clause_sha256=digest(b"plan clause"),
            citation_evidence_sha256=digest(b"citation evidence"),
            violation_evidence_sha256=digest(b"violation evidence"),
        )
        triage = sign_correction_triage(
            G4CorrectionTriage(
                task_id="task-one",
                cycle=cycle,
                review_policy_sha256=policy.policy_sha256,
                candidate_receipt_sha256=first.receipt_sha256,
                reproduction_receipt_sha256=replay.receipt_sha256,
                critic_review_sha256=digest(b"full critic review"),
                issued_at=NOW + timedelta(minutes=minute),
                findings=(finding,),
            ),
            "judge",
            judge_key,
        )
        approval = sign_correction_cycle_approval(
            G4CorrectionCycleApproval(
                approval_id=f"cycle-{cycle}",
                task_id="task-one",
                cycle=cycle,
                provenance_policy_sha256=fixture.policy.policy_sha256,
                triage_artifact_sha256=triage.artifact_sha256,
                previous_completion_sha256=previous_completion_sha256,
                source_revision=fixture.source_revision,
                approved_plan_sha256=fixture.plan,
                creator_test_suite_sha256=fixture.creator_tests,
                frozen_reviewer_test_package_sha256=fixture.package.frozen_package_sha256,
                task_budget=task_budget,
                reserved_before=reserved_before,
                child_signer_id="child",
                owned_paths=("src/demo/__init__.py",),
                max_input_tokens=1000,
                max_output_tokens=1000,
                max_tool_calls=5,
                max_seconds=300,
                max_microusd=1000,
                issued_at=NOW + timedelta(minutes=minute + 1),
                expires_at=NOW + timedelta(minutes=minute + 20),
            ),
            "creator",
            fixture.creator_key,
        )
        return policy, triage, approval

    def _renew(self, fixture: G4ProvenanceFixture) -> AuthenticatedG4ProvenanceRecord:
        fixture.base_revision = fixture.source_revision
        fixture.creator = sign_creator_approval(
            G4CreatorApproval(
                approval_id="creator-correction",
                policy_sha256=fixture.policy.policy_sha256,
                issued_at=NOW + timedelta(minutes=12),
                approved_plan_sha256=fixture.plan,
                creator_test_suite_sha256=fixture.creator_tests,
                public_interface_sha256s=(fixture.interface,),
                rubric_sha256=fixture.rubric,
                base_revision=fixture.base_revision,
            ),
            "creator",
            fixture.creator_key,
        )
        fixture.package = fixture._package()
        fixture.reviewer = sign_reviewer_custody(
            G4ReviewerCustody(
                custody_id="reviewer-correction",
                policy_sha256=fixture.policy.policy_sha256,
                issued_at=NOW + timedelta(minutes=13),
                frozen_reviewer_test_package_sha256=fixture.package.frozen_package_sha256,
                reviewer_test_payload_sha256=fixture.package.payload_sha256,
                creator_approval_artifact_sha256=fixture.creator.artifact_sha256,
                independent_human_review_claimed=True,
                single_operator_self_review_risk_accepted=False,
            ),
            "reviewer",
            fixture.reviewer_key,
        )
        child = fixture.policy.children[0]
        fixture.assignment = sign_child_assignment(
            G4ChildAssignment(
                assignment_id="correction-child",
                policy_sha256=fixture.policy.policy_sha256,
                issued_at=NOW + timedelta(minutes=14),
                creator_approval_artifact_sha256=fixture.creator.artifact_sha256,
                reviewer_custody_artifact_sha256=fixture.reviewer.artifact_sha256,
                frozen_reviewer_test_package_sha256=fixture.package.frozen_package_sha256,
                base_revision=fixture.base_revision,
                child_signer_id="child",
                child_public_key_sha256=child.public_key_sha256,
                child_brief_sha256=digest(b"correction brief"),
                acceptance_criteria_sha256=digest(b"correction criteria"),
                creator_test_paths=("tests/test_creator.py",),
                owned_paths=("src/demo/__init__.py",),
                max_input_tokens=1000,
                max_output_tokens=1000,
                max_tool_calls=5,
                max_seconds=300,
                max_microusd=1000,
            ),
            "creator",
            fixture.creator_key,
        )
        fixture.write(
            "src/demo/__init__.py",
            "def add(left, right):\n    return left + right  # correction\n",
        )
        fixture.commit("correction child")
        fixture.child_revision = fixture._text("rev-parse", "HEAD")
        patch_bytes = fixture._bytes(
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            fixture.base_revision,
            fixture.child_revision,
            "--",
        )
        fixture.result = sign_child_result(
            G4ChildResult(
                result_id="correction-result",
                policy_sha256=fixture.policy.policy_sha256,
                issued_at=NOW + timedelta(minutes=15),
                assignment_artifact_sha256=fixture.assignment.artifact_sha256,
                base_revision=fixture.base_revision,
                child_revision=fixture.child_revision,
                patch_sha256=digest(patch_bytes),
                patch_bytes=len(patch_bytes),
                changed_paths=("src/demo/__init__.py",),
                verification_evidence_sha256=digest(b"correction verification"),
                unresolved_issue_count=0,
            ),
            "child",
            fixture.child_key,
        )
        fixture.write("README.md", "correction integrated\n")
        fixture.commit("correction integration")
        fixture.source_revision = fixture._text("rev-parse", "HEAD")
        fixture.package_path.write_bytes(canonical_bytes(fixture.package))
        fixture.binding = fixture._binding()
        fixture.controls = fixture._controls()
        return fixture.record()

    def test_reproduced_defect_claim_and_renewed_candidate_completion(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = G4ProvenanceFixture(root)
            provenance = fixture.record()
            old_package = fixture.package
            old_binding = fixture.binding
            dispatch_store = root / "dispatch"
            dispatch_store.mkdir(mode=0o700)
            correction_store = root / "correction"
            correction_store.mkdir(mode=0o700)
            first = self._dispatch(
                fixture, provenance, dispatch_store, "first", 4, failed=True
            )
            replay = self._dispatch(
                fixture, provenance, dispatch_store, "replay", 6, failed=True
            )
            policy, triage, approval = self._decision(
                fixture, first, replay, Ed25519PrivateKey.generate()
            )
            kwargs: _CorrectionArgs = {
                "first": first,
                "reproduction": replay,
                "triage": triage,
                "approval": approval,
                "review_policy": policy,
                "provenance": provenance,
                "controls": fixture.controls,
                "binding": fixture.binding,
                "package": fixture.package,
                "reviewer_package_path": fixture.package_path,
                "repository_root": fixture.repository,
                "implementation_root": fixture.repository,
                "git_executable": fixture.git,
                "dispatch_store": dispatch_store,
                "correction_store": correction_store,
                "now": NOW + timedelta(minutes=12),
            }
            admission = admit_correction_cycle(**kwargs)
            self.assertFalse(admission.child_dispatch_authorized)
            with self.assertRaises(FileExistsError):
                admit_correction_cycle(**kwargs)
            next_provenance = self._renew(fixture)
            next_candidate = self._dispatch(
                fixture, next_provenance, dispatch_store, "corrected", 17, failed=False
            )
            artifacts = {
                "admission": admission,
                "prior-provenance": provenance,
                "prior-package": old_package,
                "prior-binding": old_binding,
                "next-receipt": next_candidate,
                "next-provenance": next_provenance,
                "next-controls": fixture.controls,
                "next-binding": fixture.binding,
            }
            for name, artifact in artifacts.items():
                (root / f"{name}.json").write_bytes(canonical_bytes(artifact))
            output = root / "completion.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "g4-complete-correction-cycle",
                            *(
                                item
                                for name in artifacts
                                for item in (f"--{name}", str(root / f"{name}.json"))
                            ),
                            "--next-reviewer-package",
                            str(fixture.package_path),
                            "--next-dispatch-store",
                            str(dispatch_store),
                            "--correction-store",
                            str(correction_store),
                            "--repository-root",
                            str(fixture.repository),
                            "--implementation-root",
                            str(fixture.repository),
                            "--git",
                            str(fixture.git),
                            "--output",
                            str(output),
                        ]
                    ),
                    0,
                )
            completion = decode_correction_artifact(
                output.read_bytes(), G4CorrectionCycleCompletion
            )
            self.assertTrue(completion.candidate_tests_passed)
            self.assertFalse(completion.acceptance_authorized)
            with self.assertRaises(FileExistsError):
                complete_correction_cycle(
                    admission,
                    correction_store=correction_store,
                    next_candidate=next_candidate,
                    next_provenance=next_provenance,
                    next_controls=fixture.controls,
                    next_binding=fixture.binding,
                    next_package=fixture.package,
                    next_reviewer_package_path=fixture.package_path,
                    next_dispatch_store=dispatch_store,
                    repository_root=fixture.repository,
                    implementation_root=fixture.repository,
                    git_executable=fixture.git,
                    prior_provenance=provenance,
                    prior_package=old_package,
                    prior_binding=old_binding,
                )

    def test_wrong_disposition_or_signature_denies_cycle(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = G4ProvenanceFixture(root)
            provenance = fixture.record()
            dispatch_store = root / "dispatch"
            dispatch_store.mkdir(mode=0o700)
            correction_store = root / "correction"
            correction_store.mkdir(mode=0o700)
            first = self._dispatch(
                fixture, provenance, dispatch_store, "first", 4, failed=True
            )
            replay = self._dispatch(
                fixture, provenance, dispatch_store, "replay", 6, failed=True
            )
            judge_key = Ed25519PrivateKey.generate()
            policy, triage, approval = self._decision(
                fixture, first, replay, judge_key, disposition="test_defect"
            )
            kwargs: _CorrectionArgs = {
                "first": first,
                "reproduction": replay,
                "triage": triage,
                "approval": approval,
                "review_policy": policy,
                "provenance": provenance,
                "controls": fixture.controls,
                "binding": fixture.binding,
                "package": fixture.package,
                "reviewer_package_path": fixture.package_path,
                "repository_root": fixture.repository,
                "implementation_root": fixture.repository,
                "git_executable": fixture.git,
                "dispatch_store": dispatch_store,
                "correction_store": correction_store,
                "now": NOW + timedelta(minutes=12),
            }
            with self.assertRaisesRegex(ValueError, "non-implementation"):
                admit_correction_cycle(**kwargs)
            good_policy, good_triage, good_approval = self._decision(
                fixture, first, replay, judge_key
            )
            forged = sign_correction_triage(
                good_triage.triage, "judge", Ed25519PrivateKey.generate()
            )
            forged_kwargs: _CorrectionArgs = {
                **kwargs,
                "triage": forged,
                "approval": good_approval,
                "review_policy": good_policy,
            }
            with self.assertRaisesRegex(ValueError, "judge is not enrolled"):
                admit_correction_cycle(**forged_kwargs)
            exhausted_budget = good_approval.approval.task_budget.model_copy(
                update={
                    "ceiling": G4CorrectionReservations(
                        input_tokens=10_000,
                        output_tokens=2_000,
                        tool_calls=10,
                        seconds=600,
                        microusd=10_000,
                    )
                }
            )
            exhausted = sign_correction_cycle_approval(
                good_approval.approval.model_copy(
                    update={"task_budget": exhausted_budget}
                ),
                "creator",
                fixture.creator_key,
            )
            exhausted_kwargs: _CorrectionArgs = {
                **kwargs,
                "triage": good_triage,
                "approval": exhausted,
                "review_policy": good_policy,
            }
            with self.assertRaisesRegex(ValueError, "aggregate task allowance"):
                admit_correction_cycle(**exhausted_kwargs)
            with self.assertRaises(ValidationError):
                G4CorrectionCycleApproval.model_validate(
                    {
                        **good_approval.approval.model_dump(),
                        "cycle": 3,
                    }
                )

    def test_second_cycle_requires_persisted_failed_completion(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = G4ProvenanceFixture(root)
            provenance = fixture.record()
            old_package = fixture.package
            old_binding = fixture.binding
            dispatch_store = root / "dispatch"
            dispatch_store.mkdir(mode=0o700)
            correction_store = root / "correction"
            correction_store.mkdir(mode=0o700)
            first = self._dispatch(
                fixture, provenance, dispatch_store, "first", 4, failed=True
            )
            replay = self._dispatch(
                fixture, provenance, dispatch_store, "replay", 6, failed=True
            )
            judge_key = Ed25519PrivateKey.generate()
            policy, triage, approval = self._decision(fixture, first, replay, judge_key)
            admission = admit_correction_cycle(
                first=first,
                reproduction=replay,
                triage=triage,
                approval=approval,
                review_policy=policy,
                provenance=provenance,
                controls=fixture.controls,
                binding=fixture.binding,
                package=fixture.package,
                reviewer_package_path=fixture.package_path,
                repository_root=fixture.repository,
                implementation_root=fixture.repository,
                git_executable=fixture.git,
                dispatch_store=dispatch_store,
                correction_store=correction_store,
                now=NOW + timedelta(minutes=12),
            )
            next_provenance = self._renew(fixture)
            next_failed = self._dispatch(
                fixture,
                next_provenance,
                dispatch_store,
                "next-failed",
                17,
                failed=True,
            )
            completion = complete_correction_cycle(
                admission,
                correction_store=correction_store,
                next_candidate=next_failed,
                next_provenance=next_provenance,
                next_controls=fixture.controls,
                next_binding=fixture.binding,
                next_package=fixture.package,
                next_reviewer_package_path=fixture.package_path,
                next_dispatch_store=dispatch_store,
                repository_root=fixture.repository,
                implementation_root=fixture.repository,
                git_executable=fixture.git,
                prior_provenance=provenance,
                prior_package=old_package,
                prior_binding=old_binding,
            )
            self.assertFalse(completion.candidate_tests_passed)
            second_replay = self._dispatch(
                fixture,
                next_provenance,
                dispatch_store,
                "second-replay",
                20,
                failed=True,
            )
            second_policy, second_triage, second_approval = self._decision(
                fixture,
                next_failed,
                second_replay,
                judge_key,
                cycle=2,
                previous_completion_sha256=completion.completion_sha256,
                minute=24,
                task_budget=approval.approval.task_budget,
                reserved_before=G4CorrectionReservations(
                    input_tokens=11_000,
                    output_tokens=3_000,
                    tool_calls=15,
                    seconds=900,
                    microusd=11_000,
                ),
            )
            second_kwargs: _CorrectionArgs = {
                "first": next_failed,
                "reproduction": second_replay,
                "triage": second_triage,
                "approval": second_approval,
                "review_policy": second_policy,
                "provenance": next_provenance,
                "controls": fixture.controls,
                "binding": fixture.binding,
                "package": fixture.package,
                "reviewer_package_path": fixture.package_path,
                "repository_root": fixture.repository,
                "implementation_root": fixture.repository,
                "git_executable": fixture.git,
                "dispatch_store": dispatch_store,
                "correction_store": correction_store,
                "now": NOW + timedelta(minutes=26),
            }
            with self.assertRaisesRegex(ValueError, "first correction cycle"):
                admit_correction_cycle(**second_kwargs)
            forged = completion.model_copy(
                update={"next_candidate_receipt_sha256": "f" * 64}
            )
            with self.assertRaisesRegex(ValueError, "completion differs"):
                admit_correction_cycle(**second_kwargs, previous=forged)
            second = admit_correction_cycle(**second_kwargs, previous=completion)
            self.assertEqual(second.approval.approval.cycle, 2)
            self.assertFalse(second.acceptance_authorized)

    def test_cli_admits_canonical_artifacts_and_rejects_repo_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = G4ProvenanceFixture(root)
            provenance = fixture.record()
            dispatch_store = root / "dispatch"
            dispatch_store.mkdir(mode=0o700)
            correction_store = root / "correction"
            correction_store.mkdir(mode=0o700)
            first = self._dispatch(
                fixture, provenance, dispatch_store, "first", 4, failed=True
            )
            replay = self._dispatch(
                fixture, provenance, dispatch_store, "replay", 6, failed=True
            )
            policy, triage, approval = self._decision(
                fixture, first, replay, Ed25519PrivateKey.generate()
            )
            artifacts = {
                "first": first,
                "reproduction": replay,
                "triage": triage,
                "approval": approval,
                "policy": policy,
                "provenance": provenance,
                "controls": fixture.controls,
                "binding": fixture.binding,
            }
            for name, artifact in artifacts.items():
                (root / f"{name}.json").write_bytes(canonical_bytes(artifact))
            args = [
                "g4-admit-correction-cycle",
                "--first-receipt",
                str(root / "first.json"),
                "--reproduction-receipt",
                str(root / "reproduction.json"),
                "--triage",
                str(root / "triage.json"),
                "--approval",
                str(root / "approval.json"),
                "--review-policy",
                str(root / "policy.json"),
                "--provenance",
                str(root / "provenance.json"),
                "--controls",
                str(root / "controls.json"),
                "--binding",
                str(root / "binding.json"),
                "--reviewer-package",
                str(fixture.package_path),
                "--dispatch-store",
                str(dispatch_store),
                "--correction-store",
                str(correction_store),
                "--repository-root",
                str(fixture.repository),
                "--implementation-root",
                str(fixture.repository),
                "--git",
                str(fixture.git),
                "--output",
                str(root / "admission.json"),
            ]
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main([*args[:-1], str(fixture.repository / "bad.json")]), 2
                )
            self.assertFalse((fixture.repository / "bad.json").exists())
            with (
                patch("mos_eisley.reviewer_correction.datetime") as clock,
                redirect_stdout(io.StringIO()),
            ):
                clock.now.return_value = NOW + timedelta(minutes=12)
                self.assertEqual(main(args), 0)
            admission = decode_correction_artifact(
                (root / "admission.json").read_bytes(), G4CorrectionCycleAdmission
            )
            self.assertEqual(admission.approval.approval.cycle, 1)

    def test_contained_child_dispatch_spends_once_and_never_writes_host(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = G4ProvenanceFixture(root)
            provenance = fixture.record()
            candidate_store = root / "candidate"
            candidate_store.mkdir(mode=0o700)
            correction_store = root / "correction"
            correction_store.mkdir(mode=0o700)
            child_store = root / "child"
            child_store.mkdir(mode=0o700)
            first = self._dispatch(
                fixture, provenance, candidate_store, "first", 4, failed=True
            )
            replay = self._dispatch(
                fixture, provenance, candidate_store, "replay", 6, failed=True
            )
            policy, triage, grant = self._decision(
                fixture, first, replay, Ed25519PrivateKey.generate()
            )
            admission = admit_correction_cycle(
                first=first,
                reproduction=replay,
                triage=triage,
                approval=grant,
                review_policy=policy,
                provenance=provenance,
                controls=fixture.controls,
                binding=fixture.binding,
                package=fixture.package,
                reviewer_package_path=fixture.package_path,
                repository_root=fixture.repository,
                implementation_root=fixture.repository,
                git_executable=fixture.git,
                dispatch_store=candidate_store,
                correction_store=correction_store,
                now=NOW + timedelta(minutes=12),
            )
            brief = "Correct the reproduced addition defect."
            criteria = "Preserve creator tests and change only the owned source file."
            creator_test_content = (
                fixture.repository / "tests/test_creator.py"
            ).read_bytes()
            creator_test_view = (
                G4CorrectionChildSourceFile(
                    path="tests/test_creator.py",
                    content_base64=base64.b64encode(creator_test_content).decode(),
                    content_sha256=digest(creator_test_content),
                ),
            )
            order = sign_correction_child_dispatch_approval(
                G4CorrectionChildDispatchApproval(
                    dispatch_id="correction-child-one",
                    admission_sha256=admission.admission_sha256,
                    source_revision=fixture.source_revision,
                    container_image_id=IMAGE,
                    child_signer_id="child",
                    brief_sha256=digest(brief.encode()),
                    acceptance_criteria_sha256=digest(criteria.encode()),
                    creator_test_suite_sha256=fixture.creator_tests,
                    creator_test_bundle_sha256=creator_test_bundle_sha256(
                        creator_test_view
                    ),
                    owned_paths=("src/demo/__init__.py",),
                    issued_at=NOW + timedelta(minutes=12),
                    expires_at=NOW + timedelta(minutes=25),
                ),
                "creator",
                fixture.creator_key,
            )

            class Generator:
                async def generate(
                    self, offer: G4CorrectionChildOffer
                ) -> SignedG4CorrectionChildProposal:
                    replacement = (
                        b"def add(left, right):\n    return left + right  # corrected\n"
                    )
                    return sign_correction_child_proposal(
                        G4CorrectionChildProposal(
                            offer_sha256=offer.offer_sha256,
                            replacements=(
                                G4CorrectionChildSourceFile(
                                    path="src/demo/__init__.py",
                                    content_base64=base64.b64encode(
                                        replacement
                                    ).decode(),
                                    content_sha256=digest(replacement),
                                ),
                            ),
                            usage=G4CorrectionChildUsage(
                                input_tokens=20,
                                output_tokens=30,
                                tool_calls=1,
                                seconds=1,
                                microusd=3,
                            ),
                            unresolved_issue_count=0,
                        ),
                        "child",
                        fixture.child_key,
                    )

            def execute(
                _args: tuple[str, ...], payload: bytes, timeout: float
            ) -> bytes:
                job = G4CorrectionChildJob.model_validate_json(payload)
                self.assertEqual(job.offer.brief, brief)
                self.assertEqual(job.offer.creator_test_files, creator_test_view)
                self.assertGreater(timeout, 0)
                return subprocess.run(
                    [sys.executable, "-m", "mos_eisley.run.reviewer_correction_child"],
                    input=payload,
                    capture_output=True,
                    timeout=10,
                    check=True,
                ).stdout

            container = OfflineContainer(
                Path("/usr/bin/docker"), IMAGE, root / "lifecycle"
            )

            def run_dispatch(
                dispatch_order: SignedG4CorrectionChildDispatchApproval = order,
                plan: str = "approved plan",
            ) -> G4CorrectionChildDispatchReceipt:
                return asyncio.run(
                    dispatch_correction_child(
                        admission=admission,
                        approval=dispatch_order,
                        first=first,
                        provenance=provenance,
                        controls=fixture.controls,
                        binding=fixture.binding,
                        package=fixture.package,
                        reviewer_package_path=fixture.package_path,
                        repository_root=fixture.repository,
                        implementation_root=fixture.repository,
                        git_executable=fixture.git,
                        candidate_dispatch_store=candidate_store,
                        correction_store=correction_store,
                        child_dispatch_store=child_store,
                        approved_plan=plan,
                        brief=brief,
                        acceptance_criteria=criteria,
                        generator=Generator(),
                        container=container,
                        now=NOW + timedelta(minutes=13),
                    )
                )

            before = fixture._text("rev-parse", "HEAD")
            with self.assertRaisesRegex(ValueError, "approved cycle"):
                run_dispatch(plan="unapproved plan")
            self.assertEqual(tuple(child_store.iterdir()), ())
            mismatched_tests = sign_correction_child_dispatch_approval(
                order.approval.model_copy(
                    update={"creator_test_bundle_sha256": digest(b"wrong test view")}
                ),
                "creator",
                fixture.creator_key,
            )
            with self.assertRaisesRegex(ValueError, "test view differs"):
                run_dispatch(mismatched_tests)
            self.assertEqual(tuple(child_store.iterdir()), ())
            with patch.object(container, "execute", side_effect=execute):
                receipt = run_dispatch()
            verify_correction_child_dispatch_receipt(
                receipt,
                admission=admission,
                provenance=provenance,
                correction_store=correction_store,
                child_dispatch_store=child_store,
            )
            self.assertEqual(receipt.execution.changed_paths, ("src/demo/__init__.py",))
            self.assertFalse(receipt.repository_write_authorized)
            self.assertEqual(fixture._text("rev-parse", "HEAD"), before)
            self.assertEqual(fixture._text("status", "--porcelain"), "")
            tampered = receipt.model_copy(
                update={
                    "signed_proposal": receipt.signed_proposal.model_copy(
                        update={"signature": order.signature}
                    )
                }
            )
            with self.assertRaises(ValueError):
                verify_correction_child_dispatch_receipt(
                    tampered,
                    admission=admission,
                    provenance=provenance,
                    correction_store=correction_store,
                    child_dispatch_store=child_store,
                )
            with self.assertRaises(FileExistsError):
                run_dispatch()


class CorrectionChildJobTests(unittest.TestCase):
    def test_scope_noop_budget_and_encoding_are_rejected(self) -> None:
        source = b"original\n"
        changed = b"corrected\n"
        original = G4CorrectionChildSourceFile(
            path="src/demo.py",
            content_base64=base64.b64encode(source).decode(),
            content_sha256=digest(source),
        )
        offer = G4CorrectionChildOffer(
            dispatch_approval_sha256=digest(b"approval"),
            correction_admission_sha256=digest(b"admission"),
            source_revision="a" * 40,
            approved_plan="Approved plan",
            brief="Fix the defect",
            acceptance_criteria="Preserve tests",
            source_files=(original,),
            creator_test_files=(
                G4CorrectionChildSourceFile(
                    path="tests/test_creator.py",
                    content_base64=base64.b64encode(b"assert True\n").decode(),
                    content_sha256=digest(b"assert True\n"),
                ),
            ),
            max_input_tokens=100,
            max_output_tokens=100,
            max_tool_calls=2,
            max_seconds=10,
            max_microusd=10,
        )
        usage = G4CorrectionChildUsage(
            input_tokens=5,
            output_tokens=5,
            tool_calls=1,
            seconds=1,
            microusd=1,
        )
        replacement = G4CorrectionChildSourceFile(
            path="src/demo.py",
            content_base64=base64.b64encode(changed).decode(),
            content_sha256=digest(changed),
        )
        child_key = Ed25519PrivateKey.generate()

        def job(
            replacement_file: G4CorrectionChildSourceFile,
            actual_usage: G4CorrectionChildUsage = usage,
        ) -> G4CorrectionChildJob:
            proposal = G4CorrectionChildProposal(
                offer_sha256=offer.offer_sha256,
                replacements=(replacement_file,),
                usage=actual_usage,
                unresolved_issue_count=0,
            )
            return G4CorrectionChildJob(
                offer=offer,
                signed_proposal=sign_correction_child_proposal(
                    proposal, "child", child_key
                ),
            )

        self.assertEqual(
            validate_correction_child_job(job(replacement)).changed_paths,
            ("src/demo.py",),
        )
        noncanonical = subprocess.run(
            [sys.executable, "-m", "mos_eisley.run.reviewer_correction_child"],
            input=canonical_bytes(job(replacement)) + b"\n",
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(noncanonical.returncode, 2)
        self.assertEqual(noncanonical.stdout, b"")
        with self.assertRaisesRegex(ValueError, "no valid owned-path change"):
            validate_correction_child_job(job(original))
        with self.assertRaisesRegex(ValueError, "no valid owned-path change"):
            validate_correction_child_job(
                job(replacement.model_copy(update={"path": "tests/test_creator.py"}))
            )
        with self.assertRaisesRegex(ValueError, "allowance"):
            validate_correction_child_job(
                job(replacement, usage.model_copy(update={"microusd": 11}))
            )
        with self.assertRaises(ValueError):
            G4CorrectionChildSourceFile(
                path="../escape.py",
                content_base64=base64.b64encode(source).decode(),
                content_sha256=digest(source),
            )
        with self.assertRaises(ValueError):
            G4CorrectionChildSourceFile(
                path="src/demo.py",
                content_base64="*",
                content_sha256=digest(b""),
            )
