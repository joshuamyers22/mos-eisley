"""One-page saved history with serialized background reads and stale-result guards."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from mos_eisley.run.conversation_artifacts import ArtifactContent
from mos_eisley.run.conversation_transcript import TranscriptArtifact, TranscriptPage


@dataclass(frozen=True)
class ArtifactRequest:
    selection: str
    position: int
    reference: TranscriptArtifact
    epoch: int


class TranscriptHistory:
    def __init__(
        self,
        loader: Callable[[str | None], TranscriptPage],
        identity: Callable[[], tuple[str, int, int]],
        changed: Callable[[], None],
        artifact_loader: Callable[[str], ArtifactContent] | None = None,
    ) -> None:
        self.loader = loader
        self.identity = identity
        self.changed = changed
        self.artifact_loader = artifact_loader
        self.selected_artifact = 0
        self.expanded: ArtifactContent | None = None
        self.artifact_error: str | None = None
        self.visible = False
        self.page: TranscriptPage | None = None
        self.error: str | None = None
        self.cursors: tuple[str | None, ...] = (None,)
        self.index = 0
        self.revision = -1
        self.epoch = 0
        self.pending: (
            tuple[int, tuple[str | None, ...], int] | ArtifactRequest | None
        ) = None
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
        self.clear_artifact()

    def clear_artifact(self) -> None:
        self.expanded = None
        self.artifact_error = None
        self.selected_artifact = 0

    def references(self) -> list[tuple[int, TranscriptArtifact]]:
        return (
            []
            if self.page is None
            else [
                (entry.position, ref)
                for entry in self.page.entries
                for ref in entry.artifacts
            ]
        )

    def select_next_artifact(self) -> None:
        refs = self.references()
        if not refs:
            return
        self.epoch += 1
        self.pending = None
        self.selected_artifact = (self.selected_artifact + 1) % len(refs)
        self.expanded = None
        self.artifact_error = None
        self.changed()

    def toggle_artifact(self) -> None:
        refs = self.references()
        if not self.visible or not refs or self.artifact_loader is None:
            return
        self.epoch += 1
        self.pending = None
        self.artifact_error = None
        if self.expanded is not None:
            self.expanded = None
        else:
            position, ref = refs[self.selected_artifact]
            if ref.selection is None:
                self.artifact_error = "Selection unavailable; F6 reloads history."
            else:
                self.pending = ArtifactRequest(ref.selection, position, ref, self.epoch)
                if self.task is None:
                    self.task = asyncio.create_task(self.read())
        self.changed()

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
        if not self.visible or self.page is None:
            return
        if direction < 0 and self.index > 0:
            self.request(self.index - 1, self.cursors[: self.index])
        elif direction > 0 and self.page.next_cursor is not None:
            self.request(self.index + 1, (*self.cursors, self.page.next_cursor))

    def request(self, index: int, cursors: tuple[str | None, ...]) -> None:
        self.epoch += 1
        self.page = None
        self.error = None
        self.clear_artifact()
        self.pending = index, cursors, self.epoch
        if self.task is None:
            self.task = asyncio.create_task(self.read())
        self.changed()

    async def read(self) -> None:
        try:
            while self.pending is not None:
                request = self.pending
                self.pending = None
                epoch = (
                    request.epoch
                    if isinstance(request, ArtifactRequest)
                    else request[2]
                )
                identity = self.identity()
                try:
                    if isinstance(request, ArtifactRequest):
                        assert self.artifact_loader is not None
                        expanded = await asyncio.to_thread(
                            self.artifact_loader, request.selection
                        )
                        if not self.visible or epoch != self.epoch:
                            continue
                        if (
                            self.identity() != identity
                            or self.page is None
                            or (expanded.session_id, expanded.revision) != identity[:2]
                            or expanded.snapshot_sha256 != self.page.snapshot_sha256
                            or expanded.position != request.position
                            or expanded.field != request.reference.field
                            or expanded.sha256 != request.reference.sha256
                            or expanded.bytes != request.reference.bytes
                        ):
                            raise ValueError(
                                "Artifact selection changed. F6 reloads history."
                            )
                        self.expanded = expanded
                        continue
                    index, cursors, epoch = request
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
                        if isinstance(request, ArtifactRequest):
                            self.expanded = None
                            self.artifact_error = str(error)[:1000]
                            continue
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
