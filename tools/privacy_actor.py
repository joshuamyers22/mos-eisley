"""Non-root synthetic actor for real-principal qualification of an installed wheel.

No provider, credentials, private history or evaluation stores are used. Output is
an allowlisted receipt; fixture contents and exceptions never reach CI logs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path

from mos_eisley.conversation import (
    ConversationController,
    conversation_config,
    prepare_conversation_request,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_state import LiveChatIdentity
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.run.conversation_sqlite import (
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationStore, list_conversations


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


def stores(backend: str):
    return (
        (SQLiteConversationStore, list_sqlite_conversations)
        if backend == "sqlite"
        else (ConversationStore, list_conversations)
    )


def seed(root: Path, backend: str) -> dict[str, object]:
    workspace = root / "workspace"
    workspace.mkdir(mode=0o700, exist_ok=True)
    memory = MemoryStore(root / "memory", workspace)
    memory.change("user", "set", text="SYNTHETIC-OWNER-USER-MEMORY")
    memory.change("project", "set", text="SYNTHETIC-OWNER-PROJECT-MEMORY")
    selected = memory.load()
    selected.validate_identity(os.getuid(), str(workspace.resolve()))
    cassette = demo_cassette(memory=selected)
    state = ConversationController.fresh(workspace, cassette, selected)
    store_type, _ = stores(backend)
    with store_type(root / backend, state.session_id, workspace) as store:
        store.save(state)
        controller = ConversationController(state, cassette, store.save)
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
        controller = ConversationController(state, cassette, store.save)
        controller.submit(DEMO_PROMPTS[1])
        asyncio.run(controller.step())
        require(controller.state.exchanges_consumed == 2)
        require(store.load() == controller.state)
        forged = controller.state.model_copy(
            update={
                "owner_uid": os.getuid() + 10000,
                "revision": controller.state.revision + 1,
            }
        )
        refuse(lambda: store.save(forged))
        require(store.load() == controller.state)
    fresh = ConversationController.fresh(workspace, demo_cassette())
    require(not fresh.entries and fresh.memory is None)
    memory = MemoryStore(root / "memory", workspace)
    memory.change("user", "disable")
    require(memory.load().user is None)
    memory.change("user", "enable")
    require(memory.load().user is not None)
    return {
        "uid": os.getuid(),
        "backend": backend,
        "cold_resume": True,
        "fresh_history": True,
        "memory_controls": True,
        "forged_owner_save_refused": True,
        "same_process_lock_refused": True,
    }


def foreign(root: Path, backend: str, sid: str, workspace: Path) -> dict[str, object]:
    store_type, listing = stores(backend)
    refuse(lambda: listing(root / backend, workspace))

    def access(kind: str) -> None:
        with store_type(
            root / backend, sid, workspace, create=False, require_workspace=False
        ) as store:
            if kind == "load":
                store.load()
            elif kind == "delete":
                store.delete("0" * 64)
            elif kind == "transcript":
                store.transcript_page(None)
            else:
                store.transcript_artifact("foreign-selection")

    for kind in ("load", "delete"):
        refuse(lambda kind=kind: access(kind))
    if backend == "sqlite":
        for kind in ("transcript", "artifact"):
            refuse(lambda kind=kind: access(kind))
    refuse(lambda: MemoryStore(root / "memory", workspace).load())
    return {
        "uid": os.getuid(),
        "backend": backend,
        "list_refused": True,
        "load_refused": True,
        "delete_refused": True,
        "memory_refused": True,
        "sqlite_reference_refused": backend == "sqlite",
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


async def outbound(root: Path) -> dict[str, object]:
    """Observe SDK-serialized bytes without permitting an external connection.

    This is an application transport boundary check, not a packet capture or a
    claim about native subscription clients. A contaminated control must fail.
    """
    import httpx2
    from openai import AsyncOpenAI

    from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
    from mos_eisley.providers.openai_responses import request_payload

    forbidden = (
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

    count = 0
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
            nonlocal count
            body = message.content
            require(message.url.host == "api.openai.com")
            require(message.url.path == "/v1/responses")
            require(valid(body, enabled))
            require(not valid(body + forbidden[0], enabled))
            require(not valid(b"{}", enabled))
            count += 1
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
            await client.responses.create(**payload)
    require(count == 2)
    return {
        "uid": os.getuid(),
        "sdk_request_cases": count,
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
        choices=("seed", "owner", "foreign", "hold", "contend", "erase", "outbound"),
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("backend", choices=("snapshot", "sqlite"))
    parser.add_argument("--sid", default="")
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    try:
        require(os.getuid() > 0 and os.getuid() == os.geteuid())
        workspace = args.workspace or args.root / "workspace"
        if args.operation == "hold":
            hold(args.root, args.backend, args.sid, workspace)
            return 0
        if args.operation == "outbound":
            receipt = asyncio.run(outbound(args.root))
        elif args.operation in {"seed", "owner"}:
            receipt = (seed if args.operation == "seed" else owner)(
                args.root, args.backend
            )
        else:
            action = {"foreign": foreign, "contend": contention, "erase": erase}[
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
