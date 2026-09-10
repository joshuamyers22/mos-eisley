"""Bounded, explicitly selected imports with a stable batch hash and safe retries."""

import os
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_migration import (
    ConversationMigration,
    ConversationMigrationReceipt,
    MigrationSelection,
)
from mos_eisley.run.conversation_store import validate_private_storage

MAX_BATCH_SESSIONS = 32
MAX_BATCH_SOURCE_BYTES = 64_000_000


class BatchMigrationPlan(Contract):
    schema_version: Literal[1] = 1
    owner_uid: Annotated[int, Field(ge=0)]
    storage_root: Annotated[str, Field(min_length=1, max_length=4096)]
    storage_device: Annotated[int, Field(ge=0)]
    storage_inode: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    source_byte_limit: Literal[64_000_000] = MAX_BATCH_SOURCE_BYTES
    entries: Annotated[
        tuple[MigrationSelection, ...],
        Field(min_length=1, max_length=MAX_BATCH_SESSIONS),
    ]
    source_bytes: Annotated[int, Field(ge=1, le=MAX_BATCH_SOURCE_BYTES)]
    logical_bytes: Annotated[int, Field(ge=1)]
    messages: Annotated[int, Field(ge=0, le=MAX_BATCH_SESSIONS * 16)]

    @model_validator(mode="after")
    def exact_selection(self) -> Self:
        ids = [entry.session_id for entry in self.entries]
        if ids != sorted(set(ids)) or (
            self.source_bytes != sum(entry.source_bytes for entry in self.entries)
            or self.logical_bytes != sum(entry.logical_bytes for entry in self.entries)
            or self.messages != sum(entry.messages for entry in self.entries)
        ):
            raise ValueError("invalid batch selection or totals")
        return self


