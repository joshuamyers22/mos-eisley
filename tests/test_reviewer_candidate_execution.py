"""G4 candidate approval, current Git admission and one-use offline dispatch."""

from __future__ import annotations

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from test_reviewer_provenance import IMAGE, NOW, G4ProvenanceFixture

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_candidate_execution import (
    G4CandidateAdmissionRecord,
    G4CandidateDispatchReceipt,
    G4CandidateExecutionApproval,
    SignedG4CandidateExecutionApproval,
    admit_candidate_execution,
    decode_candidate_artifact,
    dispatch_candidate_execution,
    sign_candidate_execution_approval,
    verify_candidate_dispatch_receipt,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
)
from mos_eisley.reviewer_provenance import AuthenticatedG4ProvenanceRecord
from mos_eisley.reviewer_test_execution import (
    IsolatedReviewerTestObservation,
    KnownControlValidationRecord,
    ReviewerTestExecutionRequest,
    build_isolated_reviewer_test_job,
    decode_execution_observation,
    run_isolated_reviewer_tests,
)
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.isolation import OfflineContainer


class _CaseInputs(TypedDict):
    provenance: AuthenticatedG4ProvenanceRecord
    controls: KnownControlValidationRecord
    binding: ImmutableImplementationBindingRecord
    package: FrozenReviewerTestPackage
    reviewer_package_path: Path
    repository_root: Path
    implementation_root: Path
    git_executable: Path


