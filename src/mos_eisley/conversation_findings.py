"""Historical findings projected from retained reports, never inferred resolutions."""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from mos_eisley.conversation_diff import DiffSnapshot, patch_lines
from mos_eisley.conversation_state import ArchivedConversationEntry, ConversationEntry
from mos_eisley.core.models import Contract, Finding
from mos_eisley.git_review import freeze_git_scope


class DiffFinding(Contract):
    review_position: int
    finding: Finding
    critics: tuple[str, ...]
    disposition: str
    judge_rationale: str
    review_decision: str
    scope_id: str | None
    path: str | None
    start: int | None
    end: int | None
    stale: bool
    mapping: str
    correction_positions: tuple[int, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.review_position}:{self.finding.finding_id}"

    def describe(self) -> str:
        f = self.finding
        return (
            f"[{self.key}] {f.impact} / {f.category} • {self.disposition}\n"
            f"Location: {f.location}; {self.mapping}; stale={self.stale}\n"
            f"Review snapshot: {self.scope_id}; critics: {', '.join(self.critics)}\n"
            f"Judge: {self.judge_rationale}; review decision: {self.review_decision}\n"
            f"Claim: {f.claim}\nEvidence ({f.evidence.source}): {f.evidence.quote}\n"
            f"Proposed correction: {f.suggested_fix or 'Not supplied.'}\n"
            f"Correction requests: {self.correction_positions}; "
            "resolution requires independent evidence at the corrected revision."
        )


def finding_location(
    finding: Finding, snapshot: DiffSnapshot
) -> tuple[str, int, int] | None:
    """Only exact literal paths and source-bound coordinates may be navigated."""
    location = finding.location
    for file in snapshot.scope.files:
        prefix = file.path + ":"
        if not location.startswith(prefix):
            continue
        match = re.fullmatch(
            r"(?:L)?([1-9][0-9]*)(?:-(?:L)?([1-9][0-9]*))?", location[len(prefix) :]
        )
        if (
            not match
            or finding.evidence.source != "diff"
            or finding.evidence.quote not in file.patch
        ):
            continue
        start, end = int(match[1]), int(match[2] or match[1])
        if end < start:
            continue
        rows = [
            r for r in patch_lines(file) if r.new is not None and start <= r.new <= end
        ]
        # A deletion can only map to old coordinates; never invent a new line.
        if not rows:
            rows = [
                r
                for r in patch_lines(file)
                if r.old is not None and start <= r.old <= end
            ]
        if rows and finding.evidence.quote in "".join(r.text for r in rows):
            return file.path, start, end
    return None


def retained_findings(
    entries: tuple[ConversationEntry | ArchivedConversationEntry, ...],
    load_entry: Callable[[int, ArchivedConversationEntry], ConversationEntry]
    | None = None,
) -> tuple[DiffFinding, ...]:
    views: list[DiffFinding] = []
    for position, source in enumerate(entries):
        if not source.is_review:
            continue
        if isinstance(source, ArchivedConversationEntry):
            if load_entry is None:
                continue
            entry = load_entry(position, source)
        else:
            entry = source
        packet, result = entry.review_packet, entry.review_result
        if packet is None or result is None:
            continue
        scope = packet.git_scope
        stale = True
        if scope is not None:
            with suppress(OSError, ValueError):
                stale = (
                    freeze_git_scope(Path(scope.workspace), scope.selection) != scope
                )
        candidates: dict[str, Finding] = {}
        critics: dict[str, list[str]] = {}
        for critic in result.critics:
            if critic.critique is not None:
                for finding in critic.critique.findings:
                    candidates[finding.finding_id] = finding
                    critics.setdefault(finding.finding_id, []).append(critic.critic.id)
        for finding in result.verdict.findings:
            candidates[finding.finding_id] = finding
        for finding_id, finding in candidates.items():
            upheld = (
                result.judge_decision is not None
                and finding_id in result.judge_decision.upheld
            )
            disposition = (
                "upheld; required correction"
                if finding_id in result.verdict.required_changes
                else "upheld"
                if upheld
                else "not upheld"
                if result.judge_decision is not None
                else "judge unavailable"
            )
            location = (
                None
                if scope is None
                else finding_location(
                    finding,
                    DiffSnapshot(
                        scope=scope,
                        offset=0,
                        total_files=len(scope.files),
                        catalogue_sha256=scope.scope_id,
                    ),
                )
            )
            corrections = tuple(
                i
                for i, e in enumerate(entries)
                if any(
                    a.finding_id == finding_id and a.review_position == position
                    for a in e.diff_attachments
                )
            )
            views.append(
                DiffFinding(
                    review_position=position,
                    finding=finding,
                    critics=tuple(critics.get(finding_id, [])),
                    disposition=disposition,
                    judge_rationale=result.judge_decision.rationale
                    if result.judge_decision
                    else result.verdict.rationale,
                    review_decision=result.verdict.decision,
                    scope_id=None if scope is None else scope.scope_id,
                    path=None if location is None else location[0],
                    start=None if location is None else location[1],
                    end=None if location is None else location[2],
                    stale=stale,
                    mapping="unmapped source evidence"
                    if location is None
                    else "exact historical source coordinates",
                    correction_positions=corrections,
                )
            )
    rank = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    return tuple(
        sorted(
            views,
            key=lambda f: (
                rank[f.finding.impact],
                f.review_position,
                f.finding.finding_id,
            ),
        )
    )


def hydrate_review_entries(
    entries: tuple[ConversationEntry | ArchivedConversationEntry, ...],
    load_entry: Callable[[int, ArchivedConversationEntry], ConversationEntry] | None,
) -> tuple[ConversationEntry | ArchivedConversationEntry, ...]:
    """Use owner-bound loaders on their owning thread before off-loop Git reads."""
    return tuple(
        load_entry(i, entry)
        if entry.is_review
        and isinstance(entry, ArchivedConversationEntry)
        and load_entry is not None
        else entry
        for i, entry in enumerate(entries)
    )
