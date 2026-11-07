"""Non-root synthetic actor for real-principal qualification of an installed wheel.

No provider, credentials, private history or evaluation stores are used. Output is
an allowlisted receipt; fixture contents and exceptions never reach CI logs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Callable, Generator
from pathlib import Path

from mos_eisley.conversation import (
    ConversationController,
    conversation_config,
    prepare_conversation_request,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_state import ConversationState, LiveChatIdentity
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.run.conversation_artifacts import read_sqlite_artifact
from mos_eisley.run.conversation_export import export_conversation
from mos_eisley.run.conversation_migration import ConversationMigration
from mos_eisley.run.conversation_read_cache import ArtifactReadCache
from mos_eisley.run.conversation_sqlite import (
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationStore, list_conversations
from mos_eisley.run.conversation_transcript import read_sqlite_transcript
from mos_eisley.run.conversation_transfer import transfer_conversation


def require(condition: bool) -> None:
    if not condition:
        raise AssertionError("qualification assertion failed")


def refuse(operation: Callable[[], object]) -> None:
    # The callable deliberately stays local; never print exception text/paths.
    try:
        operation()
    except (OSError, ValueError):
        return
    raise AssertionError("foreign operation was admitted")


def stores(
    backend: str,
) -> tuple[type[ConversationStore], Callable[[Path, Path], object]]:
    return (
        (SQLiteConversationStore, list_sqlite_conversations)
        if backend == "sqlite"
        else (ConversationStore, list_conversations)
    )


def seed(root: Path, backend: str) -> dict[str, object]:
    workspace = root / "workspace"
    workspace.mkdir(mode=0o700, exist_ok=True)
    memory = MemoryStore(root / "memory", workspace)
    memory.change("user", "set", text=f"SYNTHETIC-OWNER-USER-MEMORY-{os.getuid()}")
    memory.change(
        "project", "set", text=f"SYNTHETIC-OWNER-PROJECT-MEMORY-{os.getuid()}"
    )
    selected = memory.load()
    assert selected is not None
    selected.validate_identity(os.getuid(), str(workspace.resolve()))
    cassette = demo_cassette(memory=selected)
    state = ConversationController.fresh(workspace, cassette, selected)
    store_type, _ = stores(backend)
    with store_type(root / backend, state.session_id, workspace) as store:
        store.save(state)
        controller = ConversationController[ConversationState](
            state, cassette, store.save
        )
        controller.submit(DEMO_PROMPTS[0])
        asyncio.run(controller.step())
        require(controller.state.exchanges_consumed == 1)
    (root / (backend + "-session.json")).write_text(
        json.dumps({"sid": state.session_id}), encoding="utf-8"
    )
    return {"seeded": True, "uid": os.getuid(), "backend": backend}


def owner(root: Path, backend: str) -> dict[str, object]:
    workspace = root / "workspace"
    sid = json.loads((root / (backend + "-session.json")).read_text())["sid"]
    store_type, listing = stores(backend)
    require(bool(listing(root / backend, workspace)))
    with store_type(root / backend, sid, workspace, create=False) as store:
        state = store.load()
        require(state.owner_uid == os.getuid())
        # A second process tests contention separately; this also exercises the
        # exact nonblocking lock API, rather than a mocked flock.
        refuse(lambda: store_type(root / backend, sid, workspace, create=False))
        cassette = demo_cassette(memory=state.memory)
        controller = ConversationController[ConversationState](
            state, cassette, store.save
        )
        controller.submit(DEMO_PROMPTS[1])
        asyncio.run(controller.step())
        require(controller.state.exchanges_consumed == 2)
        require(store.load() == controller.state)
        runtime = ConversationMemoryRuntime(
            controller,
            MemoryStore(root / "memory", workspace),
            lambda memory: demo_cassette(memory=memory),
        )
        runtime.check()
        runtime.store.change("project", "append", text="SYNTHETIC-REFRESHED-MEMORY")
        saved = store.load()
        refuse(runtime.check)
        require(store.load() == saved)
        runtime.refresh(False)
        require(controller.state.memory == runtime.store.load())
        require(controller.state.exchanges_consumed == 2)
        runtime.refresh(True)
        require(controller.state.memory is None and controller.state.memory_disabled)
        forged = controller.state.model_copy(
            update={
                "owner_uid": os.getuid() + 10000,
                "revision": controller.state.revision + 1,
            }
        )
        refuse(lambda: store.save(forged))
        require(store.load() == controller.state)
        if isinstance(store, SQLiteConversationStore):
            store.prepare_transcript(digest(canonical_bytes(controller.state)))
            page = read_sqlite_transcript(root / backend, sid, workspace, limit=1)
            selection = next(
                artifact.selection
                for artifact in page.entries[0].artifacts
                if artifact.field == "memory_context"
            )
            assert selection is not None and page.next_cursor is not None
            require(
                read_sqlite_artifact(
                    root / backend, workspace, selection, expected_session_id=sid
                ).field
                == "memory_context"
            )
            require(
                read_sqlite_transcript(
                    root / backend, sid, workspace, cursor=page.next_cursor
                )
                .entries[0]
                .position
                == 1
            )
            (root / "references.json").write_text(
                json.dumps({"selection": selection, "cursor": page.next_cursor})
            )
    fresh = ConversationController.fresh(workspace, demo_cassette())
    require(not fresh.entries and fresh.memory is None)
    memory = MemoryStore(root / "memory", workspace)
    memory.change("user", "disable")
    disabled = memory.load()
    assert disabled is not None
    require(disabled.user is None)
    memory.change("user", "enable")
    enabled = memory.load()
    assert enabled is not None
    require(enabled.user is not None)
    return {
        "uid": os.getuid(),
        "backend": backend,
        "cold_resume": True,
        "fresh_history": True,
        "memory_controls": True,
        "forged_owner_save_refused": True,
        "same_process_lock_refused": True,
        "memory_change_pauses_and_refreshes": True,
        "sqlite_reference_positive_control": backend == "sqlite",
    }


def foreign(
    root: Path,
    backend: str,
    sid: str,
    workspace: Path,
    *,
    application_only: bool = False,
    references: Path | None = None,
) -> dict[str, object]:
    store_type, listing = stores(backend)
    path = (
        root / backend / ("sessions.sqlite3" if backend == "sqlite" else sid + ".json")
    )
    if application_only:
        require(bool(path.read_bytes()))
    else:
        refuse(lambda: os.listdir(root / backend))
        refuse(lambda: path.read_bytes())
        refuse(lambda: os.close(os.open(path, os.O_WRONLY)))
    refuse(lambda: listing(root / backend, workspace))

    def access(kind: str) -> None:
        with store_type(
            root / backend, sid, workspace, create=False, require_workspace=False
        ) as store:
            if kind == "load":
                store.load()
            elif kind == "delete":
                store.delete("0" * 64)
            elif isinstance(store, SQLiteConversationStore):
                if kind == "transcript":
                    store.transcript_page(None)
                else:
                    store.transcript_artifact("foreign-selection")
            else:
                raise AssertionError("wrong fixture backend")

    for kind in ("load", "delete"):
        refuse(lambda kind=kind: access(kind))
    if backend == "sqlite":
        for kind in ("transcript", "artifact"):
            refuse(lambda kind=kind: access(kind))
        if references is not None:
            refs = json.loads(references.read_text())
            refuse(
                lambda: read_sqlite_artifact(
                    root / backend,
                    workspace,
                    refs["selection"],
                    expected_session_id=sid,
                )
            )
            refuse(
                lambda: read_sqlite_transcript(
                    root / backend, sid, workspace, cursor=refs["cursor"]
                )
            )
        destination = Path.home() / "refused-export"
        destination.mkdir(mode=0o700, exist_ok=True)
        for apply in (False, True):
            refuse(
                lambda apply=apply: export_conversation(
                    root / backend,
                    destination,
                    sid,
                    workspace,
                    apply=apply,
                    expected_sha256="0" * 64 if apply else None,
                )
            )
        require(not tuple(destination.iterdir()))
    else:
        destination = Path.home() / "refused-transfer"
        destination.mkdir(mode=0o700, exist_ok=True)
        for apply in (False, True):
            refuse(
                lambda apply=apply: transfer_conversation(
                    root / backend,
                    destination,
                    sid,
                    workspace,
                    apply=apply,
                    expected_sha256="0" * 64 if apply else None,
                )
            )
        refuse(lambda: ConversationMigration(root / backend, sid, workspace).migrate())
        require(not tuple(destination.iterdir()))
    refuse(lambda: MemoryStore(root / "memory", workspace).load())
    return {
        "uid": os.getuid(),
        "backend": backend,
        "list_refused": True,
        "load_refused": True,
        "delete_refused": True,
        "memory_refused": True,
        "sqlite_reference_refused": backend == "sqlite",
        "kernel_denial": not application_only,
        "readable_reowned_copy_refused": application_only,
        "export_transfer_migration_refused": True,
    }


def lifecycle(root: Path, backend: str, sid: str, workspace: Path) -> dict[str, object]:
    store_type, _ = stores(backend)
    with store_type(root / backend, sid, workspace, create=False) as store:
        state = store.load()
    destination = root / ("lifecycle-" + backend)
    destination.mkdir(mode=0o700)
    if backend == "sqlite":
        preview = export_conversation(root / backend, destination, sid, workspace)
        refuse(
            lambda: export_conversation(
                root / backend,
                destination,
                sid,
                workspace,
                apply=True,
                expected_sha256="0" * 64,
            )
        )
        require(not tuple(destination.iterdir()))
        export_conversation(
            root / backend,
            destination,
            sid,
            workspace,
            apply=True,
            expected_sha256=preview.export_sha256,
        )
        selected_type = ConversationStore
    else:
        preview = transfer_conversation(root / backend, destination, sid, workspace)
        refuse(
            lambda: transfer_conversation(
                root / backend,
                destination,
                sid,
                workspace,
                apply=True,
                expected_sha256="0" * 64,
            )
        )
        require(not tuple(destination.iterdir()))
        transfer_conversation(
            root / backend,
            destination,
            sid,
            workspace,
            apply=True,
            expected_sha256=preview.transfer_sha256,
        )
        selected_type = SQLiteConversationStore
        with ConversationMigration(root / backend, sid, workspace) as migration:
            planned = migration.migrate()
            refuse(lambda: migration.migrate(apply=True, expected_sha256="0" * 64))
            migration.migrate(apply=True, expected_sha256=planned.snapshot_sha256)
        with SQLiteConversationStore(
            root / backend, sid, workspace, create=False
        ) as migrated:
            require(migrated.load() == state)
    with selected_type(destination, sid, workspace, create=False) as selected:
        require(selected.load() == state)
    payload = b"SYNTHETIC-PRIVATE-CACHE"
    path = root / "private-cache"
    path.write_bytes(payload)

    def source(_sha: str) -> Generator[bytes]:
        yield path.read_bytes()

    checksum = digest(payload)
    with ArtifactReadCache(
        source, {checksum: len(payload)}, frozenset({checksum})
    ) as cache:
        require(b"".join(cache.read(checksum)) == payload)
        require(cache.cached_bytes == len(payload))
        require(b"".join(cache.read(checksum)) == payload)
    require(cache.cached_bytes == 0)
    refuse(lambda: list(cache.read(checksum)))
    return {
        "uid": os.getuid(),
        "backend": backend,
        "owner_lifecycle": True,
        "stale_selection_refused": True,
        "cache_cleared_after_operation": True,
    }


def contention(
    root: Path, backend: str, sid: str, workspace: Path
) -> dict[str, object]:
    store_type, _ = stores(backend)
    refuse(lambda: store_type(root / backend, sid, workspace, create=False))
    return {"uid": os.getuid(), "backend": backend, "competing_process_refused": True}


def hold(root: Path, backend: str, sid: str, workspace: Path) -> None:
    store_type, _ = stores(backend)
    with store_type(root / backend, sid, workspace, create=False):
        print(json.dumps({"locked": True, "uid": os.getuid()}), flush=True)
        require(input() == "release")


def erase(root: Path, backend: str, sid: str, workspace: Path) -> dict[str, object]:
    store_type, _ = stores(backend)
    with store_type(root / backend, sid, workspace, create=False) as store:
        state = store.load()
        store.delete(digest(canonical_bytes(state)))
    refuse(lambda: store_type(root / backend, sid, workspace, create=False).load())
    return {"uid": os.getuid(), "backend": backend, "owner_delete": True}


async def outbound(root: Path, other_uid: int) -> dict[str, object]:
    """Observe SDK-serialized bytes without permitting an external connection.

    This is an application transport boundary check, not a packet capture or a
    claim about native subscription clients. A contaminated control must fail.
    """
    import httpx2
    from openai import AsyncOpenAI

    from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
    from mos_eisley.providers.openai_responses import (
        SDKOpenAITransport,
        request_payload,
    )

    other_project = root / "other-workspace"
    other_project.mkdir(mode=0o700, exist_ok=True)
    MemoryStore(root / "memory", other_project).change(
        "project", "set", text="SYNTHETIC-OTHER-PROJECT"
    )
    forbidden = (
        f"SYNTHETIC-OWNER-USER-MEMORY-{other_uid}".encode(),
        f"SYNTHETIC-OWNER-PROJECT-MEMORY-{other_uid}".encode(),
        b"SYNTHETIC-OTHER-USER",
        b"SYNTHETIC-OTHER-SESSION",
        b"SYNTHETIC-OTHER-PROJECT",
        b"SYNTHETIC-CREDENTIAL",
    )
    for number, canary in enumerate(forbidden):
        (root / f"ambient-{number}").write_bytes(canary)

    def valid(body: bytes, enabled: bool) -> bool:
        return (
            all(canary not in body for canary in forbidden)
            and b"SYNTHETIC-CURRENT-TURN" in body
            and (b"SYNTHETIC-OWNER-USER-MEMORY" in body) == enabled
            and (b"SYNTHETIC-OWNER-PROJECT-MEMORY" in body) == enabled
        )

    captures: list[bool] = []
    for enabled in (False, True):
        memory = (
            MemoryStore(root / "memory", root / "workspace").load() if enabled else None
        )
        identity = LiveChatIdentity(
            model="gpt-5.6-luna",
            effort="medium",
            max_output_tokens=1024,
            spend_policy_sha256="0" * 64,
            spend_ledger_id="1" * 64,
            artifacts_root=str(root),
        )
        config = conversation_config(
            (Turn(role="user", blocks=(TextBlock(text="SYNTHETIC-CURRENT-TURN"),)),),
            memory,
            live_chat=identity,
        )
        request, _ = prepare_conversation_request(config)
        payload = request_payload(request)

        async def capture(
            message: httpx2.Request, enabled: bool = enabled
        ) -> httpx2.Response:
            body = message.content
            require(message.url.host == "api.openai.com")
            require(message.url.path == "/v1/responses")
            require(valid(body, enabled))
            require(not valid(body + forbidden[0], enabled))
            require(not valid(b"{}", enabled))
            captures.append(True)
            return httpx2.Response(
                200,
                json={
                    "id": "resp_synthetic",
                    "object": "response",
                    "created_at": 0,
                    "status": "completed",
                    "model": "gpt-5.6-luna",
                    "output": [],
                    "tools": [],
                },
                request=message,
            )

        async with (
            BoundedOpenAIHttpClient(
                transport=httpx2.MockTransport(capture), trust_env=False
            ) as http,
            AsyncOpenAI(
                api_key="synthetic-no-authority", max_retries=0, http_client=http
            ) as client,
        ):
            await SDKOpenAITransport(client).create_response(payload)
    require(len(captures) == 2)
    return {
        "uid": os.getuid(),
        "sdk_request_cases": len(captures),
        "memory_on_off": True,
        "ambient_canaries_absent": True,
        "contaminated_and_empty_controls_rejected": True,
        "external_network_connections": 0,
        "scope": "OpenAI SDK serialized request via in-process mock transport",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=(
            "seed",
            "owner",
            "foreign",
            "hold",
            "contend",
            "erase",
            "outbound",
            "lifecycle",
        ),
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("backend", choices=("snapshot", "sqlite"))
    parser.add_argument("--sid", default="")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--application-only", action="store_true")
    parser.add_argument("--references", type=Path)
    parser.add_argument("--other-uid", type=int, default=os.getuid() + 1)
    args = parser.parse_args()
    try:
        require(os.getuid() > 0 and os.getuid() == os.geteuid())
        workspace = args.workspace or args.root / "workspace"
        if args.operation == "hold":
            hold(args.root, args.backend, args.sid, workspace)
            return 0
        if args.operation == "outbound":
            receipt = asyncio.run(outbound(args.root, args.other_uid))
        elif args.operation in {"seed", "owner"}:
            receipt = (seed if args.operation == "seed" else owner)(
                args.root, args.backend
            )
        elif args.operation == "foreign":
            receipt = foreign(
                args.root,
                args.backend,
                args.sid,
                workspace,
                application_only=args.application_only,
                references=args.references,
            )
        else:
            action = {"lifecycle": lifecycle, "contend": contention, "erase": erase}[
                args.operation
            ]
            receipt = action(args.root, args.backend, args.sid, workspace)
        print(
            json.dumps({"schema_version": 1, "passed": True, **receipt}, sort_keys=True)
        )
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "passed": False,
                    "failure_kind": type(error).__name__,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
