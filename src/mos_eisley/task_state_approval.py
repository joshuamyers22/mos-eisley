"""Pinned, time-bounded approval evidence for task-state continuation."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.task_state import OwnerProjectScope, WorkUnitRecord, WorkUnitReference

TASK_APPROVAL_SELECTION_BYTES = 128 * 1024


def _utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must use an explicit UTC offset")


def task_approval_subject_sha256(work_unit: WorkUnitRecord) -> str:
    """Hash only immutable planning fields, excluding the approval-reference cycle."""
    fields = (
        "scope",
        "work_unit_id",
        "revision",
        "parent",
        "dependencies",
        "objective",
        "component_scope",
        "interfaces",
        "applicable_clauses",
        "origin_direction_sha256",
        "policy_sha256",
        "required_inputs",
        "evidence_requirements",
        "stopping_condition",
        "resource_ceiling",
    )
    source = work_unit.model_dump(mode="json")
    payload = {
        "schema_version": 1,
        "kind": "task_approval_subject",
        **{name: source[name] for name in fields},
    }
    return digest(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


class TaskApprovalRecord(Contract):
    """External approval evidence; never executable authority by itself."""

    schema_version: Literal[1] = 1
    kind: Literal["task_approval"] = "task_approval"
    scope: OwnerProjectScope
    approval_id: Identifier
    selected_work_unit: WorkUnitReference
    work_subject_sha256: Digest
    authority: Identifier
    source_sha256: Digest
    approved_actions: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=32)
    ]
    issued_at: datetime
    expires_at: datetime
    session_reset_extends_expiry: Literal[False] = False
    automatic_replay: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def bounded_approval(self) -> Self:
        _utc(self.issued_at, "task approval issue time")
        _utc(self.expires_at, "task approval expiry")
        if self.expires_at <= self.issued_at:
            raise ValueError("task approval expiry must follow its issue time")
        if len(set(self.approved_actions)) != len(self.approved_actions):
            raise ValueError("task approval actions must be unique")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class TaskApprovalSelection(Contract):
    """Private launch snapshot of approval records and explicit revocations."""

    schema_version: Literal[1] = 1
    kind: Literal["task_approval_selection"] = "task_approval_selection"
    scope: OwnerProjectScope
    approvals: Annotated[tuple[TaskApprovalRecord, ...], Field(max_length=64)] = ()
    revoked_approval_refs: Annotated[tuple[Digest, ...], Field(max_length=64)] = ()
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def coherent_selection(self) -> Self:
        references = tuple(item.sha256 for item in self.approvals)
        identities = tuple(item.approval_id for item in self.approvals)
        if len(set(references)) != len(references) or len(set(identities)) != len(
            identities
        ):
            raise ValueError("task approvals must be unique")
        if len(set(self.revoked_approval_refs)) != len(self.revoked_approval_refs):
            raise ValueError("revoked task approval references must be unique")
        if any(item.scope != self.scope for item in self.approvals):
            raise ValueError("task approval selection crosses a scope boundary")
        if len(canonical_bytes(self)) > TASK_APPROVAL_SELECTION_BYTES:
            raise ValueError("task approval selection exceeds 128 KiB")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class TaskApprovalFreshness(Contract):
    """Text-free result of checking every required approval at an absolute time."""

    schema_version: Literal[1] = 1
    kind: Literal["task_approval_freshness"] = "task_approval_freshness"
    selection_sha256: Digest
    checked_at: datetime
    work_subject_sha256: Digest
    required_approval_refs: Annotated[tuple[Digest, ...], Field(max_length=16)] = ()
    current_approval_refs: Annotated[tuple[Digest, ...], Field(max_length=16)] = ()
    missing_approval_refs: Annotated[tuple[Digest, ...], Field(max_length=16)] = ()
    expired_approval_refs: Annotated[tuple[Digest, ...], Field(max_length=16)] = ()
    not_yet_valid_approval_refs: Annotated[
        tuple[Digest, ...], Field(max_length=16)
    ] = ()
    revoked_approval_refs: Annotated[tuple[Digest, ...], Field(max_length=16)] = ()
    mismatched_approval_refs: Annotated[tuple[Digest, ...], Field(max_length=16)] = ()
    approval_ready: bool
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_freshness(self) -> Self:
        _utc(self.checked_at, "task approval check time")
        groups = (
            self.required_approval_refs,
            self.current_approval_refs,
            self.missing_approval_refs,
            self.expired_approval_refs,
            self.not_yet_valid_approval_refs,
            self.revoked_approval_refs,
            self.mismatched_approval_refs,
        )
        if any(len(set(group)) != len(group) for group in groups):
            raise ValueError("task approval freshness references must be unique")
        problems: set[str] = set()
        for group in groups[2:]:
            problems.update(group)
        if self.approval_ready != (
            not problems
            and self.current_approval_refs == self.required_approval_refs
            and bool(self.required_approval_refs)
        ):
            raise ValueError("task approval freshness readiness is inconsistent")
        return self


def decode_task_approval_selection(payload: bytes) -> TaskApprovalSelection:
    if len(payload) > TASK_APPROVAL_SELECTION_BYTES:
        raise ValueError("Task approval selection exceeds 128 KiB.")
    try:
        payload.decode("utf-8")
        parsed = json.loads(payload, object_pairs_hook=unique_object)
        if not isinstance(parsed, dict):
            raise ValueError
        selection = TaskApprovalSelection.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid task approval selection.") from None
    if canonical_bytes(selection) != payload:
        raise ValueError("Task approval selection must be canonical.")
    return selection


def evaluate_task_approvals(
    work_unit: WorkUnitRecord,
    selection: TaskApprovalSelection,
    *,
    checked_at: datetime,
) -> TaskApprovalFreshness:
    _utc(checked_at, "task approval check time")
    if selection.scope != work_unit.scope:
        raise ValueError("task approval selection differs from the work-unit scope")
    required = work_unit.authorization_refs
    records = {item.sha256: item for item in selection.approvals}
    subject = task_approval_subject_sha256(work_unit)
    missing: list[str] = []
    expired: list[str] = []
    not_yet_valid: list[str] = []
    revoked: list[str] = []
    mismatched: list[str] = []
    current: list[str] = []
    revoked_set = set(selection.revoked_approval_refs)
    for reference in required:
        record = records.get(reference)
        if record is None:
            missing.append(reference)
            continue
        if reference in revoked_set:
            revoked.append(reference)
        if checked_at < record.issued_at:
            not_yet_valid.append(reference)
        if checked_at >= record.expires_at:
            expired.append(reference)
        if (
            record.scope != work_unit.scope
            or record.selected_work_unit != work_unit.reference
            or record.work_subject_sha256 != subject
        ):
            mismatched.append(reference)
        if not any(
            reference in group
            for group in (revoked, not_yet_valid, expired, mismatched)
        ):
            current.append(reference)
    problems = missing or expired or not_yet_valid or revoked or mismatched
    return TaskApprovalFreshness(
        selection_sha256=selection.sha256,
        checked_at=checked_at,
        work_subject_sha256=subject,
        required_approval_refs=required,
        current_approval_refs=tuple(current),
        missing_approval_refs=tuple(missing),
        expired_approval_refs=tuple(expired),
        not_yet_valid_approval_refs=tuple(not_yet_valid),
        revoked_approval_refs=tuple(revoked),
        mismatched_approval_refs=tuple(mismatched),
        approval_ready=bool(required) and not problems and tuple(current) == required,
    )


def _read_private_approval(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        details = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
            or details.st_nlink != 1
        ):
            raise ValueError("task approval selection must be a private owned file")
        payload = stream.read(TASK_APPROVAL_SELECTION_BYTES + 1)
    if len(payload) > TASK_APPROVAL_SELECTION_BYTES:
        raise ValueError("Task approval selection exceeds 128 KiB.")
    return payload


def _validate_private_parent(path: Path) -> None:
    absolute = path.absolute()
    descriptor = os.open(absolute.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        details = os.fstat(descriptor)
        named = absolute.parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
        ):
            raise ValueError(
                "task approval selection directory must be private and owner-only"
            )
        if (details.st_dev, details.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError("task approval selection directory changed")
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class PinnedTaskApprovalGuard:
    """Reopen one pinned approval selection on every continuation acquisition."""

    selection_path: Path
    selection_payload: bytes
    clock: Callable[[], datetime]

    @classmethod
    def from_path(
        cls,
        selection_path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> Self:
        _validate_private_parent(selection_path)
        payload = _read_private_approval(selection_path)
        decode_task_approval_selection(payload)
        return cls(
            selection_path=selection_path.absolute(),
            selection_payload=payload,
            clock=(lambda: datetime.now(UTC)) if clock is None else clock,
        )

    def revalidate(self, work_unit: WorkUnitRecord) -> TaskApprovalFreshness:
        payload = _read_private_approval(self.selection_path)
        if payload != self.selection_payload:
            raise ValueError("task approval selection changed since launch")
        freshness = evaluate_task_approvals(
            work_unit,
            decode_task_approval_selection(payload),
            checked_at=self.clock(),
        )
        if not freshness.approval_ready:
            reasons: list[str] = []
            for label, values in (
                ("missing", freshness.missing_approval_refs),
                ("expired", freshness.expired_approval_refs),
                ("not yet valid", freshness.not_yet_valid_approval_refs),
                ("revoked", freshness.revoked_approval_refs),
                ("mismatched", freshness.mismatched_approval_refs),
            ):
                if values:
                    reasons.append(label)
            raise ValueError("task approval is stale: " + ", ".join(reasons))
        return freshness
