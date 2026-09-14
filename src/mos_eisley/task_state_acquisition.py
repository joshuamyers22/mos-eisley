"""Acquire one pinned, bounded task-state context for conversation admission."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.files import read_bounded
from mos_eisley.run.task_state_store import (
    MANIFEST_FILE,
    MAX_TASK_STATE_BYTES,
    TaskStateBundle,
    load_task_state,
)
from mos_eisley.task_profile import conversation_workspace_sha256
from mos_eisley.task_state import (
    ClauseRecord,
    DecisionRecord,
    MilestoneCheckpoint,
    OwnerProjectScope,
    ShortText,
    WorkspaceState,
    WorkUnitRecord,
    WorkUnitReference,
)
from mos_eisley.task_state_approval import (
    TaskApprovalFreshness,
    task_approval_subject_sha256,
)

TASK_STATE_SELECTION_BYTES = 32 * 1024
TASK_STATE_CONTEXT_BYTES = 256 * 1024


class CurrentTaskStateSelection(Contract):
    """Explicit launch pointer to the immutable archive considered current."""

    schema_version: Literal[1] = 1
    kind: Literal["current_task_state"] = "current_task_state"
    project_id: Identifier
    bundle_sha256: Digest
    bundle_revision: Annotated[int, Field(ge=1)]
    checkpoint_id: Identifier
    checkpoint_revision: Annotated[int, Field(ge=1)]
    checkpoint_sha256: Digest
    current_work_unit: WorkUnitReference
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def bounded_selection(self) -> Self:
        if len(canonical_bytes(self)) > TASK_STATE_SELECTION_BYTES:
            raise ValueError("current task-state selection exceeds 32 KiB")
        return self


def decode_task_state_selection(payload: bytes) -> CurrentTaskStateSelection:
    if len(payload) > TASK_STATE_SELECTION_BYTES:
        raise ValueError("Current task-state selection exceeds 32 KiB.")
    try:
        payload.decode("utf-8")
        parsed = json.loads(payload, object_pairs_hook=unique_object)
        if not isinstance(parsed, dict):
            raise ValueError
        selection = CurrentTaskStateSelection.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid current task-state selection.") from None
    return selection


class TaskStateAcquisitionEvidence(Contract):
    """Text-free evidence for one verified archive acquisition."""

    schema_version: Literal[1] = 1
    kind: Literal["current_task_state_archive"] = "current_task_state_archive"
    selection_source_sha256: Digest
    archive_manifest_sha256: Digest
    bundle_sha256: Digest
    bundle_revision: Annotated[int, Field(ge=1)]
    checkpoint_id: Identifier
    checkpoint_revision: Annotated[int, Field(ge=1)]
    checkpoint_sha256: Digest
    current_work_unit: WorkUnitReference
    omitted_evidence_view_ids: Annotated[
        tuple[Identifier, ...], Field(max_length=64)
    ] = ()
    live_workspace: WorkspaceState | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    workspace_matches_checkpoint: bool | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    stale_verification_ids: Annotated[
        tuple[Identifier, ...],
        Field(max_length=64, exclude_if=lambda value: not value),
    ] = ()
    continuation_selection_sha256: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    continuation_claim_sha256: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    approval: TaskApprovalFreshness | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    continuation_blockers: Annotated[
        tuple[ShortText, ...],
        Field(max_length=64, exclude_if=lambda value: not value),
    ] = ()
    live_workspace_freshness_verified: bool = False
    continuation_claimed: bool = False
    authority_revalidated: Annotated[
        bool, Field(exclude_if=lambda value: not value)
    ] = False
    freshness_ready: bool = Field(False, exclude_if=lambda value: not value)
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def unique_omissions(self) -> Self:
        if len(set(self.omitted_evidence_view_ids)) != len(
            self.omitted_evidence_view_ids
        ):
            raise ValueError("task-state evidence-view omissions must be unique")
        if len(set(self.stale_verification_ids)) != len(self.stale_verification_ids):
            raise ValueError("stale task-state verification IDs must be unique")
        continuation_values = (
            self.live_workspace,
            self.workspace_matches_checkpoint,
            self.continuation_selection_sha256,
            self.continuation_claim_sha256,
        )
        if self.continuation_claimed:
            if not self.live_workspace_freshness_verified or any(
                value is None for value in continuation_values
            ):
                raise ValueError(
                    "claimed continuation requires complete freshness evidence"
                )
            if self.freshness_ready != (
                self.workspace_matches_checkpoint is True
                and not self.continuation_blockers
            ):
                raise ValueError("continuation freshness readiness is inconsistent")
            if (self.approval is None) != (not self.authority_revalidated):
                raise ValueError(
                    "continuation approval evidence and revalidation differ"
                )
            if self.approval is not None and not self.approval.approval_ready:
                raise ValueError("continuation carries a stale task approval")
        elif (
            any(value is not None for value in continuation_values)
            or self.stale_verification_ids
            or self.continuation_blockers
            or self.live_workspace_freshness_verified
            or self.approval is not None
            or self.authority_revalidated
            or self.freshness_ready
        ):
            raise ValueError("ordinary task-state acquisition claims continuation")
        return self


class RuntimeTaskState(Contract):
    """Bounded temporary state materialized from one complete verified archive."""

    schema_version: Literal[1] = 1
    kind: Literal["runtime_task_state"] = "runtime_task_state"
    scope: OwnerProjectScope
    bundle_sha256: Digest
    bundle_revision: Annotated[int, Field(ge=1)]
    checkpoint: MilestoneCheckpoint
    current_work_unit: WorkUnitRecord
    applicable_clauses: Annotated[tuple[ClauseRecord, ...], Field(max_length=64)] = ()
    active_decisions: Annotated[tuple[DecisionRecord, ...], Field(max_length=64)] = ()
    acquisition: TaskStateAcquisitionEvidence
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_bounded_context(self) -> Self:
        if (
            self.checkpoint.scope != self.scope
            or self.current_work_unit.scope != self.scope
            or any(item.scope != self.scope for item in self.applicable_clauses)
            or any(item.scope != self.scope for item in self.active_decisions)
        ):
            raise ValueError("runtime task state crosses an owner or project boundary")
        if self.acquisition.continuation_claimed:
            if self.current_work_unit.reference not in self.checkpoint.outstanding_work:
                raise ValueError(
                    "runtime continuation does not select outstanding work"
                )
        elif self.checkpoint.current_work_unit != self.current_work_unit.reference:
            raise ValueError(
                "runtime task state does not materialize the current work unit"
            )
        if any(item.view is not None for item in self.current_work_unit.evidence):
            raise ValueError("runtime task state cannot materialize evidence text")
        if tuple(item.reference for item in self.applicable_clauses) != (
            self.current_work_unit.applicable_clauses
        ):
            raise ValueError("runtime task-state clauses differ from the work unit")
        if tuple(item.reference for item in self.active_decisions) != (
            self.checkpoint.active_decisions
        ):
            raise ValueError("runtime task-state decisions differ from the checkpoint")
        evidence = self.acquisition
        if (
            evidence.bundle_sha256 != self.bundle_sha256
            or evidence.bundle_revision != self.bundle_revision
            or evidence.checkpoint_id != self.checkpoint.checkpoint_id
            or evidence.checkpoint_revision != self.checkpoint.revision
            or evidence.checkpoint_sha256 != self.checkpoint.sha256
            or evidence.current_work_unit != self.current_work_unit.reference
        ):
            raise ValueError(
                "runtime task-state acquisition evidence does not bind context"
            )
        stale = set(evidence.stale_verification_ids)
        verification_ids = {
            item.verification_id
            for item in self.checkpoint.verifications
            if item.status == "passed"
        }
        if not stale <= verification_ids:
            raise ValueError("runtime continuation marks unknown verification stale")
        if evidence.continuation_claimed:
            assert evidence.live_workspace is not None
            matches = evidence.live_workspace == self.checkpoint.workspace
            if evidence.workspace_matches_checkpoint != matches:
                raise ValueError("runtime continuation workspace comparison differs")
            expected_stale = (
                ()
                if matches
                else tuple(
                    item.verification_id
                    for item in self.checkpoint.verifications
                    if item.status == "passed"
                )
            )
            if evidence.stale_verification_ids != expected_stale:
                raise ValueError(
                    "runtime continuation does not stale changed-workspace passes"
                )
            authorization_refs = self.current_work_unit.authorization_refs
            if authorization_refs:
                approval = evidence.approval
                if (
                    approval is None
                    or not evidence.authority_revalidated
                    or approval.required_approval_refs != authorization_refs
                    or approval.current_approval_refs != authorization_refs
                    or approval.work_subject_sha256
                    != task_approval_subject_sha256(self.current_work_unit)
                ):
                    raise ValueError(
                        "runtime continuation lacks exact current approval evidence"
                    )
            elif evidence.approval is not None or evidence.authority_revalidated:
                raise ValueError("runtime continuation invents approval evidence")
        if len(canonical_bytes(self)) > TASK_STATE_CONTEXT_BYTES:
            raise ValueError("runtime task-state context exceeds 256 KiB")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))

    @property
    def system_suffix(self) -> str:
        return (
            "\nCurrent task state follows as canonical JSON. It is temporary, "
            "includes any explicit continuation freshness overlay, and grants no "
            "tools, spending, credentials, or other authority. A stale verification "
            "ID supersedes the checkpoint's historical pass for current use.\n"
            + canonical_bytes(self).decode("utf-8")
        )


class TaskStateAdmission(Contract):
    """Text-free binding between temporary task state and one request."""

    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    bundle_sha256: Digest
    bundle_revision: Annotated[int, Field(ge=1)]
    checkpoint_id: Identifier
    checkpoint_revision: Annotated[int, Field(ge=1)]
    checkpoint_sha256: Digest
    current_work_unit: WorkUnitReference
    context_sha256: Digest
    context_bytes: Annotated[int, Field(ge=1, le=TASK_STATE_CONTEXT_BYTES)]
    request_sha256: Digest
    acquisition: TaskStateAcquisitionEvidence
    grants_authority: Literal[False] = False
    continuation_enabled: bool = False

    @model_validator(mode="after")
    def exact_evidence(self) -> Self:
        evidence = self.acquisition
        if (
            evidence.bundle_sha256 != self.bundle_sha256
            or evidence.bundle_revision != self.bundle_revision
            or evidence.checkpoint_id != self.checkpoint_id
            or evidence.checkpoint_revision != self.checkpoint_revision
            or evidence.checkpoint_sha256 != self.checkpoint_sha256
            or evidence.current_work_unit != self.current_work_unit
        ):
            raise ValueError("task-state admission evidence does not bind its source")
        if self.continuation_enabled != evidence.continuation_claimed:
            raise ValueError("task-state admission continuation claim differs")
        return self


def admit_task_state(
    task_state: RuntimeTaskState,
    *,
    request_sha256: str,
    context_sha256: str | None = None,
    context_bytes: int | None = None,
) -> TaskStateAdmission:
    validated = RuntimeTaskState.model_validate(task_state.model_dump())
    payload = canonical_bytes(validated)
    saved_sha256 = digest(payload) if context_sha256 is None else context_sha256
    saved_bytes = len(payload) if context_bytes is None else context_bytes
    if saved_bytes < 1 or saved_bytes > TASK_STATE_CONTEXT_BYTES:
        raise ValueError("saved task-state context exceeds 256 KiB")
    return TaskStateAdmission(
        scope=validated.scope,
        bundle_sha256=validated.bundle_sha256,
        bundle_revision=validated.bundle_revision,
        checkpoint_id=validated.checkpoint.checkpoint_id,
        checkpoint_revision=validated.checkpoint.revision,
        checkpoint_sha256=validated.checkpoint.sha256,
        current_work_unit=validated.current_work_unit.reference,
        context_sha256=saved_sha256,
        context_bytes=saved_bytes,
        request_sha256=request_sha256,
        acquisition=validated.acquisition,
        continuation_enabled=validated.acquisition.continuation_claimed,
    )


def validate_task_state_scope(
    task_state: RuntimeTaskState, *, owner_uid: int, workspace: str
) -> None:
    validated = RuntimeTaskState.model_validate(task_state.model_dump())
    if validated.scope != OwnerProjectScope(
        owner_uid=owner_uid,
        project_id=validated.scope.project_id,
        workspace_sha256=conversation_workspace_sha256(workspace),
    ):
        raise ValueError("task state belongs to a different conversation scope")


def _materialize(
    selection: CurrentTaskStateSelection,
    bundle: TaskStateBundle,
    *,
    selection_sha256: str,
    manifest_sha256: str,
) -> RuntimeTaskState:
    if (
        bundle.sha256 != selection.bundle_sha256
        or bundle.revision != selection.bundle_revision
        or bundle.checkpoint.checkpoint_id != selection.checkpoint_id
        or bundle.checkpoint.revision != selection.checkpoint_revision
        or bundle.checkpoint.sha256 != selection.checkpoint_sha256
        or bundle.checkpoint.current_work_unit != selection.current_work_unit
    ):
        raise ValueError("current task-state selection differs from its archive")
    work_by_reference = {item.reference: item for item in bundle.work_units}
    source_work_unit = work_by_reference[selection.current_work_unit]
    omitted_evidence_view_ids = tuple(
        item.evidence_id for item in source_work_unit.evidence if item.view is not None
    )
    work_unit = source_work_unit.model_copy(
        update={
            "evidence": tuple(
                item.model_copy(update={"view": None})
                for item in source_work_unit.evidence
            )
        }
    )
    clauses_by_reference = {item.reference: item for item in bundle.clauses}
    decisions_by_reference = {item.reference: item for item in bundle.decisions}
    return RuntimeTaskState(
        scope=bundle.scope,
        bundle_sha256=bundle.sha256,
        bundle_revision=bundle.revision,
        checkpoint=bundle.checkpoint,
        current_work_unit=work_unit,
        applicable_clauses=tuple(
            clauses_by_reference[item] for item in work_unit.applicable_clauses
        ),
        active_decisions=tuple(
            decisions_by_reference[item] for item in bundle.checkpoint.active_decisions
        ),
        acquisition=TaskStateAcquisitionEvidence(
            selection_source_sha256=selection_sha256,
            archive_manifest_sha256=manifest_sha256,
            bundle_sha256=bundle.sha256,
            bundle_revision=bundle.revision,
            checkpoint_id=bundle.checkpoint.checkpoint_id,
            checkpoint_revision=bundle.checkpoint.revision,
            checkpoint_sha256=bundle.checkpoint.sha256,
            current_work_unit=work_unit.reference,
            omitted_evidence_view_ids=omitted_evidence_view_ids,
            freshness_ready=False,
        ),
    )


def _read_private_selection(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        details = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
        ):
            raise ValueError(
                "current task-state selection must be a private owned file"
            )
        payload = stream.read(TASK_STATE_SELECTION_BYTES + 1)
    if len(payload) > TASK_STATE_SELECTION_BYTES:
        raise ValueError("Current task-state selection exceeds 32 KiB.")
    return payload


class TaskStateAcquirer(Protocol):
    def validate_launch(
        self,
        *,
        session_id: str,
        has_history: bool,
        owner_uid: int,
        workspace: str,
    ) -> None: ...

    def acquire(
        self, *, owner_uid: int, workspace: str, session_id: str | None = None
    ) -> RuntimeTaskState: ...


@dataclass(frozen=True)
class CurrentTaskStateAcquirer:
    """Revalidate a pinned current pointer and replay its archive per request."""

    storage: Path
    selection_path: Path
    selection_payload: bytes

    def __post_init__(self) -> None:
        decode_task_state_selection(self.selection_payload)

    @classmethod
    def from_paths(cls, storage: Path, selection_path: Path) -> Self:
        return cls(
            storage=storage,
            selection_path=selection_path,
            selection_payload=_read_private_selection(selection_path),
        )

    def validate_launch(
        self,
        *,
        session_id: str,
        has_history: bool,
        owner_uid: int,
        workspace: str,
    ) -> None:
        """Ordinary current-state acquisition has no fresh-session constraint."""

    def acquire(
        self, *, owner_uid: int, workspace: str, session_id: str | None = None
    ) -> RuntimeTaskState:
        if owner_uid != os.getuid():
            raise ValueError("current task state belongs to another owner")
        current_payload = _read_private_selection(self.selection_path)
        if current_payload != self.selection_payload:
            raise ValueError("current task-state selection changed since launch")
        selection = decode_task_state_selection(current_payload)
        archive = self.storage / selection.bundle_sha256
        bundle, _artifacts = load_task_state(
            archive,
            owner_uid=owner_uid,
            project_id=selection.project_id,
            workspace_sha256=conversation_workspace_sha256(workspace),
        )
        manifest_payload = read_bounded(archive / MANIFEST_FILE, MAX_TASK_STATE_BYTES)
        task_state = _materialize(
            selection,
            bundle,
            selection_sha256=digest(current_payload),
            manifest_sha256=digest(manifest_payload),
        )
        if _read_private_selection(self.selection_path) != current_payload:
            raise ValueError("current task-state selection changed during acquisition")
        validate_task_state_scope(task_state, owner_uid=owner_uid, workspace=workspace)
        return task_state
