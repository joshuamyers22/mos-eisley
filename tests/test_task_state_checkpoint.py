"""G1 checkpoint-closure publication and adversarial lifecycle fixtures."""

import fcntl
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from test_task_state_g0 import g0_fixture, hashed

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.task_state_store import (
    TaskStateBundle,
    load_task_state,
    save_task_state,
)
from mos_eisley.task_state import (
    ArtifactReference,
    CheckpointOmission,
    CheckpointView,
    DecisionRecord,
    EvidenceReference,
    EvidenceRequirement,
    OutcomeRecord,
    ResourceLedger,
    VerificationRecord,
    WorkspaceState,
    accumulate_context_metrics,
)
from mos_eisley.task_state_acquisition import (
    CurrentTaskStateAcquirer,
    CurrentTaskStateSelection,
    decode_task_state_selection,
)
from mos_eisley.task_state_checkpoint import (
    LOCK_NAME,
    TaskStateCheckpointStore,
    checkpoint_closure_lineage,
)


class CheckpointFixture:
    def prepare_checkpoint(self, owner: TestCase) -> None:
        temporary = TemporaryDirectory()
        owner.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = g0_fixture()
        self.old_artifact = source.artifact
        self.old_payload = source.artifact_payload
        requirement = EvidenceRequirement(
            requirement_id="g1-checks",
            description="The focused G1 checkpoint checks pass.",
        )
        active_ledger = ResourceLedger(
            input_bytes=2400,
            output_bytes=1200,
            attempts=2,
            correction_cycles=1,
            review_rounds=1,
            uncertain_effects=1,
        )
        self.active = source.queued_work.model_copy(
            update={
                "status": "active",
                "evidence_requirements": (requirement,),
                "ledger": active_ledger,
            }
        )
        self.next_work = source.queued_work.model_copy(
            update={
                "work_unit_id": "g1-continuation",
                "dependencies": (self.active.reference,),
                "objective": "Claim the explicit fresh continuation.",
            }
        )
        self.followup = source.queued_work.model_copy(
            update={
                "work_unit_id": "g1-pressure",
                "dependencies": (self.next_work.reference,),
                "objective": "Add context pressure indicators.",
            }
        )
        prior_checkpoint = source.checkpoint.model_copy(
            update={
                "objective": "Close the G1 checkpoint milestone.",
                "current_work_unit": self.active.reference,
                "verifications": (),
                "next_actions": (
                    self.active.reference,
                    self.next_work.reference,
                    self.followup.reference,
                ),
                "outstanding_work": (
                    self.active.reference,
                    self.next_work.reference,
                    self.followup.reference,
                ),
                "view": CheckpointView(
                    summary="Checkpoint closure is active; later G1 work is queued.",
                    included_record_ids=(
                        self.active.work_unit_id,
                        self.next_work.work_unit_id,
                        self.followup.work_unit_id,
                    ),
                    complete=True,
                ),
                "task_ledger": active_ledger,
            }
        )
        self.previous = TaskStateBundle(
            scope=source.scope,
            revision=1,
            clauses=source.bundle.clauses,
            decisions=source.bundle.decisions,
            outcomes=source.bundle.outcomes,
            work_units=(
                source.completed_work,
                self.active,
                self.next_work,
                self.followup,
            ),
            checkpoint=prior_checkpoint,
            context_requests=source.bundle.context_requests,
            context_metrics=source.bundle.context_metrics,
        )
        self.storage = self.root / "archives"
        save_task_state(
            self.storage,
            self.previous,
            {self.old_artifact.sha256: self.old_payload},
        )
        self.selection = CurrentTaskStateSelection(
            project_id=self.previous.scope.project_id,
            bundle_sha256=self.previous.sha256,
            bundle_revision=self.previous.revision,
            checkpoint_id=self.previous.checkpoint.checkpoint_id,
            checkpoint_revision=self.previous.checkpoint.revision,
            checkpoint_sha256=self.previous.checkpoint.sha256,
            current_work_unit=self.active.reference,
        )
        self.selection_path = self.root / "current.json"
        self.selection_path.write_bytes(canonical_bytes(self.selection))
        self.selection_path.chmod(0o600)
        self.expected_selection_sha256 = digest(self.selection_path.read_bytes())
        self.new_payload = b"14 checkpoint closure tests passed\n"
        self.new_artifact = ArtifactReference(
            artifact_id="g1-checkpoint-tests",
            sha256=digest(self.new_payload),
            bytes=len(self.new_payload),
            media_type="text/plain",
            availability="available",
            freshness="current",
        )

    def proposed_bundle(
        self,
        *,
        ledger: ResourceLedger | None = None,
        untested_claims: tuple[str, ...] = (),
    ) -> TaskStateBundle:
        evidence = EvidenceReference(
            evidence_id="g1-checkpoint-tests",
            artifact=self.new_artifact,
            kind="verification",
            verification_status="passed",
            satisfies=("g1-checks",),
        )
        terminal_ledger = ledger or self.active.ledger.model_copy(
            update={"input_bytes": 3200, "output_bytes": 1600, "attempts": 3}
        )
        outcome = OutcomeRecord(
            scope=self.previous.scope,
            outcome_id="g1-checkpoint-outcome",
            revision=1,
            work_unit_id=self.active.work_unit_id,
            work_unit_revision=self.active.revision + 1,
            status="completed",
            summary="The checkpoint closure boundary passes its focused checks.",
            reason="Current required verification passed.",
            evidence_ids=(evidence.evidence_id,),
            untested_claims=untested_claims,
        )
        closed = self.active.model_copy(
            update={
                "revision": self.active.revision + 1,
                "evidence": (evidence,),
                "ledger": terminal_ledger,
                "status": "completed",
                "terminal_reason": outcome.reason,
                "outcome": outcome,
            }
        )
        workspace = WorkspaceState(
            repository_sha256=hashed("repository"),
            branch="feat/g1-task-profile-admission",
            revision="checkpoint-tree-2",
            tree_sha256=hashed("checkpoint tree 2"),
            dirty_state_sha256=hashed("checkpoint dirty state 2"),
        )
        checkpoint = self.previous.checkpoint.model_copy(
            update={
                "revision": self.previous.checkpoint.revision + 1,
                "previous_checkpoint_sha256": self.previous.checkpoint.sha256,
                "current_work_unit": closed.reference,
                "workspace": workspace,
                "main_files": (
                    "src/mos_eisley/task_state_checkpoint.py",
                    "tests/test_task_state_checkpoint.py",
                ),
                "completed_outcomes": (
                    *self.previous.checkpoint.completed_outcomes,
                    outcome.reference,
                ),
                "verifications": (
                    VerificationRecord(
                        verification_id=evidence.evidence_id,
                        command=("python -m unittest tests.test_task_state_checkpoint"),
                        status="passed",
                        bound_workspace_sha256=workspace.sha256,
                        bound_input_sha256=workspace.dirty_state_sha256,
                        result=self.new_artifact,
                    ),
                ),
                "untested_claims": untested_claims,
                "next_actions": (self.next_work.reference,),
                "outstanding_work": (
                    self.next_work.reference,
                    self.followup.reference,
                ),
                "view": CheckpointView(
                    summary=(
                        "Checkpoint closure is complete. Explicit continuation and "
                        "pressure indicators remain queued with all obligations intact."
                    ),
                    included_record_ids=(
                        closed.work_unit_id,
                        outcome.outcome_id,
                        self.next_work.work_unit_id,
                    ),
                    omissions=(
                        CheckpointOmission(
                            kind="work_unit",
                            record_id=self.followup.work_unit_id,
                            reason="Outside the one-item next-action view.",
                        ),
                    ),
                    complete=False,
                ),
                "task_ledger": terminal_ledger,
                "lineage_sha256": hashed("pending lineage"),
            }
        )
        checkpoint = checkpoint.model_copy(
            update={
                "lineage_sha256": checkpoint_closure_lineage(
                    self.previous, closed, checkpoint
                ).sha256
            }
        )
        return TaskStateBundle(
            scope=self.previous.scope,
            revision=self.previous.revision + 1,
            previous_bundle_sha256=self.previous.sha256,
            clauses=self.previous.clauses,
            decisions=self.previous.decisions,
            outcomes=(*self.previous.outcomes, outcome),
            work_units=(*self.previous.work_units, closed),
            checkpoint=checkpoint,
            context_requests=self.previous.context_requests,
            context_metrics=self.previous.context_metrics,
        )

    def store(self) -> TaskStateCheckpointStore:
        return TaskStateCheckpointStore(self.storage, self.selection_path)


