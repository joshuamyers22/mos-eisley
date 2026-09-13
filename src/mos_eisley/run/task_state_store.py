"""Private, content-addressed replay for G0 task-state contracts."""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import ArtifactHash, private_write
from mos_eisley.task_profile import (
    ProfileDiagnosticReport,
    TaskProfileManifest,
    diagnose_task_profile,
)
from mos_eisley.task_state import (
    ArtifactReference,
    ClauseRecord,
    CumulativeContextMetrics,
    DecisionRecord,
    MilestoneCheckpoint,
    OutcomeRecord,
    OwnerProjectScope,
    RequestContextMetric,
    WorkUnitRecord,
    accumulate_context_metrics,
    verify_bounded_evidence,
)

MAX_TASK_STATE_BYTES = 4_000_000
MAX_TASK_ARTIFACT_BYTES = 16_000_000
STATE_FILE = "state.json"
MANIFEST_FILE = "manifest.json"
ARTIFACT_DIRECTORY = "artifacts"


class ProfileAssessment(Contract):
    manifest: TaskProfileManifest
    report: ProfileDiagnosticReport

    @model_validator(mode="after")
    def reproducible_report(self) -> Self:
        if diagnose_task_profile(self.manifest) != self.report:
            raise ValueError("profile diagnostics do not reproduce from the manifest")
        return self


class TaskStateBundle(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["bounded_task_state"] = "bounded_task_state"
    scope: OwnerProjectScope
    revision: Annotated[int, Field(ge=1)]
    previous_bundle_sha256: Digest | None = None
    clauses: Annotated[tuple[ClauseRecord, ...], Field(max_length=256)] = ()
    decisions: Annotated[tuple[DecisionRecord, ...], Field(max_length=256)] = ()
    outcomes: Annotated[tuple[OutcomeRecord, ...], Field(max_length=256)] = ()
    work_units: Annotated[
        tuple[WorkUnitRecord, ...], Field(min_length=1, max_length=256)
    ]
    checkpoint: MilestoneCheckpoint
    context_requests: Annotated[
        tuple[RequestContextMetric, ...], Field(max_length=4096)
    ] = ()
    context_metrics: CumulativeContextMetrics
    profiles: Annotated[tuple[ProfileAssessment, ...], Field(max_length=64)] = ()
    runtime_continuation_enabled: Literal[False] = False

    @model_validator(mode="after")
    def connected_records(self) -> Self:
        scoped: tuple[Contract, ...] = (
            *self.clauses,
            *self.decisions,
            *self.outcomes,
            *self.work_units,
            self.checkpoint,
            *(item.manifest for item in self.profiles),
        )
        if any(getattr(item, "scope", None) != self.scope for item in scoped):
            raise ValueError("task records cross an owner or project boundary")

        def unique(values: tuple[object, ...], label: str) -> None:
            if len(set(values)) != len(values):
                raise ValueError(f"task bundle {label} identities must be unique")

        clause_refs = tuple(item.reference for item in self.clauses)
        decision_refs = tuple(item.reference for item in self.decisions)
        outcome_refs = tuple(item.reference for item in self.outcomes)
        work_refs = tuple(item.reference for item in self.work_units)
        unique(clause_refs, "clause")
        unique(decision_refs, "decision")
        unique(outcome_refs, "outcome")
        unique(work_refs, "work-unit")
        unique(tuple(item.manifest.profile_id for item in self.profiles), "profile")

        clauses = set(clause_refs)
        decisions = set(decision_refs)
        outcomes = {item.reference: item for item in self.outcomes}
        work_units = {item.reference: item for item in self.work_units}
        for work_unit in self.work_units:
            if not set(work_unit.applicable_clauses) <= clauses:
                raise ValueError("work unit references an absent clause revision")
            if work_unit.parent is not None and work_unit.parent not in work_units:
                raise ValueError("work unit references an absent parent revision")
            if not set(work_unit.dependencies) <= set(work_units):
                raise ValueError("work unit references an absent dependency revision")
            if (
                work_unit.outcome is not None
                and work_unit.outcome.reference not in outcomes
            ):
                raise ValueError(
                    "work-unit outcome is absent from the outcome inventory"
                )
            if work_unit.outcome is not None and (
                outcomes[work_unit.outcome.reference] != work_unit.outcome
            ):
                raise ValueError("work-unit outcome differs from its inventory record")
        checkpoint = self.checkpoint
        if checkpoint.current_work_unit not in work_units:
            raise ValueError("checkpoint current work unit is absent")
        if not set(checkpoint.outstanding_work) <= set(work_units):
            raise ValueError("checkpoint outstanding work is absent")
        if any(
            work_units[item].status not in ("queued", "active")
            for item in checkpoint.outstanding_work
        ):
            raise ValueError("checkpoint outstanding work must be nonterminal")
        if not set(checkpoint.active_decisions) <= decisions:
            raise ValueError("checkpoint decision is absent")
        if not set(checkpoint.completed_outcomes) <= set(outcomes):
            raise ValueError("checkpoint outcome is absent")
        if any(
            outcomes[item].status != "completed"
            for item in checkpoint.completed_outcomes
        ):
            raise ValueError("checkpoint completed outcomes must be completed")
        decision_inventory = {item.reference: item for item in self.decisions}
        if any(
            decision_inventory[item].status != "active"
            for item in checkpoint.active_decisions
        ):
            raise ValueError("checkpoint active decisions must be active")
        if accumulate_context_metrics(self.context_requests) != self.context_metrics:
            raise ValueError("context totals do not reproduce from request records")
        if checkpoint.context_metrics != self.context_metrics:
            raise ValueError("checkpoint context metrics differ from bundle totals")
        current = work_units[checkpoint.current_work_unit]
        if checkpoint.task_ledger != current.ledger:
            raise ValueError("checkpoint ledger differs from its current work unit")
        for assessment in self.profiles:
            if assessment.manifest.work_unit not in work_units:
                raise ValueError("task profile references an absent work unit")
        if len(canonical_bytes(self)) > MAX_TASK_STATE_BYTES:
            raise ValueError("task-state bundle exceeds its replay byte limit")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))

    def artifact_references(self) -> tuple[ArtifactReference, ...]:
        references: list[ArtifactReference] = []
        for work_unit in self.work_units:
            references.extend(item.artifact for item in work_unit.evidence)
        references.extend(
            verification.result
            for verification in self.checkpoint.verifications
            if verification.result is not None
        )
        by_digest: dict[str, ArtifactReference] = {}
        for reference in references:
            previous = by_digest.setdefault(reference.sha256, reference)
            if (
                previous.bytes != reference.bytes
                or previous.media_type != reference.media_type
                or previous.availability != reference.availability
                or previous.freshness != reference.freshness
            ):
                raise ValueError("artifact references disagree about retained content")
        return tuple(by_digest[key] for key in sorted(by_digest))


