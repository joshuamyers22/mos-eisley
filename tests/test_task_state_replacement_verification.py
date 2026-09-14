"""Changed-tree replacement-verification acceptance demonstration."""

import os
import subprocess
import sys
from unittest import TestCase

from test_task_state_continuation import (
    SESSION_A,
    SESSION_B,
    ContinuationFixture,
    FixedInspector,
)

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.task_state_store import (
    TaskStateBundle,
    load_task_state,
    save_task_state,
)
from mos_eisley.task_state import (
    CheckpointView,
    EvidenceReference,
    EvidenceRequirement,
    OutcomeRecord,
    VerificationRecord,
)
from mos_eisley.task_state_acquisition import (
    CurrentTaskStateSelection,
    decode_task_state_selection,
)
from mos_eisley.task_state_checkpoint import checkpoint_closure_lineage
from mos_eisley.task_state_continuation import (
    FreshContextContinuationAcquirer,
    GitWorkspaceInspector,
    WorkspaceInspection,
)
from mos_eisley.task_state_replacement_verification import (
    ChangedTreeReplacementVerificationStore,
)


class ReplacementVerificationFixture(ContinuationFixture):
    def prepare_replacement_verification(self, owner: TestCase) -> None:
        self.prepare_continuation(owner)
        requirement = EvidenceRequirement(
            requirement_id="changed-tree-tests",
            description="Replacement tests pass against the changed workspace.",
        )
        self.next_work = self.next_work.model_copy(
            update={"evidence_requirements": (requirement,)}
        )
        self.proposed = self.proposed.model_copy(
            update={
                "work_units": tuple(
                    self.next_work
                    if item.reference == self.next_work.reference
                    else item
                    for item in self.proposed.work_units
                )
            }
        )
        subprocess.run(("git", "init", "-q", str(self.workspace)), check=True)
        subprocess.run(
            (
                "git",
                "-C",
                str(self.workspace),
                "config",
                "user.email",
                "fixture@example.test",
            ),
            check=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.workspace),
                "config",
                "user.name",
                "Fixture",
            ),
            check=True,
        )
        source_name, test_name = self.proposed.checkpoint.main_files
        source_path = self.workspace / source_name
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("VALUE = 1\n")
        test_path = self.workspace / test_name
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(
            "from pathlib import Path\n"
            f'assert Path("{source_name}").read_text() == "VALUE = 1\\n"\n'
            'print("checkpoint verification passed")\n'
        )
        subprocess.run(("git", "-C", str(self.workspace), "add", "."), check=True)
        subprocess.run(
            ("git", "-C", str(self.workspace), "commit", "-qm", "checkpoint"),
            check=True,
        )
        inspector = GitWorkspaceInspector()
        clean = inspector.inspect(self.workspace, self.proposed.checkpoint.main_files)
        current_closed = next(
            item
            for item in self.proposed.work_units
            if item.reference == self.proposed.checkpoint.current_work_unit
        )
        checkpoint = self.proposed.checkpoint.model_copy(
            update={
                "workspace": clean.workspace,
                "verifications": tuple(
                    item.model_copy(
                        update={
                            "bound_workspace_sha256": clean.workspace.sha256,
                            "bound_input_sha256": clean.workspace.dirty_state_sha256,
                        }
                    )
                    for item in self.proposed.checkpoint.verifications
                ),
                "lineage_sha256": digest(b"pending clean checkpoint lineage"),
            }
        )
        checkpoint = checkpoint.model_copy(
            update={
                "lineage_sha256": checkpoint_closure_lineage(
                    self.previous, current_closed, checkpoint
                ).sha256
            }
        )
        self.proposed = self.proposed.model_copy(update={"checkpoint": checkpoint})
        save_task_state(
            self.storage,
            self.proposed,
            {
                self.old_artifact.sha256: self.old_payload,
                self.new_artifact.sha256: self.new_payload,
            },
        )
        current = CurrentTaskStateSelection.model_validate_json(
            self.selection_path.read_bytes()
        )
        current = current.model_copy(
            update={
                "bundle_sha256": self.proposed.sha256,
                "checkpoint_sha256": self.proposed.checkpoint.sha256,
            }
        )
        self.selection_path.write_bytes(canonical_bytes(current))
        self.selection_path.chmod(0o600)
        self.continuation = self.continuation.model_copy(
            update={
                "checkpoint_sha256": self.proposed.checkpoint.sha256,
                "workspace": self.proposed.checkpoint.workspace,
            }
        )
        self.continuation_path.write_bytes(canonical_bytes(self.continuation))
        self.continuation_path.chmod(0o600)
        source_path.write_text("VALUE = 2\n")
        test_path.write_text(
            "from pathlib import Path\n"
            f'assert Path("{source_name}").read_text() == "VALUE = 2\\n"\n'
            'print("replacement verification passed")\n'
        )
        self.changed_inspection = inspector.inspect(
            self.workspace, self.proposed.checkpoint.main_files
        )
        task_state = FreshContextContinuationAcquirer.from_paths(
            self.storage,
            self.selection_path,
            self.continuation_path,
            self.claim_path,
            inspector=inspector,
        ).acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )
        self.stale_verification_ids = task_state.acquisition.stale_verification_ids
        verification = subprocess.run(
            (sys.executable, test_name),
            cwd=self.workspace,
            check=True,
            capture_output=True,
        )
        self.replacement_payload = verification.stdout
        self.replacement_command = f"{sys.executable} {test_name}"
        self.replacement_artifact = self.new_artifact.model_copy(
            update={
                "artifact_id": "changed-tree-replacement-tests",
                "sha256": digest(self.replacement_payload),
                "bytes": len(self.replacement_payload),
            }
        )

    def replacement_bundle(self) -> TaskStateBundle:
        evidence = EvidenceReference(
            evidence_id="changed-tree-replacement-tests",
            artifact=self.replacement_artifact,
            kind="verification",
            verification_status="passed",
            satisfies=("changed-tree-tests",),
        )
        ledger = self.proposed.checkpoint.task_ledger.model_copy(
            update={
                "input_bytes": self.proposed.checkpoint.task_ledger.input_bytes + 900,
                "output_bytes": self.proposed.checkpoint.task_ledger.output_bytes + 300,
                "attempts": self.proposed.checkpoint.task_ledger.attempts + 1,
            }
        )
        outcome = OutcomeRecord(
            scope=self.proposed.scope,
            outcome_id="changed-tree-replacement-outcome",
            revision=1,
            work_unit_id=self.next_work.work_unit_id,
            work_unit_revision=self.next_work.revision + 1,
            status="completed",
            summary="The changed tree passed current replacement verification.",
            reason="Replacement evidence is bound to the unchanged live workspace.",
            evidence_ids=(evidence.evidence_id,),
        )
        closed = self.next_work.model_copy(
            update={
                "revision": self.next_work.revision + 1,
                "evidence": (evidence,),
                "ledger": ledger,
                "status": "completed",
                "terminal_reason": outcome.reason,
                "outcome": outcome,
            }
        )
        stale_ids = set(self.stale_verification_ids)
        stale_history = tuple(
            item.model_copy(update={"status": "stale"})
            if item.verification_id in stale_ids
            else item
            for item in self.proposed.checkpoint.verifications
        )
        replacement = VerificationRecord(
            verification_id=evidence.evidence_id,
            command=self.replacement_command,
            status="passed",
            bound_workspace_sha256=self.changed_inspection.workspace.sha256,
            bound_input_sha256=self.changed_inspection.workspace.dirty_state_sha256,
            result=self.replacement_artifact,
        )
        checkpoint = self.proposed.checkpoint.model_copy(
            update={
                "revision": self.proposed.checkpoint.revision + 1,
                "previous_checkpoint_sha256": self.proposed.checkpoint.sha256,
                "current_work_unit": closed.reference,
                "workspace": self.changed_inspection.workspace,
                "completed_outcomes": (
                    *self.proposed.checkpoint.completed_outcomes,
                    outcome.reference,
                ),
                "verifications": (*stale_history, replacement),
                "next_actions": (self.followup.reference,),
                "outstanding_work": (self.followup.reference,),
                "view": CheckpointView(
                    summary=(
                        "Changed-tree passes were replaced; the remaining G1 "
                        "obligation stays queued."
                    ),
                    included_record_ids=(
                        closed.work_unit_id,
                        outcome.outcome_id,
                        self.followup.work_unit_id,
                    ),
                    complete=True,
                ),
                "task_ledger": ledger,
                "lineage_sha256": digest(b"pending replacement lineage"),
            }
        )
        checkpoint = checkpoint.model_copy(
            update={
                "lineage_sha256": checkpoint_closure_lineage(
                    self.proposed, closed, checkpoint
                ).sha256
            }
        )
        return TaskStateBundle(
            scope=self.proposed.scope,
            revision=self.proposed.revision + 1,
            previous_bundle_sha256=self.proposed.sha256,
            clauses=self.proposed.clauses,
            decisions=self.proposed.decisions,
            outcomes=(*self.proposed.outcomes, outcome),
            work_units=(*self.proposed.work_units, closed),
            checkpoint=checkpoint,
            context_requests=self.proposed.context_requests,
            context_metrics=self.proposed.context_metrics,
            profiles=self.proposed.profiles,
        )

    def replacement_store(
        self, *inspections: WorkspaceInspection
    ) -> ChangedTreeReplacementVerificationStore:
        arguments = (
            self.storage,
            self.workspace,
            self.selection_path,
            self.continuation_path,
            self.claim_path,
        )
        if inspections:
            return ChangedTreeReplacementVerificationStore.from_paths(
                *arguments, inspector=FixedInspector(list(inspections))
            )
        return ChangedTreeReplacementVerificationStore.from_paths(*arguments)


