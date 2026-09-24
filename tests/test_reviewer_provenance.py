"""Authenticated G4 custody and trusted Git/E2 provenance regressions."""

from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
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
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ChildAssignment,
    G4ChildResult,
    G4CreatorApproval,
    G4ProvenanceTrustPolicy,
    G4ReviewerCustody,
    TrustedGitProvenance,
    assemble_authenticated_provenance,
    decode_provenance_artifact,
    provenance_signer,
    record_trusted_git_provenance,
    sign_child_assignment,
    sign_child_result,
    sign_creator_approval,
    sign_git_provenance,
    sign_reviewer_custody,
    verify_authenticated_provenance,
    verify_custody_chain,
)
from mos_eisley.reviewer_test_execution import (
    ImmutableReviewerTestExecutionReceipt,
    IsolatedReviewerTestObservation,
    KnownControlValidationRecord,
    ReviewerTestExecutionRequest,
    validate_known_controls,
)
from mos_eisley.reviewer_test_package import (
    BlindReviewReference,
    FrozenReviewerTestPackage,
    FrozenTestFile,
    ReferenceKind,
    ReviewerTestPackageManifest,
    ReviewerTestPackagePayload,
    TestCollectionContract,
    TestFileDeclaration,
)

IMAGE = "sha256:" + "a" * 64
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