class CandidateExecutionTests(unittest.TestCase):
    def _case(
        self, root: Path
    ) -> tuple[
        G4ProvenanceFixture,
        SignedG4CandidateExecutionApproval,
        ReviewerTestExecutionRequest,
        _CaseInputs,
    ]:
        fixture = G4ProvenanceFixture(root)
        provenance = fixture.record()
        request = ReviewerTestExecutionRequest(
            execution_id="candidate-once",
            binding_record_sha256=fixture.binding.binding_record_sha256,
            container_image_id=IMAGE,
            role="candidate",
            timeout_seconds=10,
        )
        payload = G4CandidateExecutionApproval(
            approval_id="candidate-approval",
            policy_sha256=fixture.policy.policy_sha256,
            authenticated_provenance_sha256=provenance.record_sha256,
            known_control_record_sha256=fixture.controls.control_record_sha256,
            request_sha256=request.request_sha256,
            repository_id="fixture-repository",
            source_revision=fixture.source_revision,
            container_image_id=IMAGE,
            issued_at=NOW + timedelta(minutes=4),
            expires_at=NOW + timedelta(minutes=20),
        )
        approval = sign_candidate_execution_approval(
            payload, "creator", fixture.creator_key
        )
        kwargs: _CaseInputs = {
            "provenance": provenance,
            "controls": fixture.controls,
            "binding": fixture.binding,
            "package": fixture.package,
            "reviewer_package_path": fixture.package_path,
            "repository_root": fixture.repository,
            "implementation_root": fixture.repository,
            "git_executable": fixture.git,
        }
        return fixture, approval, request, kwargs

    def _admit(
        self,
        approval: SignedG4CandidateExecutionApproval,
        request: ReviewerTestExecutionRequest,
        kwargs: _CaseInputs,
    ) -> G4CandidateAdmissionRecord:
        return admit_candidate_execution(
            approval=approval,
            request=request,
            now=NOW + timedelta(minutes=5),
            **kwargs,
        )

    def _observation(
        self,
        fixture: G4ProvenanceFixture,
        request: ReviewerTestExecutionRequest,
    ) -> IsolatedReviewerTestObservation:
        job = build_isolated_reviewer_test_job(
            request,
            fixture.binding,
            fixture.package_path,
            fixture.repository,
        )
        process = subprocess.run(
            [sys.executable, "-m", "mos_eisley.run.reviewer_test_worker"],
            input=canonical_bytes(job),
            capture_output=True,
            timeout=15,
            check=False,
        )
        if process.returncode:
            child = (
                Path(__file__).parents[1] / "src/mos_eisley/run/reviewer_test_child.py"
            )
            detail = subprocess.run(
                [sys.executable, "-I", str(child)],
                input=canonical_bytes(job),
                capture_output=True,
                timeout=15,
                check=False,
            )
            self.fail(detail.stderr.decode())
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        return decode_execution_observation(process.stdout)

    def test_signed_admission_dispatch_and_replay_denial(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture, approval, request, kwargs = self._case(root)
            admission = self._admit(approval, request, kwargs)
            self.assertEqual(
                decode_candidate_artifact(
                    canonical_bytes(admission), G4CandidateAdmissionRecord
                ),
                admission,
            )
            store = root / "dispatch-store"
            store.mkdir(mode=0o700)
            container = OfflineContainer(
                Path("/usr/bin/docker"), IMAGE, root / "lifecycle"
            )
            observation = self._observation(fixture, request)
            with patch.object(
                container, "execute", return_value=canonical_bytes(observation)
            ) as execute:
                receipt = dispatch_candidate_execution(
                    admission,
                    container=container,
                    dispatch_store=store,
                    now=NOW + timedelta(minutes=6),
                    **kwargs,
                )
            self.assertEqual(execute.call_count, 1)
            self.assertTrue(receipt.candidate_tests_passed)
            self.assertFalse(receipt.acceptance_authorized)
            self.assertEqual(
                decode_candidate_artifact(
                    canonical_bytes(receipt), G4CandidateDispatchReceipt
                ),
                receipt,
            )
            verify_candidate_dispatch_receipt(receipt, dispatch_store=store, **kwargs)
            claim = store / f"{approval.artifact_sha256}.claim"
            self.assertEqual(claim.read_bytes(), canonical_bytes(admission))
            with self.assertRaises(FileExistsError):
                dispatch_candidate_execution(
                    admission,
                    container=container,
                    dispatch_store=store,
                    now=NOW + timedelta(minutes=7),
                    **kwargs,
                )
            claim.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "claim differs"):
                verify_candidate_dispatch_receipt(
                    receipt, dispatch_store=store, **kwargs
                )

    def test_unsigned_generic_runner_cannot_dispatch_candidate(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture, _approval, request, _kwargs = self._case(root)
            container = OfflineContainer(
                Path("/usr/bin/docker"), IMAGE, root / "lifecycle"
            )
            with (
                patch.object(container, "execute") as execute,
                self.assertRaisesRegex(ValueError, "requires authenticated"),
            ):
                run_isolated_reviewer_tests(
                    request,
                    fixture.binding,
                    fixture.package_path,
                    fixture.repository,
                    container,
                )
            execute.assert_not_called()

    def test_signature_scope_window_and_stale_git_fail_before_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture, approval, request, kwargs = self._case(root)
            bad_key = Ed25519PrivateKey.generate()
            forged = sign_candidate_execution_approval(
                approval.approval, "creator", bad_key
            )
            with self.assertRaisesRegex(ValueError, "signer is not enrolled"):
                self._admit(forged, request, kwargs)
            with self.assertRaisesRegex(ValueError, "valid window"):
                admit_candidate_execution(
                    approval=approval,
                    request=request,
                    now=NOW + timedelta(minutes=21),
                    **kwargs,
                )
            altered_request = request.model_copy(update={"execution_id": "other"})
            with self.assertRaisesRegex(ValueError, "exact current inputs"):
                self._admit(approval, altered_request, kwargs)
            fixture.write("src/demo/__init__.py", "def add(left, right): return 0\n")
            with self.assertRaises(ValueError):
                self._admit(approval, request, kwargs)

    def test_candidate_approval_cannot_be_extended_or_recoded(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture, approval, _request, _kwargs = self._case(root)
            with self.assertRaises(ValidationError):
                G4CandidateExecutionApproval.model_validate(
                    {
                        **approval.approval.model_dump(),
                        "candidate_execution_authorized": False,
                    }
                )
            with self.assertRaises(ValidationError):
                G4CandidateExecutionApproval.model_validate(
                    {
                        **approval.approval.model_dump(),
                        "expires_at": NOW + timedelta(hours=30),
                    }
                )
            raw = canonical_bytes(approval).replace(
                b'"approval_id":"candidate-approval"',
                b'"approval_id":"candidate-approval","approval_id":"other"',
            )
            with self.assertRaises(ValueError):
                decode_candidate_artifact(raw, SignedG4CandidateExecutionApproval)

    def test_failed_candidate_is_retained_without_acceptance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture, approval, request, kwargs = self._case(root)
            admission = self._admit(approval, request, kwargs)
            store = root / "dispatch-store"
            store.mkdir(mode=0o700)
            container = OfflineContainer(
                Path("/usr/bin/docker"), IMAGE, root / "lifecycle"
            )
            observation = self._observation(fixture, request)
            failed = observation.model_copy(
                update={"failures": 1, "suite_successful": False}
            )
            with patch.object(
                container, "execute", return_value=canonical_bytes(failed)
            ):
                receipt = dispatch_candidate_execution(
                    admission,
                    container=container,
                    dispatch_store=store,
                    now=NOW + timedelta(minutes=6),
                    **kwargs,
                )
            self.assertFalse(receipt.candidate_tests_passed)
            self.assertFalse(receipt.correction_authorized)
            self.assertFalse(receipt.acceptance_authorized)

    def test_post_run_source_drift_fails_and_spends_approval(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture, approval, request, kwargs = self._case(root)
            admission = self._admit(approval, request, kwargs)
            store = root / "dispatch-store"
            store.mkdir(mode=0o700)
            container = OfflineContainer(
                Path("/usr/bin/docker"), IMAGE, root / "lifecycle"
            )
            observation = self._observation(fixture, request)

            def drift(*_args: object, **_kwargs: object) -> bytes:
                fixture.write(
                    "src/demo/__init__.py", "def add(left, right): return 0\n"
                )
                return canonical_bytes(observation)

            with (
                patch.object(container, "execute", side_effect=drift),
                self.assertRaises(ValueError),
            ):
                dispatch_candidate_execution(
                    admission,
                    container=container,
                    dispatch_store=store,
                    now=NOW + timedelta(minutes=6),
                    **kwargs,
                )
            self.assertTrue((store / f"{approval.artifact_sha256}.claim").exists())

    def test_private_store_required_before_any_execution(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture, approval, request, kwargs = self._case(root)
            admission = self._admit(approval, request, kwargs)
            store = root / "dispatch-store"
            store.mkdir(mode=0o755)
            container = OfflineContainer(
                Path("/usr/bin/docker"), IMAGE, root / "lifecycle"
            )
            with (
                patch.object(container, "execute") as execute,
                self.assertRaisesRegex(ValueError, "mode 0700"),
            ):
                dispatch_candidate_execution(
                    admission,
                    container=container,
                    dispatch_store=store,
                    now=NOW + timedelta(minutes=6),
                    **kwargs,
                )
            execute.assert_not_called()

    def test_cli_check_dispatch_and_verify_with_offline_worker(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture, approval, request, kwargs = self._case(root)
            (root / "approval.json").write_bytes(canonical_bytes(approval))
            (root / "request.json").write_bytes(canonical_bytes(request))
            (root / "provenance.json").write_bytes(
                canonical_bytes(kwargs["provenance"])
            )
            (root / "controls.json").write_bytes(canonical_bytes(fixture.controls))
            (root / "binding.json").write_bytes(canonical_bytes(fixture.binding))
            common = [
                "--provenance",
                str(root / "provenance.json"),
                "--controls",
                str(root / "controls.json"),
                "--binding",
                str(root / "binding.json"),
                "--reviewer-package",
                str(fixture.package_path),
                "--repository-root",
                str(fixture.repository),
                "--implementation-root",
                str(fixture.repository),
                "--git",
                str(fixture.git),
            ]
            admission_path = root / "admission.json"
            receipt_path = root / "receipt.json"
            store = root / "dispatch-store"
            store.mkdir(mode=0o700)
            observation = self._observation(fixture, request)
            with (
                patch("mos_eisley.reviewer_candidate_execution.datetime") as clock,
                redirect_stdout(io.StringIO()),
            ):
                clock.now.return_value = NOW + timedelta(minutes=5)
                self.assertEqual(
                    main(
                        [
                            "g4-check-candidate-execution",
                            *common,
                            "--approval",
                            str(root / "approval.json"),
                            "--request",
                            str(root / "request.json"),
                            "--output",
                            str(admission_path),
                        ]
                    ),
                    0,
                )
                clock.now.return_value = NOW + timedelta(minutes=6)
                with patch.object(
                    OfflineContainer,
                    "execute",
                    return_value=canonical_bytes(observation),
                ):
                    self.assertEqual(
                        main(
                            [
                                "g4-dispatch-candidate-execution",
                                *common,
                                "--admission",
                                str(admission_path),
                                "--docker",
                                "/usr/bin/docker",
                                "--dispatch-store",
                                str(store),
                                "--lifecycle-root",
                                str(root / "lifecycle"),
                                "--output",
                                str(receipt_path),
                            ]
                        ),
                        0,
                    )
                self.assertEqual(
                    main(
                        [
                            "g4-verify-candidate-execution",
                            *common,
                            "--receipt",
                            str(receipt_path),
                            "--dispatch-store",
                            str(store),
                        ]
                    ),
                    0,
                )


if __name__ == "__main__":
    unittest.main()
