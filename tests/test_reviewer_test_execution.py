"""Isolated G4 reviewer-test execution, counts and known-control evidence."""

import base64
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_implementation_binding import (
    AllowlistedImplementationAdapter,
    BindingFileKind,
    BindingMediaType,
    DirectSymbolBinding,
    ImmutableImplementationBindingRecord,
    ImplementationBindingManifest,
    ImplementationFileDeclaration,
    create_implementation_binding_record,
)
from mos_eisley.reviewer_test_execution import (
    ExecutionRole,
    ImmutableReviewerTestExecutionReceipt,
    IsolatedReviewerTestJob,
    IsolatedReviewerTestObservation,
    ReviewerTestExecutionRequest,
    build_isolated_reviewer_test_job,
    decode_control_record,
    decode_execution_job,
    decode_execution_observation,
    decode_execution_receipt,
    decode_execution_request,
    run_isolated_reviewer_tests,
    validate_known_controls,
    verify_execution_receipt,
)
from mos_eisley.reviewer_test_package import (
    BlindReviewReference,
    DeclaredTestMarker,
    FrozenReviewerTestPackage,
    FrozenTestFile,
    ReferenceKind,
    ReviewerTestPackageManifest,
    ReviewerTestPackagePayload,
    TestCollectionContract,
    TestFileDeclaration,
)
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import bounded_process

IMAGE = "sha256:" + "a" * 64


