"""Bounded user-entered remember phrases, without model inference or extraction."""

from mos_eisley.conversation_memory import Scope

REMEMBER_HELP = (
    "Specify scope and text: remember this for this project: TEXT "
    "or remember this everywhere: TEXT. No memory was saved."
)


def remember_command(text: str) -> str | None:
    """Return a scoped append, reject incomplete intent, or leave chat literal."""
    prefix, separator, payload = text.partition(":")
    scopes: dict[str, Scope] = {
        "remember this for this project": "project",
        "remember this everywhere": "user",
    }
    intent = prefix.strip().casefold()
    if intent not in scopes and intent != "remember this":
        return None
    if (
        intent not in scopes
        or not separator
        or not payload.strip()
        or len(text) > 8000
        or any(char in text for char in "\r\n\x00")
    ):
        raise ValueError(REMEMBER_HELP)
    return f"/memory append {scopes[intent]} {payload.lstrip()}"
