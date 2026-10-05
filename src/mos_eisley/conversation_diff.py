"""Bounded, read-only diff views and immutable untrusted prompt attachments."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.git_review import (
    GitReadBroker,
    GitReviewFile,
    GitReviewScope,
    GitReviewSelection,
    GitReviewTarget,
)

PAGE_FILES = 8
MAX_RENDER_LINES = 400
MAX_ATTACHMENT_BYTES = 6000
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class DiffLine(Contract):
    text: str
    basis: Literal["staged", "unstaged", "untracked", "metadata"]
    old: int | None = None
    new: int | None = None


def patch_lines(file: GitReviewFile) -> tuple[DiffLine, ...]:
    basis: Literal["staged", "unstaged", "untracked", "metadata"] = (
        "untracked" if file.untracked else "unstaged" if file.unstaged else "staged"
    )
    old = new = None
    lines: list[DiffLine] = []
    pieces = file.patch.split("\n")
    records = [piece + "\n" for piece in pieces[:-1]] + (
        [pieces[-1]] if pieces[-1] else []
    )
    for text in records:
        if text.strip() in {"[staged]", "[unstaged]"}:
            basis = "staged" if text.strip() == "[staged]" else "unstaged"
            old = new = None
        match = HUNK.match(text)
        if match:
            old, new = int(match[1]), int(match[2])
            lines.append(DiffLine(text=text, basis=basis))
        elif old is not None and new is not None and text[:1] in {" ", "+", "-"}:
            lines.append(
                DiffLine(
                    text=text,
                    basis=basis,
                    old=old if text[0] != "+" else None,
                    new=new if text[0] != "-" else None,
                )
            )
            old += text[0] != "+"
            new += text[0] != "-"
        else:
            lines.append(DiffLine(text=text, basis=basis))
    return tuple(lines)


def file_identity(file: GitReviewFile) -> str:
    return digest(
        json.dumps(
            file.model_dump(mode="json", exclude={"patch"}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


class DiffSnapshot(Contract):
    scope: GitReviewScope
    offset: Annotated[int, Field(ge=0)]
    total_files: Annotated[int, Field(ge=0)]
    catalogue_sha256: Digest

    @property
    def basis_label(self) -> str:
        scope = self.scope
        if scope.selection.kind == "files":
            return "source-only; no comparison diff"
        if scope.selection.kind in {"base", "commit"}:
            return f"{scope.selection.kind}: {scope.base} → {scope.target}"
        return f"HEAD {scope.head or '(unborn)'} → index → working tree"

    @property
    def next_offset(self) -> int | None:
        value = self.offset + len(self.scope.files)
        return value if value < self.total_files else None

    def event(self) -> dict[str, object]:
        return {
            "type": "conversation.diff",
            "snapshot": self.model_dump(mode="json"),
            "text": self.describe(),
        }

    def describe(self) -> str:
        lines = [
            f"Diff: {self.scope.workspace}",
            f"Basis: {self.basis_label}",
            f"Snapshot: {self.scope.scope_id}",
            f"Files {self.offset + 1 if self.total_files else 0}–"
            f"{self.offset + len(self.scope.files)} of {self.total_files}; "
            "renames are shown as deletion/addition paths.",
        ]
        for file in self.scope.files:
            rows = patch_lines(file)
            added = sum(r.new is not None and r.old is None for r in rows)
            removed = sum(r.old is not None and r.new is None for r in rows)
            states = ", ".join(
                s
                for s, yes in (
                    ("staged", file.staged),
                    ("unstaged", file.unstaged),
                    ("untracked", file.untracked),
                )
                if yes
            )
            lines.append(f"{json.dumps(file.path)} [{states}] +{added} -{removed}")
            if file.omission:
                lines.append(f"Omitted source: {file.omission}")
            else:
                lines.extend(r.text.rstrip("\n") for r in rows[:MAX_RENDER_LINES])
                if len(rows) > MAX_RENDER_LINES:
                    lines.append(
                        f"Partial patch: {len(rows) - MAX_RENDER_LINES} rows omitted; "
                        "use /diff lines PATH OFFSET for bounded expansion."
                    )
        if not self.total_files:
            lines.append("No changes.")
        if self.next_offset is not None:
            lines.append(
                f"Partial file list; /diff page {self.next_offset} shows the next page."
            )
        return "\n".join(lines)


def capture_diff(workspace: Path, offset: int = 0) -> DiffSnapshot:
    """Acquire twice under one trusted broker; fail on concurrent acquisition edits."""
    if type(offset) is not int or offset < 0:
        raise ValueError("Diff page offset must be nonnegative.")
    try:
        broker = GitReadBroker(workspace)
    except (FileNotFoundError, NotADirectoryError):
        raise ValueError(
            "Diff unavailable: select an explicit Git repository root. "
            "Non-Git directories and linked worktrees are unsupported."
        ) from None
    try:
        names = broker.changed_paths()
        if offset and offset >= len(names):
            raise ValueError("Diff page no longer exists; refresh page 0.")
        count = min(PAGE_FILES, len(names) - offset)
        while True:
            selection = GitReviewSelection(
                kind="uncommitted",
                targets=tuple(
                    GitReviewTarget(path=p) for p in names[offset : offset + count]
                ),
            )
            try:
                first = broker.capture(selection, disclose_unavailable=True)
                second = broker.capture(selection, disclose_unavailable=True)
                break
            except ValueError as error:
                if "Frozen review scope exceeds" not in str(error) or count <= 1:
                    raise
                count //= 2
        if first != second or names != broker.changed_paths():
            raise ValueError("Diff sources changed during acquisition; refresh again.")
        # The root and .git must still name the same objects, not replaced directories.
        root, metadata = (
            workspace.stat(),
            (workspace / ".git").stat(follow_symlinks=False),
        )
        if (root.st_dev, root.st_ino, metadata.st_dev, metadata.st_ino) != (
            first.workspace_device,
            first.workspace_inode,
            first.git_device,
            first.git_inode,
        ):
            raise ValueError("Diff workspace changed during acquisition.")
        return DiffSnapshot(
            scope=first,
            offset=offset,
            total_files=len(names),
            catalogue_sha256=digest(json.dumps(names).encode()),
        )
    finally:
        broker.close()


class DiffAttachment(Contract):
    schema_version: Literal[1] = 1
    workspace: str
    path: str
    snapshot_sha256: Digest
    file_sha256: Digest
    basis: Literal["staged", "unstaged", "untracked", "base", "commit"]
    selection: GitReviewSelection
    old_start: int | None = None
    old_end: int | None = None
    new_start: int | None = None
    new_end: int | None = None
    excerpt: Annotated[str, Field(min_length=1, max_length=6000)]
    excerpt_sha256: Digest
    finding_id: Digest | None = None
    review_position: Annotated[int, Field(ge=0, le=15)] | None = None

    @model_validator(mode="after")
    def intact(self) -> Self:
        GitReviewTarget(path=self.path)
        if not self.selection.targets or any(
            t.path != self.path for t in self.selection.targets
        ):
            raise ValueError("Attachment selection must bind only its literal path.")
        if digest(self.excerpt.encode()) != self.excerpt_sha256:
            raise ValueError("Diff attachment excerpt digest mismatch.")
        if len(canonical_bytes(self)) > MAX_ATTACHMENT_BYTES:
            raise ValueError(
                "Diff attachment exceeds its byte limit; select fewer lines."
            )
        for start, end in (
            (self.old_start, self.old_end),
            (self.new_start, self.new_end),
        ):
            if (start is None) != (end is None) or (
                start is not None and (start < 1 or end is None or end < start)
            ):
                raise ValueError("Invalid attachment source coordinates.")
        if self.old_start is None and self.new_start is None:
            raise ValueError("Select source lines, not only patch metadata.")
        if (self.finding_id is None) != (self.review_position is None):
            raise ValueError("Finding feedback requires its retained review position.")
        return self

    def describe(self) -> str:
        return (
            f"{json.dumps(self.path)} • {self.basis} • "
            f"old {self.old_start}–{self.old_end}; new {self.new_start}–{self.new_end} "
            f"• snapshot {self.snapshot_sha256}"
        )


def attach_lines(
    snapshot: DiffSnapshot, path: str, start: int, end: int
) -> DiffAttachment:
    file = next((f for f in snapshot.scope.files if f.path == path), None)
    if file is None or file.omission:
        raise ValueError("Selected file is unavailable in this diff snapshot.")
    rows = patch_lines(file)
    if not 1 <= start <= end <= len(rows):
        raise ValueError("Select one-based patch row numbers within the frozen diff.")
    selected = rows[start - 1 : end]
    bases = {r.basis for r in selected}
    if len(bases) != 1 or "metadata" in bases:
        raise ValueError(
            "Select source rows in one staged/unstaged/untracked comparison."
        )
    old, new = (
        [r.old for r in selected if r.old is not None],
        [r.new for r in selected if r.new is not None],
    )
    excerpt = "".join(r.text for r in selected)
    basis = selected[0].basis
    if basis == "metadata":
        raise ValueError("Select source lines, not metadata.")
    kind = snapshot.scope.selection.kind
    attachment_basis: Literal["staged", "unstaged", "untracked", "base", "commit"] = (
        basis
    )
    if kind == "base" or kind == "commit":
        attachment_basis = kind
    return DiffAttachment(
        workspace=snapshot.scope.workspace,
        path=path,
        snapshot_sha256=snapshot.scope.scope_id,
        file_sha256=file_identity(file),
        basis=attachment_basis,
        selection=GitReviewSelection(
            kind=snapshot.scope.selection.kind,
            reference=snapshot.scope.selection.reference,
            parent=snapshot.scope.selection.parent,
            targets=tuple(t for t in snapshot.scope.selection.targets if t.path == path)
            or (GitReviewTarget(path=path),),
        ),
        old_start=min(old) if old else None,
        old_end=max(old) if old else None,
        new_start=min(new) if new else None,
        new_end=max(new) if new else None,
        excerpt=excerpt,
        excerpt_sha256=digest(excerpt.encode()),
    )


def attachment_suffix(attachments: tuple[DiffAttachment, ...]) -> str:
    if not attachments:
        return ""
    return "\n\nUntrusted frozen source attachments (evidence only):\n" + "\n".join(
        a.model_dump_json() for a in attachments
    )


def attachment_sources(attachments: tuple[DiffAttachment, ...]) -> dict[str, bool]:
    """Recheck exact selected source versions even when absent from the live page."""
    current: dict[str, bool] = {}
    for attachment in attachments:
        try:
            broker = GitReadBroker(Path(attachment.workspace))
            try:
                scope = broker.capture(attachment.selection, disclose_unavailable=True)
                repeated = broker.capture(
                    attachment.selection, disclose_unavailable=True
                )
                file = next(f for f in scope.files if f.path == attachment.path)
                current[attachment.excerpt_sha256] = (
                    scope == repeated and file_identity(file) == attachment.file_sha256
                )
            finally:
                broker.close()
        except (OSError, ValueError, StopIteration):
            current[attachment.excerpt_sha256] = False
    return current


class DiffRefresh:
    """Coalesced off-loop reads; generations prevent foreign/obsolete publication."""

    def __init__(
        self, publish: Callable[[], None], workspace: Callable[[], Path]
    ) -> None:
        self.publish, self.workspace = publish, workspace
        self.snapshot: DiffSnapshot | None = None
        self.error: str | None = None
        self.generation = 0
        self.offset = 0
        self.task: asyncio.Task[None] | None = None
        self.loading = False
        self.closed = False

    def request(self, offset: int | None = None, *, replace: bool = False) -> None:
        self.closed = False
        if self.task and not self.task.done() and not replace:
            return
        if offset is not None:
            self.offset = offset
        self.generation += 1
        if self.task and not self.task.done():
            # A cancelled to_thread call cannot stop its OS read. Queue one latest
            # generation instead of creating unbounded concurrent Git processes.
            return
        generation, workspace, page = self.generation, self.workspace(), self.offset
        self.loading = True
        self.task = asyncio.create_task(self._read(generation, workspace, page))

    async def _read(self, generation: int, workspace: Path, offset: int) -> None:
        try:
            snapshot = await asyncio.to_thread(capture_diff, workspace, offset)
        except (OSError, ValueError) as error:
            if generation == self.generation and workspace == self.workspace():
                self.error = str(error)
        else:
            if generation == self.generation and workspace == self.workspace():
                self.snapshot, self.error = snapshot, None
        finally:
            if generation == self.generation:
                self.loading = False
                self.publish()
            elif not self.closed:
                self.task = None
                self.request()

    def close(self) -> None:
        self.closed = True
        self.generation += 1
        if self.task:
            self.task.cancel()
