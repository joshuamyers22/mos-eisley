"""In-process editor submissions to the shared conversation terminal."""

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol

from mos_eisley.conversation_diff import DiffAttachment


def submission_command(
    text: str,
) -> (
    Literal[
        "review",
        "steer",
        "diff_followup",
        "plan",
        "implement",
        "goal_run",
        "goal_control",
        "branch_control",
        "agent_inspection",
        "loop_control",
    ]
    | None
):
    """Recognize typed submission commands; callers keep pasted text literal."""
    if text.split(maxsplit=1)[:1] == ["/loop"]:
        return "loop_control"
    if text == "/side cancel":
        return None
    if text.split(maxsplit=1)[:1] in (["/agent"], ["/subagents"]):
        return "agent_inspection"
    if text.split(maxsplit=1)[:1] in (["/fork"], ["/side"]):
        return "branch_control"
    if text.startswith("/goal run "):
        return "goal_run"
    if text == "/goal" or text.startswith("/goal "):
        return "goal_control"
    if text.startswith("/implement "):
        return "implement"
    if text.startswith("/plan ") and text not in {
        "/plan on",
        "/plan off",
        "/plan status",
    }:
        return "plan"
    if text == "/review" or text.startswith("/review "):
        return "review"
    if text == "/steer" or text.startswith("/steer "):
        return "steer"
    if text.startswith(("/diff fix ", "/diff feedback ")):
        return "diff_followup"
    return None


@dataclass(frozen=True)
class ConversationSubmission:
    text: str
    literal: bool
    accepted: asyncio.Future[bool]
    diff_attachments: tuple[DiffAttachment, ...] = ()


type ConversationInput = str | ConversationSubmission | Exception | None


class ConversationInputQueue(Protocol):
    async def get(self) -> ConversationInput: ...
