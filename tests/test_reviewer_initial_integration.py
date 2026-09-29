"""Isolated Git integration and one-use record checks for an initial child."""

# pyright: reportPrivateUsage=false, reportArgumentType=false

from __future__ import annotations

import subprocess
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import patch

from test_reviewer_provenance import IMAGE, NOW, G4ProvenanceFixture

from mos_eisley.core.models import digest
from mos_eisley.reviewer_correction_dispatch import (
    G4CorrectionChildUsage,
    _source_file,
)
from mos_eisley.reviewer_initial_child import (
    G4InitialChildDispatchApproval,
    G4InitialChildDispatchReceipt,
    G4InitialChildOffer,
    G4InitialChildProposal,
    sign_initial_child_dispatch_approval,
    sign_initial_child_proposal,
    validate_initial_child_proposal,
)
from mos_eisley.reviewer_initial_coding_broker import G4ProductionInitialChildReceipt
from mos_eisley.reviewer_initial_integration import (
    G4InitialIntegrationApproval,
    _worktree_name,
    integrate_initial_child,
    sign_initial_integration_approval,
    sign_initial_integration_record,
    verify_initial_integration_record,
)
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.spend_ledger import SpendLedger


class InitialIntegrationTests(unittest.TestCase):
    def test_exact_child_bytes_enter_only_new_worktree_once(self) -> None:
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            fixture = G4ProvenanceFixture(folder, single_operator=True)
            source = folder / "source"
            subprocess.run(
                [
                    str(fixture.git),
                    "-C",
                    str(fixture.repository),
                    "worktree",
                    "add",
                    "--detach",
                    str(source),
                    fixture.base_revision,
                ],
                check=True,
                capture_output=True,
            )
            path = "src/demo/__init__.py"
            original = _source_file(path, (source / path).read_bytes())
            replacement = _source_file(
                path, b"def add(left, right):\n    return left + right\n"
            )
            order = G4InitialChildDispatchApproval(
                dispatch_id="initial-integration-dispatch",
                policy_sha256=fixture.policy.policy_sha256,
                creator_approval_sha256=fixture.creator.artifact_sha256,
                reviewer_custody_sha256=fixture.reviewer.artifact_sha256,
                assignment_sha256=fixture.assignment.artifact_sha256,
                source_revision=fixture.base_revision,
                container_image_id=IMAGE,
                child_signer_id="child",
                brief_sha256=digest(b"brief"),
                acceptance_criteria_sha256=digest(b"criteria"),
                creator_test_bundle_sha256=digest(b"tests"),
                owned_paths=(path,),
                issued_at=NOW + timedelta(minutes=3),
                expires_at=NOW + timedelta(minutes=10),
            )
            signed_order = sign_initial_child_dispatch_approval(
                order, "creator", fixture.creator_key
            )
            offer = G4InitialChildOffer(
                dispatch_approval_sha256=signed_order.artifact_sha256,
                assignment_sha256=fixture.assignment.artifact_sha256,
                source_revision=fixture.base_revision,
                child_signer_id="child",
                approved_plan="approved plan",
                brief="brief",
                acceptance_criteria="criteria",
                source_files=(original,),
                creator_test_files=(
                    _source_file(
                        "tests/test_creator.py",
                        (source / "tests/test_creator.py").read_bytes(),
                    ),
                ),
                max_input_tokens=1000,
                max_output_tokens=500,
                max_tool_calls=1,
                max_seconds=60,
                max_microusd=1000,
            )
            child = sign_initial_child_proposal(
                G4InitialChildProposal(
                    offer_sha256=offer.offer_sha256,
                    replacements=(replacement,),
                    usage=G4CorrectionChildUsage(
                        input_tokens=20,
                        output_tokens=30,
                        tool_calls=0,
                        seconds=1,
                        microusd=3,
                    ),
                    unresolved_issue_count=0,
                ),
                "child",
                fixture.child_key,
            )
            dispatch = G4InitialChildDispatchReceipt(
                approval=signed_order,
                offer=offer,
                signed_proposal=child,
                execution=validate_initial_child_proposal(offer, child, fixture.policy),
                dispatched_at=NOW + timedelta(minutes=4),
            )
            store = folder / "integration"
            store.mkdir(mode=0o700)
            approval = G4InitialIntegrationApproval(
                integration_id="initial-integration-one",
                policy_sha256=fixture.policy.policy_sha256,
                assignment_sha256=fixture.assignment.artifact_sha256,
                child_dispatch_receipt_sha256=dispatch.receipt_sha256,
                production_receipt_sha256=digest(b"production"),
                source_revision=fixture.base_revision,
                target_root_sha256=digest(str(source).encode()),
                integration_store_sha256=digest(str(store).encode()),
                owned_paths=(path,),
                issued_at=NOW + timedelta(minutes=5),
                expires_at=NOW + timedelta(minutes=10),
            )
            signed = sign_initial_integration_approval(
                approval, "creator", fixture.creator_key
            )
            production = cast(G4ProductionInitialChildReceipt, object())
            ledger = cast(SpendLedger, object())
            container = OfflineContainer(fixture.git, IMAGE, folder / "lifecycle")
            arguments = dict(
                dispatch=dispatch,
                production=production,
                policy=fixture.policy,
                creator=fixture.creator,
                custody=fixture.reviewer,
                assignment=fixture.assignment,
                package=fixture.package,
                repository_root=source,
                git_executable=fixture.git,
                approved_plan="approved plan",
                brief="brief",
                acceptance_criteria="criteria",
                container=container,
                dispatch_store=folder / "claims",
                production_store=folder / "paid",
                ledger=ledger,
                integration_store=store,
            )
            name = _worktree_name(approval)
            with patch(
                "mos_eisley.reviewer_initial_integration._check_inputs",
                return_value=(source.resolve(), store.resolve(), name),
            ):
                record = integrate_initial_child(
                    signed=signed, now=NOW + timedelta(minutes=6), **arguments
                )
                self.assertEqual(
                    (store / name / path).read_bytes(), replacement.content
                )
                self.assertEqual((source / path).read_bytes(), original.content)
                self.assertEqual(record.changed_paths, (path,))
                vcs = sign_initial_integration_record(
                    record, "creator", fixture.creator_key
                )
                verify_initial_integration_record(vcs, **arguments)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    integrate_initial_child(
                        signed=signed, now=NOW + timedelta(minutes=7), **arguments
                    )
                (store / name / path).write_text("tampered\n")
                with self.assertRaisesRegex(ValueError, "lineage"):
                    verify_initial_integration_record(vcs, **arguments)


if __name__ == "__main__":
    unittest.main()
