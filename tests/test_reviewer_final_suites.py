"""Offline G4 final creator/reviewer whole-suite admission and execution."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from pydantic import ValidationError
from test_reviewer_candidate_execution import CandidateExecutionTests
from test_reviewer_provenance import IMAGE, NOW, G4ProvenanceFixture

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import dispatch_candidate_execution
from mos_eisley.reviewer_final_suites import (
    G4FinalWholeSuiteApproval,
    G4FinalWholeSuiteReceipt,
    SignedG4FinalWholeSuiteApproval,
    _verify_creator_package,
    decode_final_suite_artifact,
    run_final_whole_suites,
    sign_final_whole_suite_approval,
    verify_final_whole_suite_receipt,
)
from mos_eisley.reviewer_test_execution import (
    IsolatedReviewerTestObservation,
    ReviewerTestExecutionRequest,
    decode_execution_observation,
)
from mos_eisley.reviewer_test_package import (
    BlindReviewReference,
    FrozenReviewerTestPackage,
    FrozenTestFile,
    ReviewerTestPackageManifest,
    ReviewerTestPackagePayload,
    TestCollectionContract,
    TestFileDeclaration,
)
from mos_eisley.run.isolation import OfflineContainer


class FinalWholeSuiteTests(unittest.TestCase):
    fixture: G4ProvenanceFixture

    def _creator_package(
        self, fixture: G4ProvenanceFixture
    ) -> FrozenReviewerTestPackage:
        source = (fixture.repository / "tests/test_creator.py").read_bytes()
        references = tuple(
            sorted(
                (
                    BlindReviewReference(
                        kind="approved_plan",
                        reference_id="plan",
                        content_sha256=fixture.plan,
                        bytes=13,
                    ),
                    BlindReviewReference(
                        kind="creator_approval",
                        reference_id="creator",
                        content_sha256=fixture.creator.artifact_sha256,
                        bytes=len(canonical_bytes(fixture.creator)),
                    ),
                    BlindReviewReference(
                        kind="interface",
                        reference_id="interface",
                        content_sha256=fixture.interface,
                        bytes=16,
                    ),
                    BlindReviewReference(
                        kind="rubric",
                        reference_id="rubric",
                        content_sha256=fixture.rubric,
                        bytes=6,
                    ),
                ),
                key=lambda item: (item.kind, item.reference_id),
            )
        )
        declaration = TestFileDeclaration(
            path="tests/test_creator.py",
            kind="test",
            media_type="text/x-python",
            content_sha256=digest(source),
            bytes=len(source),
        )
        manifest = ReviewerTestPackageManifest(
            package_id="creator-final-suite",
            references=references,
            collection=TestCollectionContract(
                start_directory="tests",
                top_level_directory="tests",
                expected_collected_tests=1,
                expected_executed_tests=1,
            ),
            files=(declaration,),
        )
        payload = ReviewerTestPackagePayload(
            manifest=manifest,
            files=(
                FrozenTestFile(
                    declaration=declaration,
                    content_base64=base64.b64encode(source).decode("ascii"),
                ),
            ),
        )
        return FrozenReviewerTestPackage(
            payload=payload, payload_sha256=digest(canonical_bytes(payload))
        )

    def _case(self, root: Path) -> tuple[dict[str, Any], OfflineContainer]:
        helper = CandidateExecutionTests()
        fixture, candidate_approval, candidate_request, candidate_inputs = helper._case(
            root
        )
        self.fixture = fixture
        admission = helper._admit(
            candidate_approval, candidate_request, candidate_inputs
        )
        candidate_store = root / "candidate-store"
        final_store = root / "final-store"
        candidate_store.mkdir(mode=0o700)
        final_store.mkdir(mode=0o700)
        container = OfflineContainer(Path("/usr/bin/docker"), IMAGE, root / "lifecycle")
        with patch.object(
            container,
            "execute",
            return_value=canonical_bytes(
                helper._observation(fixture, candidate_request)
            ),
        ):
            candidate = dispatch_candidate_execution(
                admission,
                container=container,
                dispatch_store=candidate_store,
                now=NOW + timedelta(minutes=6),
                **candidate_inputs,
            )
        creator_package = self._creator_package(fixture)
        creator_path = root / "creator-package.json"
        creator_path.write_bytes(canonical_bytes(creator_package))
        creator_request = ReviewerTestExecutionRequest(
            execution_id="creator-final-once",
            binding_record_sha256=fixture.binding.binding_record_sha256,
            container_image_id=IMAGE,
            role="candidate",
            timeout_seconds=10,
        )
        reviewer_request = ReviewerTestExecutionRequest(
            execution_id="reviewer-final-once",
            binding_record_sha256=fixture.binding.binding_record_sha256,
            container_image_id=IMAGE,
            role="candidate",
            timeout_seconds=10,
        )
        provenance = candidate_inputs["provenance"]
        approval = sign_final_whole_suite_approval(
            G4FinalWholeSuiteApproval(
                suite_id="final-whole-suite-once",
                policy_sha256=fixture.policy.policy_sha256,
                provenance_sha256=provenance.record_sha256,
                candidate_receipt_sha256=candidate.receipt_sha256,
                source_revision=fixture.source_revision,
                creator_test_suite_sha256=fixture.creator_tests,
                creator_package_sha256=creator_package.frozen_package_sha256,
                reviewer_package_sha256=fixture.package.frozen_package_sha256,
                reviewer_binding_sha256=fixture.binding.binding_record_sha256,
                creator_request_sha256=creator_request.request_sha256,
                reviewer_request_sha256=reviewer_request.request_sha256,
                container_image_id=IMAGE,
                issued_at=NOW + timedelta(minutes=7),
                expires_at=NOW + timedelta(minutes=20),
            ),
            "creator",
            fixture.creator_key,
        )
        inputs: dict[str, Any] = {
            "approval": approval,
            "candidate": candidate,
            "provenance": provenance,
            "controls": fixture.controls,
            "creator_request": creator_request,
            "reviewer_request": reviewer_request,
            "reviewer_binding": fixture.binding,
            "creator_package": creator_package,
            "reviewer_package": fixture.package,
            "creator_package_path": creator_path,
            "reviewer_package_path": fixture.package_path,
            "repository_root": fixture.repository,
            "implementation_root": fixture.repository,
            "git_executable": fixture.git,
            "candidate_dispatch_store": candidate_store,
            "final_dispatch_store": final_store,
            "now": NOW + timedelta(minutes=8),
        }
        return inputs, container

    @staticmethod
    def _worker_response(payload: bytes) -> bytes:
        module = (
            "mos_eisley.run.creator_test_worker"
            if json.loads(payload)["kind"] == "isolated_creator_test_job"
            else "mos_eisley.run.reviewer_test_worker"
        )
        process = subprocess.run(
            [sys.executable, "-m", module],
            input=payload,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if process.returncode:
            raise AssertionError(process.stderr.decode())
        return process.stdout

    def _execute_worker(
        self, _argv: tuple[str, ...], payload: bytes, **_kwargs: object
    ) -> bytes:
        return self._worker_response(payload)

    def _class_execute(
        self,
        _container: OfflineContainer,
        _argv: tuple[str, ...],
        payload: bytes,
        **_kwargs: object,
    ) -> bytes:
        return self._worker_response(payload)

    def test_two_real_suites_pass_and_replay_is_denied(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, container = self._case(Path(directory))
            with patch.object(
                container,
                "execute",
                side_effect=self._execute_worker,
            ) as execute:
                receipt = run_final_whole_suites(**inputs, container=container)
            self.assertEqual(execute.call_count, 2)
            self.assertTrue(receipt.final_suites_passed)
            self.assertFalse(receipt.acceptance_authorized)
            self.assertEqual(receipt.creator_execution.observation.executed_tests, 1)
            self.assertEqual(receipt.reviewer_execution.observation.executed_tests, 1)
            self.assertEqual(
                decode_final_suite_artifact(
                    canonical_bytes(receipt), G4FinalWholeSuiteReceipt
                ),
                receipt,
            )
            verify_final_whole_suite_receipt(
                receipt,
                **{
                    key: value
                    for key, value in inputs.items()
                    if key
                    not in {"approval", "creator_request", "reviewer_request", "now"}
                },
            )
            with self.assertRaises(FileExistsError):
                run_final_whole_suites(**inputs, container=container)

    def test_wrong_creator_suite_and_duplicate_execution_id_fail_before_claim(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            inputs, container = self._case(Path(directory))
            approval = inputs["approval"]
            self.assertIsInstance(approval, SignedG4FinalWholeSuiteApproval)
            grant = approval.approval.model_copy(
                update={"creator_test_suite_sha256": "f" * 64}
            )
            inputs["approval"] = SignedG4FinalWholeSuiteApproval(
                approval=grant, signature=approval.signature
            )
            with self.assertRaises(ValueError):
                run_final_whole_suites(**inputs, container=container)
            inputs["approval"] = approval
            reviewer = inputs["reviewer_request"]
            self.assertIsInstance(reviewer, ReviewerTestExecutionRequest)
            creator = inputs["creator_request"]
            self.assertIsInstance(creator, ReviewerTestExecutionRequest)
            duplicate = reviewer.model_copy(
                update={"execution_id": creator.execution_id}
            )
            inputs["reviewer_request"] = duplicate
            with self.assertRaisesRegex(ValueError, "exact current inputs"):
                run_final_whole_suites(**inputs, container=container)
            self.assertEqual(tuple(inputs["final_dispatch_store"].iterdir()), ())

    def test_test_pattern_file_cannot_hide_as_creator_fixture(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, _container = self._case(Path(directory))
            package = inputs["creator_package"]
            source = (
                b"import unittest\nclass TestShadow(unittest.TestCase):\n    pass\n"
            )
            shadow = TestFileDeclaration(
                path="tests/test_shadow.py",
                kind="fixture",
                media_type="text/x-python",
                content_sha256=digest(source),
                bytes=len(source),
            )
            payload = ReviewerTestPackagePayload(
                manifest=package.payload.manifest.model_copy(
                    update={"files": (*package.payload.manifest.files, shadow)}
                ),
                files=(
                    *package.payload.files,
                    FrozenTestFile(
                        declaration=shadow,
                        content_base64=base64.b64encode(source).decode("ascii"),
                    ),
                ),
            )
            hidden = FrozenReviewerTestPackage(
                payload=payload,
                payload_sha256=digest(canonical_bytes(payload)),
            )
            with self.assertRaisesRegex(ValueError, "hides a collected test"):
                _verify_creator_package(
                    hidden,
                    inputs["provenance"],
                    inputs["repository_root"],
                    inputs["implementation_root"],
                    inputs["git_executable"],
                )

    def test_failed_creator_suite_is_nonaccepting_and_both_suites_run(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, container = self._case(Path(directory))
            calls = 0

            def respond(_argv: object, payload: bytes, **_kwargs: object) -> bytes:
                nonlocal calls
                calls += 1
                response = self._worker_response(payload)
                if calls == 1:
                    observed = decode_execution_observation(response)
                    failed = IsolatedReviewerTestObservation.model_validate(
                        {
                            **observed.model_dump(),
                            "failed_test_ids": ("test_creator.TestCreator.test_add",),
                            "failures": 1,
                            "suite_successful": False,
                        }
                    )
                    return canonical_bytes(failed)
                return response

            with patch.object(container, "execute", side_effect=respond):
                receipt = run_final_whole_suites(**inputs, container=container)
            self.assertEqual(calls, 2)
            self.assertFalse(receipt.final_suites_passed)
            self.assertFalse(receipt.acceptance_authorized)
            with self.assertRaises(ValidationError):
                G4FinalWholeSuiteReceipt.model_validate(
                    {**receipt.model_dump(), "final_suites_passed": True}
                )

    def test_cli_run_and_verify_retains_private_receipt(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, _container = self._case(root)
            artifacts = {
                "approval": inputs["approval"],
                "candidate": inputs["candidate"],
                "provenance": inputs["provenance"],
                "controls": inputs["controls"],
                "binding": inputs["reviewer_binding"],
                "creator-request": inputs["creator_request"],
                "reviewer-request": inputs["reviewer_request"],
            }
            for name, artifact in artifacts.items():
                (root / f"{name}.json").write_bytes(canonical_bytes(artifact))
            common = [
                "--candidate",
                str(root / "candidate.json"),
                "--provenance",
                str(root / "provenance.json"),
                "--controls",
                str(root / "controls.json"),
                "--binding",
                str(root / "binding.json"),
                "--creator-package",
                str(inputs["creator_package_path"]),
                "--reviewer-package",
                str(inputs["reviewer_package_path"]),
                "--repository-root",
                str(inputs["repository_root"]),
                "--implementation-root",
                str(inputs["implementation_root"]),
                "--git",
                str(inputs["git_executable"]),
                "--candidate-dispatch-store",
                str(inputs["candidate_dispatch_store"]),
                "--final-dispatch-store",
                str(inputs["final_dispatch_store"]),
            ]
            output = root / "final-receipt.json"
            with (
                patch.object(
                    OfflineContainer,
                    "execute",
                    autospec=True,
                    side_effect=self._class_execute,
                ),
                patch("mos_eisley.reviewer_final_suites.datetime") as clock,
                redirect_stdout(io.StringIO()),
            ):
                clock.now.return_value = NOW + timedelta(minutes=8)
                code = main(
                    [
                        "g4-run-final-whole-suites",
                        "--approval",
                        str(root / "approval.json"),
                        "--creator-request",
                        str(root / "creator-request.json"),
                        "--reviewer-request",
                        str(root / "reviewer-request.json"),
                        "--docker",
                        "/usr/bin/docker",
                        "--lifecycle-root",
                        str(root / "lifecycle"),
                        "--output",
                        str(output),
                        *common,
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with redirect_stdout(io.StringIO()):
                code = main(
                    [
                        "g4-verify-final-whole-suites",
                        "--receipt",
                        str(output),
                        *common,
                    ]
                )
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
