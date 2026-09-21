"""Locked compare-and-swap closure for private milestone checkpoints."""

from __future__ import annotations

import fcntl
import json
import os
import stat
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import Literal, NamedTuple, Self
from uuid import uuid4

from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.files import read_bounded
from mos_eisley.run.task_state_store import (
    TaskStateBundle,
    load_task_state,
    save_task_state,
)
from mos_eisley.task_profile import (
    AcquiredWorkUnitProfile,
    WorkUnitProfileAcquisition,
)
from mos_eisley.task_state import (
    ContinuationSelection,
    FreshContinuationContext,
    OwnerProjectScope,
    TaskCheckpointHead,
    TaskContinuationClaim,
    WorkspaceState,
    continuation_claim_id,
    validate_continuation,
)

ARCHIVE_DIRECTORY = "archives"
HEAD_FILE = "current.json"
LOCK_FILE = "checkpoint.lock"
CLAIM_DIRECTORY = "claims"
MAX_HEAD_BYTES = 64_000
MAX_CLAIM_BYTES = 256_000
MAX_FRESH_CONTEXT_BYTES = 1_000_000
CheckpointClosureReason = Literal[
    "completed_milestone",
    "material_objective_change",
    "deliberate_handoff",
]
CHECKPOINT_CLOSURE_REASONS: frozenset[str] = frozenset(
    {
        "completed_milestone",
        "material_objective_change",
        "deliberate_handoff",
    }
)


class CheckpointClosureError(ValueError):
    """A milestone could not be closed without changing current task state."""


class ContinuationClaimError(ValueError):
    """A continuation could not be claimed or revalidated without dispatch."""


class ClaimedContinuation(NamedTuple):
    head: TaskCheckpointHead
    claim: TaskContinuationClaim
    context: FreshContinuationContext
    profile: AcquiredWorkUnitProfile


class ResolvedContinuation(NamedTuple):
    context: FreshContinuationContext
    profile: AcquiredWorkUnitProfile


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate checkpoint-head key")
        result[key] = value
    return result


def _private_directory(path: Path) -> None:
    details = path.lstat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_mode & 0o077
    ):
        raise CheckpointClosureError(
            "checkpoint storage must be a private owned directory"
        )


def _private_file(path: Path) -> None:
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_mode & 0o077
        or details.st_nlink != 1
    ):
        raise CheckpointClosureError("checkpoint file must be a private owned file")


def _durable_checkpoint_state(bundle: TaskStateBundle) -> dict[str, object]:
    return bundle.checkpoint.model_dump(
        mode="python", exclude={"revision", "previous_checkpoint_sha256"}
    )


