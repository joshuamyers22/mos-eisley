"""One-page saved history with serialized background reads and stale-result guards."""

import asyncio
from collections.abc import Callable

from mos_eisley.run.conversation_transcript import TranscriptPage


class TranscriptHistory:
    def __init__(
        self,
        loader: Callable[[str | None], TranscriptPage],
        identity: Callable[[], tuple[str, int, int]],
        changed: Callable[[], None],
    ) -> None:
        self.loader = loader
        self.identity = identity
        self.changed = changed
        self.visible = False
        self.page: TranscriptPage | None = None
        self.error: str | None = None
        self.cursors: tuple[str | None, ...] = (None,)
        self.index = 0
        self.revision = -1
        self.epoch = 0
        self.pending: tuple[int, tuple[str | None, ...], int] | None = None
        self.task: asyncio.Task[None] | None = None

    @property
    def loading(self) -> bool:
        return self.task is not None

    def close(self) -> None:
        self.visible = False
        self.invalidate()

    def invalidate(self) -> None:
        self.epoch += 1
        self.pending = None
        self.page = None
        self.cursors = (None,)
        self.index = 0
        self.error = None

    def reload(self) -> None:
        self.invalidate()
        self.visible = True
        self.revision = self.identity()[1]
        self.request(0, (None,))

    def check_revision(self) -> None:
        if self.visible and self.revision != self.identity()[1]:
            self.invalidate()
            self.revision = self.identity()[1]
            self.error = (
                "Session changed. F6 reloads saved history; F5 returns to live."
            )

    def move(self, direction: int) -> None:
        if not self.visible or self.loading or self.page is None:
            return
        if direction < 0 and self.index > 0:
            self.request(self.index - 1, self.cursors[: self.index])
        elif direction > 0 and self.page.next_cursor is not None:
            self.request(self.index + 1, (*self.cursors, self.page.next_cursor))

    def request(self, index: int, cursors: tuple[str | None, ...]) -> None:
        self.epoch += 1
        self.page = None
        self.error = None
        self.pending = index, cursors, self.epoch
        if self.task is None:
            self.task = asyncio.create_task(self.read())
        self.changed()

    async def read(self) -> None:
        try:
            while self.pending is not None:
                index, cursors, epoch = self.pending
                self.pending = None
                identity = self.identity()
                try:
                    page = await asyncio.to_thread(self.loader, cursors[index])
                    if not self.visible or epoch != self.epoch:
                        continue
                    if (
                        self.identity() != identity
                        or (page.session_id, page.revision, page.total_messages)
                        != identity
                    ):
                        raise ValueError("Session changed. F6 reloads saved history.")
                    self.page = page
                    self.index = index
                    self.cursors = cursors
                except (OSError, ValueError) as error:
                    if self.visible and epoch == self.epoch:
                        self.page = None
                        self.cursors = (None,)
                        self.index = 0
                        self.error = str(error)[:1000] + " • F6 reload • F5 live"
        finally:
            self.task = None
            self.changed()

    async def shutdown(self) -> None:
        self.close()
        if self.task is not None:
            await self.task