class ChangedTreeReplacementVerificationTests(ReplacementVerificationFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_replacement_verification(self)

    def test_changed_tree_passes_are_replaced_and_completion_is_published(self) -> None:
        before = self.selection_path.read_bytes()
        proposed = self.replacement_bundle()

        receipt = self.replacement_store().close(
            expected_selection_sha256=digest(before),
            session_id=SESSION_A,
            proposed=proposed,
            new_artifacts={self.replacement_artifact.sha256: self.replacement_payload},
        )

        selected = decode_task_state_selection(self.selection_path.read_bytes())
        saved, artifacts = load_task_state(
            self.storage / selected.bundle_sha256,
            owner_uid=os.getuid(),
            project_id=proposed.scope.project_id,
            workspace_sha256=proposed.scope.workspace_sha256,
        )
        self.assertEqual(saved, proposed)
        self.assertEqual(
            saved.work_units[: len(self.proposed.work_units)], self.proposed.work_units
        )
        self.assertEqual(saved.checkpoint.outstanding_work, (self.followup.reference,))
        self.assertEqual(saved.context_metrics, self.proposed.context_metrics)
        self.assertGreaterEqual(
            saved.checkpoint.task_ledger.attempts,
            self.proposed.checkpoint.task_ledger.attempts,
        )
        self.assertEqual(
            saved.checkpoint.verifications[0].status,
            "stale",
        )
        self.assertEqual(
            saved.checkpoint.verifications[-1].verification_id,
            "changed-tree-replacement-tests",
        )
        self.assertEqual(
            artifacts[self.replacement_artifact.sha256], self.replacement_payload
        )
        self.assertEqual(receipt.stale_verification_ids, self.stale_verification_ids)
        self.assertEqual(
            receipt.replacement_verification_ids,
            ("changed-tree-replacement-tests",),
        )
        self.assertEqual(receipt.remaining_outstanding_work, (self.followup.reference,))
        self.assertTrue(receipt.historical_passes_superseded)
        self.assertTrue(receipt.replacement_verification_current)
        self.assertFalse(receipt.grants_authority)
        self.assertTrue(self.claim_path.exists())

    def test_historical_pass_cannot_be_reused_on_the_changed_tree(self) -> None:
        before = self.selection_path.read_bytes()
        proposed = self.replacement_bundle()
        checkpoint = proposed.checkpoint.model_copy(
            update={
                "verifications": (
                    self.proposed.checkpoint.verifications[0],
                    proposed.checkpoint.verifications[-1],
                )
            }
        )
        blind = proposed.model_copy(update={"checkpoint": checkpoint})

        with self.assertRaisesRegex(ValueError, "stale passing verification"):
            self.replacement_store().close(
                expected_selection_sha256=digest(before),
                session_id=SESSION_A,
                proposed=blind,
                new_artifacts={
                    self.replacement_artifact.sha256: self.replacement_payload
                },
            )

        self.assertEqual(self.selection_path.read_bytes(), before)

    def test_completion_requires_a_new_replacement_verification(self) -> None:
        before = self.selection_path.read_bytes()
        proposed = self.replacement_bundle()
        checkpoint = proposed.checkpoint.model_copy(
            update={"verifications": proposed.checkpoint.verifications[:-1]}
        )
        missing = proposed.model_copy(update={"checkpoint": checkpoint})

        with self.assertRaisesRegex(ValueError, "matching current verification"):
            self.replacement_store().close(
                expected_selection_sha256=digest(before),
                session_id=SESSION_A,
                proposed=missing,
                new_artifacts={
                    self.replacement_artifact.sha256: self.replacement_payload
                },
            )

        self.assertEqual(self.selection_path.read_bytes(), before)

    def test_replacement_must_bind_the_exact_live_input(self) -> None:
        before = self.selection_path.read_bytes()
        proposed = self.replacement_bundle()
        replacement = proposed.checkpoint.verifications[-1].model_copy(
            update={"bound_input_sha256": digest(b"different live input")}
        )
        checkpoint = proposed.checkpoint.model_copy(
            update={
                "verifications": (
                    *proposed.checkpoint.verifications[:-1],
                    replacement,
                )
            }
        )
        stale = proposed.model_copy(update={"checkpoint": checkpoint})

        with self.assertRaisesRegex(ValueError, "not current for the live tree"):
            self.replacement_store().close(
                expected_selection_sha256=digest(before),
                session_id=SESSION_A,
                proposed=stale,
                new_artifacts={
                    self.replacement_artifact.sha256: self.replacement_payload
                },
            )

        self.assertEqual(self.selection_path.read_bytes(), before)

    def test_wrong_session_cannot_publish_claimed_replacement(self) -> None:
        before = self.selection_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "differs from its continuation claim"):
            self.replacement_store().close(
                expected_selection_sha256=digest(before),
                session_id=SESSION_B,
                proposed=self.replacement_bundle(),
                new_artifacts={
                    self.replacement_artifact.sha256: self.replacement_payload
                },
            )
        self.assertEqual(self.selection_path.read_bytes(), before)

    def test_workspace_race_leaves_pointer_on_the_previous_checkpoint(self) -> None:
        before = self.selection_path.read_bytes()
        later = self.changed_inspection.model_copy(
            update={
                "workspace": self.changed_inspection.workspace.model_copy(
                    update={"dirty_state_sha256": digest(b"later workspace change")}
                )
            }
        )

        with self.assertRaisesRegex(ValueError, "changed during replacement"):
            self.replacement_store(self.changed_inspection, later).close(
                expected_selection_sha256=digest(before),
                session_id=SESSION_A,
                proposed=self.replacement_bundle(),
                new_artifacts={
                    self.replacement_artifact.sha256: self.replacement_payload
                },
            )

        self.assertEqual(self.selection_path.read_bytes(), before)

    def test_continued_completion_cannot_reset_the_checkpoint_ledger(self) -> None:
        before = self.selection_path.read_bytes()
        proposed = self.replacement_bundle()
        closed = proposed.work_units[-1].model_copy(
            update={"ledger": self.next_work.ledger}
        )
        checkpoint = proposed.checkpoint.model_copy(
            update={"task_ledger": closed.ledger}
        )
        reset = proposed.model_copy(
            update={
                "work_units": (*proposed.work_units[:-1], closed),
                "checkpoint": checkpoint,
            }
        )

        with self.assertRaisesRegex(ValueError, "reset the checkpoint task ledger"):
            self.replacement_store().close(
                expected_selection_sha256=digest(before),
                session_id=SESSION_A,
                proposed=reset,
                new_artifacts={
                    self.replacement_artifact.sha256: self.replacement_payload
                },
            )

        self.assertEqual(self.selection_path.read_bytes(), before)
