"""Shared plain/JSON diff controls; selections never implicitly submit work."""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Callable
from pathlib import Path

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_diff import (
    MAX_RENDER_LINES,
    DiffAttachment,
    DiffSnapshot,
    attach_lines,
    attachment_sources,
    capture_diff,
    patch_lines,
)
from mos_eisley.conversation_findings import (
    DiffFinding,
    hydrate_review_entries,
    retained_findings,
)
from mos_eisley.git_review import revalidate_git_scope


class DiffCommands:
    def __init__(
        self,
        controller: RuntimeConversationController,
        emit: Callable[[dict[str, object]], None],
    ) -> None:
        self.controller, self.emit = controller, emit
        self.snapshot: DiffSnapshot | None = None
        self.attachments: tuple[DiffAttachment, ...] = ()
        self.findings: tuple[DiffFinding, ...] = ()

    async def execute(self, command: str) -> str | None:
        args = shlex.split(command)[1:]
        if not args or args[:1] in (["refresh"], ["page"]):
            if args and args[0] == "page":
                if len(args) != 2:
                    raise ValueError("Use /diff page OFFSET.")
                offset = int(args[1])
            else:
                if len(args) > 1:
                    raise ValueError("Use /diff or /diff refresh.")
                offset = 0 if self.snapshot is None else self.snapshot.offset
            self.snapshot = await asyncio.to_thread(
                capture_diff, Path(self.controller.state.workspace), offset
            )
            self.emit({**self.snapshot.event(), "toggle": not args})
            if self.attachments:
                current = await asyncio.to_thread(attachment_sources, self.attachments)
                self.emit(
                    {
                        "type": "conversation.diff_attachment_sources",
                        "sources": current,
                        "text": "Frozen attachment source freshness: " + str(current),
                    }
                )
            return None
        if args == ["findings"]:
            self.findings = await asyncio.to_thread(
                retained_findings,
                hydrate_review_entries(
                    self.controller.state.entries, self.controller.load_entry
                ),
            )
            self.emit(
                {
                    "type": "conversation.diff_findings",
                    "findings": [f.model_dump(mode="json") for f in self.findings],
                    "text": "\n\n".join(f.describe() for f in self.findings[:20])
                    or "No retained findings.",
                    "omitted": max(0, len(self.findings) - 20),
                }
            )
            return None
        if args[:1] == ["remove"] and len(args) == 2:
            index = int(args[1]) - 1
            if not 0 <= index < len(self.attachments):
                raise ValueError("Attachment number is unavailable.")
            self.attachments = self.attachments[:index] + self.attachments[index + 1 :]
            self.emit_attachments()
            return None
        if args[:1] in (["finding"], ["feedback"], ["fix"]):
            if len(args) < 2:
                raise ValueError(
                    "Use /diff finding KEY, /diff feedback KEY TEXT or /diff fix KEY."
                )
            if args[0] in {"fix", "finding"} and len(args) != 2:
                raise ValueError("Use /diff fix KEY or /diff finding KEY.")
            if args[0] == "feedback" and len(args) < 3:
                raise ValueError("Use /diff feedback KEY TEXT.")
            # Keys include the retained review position and content-derived finding ID.
            self.findings = await asyncio.to_thread(
                retained_findings,
                hydrate_review_entries(
                    self.controller.state.entries, self.controller.load_entry
                ),
            )
            finding = next((f for f in self.findings if f.key == args[1]), None)
            if finding is None:
                raise ValueError("Finding key unavailable; use /diff findings.")
            self.emit(
                {
                    "type": "conversation.diff_finding",
                    "finding": finding.model_dump(mode="json"),
                    "text": finding.describe(),
                }
            )
            if args[0] == "finding":
                if len(args) != 2:
                    raise ValueError("Use /diff finding KEY.")
                source = self.controller.state.entries[finding.review_position]
                from mos_eisley.conversation_state import ArchivedConversationEntry

                if isinstance(source, ArchivedConversationEntry):
                    if self.controller.load_entry is None:
                        raise ValueError("Retained review loader unavailable.")
                    source = self.controller.load_entry(finding.review_position, source)
                if (
                    source.review_packet is not None
                    and source.review_packet.git_scope is not None
                ):
                    scope = source.review_packet.git_scope
                    snapshot = DiffSnapshot(
                        scope=scope,
                        offset=0,
                        total_files=len(scope.files),
                        catalogue_sha256=scope.scope_id,
                    )
                    self.emit(
                        {
                            "type": "conversation.diff_finding_source",
                            "finding": finding.model_dump(mode="json"),
                            "snapshot": snapshot.model_dump(mode="json"),
                            "text": "Historical review source\n" + snapshot.describe(),
                        }
                    )
                return None
            if finding.stale or finding.path is None or finding.start is None:
                raise ValueError(
                    "Stale or unmapped finding cannot attach current source; "
                    "rerun review."
                )
            source = self.controller.state.entries[finding.review_position]
            from mos_eisley.conversation_state import ArchivedConversationEntry

            if isinstance(source, ArchivedConversationEntry):
                if self.controller.load_entry is None:
                    raise ValueError("Retained review loader unavailable.")
                source = self.controller.load_entry(finding.review_position, source)
            assert (
                source.review_packet is not None
                and source.review_packet.git_scope is not None
            )
            scope = source.review_packet.git_scope
            snapshot = DiffSnapshot(
                scope=scope,
                offset=0,
                total_files=len(scope.files),
                catalogue_sha256=scope.scope_id,
            )
            file = next(f for f in scope.files if f.path == finding.path)
            rows = patch_lines(file)
            matches = [
                i + 1
                for i, r in enumerate(rows)
                if (
                    r.new is not None
                    and finding.start <= r.new <= (finding.end or finding.start)
                )
            ]
            if not matches:
                matches = [
                    i + 1
                    for i, r in enumerate(rows)
                    if (
                        r.old is not None
                        and finding.start <= r.old <= (finding.end or finding.start)
                    )
                ]
            attachment = attach_lines(snapshot, file.path, min(matches), max(matches))
            attachment = DiffAttachment.model_validate(
                {
                    **attachment.model_dump(),
                    "finding_id": finding.finding.finding_id,
                    "review_position": finding.review_position,
                }
            )
            await asyncio.to_thread(revalidate_git_scope, scope)
            if attachment not in self.attachments and len(self.attachments) >= 4:
                raise ValueError(
                    "Remove an attachment before adding another (maximum four)."
                )
            if attachment not in self.attachments:
                self.attachments += (attachment,)
            self.emit_attachments()
            if args[0] == "fix":
                if len(args) != 2:
                    raise ValueError("Use /diff fix KEY.")
                return (
                    f"Fix selected finding {finding.key} under the current creator-led "
                    "plan/test and bounded correction policy. Preserve task "
                    "budgets and review counters. Verify the correction and obtain "
                    "independent review "
                    "at its exact revision before claiming resolution.\n"
                    + finding.describe()
                )
            if len(args) < 3:
                raise ValueError("Use /diff feedback KEY TEXT.")
            return f"Feedback on finding {finding.key}: " + " ".join(args[2:])
        if self.snapshot is None:
            raise ValueError("Open /diff before selecting a file or source lines.")
        if args[:1] == ["attach"] and len(args) == 4:
            if len(self.attachments) >= 4:
                raise ValueError(
                    "Remove an attachment before adding another (maximum four)."
                )
            self.attachments += (
                attach_lines(self.snapshot, args[1], int(args[2]), int(args[3])),
            )
            self.emit_attachments()
            return None
        if args[:1] == ["lines"] and len(args) == 3:
            file = next(
                (f for f in self.snapshot.scope.files if f.path == args[1]), None
            )
            if file is None:
                raise ValueError("File is not in the frozen diff page.")
            offset = int(args[2])
            rows = patch_lines(file)
            if offset < 0 or offset >= len(rows):
                raise ValueError("Patch row offset is unavailable.")
            self.emit(
                {
                    "type": "conversation.diff_lines",
                    "path": file.path,
                    "snapshot_sha256": self.snapshot.scope.scope_id,
                    "offset": offset,
                    "total_rows": len(rows),
                    "rows": [
                        r.model_dump(mode="json")
                        for r in rows[offset : offset + MAX_RENDER_LINES]
                    ],
                    "text": "\n".join(
                        f"{i + 1}: {r.text.rstrip(chr(10))}"
                        for i, r in enumerate(
                            rows[offset : offset + MAX_RENDER_LINES], offset
                        )
                    ),
                }
            )
            return None
        raise ValueError(
            "Diff commands: /diff [refresh|page OFFSET|lines PATH OFFSET|"
            "attach PATH START END|remove N|findings|finding KEY|"
            "feedback KEY TEXT|fix KEY]."
        )

    def emit_attachments(self) -> None:
        self.emit(
            {
                "type": "conversation.diff_attachments",
                "attachments": [a.model_dump(mode="json") for a in self.attachments],
                "text": "\n".join(
                    f"{i + 1}. {a.describe()}" for i, a in enumerate(self.attachments)
                )
                or "No source attachments.",
            }
        )
