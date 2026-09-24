"""Offline G4 correction integration and protected-worktree regressions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import base64
import subprocess
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import test_reviewer_correction
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_reviewer_provenance import IMAGE, NOW, G4ProvenanceFixture

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_correction import admit_correction_cycle
from mos_eisley.reviewer_correction_dispatch import (
    G4CorrectionChildDispatchApproval,
    G4CorrectionChildJob,
    G4CorrectionChildOffer,
    G4CorrectionChildProposal,
    G4CorrectionChildSourceFile,
    G4CorrectionChildUsage,
    SignedG4CorrectionChildProposal,
    creator_test_bundle_sha256,
    dispatch_correction_child,
    sign_correction_child_dispatch_approval,
    sign_correction_child_proposal,
)
from mos_eisley.reviewer_correction_integration import (
    G4CorrectionIntegrationApproval,
    G4CorrectionIntegrationRecord,
    SignedG4CorrectionIntegrationApproval,
    SignedG4CorrectionIntegrationRecord,
    _preflight_tree,
    _verify_integrated_git,
    integrate_correction_child,
    sign_correction_integration_approval,
    sign_correction_integration_record,
    verify_correction_integration_record,
)
from mos_eisley.run.isolation import OfflineContainer


class CorrectionIntegrationTests(unittest.TestCase):
    def test_signed_one_use_integration_commits_only_in_private_worktree(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = G4ProvenanceFixture(root)
            provenance = fixture.record()
            candidate_store = root / "candidate"
            correction_store = root / "correction"
            child_store = root / "child"
            integration_store = root / "integration"
            for store in (
                candidate_store,
                correction_store,
                child_store,
                integration_store,
            ):
                store.mkdir(mode=0o700)
            helper = test_reviewer_correction.CorrectionCycleTests()
            first = helper._dispatch(
                fixture, provenance, candidate_store, "first", 4, failed=True
            )
            replay = helper._dispatch(
                fixture, provenance, candidate_store, "replay", 6, failed=True
            )
            policy, triage, cycle_grant = helper._decision(
                fixture, first, replay, Ed25519PrivateKey.generate()
            )
            admission = admit_correction_cycle(
                first=first,
                reproduction=replay,
                triage=triage,
                approval=cycle_grant,
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
            test_bytes = (fixture.repository / "tests/test_creator.py").read_bytes()
            creator_test_view = (
                G4CorrectionChildSourceFile(
                    path="tests/test_creator.py",
                    content_base64=base64.b64encode(test_bytes).decode(),
                    content_sha256=digest(test_bytes),
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
                        b"def add(left, right):\n"
                        b"    return left + right  # correction\n"
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

            container = OfflineContainer(
                Path("/usr/bin/docker"), IMAGE, root / "lifecycle"
            )

            def execute(
                _args: tuple[str, ...], payload: bytes, timeout: float
            ) -> bytes:
                self.assertGreater(timeout, 0)
                G4CorrectionChildJob.model_validate_json(payload)
                return subprocess.run(
                    [sys.executable, "-m", "mos_eisley.run.reviewer_correction_child"],
                    input=payload,
                    capture_output=True,
                    timeout=10,
                    check=True,
                ).stdout

            with patch.object(container, "execute", side_effect=execute):
                receipt = asyncio.run(
                    dispatch_correction_child(
                        admission=admission,
                        approval=order,
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
                        approved_plan="approved plan",
                        brief=brief,
                        acceptance_criteria=criteria,
                        generator=Generator(),
                        container=container,
                        now=NOW + timedelta(minutes=13),
                    )
                )
            integration_grant = sign_correction_integration_approval(
                G4CorrectionIntegrationApproval(
                    integration_id="integration-one",
                    policy_sha256=fixture.policy.policy_sha256,
                    admission_sha256=admission.admission_sha256,
                    child_dispatch_receipt_sha256=digest(canonical_bytes(receipt)),
                    repository_id="fixture-repository",
                    source_revision=fixture.source_revision,
                    owned_paths=receipt.execution.changed_paths,
                    issued_at=NOW + timedelta(minutes=14),
                    expires_at=NOW + timedelta(minutes=24),
                ),
                "creator",
                fixture.creator_key,
            )

            def run_integration(
                grant: SignedG4CorrectionIntegrationApproval = integration_grant,
                store: Path = integration_store,
            ) -> G4CorrectionIntegrationRecord:
                return integrate_correction_child(
                    admission=admission,
                    receipt=receipt,
                    approval=grant,
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
                    integration_store=store,
                    now=NOW + timedelta(minutes=15),
                )

            wrong = sign_correction_integration_approval(
                integration_grant.approval.model_copy(
                    update={"child_dispatch_receipt_sha256": digest(b"wrong")}
                ),
                "creator",
                fixture.creator_key,
            )
            with self.assertRaisesRegex(ValueError, "signed cycle or proposal"):
                run_integration(wrong)
            self.assertEqual(tuple(integration_store.iterdir()), ())
            linked_store = root / "linked-integration-store"
            linked_store.symlink_to(integration_store, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "owner-owned mode 0700"):
                run_integration(store=linked_store)
            self.assertEqual(tuple(integration_store.iterdir()), ())
            hook_sentinel = root / "hook-ran"
            for hook_name in ("post-checkout", "pre-commit"):
                hook = fixture.repository / ".git" / "hooks" / hook_name
                hook.write_text(f"#!/bin/sh\nprintf ran > {hook_sentinel}\nexit 77\n")
                hook.chmod(0o755)
            before = fixture._text("rev-parse", "HEAD")
            record = run_integration()
            self.assertFalse(hook_sentinel.exists())
            self.assertEqual(fixture._text("rev-parse", "HEAD"), before)
            self.assertEqual(fixture._text("status", "--porcelain"), "")
            self.assertNotEqual(record.integrated_revision, before)
            self.assertEqual(record.changed_paths, ("src/demo/__init__.py",))
            self.assertFalse(record.acceptance_authorized)
            worktree = integration_store / record.worktree_name
            self.assertEqual(
                subprocess.run(
                    [str(fixture.git), "rev-parse", "HEAD"],
                    cwd=worktree,
                    check=True,
                    capture_output=True,
                )
                .stdout.decode()
                .strip(),
                record.integrated_revision,
            )
            signed = sign_correction_integration_record(
                record, "vcs-broker", fixture.vcs_key
            )

            def verify(signed_record: SignedG4CorrectionIntegrationRecord) -> None:
                verify_correction_integration_record(
                    signed_record,
                    admission=admission,
                    receipt=receipt,
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
                    integration_store=integration_store,
                )

            verify(signed)
            original_readme = fixture.repository / "README.md"
            original_readme.write_text("changed outside binding\n")
            with self.assertRaisesRegex(ValueError, "original checkout is not clean"):
                _verify_integrated_git(
                    git=fixture.git,
                    root=fixture.repository.resolve(strict=True),
                    worktree=worktree.resolve(strict=True),
                    source=record.source_revision,
                    receipt=receipt,
                )
            with self.assertRaisesRegex(ValueError, "clean original checkout"):
                verify(signed)
            original_readme.write_text("integrated\n")
            verify(signed)
            tampered_signed = sign_correction_integration_record(
                record.model_copy(update={"patch_sha256": digest(b"wrong")}),
                "vcs-broker",
                fixture.vcs_key,
            )
            with self.assertRaisesRegex(ValueError, "current Git"):
                verify(tampered_signed)
            (worktree / "src/demo/__init__.py").write_text("tampered\n")
            with self.assertRaisesRegex(ValueError, "worktree is not clean"):
                verify(signed)
            with self.assertRaises((FileExistsError, ValueError)):
                run_integration()

    def test_checkout_preflight_rejects_tracked_attributes(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = G4ProvenanceFixture(Path(directory))
            fixture.write(".gitattributes", "*.py filter=untrusted\n")
            fixture.commit("unsafe checkout policy")
            with self.assertRaisesRegex(ValueError, "unsafe Git material"):
                _preflight_tree(
                    fixture.git,
                    fixture.repository,
                    fixture._text("rev-parse", "HEAD"),
                )


if __name__ == "__main__":
    unittest.main()