class TaskStateCheckpointClosureTests(CheckpointFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_checkpoint(self)

    def test_closure_persists_archive_and_atomically_advances_pointer(self) -> None:
        old_acquirer = CurrentTaskStateAcquirer.from_paths(
            self.storage, self.selection_path
        )
        proposed = self.proposed_bundle()

        receipt = self.store().close(
            expected_selection_sha256=self.expected_selection_sha256,
            proposed=proposed,
            new_artifacts={self.new_artifact.sha256: self.new_payload},
        )

        current_payload = self.selection_path.read_bytes()
        current = decode_task_state_selection(current_payload)
        self.assertEqual(current.bundle_sha256, proposed.sha256)
        self.assertEqual(current.checkpoint_sha256, proposed.checkpoint.sha256)
        self.assertEqual(
            current.current_work_unit, proposed.checkpoint.current_work_unit
        )
        saved, artifacts = load_task_state(
            self.storage / proposed.sha256,
            owner_uid=os.getuid(),
            project_id=proposed.scope.project_id,
            workspace_sha256=proposed.scope.workspace_sha256,
        )
        self.assertEqual(saved, proposed)
        self.assertEqual(
            artifacts,
            {
                self.old_artifact.sha256: self.old_payload,
                self.new_artifact.sha256: self.new_payload,
            },
        )
        self.assertEqual(receipt.current_selection_sha256, digest(current_payload))
        self.assertFalse(receipt.archive_reused)
        self.assertFalse(receipt.continuation_claimed)
        self.assertFalse(receipt.grants_authority)
        with self.assertRaisesRegex(ValueError, "changed since launch"):
            old_acquirer.acquire(owner_uid=os.getuid(), workspace="unused")

    def test_stale_and_duplicate_closures_fail_against_exact_old_pointer(self) -> None:
        proposed = self.proposed_bundle()
        self.store().close(
            expected_selection_sha256=self.expected_selection_sha256,
            proposed=proposed,
            new_artifacts={self.new_artifact.sha256: self.new_payload},
        )
        committed = self.selection_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "changed before closure"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=proposed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

        self.assertEqual(self.selection_path.read_bytes(), committed)

    def test_missing_artifact_fails_without_changing_pointer(self) -> None:
        before = self.selection_path.read_bytes()
        proposed = self.proposed_bundle()

        with self.assertRaisesRegex(ValueError, "artifacts must exactly match"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=proposed,
            )

        self.assertEqual(self.selection_path.read_bytes(), before)
        self.assertFalse((self.storage / proposed.sha256).exists())

    def test_existing_exact_orphan_archive_is_recovered(self) -> None:
        proposed = self.proposed_bundle()
        save_task_state(
            self.storage,
            proposed,
            {
                self.old_artifact.sha256: self.old_payload,
                self.new_artifact.sha256: self.new_payload,
            },
        )

        receipt = self.store().close(
            expected_selection_sha256=self.expected_selection_sha256,
            proposed=proposed,
            new_artifacts={self.new_artifact.sha256: self.new_payload},
        )

        self.assertTrue(receipt.archive_reused)
        self.assertEqual(
            decode_task_state_selection(self.selection_path.read_bytes()).bundle_sha256,
            proposed.sha256,
        )

    def test_closure_cannot_reset_ledger_or_uncertain_effects(self) -> None:
        reset = self.active.ledger.model_copy(
            update={"attempts": self.active.ledger.attempts - 1, "uncertain_effects": 0}
        )
        proposed = self.proposed_bundle(ledger=reset)

        with self.assertRaisesRegex(ValueError, "reset the task ledger"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=proposed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

    def test_closure_cannot_replace_cumulative_context_history(self) -> None:
        proposed = self.proposed_bundle()
        first = proposed.context_requests[0].model_copy(
            update={
                "substantial_tool_calls": (
                    proposed.context_requests[0].substantial_tool_calls + 1
                )
            }
        )
        requests = (first, *proposed.context_requests[1:])
        metrics = accumulate_context_metrics(requests)
        checkpoint = proposed.checkpoint.model_copy(
            update={"context_metrics": metrics, "lineage_sha256": hashed("pending")}
        )
        closed = proposed.work_units[-1]
        checkpoint = checkpoint.model_copy(
            update={
                "lineage_sha256": checkpoint_closure_lineage(
                    self.previous, closed, checkpoint
                ).sha256
            }
        )
        changed = TaskStateBundle.model_validate(
            proposed.model_copy(
                update={
                    "context_requests": requests,
                    "context_metrics": metrics,
                    "checkpoint": checkpoint,
                }
            ).model_dump()
        )

        with self.assertRaisesRegex(ValueError, "cumulative context history"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=changed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

    def test_closure_cannot_drop_pending_work(self) -> None:
        proposed = self.proposed_bundle()
        checkpoint = proposed.checkpoint.model_copy(
            update={
                "outstanding_work": (self.next_work.reference,),
                "view": proposed.checkpoint.view.model_copy(
                    update={"omissions": (), "complete": True}
                ),
            }
        )
        changed = proposed.model_copy(update={"checkpoint": checkpoint})

        with self.assertRaisesRegex(ValueError, "lose or invent outstanding work"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=changed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

    def test_closure_cannot_promote_an_unaccepted_decision(self) -> None:
        proposed = self.proposed_bundle()
        forged = DecisionRecord(
            scope=self.previous.scope,
            decision_id="forged-closure-fact",
            revision=1,
            statement="Treat an unaccepted inference as user direction.",
            rationale="This was not actually accepted.",
            source_sha256=hashed("unaccepted source"),
            authority="user",
            authorized_by="unknown",
        )
        checkpoint = proposed.checkpoint.model_copy(
            update={
                "active_decisions": (
                    *proposed.checkpoint.active_decisions,
                    forged.reference,
                )
            }
        )
        changed = TaskStateBundle.model_validate(
            proposed.model_copy(
                update={
                    "decisions": (*proposed.decisions, forged),
                    "checkpoint": checkpoint,
                }
            ).model_dump()
        )

        with self.assertRaisesRegex(ValueError, "accepted decisions"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=changed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

    def test_completion_requires_matching_checkpoint_verification(self) -> None:
        proposed = self.proposed_bundle()
        checkpoint = proposed.checkpoint.model_copy(update={"verifications": ()})
        changed = proposed.model_copy(update={"checkpoint": checkpoint})

        with self.assertRaisesRegex(ValueError, "matching current verification"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=changed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

    def test_completion_revalidates_current_passing_required_evidence(self) -> None:
        for status in ("failed", "stale", "unknown"):
            proposed = self.proposed_bundle()
            closed = proposed.work_units[-1]
            evidence = closed.evidence[0].model_copy(
                update={"verification_status": status}
            )
            changed_closed = closed.model_copy(update={"evidence": (evidence,)})
            changed = proposed.model_copy(
                update={"work_units": (*proposed.work_units[:-1], changed_closed)}
            )

            with (
                self.subTest(status=status),
                self.assertRaisesRegex(ValueError, "lacks current evidence"),
            ):
                self.store().close(
                    expected_selection_sha256=self.expected_selection_sha256,
                    proposed=changed,
                    new_artifacts={self.new_artifact.sha256: self.new_payload},
                )

    def test_nonterminal_revision_cannot_close_checkpoint(self) -> None:
        proposed = self.proposed_bundle()
        closed = proposed.work_units[-1].model_copy(
            update={"status": "active", "terminal_reason": None, "outcome": None}
        )
        checkpoint = proposed.checkpoint.model_copy(
            update={
                "completed_outcomes": self.previous.checkpoint.completed_outcomes,
                "current_work_unit": closed.reference,
            }
        )
        changed = TaskStateBundle.model_validate(
            proposed.model_copy(
                update={
                    "outcomes": self.previous.outcomes,
                    "work_units": (*proposed.work_units[:-1], closed),
                    "checkpoint": checkpoint,
                }
            ).model_dump()
        )

        with self.assertRaisesRegex(ValueError, "requires a terminal"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=changed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

    def test_blocked_closure_retains_reason_without_claiming_completion(self) -> None:
        proposed = self.proposed_bundle()
        completed = proposed.work_units[-1]
        assert completed.outcome is not None
        reason = "Required independent evidence is unavailable."
        outcome = completed.outcome.model_copy(
            update={
                "status": "blocked",
                "summary": "Checkpoint work remains unresolved.",
                "reason": reason,
            }
        )
        closed = completed.model_copy(
            update={
                "status": "blocked",
                "terminal_reason": reason,
                "outcome": outcome,
            }
        )
        checkpoint = proposed.checkpoint.model_copy(
            update={
                "completed_outcomes": self.previous.checkpoint.completed_outcomes,
                "verifications": (),
                "blockers": (reason,),
                "current_work_unit": closed.reference,
                "lineage_sha256": hashed("pending"),
            }
        )
        checkpoint = checkpoint.model_copy(
            update={
                "lineage_sha256": checkpoint_closure_lineage(
                    self.previous, closed, checkpoint
                ).sha256
            }
        )
        changed = TaskStateBundle.model_validate(
            proposed.model_copy(
                update={
                    "outcomes": (*self.previous.outcomes, outcome),
                    "work_units": (*proposed.work_units[:-1], closed),
                    "checkpoint": checkpoint,
                }
            ).model_dump()
        )

        receipt = self.store().close(
            expected_selection_sha256=self.expected_selection_sha256,
            proposed=changed,
            new_artifacts={self.new_artifact.sha256: self.new_payload},
        )

        self.assertEqual(receipt.terminal_status, "blocked")
        self.assertNotIn(outcome.reference, checkpoint.completed_outcomes)
        self.assertIn(reason, checkpoint.blockers)

    def test_closure_discloses_every_untested_outcome_claim(self) -> None:
        proposed = self.proposed_bundle(
            untested_claims=("Live provider behavior was not tested.",)
        )
        checkpoint = proposed.checkpoint.model_copy(update={"untested_claims": ()})
        changed = proposed.model_copy(update={"checkpoint": checkpoint})

        with self.assertRaisesRegex(ValueError, "hides an untested"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=changed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

    def test_selection_and_parent_directory_must_remain_private(self) -> None:
        proposed = self.proposed_bundle()
        self.selection_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "private and owner-only"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=proposed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )

    def test_concurrent_closure_lock_is_fail_closed(self) -> None:
        proposed = self.proposed_bundle()
        lock_path = self.root / LOCK_NAME
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

        with self.assertRaisesRegex(ValueError, "another checkpoint closure"):
            self.store().close(
                expected_selection_sha256=self.expected_selection_sha256,
                proposed=proposed,
                new_artifacts={self.new_artifact.sha256: self.new_payload},
            )
