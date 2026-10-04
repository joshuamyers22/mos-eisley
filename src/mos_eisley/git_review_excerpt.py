"""Render only explicitly selected source intervals, with honest comparison labels."""

from __future__ import annotations

import difflib
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mos_eisley.git_review import GitReviewTarget


def _lines(text: str) -> list[str]:
    # Editor/Git coordinates count LF records; preserve CRLF and UTF-8 bytes.
    pieces = text.split("\n")
    return [piece + "\n" for piece in pieces[:-1]] + (
        [pieces[-1]] if pieces[-1] else []
    )


def _slice(payload: bytes | None, target: GitReviewTarget) -> tuple[str | None, int]:
    if payload is None:
        return None, 0
    lines = _lines(payload.decode("utf-8"))
    offset = min((target.start or 1) - 1, len(lines))
    return "".join(lines[offset : target.end]), offset


def _diff(
    path: str, before: tuple[str | None, int], after: tuple[str | None, int]
) -> str:
    old, old_offset = before
    new, new_offset = after
    if old == new:
        return ""
    label = json.dumps(path, ensure_ascii=False)
    lines = difflib.unified_diff(
        _lines(old or ""),
        _lines(new or ""),
        fromfile="/dev/null" if old is None else "a/" + label,
        tofile="/dev/null" if new is None else "b/" + label,
    )
    result: list[str] = []
    for line in lines:
        hunk = re.fullmatch(r"@@ -(\d+)(,\d+)? \+(\d+)(,\d+)? @@\n", line)
        if hunk:
            line = (
                f"@@ -{int(hunk[1]) + old_offset}{hunk[2] or ''} "
                f"+{int(hunk[3]) + new_offset}{hunk[4] or ''} @@\n"
            )
        result.append(
            line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        )
    return "".join(result) or f"Selected file presence changed: {label}\n"


def _source(path: str, payload: tuple[str | None, int]) -> str:
    text, offset = payload
    lines = [f"Source excerpt (no comparison diff): {json.dumps(path)}\n"]
    for index, line in enumerate(_lines(text or ""), offset + 1):
        lines.append(f"{index}: " + line)
        if not line.endswith("\n"):
            lines.append("\n\\ No newline at end of file\n")
    if not text:
        lines.append("Selected source is empty.\n")
    return "".join(lines)


def selected_patch(
    path: str,
    before: bytes | None,
    index: bytes | None,
    after: bytes | None,
    targets: tuple[GitReviewTarget, ...],
    *,
    kind: str,
    mode_patch: str,
) -> str:
    parts = [mode_patch] if mode_patch else []
    anchor = after if after is not None else before
    anchor_side = "after" if after is not None else "before (deleted file)"
    for target in targets:
        if target.end is not None:
            if anchor is None or target.end > len(_lines(anchor.decode("utf-8"))):
                raise ValueError("Selected range exceeds the source line count.")
            parts.append(
                f"Selected {json.dumps(path)} lines {target.start}-{target.end}; "
                f"anchor={anchor_side}. Excerpt comparison uses the same coordinates "
                "independently in each version; other lines are excluded.\n"
            )
            for label, payload in (
                ("before", before),
                ("index", index),
                ("after", after),
            ):
                if payload is not None and target.end > len(
                    _lines(payload.decode("utf-8"))
                ):
                    parts.append(f"{label}: interval clipped at end of source.\n")
        else:
            parts.append(f"Explicitly selected whole file: {json.dumps(path)}\n")
        old, staged, new = (
            _slice(payload, target) for payload in (before, index, after)
        )
        if kind == "files":
            parts.append(_source(path, new))
        else:
            change = _diff(path, old, new)
            if kind == "uncommitted" and old != staged:
                change = (
                    "[staged]\n"
                    + _diff(path, old, staged)
                    + "[unstaged]\n"
                    + _diff(path, staged, new)
                )
            parts.append(
                change
                or "No differences in the selected input.\n"
                + _source(path, new if after is not None else old)
            )
    return "\n".join(parts)
