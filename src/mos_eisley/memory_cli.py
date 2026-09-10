"""User-invoked memory management, never callable by a model tool dispatcher."""

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley.conversation_memory import MEMORY_BYTES, Action, MemoryStore, Scope
from mos_eisley.run.files import read_bounded


def add_memory_options(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--memory-storage",
        type=Path,
        default=Path.home() / ".mos-eisley-memory",
        help="Private user/project memory directory (default: ~/.mos-eisley-memory)",
    )
    command.add_argument(
        "--no-memory",
        action="store_true",
        help="Do not read or load saved memory",
    )


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "action", choices=("show", "set", "append", "clear", "enable", "disable")
    )
    command.add_argument("--scope", choices=("user", "project"), required=True)
    command.add_argument(
        "--memory-storage", type=Path, default=Path.home() / ".mos-eisley-memory"
    )
    command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    content = command.add_mutually_exclusive_group()
    content.add_argument("--text")
    content.add_argument("--text-file", type=Path)
    command.add_argument(
        "--expected-sha256", help="Reject stale edits; use missing for a new document"
    )
    command.add_argument("--json", action="store_true")


def safe_text(value: str) -> str:
    return "".join(
        char if char.isprintable() or char in "\n\t" else json.dumps(char)[1:-1]
        for char in value
    )


def run_command(args: argparse.Namespace) -> int:
    writing_text = args.action in {"set", "append"}
    has_text = args.text is not None or args.text_file is not None
    if writing_text != has_text or (
        args.action == "show" and args.expected_sha256 is not None
    ):
        raise ValueError(
            "set/append require --text or --text-file; other actions do not accept text"
        )
    text = (
        read_bounded(args.text_file, MEMORY_BYTES).decode("utf-8")
        if args.text_file is not None
        else args.text or ""
    )
    store = MemoryStore(args.memory_storage, args.workspace)
    scope = cast(Scope, args.scope)
    snapshot = (
        store.read(scope)
        if args.action == "show"
        else store.change(
            scope,
            cast(Action, args.action),
            text=text,
            expected_sha256=args.expected_sha256,
        )
    )
    event = {
        "type": "memory.inspected" if args.action == "show" else "memory.updated",
        "scope": scope,
        "path": str(store.path(scope)),
        "snapshot": snapshot.model_dump(mode="json") if snapshot else None,
    }
    if args.json:
        print(json.dumps(event, ensure_ascii=True))
    else:
        print(safe_text(f"{scope.capitalize()} memory: {store.path(scope)}"))
        if snapshot is None:
            print("No memory saved in this scope.")
        else:
            doc = snapshot.document
            print(
                f"Revision {doc.revision} • "
                f"{'enabled' if doc.enabled else 'disabled'} • {snapshot.sha256}"
            )
            print(safe_text(doc.text) if doc.text else "(empty)")
        if args.action != "show":
            print(
                "Saved. Changes apply to new sessions. "
                "Existing session snapshots may retain older text."
            )
    return 0