class TaskStateManifest(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["bounded_task_state_archive"] = "bounded_task_state_archive"
    bundle_sha256: Digest
    owner_uid: Annotated[int, Field(ge=0)]
    project_id: Identifier
    workspace_sha256: Digest
    files: Annotated[tuple[ArtifactHash, ...], Field(min_length=1, max_length=1024)]


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _directory_names(path: Path, *, owner_uid: int, maximum: int) -> set[str]:
    details = path.lstat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or details.st_uid != owner_uid
        or details.st_mode & 0o077
    ):
        raise ValueError("task-state archive contains a nonprivate directory")
    names: set[str] = set()
    with os.scandir(path) as entries:
        for entry in entries:
            if len(names) >= maximum or entry.name in names:
                raise ValueError("task-state archive directory inventory is invalid")
            names.add(entry.name)
    return names


def _read_private(path: Path, maximum: int, owner_uid: int) -> bytes:
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or details.st_uid != owner_uid
        or details.st_mode & 0o077
    ):
        raise ValueError("task-state archive contains a nonprivate file")
    return read_bounded(path, maximum)


def _verify_evidence_views(
    bundle: TaskStateBundle, artifacts: Mapping[str, bytes]
) -> None:
    for work_unit in bundle.work_units:
        for evidence in work_unit.evidence:
            if evidence.view is None or evidence.artifact.availability != "available":
                continue
            verify_bounded_evidence(
                evidence.view,
                artifacts[evidence.artifact.sha256],
            )


