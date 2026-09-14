"""Explicit fresh-context continuation and live-freshness fixtures."""

import fcntl
import json
import os
import stat
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic import JsonValue, ValidationError
from test_task_profile_admission import CapturingClient
from test_task_state_checkpoint import CheckpointFixture

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.task_state_store import TaskStateBundle, save_task_state
from mos_eisley.task_profile import conversation_workspace_sha256
from mos_eisley.task_state import (
    ContinuationSelection,
    ResourceLedger,
    accumulate_context_metrics,
)
from mos_eisley.task_state_acquisition import (
    CurrentTaskStateSelection,
    RuntimeTaskState,
)
from mos_eisley.task_state_checkpoint import TaskStateCheckpointStore
from mos_eisley.task_state_continuation import (
    LOCK_NAME as CONTINUATION_LOCK_NAME,
)
from mos_eisley.task_state_continuation import (
    ContinuationClaim,
    FreshContextContinuationAcquirer,
    GitWorkspaceInspector,
    RelevantFileInspection,
    WorkspaceInspection,
    continuation_claim_path,
    decode_continuation_selection,
)

SESSION_A = "a" * 32
SESSION_B = "b" * 32


def _replace_scope(value: JsonValue, *, workspace_sha256: str) -> JsonValue:
    if isinstance(value, list):
        return [
            _replace_scope(item, workspace_sha256=workspace_sha256) for item in value
        ]
    if not isinstance(value, dict):
        return value
    replaced = {
        key: _replace_scope(item, workspace_sha256=workspace_sha256)
        for key, item in value.items()
    }
    if {"owner_uid", "project_id", "workspace_sha256"} <= replaced.keys():
        replaced["owner_uid"] = os.getuid()
        replaced["project_id"] = "mos-eisley"
        replaced["workspace_sha256"] = workspace_sha256
    return replaced


@dataclass
class FixedInspector:
    inspections: list[WorkspaceInspection]
    calls: int = 0

    def inspect(
        self, workspace: Path, relevant_files: Sequence[str]
    ) -> WorkspaceInspection:
        selected = self.inspections[min(self.calls, len(self.inspections) - 1)]
        self.calls += 1
        return selected


class ContinuationFixture(CheckpointFixture):
    def prepare_continuation(self, owner: TestCase) -> None:
        self.prepare_checkpoint(owner)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        scope_sha256 = conversation_workspace_sha256(str(self.workspace.resolve()))
        previous_payload = _replace_scope(
            cast(dict[str, JsonValue], self.previous.model_dump(mode="json")),
            workspace_sha256=scope_sha256,
        )
        assert isinstance(previous_payload, dict)
        self.previous = TaskStateBundle.model_validate_json(
            json.dumps(previous_payload)
        )
        self.previous = self.previous.model_copy(
            update={
                "work_units": tuple(
                    item.model_copy(
                        update={
                            "required_inputs": tuple(
                                reference.model_copy(
                                    update={"sha256": self.old_artifact.sha256}
                                )
                                for reference in item.required_inputs
                            )
                        }
                    )
                    for item in self.previous.work_units
                )
            }
        )
        work = {item.work_unit_id: item for item in self.previous.work_units}
        self.active = work[self.active.work_unit_id]
        self.next_work = work[self.next_work.work_unit_id]
        self.followup = work[self.followup.work_unit_id]
        self.proposed = self.proposed_bundle()
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
            current_work_unit=self.previous.checkpoint.current_work_unit,
        )
        self.selection_path.write_bytes(canonical_bytes(self.selection))
        self.selection_path.chmod(0o600)
        TaskStateCheckpointStore(self.storage, self.selection_path).close(
            expected_selection_sha256=digest(self.selection_path.read_bytes()),
            proposed=self.proposed,
            new_artifacts={self.new_artifact.sha256: self.new_payload},
        )
        self.next_work = next(
            item
            for item in self.proposed.work_units
            if item.work_unit_id == "g1-continuation"
        )
        self.continuation = ContinuationSelection(
            scope=self.proposed.scope,
            checkpoint_id=self.proposed.checkpoint.checkpoint_id,
            checkpoint_revision=self.proposed.checkpoint.revision,
            checkpoint_sha256=self.proposed.checkpoint.sha256,
            selected_work_unit=self.next_work.reference,
            workspace=self.proposed.checkpoint.workspace,
            required_inputs=self.next_work.required_inputs,
            context_baseline=self.proposed.checkpoint.context_metrics,
            ledger_baseline=self.proposed.checkpoint.task_ledger,
        )
        self.continuation_path = self.root / "continue.json"
        self.continuation_path.write_bytes(canonical_bytes(self.continuation))
        self.continuation_path.chmod(0o600)
        self.claim_path = continuation_claim_path(self.storage, self.continuation)
        self.inspection = WorkspaceInspection(
            workspace=self.proposed.checkpoint.workspace,
            relevant_files=tuple(
                RelevantFileInspection(
                    path=path,
                    availability="available",
                    sha256=digest(path.encode()),
                    bytes=len(path.encode()),
                    changed_since_checkpoint=False,
                )
                for path in self.proposed.checkpoint.main_files
            ),
        )

    def acquirer(
        self, *inspections: WorkspaceInspection
    ) -> FreshContextContinuationAcquirer:
        return FreshContextContinuationAcquirer.from_paths(
            self.storage,
            self.selection_path,
            self.continuation_path,
            self.claim_path,
            inspector=FixedInspector(list(inspections or (self.inspection,))),
        )


