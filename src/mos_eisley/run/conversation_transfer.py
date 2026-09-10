"""Explicit single-session JSON-to-SQLite copies between private storage roots."""

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import (
    Contract,
    Digest,
    canonical_bytes,
    canonical_fingerprint,
    digest,
)
from mos_eisley.run.conversation_migration import (
    ConversationMigration,
    MigrationSelection,
    migration_database_exists,
)
from mos_eisley.run.conversation_sqlite import (
    SQLiteConversationStore,
    sqlite_read_transaction,
)
from mos_eisley.run.conversation_store import (
    ConversationStore,
    validate_private_storage,
)


class TransferLocation(Contract):
    path: Annotated[str, Field(min_length=1, max_length=4096)]
    device: Annotated[int, Field(ge=0)]
    inode: Annotated[int, Field(ge=0)]

    @property
    def identity(self) -> tuple[int, int]:
        return self.device, self.inode


class ConversationTransferPlan(Contract):
    schema_version: Literal[1] = 1
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    source_backend: Literal["snapshot"] = "snapshot"
    destination_backend: Literal["sqlite"] = "sqlite"
    source: TransferLocation
    destination: TransferLocation
    selection: MigrationSelection

    @model_validator(mode="after")
    def separate_roots(self) -> Self:
        if self.source.identity == self.destination.identity:
            raise ValueError("transfer roots must differ")
        return self


class ConversationTransferReceipt(Contract):
    schema_version: Literal[1] = 1
    status: Literal["planned", "imported", "already_present"]
    transfer_sha256: Digest
    plan: ConversationTransferPlan
    source_retained: Literal[True] = True

    @model_validator(mode="after")
    def exact_plan(self) -> Self:
        if self.transfer_sha256 != digest(canonical_bytes(self.plan)):
            raise ValueError("transfer receipt does not match its plan")
        return self


@contextmanager
def _root(root: Path) -> Generator[int]:
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        validate_private_storage(fd, directory=True)
        yield fd
    finally:
        os.close(fd)


def _location(root: Path, fd: int) -> TransferLocation:
    info = os.fstat(fd)
    return TransferLocation(
        path=str(root.absolute()), device=info.st_dev, inode=info.st_ino
    )


def _check_locations(plan: ConversationTransferPlan) -> None:
    for selected in (plan.source, plan.destination):
        with _root(Path(selected.path)) as fd:
            if _location(Path(selected.path), fd) != selected:
                raise ValueError("selected transfer directory changed")


def inspect_transfer_destination(root: Path) -> TransferLocation:
    """Read an existing private destination identity without creating metadata."""
    with _root(root) as fd:
        location = _location(root, fd)
        migration_database_exists(fd)
        return location


def _preview_destination(
    plan: ConversationTransferPlan,
) -> Literal["planned", "already_present"]:
    target = Path(plan.destination.path)
    sid = plan.selection.session_id
    with _root(target) as fd:
        if _location(target, fd) != plan.destination:
            raise ValueError("selected transfer directory changed")
        exists = migration_database_exists(fd)
        try:
            os.stat(f"{sid}.lock", dir_fd=fd, follow_symlinks=False)
            has_lock = True
        except FileNotFoundError:
            has_lock = False
    if not has_lock:
        if exists:
            with sqlite_read_transaction(target) as (db, _, _):
                if db.execute("SELECT 1 FROM sessions WHERE sid=?", (sid,)).fetchone():
                    raise ValueError("destination session lock is missing")
        _check_locations(plan)
        return "planned"
    if not exists:
        with ConversationStore(
            target,
            sid,
            Path(plan.workspace),
            create=False,
            require_workspace=False,
            expected_root_identity=plan.destination.identity,
        ):
            pass
        _check_locations(plan)
        return "planned"
    with SQLiteConversationStore(
        target,
        sid,
        Path(plan.workspace),
        create=False,
        require_workspace=False,
        writable=False,
        expected_root_identity=plan.destination.identity,
    ) as destination:
        try:
            current = destination.load()
        except FileNotFoundError:
            status = "planned"
        else:
            if canonical_fingerprint(current).sha256 != plan.selection.snapshot_sha256:
                raise ValueError("destination contains a different session state")
            status = "already_present"
    _check_locations(plan)
    return status


def _apply_transfer(
    source: ConversationMigration, plan: ConversationTransferPlan
) -> Literal["imported", "already_present"]:
    selected = plan.selection
    snapshot, modified_ns, size = source.inspect_json_snapshot(
        byte_limit=selected.source_bytes
    )
    if snapshot.sha256 != selected.snapshot_sha256 or size != selected.source_bytes:
        raise ValueError("JSON source changed since transfer selection")
    _check_locations(plan)
    with _root(Path(plan.destination.path)) as fd:
        migration_database_exists(fd)
    with SQLiteConversationStore(
        Path(plan.destination.path),
        selected.session_id,
        Path(plan.workspace),
        require_workspace=False,
        expected_root_identity=plan.destination.identity,
    ) as destination:
        try:
            current = destination.load()
        except FileNotFoundError:
            pass
        else:
            if canonical_fingerprint(current).sha256 != selected.snapshot_sha256:
                raise ValueError("destination contains a different session state")
            _check_locations(plan)
            return "already_present"

        def validate_source() -> None:
            _check_locations(plan)
            if (
                source.inspect_selection(source_max_bytes=selected.source_bytes)
                != selected
            ):
                raise ValueError("JSON source changed during transfer")

        inserted = destination.import_snapshot(
            snapshot.state, modified_ns, validate_source=validate_source
        )
        return "imported" if inserted else "already_present"


def transfer_conversation(
    source_root: Path,
    destination_root: Path,
    session_id: str,
    workspace: Path,
    *,
    expected_sha256: str | None = None,
    apply: bool = False,
    source_max_bytes: int = MAX_SNAPSHOT_BYTES,
) -> ConversationTransferReceipt:
    try:
        sid = TypeAdapter[str](SessionID).validate_python(session_id)
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
    except ValueError:
        raise ValueError("invalid transfer session ID or expected hash") from None
    if apply and expected is None:
        raise ValueError("--apply requires --expected-sha256 from a transfer preview")
    with ConversationMigration(source_root, sid, workspace) as source:
        selected = source.inspect_selection(source_max_bytes=source_max_bytes)
        source_identity = source.storage_identity()
        destination = inspect_transfer_destination(destination_root)
        if source_identity == destination.identity:
            raise ValueError(
                "transfer requires different roots; use session-migrate here"
            )
        plan = ConversationTransferPlan(
            owner_uid=os.getuid(),
            workspace=source.workspace,
            source=TransferLocation(
                path=str(source_root.absolute()),
                device=source_identity[0],
                inode=source_identity[1],
            ),
            destination=destination,
            selection=selected,
        )
        sha = digest(canonical_bytes(plan))
        if expected is not None and expected != sha:
            raise ValueError(
                "transfer selection changed; preview again before applying"
            )
        status = _apply_transfer(source, plan) if apply else _preview_destination(plan)
        return ConversationTransferReceipt(
            status=status, transfer_sha256=sha, plan=plan
        )
