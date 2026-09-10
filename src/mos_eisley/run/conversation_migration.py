"""Explicit, source-preserving JSON-to-SQLite migration under one session lock."""

import os
import threading
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from mos_eisley.conversation import SessionID
from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.core.models import Contract, Digest, canonical_bytes
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_store import (
    ConversationStore,
    validate_private_storage,
)


class ConversationMigrationReceipt(Contract):
    status: Literal["planned", "imported", "already_present"]
    session_id: SessionID
    snapshot_sha256: Digest
    revision: Annotated[int, Field(ge=0)]
    messages: Annotated[int, Field(ge=0, le=16)]
    source_bytes: Annotated[int, Field(ge=0, le=MAX_SNAPSHOT_BYTES)]
    logical_bytes: Annotated[int, Field(ge=0, le=MAX_SNAPSHOT_BYTES)]
    source_path: str
    destination_path: str
    source_retained: Literal[True] = True


class ConversationMigration(SQLiteConversationStore):
    def __init__(self, root: Path, session_id: str, workspace: Path) -> None:
        # Acquire the existing source lock without creating a database or any lock
        # file. JSON and SQLite share that session lock within this storage root.
        self._db = None
        self.input_limits = None
        self._verified_checkpoint = None
        self._transcript_guard = threading.Lock()
        self._path = root.absolute()
        ConversationStore.__init__(
            self, root, session_id, workspace, create=False, require_workspace=False
        )

    def _preflight_destination(self, *, writable: bool) -> bool:
        exists = False
        try:
            os.stat(DATABASE, dir_fd=self._root, follow_symlinks=False)
            exists = True
        except FileNotFoundError:
            pass
        if exists:
            self._open_database(create=False, writable=writable)
            return True
        for name in (
            "sqlite.lock",
            DATABASE + "-journal",
            DATABASE + "-wal",
            DATABASE + "-shm",
        ):
            try:
                fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._root
                )
            except FileNotFoundError:
                continue
            try:
                validate_private_storage(fd)
                if name != "sqlite.lock":
                    raise ValueError("orphan SQLite sidecar prevents migration")
            finally:
                os.close(fd)
        return False

    def migrate(
        self, *, expected_sha256: str | None = None, apply: bool = False
    ) -> ConversationMigrationReceipt:
        if apply and expected_sha256 is None:
            raise ValueError("--apply requires --expected-sha256 from a preview")
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
        snapshot, modified_ns, source_bytes = self.inspect_json_snapshot()
        state = snapshot.state
        if expected is not None and snapshot.sha256 != expected:
            raise ValueError("JSON source changed since migration was selected")
        logical_bytes = len(canonical_bytes(snapshot))
        if logical_bytes > state.snapshot_byte_limit or modified_ns < 0:
            raise ValueError(
                "JSON source exceeds the destination snapshot budget "
                "or timestamp bounds"
            )
        status: Literal["planned", "imported", "already_present"] = "planned"
        exists = self._preflight_destination(writable=apply)
        if exists:
            try:
                current = self._read()
            except FileNotFoundError:
                pass
            else:
                if current.state != state:
                    raise ValueError(
                        "SQLite destination contains a different session state"
                    )
                status = "already_present"
        if apply and status != "already_present":
            self._open_database(create=True, writable=True)

            def validate_source() -> None:
                if self.inspect_json_snapshot()[0].sha256 != snapshot.sha256:
                    raise ValueError("JSON source changed during migration")

            inserted = self.import_snapshot(
                state, modified_ns, validate_source=validate_source
            )
            status = "imported" if inserted else "already_present"
        return ConversationMigrationReceipt(
            status=status,
            session_id=state.session_id,
            snapshot_sha256=snapshot.sha256,
            revision=state.revision,
            messages=len(state.entries),
            source_bytes=source_bytes,
            logical_bytes=logical_bytes,
            source_path=str(self._path / f"{state.session_id}.json"),
            destination_path=str(self._path / DATABASE),
        )