class FreshContextContinuationTests(ContinuationFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_continuation(self)

    def test_exact_selection_is_claimed_and_materializes_outstanding_work(self) -> None:
        task_state = self.acquirer().acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )

        self.assertEqual(task_state.current_work_unit, self.next_work)
        self.assertEqual(
            task_state.checkpoint.outstanding_work,
            self.proposed.checkpoint.outstanding_work,
        )
        self.assertEqual(
            task_state.checkpoint.task_ledger,
            self.proposed.checkpoint.task_ledger,
        )
        self.assertTrue(task_state.acquisition.continuation_claimed)
        self.assertTrue(task_state.acquisition.live_workspace_freshness_verified)
        self.assertTrue(task_state.acquisition.freshness_ready)
        self.assertEqual(task_state.acquisition.stale_verification_ids, ())
        self.assertFalse(task_state.grants_authority)
        claim = ContinuationClaim.model_validate_json(self.claim_path.read_bytes())
        self.assertEqual(claim.session_id, SESSION_A)
        self.assertEqual(claim.selected_work_unit_id, self.next_work.work_unit_id)
        self.assertFalse(claim.grants_authority)
        self.assertEqual(stat.S_IMODE(self.claim_path.stat().st_mode), 0o600)

    def test_same_session_retry_is_idempotent(self) -> None:
        acquirer = self.acquirer()
        first = acquirer.acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )
        payload = self.claim_path.read_bytes()
        second = acquirer.acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )

        self.assertEqual(second, first)
        self.assertEqual(self.claim_path.read_bytes(), payload)

    def test_duplicate_session_cannot_reuse_the_claim(self) -> None:
        acquirer = self.acquirer()
        acquirer.acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )
        with self.assertRaisesRegex(ValueError, "another session"):
            acquirer.acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_B,
            )

    def test_another_claim_filename_cannot_duplicate_work(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical work identity"):
            FreshContextContinuationAcquirer.from_paths(
                self.storage,
                self.selection_path,
                self.continuation_path,
                self.root / "another-claim.json",
                inspector=FixedInspector([self.inspection]),
            )

    def test_changed_workspace_stales_historical_passes(self) -> None:
        changed = self.inspection.model_copy(
            update={
                "workspace": self.inspection.workspace.model_copy(
                    update={
                        "branch": "other-branch",
                        "dirty_state_sha256": digest(b"changed dirty state"),
                    }
                ),
                "changed_paths": (self.proposed.checkpoint.main_files[0],),
            }
        )
        task_state = self.acquirer(changed).acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )

        self.assertFalse(task_state.acquisition.freshness_ready)
        self.assertFalse(task_state.acquisition.workspace_matches_checkpoint)
        self.assertEqual(
            task_state.acquisition.stale_verification_ids,
            tuple(
                item.verification_id
                for item in self.proposed.checkpoint.verifications
                if item.status == "passed"
            ),
        )
        self.assertIn("branch", task_state.acquisition.continuation_blockers[0])
        self.assertIn("dirty_state", task_state.acquisition.continuation_blockers[0])

    def test_workspace_change_during_claim_fails_closed(self) -> None:
        changed = self.inspection.model_copy(
            update={
                "workspace": self.inspection.workspace.model_copy(
                    update={"dirty_state_sha256": digest(b"late change")}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "changed during"):
            self.acquirer(self.inspection, changed).acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertTrue(self.claim_path.exists())

    def test_stale_pointer_and_edited_selection_fail_before_claim(self) -> None:
        acquirer = self.acquirer()
        self.selection_path.write_bytes(self.selection_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "changed since launch"):
            acquirer.acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertFalse(self.claim_path.exists())
        self.selection_path.write_bytes(acquirer.current_selection_payload)
        self.continuation_path.write_bytes(self.continuation_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "changed since launch"):
            acquirer.acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )

    def test_incomplete_dependency_cannot_be_claimed(self) -> None:
        followup = next(
            item
            for item in self.proposed.work_units
            if item.work_unit_id == "g1-pressure"
        )
        selection = self.continuation.model_copy(
            update={
                "selected_work_unit": followup.reference,
                "required_inputs": followup.required_inputs,
            }
        )
        self.continuation_path.write_bytes(canonical_bytes(selection))
        self.claim_path = continuation_claim_path(self.storage, selection)
        with self.assertRaisesRegex(ValueError, "dependency is not completed"):
            self.acquirer().acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertFalse(self.claim_path.exists())

    def test_context_or_ledger_reset_is_rejected(self) -> None:
        reset = self.continuation.model_copy(
            update={"ledger_baseline": ResourceLedger()}
        )
        self.continuation_path.write_bytes(canonical_bytes(reset))
        self.continuation_path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "reset or replace"):
            self.acquirer().acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertFalse(self.claim_path.exists())

        reset = self.continuation.model_copy(
            update={"context_baseline": accumulate_context_metrics(())}
        )
        self.continuation_path.write_bytes(canonical_bytes(reset))
        with self.assertRaisesRegex(ValueError, "reset cumulative context"):
            self.acquirer().acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )

    def test_concurrent_claim_lock_fails_closed(self) -> None:
        lock_path = self.claim_path.parent / CONTINUATION_LOCK_NAME
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.assertRaisesRegex(ValueError, "another continuation claim"):
            self.acquirer().acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )

    def test_missing_main_file_is_an_explicit_blocker(self) -> None:
        missing = self.inspection.model_copy(
            update={
                "relevant_files": (
                    self.inspection.relevant_files[0].model_copy(
                        update={"availability": "missing", "sha256": None, "bytes": 0}
                    ),
                    *self.inspection.relevant_files[1:],
                )
            }
        )
        task_state = self.acquirer(missing).acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )
        self.assertFalse(task_state.acquisition.freshness_ready)
        self.assertIn(
            "main file is missing", task_state.acquisition.continuation_blockers[0]
        )

    def test_missing_archive_evidence_prevents_claim(self) -> None:
        artifact = (
            self.storage / self.proposed.sha256 / "artifacts" / self.old_artifact.sha256
        )
        artifact.unlink()
        with self.assertRaisesRegex(ValueError, "artifact inventory"):
            self.acquirer().acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertFalse(self.claim_path.exists())

    def test_declared_available_input_requires_recoverable_bytes(self) -> None:
        missing_input = self.next_work.required_inputs[0].model_copy(
            update={"sha256": digest(b"unrecoverable input")}
        )
        next_work = self.next_work.model_copy(
            update={"required_inputs": (missing_input,)}
        )
        bundle = self.proposed.model_copy(
            update={
                "work_units": tuple(
                    next_work if item.reference == next_work.reference else item
                    for item in self.proposed.work_units
                )
            }
        )
        save_task_state(
            self.storage,
            bundle,
            {
                self.old_artifact.sha256: self.old_payload,
                self.new_artifact.sha256: self.new_payload,
            },
        )
        current = CurrentTaskStateSelection.model_validate_json(
            self.selection_path.read_bytes()
        )
        self.selection_path.write_bytes(
            canonical_bytes(current.model_copy(update={"bundle_sha256": bundle.sha256}))
        )
        self.continuation_path.write_bytes(
            canonical_bytes(
                self.continuation.model_copy(
                    update={"required_inputs": next_work.required_inputs}
                )
            )
        )
        with self.assertRaisesRegex(ValueError, "input cannot be recovered"):
            self.acquirer().acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )
        self.assertFalse(self.claim_path.exists())

    def test_unclaimed_continuation_refuses_an_existing_conversation(self) -> None:
        with self.assertRaisesRegex(ValueError, "fresh conversation"):
            self.acquirer().validate_launch(
                session_id=SESSION_A,
                has_history=True,
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
            )
        self.assertFalse(self.claim_path.exists())

    def test_forged_stale_verification_identity_is_rejected(self) -> None:
        task_state = self.acquirer().acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )
        forged = task_state.model_copy(
            update={
                "acquisition": task_state.acquisition.model_copy(
                    update={"stale_verification_ids": ("unknown-pass",)}
                )
            }
        )
        with self.assertRaisesRegex(ValidationError, "unknown verification"):
            RuntimeTaskState.model_validate(forged.model_dump())

    def test_fixed_runtime_cannot_bypass_the_live_claim_boundary(self) -> None:
        task_state = self.acquirer().acquire(
            owner_uid=os.getuid(),
            workspace=str(self.workspace.resolve()),
            session_id=SESSION_A,
        )
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        with self.assertRaisesRegex(ValueError, "live acquisition boundary"):
            ConversationController(
                state,
                cassette,
                lambda _: None,
                task_state=task_state,
            )

    def test_selection_decoder_rejects_duplicates_and_oversize(self) -> None:
        payload = canonical_bytes(self.continuation)
        duplicate = payload.decode().replace(
            '"schema_version":1', '"schema_version":1,"schema_version":1'
        )
        with self.assertRaisesRegex(ValueError, "Invalid continuation"):
            decode_continuation_selection(duplicate.encode())
        with self.assertRaisesRegex(ValueError, "exceeds 64 KiB"):
            decode_continuation_selection(b"x" * (64 * 1024 + 1))

    def test_claim_directory_must_be_private(self) -> None:
        self.root.chmod(0o755)
        self.addCleanup(self.root.chmod, 0o700)
        with self.assertRaisesRegex(ValueError, "private and owner-only"):
            self.acquirer().acquire(
                owner_uid=os.getuid(),
                workspace=str(self.workspace.resolve()),
                session_id=SESSION_A,
            )