class G4ProvenanceFixture:
    def __init__(self, root: Path, *, single_operator: bool = False) -> None:
        self.root = root
        self.repository = root / "repository"
        self.repository.mkdir()
        self.git = Path("/usr/bin/git")
        self.run_git("init", "-q")
        self.run_git("config", "user.name", "Fixture")
        self.run_git("config", "user.email", "fixture@example.test")
        (self.repository / "src/demo").mkdir(parents=True)
        self.write(
            "src/demo/__init__.py", "def add(left, right):\n    return left - right\n"
        )
        self.write("pyproject.toml", "[project]\nname='demo'\n")
        self.write("uv.lock", "version = 1\n")
        self.write("tests/test_creator.py", "def test_creator():\n    assert True\n")
        self.write("README.md", "base\n")
        self.commit("base")
        self.base_revision = self._text("rev-parse", "HEAD")

        self.creator_key = Ed25519PrivateKey.generate()
        self.reviewer_key = (
            self.creator_key if single_operator else Ed25519PrivateKey.generate()
        )
        self.vcs_key = (
            self.creator_key if single_operator else Ed25519PrivateKey.generate()
        )
        self.child_key = Ed25519PrivateKey.generate()
        creator = provenance_signer("creator", self.creator_key.public_key())
        reviewer = provenance_signer(
            "creator" if single_operator else "reviewer",
            self.reviewer_key.public_key(),
        )
        vcs = provenance_signer(
            "creator" if single_operator else "vcs-broker",
            self.vcs_key.public_key(),
        )
        child = provenance_signer("child", self.child_key.public_key())
        self.policy = G4ProvenanceTrustPolicy(
            schema_version=2 if single_operator else 1,
            policy_id="g4-policy",
            creators=(creator,),
            reviewers=(reviewer,),
            vcs_brokers=(vcs,),
            children=(child,),
            valid_from=NOW - timedelta(hours=1),
            valid_until=NOW + timedelta(hours=1),
            operator_mode="single_operator" if single_operator else "separated",
        )
        self.plan = digest(b"approved plan")
        self.interface = digest(b"public interface")
        self.rubric = digest(b"rubric")
        self.creator_tests = digest(b"creator tests")
        approval = G4CreatorApproval(
            schema_version=2 if single_operator else 1,
            approval_id="creator-approval",
            policy_sha256=self.policy.policy_sha256,
            operator_mode="single_operator" if single_operator else "separated",
            issued_at=NOW,
            approved_plan_sha256=self.plan,
            creator_test_suite_sha256=self.creator_tests,
            public_interface_sha256s=(self.interface,),
            rubric_sha256=self.rubric,
            base_revision=self.base_revision,
        )
        self.creator = sign_creator_approval(approval, "creator", self.creator_key)
        self.package = self._package()
        custody = G4ReviewerCustody(
            schema_version=2 if single_operator else 1,
            custody_id="reviewer-custody",
            policy_sha256=self.policy.policy_sha256,
            operator_mode="single_operator" if single_operator else "separated",
            issued_at=NOW + timedelta(minutes=1),
            frozen_reviewer_test_package_sha256=self.package.frozen_package_sha256,
            reviewer_test_payload_sha256=self.package.payload_sha256,
            creator_approval_artifact_sha256=self.creator.artifact_sha256,
            independent_human_review_claimed=not single_operator,
            single_operator_self_review_risk_accepted=single_operator,
        )
        self.reviewer = sign_reviewer_custody(
            custody,
            "creator" if single_operator else "reviewer",
            self.reviewer_key,
        )
        assignment = G4ChildAssignment(
            assignment_id="child-assignment",
            policy_sha256=self.policy.policy_sha256,
            issued_at=NOW + timedelta(minutes=2),
            creator_approval_artifact_sha256=self.creator.artifact_sha256,
            reviewer_custody_artifact_sha256=self.reviewer.artifact_sha256,
            frozen_reviewer_test_package_sha256=self.package.frozen_package_sha256,
            base_revision=self.base_revision,
            child_signer_id="child",
            child_public_key_sha256=child.public_key_sha256,
            child_brief_sha256=digest(b"child brief"),
            acceptance_criteria_sha256=digest(b"acceptance criteria"),
            creator_test_paths=("tests/test_creator.py",),
            owned_paths=("src/demo/__init__.py",),
            max_input_tokens=10_000,
            max_output_tokens=2_000,
            max_tool_calls=10,
            max_seconds=600,
            max_microusd=10_000,
        )
        self.assignment = sign_child_assignment(assignment, "creator", self.creator_key)

        self.write(
            "src/demo/__init__.py", "def add(left, right):\n    return left + right\n"
        )
        self.commit("child implementation")
        self.child_revision = self._text("rev-parse", "HEAD")
        patch = self._bytes(
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            self.base_revision,
            self.child_revision,
            "--",
        )
        result = G4ChildResult(
            result_id="child-result",
            policy_sha256=self.policy.policy_sha256,
            issued_at=NOW + timedelta(minutes=3),
            assignment_artifact_sha256=self.assignment.artifact_sha256,
            base_revision=self.base_revision,
            child_revision=self.child_revision,
            patch_sha256=digest(patch),
            patch_bytes=len(patch),
            changed_paths=("src/demo/__init__.py",),
            verification_evidence_sha256=digest(b"child verification"),
            unresolved_issue_count=0,
        )
        self.result = sign_child_result(result, "child", self.child_key)

        self.write("README.md", "integrated\n")
        self.commit("creator integration")
        self.source_revision = self._text("rev-parse", "HEAD")
        self.package_path = root / "reviewer-package.json"
        self.package_path.write_bytes(canonical_bytes(self.package))
        self.binding = self._binding()
        self.controls = self._controls()

    def run_git(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [str(self.git), *arguments],
            cwd=self.repository,
            check=True,
            capture_output=True,
        )

    def _bytes(self, *arguments: str) -> bytes:
        return self.run_git(*arguments).stdout

    def _text(self, *arguments: str) -> str:
        return self._bytes(*arguments).decode().strip()

    def write(self, relative: str, value: str) -> None:
        path = self.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def commit(self, message: str) -> None:
        self.run_git("add", "--all")
        self.run_git("commit", "-q", "-m", message)

    def _package(self) -> FrozenReviewerTestPackage:
        source = (
            b"from mos_eisley_reviewer_adapter import add\n"
            b"import unittest\n\n"
            b"class TestAdd(unittest.TestCase):\n"
            b"    def test_add(self): self.assertEqual(add(2, 3), 5)\n"
        )
        declaration = TestFileDeclaration(
            path="tests/test_add.py",
            kind="test",
            media_type="text/x-python",
            content_sha256=digest(source),
            bytes=len(source),
        )
        reference_values: tuple[tuple[ReferenceKind, str, str, int], ...] = (
            ("approved_plan", "plan", self.plan, 13),
            (
                "creator_approval",
                "creator",
                self.creator.artifact_sha256,
                len(canonical_bytes(self.creator)),
            ),
            ("interface", "interface", self.interface, 16),
            ("rubric", "rubric", self.rubric, 6),
        )
        references = tuple(
            BlindReviewReference(
                kind=kind,
                reference_id=reference_id,
                content_sha256=sha,
                bytes=size,
            )
            for kind, reference_id, sha, size in sorted(reference_values)
        )
        manifest = ReviewerTestPackageManifest(
            package_id="reviewer-package",
            references=references,
            collection=TestCollectionContract(
                start_directory="tests",
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
            payload=payload,
            payload_sha256=digest(canonical_bytes(payload)),
        )

    def _binding(self) -> ImmutableImplementationBindingRecord:
        declarations: list[ImplementationFileDeclaration] = []
        values: tuple[tuple[str, BindingFileKind, BindingMediaType], ...] = (
            ("pyproject.toml", "build_metadata", "application/toml"),
            ("src/demo/__init__.py", "implementation_source", "text/x-python"),
            ("uv.lock", "dependency_lock", "text/plain"),
        )
        for relative, kind, media in values:
            payload = (self.repository / relative).read_bytes()
            declarations.append(
                ImplementationFileDeclaration(
                    path=relative,
                    kind=kind,
                    media_type=media,
                    content_sha256=digest(payload),
                    bytes=len(payload),
                )
            )
        manifest = ImplementationBindingManifest(
            binding_id="final-binding",
            source_revision=self.source_revision,
            frozen_reviewer_test_package_sha256=self.package.frozen_package_sha256,
            source_roots=("src",),
            files=tuple(sorted(declarations, key=lambda item: item.path)),
            adapter=AllowlistedImplementationAdapter(
                exports=(
                    DirectSymbolBinding(
                        exposed_name="add",
                        target_module="demo",
                        target_symbol="add",
                        target_file="src/demo/__init__.py",
                    ),
                )
            ),
        )
        return create_implementation_binding_record(
            manifest, self.package_path, self.repository
        )

    def _receipt(
        self, *, good: bool, binding_sha: str, tree_sha: str
    ) -> ImmutableReviewerTestExecutionReceipt:
        request = ReviewerTestExecutionRequest(
            execution_id="good" if good else "bad",
            binding_record_sha256=binding_sha,
            container_image_id=IMAGE,
            role="known_good" if good else "known_bad",
        )
        observation = IsolatedReviewerTestObservation(
            job_sha256=("1" if good else "2") * 64,
            collected_tests=1,
            started_tests=1,
            executed_tests=1,
            skipped_tests=0,
            failures=0 if good else 1,
            errors=0,
            expected_failures=0,
            unexpected_successes=0,
            collected_test_ids_sha256="3" * 64,
            started_test_ids_sha256="4" * 64,
            executed_test_ids_sha256="5" * 64,
            output_bytes=0,
            suite_successful=good,
        )
        collection = self.package.payload.manifest.collection
        return ImmutableReviewerTestExecutionReceipt(
            request=request,
            request_sha256=request.request_sha256,
            binding_record_sha256=binding_sha,
            frozen_reviewer_test_package_sha256=self.package.frozen_package_sha256,
            reviewer_test_payload_sha256=self.package.payload_sha256,
            implementation_tree_sha256=tree_sha,
            adapter_sha256=self.binding.payload.adapter_sha256,
            collection=collection,
            collection_sha256=digest(canonical_bytes(collection)),
            job_sha256=observation.job_sha256,
            observation=observation,
            collection_contract_satisfied=True,
            role_expectation_satisfied=True,
        )

    def _controls(self) -> KnownControlValidationRecord:
        good = self._receipt(
            good=True,
            binding_sha=self.binding.binding_record_sha256,
            tree_sha=self.binding.payload.implementation_tree_sha256,
        )
        bad = self._receipt(
            good=False,
            binding_sha="b" * 64,
            tree_sha="c" * 64,
        )
        return validate_known_controls(good, bad)

    def provenance(self):  # type: ignore[no-untyped-def]
        verify_custody_chain(
            self.policy,
            self.creator,
            self.reviewer,
            self.assignment,
            self.result,
            self.package,
        )
        return record_trusted_git_provenance(
            repository_id="fixture-repository",
            repository_root=self.repository,
            implementation_root=self.repository,
            git_executable=self.git,
            binding=self.binding,
            reviewer_package_path=self.package_path,
            assignment=self.assignment,
            result=self.result,
        )

    def record(self) -> AuthenticatedG4ProvenanceRecord:
        signed_git = sign_git_provenance(
            self.provenance(),
            "creator"
            if self.policy.operator_mode == "single_operator"
            else "vcs-broker",
            self.vcs_key,
        )
        return assemble_authenticated_provenance(
            policy=self.policy,
            creator=self.creator,
            reviewer=self.reviewer,
            assignment=self.assignment,
            result=self.result,
            git_provenance=signed_git,
            package=self.package,
            binding=self.binding,
            controls=self.controls,
        )


class ReviewerProvenanceTests(unittest.TestCase):
    def test_separated_chain_reconstructs_git_and_replays(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = G4ProvenanceFixture(Path(directory))
            record = fixture.record()
            self.assertTrue(record.custody_authenticated)
            self.assertTrue(record.vcs_provenance_verified)
            self.assertTrue(record.e2_provenance_verified)
            self.assertFalse(record.child_dispatch_authorized)
            self.assertFalse(record.vcs_write_authorized)
            self.assertEqual(
                decode_provenance_artifact(
                    canonical_bytes(record), AuthenticatedG4ProvenanceRecord
                ),
                record,
            )
            verify_authenticated_provenance(
                record,
                package=fixture.package,
                binding=fixture.binding,
                controls=fixture.controls,
            )

    def test_single_operator_discloses_risk_and_requires_distinct_child(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = G4ProvenanceFixture(Path(directory), single_operator=True)
            record = fixture.record()
            self.assertFalse(
                record.reviewer_custody.custody.independent_human_review_claimed
            )
            self.assertTrue(
                record.reviewer_custody.custody.single_operator_self_review_risk_accepted
            )
            with self.assertRaisesRegex(ValidationError, "child signers"):
                G4ProvenanceTrustPolicy(
                    schema_version=2,
                    policy_id="bad-policy",
                    creators=fixture.policy.creators,
                    reviewers=fixture.policy.reviewers,
                    vcs_brokers=fixture.policy.vcs_brokers,
                    children=fixture.policy.creators,
                    valid_from=NOW,
                    valid_until=NOW + timedelta(hours=1),
                    operator_mode="single_operator",
                )
            with self.assertRaisesRegex(ValidationError, "exclude creator tests"):
                G4ChildAssignment.model_validate(
                    {
                        **fixture.assignment.assignment.model_dump(mode="python"),
                        "creator_test_paths": ("src/demo/__init__.py",),
                    }
                )

    def test_signature_and_role_substitution_fail(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = G4ProvenanceFixture(Path(directory))
            tampered = fixture.creator.model_copy(
                update={
                    "approval": fixture.creator.approval.model_copy(
                        update={"creator_test_suite_sha256": "f" * 64}
                    )
                }
            )
            with self.assertRaisesRegex(ValueError, "invalid G4 creator signature"):
                verify_custody_chain(
                    fixture.policy,
                    tampered,
                    fixture.reviewer,
                    fixture.assignment,
                    fixture.result,
                    fixture.package,
                )
            wrong_child = sign_child_result(
                fixture.result.result, "creator", fixture.creator_key
            )
            with self.assertRaisesRegex(ValueError, "child signer is not enrolled"):
                verify_custody_chain(
                    fixture.policy,
                    fixture.creator,
                    fixture.reviewer,
                    fixture.assignment,
                    wrong_child,
                    fixture.package,
                )

    def test_dirty_or_untracked_bound_source_fails(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = G4ProvenanceFixture(Path(directory))
            fixture.write("src/demo/extra.txt", "untracked\n")
            with self.assertRaisesRegex(ValueError, "worktree paths are not clean"):
                fixture.provenance()
            (fixture.repository / "src/demo/extra.txt").unlink()
            fixture.write("src/demo/__init__.py", "dirty\n")
            with self.assertRaisesRegex(ValueError, "worktree paths are not clean"):
                fixture.provenance()

    def test_child_diff_outside_owned_paths_fails(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = G4ProvenanceFixture(Path(directory))
            changed = fixture.result.result.model_copy(
                update={"changed_paths": ("pyproject.toml",)}
            )
            resigned = sign_child_result(changed, "child", fixture.child_key)
            with self.assertRaisesRegex(ValueError, "custody or child lineage"):
                verify_custody_chain(
                    fixture.policy,
                    fixture.creator,
                    fixture.reviewer,
                    fixture.assignment,
                    resigned,
                    fixture.package,
                )

    def test_changed_head_and_untrusted_fsmonitor_config_fail_safely(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = G4ProvenanceFixture(Path(directory))
            marker = fixture.root / "fsmonitor-ran"
            script = fixture.root / "fsmonitor"
            script.write_text(f"#!/bin/sh\ntouch {marker}\n")
            script.chmod(0o700)
            fixture.run_git("config", "core.fsmonitor", str(script))
            fixture.provenance()
            self.assertFalse(marker.exists())
            fixture.write("README.md", "post-binding head\n")
            fixture.commit("unexpected later commit")
            with self.assertRaisesRegex(ValueError, "HEAD differs"):
                fixture.provenance()

    def test_noncanonical_and_duplicate_records_fail(self) -> None:
        with TemporaryDirectory() as directory:
            record = G4ProvenanceFixture(Path(directory)).record()
            duplicate = canonical_bytes(record).replace(
                b'"schema_version":1',
                b'"schema_version":1,"schema_version":1',
                1,
            )
            with self.assertRaises(ValueError):
                decode_provenance_artifact(duplicate, AuthenticatedG4ProvenanceRecord)

    def test_cli_records_assembles_and_replays_private_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = G4ProvenanceFixture(root)
            artifacts = {
                "policy": fixture.policy,
                "creator.json": fixture.creator,
                "reviewer.json": fixture.reviewer,
                "assignment.json": fixture.assignment,
                "result.json": fixture.result,
                "binding.json": fixture.binding,
                "controls.json": fixture.controls,
            }
            paths: dict[str, Path] = {}
            for name, value in artifacts.items():
                path = root / name
                path.write_bytes(canonical_bytes(value))
                paths[name] = path
            git_record_path = root / "git-provenance.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        [
                            "g4-record-reviewer-git-provenance",
                            "--policy",
                            str(paths["policy"]),
                            "--creator-approval",
                            str(paths["creator.json"]),
                            "--reviewer-custody",
                            str(paths["reviewer.json"]),
                            "--child-assignment",
                            str(paths["assignment.json"]),
                            "--child-result",
                            str(paths["result.json"]),
                            "--binding",
                            str(paths["binding.json"]),
                            "--reviewer-package",
                            str(fixture.package_path),
                            "--repository-root",
                            str(fixture.repository),
                            "--implementation-root",
                            str(fixture.repository),
                            "--git",
                            str(fixture.git),
                            "--repository-id",
                            "fixture-repository",
                            "--output",
                            str(git_record_path),
                        ]
                    ),
                    0,
                )
            self.assertEqual(
                json.loads(stdout.getvalue())["type"], "g4.git_provenance.recorded"
            )
            self.assertEqual(os.stat(git_record_path).st_mode & 0o777, 0o600)
            raw_git = decode_provenance_artifact(
                git_record_path.read_bytes(),
                TrustedGitProvenance,
            )
            signed_git = sign_git_provenance(raw_git, "vcs-broker", fixture.vcs_key)
            signed_git_path = root / "signed-git.json"
            signed_git_path.write_bytes(canonical_bytes(signed_git))
            final_path = root / "authenticated-provenance.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "g4-assemble-reviewer-provenance",
                            "--policy",
                            str(paths["policy"]),
                            "--creator-approval",
                            str(paths["creator.json"]),
                            "--reviewer-custody",
                            str(paths["reviewer.json"]),
                            "--child-assignment",
                            str(paths["assignment.json"]),
                            "--child-result",
                            str(paths["result.json"]),
                            "--binding",
                            str(paths["binding.json"]),
                            "--reviewer-package",
                            str(fixture.package_path),
                            "--git-provenance",
                            str(signed_git_path),
                            "--controls",
                            str(paths["controls.json"]),
                            "--output",
                            str(final_path),
                        ]
                    ),
                    0,
                )
            self.assertEqual(os.stat(final_path).st_mode & 0o777, 0o600)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "g4-verify-reviewer-provenance",
                            "--record",
                            str(final_path),
                            "--binding",
                            str(paths["binding.json"]),
                            "--reviewer-package",
                            str(fixture.package_path),
                            "--controls",
                            str(paths["controls.json"]),
                            "--repository-root",
                            str(fixture.repository),
                            "--implementation-root",
                            str(fixture.repository),
                            "--git",
                            str(fixture.git),
                        ]
                    ),
                    0,
                )
            with (
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "g4-assemble-reviewer-provenance",
                            "--policy",
                            str(paths["policy"]),
                            "--creator-approval",
                            str(paths["creator.json"]),
                            "--reviewer-custody",
                            str(paths["reviewer.json"]),
                            "--child-assignment",
                            str(paths["assignment.json"]),
                            "--child-result",
                            str(paths["result.json"]),
                            "--binding",
                            str(paths["binding.json"]),
                            "--reviewer-package",
                            str(fixture.package_path),
                            "--git-provenance",
                            str(signed_git_path),
                            "--controls",
                            str(paths["controls.json"]),
                            "--output",
                            str(final_path),
                        ]
                    ),
                    2,
                )


if __name__ == "__main__":
    unittest.main()
