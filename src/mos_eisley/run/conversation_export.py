"""Explicit source-preserving SQLite-to-JSON export under session locks."""

import os
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore
from mos_eisley.run.conversation_transfer import (
    TransferLocation,
    inspect_storage_location,
)


class ConversationExportPlan(Contract):
    schema_version: Literal[1, 2] = 1
    source_backend: Literal["sqlite"] = "sqlite"
    destination_backend: Literal["snapshot"] = "snapshot"
    source: TransferLocation
    destination: TransferLocation
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    session_id: SessionID
    snapshot_sha256: Digest
    revision: Annotated[int, Field(ge=0)]
    messages: Annotated[int, Field(ge=0, le=16)]
    snapshot_bytes: Annotated[int, Field(ge=1, le=MAX_SNAPSHOT_BYTES)]

    @model_validator(mode="after")
    def versioned_layout(self) -> Self:
        same_root = self.source.identity == self.destination.identity
        if same_root != (self.schema_version == 2):
            raise ValueError("export plan version does not match its directory layout")
        return self


class ConversationExportReceipt(Contract):
    schema_version: Literal[1] = 1
    status: Literal["planned", "exported", "already_present"]
    export_sha256: Digest
    plan: ConversationExportPlan
    source_retained: Literal[True] = True

    @model_validator(mode="after")
    def exact_plan(self) -> Self:
        if self.export_sha256 != digest(canonical_bytes(self.plan)):
            raise ValueError("export receipt does not match its plan")
        return self


def _check_locations(plan: ConversationExportPlan) -> None:
    for location in (plan.source, plan.destination):
        if inspect_storage_location(Path(location.path)) != location:
            raise ValueError("selected export directory changed")


def _plan(
    snapshot: ConversationSnapshot,
    source: TransferLocation,
    destination: TransferLocation,
) -> ConversationExportPlan:
    size = len(canonical_bytes(snapshot))
    if size > snapshot.state.snapshot_byte_limit:
        raise ValueError("exported snapshot exceeds its saved byte limit")
    return ConversationExportPlan(
        schema_version=2 if source.identity == destination.identity else 1,
        source=source,
        destination=destination,
        owner_uid=snapshot.state.owner_uid,
        workspace=snapshot.state.workspace,
        session_id=snapshot.state.session_id,
        snapshot_sha256=snapshot.sha256,
        revision=snapshot.state.revision,
        messages=len(snapshot.state.entries),
        snapshot_bytes=size,
    )


def _preview_snapshot(
    destination: ConversationStore, plan: ConversationExportPlan
) -> Literal["planned", "already_present"]:
    try:
        current = destination.inspect_json_snapshot()[0]
    except FileNotFoundError:
        status = "planned"
    else:
        if current.sha256 != plan.snapshot_sha256:
            raise ValueError("destination contains a different session state")
        status = "already_present"
    _check_locations(plan)
    return status


def _preview(plan: ConversationExportPlan) -> Literal["planned", "already_present"]:
    target = Path(plan.destination.path)
    fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != plan.destination.identity:
            raise ValueError("selected export directory changed")
        try:
            os.stat(f"{plan.session_id}.lock", dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            try:
                os.stat(f"{plan.session_id}.json", dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                _check_locations(plan)
                return "planned"
            raise ValueError("destination session lock is missing") from None
    finally:
        os.close(fd)
    with ConversationStore(
        target,
        plan.session_id,
        Path(plan.workspace),
        create=False,
        require_workspace=False,
        expected_root_identity=plan.destination.identity,
    ) as destination:
        return _preview_snapshot(destination, plan)


def export_conversation(
    source_root: Path,
    destination_root: Path,
    session_id: str,
    workspace: Path,
    *,
    expected_sha256: str | None = None,
    apply: bool = False,
) -> ConversationExportReceipt:
    try:
        sid = TypeAdapter[str](SessionID).validate_python(session_id)
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
    except ValueError:
        raise ValueError("invalid export session ID or expected hash") from None
    if apply and expected is None:
        raise ValueError("--apply requires --expected-sha256 from an export preview")
    source_location = inspect_storage_location(source_root)
    destination_location = inspect_storage_location(destination_root)
    same_root = source_location.identity == destination_location.identity
    with SQLiteConversationStore(
        source_root,
        sid,
        workspace,
        create=False,
        require_workspace=False,
        writable=False,
        expected_root_identity=source_location.identity,
    ) as source:
        snapshot, modified_ns = source.inspect_snapshot()
        plan = _plan(snapshot, source_location, destination_location)
        sha = digest(canonical_bytes(plan))
        if expected is not None and expected != sha:
            raise ValueError("export selection changed; preview again before applying")
        _check_locations(plan)
        if apply:

            def validate_source() -> None:
                _check_locations(plan)
                current, _ = source.inspect_snapshot()
                if _plan(current, source_location, destination_location) != plan:
                    raise ValueError("SQLite source changed during export")

            if same_root:
                # Both backends use the same lock inode in this directory. The
                # fresh SQLite handle owns it and also exposes the JSON root fd.
                inserted = ConversationStore.publish_snapshot(
                    source, snapshot.state, modified_ns, validate_source=validate_source
                )
            else:
                with ConversationStore(
                    destination_root,
                    sid,
                    workspace,
                    require_workspace=False,
                    expected_root_identity=destination_location.identity,
                ) as destination:
                    inserted = destination.publish_snapshot(
                        snapshot.state, modified_ns, validate_source=validate_source
                    )
            status = "exported" if inserted else "already_present"
        else:
            status = _preview_snapshot(source, plan) if same_root else _preview(plan)
        return ConversationExportReceipt(status=status, export_sha256=sha, plan=plan)