def save_task_state(
    root: Path,
    bundle: TaskStateBundle,
    artifacts: Mapping[str, bytes],
) -> Path:
    """Save one immutable archive; the manifest is its completion marker."""
    if bundle.scope.owner_uid != os.getuid():
        raise ValueError("task-state owner must match the current process owner")
    references = {
        item.sha256: item
        for item in bundle.artifact_references()
        if item.availability == "available"
    }
    if set(artifacts) != set(references):
        raise ValueError("archive artifacts must exactly match available references")
    for artifact_sha256, payload in artifacts.items():
        reference = references[artifact_sha256]
        if (
            len(payload) > MAX_TASK_ARTIFACT_BYTES
            or len(payload) != reference.bytes
            or digest(payload) != artifact_sha256
        ):
            raise ValueError("task artifact content does not match its reference")
    _verify_evidence_views(bundle, artifacts)

    state_payload = canonical_bytes(bundle)
    if len(state_payload) > MAX_TASK_STATE_BYTES:
        raise ValueError("task-state bundle exceeds its replay byte limit")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root_stat = root.lstat()
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or stat.S_ISLNK(root_stat.st_mode)
        or root_stat.st_uid != os.getuid()
        or root_stat.st_mode & 0o077
    ):
        raise ValueError("task-state archive root must be a private owned directory")
    destination = root / bundle.sha256
    if destination.exists():
        raise FileExistsError("task-state archive already exists")
    temporary = root / f".{bundle.sha256}.{uuid4().hex}.tmp"
    temporary.mkdir(mode=0o700)
    try:
        artifact_root = temporary / ARTIFACT_DIRECTORY
        artifact_root.mkdir(mode=0o700)
        private_write(temporary / STATE_FILE, state_payload)
        files = [ArtifactHash(name=STATE_FILE, sha256=digest(state_payload))]
        for artifact_sha256 in sorted(artifacts):
            payload = artifacts[artifact_sha256]
            name = f"{ARTIFACT_DIRECTORY}/{artifact_sha256}"
            private_write(artifact_root / artifact_sha256, payload)
            files.append(ArtifactHash(name=name, sha256=artifact_sha256))
        manifest = TaskStateManifest(
            bundle_sha256=bundle.sha256,
            owner_uid=bundle.scope.owner_uid,
            project_id=bundle.scope.project_id,
            workspace_sha256=bundle.scope.workspace_sha256,
            files=tuple(files),
        )
        private_write(temporary / MANIFEST_FILE, canonical_bytes(manifest))
        _sync_directory(artifact_root)
        _sync_directory(temporary)
        temporary.rename(destination)
        _sync_directory(root)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def load_task_state(
    path: Path,
    *,
    owner_uid: int,
    project_id: str,
    workspace_sha256: str,
) -> tuple[TaskStateBundle, dict[str, bytes]]:
    """Replay a complete archive only for its exact owner/project/workspace scope."""
    if owner_uid != os.getuid():
        raise ValueError("task-state replay owner must match the current process owner")
    path_stat = path.lstat()
    if (
        not stat.S_ISDIR(path_stat.st_mode)
        or stat.S_ISLNK(path_stat.st_mode)
        or path_stat.st_uid != owner_uid
        or path_stat.st_mode & 0o077
    ):
        raise ValueError("task-state archive requires a private owner directory")
    top_names = _directory_names(path, owner_uid=owner_uid, maximum=4)
    if top_names != {STATE_FILE, MANIFEST_FILE, ARTIFACT_DIRECTORY}:
        raise ValueError("task-state archive top-level inventory is invalid")
    manifest_payload = _read_private(
        path / MANIFEST_FILE, MAX_TASK_STATE_BYTES, owner_uid
    )
    try:
        parsed_manifest = json.loads(manifest_payload, object_pairs_hook=_unique_object)
        if not isinstance(parsed_manifest, dict):
            raise ValueError
        manifest = TaskStateManifest.model_validate_json(manifest_payload)
    except (ValueError, RecursionError):
        raise ValueError("invalid task-state manifest") from None
    if canonical_bytes(manifest) != manifest_payload:
        raise ValueError("task-state manifest is noncanonical")
    if (
        manifest.owner_uid != owner_uid
        or manifest.project_id != project_id
        or manifest.workspace_sha256 != workspace_sha256
    ):
        raise ValueError("task-state archive crosses an owner or project boundary")
    names = tuple(item.name for item in manifest.files)
    if len(set(names)) != len(names) or not names or names[0] != STATE_FILE:
        raise ValueError("task-state manifest file inventory is invalid")
    if any(
        item.name != f"{ARTIFACT_DIRECTORY}/{item.sha256}"
        for item in manifest.files[1:]
    ):
        raise ValueError("task-state manifest artifact names are invalid")
    artifact_names = _directory_names(
        path / ARTIFACT_DIRECTORY,
        owner_uid=owner_uid,
        maximum=1025,
    )
    if artifact_names != {
        name.removeprefix(f"{ARTIFACT_DIRECTORY}/") for name in names[1:]
    }:
        raise ValueError("task-state archive artifact inventory is invalid")
    payloads: dict[str, bytes] = {}
    for item in manifest.files:
        maximum = (
            MAX_TASK_STATE_BYTES if item.name == STATE_FILE else MAX_TASK_ARTIFACT_BYTES
        )
        payload = _read_private(path / item.name, maximum, owner_uid)
        if digest(payload) != item.sha256:
            raise ValueError("task-state archive artifact digest mismatch")
        payloads[item.name] = payload
    state_payload = payloads.pop(STATE_FILE)
    try:
        parsed = json.loads(state_payload, object_pairs_hook=_unique_object)
        if not isinstance(parsed, dict):
            raise ValueError
        bundle = TaskStateBundle.model_validate_json(state_payload)
    except (ValueError, RecursionError):
        raise ValueError("invalid task-state bundle") from None
    if (
        canonical_bytes(bundle) != state_payload
        or bundle.sha256 != manifest.bundle_sha256
    ):
        raise ValueError("task-state bundle is noncanonical or changed")
    if bundle.scope != OwnerProjectScope(
        owner_uid=owner_uid,
        project_id=project_id,
        workspace_sha256=workspace_sha256,
    ):
        raise ValueError("task-state bundle scope differs from its manifest")
    expected = {
        item.sha256
        for item in bundle.artifact_references()
        if item.availability == "available"
    }
    artifacts = {
        name.removeprefix(f"{ARTIFACT_DIRECTORY}/"): payload
        for name, payload in payloads.items()
    }
    if set(artifacts) != expected:
        raise ValueError("task-state replay artifact inventory is incomplete")
    _verify_evidence_views(bundle, artifacts)
    return bundle, artifacts


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate task-state key")
        value[key] = item
    return value