class TaskCheckpointStore:
    """One held lock owns the current head for an exact task and scope."""

    def __init__(
        self,
        root: Path,
        scope: OwnerProjectScope,
        checkpoint_id: str,
        *,
        max_view_bytes: int = 16_000,
    ) -> None:
        if type(max_view_bytes) is not int or not 1 <= max_view_bytes <= 16_000:
            raise ValueError("invalid checkpoint view byte limit")
        self.root = root
        self.scope = OwnerProjectScope.model_validate(scope.model_dump())
        self.checkpoint_id = checkpoint_id
        self.max_view_bytes = max_view_bytes
        self._lock = -1
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _private_directory(root)
        archive_root = root / ARCHIVE_DIRECTORY
        archive_root.mkdir(mode=0o700, exist_ok=True)
        _private_directory(archive_root)
        self.archive_root = archive_root
        try:
            self._lock = os.open(
                root / LOCK_FILE,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
            )
            lock_details = os.fstat(self._lock)
            if (
                not stat.S_ISREG(lock_details.st_mode)
                or lock_details.st_uid != os.getuid()
                or lock_details.st_mode & 0o077
                or lock_details.st_nlink != 1
            ):
                raise CheckpointClosureError(
                    "checkpoint lock must be a private owned file"
                )
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._lock >= 0:
            os.close(self._lock)
            self._lock = -1

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._lock < 0:
            raise CheckpointClosureError("checkpoint store is closed")
        _private_directory(self.root)
        _private_directory(self.archive_root)

    def _read_head(self) -> TaskCheckpointHead | None:
        self._require_open()
        path = self.root / HEAD_FILE
        try:
            _private_file(path)
            payload = read_bounded(path, MAX_HEAD_BYTES)
        except FileNotFoundError:
            return None
        try:
            parsed = json.loads(payload, object_pairs_hook=_unique_object)
            if not isinstance(parsed, dict):
                raise ValueError
            head = TaskCheckpointHead.model_validate_json(payload)
        except (ValueError, RecursionError):
            raise CheckpointClosureError("invalid checkpoint head") from None
        if canonical_bytes(head) != payload:
            raise CheckpointClosureError("checkpoint head is noncanonical")
        if head.scope != self.scope or head.checkpoint_id != self.checkpoint_id:
            raise CheckpointClosureError("checkpoint head crosses its selected scope")
        return head

    def _load_archive(
        self, head: TaskCheckpointHead
    ) -> tuple[TaskStateBundle, dict[str, bytes]]:
        bundle, artifacts = load_task_state(
            self.archive_root / head.bundle_sha256,
            owner_uid=self.scope.owner_uid,
            project_id=self.scope.project_id,
            workspace_sha256=self.scope.workspace_sha256,
        )
        if (
            bundle.sha256 != head.bundle_sha256
            or bundle.revision != head.bundle_revision
            or bundle.checkpoint.sha256 != head.checkpoint_sha256
            or bundle.checkpoint.revision != head.checkpoint_revision
        ):
            raise CheckpointClosureError("current checkpoint archive differs from head")
        return bundle, artifacts

    def _load_bundle(self, head: TaskCheckpointHead) -> TaskStateBundle:
        return self._load_archive(head)[0]

    def load_current(self) -> tuple[TaskCheckpointHead, TaskStateBundle] | None:
        """Read and fully verify the current head and its immutable archive."""
        head = self._read_head()
        return None if head is None else (head, self._load_bundle(head))

    def _write_record(self, path: Path, payload: bytes) -> None:
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(
                path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except BaseException:
            with suppress(FileNotFoundError):
                temporary.unlink()
            raise

    def _write_head(self, head: TaskCheckpointHead) -> None:
        self._write_record(self.root / HEAD_FILE, canonical_bytes(head))

    def _claim_path(self, checkpoint_sha256: str) -> Path:
        return self.root / CLAIM_DIRECTORY / f"{checkpoint_sha256}.json"

    def _read_claim(self, checkpoint_sha256: str) -> TaskContinuationClaim | None:
        path = self._claim_path(checkpoint_sha256)
        try:
            _private_file(path)
            payload = read_bounded(path, MAX_CLAIM_BYTES)
        except FileNotFoundError:
            return None
        try:
            parsed = json.loads(payload, object_pairs_hook=_unique_object)
            if not isinstance(parsed, dict):
                raise ValueError
            claim = TaskContinuationClaim.model_validate_json(payload)
        except (ValueError, RecursionError):
            raise ContinuationClaimError("invalid continuation claim") from None
        if canonical_bytes(claim) != payload:
            raise ContinuationClaimError("continuation claim is noncanonical")
        return claim

    def _materialize_continuation(
        self,
        head: TaskCheckpointHead,
        bundle: TaskStateBundle,
        selection: ContinuationSelection,
        observed_workspace: WorkspaceState,
    ) -> ResolvedContinuation:
        checkpoint = bundle.checkpoint
        work_units = {item.reference: item for item in bundle.work_units}
        work_unit = work_units.get(selection.selected_work_unit)
        if work_unit is None:
            raise ContinuationClaimError("selected continuation work unit is absent")
        try:
            validate_continuation(checkpoint, work_unit, selection)
        except ValueError as error:
            raise ContinuationClaimError(str(error)) from None
        if selection.selected_work_unit not in checkpoint.next_actions:
            raise ContinuationClaimError(
                "continuation must select an explicit checkpoint next action"
            )
        if observed_workspace != checkpoint.workspace:
            stale = tuple(
                item.verification_id
                for item in checkpoint.verifications
                if item.status == "passed"
                and (
                    item.bound_workspace_sha256 != observed_workspace.sha256
                    or item.bound_input_sha256 != observed_workspace.dirty_state_sha256
                )
            )
            detail = ", ".join(stale) if stale else "none"
            raise ContinuationClaimError(
                "workspace changed since checkpoint; stale verification IDs: " + detail
            )
        stale = tuple(
            item.verification_id
            for item in checkpoint.verifications
            if item.status == "passed"
            and item.bound_input_sha256 != observed_workspace.dirty_state_sha256
        )
        if stale:
            raise ContinuationClaimError(
                "checkpoint has stale passing verification inputs: " + ", ".join(stale)
            )
        if selection.ledger_baseline.uncertain_effects:
            raise ContinuationClaimError(
                "continuation is blocked by unresolved uncertain effects"
            )
        clauses = {item.reference: item for item in bundle.clauses}
        decisions = {item.reference: item for item in bundle.decisions}
        context = FreshContinuationContext(
            selection=selection,
            checkpoint_view=checkpoint.view,
            selected_work_unit=work_unit,
            applicable_clauses=tuple(
                clauses[item] for item in work_unit.applicable_clauses
            ),
            active_decisions=tuple(
                decisions[item] for item in checkpoint.active_decisions
            ),
            verifications=checkpoint.verifications,
            untested_claims=checkpoint.untested_claims,
            blockers=checkpoint.blockers,
            lineage_sha256=checkpoint.lineage_sha256,
        )
        if len(canonical_bytes(context)) > MAX_FRESH_CONTEXT_BYTES:
            raise ContinuationClaimError("fresh continuation context exceeds its limit")
        if (
            head.checkpoint_sha256 != checkpoint.sha256
            or head.bundle_sha256 != bundle.sha256
        ):
            raise ContinuationClaimError("checkpoint changed during continuation load")
        profile_id = work_unit.task_profile_id
        if profile_id is None:
            raise ContinuationClaimError(
                "selected continuation work unit has no owned task profile"
            )
        assessments = {item.manifest.profile_id: item for item in bundle.profiles}
        assessment = assessments.get(profile_id)
        if assessment is None:
            raise ContinuationClaimError("owned task profile is absent")
        try:
            profile = assessment.materialize()
        except ValueError:
            raise ContinuationClaimError(
                "owned task profile material failed validation"
            ) from None
        manifest = profile.manifest
        if (
            manifest.scope != self.scope
            or manifest.work_unit != work_unit.reference
            or manifest.policy_sha256 != work_unit.policy_sha256
            or assessment.report.status == "fail"
        ):
            raise ContinuationClaimError(
                "owned task profile differs from the selected work unit"
            )
        acquired = AcquiredWorkUnitProfile(
            profile=profile,
            acquisition=WorkUnitProfileAcquisition(
                checkpoint_id=checkpoint.checkpoint_id,
                checkpoint_revision=checkpoint.revision,
                checkpoint_sha256=checkpoint.sha256,
                bundle_revision=bundle.revision,
                bundle_sha256=bundle.sha256,
                work_unit=work_unit.reference,
                profile_id=manifest.profile_id,
                profile_sha256=manifest.sha256,
            ),
        )
        return ResolvedContinuation(context=context, profile=acquired)

    def claim_continuation(
        self,
        selection: ContinuationSelection,
        *,
        session_id: str,
        observed_workspace: WorkspaceState,
    ) -> ClaimedContinuation:
        """Atomically claim an exact checkpoint for one fresh conversation."""
        self._require_open()
        loaded = self.load_current()
        if loaded is None:
            raise ContinuationClaimError("no checkpoint is available to continue")
        head, bundle = loaded
        if not bundle.runtime_continuation_enabled:
            raise ContinuationClaimError(
                "checkpoint does not enable runtime continuation"
            )
        resolved = self._materialize_continuation(
            head, bundle, selection, observed_workspace
        )
        context = resolved.context
        claim = TaskContinuationClaim(
            claim_id=continuation_claim_id(selection, session_id),
            session_id=session_id,
            selection=selection,
            context_sha256=context.sha256,
            lineage_sha256=bundle.checkpoint.lineage_sha256,
        )
        existing = self._read_claim(head.checkpoint_sha256)
        if existing is not None:
            if existing == claim:
                return ClaimedContinuation(head, claim, context, resolved.profile)
            raise ContinuationClaimError(
                "checkpoint continuation is already claimed by another selection"
            )
        claim_root = self.root / CLAIM_DIRECTORY
        claim_root.mkdir(mode=0o700, exist_ok=True)
        _private_directory(claim_root)
        self._write_record(
            self._claim_path(head.checkpoint_sha256), canonical_bytes(claim)
        )
        return ClaimedContinuation(head, claim, context, resolved.profile)

    def resolve_continuation(
        self,
        claim: TaskContinuationClaim,
        *,
        observed_workspace: WorkspaceState,
    ) -> ResolvedContinuation:
        """Revalidate a committed claim immediately before request admission."""
        self._require_open()
        loaded = self.load_current()
        if loaded is None:
            raise ContinuationClaimError("claimed checkpoint is no longer current")
        head, bundle = loaded
        if head.checkpoint_sha256 != claim.selection.checkpoint_sha256:
            raise ContinuationClaimError("claimed checkpoint is no longer current")
        saved = self._read_claim(head.checkpoint_sha256)
        if saved != claim:
            raise ContinuationClaimError(
                "saved continuation claim differs from session"
            )
        resolved = self._materialize_continuation(
            head, bundle, claim.selection, observed_workspace
        )
        context = resolved.context
        if (
            context.sha256 != claim.context_sha256
            or context.lineage_sha256 != claim.lineage_sha256
        ):
            raise ContinuationClaimError(
                "fresh continuation context changed after claim"
            )
        return resolved

    def close_milestone(
        self,
        bundle: TaskStateBundle,
        artifacts: Mapping[str, bytes],
        *,
        expected_revision: int,
        reason: CheckpointClosureReason = "completed_milestone",
    ) -> TaskCheckpointHead:
        """Archive and atomically publish one durable task boundary."""
        self._require_open()
        if type(expected_revision) is not int or expected_revision < 0:
            raise CheckpointClosureError("invalid expected checkpoint revision")
        if reason not in CHECKPOINT_CLOSURE_REASONS:
            raise CheckpointClosureError("invalid checkpoint closure reason")
        try:
            bundle = TaskStateBundle.model_validate(bundle.model_dump(mode="python"))
        except ValueError:
            raise CheckpointClosureError(
                "task-state bundle failed closure validation"
            ) from None
        checkpoint = bundle.checkpoint
        if bundle.scope != self.scope or checkpoint.scope != self.scope:
            raise CheckpointClosureError(
                "checkpoint closure crosses its selected scope"
            )
        if checkpoint.checkpoint_id != self.checkpoint_id:
            raise CheckpointClosureError("checkpoint closure names another task")
        if checkpoint.revision != bundle.revision:
            raise CheckpointClosureError(
                "checkpoint and bundle revisions must advance together"
            )
        if len(checkpoint.view.summary.encode("utf-8")) > self.max_view_bytes:
            raise CheckpointClosureError("checkpoint view exceeds its closure limit")
        inventory = {item.reference: item for item in bundle.work_units}
        current = inventory[checkpoint.current_work_unit]
        if reason == "completed_milestone":
            if current.status != "completed" or current.outcome is None:
                raise CheckpointClosureError(
                    "milestone closure requires a completed current work unit"
                )
            if current.outcome.reference not in checkpoint.completed_outcomes:
                raise CheckpointClosureError(
                    "checkpoint omits the completed milestone outcome"
                )
        elif current.status != "active":
            raise CheckpointClosureError(
                "handoff or objective-change closure requires active work"
            )

        loaded = self.load_current()
        previous_head = None if loaded is None else loaded[0]
        previous_bundle = None if loaded is None else loaded[1]
        if previous_head is not None and previous_head.bundle_sha256 == bundle.sha256:
            if previous_head.closure_reason != reason:
                raise CheckpointClosureError(
                    "existing closure reason differs from retry"
                )
            if expected_revision in (
                previous_head.checkpoint_revision,
                previous_head.checkpoint_revision - 1,
            ):
                return previous_head
            raise CheckpointClosureError("checkpoint revision changed before closure")
        if previous_head is None:
            if (
                expected_revision != 0
                or bundle.revision != 1
                or bundle.previous_bundle_sha256 is not None
                or checkpoint.previous_checkpoint_sha256 is not None
            ):
                raise CheckpointClosureError("initial checkpoint revision is stale")
        else:
            assert previous_bundle is not None
            if expected_revision != previous_head.checkpoint_revision:
                raise CheckpointClosureError(
                    "checkpoint revision changed before closure"
                )
            if (
                bundle.revision != previous_head.bundle_revision + 1
                or checkpoint.revision != previous_head.checkpoint_revision + 1
                or bundle.previous_bundle_sha256 != previous_head.bundle_sha256
                or checkpoint.previous_checkpoint_sha256
                != previous_head.checkpoint_sha256
            ):
                raise CheckpointClosureError("checkpoint lineage is stale")
            if _durable_checkpoint_state(previous_bundle) == _durable_checkpoint_state(
                bundle
            ):
                raise CheckpointClosureError(
                    "checkpoint update contains no durable state change"
                )

        try:
            save_task_state(self.archive_root, bundle, artifacts)
        except FileExistsError:
            archived, archived_artifacts = load_task_state(
                self.archive_root / bundle.sha256,
                owner_uid=self.scope.owner_uid,
                project_id=self.scope.project_id,
                workspace_sha256=self.scope.workspace_sha256,
            )
            if archived != bundle or archived_artifacts != dict(artifacts):
                raise CheckpointClosureError(
                    "existing checkpoint archive differs from closure input"
                ) from None
        head = TaskCheckpointHead(
            scope=self.scope,
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_revision=checkpoint.revision,
            checkpoint_sha256=checkpoint.sha256,
            bundle_revision=bundle.revision,
            bundle_sha256=bundle.sha256,
            closure_reason=reason,
        )
        self._write_head(head)
        return head
