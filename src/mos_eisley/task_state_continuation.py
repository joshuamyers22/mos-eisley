"""Explicit one-session continuation from a closed task-state checkpoint."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import selectors
import stat
import subprocess
import time
from collections.abc import Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self, cast
from uuid import uuid4

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
    ContinuationSelection,
    ShortText,
    WorkspaceState,
    WorkUnitRecord,
    validate_continuation,
)
from mos_eisley.task_state_acquisition import (
    RuntimeTaskState,
    TaskStateAcquisitionEvidence,
    decode_task_state_selection,
    validate_task_state_scope,
)

CONTINUATION_SELECTION_BYTES = 64 * 1024
CONTINUATION_CLAIM_BYTES = 128 * 1024
GIT_OUTPUT_BYTES = 4 * 1024 * 1024
DIRTY_CONTENT_BYTES = 16 * 1024 * 1024
LOCK_NAME = ".task-state-continuation.lock"
ChangedDimension = Literal["repository", "branch", "revision", "tree", "dirty_state"]


class RelevantFileInspection(Contract):
    """Current identity and checkpoint-relative status of one main file."""

    path: Annotated[str, Field(min_length=1, max_length=4096)]
    availability: Literal["available", "missing", "unsupported"]
    sha256: Digest | None = Field(default=None, exclude_if=lambda value: value is None)
    bytes: Annotated[int, Field(ge=0)] = 0
    changed_since_checkpoint: bool

    @model_validator(mode="after")
    def exact_available_file(self) -> Self:
        if (self.availability == "available") != (self.sha256 is not None):
            raise ValueError("available continuation file requires an exact digest")
        if self.availability != "available" and self.bytes != 0:
            raise ValueError("unavailable continuation file cannot claim bytes")
        return self


class WorkspaceInspection(Contract):
    """Bounded live Git and relevant-file observation."""

    schema_version: Literal[1] = 1
    workspace: WorkspaceState
    changed_paths: Annotated[tuple[str, ...], Field(max_length=4096)] = ()
    relevant_files: Annotated[
        tuple[RelevantFileInspection, ...], Field(max_length=64)
    ] = ()

    @model_validator(mode="after")
    def unique_inventory(self) -> Self:
        if len(set(self.changed_paths)) != len(self.changed_paths):
            raise ValueError("live workspace changed paths must be unique")
        paths = tuple(item.path for item in self.relevant_files)
        if len(set(paths)) != len(paths):
            raise ValueError("live workspace relevant files must be unique")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class ContinuationFreshness(Contract):
    """Explicit overlay that supersedes stale checkpoint passes."""

    schema_version: Literal[1] = 1
    checkpoint_workspace_sha256: Digest
    inspection: WorkspaceInspection
    changed_dimensions: Annotated[
        tuple[ChangedDimension, ...],
        Field(max_length=5),
    ] = ()
    stale_verification_ids: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()
    blockers: Annotated[tuple[ShortText, ...], Field(max_length=64)] = ()
    freshness_ready: bool

    @model_validator(mode="after")
    def exact_readiness(self) -> Self:
        if self.freshness_ready != (not self.changed_dimensions and not self.blockers):
            raise ValueError("continuation freshness readiness does not reproduce")
        if len(set(self.changed_dimensions)) != len(self.changed_dimensions):
            raise ValueError("continuation changed dimensions must be unique")
        if len(set(self.stale_verification_ids)) != len(self.stale_verification_ids):
            raise ValueError("continuation stale verification IDs must be unique")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class ContinuationClaim(Contract):
    """Durable one-session claim committed before recorded-model dispatch."""

    schema_version: Literal[1] = 1
    kind: Literal["task_state_continuation_claim"] = "task_state_continuation_claim"
    session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    current_selection_sha256: Digest
    continuation_selection_sha256: Digest
    bundle_sha256: Digest
    bundle_revision: Annotated[int, Field(ge=1)]
    checkpoint_sha256: Digest
    checkpoint_revision: Annotated[int, Field(ge=1)]
    selected_work_unit_id: Identifier
    selected_work_unit_revision: Annotated[int, Field(ge=1)]
    freshness_sha256: Digest
    continuation_claimed: Literal[True] = True
    grants_authority: Literal[False] = False

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class WorkspaceInspector(Protocol):
    def inspect(
        self, workspace: Path, relevant_files: Sequence[str]
    ) -> WorkspaceInspection: ...


def continuation_claim_path(storage: Path, selection: ContinuationSelection) -> Path:
    identity = digest(
        canonical_bytes(selection.scope) + canonical_bytes(selection.selected_work_unit)
    )
    return storage.absolute() / f"continuation-{identity}.json"


def decode_continuation_selection(payload: bytes) -> ContinuationSelection:
    if len(payload) > CONTINUATION_SELECTION_BYTES:
        raise ValueError("Continuation selection exceeds 64 KiB.")
    try:
        payload.decode("utf-8")
        parsed = json.loads(payload, object_pairs_hook=unique_object)
        if not isinstance(parsed, dict):
            raise ValueError
        return ContinuationSelection.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid continuation selection.") from None


def _git(workspace: Path, *arguments: str, maximum: int = GIT_OUTPUT_BYTES) -> bytes:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    process = subprocess.Popen(
        (
            "/usr/bin/git",
            "--no-pager",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-C",
            str(workspace),
            *arguments,
        ),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert process.stdout is not None
    output = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + 15
    try:
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(process.args, 15)
                if not selector.select(remaining):
                    raise subprocess.TimeoutExpired(process.args, 15)
                chunk = os.read(
                    process.stdout.fileno(), min(65_536, maximum + 1 - len(output))
                )
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > maximum:
                    raise ValueError("live Git inspection exceeds its output bound")
            result = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except BaseException:
            with suppress(ProcessLookupError):
                process.kill()
            process.wait()
            raise
    finally:
        selector.close()
        process.stdout.close()
    payload = bytes(output)
    if result != 0:
        detail = payload.decode("utf-8", errors="replace").strip()[:1000]
        raise ValueError(f"live Git inspection failed: {detail}")
    return payload


def _safe_relative_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("checkpoint main file escapes the repository")
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("continuation inspection does not follow symlink paths")
    resolved = (root / candidate).resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise ValueError("checkpoint main file escapes the repository")
    return resolved


def _file_payload(path: Path, maximum: int) -> tuple[bytes, str]:
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode):
        payload = os.readlink(path).encode("utf-8")
        kind = "symlink"
    elif stat.S_ISREG(details.st_mode):
        payload = read_bounded(path, maximum)
        kind = "file"
    else:
        raise ValueError("live Git inspection encountered an unsupported path")
    if len(payload) > maximum:
        raise ValueError("live Git dirty content exceeds its byte bound")
    return payload, kind


@dataclass(frozen=True)
class GitWorkspaceInspector:
    """Inspect one repository without changing its index or working tree."""

    git_output_bytes: int = GIT_OUTPUT_BYTES
    dirty_content_bytes: int = DIRTY_CONTENT_BYTES

    def inspect(
        self, workspace: Path, relevant_files: Sequence[str]
    ) -> WorkspaceInspection:
        root_text = (
            _git(
                workspace, "rev-parse", "--show-toplevel", maximum=self.git_output_bytes
            )
            .decode("utf-8")
            .strip()
        )
        root = Path(root_text).resolve(strict=True)
        requested = workspace.resolve(strict=True)
        if requested != root and root not in requested.parents:
            raise ValueError("live Git root does not contain the workspace")
        revision = (
            _git(root, "rev-parse", "--verify", "HEAD", maximum=self.git_output_bytes)
            .decode("ascii")
            .strip()
        )
        tree = _git(
            root, "rev-parse", "--verify", "HEAD^{tree}", maximum=self.git_output_bytes
        ).strip()
        branch = (
            _git(root, "branch", "--show-current", maximum=self.git_output_bytes)
            .decode("utf-8")
            .strip()
            or "(detached)"
        )
        diff = _git(
            root,
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            "HEAD",
            "--",
            maximum=self.git_output_bytes,
        )
        tracked_names = _git(
            root,
            "diff",
            "--name-only",
            "-z",
            "--no-ext-diff",
            "--no-textconv",
            "HEAD",
            "--",
            maximum=self.git_output_bytes,
        )
        untracked_names = _git(
            root,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            maximum=self.git_output_bytes,
        )
        changed = tuple(
            sorted(
                {
                    item.decode("utf-8")
                    for item in (
                        *tracked_names.split(b"\0"),
                        *untracked_names.split(b"\0"),
                    )
                    if item
                }
            )
        )
        dirty = hashlib.sha256(b"mos-eisley/git-dirty-state/v1\x00")
        dirty.update(len(diff).to_bytes(8, "big"))
        dirty.update(diff)
        remaining = self.dirty_content_bytes
        for name_bytes in sorted(item for item in untracked_names.split(b"\0") if item):
            name = name_bytes.decode("utf-8")
            path = _safe_relative_path(root, name)
            payload, kind = _file_payload(path, remaining)
            remaining -= len(payload)
            dirty.update(len(name_bytes).to_bytes(8, "big"))
            dirty.update(name_bytes)
            dirty.update(kind.encode("ascii") + b"\x00")
            dirty.update(len(payload).to_bytes(8, "big"))
            dirty.update(payload)

        inspected_files: list[RelevantFileInspection] = []
        changed_set = set(changed)
        for name in relevant_files:
            path = _safe_relative_path(root, name)
            try:
                payload, _kind = _file_payload(path, self.dirty_content_bytes)
            except FileNotFoundError:
                inspected_files.append(
                    RelevantFileInspection(
                        path=name,
                        availability="missing",
                        changed_since_checkpoint=name in changed_set,
                    )
                )
            except ValueError:
                inspected_files.append(
                    RelevantFileInspection(
                        path=name,
                        availability="unsupported",
                        changed_since_checkpoint=name in changed_set,
                    )
                )
            else:
                inspected_files.append(
                    RelevantFileInspection(
                        path=name,
                        availability="available",
                        sha256=digest(payload),
                        bytes=len(payload),
                        changed_since_checkpoint=name in changed_set,
                    )
                )
        return WorkspaceInspection(
            workspace=WorkspaceState(
                repository_sha256=digest(
                    b"mos-eisley/git-repository/v1\x00" + str(root).encode("utf-8")
                ),
                branch=branch,
                revision=revision,
                tree_sha256=digest(tree),
                dirty_state_sha256=dirty.hexdigest(),
            ),
            changed_paths=changed,
            relevant_files=tuple(inspected_files),
        )


def continuation_freshness(
    bundle: TaskStateBundle,
    work_unit: WorkUnitRecord,
    inspection: WorkspaceInspection,
) -> ContinuationFreshness:
    checkpoint = bundle.checkpoint
    pairs: tuple[tuple[ChangedDimension, str, str], ...] = (
        (
            "repository",
            checkpoint.workspace.repository_sha256,
            inspection.workspace.repository_sha256,
        ),
        ("branch", checkpoint.workspace.branch, inspection.workspace.branch),
        ("revision", checkpoint.workspace.revision, inspection.workspace.revision),
        ("tree", checkpoint.workspace.tree_sha256, inspection.workspace.tree_sha256),
        (
            "dirty_state",
            checkpoint.workspace.dirty_state_sha256,
            inspection.workspace.dirty_state_sha256,
        ),
    )
    changed_dimensions = cast(
        tuple[ChangedDimension, ...],
        tuple(name for name, previous, current in pairs if previous != current),
    )
    stale = (
        tuple(
            item.verification_id
            for item in checkpoint.verifications
            if item.status == "passed"
        )
        if changed_dimensions
        else ()
    )
    blockers: list[str] = []
    if changed_dimensions:
        blockers.append(
            "live workspace differs from checkpoint: " + ", ".join(changed_dimensions)
        )
    blockers.extend(
        f"checkpoint main file is {item.availability}: {item.path}"
        for item in inspection.relevant_files
        if item.availability != "available"
    )
    blockers.extend(
        f"required input is not current and available: {item.input_id}"
        for item in work_unit.required_inputs
        if item.required
        and (item.availability != "available" or item.freshness != "current")
    )
    blockers.extend(
        f"retained work evidence is not current and available: {item.evidence_id}"
        for item in work_unit.evidence
        if item.artifact.availability != "available"
        or item.artifact.freshness != "current"
    )
    return ContinuationFreshness(
        checkpoint_workspace_sha256=checkpoint.workspace.sha256,
        inspection=inspection,
        changed_dimensions=changed_dimensions,
        stale_verification_ids=stale,
        blockers=tuple(blockers),
        freshness_ready=not changed_dimensions and not blockers,
    )


def _validate_dependencies(bundle: TaskStateBundle, work_unit: WorkUnitRecord) -> None:
    for dependency in work_unit.dependencies:
        revisions = tuple(
            item
            for item in bundle.work_units
            if item.work_unit_id == dependency.work_unit_id
            and item.revision >= dependency.revision
        )
        latest = max(revisions, key=lambda item: item.revision, default=None)
        if latest is None or latest.status != "completed":
            raise ValueError(
                "continuation dependency is not completed: "
                f"{dependency.work_unit_id}@{dependency.revision}"
            )


def read_private_continuation_payload(path: Path, maximum: int, label: str) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        details = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
            or details.st_nlink != 1
        ):
            raise ValueError(f"{label} must be a private owned file")
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError(f"{label} exceeds its byte bound")
    return payload


def _private_directory(fd: int) -> None:
    details = os.fstat(fd)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_mode & 0o077
    ):
        raise ValueError("continuation claim directory must be private and owner-only")


def validate_private_continuation_parent(path: Path, label: str) -> None:
    absolute = path.absolute()
    parent = os.open(absolute.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _private_directory(parent)
        held = os.fstat(parent)
        named = absolute.parent.stat(follow_symlinks=False)
        if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError(f"{label} directory changed")
    finally:
        os.close(parent)


@contextmanager
def _claim_lock(path: Path):
    absolute = path.absolute()
    parent = os.open(absolute.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock = -1
    try:
        _private_directory(parent)
        held_parent = os.fstat(parent)
        named_parent = absolute.parent.stat(follow_symlinks=False)
        if (held_parent.st_dev, held_parent.st_ino) != (
            named_parent.st_dev,
            named_parent.st_ino,
        ):
            raise ValueError("continuation claim directory changed")
        lock = os.open(
            LOCK_NAME,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=parent,
        )
        details = os.fstat(lock)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
            or details.st_nlink != 1
        ):
            raise ValueError("continuation claim lock must be private and owner-only")
        named_lock = os.stat(LOCK_NAME, dir_fd=parent, follow_symlinks=False)
        if (details.st_dev, details.st_ino) != (
            named_lock.st_dev,
            named_lock.st_ino,
        ):
            raise ValueError("continuation claim lock changed")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another continuation claim is in progress") from None
        yield parent, absolute.name
    finally:
        if lock >= 0:
            os.close(lock)
        os.close(parent)


def decode_continuation_claim(payload: bytes) -> ContinuationClaim:
    try:
        parsed = json.loads(payload, object_pairs_hook=unique_object)
        if not isinstance(parsed, dict):
            raise ValueError
        claim = ContinuationClaim.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("invalid continuation claim") from None
    if canonical_bytes(claim) != payload:
        raise ValueError("continuation claim is noncanonical")
    return claim


def _read_claim_at(parent: int, name: str) -> ContinuationClaim:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, "rb") as stream:
        details = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
            or details.st_nlink != 1
        ):
            raise ValueError("continuation claim must be private and owner-only")
        payload = stream.read(CONTINUATION_CLAIM_BYTES + 1)
    if len(payload) > CONTINUATION_CLAIM_BYTES:
        raise ValueError("continuation claim exceeds its byte bound")
    return decode_continuation_claim(payload)


def _write_claim_at(parent: int, name: str, claim: ContinuationClaim) -> None:
    payload = canonical_bytes(claim)
    temporary = f".{name}.{uuid4().hex}.tmp"
    fd = -1
    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(
            temporary,
            name,
            src_dir_fd=parent,
            dst_dir_fd=parent,
            follow_symlinks=False,
        )
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
    finally:
        if fd >= 0:
            os.close(fd)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=parent)


@dataclass(frozen=True)
class FreshContextContinuationAcquirer:
    """Claim and materialize one explicit continuation into a fresh session."""

    storage: Path
    current_selection_path: Path
    current_selection_payload: bytes
    continuation_selection_path: Path
    continuation_selection_payload: bytes
    claim_path: Path
    inspector: WorkspaceInspector = GitWorkspaceInspector()

    def __post_init__(self) -> None:
        decode_task_state_selection(self.current_selection_payload)
        selection = decode_continuation_selection(self.continuation_selection_payload)
        if self.claim_path.absolute() != continuation_claim_path(
            self.storage, selection
        ):
            raise ValueError(
                "continuation claim path must match its canonical work identity"
            )
        if self.claim_path.absolute() in {
            self.current_selection_path.absolute(),
            self.continuation_selection_path.absolute(),
        }:
            raise ValueError("continuation claim cannot replace a selection file")
        if self.claim_path.name == LOCK_NAME:
            raise ValueError("continuation claim cannot replace its lock")

    @classmethod
    def from_paths(
        cls,
        storage: Path,
        current_selection_path: Path,
        continuation_selection_path: Path,
        claim_path: Path | None = None,
        *,
        inspector: WorkspaceInspector | None = None,
    ) -> Self:
        continuation_payload = read_private_continuation_payload(
            continuation_selection_path,
            CONTINUATION_SELECTION_BYTES,
            "continuation selection",
        )
        if claim_path is None:
            claim_path = continuation_claim_path(
                storage, decode_continuation_selection(continuation_payload)
            )
        validate_private_continuation_parent(
            current_selection_path, "current task-state selection"
        )
        validate_private_continuation_parent(
            continuation_selection_path, "continuation selection"
        )
        validate_private_continuation_parent(claim_path, "continuation claim")
        return cls(
            storage=storage.absolute(),
            current_selection_path=current_selection_path.absolute(),
            current_selection_payload=read_private_continuation_payload(
                current_selection_path,
                CONTINUATION_SELECTION_BYTES,
                "current task-state selection",
            ),
            continuation_selection_path=continuation_selection_path.absolute(),
            continuation_selection_payload=read_private_continuation_payload(
                continuation_selection_path,
                CONTINUATION_SELECTION_BYTES,
                "continuation selection",
            ),
            claim_path=claim_path.absolute(),
            inspector=GitWorkspaceInspector() if inspector is None else inspector,
        )

    def validate_launch(
        self,
        *,
        session_id: str,
        has_history: bool,
        owner_uid: int,
        workspace: str,
    ) -> None:
        if has_history:
            try:
                payload = read_private_continuation_payload(
                    self.claim_path, CONTINUATION_CLAIM_BYTES, "continuation claim"
                )
            except FileNotFoundError:
                raise ValueError(
                    "an unclaimed continuation must start in a fresh conversation"
                ) from None
            claim = decode_continuation_claim(payload)
            if claim.session_id != session_id:
                raise ValueError("continuation is already claimed by another session")
        self.acquire(owner_uid=owner_uid, workspace=workspace, session_id=session_id)

    def _claim(self, proposed: ContinuationClaim) -> tuple[ContinuationClaim, bool]:
        with _claim_lock(self.claim_path) as (parent, name):
            try:
                current = _read_claim_at(parent, name)
            except FileNotFoundError:
                _write_claim_at(parent, name, proposed)
                current = _read_claim_at(parent, name)
                reused = False
            else:
                reused = True
            if current.session_id != proposed.session_id:
                raise ValueError("continuation is already claimed by another session")
            if current != proposed:
                raise ValueError(
                    "existing continuation claim differs from this handoff"
                )
            return current, reused

    def acquire(
        self, *, owner_uid: int, workspace: str, session_id: str | None = None
    ) -> RuntimeTaskState:
        if owner_uid != os.getuid():
            raise ValueError("continuation belongs to another owner")
        if session_id is None:
            raise ValueError("continuation acquisition requires a session identity")
        current_payload = read_private_continuation_payload(
            self.current_selection_path,
            CONTINUATION_SELECTION_BYTES,
            "current task-state selection",
        )
        continuation_payload = read_private_continuation_payload(
            self.continuation_selection_path,
            CONTINUATION_SELECTION_BYTES,
            "continuation selection",
        )
        if current_payload != self.current_selection_payload:
            raise ValueError("current task-state selection changed since launch")
        if continuation_payload != self.continuation_selection_payload:
            raise ValueError("continuation selection changed since launch")
        current = decode_task_state_selection(current_payload)
        selection = decode_continuation_selection(continuation_payload)
        archive = self.storage / current.bundle_sha256
        bundle, artifacts = load_task_state(
            archive,
            owner_uid=owner_uid,
            project_id=current.project_id,
            workspace_sha256=conversation_workspace_sha256(workspace),
        )
        if (
            bundle.sha256 != current.bundle_sha256
            or bundle.revision != current.bundle_revision
            or bundle.checkpoint.checkpoint_id != current.checkpoint_id
            or bundle.checkpoint.revision != current.checkpoint_revision
            or bundle.checkpoint.sha256 != current.checkpoint_sha256
            or bundle.checkpoint.current_work_unit != current.current_work_unit
        ):
            raise ValueError("current task-state selection differs from its archive")
        work_by_reference = {item.reference: item for item in bundle.work_units}
        try:
            source_work = work_by_reference[selection.selected_work_unit]
        except KeyError:
            raise ValueError(
                "continuation work unit is absent from the archive"
            ) from None
        validate_continuation(bundle.checkpoint, source_work, selection)
        _validate_dependencies(bundle, source_work)
        inspection = self.inspector.inspect(
            Path(workspace), bundle.checkpoint.main_files
        )
        inspection = WorkspaceInspection.model_validate(inspection.model_dump())
        if (
            tuple(item.path for item in inspection.relevant_files)
            != bundle.checkpoint.main_files
        ):
            raise ValueError("continuation inspection omits checkpoint main files")
        recovered = set(artifacts) | {
            item.sha256
            for item in inspection.relevant_files
            if item.availability == "available"
        }
        for required_input in source_work.required_inputs:
            if required_input.required and required_input.sha256 not in recovered:
                raise ValueError(
                    "required continuation input cannot be recovered: "
                    + required_input.input_id
                )
        freshness = continuation_freshness(bundle, source_work, inspection)
        proposed_claim = ContinuationClaim(
            session_id=session_id,
            current_selection_sha256=digest(current_payload),
            continuation_selection_sha256=digest(continuation_payload),
            bundle_sha256=bundle.sha256,
            bundle_revision=bundle.revision,
            checkpoint_sha256=bundle.checkpoint.sha256,
            checkpoint_revision=bundle.checkpoint.revision,
            selected_work_unit_id=source_work.work_unit_id,
            selected_work_unit_revision=source_work.revision,
            freshness_sha256=freshness.sha256,
        )
        omitted = tuple(
            item.evidence_id for item in source_work.evidence if item.view is not None
        )
        work = source_work.model_copy(
            update={
                "evidence": tuple(
                    item.model_copy(update={"view": None})
                    for item in source_work.evidence
                )
            }
        )
        clauses = {item.reference: item for item in bundle.clauses}
        decisions = {item.reference: item for item in bundle.decisions}
        manifest = read_bounded(archive / MANIFEST_FILE, MAX_TASK_STATE_BYTES)
        result = RuntimeTaskState(
            scope=bundle.scope,
            bundle_sha256=bundle.sha256,
            bundle_revision=bundle.revision,
            checkpoint=bundle.checkpoint,
            current_work_unit=work,
            applicable_clauses=tuple(clauses[item] for item in work.applicable_clauses),
            active_decisions=tuple(
                decisions[item] for item in bundle.checkpoint.active_decisions
            ),
            acquisition=TaskStateAcquisitionEvidence(
                selection_source_sha256=digest(current_payload),
                archive_manifest_sha256=digest(manifest),
                bundle_sha256=bundle.sha256,
                bundle_revision=bundle.revision,
                checkpoint_id=bundle.checkpoint.checkpoint_id,
                checkpoint_revision=bundle.checkpoint.revision,
                checkpoint_sha256=bundle.checkpoint.sha256,
                current_work_unit=work.reference,
                omitted_evidence_view_ids=omitted,
                live_workspace=inspection.workspace,
                workspace_matches_checkpoint=(
                    inspection.workspace == bundle.checkpoint.workspace
                ),
                stale_verification_ids=freshness.stale_verification_ids,
                continuation_selection_sha256=digest(continuation_payload),
                continuation_claim_sha256=proposed_claim.sha256,
                continuation_blockers=freshness.blockers,
                live_workspace_freshness_verified=True,
                continuation_claimed=True,
                freshness_ready=freshness.freshness_ready,
            ),
        )
        validate_task_state_scope(result, owner_uid=owner_uid, workspace=workspace)
        claim, _reused = self._claim(proposed_claim)
        if claim != proposed_claim:
            raise ValueError("continuation claim commit did not reproduce")
        if (
            read_private_continuation_payload(
                self.current_selection_path,
                CONTINUATION_SELECTION_BYTES,
                "current task-state selection",
            )
            != current_payload
            or read_private_continuation_payload(
                self.continuation_selection_path,
                CONTINUATION_SELECTION_BYTES,
                "continuation selection",
            )
            != continuation_payload
        ):
            raise ValueError("continuation selection changed during acquisition")
        if (
            self.inspector.inspect(Path(workspace), bundle.checkpoint.main_files)
            != inspection
        ):
            raise ValueError("live workspace changed during continuation acquisition")
        return result
