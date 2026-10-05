"""In-process editor submissions to the shared conversation terminal."""

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol

from mos_eisley.conversation_diff_attachment import DiffAttachment


def submission_command(text: str) -> Literal["review", "steer"] | None:
    """Recognize typed submission commands; callers keep pasted text literal."""
    if text == "/review":
        return "review"
    if text == "/steer" or text.startswith("/steer "):
        return "steer"
    return None


@dataclass(frozen=True)
class ConversationSubmission:
    text: str
    literal: bool
    accepted: asyncio.Future[bool]
    attachments: tuple[DiffAttachment, ...] = ()


type ConversationInput = str | ConversationSubmission | Exception | None


class ConversationInputQueue(Protocol):
    async def get(self) -> ConversationInput: ...
