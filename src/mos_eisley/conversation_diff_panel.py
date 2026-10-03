"""Bounded presentation model for the read-only conversation diff panel."""

from __future__ import annotations

from dataclasses import dataclass

from mos_eisley.conversation_git import (
    Change,
    ChangeKind,
    DiffBasis,
    GitSnapshot,
    GitState,
    Patch,
)

RENDER_LINE_LIMITS = (500, 1500, 4000)


@dataclass(frozen=True)
class DiffItem:
    change: Change
    basis: DiffBasis | None

    @property
    def key(self) -> tuple[str, DiffBasis | None]:
        return self.change.path, self.basis


def items(snapshot: GitSnapshot) -> tuple[DiffItem, ...]:
    result: list[DiffItem] = []
    for change in snapshot.changes:
        if change.kind is ChangeKind.UNTRACKED:
            result.append(DiffItem(change, None))
        else:
            if change.staged is not None:
                result.append(DiffItem(change, DiffBasis.STAGED))
            if change.unstaged is not None:
                result.append(DiffItem(change, DiffBasis.UNSTAGED))
    return tuple(result)


def item_label(item: DiffItem) -> str:
    change = item.change
    if item.basis is None:
        return f"untracked  ?/?  {change.path}"
    if item.basis is DiffBasis.STAGED:
        added, removed, status = (
            change.staged_added,
            change.staged_removed,
            change.staged,
        )
    else:
        added, removed, status = (
            change.unstaged_added,
            change.unstaged_removed,
            change.unstaged,
        )
    counts = "binary" if added is None or removed is None else f"+{added}/-{removed}"
    rename = f" (from {change.old_path})" if change.old_path else ""
    return f"{item.basis.value} {status or '?'} {counts} {change.path}{rename}"


def inventory_text(
    snapshot: GitSnapshot, entries: tuple[DiffItem, ...], selected: int
) -> str:
    if snapshot.state is GitState.NON_GIT:
        return "Not a Git checkout in the selected directory."
    heading = (
        "Unborn HEAD • staged changes compare to an empty tree"
        if snapshot.state is GitState.UNBORN
        else "Tracked: staged HEAD → index; unstaged index → worktree"
    )
    lines = [heading, "Safe raw Git comparison; filters are disabled."]
    if snapshot.omission:
        lines.append("Incomplete view: " + snapshot.omission)
    if not entries:
        lines.append(
            "No displayable changed files; see omission above."
            if snapshot.omission
            else "No changed files in the selected directory."
        )
    else:
        for index, item in enumerate(entries):
            marker = "▶" if index == selected else " "
            lines.append(f"{marker} {item_label(item)}")
    return "\n".join(lines)


def patch_text(patch: Patch | None, item: DiffItem | None, limit_index: int) -> str:
    if item is None:
        return "Select a changed file."
    if item.basis is None:
        return "Untracked path only. Content preview requires a separate read policy."
    if patch is None:
        return "Loading bounded patch…"
    text = patch.data.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    limit = RENDER_LINE_LIMITS[limit_index]
    shown = "".join(lines[:limit])
    if len(lines) > limit:
        shown += (
            f"\n[Partial view: {len(lines) - limit} lines omitted. "
            "F11 expands within the 256 KB patch cap.]\n"
        )
    if not shown:
        return "No textual patch for this change (binary or metadata-only)."
    return shown
