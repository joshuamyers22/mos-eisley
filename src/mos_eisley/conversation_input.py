"""In-process editor submissions to the shared conversation terminal."""

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ConversationSubmission:
    text: str
    literal: bool
    accepted: asyncio.Future[bool]


type ConversationInput = str | ConversationSubmission | Exception | None


class ConversationInputQueue(Protocol):
    async def get(self) -> ConversationInput: ...
