"""Claim-bound replacement verification after a changed-tree continuation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.task_state_store import (
    TaskStateBundle,
    load_task_state,
    save_task_state,
)
from mos_eisley.task_profile import conversation_workspace_sha256
from mos_eisley.task_state import (
    ContinuationSelection,
    ResourceLedger,
    VerificationRecord,
    WorkspaceState,
    WorkUnitRecord,
    WorkUnitReference,
    validate_continuation,
)
from mos_eisley.task_state_acquisition import (
    CurrentTaskStateSelection,
    decode_task_state_selection,
)
from mos_eisley.task_state_checkpoint import (
    read_task_state_selection_at,
    replace_task_state_selection,
    task_state_selection_lock,
    validate_claimed_checkpoint_closure,
)
from mos_eisley.task_state_continuation import (
    CONTINUATION_CLAIM_BYTES,
    CONTINUATION_SELECTION_BYTES,
    ChangedDimension,
    ContinuationClaim,
    GitWorkspaceInspector,
    WorkspaceInspection,
    WorkspaceInspector,
    continuation_claim_path,
    continuation_freshness,
    decode_continuation_claim,
    decode_continuation_selection,
    read_private_continuation_payload,
    validate_private_continuation_parent,
)


class ChangedTreeReplacementVerificationReceipt(Contract):
    """Text-free proof that stale passes were replaced before atomic closure."""

    schema_version: Literal[1] = 1
    kind: Literal["changed_tree_replacement_verification"] = (
        "changed_tree_replacement_verification"
    )
    session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    previous_selection_sha256: Digest
    continuation_selection_sha256: Digest
    continuation_claim_sha256: Digest
    freshness_sha256: Digest
    changed_dimensions: Annotated[
        tuple[ChangedDimension, ...], Field(min_length=1, max_length=5)
    ]
    stale_verification_ids: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=64)
    ]
    replacement_verification_ids: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=64)
    ]
    live_workspace: WorkspaceState
    previous_bundle_sha256: Digest
    previous_bundle_revision: Annotated[int, Field(ge=1)]
    previous_checkpoint_sha256: Digest
    previous_checkpoint_revision: Annotated[int, Field(ge=1)]
    closed_work_unit: WorkUnitReference
    bundle_sha256: Digest
    bundle_revision: Annotated[int, Field(ge=2)]
    checkpoint_sha256: Digest
    checkpoint_revision: Annotated[int, Field(ge=2)]
    current_selection_sha256: Digest
    remaining_outstanding_work: Annotated[
        tuple[WorkUnitReference, ...], Field(max_length=128)
    ] = ()
    task_ledger: ResourceLedger
    cumulative_context_sha256: Digest
    archive_reused: bool
    atomic_pointer_commit: Literal[True] = True
    historical_passes_superseded: Literal[True] = True
    replacement_verification_current: Literal[True] = True
    grants_authority: Literal[False] = False


@dataclass(frozen=True)
class _ReplacementValidation:
    closed: WorkUnitRecord
    freshness_sha256: str
    changed_dimensions: tuple[ChangedDimension, ...]
    stale_verification_ids: tuple[str, ...]
    replacement_verification_ids: tuple[str, ...]


def _validate_dependencies(
    bundle: TaskStateBundle, selected_work_unit: WorkUnitRecord
) -> None:
    for dependency in selected_work_unit.dependencies:
        latest = max(
            (
                item
                for item in bundle.work_units
                if item.work_unit_id == dependency.work_unit_id
                and item.revision >= dependency.revision
            ),
            key=lambda item: item.revision,
            default=None,
        )
        if latest is None or latest.status != "completed":
            raise ValueError(
                "replacement verification dependency is not completed: "
                f"{dependency.work_unit_id}@{dependency.revision}"
            )


def _staled_verification(
    verification: VerificationRecord, stale_ids: set[str]
) -> VerificationRecord:
    if verification.verification_id not in stale_ids:
        return verification
    return verification.model_copy(update={"status": "stale"})


def validate_changed_tree_replacement_verification(
    previous: TaskStateBundle,
    current_selection: CurrentTaskStateSelection,
    continuation_selection: ContinuationSelection,
    claim: ContinuationClaim,
    proposed: TaskStateBundle,
    inspection: WorkspaceInspection,
    *,
    session_id: str,
    current_selection_sha256: str,
    continuation_selection_sha256: str,
) -> _ReplacementValidation:
    """Reproduce one changed-tree claim and its current replacement evidence."""
    previous = TaskStateBundle.model_validate(previous.model_dump())
    current_selection = CurrentTaskStateSelection.model_validate(
        current_selection.model_dump()
    )
    continuation_selection = ContinuationSelection.model_validate(
        continuation_selection.model_dump()
    )
    claim = ContinuationClaim.model_validate(claim.model_dump())
    proposed = TaskStateBundle.model_validate(proposed.model_dump())
    inspection = WorkspaceInspection.model_validate(inspection.model_dump())

    work_by_reference = {item.reference: item for item in previous.work_units}
    try:
        source = work_by_reference[continuation_selection.selected_work_unit]
    except KeyError:
        raise ValueError("replacement verification work unit is absent") from None
    validate_continuation(previous.checkpoint, source, continuation_selection)
    _validate_dependencies(previous, source)
    if tuple(item.path for item in inspection.relevant_files) != (
        previous.checkpoint.main_files
    ):
        raise ValueError("replacement inspection omits checkpoint main files")
    freshness = continuation_freshness(previous, source, inspection)
    if not freshness.changed_dimensions:
        raise ValueError("replacement verification requires a detected changed tree")
    if not freshness.stale_verification_ids:
        raise ValueError("changed checkpoint has no passing verification to replace")
    if (
        claim.session_id != session_id
        or claim.current_selection_sha256 != current_selection_sha256
        or claim.continuation_selection_sha256 != continuation_selection_sha256
        or claim.bundle_sha256 != previous.sha256
        or claim.bundle_revision != previous.revision
        or claim.checkpoint_sha256 != previous.checkpoint.sha256
        or claim.checkpoint_revision != previous.checkpoint.revision
        or claim.selected_work_unit_id != source.work_unit_id
        or claim.selected_work_unit_revision != source.revision
        or claim.freshness_sha256 != freshness.sha256
        or claim.authorization_refs != source.authorization_refs
        or (claim.approval_selection_sha256 is None) != (not source.authorization_refs)
    ):
        raise ValueError("replacement verification differs from its continuation claim")

    closed = validate_claimed_checkpoint_closure(
        previous,
        current_selection,
        proposed,
        selected_work_unit=source.reference,
    )
    if closed.status != "completed":
        raise ValueError("replacement verification closure must complete its work unit")
    checkpoint = proposed.checkpoint
    if checkpoint.workspace != inspection.workspace:
        raise ValueError("replacement checkpoint does not bind the live workspace")
    if checkpoint.main_files != previous.checkpoint.main_files:
        raise ValueError("replacement checkpoint cannot narrow its main-file inventory")

    stale_ids = set(freshness.stale_verification_ids)
    expected_history = tuple(
        _staled_verification(item, stale_ids)
        for item in previous.checkpoint.verifications
    )
    if checkpoint.verifications[: len(expected_history)] != expected_history:
        raise ValueError(
            "replacement checkpoint does not retain stale verification history"
        )
    replacements = checkpoint.verifications[len(expected_history) :]
    if not replacements:
        raise ValueError("replacement checkpoint lacks a new verification")
    for replacement in replacements:
        if (
            replacement.status != "passed"
            or replacement.bound_workspace_sha256 != inspection.workspace.sha256
            or replacement.bound_input_sha256 != inspection.workspace.dirty_state_sha256
            or replacement.result is None
        ):
            raise ValueError(
                "replacement verification is not current for the live tree"
            )

    evidence = {item.evidence_id: item for item in closed.evidence}
    for replacement in replacements:
        bound = evidence.get(replacement.verification_id)
        if (
            bound is None
            or bound.kind != "verification"
            or bound.verification_status != "passed"
            or bound.artifact != replacement.result
        ):
            raise ValueError("replacement verification is not bound to completed work")

    return _ReplacementValidation(
        closed=closed,
        freshness_sha256=freshness.sha256,
        changed_dimensions=tuple(freshness.changed_dimensions),
        stale_verification_ids=freshness.stale_verification_ids,
        replacement_verification_ids=tuple(
            item.verification_id for item in replacements
        ),
    )


@dataclass(frozen=True)
class ChangedTreeReplacementVerificationStore:
    """Publish one claim-bound completion with current replacement evidence."""

    storage: Path
    workspace: Path
    current_selection_path: Path
    continuation_selection_path: Path
    continuation_selection_payload: bytes
    claim_path: Path
    claim_payload: bytes
    inspector: WorkspaceInspector = GitWorkspaceInspector()

    def __post_init__(self) -> None:
        selection = decode_continuation_selection(self.continuation_selection_payload)
        decode_continuation_claim(self.claim_payload)
        if self.claim_path.absolute() != continuation_claim_path(
            self.storage, selection
        ):
            raise ValueError("replacement claim path differs from its work identity")

    @classmethod
    def from_paths(
        cls,
        storage: Path,
        workspace: Path,
        current_selection_path: Path,
        continuation_selection_path: Path,
        claim_path: Path,
        *,
        inspector: WorkspaceInspector | None = None,
    ) -> ChangedTreeReplacementVerificationStore:
        validate_private_continuation_parent(
            current_selection_path, "current task-state selection"
        )
        validate_private_continuation_parent(
            continuation_selection_path, "continuation selection"
        )
        validate_private_continuation_parent(claim_path, "continuation claim")
        return cls(
            storage=storage.absolute(),
            workspace=workspace.resolve(strict=True),
            current_selection_path=current_selection_path.absolute(),
            continuation_selection_path=continuation_selection_path.absolute(),
            continuation_selection_payload=read_private_continuation_payload(
                continuation_selection_path,
                CONTINUATION_SELECTION_BYTES,
                "continuation selection",
            ),
            claim_path=claim_path.absolute(),
            claim_payload=read_private_continuation_payload(
                claim_path, CONTINUATION_CLAIM_BYTES, "continuation claim"
            ),
            inspector=GitWorkspaceInspector() if inspector is None else inspector,
        )

    def close(
        self,
        *,
        expected_selection_sha256: str,
        session_id: str,
        proposed: TaskStateBundle,
        new_artifacts: Mapping[str, bytes] | None = None,
    ) -> ChangedTreeReplacementVerificationReceipt:
        if len(expected_selection_sha256) != 64 or any(
            item not in "0123456789abcdef" for item in expected_selection_sha256
        ):
            raise ValueError("expected task-state selection digest is invalid")
        proposed = TaskStateBundle.model_validate(proposed.model_dump())
        if proposed.scope.workspace_sha256 != conversation_workspace_sha256(
            str(self.workspace)
        ):
            raise ValueError("replacement verification belongs to another workspace")
        with task_state_selection_lock(self.current_selection_path) as (
            selection_root,
            selection_name,
        ):
            current_payload = read_task_state_selection_at(
                selection_root, selection_name
            )
            if digest(current_payload) != expected_selection_sha256:
                raise ValueError(
                    "current task-state selection changed before replacement"
                )
            current = decode_task_state_selection(current_payload)
            previous, previous_artifacts = load_task_state(
                self.storage / current.bundle_sha256,
                owner_uid=os.getuid(),
                project_id=current.project_id,
                workspace_sha256=proposed.scope.workspace_sha256,
            )
            continuation_payload = read_private_continuation_payload(
                self.continuation_selection_path,
                CONTINUATION_SELECTION_BYTES,
                "continuation selection",
            )
            claim_payload = read_private_continuation_payload(
                self.claim_path, CONTINUATION_CLAIM_BYTES, "continuation claim"
            )
            if continuation_payload != self.continuation_selection_payload:
                raise ValueError("continuation selection changed before replacement")
            if claim_payload != self.claim_payload:
                raise ValueError("continuation claim changed before replacement")
            continuation = decode_continuation_selection(continuation_payload)
            claim = decode_continuation_claim(claim_payload)
            inspection = self.inspector.inspect(
                self.workspace, previous.checkpoint.main_files
            )
            validation = validate_changed_tree_replacement_verification(
                previous,
                current,
                continuation,
                claim,
                proposed,
                inspection,
                session_id=session_id,
                current_selection_sha256=digest(current_payload),
                continuation_selection_sha256=digest(continuation_payload),
            )

            artifacts = dict(previous_artifacts)
            for artifact_sha256, payload in (new_artifacts or {}).items():
                if (
                    artifact_sha256 in artifacts
                    and artifacts[artifact_sha256] != payload
                ):
                    raise ValueError(
                        "replacement verification replaces retained content"
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
                        "existing replacement archive conflicts with this closure"
                    ) from None
                archive_reused = True

            if (
                read_task_state_selection_at(selection_root, selection_name)
                != current_payload
            ):
                raise ValueError(
                    "current task-state selection changed during replacement"
                )
            if (
                read_private_continuation_payload(
                    self.continuation_selection_path,
                    CONTINUATION_SELECTION_BYTES,
                    "continuation selection",
                )
                != continuation_payload
                or read_private_continuation_payload(
                    self.claim_path,
                    CONTINUATION_CLAIM_BYTES,
                    "continuation claim",
                )
                != claim_payload
            ):
                raise ValueError("continuation evidence changed during replacement")
            if (
                self.inspector.inspect(self.workspace, previous.checkpoint.main_files)
                != inspection
            ):
                raise ValueError(
                    "live workspace changed during replacement verification"
                )

            selected = CurrentTaskStateSelection(
                project_id=proposed.scope.project_id,
                bundle_sha256=proposed.sha256,
                bundle_revision=proposed.revision,
                checkpoint_id=proposed.checkpoint.checkpoint_id,
                checkpoint_revision=proposed.checkpoint.revision,
                checkpoint_sha256=proposed.checkpoint.sha256,
                current_work_unit=proposed.checkpoint.current_work_unit,
            )
            selected_payload = canonical_bytes(selected)
            replace_task_state_selection(
                selection_root, selection_name, selected_payload
            )
            if (
                read_task_state_selection_at(selection_root, selection_name)
                != selected_payload
            ):
                raise ValueError("replacement selection commit did not reproduce")

        return ChangedTreeReplacementVerificationReceipt(
            session_id=session_id,
            previous_selection_sha256=expected_selection_sha256,
            continuation_selection_sha256=digest(continuation_payload),
            continuation_claim_sha256=digest(claim_payload),
            freshness_sha256=validation.freshness_sha256,
            changed_dimensions=validation.changed_dimensions,
            stale_verification_ids=validation.stale_verification_ids,
            replacement_verification_ids=validation.replacement_verification_ids,
            live_workspace=inspection.workspace,
            previous_bundle_sha256=previous.sha256,
            previous_bundle_revision=previous.revision,
            previous_checkpoint_sha256=previous.checkpoint.sha256,
            previous_checkpoint_revision=previous.checkpoint.revision,
            closed_work_unit=validation.closed.reference,
            bundle_sha256=proposed.sha256,
            bundle_revision=proposed.revision,
            checkpoint_sha256=proposed.checkpoint.sha256,
            checkpoint_revision=proposed.checkpoint.revision,
            current_selection_sha256=digest(selected_payload),
            remaining_outstanding_work=proposed.checkpoint.outstanding_work,
            task_ledger=proposed.checkpoint.task_ledger,
            cumulative_context_sha256=proposed.context_metrics.sha256,
            archive_reused=archive_reused,
        )
