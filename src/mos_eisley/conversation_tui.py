"""Full-screen recorded conversation; execution stays in the shared terminal."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from prompt_toolkit.application import Application, in_terminal
from prompt_toolkit.application.current import set_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import DummyHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.output import Output
from prompt_toolkit.selection import SelectionState
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea
from pydantic import TypeAdapter

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_cli import terminal
from mos_eisley.conversation_context_preview import pressure_status
from mos_eisley.conversation_diff import (
    MAX_RENDER_LINES,
    DiffAttachment,
    DiffRefresh,
    DiffSnapshot,
    attach_lines,
    attachment_sources,
    file_identity,
    patch_lines,
)
from mos_eisley.conversation_directory import (
    DirectoryPicker,
    DirectorySelection,
    DirectorySelectionError,
)
from mos_eisley.conversation_findings import (
    DiffFinding,
    hydrate_review_entries,
    retained_findings,
)
from mos_eisley.conversation_history import TranscriptHistory
from mos_eisley.conversation_input import (
    ConversationInput,
    ConversationSubmission,
    submission_command,
)
from mos_eisley.conversation_project import ProjectLocation
from mos_eisley.conversation_remember import memory_phrase_command
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_switch import SWITCH_COMMAND, switch_target
from mos_eisley.run.conversation_artifacts import ArtifactContent
from mos_eisley.run.conversation_transcript import TranscriptPage


def display_text(text: str) -> str:
    """Render text, never model-controlled terminal escapes or bidi controls."""
    return "".join(
        char if char.isprintable() or char in "\n\t" else json.dumps(char)[1:-1]
        for char in text
    )


class EditorBuffer(Buffer):
    """Bounded draft and undo history, without persistent input history."""

    def __init__(self, notice: Callable[[str], None], busy: Callable[[], bool]) -> None:
        self.notice = notice
        self.invalid = False
        self.literal = False
        self.previous = Document()
        self.restoring = False
        self.undo_documents: list[Document] = []
        self.redo_documents: list[Document] = []
        super().__init__(
            multiline=True,
            history=DummyHistory(),
            read_only=Condition(busy),
            on_text_changed=self.changed,
        )

    def changed(self, buffer: Buffer) -> None:
        if self.restoring:
            return
        if len(self.text) > 8000 or self.text.count("\n") >= 256:
            self.restoring = True
            try:
                self.set_document(self.previous, bypass_readonly=True)
            finally:
                self.restoring = False
            self.invalid = True
            self.notice(
                "Edit exceeds 8,000 characters or 256 lines. Ctrl-U clears the draft."
            )
        else:
            self.previous = self.document

    def save_to_undo_stack(self, clear_redo_stack: bool = True) -> None:
        if not self.undo_documents or self.undo_documents[-1].text != self.text:
            self.undo_documents.append(self.document)
            self.undo_documents[:] = self.undo_documents[-32:]
        if clear_redo_stack:
            self.redo_documents.clear()

    def undo(self) -> None:
        while self.undo_documents:
            document = self.undo_documents.pop()
            if document.text != self.text:
                self.redo_documents.append(self.document)
                self.set_document(document)
                break

    def redo(self) -> None:
        if self.redo_documents:
            self.save_to_undo_stack(clear_redo_stack=False)
            self.set_document(self.redo_documents.pop())

    def clear(self) -> None:
        self.reset()
        self.previous = Document()
        self.invalid = False
        self.literal = False
        self.undo_documents.clear()
        self.redo_documents.clear()


class ConversationTUI:
    def __init__(
        self,
        controller: RuntimeConversationController,
        review_packet: ConversationReviewPacket | None = None,
        *,
        welcome: str = "",
        initial_prompt: str | None = None,
        allow_directory_switch: bool = False,
        project_location: ProjectLocation | None = None,
        memory_resolver: Callable[[Path], DirectorySelection | None] | None = None,
        refresh_memory: Callable[[bool], None] | None = None,
        memory_command: Callable[[str], dict[str, object]] | None = None,
        load_transcript: Callable[[str | None], TranscriptPage] | None = None,
        load_artifact: Callable[[str], ArtifactContent] | None = None,
        input: Input | None = None,
        output: Output | None = None,
    ) -> None:
        self.controller = controller
        self.review_packet = review_packet
        self.welcome = welcome
        self.initial_prompt = initial_prompt
        self.allow_directory_switch = allow_directory_switch
        self.directory_target: DirectorySelection | None = None
        self.memory_resolver = memory_resolver
        self.project_location = project_location or ProjectLocation.inspect(
            Path(controller.state.workspace)
        )
        self.refresh_memory = refresh_memory
        self.memory_command = memory_command
        self.history = (
            None
            if load_transcript is None
            else TranscriptHistory(
                load_transcript,
                lambda: (
                    self.controller.state.session_id,
                    self.controller.state.revision,
                    len(self.controller.state.entries),
                ),
                self.refresh,
                load_artifact,
            )
        )
        self.queue: asyncio.Queue[ConversationInput] = asyncio.Queue(maxsize=32)
        self.notice = (
            "Enter sends • Alt-Enter adds a line • Ctrl-C stops • Ctrl-D quits"
        )
        self.sending = False
        self.details = False
        self.memory_visible = False
        self.memory_report: str | None = None
        self.directory_visible = False
        self.context_preview: tuple[int, str] | None = None
        self.review_scope_preview: str | None = None
        self.context_command = "/context"
        self.submission: asyncio.Task[None] | None = None
        self.editor = EditorBuffer(self.set_notice, lambda: self.sending)
        self.transcript = TextArea(read_only=True, scrollbar=True, wrap_lines=True)
        self.diff_visible = False
        self.diff_file = 0
        self.diff_selected_path: str | None = None
        self.diff_rows_offset = 0
        self.diff_findings: tuple[DiffFinding, ...] = ()
        self.diff_finding = 0
        self.diff_show_findings = False
        self.diff_evidence: DiffSnapshot | None = None
        self.diff_evidence_finding: DiffFinding | None = None
        self.diff_last_file_sha256: str | None = None
        self.diff_attachments: tuple[DiffAttachment, ...] = ()
        self.diff_attachment_freshness: dict[str, bool] = {}
        self.diff_pane = TextArea(read_only=True, scrollbar=True, wrap_lines=False)
        self.diff_refresh = DiffRefresh(
            self.render_diff, lambda: Path(self.controller.state.workspace)
        )
        self.diff_poll: asyncio.Task[None] | None = None
        self.editor_control = BufferControl(buffer=self.editor)
        keys = KeyBindings()

        def send(event: KeyPressEvent) -> None:
            self.send()

        def newline(event: KeyPressEvent) -> None:
            if not self.sending:
                self.app.layout.focus(self.editor_control)
                self.editor.insert_text("\n")

        def literal_send(event: KeyPressEvent) -> None:
            self.send(literal=True)

        def paste(event: KeyPressEvent) -> None:
            if not self.sending:
                self.editor.literal = True
                self.app.layout.focus(self.editor_control)
                self.editor.insert_text(
                    event.data.replace("\r\n", "\n").replace("\r", "\n")
                )

        def stop(event: KeyPressEvent) -> None:
            self.control("/stop", priority=True)

        def quit_session(event: KeyPressEvent) -> None:
            self.control("/quit", priority=True)

        def directory(event: KeyPressEvent) -> None:
            if self.editor.text or self.sending:
                self.set_notice("Send or discard the unsent draft before switching.")
            else:
                self.control(SWITCH_COMMAND)

        def clear(event: KeyPressEvent) -> None:
            if not self.sending:
                self.editor.clear()
                self.diff_attachments = ()
                self.set_notice("Unsent draft discarded.")

        def focus(event: KeyPressEvent) -> None:
            targets = [self.editor_control, self.transcript]
            if self.diff_visible:
                targets.append(self.diff_pane)
            current = next(
                (
                    i
                    for i, target in enumerate(targets)
                    if self.app.layout.has_focus(target)
                ),
                0,
            )
            self.app.layout.focus(targets[(current + 1) % len(targets)])

        def toggle_diff(event: KeyPressEvent) -> None:
            self.toggle_diff()

        def refresh_diff(event: KeyPressEvent) -> None:
            self.diff_evidence = self.diff_evidence_finding = None
            self.diff_show_findings = False
            self.diff_refresh.request(replace=True)

        def next_file(event: KeyPressEvent) -> None:
            if self.diff_show_findings and self.diff_findings:
                self.diff_finding = (self.diff_finding + 1) % len(self.diff_findings)
                self.render_diff(reset=True)
                return
            snapshot = self.diff_refresh.snapshot
            if snapshot is None:
                return
            if self.diff_file + 1 < len(snapshot.scope.files):
                self.diff_file += 1
            elif snapshot.next_offset is not None:
                self.diff_file = 0
                self.diff_refresh.request(snapshot.next_offset, replace=True)
            self.diff_rows_offset = 0
            self.diff_selected_path = None
            self.diff_show_findings = False
            self.render_diff(reset=True)

        def previous_file(event: KeyPressEvent) -> None:
            if self.diff_show_findings and self.diff_findings:
                self.diff_finding = (self.diff_finding - 1) % len(self.diff_findings)
                self.render_diff(reset=True)
                return
            if self.diff_file:
                self.diff_file -= 1
            else:
                self.diff_refresh.request(0, replace=True)
            self.diff_rows_offset = 0
            self.diff_selected_path = None
            self.diff_show_findings = False
            self.render_diff(reset=True)

        def expand_diff(event: KeyPressEvent) -> None:
            snapshot = self.diff_refresh.snapshot
            if snapshot and snapshot.scope.files:
                rows = patch_lines(snapshot.scope.files[self.diff_file])
                self.diff_rows_offset = (
                    self.diff_rows_offset + MAX_RENDER_LINES
                ) % max(1, len(rows))
                self.render_diff(reset=True)

        def attach_diff(event: KeyPressEvent) -> None:
            if self.sending:
                self.set_notice(
                    "Wait for the current submission before attaching source."
                )
                return
            snapshot = self.diff_evidence or self.diff_refresh.snapshot
            if snapshot is None or not snapshot.scope.files or self.diff_show_findings:
                self.set_notice("Select source rows in the diff before attaching.")
                return
            document = self.diff_pane.buffer.document
            selection = document.selection
            start = document.cursor_position_row
            end = start
            if selection is not None:
                other, _ = document.translate_index_to_position(
                    selection.original_cursor_position
                )
                start, end = min(start, other), max(end, other)
            # The rendered patch begins after five bounded metadata rows.
            start = start - self.diff_patch_header_rows + self.diff_rows_offset + 1
            end = end - self.diff_patch_header_rows + self.diff_rows_offset + 1
            try:
                if len(self.diff_attachments) >= 4:
                    raise ValueError("Remove an attachment first (maximum four).")
                attachment = attach_lines(
                    snapshot, snapshot.scope.files[self.diff_file].path, start, end
                )
            except ValueError as error:
                self.set_notice(str(error))
            else:
                self.diff_attachments += (attachment,)
                self.set_notice(
                    "Frozen source attached. Alt-Backspace removes latest attachment."
                )
                self.app.invalidate()

        def remove_attachment(event: KeyPressEvent) -> None:
            self.diff_attachments = self.diff_attachments[:-1]
            self.app.invalidate()

        def findings(event: KeyPressEvent) -> None:
            self.control("/diff findings")

        def open_finding(event: KeyPressEvent) -> None:
            if self.diff_show_findings and self.diff_findings:
                self.control(
                    "/diff finding " + self.diff_findings[self.diff_finding].key
                )

        def previous_page(event: KeyPressEvent) -> None:
            if self.diff_visible and self.app.layout.has_focus(self.diff_pane):
                self.diff_pane.buffer.cursor_up(count=10)
                return
            self.app.layout.focus(self.transcript)
            if (
                self.history
                and self.history.visible
                and self.transcript.buffer.document.cursor_position_row == 0
            ):
                self.history.move(-1)
            else:
                self.transcript.buffer.cursor_up(count=10)

        def next_page(event: KeyPressEvent) -> None:
            if self.diff_visible and self.app.layout.has_focus(self.diff_pane):
                self.diff_pane.buffer.cursor_down(count=10)
                return
            self.app.layout.focus(self.transcript)
            document = self.transcript.buffer.document
            if (
                self.history
                and self.history.visible
                and document.cursor_position_row == document.line_count - 1
            ):
                self.history.move(1)
            else:
                self.transcript.buffer.cursor_down(count=10)

        def details(event: KeyPressEvent) -> None:
            if self.history and self.history.visible:
                self.set_notice("F5 returns to live view for latest review details.")
                return
            self.details = not self.details
            self.refresh()

        def history(event: KeyPressEvent) -> None:
            if self.history is None:
                self.set_notice(
                    "Saved history paging is available for SQLite sessions."
                )
                return
            if self.history.visible:
                self.history.close()
                self.app.layout.focus(self.editor_control)
                self.refresh()
            else:
                self.details = self.memory_visible = self.directory_visible = False
                self.memory_report = None
                self.context_preview = None
                self.app.layout.focus(self.transcript)
                self.history.reload()

        def reload_history(event: KeyPressEvent) -> None:
            if self.history and self.history.visible:
                self.history.reload()

        def continue_work(event: KeyPressEvent) -> None:
            self.control("/continue")

        def select_artifact(event: KeyPressEvent) -> None:
            if self.history and self.history.visible:
                self.history.select_next_artifact()

        def expand_artifact(event: KeyPressEvent) -> None:
            if self.history and self.history.visible:
                self.app.layout.focus(self.transcript)
                self.history.toggle_artifact()

        keys.add(
            "enter",
            filter=Condition(lambda: self.app.layout.has_focus(self.editor_control)),
        )(send)
        keys.add("escape", "enter")(newline)
        keys.add("c-j")(newline)
        keys.add("c-s")(literal_send)
        keys.add(Keys.BracketedPaste)(paste)
        keys.add("c-c")(stop)
        keys.add(Keys.SIGINT)(stop)
        keys.add("c-d")(quit_session)
        keys.add("c-u")(clear)
        keys.add("tab")(focus)
        keys.add("pageup")(previous_page)
        keys.add("pagedown")(next_page)
        keys.add("f3")(details)
        keys.add("f4")(continue_work)
        keys.add("f5")(history)
        keys.add("f6")(reload_history)
        keys.add("f7")(select_artifact)
        keys.add("f8")(expand_artifact)
        keys.add("f9")(directory)
        keys.add("f10")(toggle_diff)
        keys.add(
            "f11",
            filter=Condition(
                lambda: self.diff_visible and self.app.layout.has_focus(self.diff_pane)
            ),
        )(attach_diff)
        keys.add("f12")(findings)
        diff_focus = Condition(
            lambda: self.diff_visible and self.app.layout.has_focus(self.diff_pane)
        )
        keys.add("c-r", filter=diff_focus)(refresh_diff)
        keys.add("c-n", filter=diff_focus)(next_file)
        keys.add("c-p", filter=diff_focus)(previous_file)
        keys.add("c-e", filter=diff_focus)(expand_diff)
        keys.add("enter", filter=diff_focus)(open_finding)
        keys.add("escape", "backspace")(remove_attachment)

        wide = Condition(lambda: self.app.output.get_size().columns >= 110)
        shown = Condition(lambda: self.diff_visible)
        conversation_frame = Frame(
            self.transcript,
            title="Conversation • Tab / PgUp / PgDn • F3 review • F5 history",
        )
        diff_frame = Frame(
            self.diff_pane,
            title=(
                "Diff • Ctrl-N/P files • Ctrl-R refresh • Ctrl-E expand "
                "• F11 attach • F12 findings"
            ),
        )
        body = VSplit(
            [
                ConditionalContainer(
                    conversation_frame,
                    filter=~shown
                    | wide
                    | Condition(lambda: not self.app.layout.has_focus(self.diff_pane)),
                ),
                ConditionalContainer(
                    diff_frame,
                    filter=shown
                    & (
                        wide
                        | Condition(lambda: self.app.layout.has_focus(self.diff_pane))
                    ),
                ),
            ]
        )

        layout = HSplit(
            [
                Window(
                    FormattedTextControl(self.header),
                    height=3,
                    style="class:title",
                ),
                body,
                ConditionalContainer(
                    Window(
                        FormattedTextControl(self.attachment_preview),
                        height=Dimension(max=5),
                        wrap_lines=True,
                    ),
                    filter=Condition(lambda: bool(self.diff_attachments)),
                ),
                Frame(
                    Window(
                        self.editor_control,
                        height=Dimension(min=3, preferred=5, max=10),
                        wrap_lines=True,
                    ),
                    title=(
                        "Message • Enter send • Alt-Enter newline • "
                        "Ctrl-S literal send • Ctrl-U clear"
                    ),
                ),
                Window(
                    FormattedTextControl(lambda: display_text(self.notice)),
                    height=2,
                    wrap_lines=True,
                ),
                Window(
                    FormattedTextControl(self.status),
                    height=2,
                    wrap_lines=True,
                    style="class:status",
                ),
            ]
        )
        self.app: Application[None] = Application(
            layout=Layout(layout, focused_element=self.editor_control),
            key_bindings=keys,
            full_screen=True,
            input=input,
            output=output,
            style=Style.from_dict(
                {"title": "bold", "status": "reverse", "frame.label": "bold"}
            ),
            min_redraw_interval=0.05,
            mouse_support=True,
        )
        self.refresh()

    def toggle_diff(self) -> None:
        self.diff_visible = not self.diff_visible
        if self.diff_visible:
            self.app.layout.focus(self.diff_pane)
            self.diff_refresh.request()
        else:
            self.app.layout.focus(self.editor_control)
        self.app.invalidate()

    def attachment_preview(self) -> str:
        snapshot = self.diff_refresh.snapshot
        current = (
            {}
            if snapshot is None
            else {f.path: file_identity(f) for f in snapshot.scope.files}
        )
        return display_text(
            "Source attachments • Alt-Backspace removes latest\n"
            + "\n".join(
                f"{i + 1}. {a.describe()} • "
                + (
                    "source changed"
                    if self.diff_attachment_freshness.get(a.excerpt_sha256) is False
                    or a.path in current
                    and current[a.path] != a.file_sha256
                    else "source unchanged at last refresh"
                    if self.diff_attachment_freshness.get(a.excerpt_sha256) is True
                    or current.get(a.path) == a.file_sha256
                    else "source freshness unverified"
                )
                for i, a in enumerate(self.diff_attachments)
            )
        )

    def render_diff(self, *, reset: bool = False) -> None:
        snapshot = self.diff_evidence or self.diff_refresh.snapshot
        before = self.diff_pane.buffer.document
        selected_file_sha256: str | None = None
        if self.diff_show_findings:
            if self.diff_findings:
                self.diff_finding = min(self.diff_finding, len(self.diff_findings) - 1)
                selected = self.diff_findings[self.diff_finding]
                text = (
                    f"Historical finding {self.diff_finding + 1} "
                    f"of {len(self.diff_findings)}\n"
                    "Ctrl-N/P findings • Enter opens evidence/diff "
                    "• /diff refresh returns to live\n" + selected.describe()
                )
            else:
                text = "No retained findings."
        elif snapshot is None:
            text = "Diff unavailable: " + (
                self.diff_refresh.error or "Loading bounded Git snapshot…"
            )
        else:
            paths = [f.path for f in snapshot.scope.files]
            if self.diff_selected_path in paths:
                self.diff_file = paths.index(self.diff_selected_path)
            self.diff_file = min(self.diff_file, max(0, len(snapshot.scope.files) - 1))
            self.diff_selected_path = paths[self.diff_file] if paths else None
            header = [
                f"Workspace: {snapshot.scope.workspace}",
                f"Basis: {snapshot.basis_label}",
                f"Snapshot: {snapshot.scope.scope_id}",
                f"Files {snapshot.offset + 1 if snapshot.total_files else 0}–"
                f"{snapshot.offset + len(snapshot.scope.files)} "
                f"of {snapshot.total_files} "
                "(renames: deletion/addition)",
            ]
            if self.diff_evidence_finding is not None:
                finding = next(
                    (
                        f
                        for f in self.diff_findings
                        if f.key == self.diff_evidence_finding.key
                    ),
                    self.diff_evidence_finding,
                )
                header.insert(
                    0,
                    f"Historical finding {finding.key}; stale={finding.stale}; "
                    "Ctrl-R returns to the live diff.",
                )
            for i, file in enumerate(snapshot.scope.files):
                rows = patch_lines(file)
                added, removed = (
                    sum(r.new is not None and r.old is None for r in rows),
                    sum(r.old is not None and r.new is None for r in rows),
                )
                states = ",".join(
                    s
                    for s, yes in (
                        ("staged", file.staged),
                        ("unstaged", file.unstaged),
                        ("untracked", file.untracked),
                    )
                    if yes
                )
                header.append(
                    f"{'→' if i == self.diff_file else ' '} {i + 1}. "
                    f"{json.dumps(file.path)} [{states}] +{added} -{removed}"
                    + (f" • omitted {file.omission}" if file.omission else "")
                )
            if not snapshot.scope.files:
                header.append("No changes.")
            if snapshot.next_offset is not None:
                header.append(
                    f"Partial file list; Ctrl-N loads page {snapshot.next_offset}."
                )
            self.diff_patch_header_rows = len(header)
            if snapshot.scope.files:
                file = snapshot.scope.files[self.diff_file]
                selected_file_sha256 = file_identity(file)
                rows = patch_lines(file)
                self.diff_rows_offset = min(
                    self.diff_rows_offset, max(0, len(rows) - 1)
                )
                header.extend(
                    f"{i + 1:4} {r.basis:9} {r.old or '-':>5} "
                    f"{r.new or '-':>5} | {r.text.rstrip(chr(10))}"
                    for i, r in enumerate(
                        rows[
                            self.diff_rows_offset : self.diff_rows_offset
                            + MAX_RENDER_LINES
                        ],
                        self.diff_rows_offset,
                    )
                )
                if self.diff_rows_offset or len(rows) > MAX_RENDER_LINES:
                    header.append(
                        "Partial patch rows; Ctrl-E expands the next bounded chunk."
                    )
            text = "\n".join(header)
        if self.diff_refresh.error and snapshot is not None:
            text = "STALE: refresh failed: " + self.diff_refresh.error + "\n" + text
            self.diff_patch_header_rows = getattr(self, "diff_patch_header_rows", 0) + 1
        text = display_text(text)
        if text != self.diff_pane.text:
            # Patch row prefixes retain comparison and source coordinates; anchor
            # to those when insertions move the file list or hunk headers.
            def anchor(position: int) -> int:
                old_row, column = before.translate_index_to_position(position)
                current_line = before.lines[old_row]
                if " | " in current_line:
                    prefix = current_line.split(" | ", 1)[0].split()
                    if len(prefix) == 4:
                        for index, line in enumerate(text.splitlines()):
                            candidate = line.split(" | ", 1)[0].split()
                            if len(candidate) == 4 and candidate[1:] == prefix[1:]:
                                return Document(text).translate_row_col_to_index(
                                    index, min(column, len(line))
                                )
                return min(position, len(text))

            cursor = 0 if reset else anchor(before.cursor_position)
            selection = None
            if not reset and before.selection is not None:
                if selected_file_sha256 == self.diff_last_file_sha256:
                    selection = SelectionState(
                        anchor(before.selection.original_cursor_position),
                        before.selection.type,
                    )
                else:
                    self.set_notice(
                        "Diff source changed; selection cleared. "
                        "Frozen attachments retained."
                    )
            self.diff_pane.buffer.set_document(
                Document(text, cursor, selection), bypass_readonly=True
            )
            self.diff_pane.buffer.selection_state = selection
        self.diff_last_file_sha256 = selected_file_sha256
        self.app.invalidate()

    async def poll_diff(self) -> None:
        while True:
            await asyncio.sleep(2)
            if self.diff_visible:
                self.diff_refresh.request()
                if self.diff_attachments:
                    attachments = self.diff_attachments
                    current = await asyncio.to_thread(attachment_sources, attachments)
                    if attachments == self.diff_attachments:
                        self.diff_attachment_freshness = current
                        self.app.invalidate()
                if self.diff_findings:
                    workspace = self.controller.state.workspace
                    try:
                        findings = await asyncio.to_thread(
                            retained_findings,
                            hydrate_review_entries(
                                self.controller.state.entries,
                                self.controller.load_entry,
                            ),
                        )
                    except (OSError, ValueError) as error:
                        findings = tuple(
                            f.model_copy(update={"stale": True})
                            for f in self.diff_findings
                        )
                        self.set_notice(
                            "Findings refresh failed; freshness unverified: "
                            + str(error)
                        )
                    if workspace == self.controller.state.workspace:
                        selected_key = (
                            self.diff_findings[self.diff_finding].key
                            if self.diff_finding < len(self.diff_findings)
                            else None
                        )
                        self.diff_findings = findings
                        self.diff_finding = next(
                            (
                                i
                                for i, finding in enumerate(findings)
                                if finding.key == selected_key
                            ),
                            0,
                        )
                        self.render_diff()

    def set_notice(self, text: str) -> None:
        self.notice = text[:400]
        self.app.invalidate()

    def header(self) -> str:
        state = self.controller.state
        memory = state.memory
        scopes = " / ".join(
            f"{scope} r{snapshot.document.revision}"
            if snapshot is not None
            else f"{scope} none"
            for scope, snapshot in (
                ("user", memory.user if memory else None),
                ("project", memory.project if memory else None),
            )
        )
        workspace = state.workspace
        if state.memory_disabled:
            scopes = "off"
        abbreviated = workspace if len(workspace) <= 70 else "…" + workspace[-69:]
        root = self.project_location.root_label()
        root = root if len(root) <= 70 else "…" + root[-69:]
        return display_text(
            f"Mos Eisley • recorded • {state.session_name or '(unnamed)'} • "
            f"{state.session_id[:8]} • memory {scopes}\n"
            f"Directory: {abbreviated} • /directory shows full paths\n"
            f"Project root: {root}"
        )

    def status(self) -> str:
        state = self.controller.state
        queued = sum(entry.status == "queued" for entry in state.entries)
        active = next(
            (entry for entry in state.entries if entry.status == "running"), None
        )
        phase = (
            "idle"
            if active is None
            else "reviewing"
            if active.is_review
            else "responding"
        )
        usage = sum(
            entry.usage.billed_input + entry.usage.billed_output
            for entry in state.entries
            if entry.usage is not None
        )
        pending = (
            ""
            if self.controller.pending_limits is None
            else f"{self.controller.pending_text_bytes}/"
            f"{self.controller.pending_limits.max_bytes} queued text bytes • "
        )
        pressure = pressure_status(state, self.controller.context_pressure_policy)
        pressure_text = (
            "pressure unmeasured"
            if pressure.latest_request is None
            else "pressure "
            f"{pressure.latest_request.request_usage_basis_points / 100:.1f}%"
        )
        goal = self.controller.current_goal
        goal_text = (
            ""
            if goal is None
            else (
                f" • goal {goal.status} • {goal.ledger.attempts}/"
                f"{goal.definition.ceiling.attempts} goal attempts"
            )
        )
        return (
            f" fixture/tool-reviewer-v1 • high • tools off • "
            f"{state.interaction_mode} • {phase} • "
            f"{queued} queued • {state.exchanges_consumed}/"
            f"{len(self.controller.cassette.exchanges)} attempts • "
            f"{pending}{usage} recorded bytes • {pressure_text} • "
            f"{pressure.substantial_tool_calls_since_boundary} substantial tools • "
            f"{pressure.repeated_reads_since_boundary} repeated reads {goal_text}"
        )

    def refresh(self) -> None:
        state = self.controller.state
        if self.history:
            self.history.check_revision()
            if self.history.visible:
                self.refresh_history()
                return
        parts = [
            f"Mos Eisley\nDirectory: {state.workspace}\nSession: {state.session_id}"
        ]
        if self.welcome:
            parts.append(self.welcome)
        start = max(0, len(state.entries) - 4) if self.history else 0
        if self.history:
            parts.append("Recent messages • F5 browses saved history")
        for index, entry in enumerate(state.entries[start:], start=start):
            link = (
                "" if entry.steering_for is None else f" • refines {entry.steering_for}"
            )
            mode = " • plan" if entry.interaction_mode == "plan" else ""
            parts.append(f"You [{index}] • {entry.status}{mode}{link}\n{entry.text}")
            if entry.answer is not None:
                parts.append(f"Mos\n{entry.answer}")
        if self.details:
            result = next(
                (
                    entry.review_result
                    for entry in reversed(self.controller.state.entries)
                    if entry.review_result is not None
                ),
                None,
            )
            if result is None:
                parts.append("No completed review to expand.")
            else:
                parts.append(
                    f"Latest review • {result.verdict.decision}\n"
                    f"{result.verdict.rationale}"
                )
                for finding in result.verdict.findings[:10]:
                    parts.append(
                        f"{finding.impact} • {finding.location}\n{finding.claim}\n"
                        f"Evidence: {finding.evidence.quote}\n"
                        f"{finding.evidence.explanation}"
                    )
                parts.append(
                    "Showing up to ten adjudicated findings. "
                    "The full report remains in the saved session."
                )
        if self.memory_report is not None:
            parts.append(self.memory_report)
        if self.memory_visible:
            parts.append(
                state.memory.describe()
                if state.memory is not None
                else "No memory is active in this session."
            )
        if self.directory_visible:
            parts.append(
                self.project_location.describe(state.effective_memory_workspace)
            )
        if self.review_scope_preview is not None:
            parts.append(
                "Selected review scope (rerun /review to refresh)\n"
                + self.review_scope_preview
            )
        if self.context_preview is not None:
            revision, preview = self.context_preview
            parts.append(
                preview
                if revision == state.revision
                else (
                    "Context preview is stale; run /context again."
                    if self.context_command == "/context"
                    else "Saved admission view is stale; "
                    f"run {self.context_command} again."
                )
            )
        text = display_text(
            "\n\n".join(parts)
            or (
                "Start a conversation. /review uses the selected review packet. "
                "F4 continues saved queued work."
            )
        )
        position = (
            min(self.transcript.buffer.cursor_position, len(text))
            if self.diff_visible or self.app.layout.has_focus(self.transcript)
            else len(text)
        )
        self.transcript.buffer.set_document(
            Document(text, position), bypass_readonly=True
        )
        self.app.invalidate()

    def refresh_history(self) -> None:
        history = self.history
        assert history is not None
        page = history.page
        expansion_position = 0
        if history.error:
            text = "Saved history unavailable\n" + history.error
        elif page is None:
            text = "Loading saved history… • F5 returns to live"
        else:
            parts = [
                f"Saved history • page {history.index + 1} • "
                f"{page.total_messages} messages\n"
                "PgUp/PgDn scroll, then change page • F6 reload • F5 live"
            ]
            reference_number = 0
            for entry in page.entries:
                content = entry.content
                link = (
                    ""
                    if content.steering_for is None
                    else f" • refines {content.steering_for}"
                )
                parts.append(
                    f"You [{entry.position}] • {content.status}"
                    + (" • plan" if content.interaction_mode == "plan" else "")
                    + f"{link}\n{content.text}"
                )
                if content.answer is not None:
                    parts.append(f"Mos\n{content.answer}")
                for ref in entry.artifacts:
                    marker = (
                        "→" if reference_number == history.selected_artifact else " "
                    )
                    parts.append(
                        f"{marker} Artifact {reference_number + 1}: "
                        f"{ref.field.replace('_', ' ')} • {ref.bytes} bytes • "
                        "F7 select • F8 open/close"
                    )
                    reference_number += 1
            if history.artifact_error:
                parts.append("Artifact unavailable\n" + history.artifact_error)
            elif history.expanded is not None:
                expanded = history.expanded
                expansion_position = len(display_text("\n\n".join(parts))) + 2
                parts.append(
                    f"Expanded {expanded.field.replace('_', ' ')} "
                    f"for message {expanded.position} • F8 closes\n"
                    + json.dumps(expanded.content, ensure_ascii=True, indent=2)
                )
            elif history.loading:
                parts.append("Loading selected artifact…")
            if not page.entries:
                parts.append("No saved messages yet.")
            parts.append(
                "End of saved history."
                if page.next_cursor is None
                else "More messages below."
            )
            text = "\n\n".join(parts)
        text = display_text(text)
        # A newly selected page starts at its top; redraws retain its scroll position.
        position = (
            self.transcript.buffer.cursor_position
            if text == self.transcript.text
            else expansion_position
        )
        self.transcript.buffer.set_document(
            Document(text, position), bypass_readonly=True
        )
        self.app.invalidate()

    def emit(self, event: dict[str, object]) -> None:
        if event["type"] == "conversation.diff":
            self.diff_evidence = self.diff_evidence_finding = None
            self.diff_refresh.snapshot = DiffSnapshot.model_validate_json(
                json.dumps(event["snapshot"])
            )
            self.diff_refresh.error = None
            self.diff_show_findings = False
            if event.get("toggle"):
                self.toggle_diff()
            else:
                self.diff_visible = True
                self.app.layout.focus(self.diff_pane)
            self.render_diff()
            return
        if event["type"] == "conversation.diff_attachments":
            self.diff_attachments = TypeAdapter(
                tuple[DiffAttachment, ...]
            ).validate_json(json.dumps(event["attachments"]))
            self.set_notice(str(event["text"]))
            return
        if event["type"] == "conversation.diff_attachment_sources":
            self.diff_attachment_freshness = TypeAdapter(dict[str, bool]).validate_json(
                json.dumps(event["sources"])
            )
            self.app.invalidate()
            return
        if event["type"] == "conversation.diff_findings":
            self.diff_findings = TypeAdapter(tuple[DiffFinding, ...]).validate_json(
                json.dumps(event["findings"])
            )
            self.diff_show_findings = self.diff_visible = True
            self.app.layout.focus(self.diff_pane)
            self.render_diff(reset=True)
            return
        if event["type"] == "conversation.diff_finding":
            finding = DiffFinding.model_validate_json(json.dumps(event["finding"]))
            self.diff_findings = (finding,)
            self.diff_finding = 0
            self.diff_show_findings = self.diff_visible = True
            self.app.layout.focus(self.diff_pane)
            self.render_diff(reset=True)
            return
        if event["type"] == "conversation.diff_finding_source":
            finding = DiffFinding.model_validate_json(json.dumps(event["finding"]))
            snapshot = DiffSnapshot.model_validate_json(json.dumps(event["snapshot"]))
            self.diff_evidence, self.diff_evidence_finding = snapshot, finding
            paths = [f.path for f in snapshot.scope.files]
            self.diff_selected_path = finding.path if finding.path in paths else None
            self.diff_file = paths.index(finding.path) if finding.path in paths else 0
            self.diff_show_findings = False
            self.diff_rows_offset = 0
            if finding.path in paths:
                rows = patch_lines(snapshot.scope.files[self.diff_file])
                position = next(
                    (i for i, row in enumerate(rows) if row.new == finding.start),
                    next(
                        (i for i, row in enumerate(rows) if row.old == finding.start), 0
                    ),
                )
                self.diff_rows_offset = (
                    position // MAX_RENDER_LINES
                ) * MAX_RENDER_LINES
                self.render_diff(reset=True)
                document = self.diff_pane.buffer.document
                row = self.diff_patch_header_rows + position - self.diff_rows_offset
                self.diff_pane.buffer.cursor_position = (
                    document.translate_row_col_to_index(row, 0)
                )
            else:
                self.render_diff(reset=True)
            return
        if event["type"] == "conversation.diff_lines":
            snapshot = self.diff_refresh.snapshot
            if (
                snapshot is not None
                and event["snapshot_sha256"] == snapshot.scope.scope_id
            ):
                paths = [f.path for f in snapshot.scope.files]
                path = event["path"]
                if isinstance(path, str) and path in paths:
                    self.diff_file = paths.index(path)
                    self.diff_selected_path = paths[self.diff_file]
                    offset = event["offset"]
                    assert type(offset) is int
                    self.diff_rows_offset = offset
                    self.diff_show_findings = False
                    self.render_diff(reset=True)
            return
        if event["type"] == "conversation.review_scope":
            self.review_scope_preview = str(event["text"])
            self.context_preview = None
            self.memory_visible = self.directory_visible = False
            self.memory_report = None
            self.set_notice("Frozen Git review scope shown.")
            self.refresh()
            return
        if event["type"] in {
            "conversation.context",
            "conversation.context_admission",
            "conversation.status",
        }:
            if self.history:
                self.history.close()
            revision = event["revision"]
            if type(revision) is not int:
                raise ValueError("invalid context preview revision")
            command = "/context"
            if event["type"] == "conversation.context_admission":
                position = event["message_index"]
                if type(position) is not int or not 0 <= position <= 15:
                    raise ValueError("invalid admission message position")
                command = f"/context {position}"
            elif event["type"] == "conversation.status":
                command = "/status"
            selected = (revision, str(event["text"]))
            self.context_preview = (
                None if self.context_preview == selected else selected
            )
            self.context_command = command
            self.memory_visible = self.directory_visible = False
            self.memory_report = None
            self.set_notice(f"Context report toggled. {command} shows or hides it.")
            self.refresh()
            return
        if event["type"] == "conversation.agents":
            self.context_preview = (self.controller.state.revision, str(event["text"]))
            self.context_command = "/agent"
            self.memory_visible = self.directory_visible = False
            self.memory_report = None
            self.set_notice(
                "Agent inspection shown; creator retains integration ownership."
            )
            self.refresh()
            return
        if event["type"] in {
            "conversation.fork",
            "conversation.side",
            "conversation.branches",
        }:
            self.context_preview = (self.controller.state.revision, str(event["text"]))
            self.context_command = "/side status"
            self.memory_visible = self.directory_visible = False
            self.memory_report = None
            self.set_notice(
                "Fork/side report shown; context enters the author "
                "only by explicit selection."
            )
            self.refresh()
            return
        if event["type"] == "conversation.goal":
            self.context_preview = (self.controller.state.revision, str(event["text"]))
            self.context_command = "/goal status"
            self.memory_visible = self.directory_visible = False
            self.memory_report = None
            self.set_notice("Goal status shown; /goal status refreshes it.")
            self.refresh()
            return
        if event["type"] in {
            "conversation.memory.inspected",
            "conversation.memory.saved",
            "conversation.memory.forget.preview",
            "conversation.memory.forget.saved",
            "conversation.memory.forget.discarded",
            "conversation.memory.replace.preview",
            "conversation.memory.replace.saved",
            "conversation.memory.replace.discarded",
            "conversation.memory.proposal.preview",
            "conversation.memory.proposal.saved",
            "conversation.memory.proposal.discarded",
        }:
            if self.history:
                self.history.close()
            self.memory_report = "Saved memory receipt (rerun to refresh)\n" + str(
                event["text"]
            )
            self.memory_visible = self.directory_visible = False
            self.context_preview = None
            self.set_notice(
                "Saved memory receipt shown. /memory shows active session memory."
            )
            self.refresh()
            return
        if event["type"] == "conversation.memory":
            if self.history:
                self.history.close()
            self.memory_visible = not self.memory_visible
            self.memory_report = None
            self.directory_visible = False
            self.context_preview = None
            self.set_notice(
                "Memory details shown. /memory hides them."
                if self.memory_visible
                else "Memory details hidden."
            )
            self.refresh()
            return
        if event["type"] == "conversation.directory":
            if self.history:
                self.history.close()
            self.directory_visible = not self.directory_visible
            self.memory_visible = False
            self.memory_report = None
            self.context_preview = None
            self.set_notice(
                "Directory details toggled. /directory shows or hides them."
            )
            self.refresh()
            return
        if str(event["type"]).startswith("conversation."):
            self.set_notice(str(event.get("text", "")))
        self.refresh()

    def control(self, command: str, *, priority: bool = False) -> bool:
        if self.directory_target is not None:
            return False
        if priority:
            if self.submission is not None:
                self.submission.cancel()
            self.sending = False
            self.editor.clear()
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if isinstance(item, ConversationSubmission):
                    item.accepted.cancel()
        try:
            self.queue.put_nowait(command)
            self.set_notice(f"{command} requested.")
            return True
        except asyncio.QueueFull:
            self.set_notice(
                "Input queue is full; try again after pending input is handled."
            )
            return False

    def send(self, *, literal: bool = False) -> None:
        if self.sending:
            return
        text = self.editor.text
        if self.editor.invalid:
            self.set_notice(
                "An edit exceeded the draft limits. Ctrl-U clears the draft."
            )
            return
        if not text.strip():
            return
        literal = literal or self.editor.literal or "\n" in text
        if not literal and text.startswith("/") and submission_command(text) is None:
            if text in {"/compose", "/send", "/discard"}:
                self.set_notice(
                    "Use Enter to send, Alt-Enter for a newline, and Ctrl-U to discard."
                )
                return
            if self.control(text, priority=text in {"/stop", "/quit"}):
                self.editor.clear()
            return
        if self.queue.full():
            self.set_notice("Input queue is full; draft retained.")
            return
        self.sending = True
        self.submission = asyncio.create_task(self.submit(text, literal))

    async def submit(self, text: str, literal: bool) -> None:
        accepted: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        try:
            attachments = self.diff_attachments
            self.queue.put_nowait(
                ConversationSubmission(text, literal, accepted, attachments)
            )
            if await accepted and self.editor.text == text:
                self.editor.clear()
                if self.diff_attachments == attachments:
                    self.diff_attachments = ()
                if not literal and memory_phrase_command(text) is not None:
                    return
                self.set_notice(
                    "Message queued. Enter sends • Alt-Enter adds a line • "
                    "Ctrl-C stops • Ctrl-D quits"
                )
        except asyncio.QueueFull:
            self.set_notice("Input queue is full; draft retained.")
        except asyncio.CancelledError:
            accepted.cancel()
        finally:
            self.sending = False
            self.app.invalidate()

    async def switch_directory(self, text: str) -> bool:
        if (
            self.editor.text
            or self.diff_attachments
            or self.sending
            or not self.queue.empty()
        ):
            self.set_notice(
                "Handle the unsent draft and pending input before switching."
            )
            return False
        self.sending = True
        try:
            workspace = Path(self.controller.state.workspace)
            selected = switch_target(text, workspace)
            if selected is None:
                with set_app(self.app):
                    async with in_terminal():
                        selected = await DirectoryPicker(
                            workspace,
                            base=workspace,
                            memory_resolver=self.memory_resolver,
                            input=self.app.input,
                            output=self.app.output,
                        ).app.run_async(set_exception_handler=False)
            if selected is None:
                self.set_notice("Directory switch cancelled. Queued work stays paused.")
                return False
            selected.verify()
            if self.memory_resolver is not None:
                self.memory_resolver(selected.path)
            if selected.path == workspace:
                self.set_notice("Already in that directory. Queued work stays paused.")
                return False
            if not self.queue.empty():
                self.set_notice(
                    "Input arrived during selection; handle it before switching."
                )
                return False
            self.directory_target = selected
            self.set_notice(
                "Switching directory. This session and its queue remain saved."
            )
            return True
        except DirectorySelectionError as error:
            self.set_notice(str(error))
            return False
        finally:
            self.sending = self.directory_target is not None
            self.app.invalidate()

    async def run(self) -> None:
        self.diff_poll = asyncio.create_task(self.poll_diff())
        worker = asyncio.create_task(
            terminal(
                self.controller,
                self.queue,
                self.emit,
                self.review_packet,
                self.refresh_memory,
                memory_command=self.memory_command,
                initial_prompt=self.initial_prompt,
                project_location=self.project_location,
                source_attachments=lambda: self.diff_attachments,
                source_snapshot=lambda: self.diff_refresh.snapshot,
                switch_directory=self.switch_directory
                if self.allow_directory_switch
                else None,
            )
        )
        screen = asyncio.create_task(self.app.run_async(set_exception_handler=False))
        try:
            done, _ = await asyncio.wait(
                {worker, screen}, return_when=asyncio.FIRST_COMPLETED
            )
            if worker in done:
                await worker
                if self.app.is_running:
                    self.app.exit()
                await screen
            else:
                with suppress(EOFError):
                    await screen
                self.control("/quit", priority=True)
                await worker
        finally:
            self.diff_refresh.close()
            for task in (worker, screen, self.submission, self.diff_poll):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                worker,
                screen,
                *([self.submission] if self.submission is not None else []),
                self.diff_poll,
                return_exceptions=True,
            )
            self.editor.clear()
            if self.history:
                await self.history.shutdown()
