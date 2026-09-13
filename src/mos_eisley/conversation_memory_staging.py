"""Exact raw staging review, with separate invalid and verified-project paths."""

import json
import os
import re
from pathlib import Path

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStorage
from mos_eisley.conversation_memory_cleanup import MemoryCleanupStore
from mos_eisley.conversation_memory_identity import RelocationSource
from mos_eisley.conversation_memory_raw import (
    MAX_RAW_REVIEW_BYTES,
    MemoryDiscardError,
    discard_reviewed,
    read_raw_record,
    validate_raw_review,
    verify_raw_record,
)
from mos_eisley.core.models import canonical_bytes

MAX_STAGING_REVIEW_BYTES = MAX_RAW_REVIEW_BYTES


class MemoryStagingDiscardError(MemoryDiscardError):
    """Report returned unlink/flush operations when an in-process apply fails."""

    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(receipt)
        self.args = (
            "Staging discard stopped; inspect the exact file before further action.",
        )
        self.receipt = receipt


class _StagingDiscardStore(MemoryStorage):
    def discard(
        self, name: str, raw_sha256: str, expected_sha256: str | None, max_bytes: int
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Discard requires existing memory storage and lock.")

            def inspect() -> dict[str, object]:
                storage = self._storage_identity(handles)
                payload, record = read_raw_record(
                    handles[0], name, raw_sha256, max_bytes
                )
                try:
                    MemorySnapshot.model_validate_json(payload)
                except ValueError:
                    pass
                else:
                    raise ValueError(
                        "Valid snapshots require project-aware cleanup; "
                        "raw discard is refused."
                    )
                if self._storage_identity(handles) != storage:
                    raise ValueError("Memory storage changed; preview discard again.")
                verify_raw_record(handles[0], name, record)
                return {
                    "schema_version": 1,
                    "operation": "discard-invalid-memory-staging",
                    "scope": "storage",
                    "project_identity": None,
                    "project_identity_verified": False,
                    "storage": storage,
                    "temporary_name": name,
                    "temporary_path": str(self.root / name),
                    **record,
                }

            return discard_reviewed(
                handles[0], name, inspect, expected_sha256, MemoryStagingDiscardError
            )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Project staging review refuses duplicate JSON keys.")
        result[key] = value
    return result


class _ProjectStagingDiscardStore(MemoryCleanupStore):
    def discard(
        self,
        workspace: RelocationSource,
        name: str,
        raw_sha256: str,
        expected_sha256: str | None,
        max_bytes: int,
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Discard requires existing memory storage and lock.")
            root = handles[0]

            def inspect() -> dict[str, object]:
                workspace.verify()
                storage = self._storage_identity(handles)
                payload, raw_record = read_raw_record(root, name, raw_sha256, max_bytes)
                snapshot = MemorySnapshot.model_validate_json(payload)
                json.loads(payload, object_pairs_hook=_unique_object)
                document = snapshot.document
                if (
                    document.owner_uid != os.getuid()
                    or document.scope != "project"
                    or document.workspace != self.workspace
                ):
                    raise ValueError(
                        "Staging record does not match this owner/project."
                    )
                current_identity = self._project_record_identity(root)
                current = self._read(root, "project")
                if (
                    self._project_record_identity(root) != current_identity
                    or self._storage_identity(handles) != storage
                ):
                    raise ValueError(
                        "Project memory or storage changed; preview again."
                    )
                workspace.verify()
                verify_raw_record(root, name, raw_record)
                return {
                    "schema_version": 1,
                    "operation": "discard-project-memory-staging",
                    "scope": "project",
                    "project_identity": self.workspace,
                    "project_identity_verified": True,
                    "workspace_identity": workspace.receipt(),
                    "storage": storage,
                    "temporary_name": name,
                    "temporary_path": str(self.root / name),
                    "record": snapshot.model_dump(mode="json"),
                    "serialization": "canonical"
                    if payload == canonical_bytes(snapshot)
                    else "noncanonical",
                    "current_project_path": str(self.path("project")),
                    "current_project": current.model_dump(mode="json")
                    if current
                    else None,
                    "current_record_identity": current_identity,
                    **raw_record,
                }

            return discard_reviewed(
                root, name, inspect, expected_sha256, MemoryStagingDiscardError
            )


def _validate_inputs(
    temporary_name: str, raw_sha256: str, expected_sha256: str | None, max_bytes: int
) -> None:
    if (
        re.fullmatch(
            r"\.memory-(?:migration|resolution)-[0-9a-f]{32}\.tmp", temporary_name
        )
        is None
    ):
        raise ValueError("Discard requires an exact supported staging filename.")
    validate_raw_review(raw_sha256, expected_sha256, max_bytes)


def discard_memory_staging(
    storage: Path,
    temporary_name: str,
    raw_sha256: str,
    *,
    expected_sha256: str | None = None,
    review_max_bytes: int = RECORD_BYTES,
) -> dict[str, object]:
    """Review exact raw bytes; never infer a project from an invalid record."""
    _validate_inputs(temporary_name, raw_sha256, expected_sha256, review_max_bytes)
    return _StagingDiscardStore(storage).discard(
        temporary_name, raw_sha256, expected_sha256, review_max_bytes
    )


def discard_project_memory_staging(
    storage: Path,
    workspace_identity: str,
    temporary_name: str,
    raw_sha256: str,
    *,
    expected_sha256: str | None = None,
    review_max_bytes: int = RECORD_BYTES,
) -> dict[str, object]:
    """Discard one valid project snapshot, binding its logical and exact raw forms."""
    _validate_inputs(temporary_name, raw_sha256, expected_sha256, review_max_bytes)
    workspace = RelocationSource.inspect(workspace_identity)
    return _ProjectStagingDiscardStore(storage, workspace).discard(
        workspace, temporary_name, raw_sha256, expected_sha256, review_max_bytes
    )
