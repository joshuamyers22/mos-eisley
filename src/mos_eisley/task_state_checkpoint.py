"""Atomic milestone closure for one explicitly selected task-state archive."""

from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Generator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, cast
from uuid import uuid4

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.task_state_store import (
    TaskStateBundle,
    load_task_state,
    save_task_state,
)
from mos_eisley.task_state import (
    MilestoneCheckpoint,
    OutcomeReference,
    ResourceLedger,
    WorkUnitRecord,
    WorkUnitReference,
)
from mos_eisley.task_state_acquisition import (
    CurrentTaskStateSelection,
    decode_task_state_selection,
)

LOCK_NAME = ".task-state-checkpoint.lock"


class CheckpointClosureLineage(Contract):
    """Deterministic link from a prior checkpoint to its terminal work revision."""

    schema_version: Literal[1] = 1
    previous_lineage_sha256: Digest
    previous_bundle_sha256: Digest
    previous_checkpoint_sha256: Digest
    closed_work_unit: WorkUnitReference
    outcome: OutcomeReference
    workspace_sha256: Digest
    context_metrics_sha256: Digest
    task_ledger: ResourceLedger
    outstanding_work: Annotated[
        tuple[WorkUnitReference, ...], Field(min_length=1, max_length=128)
    ]

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


def checkpoint_closure_lineage(
    previous: TaskStateBundle,
    closed_work_unit: WorkUnitRecord,
    checkpoint: MilestoneCheckpoint,
) -> CheckpointClosureLineage:
    """Build the one accepted lineage value for a proposed checkpoint closure."""
    outcome = closed_work_unit.outcome
    if outcome is None:
        raise ValueError("checkpoint closure requires a terminal work-unit outcome")
    return CheckpointClosureLineage(
        previous_lineage_sha256=previous.checkpoint.lineage_sha256,
        previous_bundle_sha256=previous.sha256,
        previous_checkpoint_sha256=previous.checkpoint.sha256,
        closed_work_unit=closed_work_unit.reference,
        outcome=outcome.reference,
        workspace_sha256=checkpoint.workspace.sha256,
        context_metrics_sha256=checkpoint.context_metrics.sha256,
        task_ledger=checkpoint.task_ledger,
        outstanding_work=checkpoint.outstanding_work,
    )


class CheckpointClosureReceipt(Contract):
    """Text-free evidence that one archive and current pointer were committed."""

    schema_version: Literal[1] = 1
    kind: Literal["task_state_checkpoint_closure"] = "task_state_checkpoint_closure"
    previous_selection_sha256: Digest
    previous_bundle_sha256: Digest
    previous_bundle_revision: Annotated[int, Field(ge=1)]
    previous_checkpoint_sha256: Digest
    previous_checkpoint_revision: Annotated[int, Field(ge=1)]
    closed_work_unit: WorkUnitReference
    terminal_status: Literal["completed", "blocked", "cancelled"]
    bundle_sha256: Digest
    bundle_revision: Annotated[int, Field(ge=2)]
    checkpoint_sha256: Digest
    checkpoint_revision: Annotated[int, Field(ge=2)]
    current_selection_sha256: Digest
    archive_reused: bool
    atomic_pointer_commit: Literal[True] = True
    continuation_claimed: Literal[False] = False
    grants_authority: Literal[False] = False


_PLANNING_FIELDS = (
    "scope",
    "work_unit_id",
    "parent",
    "dependencies",
    "objective",
    "component_scope",
    "interfaces",
    "applicable_clauses",
    "origin_direction_sha256",
    "policy_sha256",
    "authorization_refs",
    "required_inputs",
    "evidence_requirements",
    "stopping_condition",
    "resource_ceiling",
    "grants_authority",
)


def _nondecreasing_ledger(previous: ResourceLedger, current: ResourceLedger) -> bool:
    return all(
        getattr(current, field) >= getattr(previous, field)
        for field in ResourceLedger.model_fields
    )


def _validate_selected_archive(
    selection: CurrentTaskStateSelection, bundle: TaskStateBundle
) -> None:
    checkpoint = bundle.checkpoint
    if (
        bundle.scope.project_id != selection.project_id
        or bundle.sha256 != selection.bundle_sha256
        or bundle.revision != selection.bundle_revision
        or checkpoint.checkpoint_id != selection.checkpoint_id
        or checkpoint.revision != selection.checkpoint_revision
        or checkpoint.sha256 != selection.checkpoint_sha256
        or checkpoint.current_work_unit != selection.current_work_unit
    ):
        raise ValueError("current task-state selection differs from its archive")


