"""Metadata authorization preserves the original child and counts one Git use."""

# pyright: reportPrivateUsage=false
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from test_reviewer_provenance import NOW, G4ProvenanceFixture

from mos_eisley.core.models import digest
from mos_eisley.reviewer_creator_metadata import (
    DECLARATION,
    G4CreatorMetadataAmendment,
    SignedG4CreatorMetadataAmendment,
    amend_creator_metadata_once,
    prepare_creator_metadata_amendment,
    sign_creator_metadata_amendment,
    sign_creator_metadata_record,
    verify_creator_metadata_amendment,
    verify_creator_metadata_record,
    verify_creator_metadata_record_signature,
)
from mos_eisley.reviewer_initial_integration import (
    G4InitialIntegrationApproval,
    G4InitialIntegrationRecord,
    sign_initial_integration_approval,
    sign_initial_integration_record,
)
from mos_eisley.reviewer_provenance import _git, _git_text


class CreatorMetadataTests(unittest.TestCase):
    def test_real_git_metadata_only_one_use_and_record_replay(self) -> None:
        with TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            f = G4ProvenanceFixture(folder, single_operator=True)
            parent = folder / "parent"
            _git(
                f.git,
                f.repository,
                ["worktree", "add", "--detach", str(parent), f.child_revision],
            )
            patch = _git(
                f.git,
                parent,
                [
                    "diff",
                    "--binary",
                    "--full-index",
                    "--no-color",
                    "--no-ext-diff",
                    "--no-renames",
                    f.base_revision,
                    f.child_revision,
                ],
            )
            grant = G4InitialIntegrationApproval(
                integration_id="initial",
                policy_sha256=f.policy.policy_sha256,
                assignment_sha256=f.assignment.artifact_sha256,
                child_dispatch_receipt_sha256=digest(b"dispatch"),
                production_receipt_sha256=digest(b"production"),
                source_revision=f.base_revision,
                target_root_sha256=digest(b"original"),
                integration_store_sha256=digest(b"parent-store"),
                owned_paths=("src/demo/__init__.py",),
                issued_at=NOW + timedelta(minutes=4),
                expires_at=NOW + timedelta(minutes=30),
            )
            record = G4InitialIntegrationRecord(
                approval=sign_initial_integration_approval(
                    grant, "creator", f.creator_key
                ),
                child_dispatch_receipt_sha256=digest(b"dispatch"),
                source_revision=f.base_revision,
                integrated_revision=f.child_revision,
                integrated_tree_id=_git_text(
                    f.git, parent, ["rev-parse", "HEAD^{tree}"]
                ),
                patch_sha256=digest(patch),
                patch_bytes=len(patch),
                worktree_name="parent",
                changed_paths=("src/demo/__init__.py",),
                integrated_at=NOW + timedelta(minutes=5),
            )
            vcs = sign_initial_integration_record(record, "creator", f.creator_key)
            store = folder / "metadata"
            store.mkdir(mode=0o700)
            at = NOW + timedelta(minutes=6)
            amendment = prepare_creator_metadata_amendment(
                amendment_id="metadata-1",
                policy=f.policy,
                creator=f.creator,
                custody=f.reviewer,
                vcs=vcs,
                parent_root=parent,
                store=store,
                git=f.git,
                issued=at,
                expires=at + timedelta(minutes=20),
            )
            signed = sign_creator_metadata_amendment(
                amendment, "creator", f.creator_key
            )

            def verify(
                candidate: SignedG4CreatorMetadataAmendment = signed,
                now: datetime = at,
            ) -> None:
                verify_creator_metadata_amendment(
                    candidate,
                    policy=f.policy,
                    creator=f.creator,
                    custody=f.reviewer,
                    vcs=vcs,
                    parent_root=parent,
                    store=store,
                    git=f.git,
                    now=now,
                )

            verify()
            with self.assertRaises(ValueError):
                verify(
                    sign_creator_metadata_amendment(
                        amendment, "creator", Ed25519PrivateKey.generate()
                    )
                )
            with self.assertRaises(ValueError):
                verify(now=at + timedelta(minutes=21))
            with self.assertRaises(ValidationError):
                G4CreatorMetadataAmendment.model_validate(
                    amendment.model_dump() | {"metadata_path": "tests/test_creator.py"}
                )
            with self.assertRaises(ValidationError):
                G4CreatorMetadataAmendment.model_validate(
                    amendment.model_dump() | {"metadata_content": "requests==1\n"}
                )
            (parent / "drift.txt").write_text("unauthorized")
            with self.assertRaises(ValueError):
                verify()
            (parent / "drift.txt").unlink()
            original = (parent / "src/demo/__init__.py").read_bytes()
            amended = amend_creator_metadata_once(
                signed,
                policy=f.policy,
                creator=f.creator,
                custody=f.reviewer,
                vcs=vcs,
                parent_root=parent,
                store=store,
                git=f.git,
                now=at + timedelta(minutes=1),
            )
            verify_creator_metadata_record(
                amended,
                policy=f.policy,
                creator=f.creator,
                custody=f.reviewer,
                vcs=vcs,
                parent_root=parent,
                store=store,
                git=f.git,
            )
            root = store / amended.worktree_name
            attested = sign_creator_metadata_record(amended, "creator", f.creator_key)
            verify_creator_metadata_record_signature(attested, f.policy)
            with self.assertRaises(ValueError):
                verify_creator_metadata_record_signature(
                    sign_creator_metadata_record(
                        amended, "creator", Ed25519PrivateKey.generate()
                    ),
                    f.policy,
                )
            self.assertEqual((root / "requirements.lock").read_text(), DECLARATION)
            self.assertEqual((root / "src/demo/__init__.py").read_bytes(), original)
            self.assertFalse((parent / "requirements.lock").exists())
            self.assertEqual(
                _git_text(f.git, parent, ["rev-parse", "HEAD"]), f.child_revision
            )
            with self.assertRaises(ValueError):
                amend_creator_metadata_once(
                    signed,
                    policy=f.policy,
                    creator=f.creator,
                    custody=f.reviewer,
                    vcs=vcs,
                    parent_root=parent,
                    store=store,
                    git=f.git,
                    now=at,
                )
            (root / "requirements.lock").write_text("tampered\n")
            with self.assertRaises(ValueError):
                verify_creator_metadata_record(
                    amended,
                    policy=f.policy,
                    creator=f.creator,
                    custody=f.reviewer,
                    vcs=vcs,
                    parent_root=parent,
                    store=store,
                    git=f.git,
                )