class BatchMigrationReceipt(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["preview", "apply"]
    status: Literal["planned", "completed", "stopped"]
    batch_sha256: Digest
    plan: BatchMigrationPlan
    receipts: Annotated[
        tuple[ConversationMigrationReceipt, ...], Field(max_length=MAX_BATCH_SESSIONS)
    ]
    imported: Annotated[int, Field(ge=0, le=MAX_BATCH_SESSIONS)]
    already_present: Annotated[int, Field(ge=0, le=MAX_BATCH_SESSIONS)]
    failed_session_id: SessionID | None = None
    failure: Literal["source_or_destination_invalid", "storage_unavailable"] | None = (
        None
    )
    source_retained: Literal[True] = True

    @model_validator(mode="after")
    def verified_results(self) -> Self:
        selected = self.plan.entries
        if (
            self.batch_sha256 != digest(canonical_bytes(self.plan))
            or len(self.receipts) > len(selected)
            or self.imported != sum(item.status == "imported" for item in self.receipts)
            or self.already_present
            != sum(item.status == "already_present" for item in self.receipts)
        ):
            raise ValueError("invalid batch receipt hash or counts")
        for actual, expected in zip(self.receipts, selected, strict=False):
            if any(
                getattr(actual, field) != getattr(expected, field)
                for field in MigrationSelection.model_fields
            ):
                raise ValueError("batch receipt does not match its selected source")
            if actual.status == ("imported" if self.mode == "preview" else "planned"):
                raise ValueError("batch result does not match its execution mode")
        if self.status == "stopped":
            if (
                len(self.receipts) >= len(selected)
                or self.failed_session_id != selected[len(self.receipts)].session_id
                or self.failure is None
            ):
                raise ValueError("invalid stopped batch result")
        elif (
            len(self.receipts) != len(selected)
            or self.failed_session_id is not None
            or self.failure is not None
            or self.status != ("planned" if self.mode == "preview" else "completed")
        ):
            raise ValueError("invalid completed batch result")
        return self


class BatchMigrationError(ValueError):
    def __init__(self, receipt: BatchMigrationReceipt) -> None:
        self.receipt = receipt
        super().__init__(
            f"Batch stopped at session {receipt.failed_session_id}; "
            "completed imports remain saved and JSON sources are retained. "
            "Resolve the source/destination problem, then retry the unchanged "
            "selection with the same hash or preview a changed selection again."
        )


def _identity(root: Path) -> tuple[int, int]:
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        validate_private_storage(fd, directory=True)
        info = os.fstat(fd)
        return info.st_dev, info.st_ino
    finally:
        os.close(fd)


def _plan(root: Path, workspace: Path, ids: tuple[str, ...]) -> BatchMigrationPlan:
    identity = _identity(root)
    entries: list[MigrationSelection] = []
    total = 0
    for sid in ids:
        remaining = MAX_BATCH_SOURCE_BYTES - total
        if remaining <= 0:
            raise ValueError("batch sources exceed the 64000000-byte read budget")
        try:
            with ConversationMigration(root, sid, workspace) as migration:
                if migration.storage_identity() != identity:
                    raise ValueError("batch storage directory changed")
                entry = migration.inspect_selection(
                    source_max_bytes=min(MAX_SNAPSHOT_BYTES, remaining)
                )
        except (OSError, ValueError) as error:
            raise ValueError(
                f"Batch source preflight failed for session {sid}; check ownership, "
                "workspace, locks, integrity and the 64000000-byte source budget."
            ) from error
        entries.append(entry)
        total += entry.source_bytes
    return BatchMigrationPlan(
        owner_uid=os.getuid(),
        storage_root=str(root.absolute()),
        storage_device=identity[0],
        storage_inode=identity[1],
        workspace=str(workspace.resolve()),
        entries=tuple(entries),
        source_bytes=total,
        logical_bytes=sum(entry.logical_bytes for entry in entries),
        messages=sum(entry.messages for entry in entries),
    )


def _receipt(
    plan: BatchMigrationPlan,
    receipts: list[ConversationMigrationReceipt],
    *,
    apply: bool,
    failed: str | None = None,
    failure: Literal["source_or_destination_invalid", "storage_unavailable"]
    | None = None,
) -> BatchMigrationReceipt:
    return BatchMigrationReceipt(
        mode="apply" if apply else "preview",
        status="stopped" if failed is not None else "completed" if apply else "planned",
        batch_sha256=digest(canonical_bytes(plan)),
        plan=plan,
        receipts=tuple(receipts),
        imported=sum(receipt.status == "imported" for receipt in receipts),
        already_present=sum(
            receipt.status == "already_present" for receipt in receipts
        ),
        failed_session_id=failed,
        failure=failure,
    )


def migrate_batch(
    root: Path,
    session_ids: tuple[str, ...],
    workspace: Path,
    *,
    expected_sha256: str | None = None,
    apply: bool = False,
) -> BatchMigrationReceipt:
    """Preflight all sources, then verify/import one locked session at a time.

    Transactions are per session. The plan excludes destination status so a retry
    keeps its selection hash after earlier imports have committed successfully.
    """
    if not 1 <= len(session_ids) <= MAX_BATCH_SESSIONS:
        raise ValueError("a migration batch requires 1–32 explicit session IDs")
    try:
        ids = tuple(
            sorted(
                TypeAdapter[str](SessionID).validate_python(sid) for sid in session_ids
            )
        )
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
    except ValueError:
        raise ValueError("invalid batch session ID or expected hash") from None
    if len(set(ids)) != len(ids):
        raise ValueError("a migration batch cannot repeat session IDs")
    if apply and expected is None:
        raise ValueError("--apply requires --expected-sha256 from a batch preview")
    plan = _plan(root, workspace, ids)
    if expected is not None and expected != digest(canonical_bytes(plan)):
        raise ValueError("batch selection changed; preview again before applying")
    receipts: list[ConversationMigrationReceipt] = []
    for entry in plan.entries:
        try:
            with ConversationMigration(root, entry.session_id, workspace) as migration:
                if migration.storage_identity() != (
                    plan.storage_device,
                    plan.storage_inode,
                ):
                    raise ValueError("batch storage directory changed")
                receipt = migration.migrate(
                    expected_sha256=entry.snapshot_sha256,
                    expected_selection=entry,
                    apply=apply,
                )
            receipts.append(receipt)
        except (OSError, ValueError) as error:
            raise BatchMigrationError(
                _receipt(
                    plan,
                    receipts,
                    apply=apply,
                    failed=entry.session_id,
                    failure="storage_unavailable"
                    if isinstance(error, OSError)
                    else "source_or_destination_invalid",
                )
            ) from error
    return _receipt(plan, receipts, apply=apply)