def validate_checkpoint_closure(
    previous: TaskStateBundle,
    selection: CurrentTaskStateSelection,
    proposed: TaskStateBundle,
) -> WorkUnitRecord:
    """Reject any closure that loses history, obligations, evidence, or counters."""
    return _validate_checkpoint_closure_transition(
        previous,
        selection,
        proposed,
        selected_work_unit=selection.current_work_unit,
        allow_queued_source=False,
    )


def validate_claimed_checkpoint_closure(
    previous: TaskStateBundle,
    selection: CurrentTaskStateSelection,
    proposed: TaskStateBundle,
    *,
    selected_work_unit: WorkUnitReference,
) -> WorkUnitRecord:
    """Validate closure of a separately authenticated continuation claim."""
    return _validate_checkpoint_closure_transition(
        previous,
        selection,
        proposed,
        selected_work_unit=selected_work_unit,
        allow_queued_source=True,
    )


def _validate_checkpoint_closure_transition(
    previous: TaskStateBundle,
    selection: CurrentTaskStateSelection,
    proposed: TaskStateBundle,
    *,
    selected_work_unit: WorkUnitReference,
    allow_queued_source: bool,
) -> WorkUnitRecord:
    previous = TaskStateBundle.model_validate(previous.model_dump())
    proposed = TaskStateBundle.model_validate(proposed.model_dump())
    selection = CurrentTaskStateSelection.model_validate(selection.model_dump())
    selected_work_unit = WorkUnitReference.model_validate(
        selected_work_unit.model_dump()
    )
    _validate_selected_archive(selection, previous)

    old_checkpoint = previous.checkpoint
    checkpoint = proposed.checkpoint
    if proposed.scope != previous.scope:
        raise ValueError("checkpoint closure crosses an owner or project boundary")
    if (
        proposed.revision != previous.revision + 1
        or proposed.previous_bundle_sha256 != previous.sha256
    ):
        raise ValueError("checkpoint closure must extend the selected bundle revision")
    if (
        checkpoint.checkpoint_id != old_checkpoint.checkpoint_id
        or checkpoint.revision != old_checkpoint.revision + 1
        or checkpoint.previous_checkpoint_sha256 != old_checkpoint.sha256
    ):
        raise ValueError(
            "checkpoint closure must extend the selected checkpoint revision"
        )
    if proposed.runtime_continuation_enabled:
        raise ValueError("checkpoint closure cannot enable runtime continuation")

    for field, label in (
        ("clauses", "clauses"),
        ("decisions", "accepted decisions"),
        ("profiles", "task profiles"),
    ):
        if getattr(proposed, field) != getattr(previous, field):
            raise ValueError(f"checkpoint closure cannot change {label}")
    if proposed.context_requests[: len(previous.context_requests)] != (
        previous.context_requests
    ):
        raise ValueError("checkpoint closure cannot replace cumulative context history")

    if proposed.work_units[: len(previous.work_units)] != previous.work_units:
        raise ValueError("checkpoint closure must preserve immutable work-unit history")
    appended_work = proposed.work_units[len(previous.work_units) :]
    if len(appended_work) != 1:
        raise ValueError("checkpoint closure must append one terminal work revision")
    closed = appended_work[0]
    source_by_reference = {item.reference: item for item in previous.work_units}
    try:
        source = source_by_reference[selected_work_unit]
    except KeyError:
        raise ValueError("checkpoint closure work unit is absent") from None
    accepted_source_statuses = (
        ("queued", "active") if allow_queued_source else ("active",)
    )
    if (
        source.status not in accepted_source_statuses
        or source.reference not in old_checkpoint.outstanding_work
    ):
        raise ValueError("checkpoint closure requires the selected active work unit")
    if (
        closed.work_unit_id != source.work_unit_id
        or closed.revision != source.revision + 1
    ):
        raise ValueError("checkpoint closure must revise the selected work unit once")
    if closed.status not in ("completed", "blocked", "cancelled"):
        raise ValueError("checkpoint closure requires a terminal work-unit state")
    if any(
        getattr(closed, field) != getattr(source, field) for field in _PLANNING_FIELDS
    ):
        raise ValueError("checkpoint closure cannot rewrite the work-unit plan")
    if closed.evidence[: len(source.evidence)] != source.evidence:
        raise ValueError("checkpoint closure cannot replace prior work-unit evidence")
    if not _nondecreasing_ledger(source.ledger, closed.ledger):
        raise ValueError("checkpoint closure cannot reset the task ledger or counters")
    if allow_queued_source and not _nondecreasing_ledger(
        old_checkpoint.task_ledger, closed.ledger
    ):
        raise ValueError("continued closure cannot reset the checkpoint task ledger")
    outcome = closed.outcome
    assert outcome is not None
    if any(item.outcome_id == outcome.outcome_id for item in previous.outcomes):
        raise ValueError("checkpoint closure outcome identity already exists")
    if outcome.revision != 1:
        raise ValueError("a new checkpoint closure outcome must begin at revision one")
    if proposed.outcomes != (*previous.outcomes, outcome):
        raise ValueError("checkpoint closure must append only its terminal outcome")

    expected_outstanding = tuple(
        item for item in old_checkpoint.outstanding_work if item != source.reference
    )
    if checkpoint.current_work_unit != closed.reference:
        raise ValueError("checkpoint closure must select the terminal work revision")
    if checkpoint.outstanding_work != expected_outstanding:
        raise ValueError("checkpoint closure cannot lose or invent outstanding work")
    if checkpoint.active_decisions != old_checkpoint.active_decisions:
        raise ValueError("checkpoint closure cannot promote an unaccepted decision")
    expected_outcomes = old_checkpoint.completed_outcomes + (
        (outcome.reference,) if closed.status == "completed" else ()
    )
    if checkpoint.completed_outcomes != expected_outcomes:
        raise ValueError("checkpoint closure completed outcomes are incomplete")
    if not checkpoint.main_files:
        raise ValueError("checkpoint closure must identify its main files")
    included = set(checkpoint.view.included_record_ids)
    required_included = {
        closed.work_unit_id,
        outcome.outcome_id,
        *(item.work_unit_id for item in checkpoint.next_actions),
    }
    if not required_included <= included:
        raise ValueError("checkpoint view omits a closure or next-action identity")
    if not set(outcome.untested_claims) <= set(checkpoint.untested_claims):
        raise ValueError("checkpoint closure hides an untested outcome claim")
    if not set(old_checkpoint.untested_claims) <= set(checkpoint.untested_claims):
        raise ValueError("checkpoint closure drops a prior untested claim")
    if closed.status == "blocked" and closed.terminal_reason not in checkpoint.blockers:
        raise ValueError("blocked checkpoint closure must retain its blocker")

    verification_ids = tuple(item.verification_id for item in checkpoint.verifications)
    if len(set(verification_ids)) != len(verification_ids):
        raise ValueError("checkpoint closure verification identities must be unique")
    if closed.status == "completed":
        verifications = {
            item.verification_id: item for item in checkpoint.verifications
        }
        for requirement in closed.evidence_requirements:
            if not requirement.verification_required:
                continue
            matching = False
            for evidence in closed.evidence:
                verification = verifications.get(evidence.evidence_id)
                if (
                    requirement.requirement_id in evidence.satisfies
                    and evidence.kind == "verification"
                    and evidence.verification_status == "passed"
                    and verification is not None
                    and verification.status == "passed"
                    and verification.result == evidence.artifact
                    and verification.bound_workspace_sha256
                    == checkpoint.workspace.sha256
                ):
                    matching = True
                    break
            if not matching:
                raise ValueError(
                    "completed checkpoint closure lacks a matching current verification"
                )

    expected_lineage = checkpoint_closure_lineage(previous, closed, checkpoint).sha256
    if checkpoint.lineage_sha256 != expected_lineage:
        raise ValueError("checkpoint closure lineage does not reproduce")
    return closed