class ReviewerTestExecutionTests(unittest.TestCase):
    def _package(
        self,
        *,
        expected_collected: int = 1,
        skipped: bool = False,
        target: str = "add",
        source_override: bytes | None = None,
    ) -> FrozenReviewerTestPackage:
        if source_override is not None:
            source = source_override
        elif skipped:
            source = (
                f"from mos_eisley_reviewer_adapter import {target}\n"
                "import unittest\n\n"
                "class TestAdd(unittest.TestCase):\n"
                "    @unittest.skip('approved')\n"
                f"    def test_add(self): self.assertEqual({target}(2, 3), 5)\n"
                f"    def test_add_again(self): self.assertEqual({target}(3, 2), 5)\n"
            ).encode()
        else:
            source = (
                f"from mos_eisley_reviewer_adapter import {target}\n"
                "import unittest\n\n"
                "class TestAdd(unittest.TestCase):\n"
                f"    def test_add(self): self.assertEqual({target}(2, 3), 5)\n"
            ).encode()
        reference_payloads: dict[tuple[ReferenceKind, str], bytes] = {
            ("approved_plan", "plan"): b"approved plan",
            ("creator_approval", "creator"): b"creator approval",
            ("interface", "interface"): b"public interface",
            ("rubric", "rubric"): b"review rubric",
        }
        if skipped:
            reference_payloads[("marker_approval", "skip-approval")] = b"approved skip"
        references = tuple(
            BlindReviewReference(
                kind=kind,
                reference_id=reference_id,
                content_sha256=digest(payload),
                bytes=len(payload),
            )
            for (kind, reference_id), payload in sorted(reference_payloads.items())
        )
        declaration = TestFileDeclaration(
            path="tests/test_add.py",
            kind="test",
            media_type="text/x-python",
            content_sha256=digest(source),
            bytes=len(source),
        )
        markers = (
            (
                DeclaredTestMarker(
                    path="tests/test_add.py",
                    line=5,
                    kind="skip",
                    reason="approved",
                    approval_reference_id="skip-approval",
                ),
            )
            if skipped
            else ()
        )
        init_payload = b'"""Reviewer tests."""\n'
        init_declaration = TestFileDeclaration(
            path="tests/__init__.py",
            kind="fixture",
            media_type="text/x-python",
            content_sha256=digest(init_payload),
            bytes=len(init_payload),
        )
        collected = 2 if skipped else expected_collected
        manifest = ReviewerTestPackageManifest(
            package_id="isolated-reviewer-tests",
            references=references,
            collection=TestCollectionContract(
                start_directory="tests",
                expected_collected_tests=collected,
                expected_executed_tests=1 if skipped else expected_collected,
                expected_skipped_tests=1 if skipped else 0,
            ),
            files=(init_declaration, declaration),
            declared_markers=markers,
        )
        payload = ReviewerTestPackagePayload(
            manifest=manifest,
            files=(
                FrozenTestFile(
                    declaration=init_declaration,
                    content_base64=base64.b64encode(init_payload).decode("ascii"),
                ),
                FrozenTestFile(
                    declaration=declaration,
                    content_base64=base64.b64encode(source).decode("ascii"),
                ),
            ),
        )
        return FrozenReviewerTestPackage(
            payload=payload,
            payload_sha256=digest(canonical_bytes(payload)),
        )

    def _binding(
        self,
        root: Path,
        package: FrozenReviewerTestPackage,
        *,
        name: str,
        implementation: bytes,
        target_package: str = "demo",
        target_symbol: str = "add",
    ) -> tuple[ImmutableImplementationBindingRecord, Path, Path]:
        implementation_root = root / name
        source_directory = implementation_root / "src" / target_package
        source_directory.mkdir(parents=True)
        package_path = root / f"{name}-reviewer-package.json"
        package_path.write_bytes(canonical_bytes(package))
        source_path = f"src/{target_package}/__init__.py"
        payloads = {
            "pyproject.toml": f"[project]\nname='{target_package}'\n".encode(),
            source_path: implementation,
            "uv.lock": b"version = 1\n",
        }
        kinds: dict[str, BindingFileKind] = {
            "pyproject.toml": "build_metadata",
            source_path: "implementation_source",
            "uv.lock": "dependency_lock",
        }
        media_types: dict[str, BindingMediaType] = {
            "pyproject.toml": "application/toml",
            source_path: "text/x-python",
            "uv.lock": "text/plain",
        }
        declarations: list[ImplementationFileDeclaration] = []
        for relative, payload in payloads.items():
            path = implementation_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            declarations.append(
                ImplementationFileDeclaration(
                    path=relative,
                    kind=kinds[relative],
                    media_type=media_types[relative],
                    content_sha256=digest(payload),
                    bytes=len(payload),
                )
            )
        manifest = ImplementationBindingManifest(
            binding_id=f"{name}-binding",
            source_revision=("a" if name == "good" else "b") * 40,
            frozen_reviewer_test_package_sha256=package.frozen_package_sha256,
            source_roots=("src",),
            files=tuple(sorted(declarations, key=lambda item: item.path)),
            adapter=AllowlistedImplementationAdapter(
                exports=(
                    DirectSymbolBinding(
                        exposed_name=target_symbol,
                        target_module=target_package,
                        target_symbol=target_symbol,
                        target_file=source_path,
                    ),
                )
            ),
        )
        record = create_implementation_binding_record(
            manifest, package_path, implementation_root
        )
        return record, package_path, implementation_root

    def _request(
        self,
        binding: ImmutableImplementationBindingRecord,
        role: ExecutionRole,
        execution_id: str,
    ) -> ReviewerTestExecutionRequest:
        return ReviewerTestExecutionRequest(
            execution_id=execution_id,
            binding_record_sha256=binding.binding_record_sha256,
            container_image_id=IMAGE,
            role=role,
            timeout_seconds=10,
        )

    def _observe(self, job: IsolatedReviewerTestJob) -> IsolatedReviewerTestObservation:
        output = bounded_process(
            [sys.executable, "-m", "mos_eisley.run.reviewer_test_worker"],
            canonical_bytes(job),
            timeout=15,
            limit=256_000,
        )
        return decode_execution_observation(output)

    def _receipt(
        self,
        request: ReviewerTestExecutionRequest,
        binding: ImmutableImplementationBindingRecord,
        package_path: Path,
        implementation_root: Path,
    ) -> ImmutableReviewerTestExecutionReceipt:
        job = build_isolated_reviewer_test_job(
            request, binding, package_path, implementation_root
        )
        observation = self._observe(job)
        container = OfflineContainer(Path("/usr/bin/docker"), IMAGE)
        with patch.object(
            container, "execute", return_value=canonical_bytes(observation)
        ) as execute:
            receipt = run_isolated_reviewer_tests(
                request,
                binding,
                package_path,
                implementation_root,
                container,
            )
        self.assertEqual(
            execute.call_args.args[0],
            ("-m", "mos_eisley.run.reviewer_test_worker"),
        )
        return receipt

    def test_known_good_and_assertion_only_known_bad_validate(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package()
            good, good_package, good_root = self._binding(
                root,
                package,
                name="good",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            bad, bad_package, bad_root = self._binding(
                root,
                package,
                name="bad",
                implementation=b"def add(left, right):\n    return left - right\n",
            )
            good_receipt = self._receipt(
                self._request(good, "known_good", "good-control"),
                good,
                good_package,
                good_root,
            )
            bad_receipt = self._receipt(
                self._request(bad, "known_bad", "bad-control"),
                bad,
                bad_package,
                bad_root,
            )
            self.assertTrue(good_receipt.observation.suite_successful)
            self.assertEqual(bad_receipt.observation.failures, 1)
            self.assertEqual(bad_receipt.observation.errors, 0)
            control = validate_known_controls(good_receipt, bad_receipt)
            self.assertTrue(control.controls_validated)
            self.assertFalse(control.candidate_execution_authorized)
            self.assertFalse(control.correction_authorized)
            self.assertFalse(control.acceptance_authorized)

    def test_clean_child_prefers_materialized_same_name_package(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package(target="add")
            binding, package_path, implementation_root = self._binding(
                root,
                package,
                name="good",
                implementation=b"def add(left, right):\n    return left + right\n",
                target_package="mos_eisley",
            )
            request = self._request(binding, "known_good", "same-name-control")
            job = build_isolated_reviewer_test_job(
                request,
                binding,
                package_path,
                implementation_root,
            )
            observation = self._observe(job)
            self.assertTrue(observation.suite_successful)

    def test_skip_and_count_mismatch_are_observed_exactly(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            skipped_package = self._package(skipped=True)
            binding, package_path, implementation_root = self._binding(
                root,
                skipped_package,
                name="good",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            receipt = self._receipt(
                self._request(binding, "known_good", "skip-control"),
                binding,
                package_path,
                implementation_root,
            )
            self.assertEqual(receipt.observation.collected_tests, 2)
            self.assertEqual(receipt.observation.executed_tests, 1)
            self.assertEqual(receipt.observation.skipped_tests, 1)
            self.assertTrue(receipt.collection_contract_satisfied)

            mismatched = self._package(expected_collected=2)
            other, other_package, other_root = self._binding(
                root,
                mismatched,
                name="bad",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            mismatch_receipt = self._receipt(
                self._request(other, "known_good", "count-mismatch"),
                other,
                other_package,
                other_root,
            )
            self.assertFalse(mismatch_receipt.collection_contract_satisfied)
            self.assertFalse(mismatch_receipt.role_expectation_satisfied)

    def test_known_bad_import_error_is_not_a_valid_control(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package()
            good, good_package, good_root = self._binding(
                root,
                package,
                name="good",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            broken, broken_package, broken_root = self._binding(
                root,
                package,
                name="bad",
                implementation=(
                    b"def add(left, right):\n    raise RuntimeError('broken import')\n"
                ),
            )
            good_receipt = self._receipt(
                self._request(good, "known_good", "good-import-control"),
                good,
                good_package,
                good_root,
            )
            broken_receipt = self._receipt(
                self._request(broken, "known_bad", "bad-import-control"),
                broken,
                broken_package,
                broken_root,
            )
            self.assertEqual(broken_receipt.observation.errors, 1)
            self.assertFalse(broken_receipt.role_expectation_satisfied)
            with self.assertRaisesRegex(ValueError, "role expectation"):
                validate_known_controls(good_receipt, broken_receipt)

    def test_job_observation_and_receipt_tampering_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package()
            binding, package_path, implementation_root = self._binding(
                root,
                package,
                name="good",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            request = self._request(binding, "known_good", "tamper-control")
            job = build_isolated_reviewer_test_job(
                request,
                binding,
                package_path,
                implementation_root,
            )
            self.assertEqual(decode_execution_job(canonical_bytes(job)), job)
            changed = json.loads(canonical_bytes(job))
            changed["implementation_files"][0]["content_base64"] = base64.b64encode(
                b"changed"
            ).decode()
            with self.assertRaises(ValueError):
                decode_execution_job(
                    json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
                )
            observation = self._observe(job)
            wrong = observation.model_copy(update={"job_sha256": "f" * 64})
            container = OfflineContainer(Path("/usr/bin/docker"), IMAGE)
            with (
                patch.object(container, "execute", return_value=canonical_bytes(wrong)),
                self.assertRaisesRegex(ValueError, "different execution job"),
            ):
                run_isolated_reviewer_tests(
                    request,
                    binding,
                    package_path,
                    implementation_root,
                    container,
                )

            receipt = self._receipt(request, binding, package_path, implementation_root)
            self.assertEqual(
                decode_execution_receipt(canonical_bytes(receipt)), receipt
            )
            duplicate = canonical_bytes(receipt).replace(
                b'"schema_version":1', b'"schema_version":1,"schema_version":1', 1
            )
            with self.assertRaises(ValueError):
                decode_execution_receipt(duplicate)
            noncanonical = json.dumps(
                receipt.model_dump(mode="json"), indent=2
            ).encode()
            with self.assertRaises(ValueError):
                decode_execution_receipt(noncanonical)
            with self.assertRaises(ValidationError):
                receipt.request.execution_id = "changed"  # type: ignore[misc]

    def test_current_input_verification_detects_drift(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package()
            binding, package_path, implementation_root = self._binding(
                root,
                package,
                name="good",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            request = self._request(binding, "known_good", "input-drift-control")
            receipt = self._receipt(request, binding, package_path, implementation_root)
            verify_execution_receipt(
                receipt,
                request,
                binding,
                package_path,
                implementation_root,
            )
            (implementation_root / "src/demo/__init__.py").write_text(
                "def add(left, right): return 0\n"
            )
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_execution_receipt(
                    receipt,
                    request,
                    binding,
                    package_path,
                    implementation_root,
                )

    def test_output_mutation_and_deadline_attacks_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output_package = self._package(
                source_override=(
                    b"from mos_eisley_reviewer_adapter import add\n"
                    b"import unittest\n\n"
                    b"class TestOutput(unittest.TestCase):\n"
                    b"    def test_output(self):\n"
                    b"        print('x' * 70000)\n"
                    b"        self.assertEqual(add(2, 3), 5)\n"
                )
            )
            output_binding, output_path, output_root = self._binding(
                root,
                output_package,
                name="good",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            output_request = self._request(output_binding, "known_good", "output-limit")
            output_job = build_isolated_reviewer_test_job(
                output_request, output_binding, output_path, output_root
            )
            output_observation = self._observe(output_job)
            self.assertEqual(output_observation.errors, 1)
            self.assertFalse(output_observation.suite_successful)

            mutation_package = self._package(
                source_override=(
                    b"from mos_eisley_reviewer_adapter import add\n"
                    b"import os, sys, unittest\n\n"
                    b"class TestMutation(unittest.TestCase):\n"
                    b"    def test_mutation(self):\n"
                    b"        path = sys.modules[add.__module__].__file__\n"
                    b"        os.chmod(path, 0o600)\n"
                    b"        with open(path, 'ab') as stream:\n"
                    b"            stream.write(b'# changed')\n"
                )
            )
            mutation_binding, mutation_path, mutation_root = self._binding(
                root,
                mutation_package,
                name="bad",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            mutation_job = build_isolated_reviewer_test_job(
                self._request(mutation_binding, "known_bad", "mutation-attempt"),
                mutation_binding,
                mutation_path,
                mutation_root,
            )
            with self.assertRaisesRegex(ValueError, "isolated process failed"):
                self._observe(mutation_job)

            deadline_package = self._package(
                source_override=(
                    b"from mos_eisley_reviewer_adapter import add\n"
                    b"import time, unittest\n\n"
                    b"class TestDeadline(unittest.TestCase):\n"
                    b"    def test_deadline(self):\n"
                    b"        time.sleep(20)\n"
                    b"        self.assertEqual(add(2, 3), 5)\n"
                )
            )
            deadline_binding, deadline_path, deadline_root = self._binding(
                root,
                deadline_package,
                name="deadline",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            deadline_request = ReviewerTestExecutionRequest(
                execution_id="deadline-attempt",
                binding_record_sha256=deadline_binding.binding_record_sha256,
                container_image_id=IMAGE,
                role="known_good",
                timeout_seconds=5,
            )
            deadline_job = build_isolated_reviewer_test_job(
                deadline_request, deadline_binding, deadline_path, deadline_root
            )
            with self.assertRaisesRegex(ValueError, "isolated process failed"):
                self._observe(deadline_job)

    def test_cli_writes_replays_and_validates_private_records(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package()
            good, package_path, implementation_root = self._binding(
                root,
                package,
                name="good",
                implementation=b"def add(left, right):\n    return left + right\n",
            )
            request = self._request(good, "known_good", "cli-good")
            job = build_isolated_reviewer_test_job(
                request,
                good,
                package_path,
                implementation_root,
            )
            observation = self._observe(job)
            request_path = root / "request.json"
            binding_path = root / "binding.json"
            request_path.write_bytes(canonical_bytes(request))
            binding_path.write_bytes(canonical_bytes(good))
            output = root / "good-receipt.json"
            stdout = io.StringIO()
            with (
                patch.object(
                    OfflineContainer,
                    "execute",
                    return_value=canonical_bytes(observation),
                ),
                redirect_stdout(stdout),
            ):
                result = main(
                    [
                        "g4-run-reviewer-tests-isolated",
                        "--request",
                        str(request_path),
                        "--binding",
                        str(binding_path),
                        "--reviewer-package",
                        str(package_path),
                        "--implementation-root",
                        str(implementation_root),
                        "--docker",
                        "/usr/bin/docker",
                        "--output",
                        str(output),
                        "--lifecycle-root",
                        str(root / "lifecycles"),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["type"], "g4.reviewer_test_execution.completed")
            receipt = decode_execution_receipt(output.read_bytes())
            self.assertFalse(receipt.repository_write_authorized)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        [
                            "g4-verify-reviewer-test-execution",
                            "--receipt",
                            str(output),
                            "--request",
                            str(request_path),
                            "--binding",
                            str(binding_path),
                            "--reviewer-package",
                            str(package_path),
                            "--implementation-root",
                            str(implementation_root),
                        ]
                    ),
                    0,
                )
            self.assertEqual(
                json.loads(stdout.getvalue())["type"],
                "g4.reviewer_test_execution.verified",
            )
            with (
                patch.object(
                    OfflineContainer,
                    "execute",
                    return_value=canonical_bytes(observation),
                ),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "g4-run-reviewer-tests-isolated",
                            "--request",
                            str(request_path),
                            "--binding",
                            str(binding_path),
                            "--reviewer-package",
                            str(package_path),
                            "--implementation-root",
                            str(implementation_root),
                            "--docker",
                            "/usr/bin/docker",
                            "--output",
                            str(output),
                            "--lifecycle-root",
                            str(root / "lifecycles"),
                        ]
                    ),
                    2,
                )

            bad, bad_package, bad_root = self._binding(
                root,
                package,
                name="bad",
                implementation=b"def add(left, right):\n    return left - right\n",
            )
            bad_receipt = self._receipt(
                self._request(bad, "known_bad", "cli-bad"),
                bad,
                bad_package,
                bad_root,
            )
            bad_path = root / "bad-receipt.json"
            bad_path.write_bytes(canonical_bytes(bad_receipt))
            control_path = root / "control.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "g4-validate-reviewer-test-controls",
                            "--known-good",
                            str(output),
                            "--known-bad",
                            str(bad_path),
                            "--output",
                            str(control_path),
                        ]
                    ),
                    0,
                )
            control = decode_control_record(control_path.read_bytes())
            self.assertTrue(control.controls_validated)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "g4-verify-reviewer-test-controls",
                            "--control-record",
                            str(control_path),
                        ]
                    ),
                    0,
                )
            self.assertEqual(
                decode_execution_request(request_path.read_bytes()), request
            )

            with (
                patch.object(OfflineContainer, "execute") as execute,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "g4-run-reviewer-tests-isolated",
                            "--request",
                            str(request_path),
                            "--binding",
                            str(binding_path),
                            "--reviewer-package",
                            str(package_path),
                            "--implementation-root",
                            str(implementation_root),
                            "--docker",
                            "/usr/bin/docker",
                            "--output",
                            str(root / "other-receipt.json"),
                            "--lifecycle-root",
                            str(implementation_root / ".lifecycles"),
                        ]
                    ),
                    2,
                )
            execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
