"""Offline initial-child scope and signature regressions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import base64
import subprocess
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_reviewer_provenance import IMAGE, NOW, G4ProvenanceFixture

from mos_eisley.core.models import digest
from mos_eisley.reviewer_correction_dispatch import (
    G4CorrectionChildSourceFile,
    G4CorrectionChildUsage,
    _source_file,
    creator_test_bundle_sha256,
)
from mos_eisley.reviewer_initial_child import (
    G4InitialChildDispatchApproval,
    G4InitialChildJob,
    G4InitialChildOffer,
    G4InitialChildProposal,
    SignedG4InitialChildProposal,
    dispatch_initial_child,
    preview_initial_child_offer,
    sign_initial_child_dispatch_approval,
    sign_initial_child_proposal,
    validate_initial_child_proposal,
    verify_initial_child_dispatch_receipt,
)
from mos_eisley.reviewer_provenance import G4ProvenanceTrustPolicy, provenance_signer
from mos_eisley.run.isolation import OfflineContainer


def _file(path: str, content: bytes) -> G4CorrectionChildSourceFile:
    return G4CorrectionChildSourceFile(
        path=path,
        content_base64=base64.b64encode(content).decode("ascii"),
        content_sha256=digest(content),
    )


class InitialChildProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.owner = Ed25519PrivateKey.generate()
        self.child = Ed25519PrivateKey.generate()
        self.foreign = Ed25519PrivateKey.generate()
        now = datetime.now(UTC)
        human = provenance_signer("owner", self.owner.public_key())
        self.policy = G4ProvenanceTrustPolicy(
            schema_version=2,
            policy_id="initial-child-fixture",
            creators=(human,),
            reviewers=(human,),
            vcs_brokers=(human,),
            children=(provenance_signer("child", self.child.public_key()),),
            valid_from=now - timedelta(minutes=1),
            valid_until=now + timedelta(hours=1),
            operator_mode="single_operator",
        )
        self.offer = G4InitialChildOffer(
            dispatch_approval_sha256=digest(b"dispatch"),
            assignment_sha256=digest(b"assignment"),
            source_revision="a" * 40,
            child_signer_id="child",
            approved_plan="Implement the function.",
            brief="Change only src/demo.py.",
            acceptance_criteria="The function passes creator tests.",
            source_files=(_file("src/demo.py", b"def f():\n    pass\n"),),
            creator_test_files=(_file("tests/test_demo.py", b"assert f() == 1\n"),),
            max_input_tokens=1000,
            max_output_tokens=500,
            max_tool_calls=1,
            max_seconds=60,
            max_microusd=1000,
        )

    def _proposal(
        self, path: str = "src/demo.py", *, input_tokens: int = 100
    ) -> G4InitialChildProposal:
        return G4InitialChildProposal(
            offer_sha256=self.offer.offer_sha256,
            replacements=(_file(path, b"def f():\n    return 1\n"),),
            usage=G4CorrectionChildUsage(
                input_tokens=input_tokens,
                output_tokens=50,
                tool_calls=0,
                seconds=1,
                microusd=5,
            ),
            unresolved_issue_count=0,
        )

    def test_enrolled_child_can_change_only_owned_source(self) -> None:
        signed = sign_initial_child_proposal(self._proposal(), "child", self.child)
        result = validate_initial_child_proposal(self.offer, signed, self.policy)
        self.assertEqual(result.changed_paths, ("src/demo.py",))
        self.assertEqual(result.usage.microusd, 5)

    def test_wrong_key_and_test_change_are_rejected(self) -> None:
        foreign = sign_initial_child_proposal(self._proposal(), "child", self.foreign)
        with self.assertRaisesRegex(ValueError, "not enrolled"):
            validate_initial_child_proposal(self.offer, foreign, self.policy)
        test_change = sign_initial_child_proposal(
            self._proposal("tests/test_demo.py"), "child", self.child
        )
        with self.assertRaisesRegex(ValueError, "owned-path"):
            validate_initial_child_proposal(self.offer, test_change, self.policy)

    def test_allowance_and_offer_substitution_are_rejected(self) -> None:
        expensive = sign_initial_child_proposal(
            self._proposal(input_tokens=1001), "child", self.child
        )
        with self.assertRaisesRegex(ValueError, "allowance"):
            validate_initial_child_proposal(self.offer, expensive, self.policy)
        changed_offer = self.offer.model_copy(update={"brief": "Different task"})
        valid = sign_initial_child_proposal(self._proposal(), "child", self.child)
        with self.assertRaisesRegex(ValueError, "owned-path"):
            validate_initial_child_proposal(changed_offer, valid, self.policy)


class InitialChildPreflightTests(unittest.TestCase):
    def test_exact_custody_and_clean_git_are_required(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = G4ProvenanceFixture(root, single_operator=True)
            base = root / "base-worktree"
            subprocess.run(
                [
                    str(fixture.git),
                    "-C",
                    str(fixture.repository),
                    "worktree",
                    "add",
                    "--detach",
                    str(base),
                    fixture.base_revision,
                ],
                check=True,
                capture_output=True,
            )
            test_path = "tests/test_creator.py"
            test_file = _source_file(test_path, (base / test_path).read_bytes())
            order = G4InitialChildDispatchApproval(
                dispatch_id="initial-child-fixture",
                policy_sha256=fixture.policy.policy_sha256,
                creator_approval_sha256=fixture.creator.artifact_sha256,
                reviewer_custody_sha256=fixture.reviewer.artifact_sha256,
                assignment_sha256=fixture.assignment.artifact_sha256,
                source_revision=fixture.base_revision,
                container_image_id=IMAGE,
                child_signer_id="child",
                brief_sha256=digest(b"child brief"),
                acceptance_criteria_sha256=digest(b"acceptance criteria"),
                creator_test_bundle_sha256=creator_test_bundle_sha256((test_file,)),
                owned_paths=("src/demo/__init__.py",),
                issued_at=NOW + timedelta(minutes=3),
                expires_at=NOW + timedelta(minutes=10),
            )
            signed = sign_initial_child_dispatch_approval(
                order, "creator", fixture.creator_key
            )

            def preview(plan: str = "approved plan") -> G4InitialChildOffer:
                return preview_initial_child_offer(
                    policy=fixture.policy,
                    creator=fixture.creator,
                    custody=fixture.reviewer,
                    assignment=fixture.assignment,
                    package=fixture.package,
                    approval=signed,
                    repository_root=base,
                    git_executable=fixture.git,
                    approved_plan=plan,
                    brief="child brief",
                    acceptance_criteria="acceptance criteria",
                    container_image_id=IMAGE,
                    now=NOW + timedelta(minutes=4),
                )

            offer = preview()
            self.assertEqual(offer.source_revision, fixture.base_revision)
            self.assertEqual(
                tuple(item.path for item in offer.source_files),
                ("src/demo/__init__.py",),
            )
            (base / test_path).write_text("assert False\n")
            with self.assertRaisesRegex(ValueError, "dirty"):
                preview()
            (base / test_path).write_bytes(test_file.content)
            with self.assertRaisesRegex(ValueError, "custody"):
                preview("changed plan")

            class Generator:
                calls = 0

                async def generate(
                    self, offer: G4InitialChildOffer
                ) -> SignedG4InitialChildProposal:
                    self.calls += 1
                    proposal = G4InitialChildProposal(
                        offer_sha256=offer.offer_sha256,
                        replacements=(
                            _file(
                                "src/demo/__init__.py",
                                b"def add(left, right):\n    return left + right\n",
                            ),
                        ),
                        usage=G4CorrectionChildUsage(
                            input_tokens=20,
                            output_tokens=30,
                            tool_calls=0,
                            seconds=1,
                            microusd=3,
                        ),
                        unresolved_issue_count=0,
                    )
                    return sign_initial_child_proposal(
                        proposal, "child", fixture.child_key
                    )

            def execute(
                _args: tuple[str, ...], payload: bytes, timeout: float
            ) -> bytes:
                job = G4InitialChildJob.model_validate_json(payload)
                self.assertEqual(job.offer, offer)
                self.assertGreater(timeout, 0)
                return subprocess.run(
                    [sys.executable, "-m", "mos_eisley.run.reviewer_initial_child"],
                    input=payload,
                    capture_output=True,
                    timeout=10,
                    check=True,
                ).stdout

            store = root / "claims"
            store.mkdir(mode=0o700)
            container = OfflineContainer(
                Path("/usr/bin/docker"), IMAGE, root / "lifecycle"
            )
            generator = Generator()

            def dispatch() -> None:
                receipt = asyncio.run(
                    dispatch_initial_child(
                        policy=fixture.policy,
                        creator=fixture.creator,
                        custody=fixture.reviewer,
                        assignment=fixture.assignment,
                        package=fixture.package,
                        approval=signed,
                        repository_root=base,
                        git_executable=fixture.git,
                        approved_plan="approved plan",
                        brief="child brief",
                        acceptance_criteria="acceptance criteria",
                        container=container,
                        dispatch_store=store,
                        generator=generator,
                        now=NOW + timedelta(minutes=4),
                    )
                )
                self.assertEqual(
                    receipt.execution.changed_paths, ("src/demo/__init__.py",)
                )
                verify_initial_child_dispatch_receipt(
                    receipt,
                    policy=fixture.policy,
                    creator=fixture.creator,
                    custody=fixture.reviewer,
                    assignment=fixture.assignment,
                    package=fixture.package,
                    repository_root=base,
                    git_executable=fixture.git,
                    approved_plan="approved plan",
                    brief="child brief",
                    acceptance_criteria="acceptance criteria",
                    container=container,
                    dispatch_store=store,
                )

            with patch.object(container, "execute", side_effect=execute):
                dispatch()
                with self.assertRaises(FileExistsError):
                    dispatch()
            self.assertEqual(generator.calls, 1)


if __name__ == "__main__":
    unittest.main()