def _private_descriptor(fd: int, *, directory: bool = False) -> os.stat_result:
    details = os.fstat(fd)
    expected = (
        stat.S_ISDIR(details.st_mode) if directory else stat.S_ISREG(details.st_mode)
    )
    if (
        not expected
        or details.st_uid != os.getuid()
        or details.st_mode & 0o077
        or (not directory and details.st_nlink != 1)
    ):
        raise ValueError("checkpoint closure storage must be private and owner-only")
    return details


def read_task_state_selection_at(root: int, name: str) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    try:
        _private_descriptor(fd)
        payload = os.read(fd, 32 * 1024 + 1)
    finally:
        os.close(fd)
    if len(payload) > 32 * 1024:
        raise ValueError("Current task-state selection exceeds 32 KiB.")
    return payload


@contextmanager
def task_state_selection_lock(path: Path) -> Generator[tuple[int, str], None, None]:
    absolute = path.absolute()
    parent = os.open(absolute.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock = -1
    try:
        held_parent = _private_descriptor(parent, directory=True)
        named_parent = absolute.parent.stat(follow_symlinks=False)
        if (held_parent.st_dev, held_parent.st_ino) != (
            named_parent.st_dev,
            named_parent.st_ino,
        ):
            raise ValueError("checkpoint closure selection directory changed")
        lock = os.open(
            LOCK_NAME,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=parent,
        )
        _private_descriptor(lock)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another checkpoint closure is in progress") from None
        named_lock = os.stat(LOCK_NAME, dir_fd=parent, follow_symlinks=False)
        held_lock = os.fstat(lock)
        if (named_lock.st_dev, named_lock.st_ino) != (
            held_lock.st_dev,
            held_lock.st_ino,
        ):
            raise ValueError("checkpoint closure lock changed")
        yield parent, absolute.name
    finally:
        if lock >= 0:
            os.close(lock)
        os.close(parent)


def replace_task_state_selection(root: int, name: str, payload: bytes) -> None:
    temporary = f".{name}.{uuid4().hex}.tmp"
    fd = -1
    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=root,
        )
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, name, src_dir_fd=root, dst_dir_fd=root)
        os.fsync(root)
    finally:
        if fd >= 0:
            os.close(fd)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=root)


