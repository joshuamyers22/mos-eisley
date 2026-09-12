"""Explicit terminal memory commands; chat and model output never enter this path."""

from dataclasses import dataclass
from typing import Literal, cast

from mos_eisley.conversation_memory import Action, MemoryStore, Scope

USAGE = (
    "Use /memory show|append|set|clear|enable|disable user|project [TEXT]. "
    "Only append and set accept text. /memory shows the active session selection. "
    "Use /memory forget SCOPE EXACT_TEXT for reviewed removal. "
    'Use /memory replace SCOPE {"old":"TEXT","new":"TEXT"} for reviewed replacement. '
    "Use /memory review-proposal SCOPE MESSAGE_NUMBER to review an assistant proposal."
)


@dataclass(frozen=True)
class MemoryCommand:
    action: Action | Literal["show"]
    scope: Scope
    text: str = ""


def parse_memory_command(line: str) -> MemoryCommand:
    # Match the terminal's single-line command boundary. Do not shell-parse text:
    # quotes, slashes and substitution syntax are ordinary saved characters.
    if len(line) > 8000 or any(char in line for char in "\r\n\x00"):
        raise ValueError("Memory commands require one line within 8,000 characters.")
    parts = line.split(maxsplit=3)
    if (
        len(parts) < 3
        or parts[0] != "/memory"
        or parts[1] not in {"show", "append", "set", "clear", "enable", "disable"}
        or parts[2] not in {"user", "project"}
    ):
        raise ValueError(USAGE)
    action, scope = parts[1], parts[2]
    text = parts[3] if len(parts) == 4 else ""
    if (action in {"append", "set"}) != bool(text.strip()):
        raise ValueError(USAGE)
    return MemoryCommand(
        cast(Action | Literal["show"], action),
        "user" if scope == "user" else "project",
        text,
    )


def run_memory_command(store: MemoryStore, line: str) -> dict[str, object]:
    command = parse_memory_command(line)
    action, scope = command.action, command.scope
    try:
        if action == "show":
            snapshot = store.read(scope)
        else:
            # Narrow the validated parser value without accepting unknown actions
            # through MemoryStore.change's enable/disable fallback.
            assert action in {"append", "set", "clear", "enable", "disable"}
            snapshot = store.change(scope, action, text=command.text)
    except (OSError, ValueError):
        raise ValueError(
            "Memory storage operation could not be completed. Inspect the saved "
            "scope before retrying; a failed write may already have been published. "
            "The active session selection is unchanged."
        ) from None
    details = (
        f"revision {snapshot.document.revision}, "
        f"{'enabled' if snapshot.document.enabled else 'disabled'}, "
        f"SHA-256 {snapshot.sha256}"
        if snapshot is not None
        else "no saved document"
    )
    text = f"{scope.capitalize()} memory at {store.path(scope)}: {details}."
    if action == "show":
        if snapshot is not None:
            text += "\n" + snapshot.document.text
    else:
        text += (
            f" Saved {action}. Session memory is unchanged and queued work is paused. "
            "Use /memory refresh to load current memory, then /continue."
        )
    if action in {"append", "set"}:
        text += "\nSaved text:\n" + command.text
    return {
        "type": "conversation.memory.inspected"
        if action == "show"
        else "conversation.memory.saved",
        "action": action,
        "scope": scope,
        "path": str(store.path(scope)),
        "document": snapshot.model_dump(mode="json") if snapshot is not None else None,
        "text": text,
    }
