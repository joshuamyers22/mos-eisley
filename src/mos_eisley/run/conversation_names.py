"""Owner/workspace-scoped name lookup and explicit metadata editing."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from mos_eisley.conversation_name import SessionName, SessionSelectionError, name_key
from mos_eisley.conversation_state import ConversationState
from mos_eisley.core.models import Digest, canonical_bytes, digest
from mos_eisley.run.conversation_sqlite import (
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import (
    ConversationStore,
    ConversationSummary,
    list_conversations,
)
from mos_eisley.run.conversation_transfer import (
    TransferLocation,
    inspect_storage_location,
)

MAX_RESUME_CATALOG = 1000


@dataclass(frozen=True)
class ResumeCatalog:
    location: TransferLocation
    workspace: str
    sessions: tuple[ConversationSummary, ...]


def resume_catalog(
    root: Path, workspace: Path, *, sqlite: bool, max_bytes: int | None = None
) -> ResumeCatalog:
    location = inspect_storage_location(root)
    selected_workspace = str(workspace.resolve())
    if sqlite:
        sessions: list[ConversationSummary] = []
        cursor = None
        while True:
            page = list_sqlite_conversations(root, workspace, limit=100, cursor=cursor)
            sessions.extend(page.sessions)
            if len(sessions) > MAX_RESUME_CATALOG or (
                len(sessions) == MAX_RESUME_CATALOG and page.next_cursor is not None
            ):
                raise SessionSelectionError(
                    "Resume catalog exceeds 1,000 sessions; use an explicit session ID."
                )
            cursor = page.next_cursor
            if cursor is None:
                break
        summaries = tuple(sessions)
    else:
        summaries = list_conversations(root, workspace, max_bytes=max_bytes)
    if inspect_storage_location(root) != location:
        raise SessionSelectionError("Resume storage changed; select again.")
    return ResumeCatalog(location, selected_workspace, summaries)


def named_sessions(
    catalog: ResumeCatalog, name: str
) -> tuple[ConversationSummary, ...]:
    selected = name_key(TypeAdapter[str](SessionName).validate_python(name))
    return tuple(
        s
        for s in catalog.sessions
        if s.session_name is not None and name_key(s.session_name) == selected
    )


def rename_session(
    root: Path,
    workspace: Path,
    sid: str,
    *,
    sqlite: bool,
    expected_sha256: str,
    name: str | None,
) -> dict[str, object]:
    expected = TypeAdapter[str](Digest).validate_python(expected_sha256)
    if name is not None:
        name = TypeAdapter[str](SessionName).validate_python(name)
    store_type = SQLiteConversationStore if sqlite else ConversationStore
    with store_type(
        root, sid, workspace, create=False, require_workspace=False
    ) as store:
        state = store.load()
        if digest(canonical_bytes(state)) != expected:
            raise SessionSelectionError(
                "Selected conversation changed; list again before renaming."
            )
        if any(entry.status == "running" for entry in state.entries):
            raise SessionSelectionError(
                "Interrupted running work must be resumed and stopped before renaming."
            )
        changed = name != state.session_name
        if changed:
            state = ConversationState.model_validate_json(
                state.model_copy(
                    update={
                        "session_name": name,
                        "revision": state.revision + 1,
                    }
                ).model_dump_json()
            )
            store.save(state)
        return {
            "type": "conversation.renamed",
            "session_id": sid,
            "session_name": name,
            "changed": changed,
            "snapshot_sha256": digest(canonical_bytes(state)),
        }