@dataclass(frozen=True)
class TaskStateCheckpointStore:
    """Close one selected active unit and publish its next immutable checkpoint."""

    storage: Path
    selection_path: Path

    def close(
        self,
        *,
        expected_selection_sha256: str,
        proposed: TaskStateBundle,
        new_artifacts: Mapping[str, bytes] | None = None,
    ) -> CheckpointClosureReceipt:
        if len(expected_selection_sha256) != 64 or any(
            item not in "0123456789abcdef" for item in expected_selection_sha256
        ):
            raise ValueError("expected task-state selection digest is invalid")
        proposed = TaskStateBundle.model_validate(proposed.model_dump())
        with task_state_selection_lock(self.selection_path) as (
            selection_root,
            selection_name,
        ):
            previous_payload = read_task_state_selection_at(
                selection_root, selection_name
            )
            if digest(previous_payload) != expected_selection_sha256:
                raise ValueError("current task-state selection changed before closure")
            selection = decode_task_state_selection(previous_payload)
            previous, previous_artifacts = load_task_state(
                self.storage / selection.bundle_sha256,
                owner_uid=os.getuid(),
                project_id=selection.project_id,
                workspace_sha256=proposed.scope.workspace_sha256,
            )
            closed = validate_checkpoint_closure(previous, selection, proposed)

            artifacts = dict(previous_artifacts)
            for artifact_sha256, payload in (new_artifacts or {}).items():
                if (
                    artifact_sha256 in artifacts
                    and artifacts[artifact_sha256] != payload
                ):
                    raise ValueError(
                        "new checkpoint artifact replaces retained content"
                    )
                artifacts[artifact_sha256] = payload
            archive_reused = False
            try:
                save_task_state(self.storage, proposed, artifacts)
            except FileExistsError:
                saved, saved_artifacts = load_task_state(
                    self.storage / proposed.sha256,
                    owner_uid=os.getuid(),
                    project_id=proposed.scope.project_id,
                    workspace_sha256=proposed.scope.workspace_sha256,
                )
                if saved != proposed or saved_artifacts != artifacts:
                    raise ValueError(
                        "existing checkpoint archive conflicts with this closure"
                    ) from None
                archive_reused = True

            if (
                read_task_state_selection_at(selection_root, selection_name)
                != previous_payload
            ):
                raise ValueError("current task-state selection changed during closure")
            current = CurrentTaskStateSelection(
                project_id=proposed.scope.project_id,
                bundle_sha256=proposed.sha256,
                bundle_revision=proposed.revision,
                checkpoint_id=proposed.checkpoint.checkpoint_id,
                checkpoint_revision=proposed.checkpoint.revision,
                checkpoint_sha256=proposed.checkpoint.sha256,
                current_work_unit=proposed.checkpoint.current_work_unit,
            )
            current_payload = canonical_bytes(current)
            replace_task_state_selection(
                selection_root, selection_name, current_payload
            )
            if (
                read_task_state_selection_at(selection_root, selection_name)
                != current_payload
            ):
                raise ValueError("checkpoint selection commit did not reproduce")

        return CheckpointClosureReceipt(
            previous_selection_sha256=expected_selection_sha256,
            previous_bundle_sha256=previous.sha256,
            previous_bundle_revision=previous.revision,
            previous_checkpoint_sha256=previous.checkpoint.sha256,
            previous_checkpoint_revision=previous.checkpoint.revision,
            closed_work_unit=closed.reference,
            terminal_status=cast(
                Literal["completed", "blocked", "cancelled"], closed.status
            ),
            bundle_sha256=proposed.sha256,
            bundle_revision=proposed.revision,
            checkpoint_sha256=proposed.checkpoint.sha256,
            checkpoint_revision=proposed.checkpoint.revision,
            current_selection_sha256=digest(current_payload),
            archive_reused=archive_reused,
        )