class ConversationContinuationTests(ContinuationFixture, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_continuation(self)

    async def test_claim_precedes_preview_and_recorded_dispatch_admission(self) -> None:
        acquirer = self.acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state,
            cassette,
            lambda _: None,
            task_state_acquirer=acquirer,
        )
        self.assertTrue(self.claim_path.exists())
        controller.submit(DEMO_PROMPTS[0])
        preview = preview_context(controller.state, task_state_acquirer=acquirer)

        await controller.step(CapturingClient())

        entry = controller.state.entries[0]
        assert entry.request_admission is not None
        assert entry.request_admission.task_state is not None
        assert preview.task_state is not None
        self.assertTrue(preview.task_state.continuation_enabled)
        self.assertTrue(entry.request_admission.task_state.continuation_enabled)
        self.assertFalse(entry.request_admission.task_state.grants_authority)


class GitWorkspaceInspectorTests(TestCase):
    def test_tracked_and_untracked_changes_alter_live_fingerprint(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(("git", "init", "-q", str(root)), check=True)
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "user.email",
                    "fixture@example.test",
                ),
                check=True,
            )
            subprocess.run(
                ("git", "-C", str(root), "config", "user.name", "Fixture"),
                check=True,
            )
            main = root / "main.py"
            main.write_text("value = 1\n")
            subprocess.run(("git", "-C", str(root), "add", "main.py"), check=True)
            subprocess.run(
                ("git", "-C", str(root), "commit", "-qm", "fixture"), check=True
            )
            inspector = GitWorkspaceInspector()
            clean = inspector.inspect(root, ("main.py",))
            main.write_text("value = 2\n")
            (root / "new.txt").write_text("new\n")
            changed = inspector.inspect(root, ("main.py",))

            self.assertNotEqual(
                clean.workspace.dirty_state_sha256,
                changed.workspace.dirty_state_sha256,
            )
            self.assertEqual(set(changed.changed_paths), {"main.py", "new.txt"})
            self.assertTrue(changed.relevant_files[0].changed_since_checkpoint)
