"""Full-screen conversation; execution stays in the shared terminal."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer, VSplit
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.output import Output
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_cli import terminal
from mos_eisley.conversation_context_preview import pressure_status
from mos_eisley.conversation_diff_attachment import (
    MAX_ATTACHMENTS,
    DiffAttachment,
    DiffAttachmentError,
    attached_prompt,
    select_patch_lines,
)
from mos_eisley.conversation_diff_panel import (
    RENDER_LINE_LIMITS,
    DiffItem,
    inventory_text,
    items,
    patch_text,
)
from mos_eisley.conversation_directory import (
    DirectoryPicker,
    DirectorySelection,
    DirectorySelectionError,
)
from mos_eisley.conversation_git import (
    GitReadError,
    GitSnapshot,
    GitWorkspaceReader,
    Patch,
)
from mos_eisley.conversation_history import TranscriptHistory
from mos_eisley.conversation_input import (
    ConversationInput,
    ConversationSubmission,
    submission_command,
)
from mos_eisley.conversation_project import ProjectLocation
from mos_eisley.conversation_remember import memory_phrase_command
from mos_eisley.conversation_review import ConversationLiveReviewPacket, ReviewPacket
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
        review_packet: ReviewPacket | None = None,
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
        git_executable: Path = Path("/usr/bin/git"),
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
        self.git_executable = git_executable
        self.diff_visible = False
        self.diff_generation = 0
        self.diff_task: asyncio.Task[None] | None = None
        self.diff_wakeup = asyncio.Event()
        self.diff_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="mos-diff"
        )
        self.diff_snapshot: GitSnapshot | None = None
        self.diff_items: tuple[DiffItem, ...] = ()
        self.diff_selected = 0
        self.diff_patch: Patch | None = None
        self.diff_error: str | None = None
        self.diff_loading = False
        self.diff_limit_index = 0
        self.diff_attachments: list[DiffAttachment] = []
        self.attachment_send_review: (
            tuple[str, tuple[DiffAttachment, ...], str] | None
        ) = None
        self.context_preview: tuple[int, str] | None = None
        self.review_scope_preview: str | None = None
        self.context_command = "/context"
        self.submission: asyncio.Task[None] | None = None
        self.editor = EditorBuffer(self.set_notice, lambda: self.sending)
        self.transcript = TextArea(read_only=True, scrollbar=True, wrap_lines=True)
        self.diff_files = TextArea(read_only=True, scrollbar=True, wrap_lines=False)
        self.diff_content = TextArea(read_only=True, scrollbar=True, wrap_lines=False)
        self.attachment_review = TextArea(
            read_only=True, scrollbar=True, wrap_lines=True
        )
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
            if self.editor.text or self.diff_attachments or self.sending:
                self.set_notice("Send or discard the unsent draft before switching.")
            else:
                self.control(SWITCH_COMMAND)

        def clear(event: KeyPressEvent) -> None:
            if not self.sending:
                self.editor.clear()
                self.diff_attachments.clear()
                self.attachment_send_review = None
                self.app.layout.focus(self.editor_control)
                self.restart_diff_poll()
                self.set_notice("Unsent draft discarded.")

        def focus(event: KeyPressEvent) -> None:
            if self.attachment_send_review is not None:
                targets: list[BufferControl | TextArea] = [
                    self.editor_control,
                    self.attachment_review,
                ]
                target = 0 if self.app.layout.has_focus(self.attachment_review) else 1
                self.app.layout.focus(targets[target])
                return
            targets: list[BufferControl | TextArea] = [self.editor_control]
            if not self.diff_visible or self.app.output.get_size().columns >= 110:
                targets.append(self.transcript)
            if self.diff_visible:
                targets.extend((self.diff_files, self.diff_content))
            current = next(
                (
                    index
                    for index, target in enumerate(targets)
                    if self.app.layout.has_focus(target)
                ),
                -1,
            )
            self.app.layout.focus(targets[(current + 1) % len(targets)])

        def previous_page(event: KeyPressEvent) -> None:
            if self.attachment_send_review is not None:
                self.app.layout.focus(self.attachment_review)
                self.attachment_review.buffer.cursor_up(count=10)
                return
            if self.diff_visible and self.app.layout.has_focus(self.diff_content):
                self.diff_content.buffer.cursor_up(count=10)
                return
            if self.diff_visible and self.app.layout.has_focus(self.diff_files):
                self.move_diff_selection(-10)
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
            if self.attachment_send_review is not None:
                self.app.layout.focus(self.attachment_review)
                self.attachment_review.buffer.cursor_down(count=10)
                return
            if self.diff_visible and self.app.layout.has_focus(self.diff_content):
                self.diff_content.buffer.cursor_down(count=10)
                return
            if self.diff_visible and self.app.layout.has_focus(self.diff_files):
                self.move_diff_selection(10)
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

        def toggle_diff(event: KeyPressEvent) -> None:
            self.toggle_diff()

        def move_diff_up(event: KeyPressEvent) -> None:
            self.move_diff_selection(-1)

        def move_diff_down(event: KeyPressEvent) -> None:
            self.move_diff_selection(1)

        def expand_diff(event: KeyPressEvent) -> None:
            self.diff_limit_index = min(
                self.diff_limit_index + 1, len(RENDER_LINE_LIMITS) - 1
            )
            self.render_diff()

        def attach_diff(event: KeyPressEvent) -> None:
            self.attach_diff_selection()

        def remove_attachment(event: KeyPressEvent) -> None:
            if self.sending:
                return
            if self.diff_attachments:
                self.diff_attachments.pop()
                self.cancel_attachment_review()
                self.restart_diff_poll()
                self.set_notice("Latest diff excerpt removed from the draft.")
            else:
                self.set_notice("No diff excerpt is attached.")

        def confirm_attachment_send(event: KeyPressEvent) -> None:
            self.send(literal=True)

        def cancel_attachment_send(event: KeyPressEvent) -> None:
            self.cancel_attachment_review()

        def extend_diff_up(event: KeyPressEvent) -> None:
            if self.diff_content.buffer.selection_state is None:
                self.diff_content.buffer.start_selection()
            self.diff_content.buffer.cursor_up()

        def extend_diff_down(event: KeyPressEvent) -> None:
            if self.diff_content.buffer.selection_state is None:
                self.diff_content.buffer.start_selection()
            self.diff_content.buffer.cursor_down()

        keys.add(
            "enter",
            filter=Condition(lambda: self.app.layout.has_focus(self.editor_control)),
        )(send)
        keys.add(
            "enter",
            filter=Condition(
                lambda: (
                    self.attachment_send_review is not None
                    and self.app.layout.has_focus(self.attachment_review)
                )
            ),
        )(confirm_attachment_send)
        keys.add("escape", "enter")(newline)
        keys.add("c-j")(newline)
        keys.add("c-s")(literal_send)
        keys.add(Keys.BracketedPaste)(paste)
        keys.add("c-c")(stop)
        keys.add(Keys.SIGINT)(stop)
        keys.add("c-d")(quit_session)
        keys.add("c-u")(clear)
        keys.add(
            "c-g", filter=Condition(lambda: self.attachment_send_review is not None)
        )(cancel_attachment_send)
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
        keys.add("f11", filter=Condition(lambda: self.diff_visible))(expand_diff)
        keys.add("f12", filter=Condition(lambda: self.diff_visible))(attach_diff)
        keys.add("c-x")(remove_attachment)
        keys.add(
            "s-up",
            filter=Condition(lambda: self.app.layout.has_focus(self.diff_content)),
        )(extend_diff_up)
        keys.add(
            "s-down",
            filter=Condition(lambda: self.app.layout.has_focus(self.diff_content)),
        )(extend_diff_down)
        keys.add(
            "up", filter=Condition(lambda: self.app.layout.has_focus(self.diff_files))
        )(move_diff_up)
        keys.add(
            "down", filter=Condition(lambda: self.app.layout.has_focus(self.diff_files))
        )(move_diff_down)

        layout = HSplit(
            [
                Window(
                    FormattedTextControl(self.header),
                    height=3,
                    style="class:title",
                ),
                VSplit(
                    [
                        ConditionalContainer(
                            Frame(
                                self.transcript,
                                title="Conversation • Tab / PgUp / PgDn • F5 history",
                            ),
                            filter=Condition(
                                lambda: (
                                    self.attachment_send_review is None
                                    and (
                                        not self.diff_visible
                                        or self.app.output.get_size().columns >= 110
                                    )
                                )
                            ),
                        ),
                        ConditionalContainer(
                            HSplit(
                                [
                                    Frame(
                                        self.diff_files,
                                        title="Changed files • ↑/↓ select • Tab focus",
                                    ),
                                    Frame(
                                        self.diff_content,
                                        title="Patch • F11 expand • F12 attach",
                                    ),
                                ]
                            ),
                            filter=Condition(
                                lambda: (
                                    self.attachment_send_review is None
                                    and self.diff_visible
                                )
                            ),
                        ),
                        ConditionalContainer(
                            Frame(
                                self.attachment_review,
                                title="Diff send review • Enter queue • Ctrl-G back",
                            ),
                            filter=Condition(
                                lambda: self.attachment_send_review is not None
                            ),
                        ),
                    ],
                    padding=1,
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
                ConditionalContainer(
                    Window(
                        FormattedTextControl(self.attachment_preview),
                        height=Dimension(min=2, preferred=8, max=8),
                        wrap_lines=True,
                    ),
                    filter=Condition(lambda: bool(self.diff_attachments)),
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
        self.render_diff()
        self.refresh()

    def set_notice(self, text: str) -> None:
        self.notice = text[:400]
        self.app.invalidate()

    def restart_diff_poll(self) -> None:
        self.diff_generation += 1
        self.diff_wakeup.set()
        if (self.diff_visible or self.diff_attachments) and (
            self.diff_task is None or self.diff_task.done()
        ):
            self.diff_task = asyncio.create_task(self.poll_diff())
        self.app.invalidate()

    def attachment_destination(self) -> str:
        session = self.controller.state.session_id
        live = self.controller.state.live_chat
        if live is None:
            mode = "Recorded local chat (fixture; no live provider)"
            return f"{mode} • session {session}"
        return (
            f"OpenAI live chat • model {live.model} • effort {live.effort} "
            f"• session {session}"
        )

    def attachment_send_preview(
        self,
        text: str,
        attachments: tuple[DiffAttachment, ...],
        destination: str,
    ) -> str:
        lines = [
            f"Destination: {destination}",
            "Queues one chat message. Diff text is untrusted source data.",
            "No Git edit, tool, review, provider choice, or new spend authority.",
            "Live dispatch still requires its separately selected policy and cap.",
            "",
            "Message (exact JSON string; escapes show controls and line endings):",
            json.dumps(text, ensure_ascii=True),
            "",
            "Frozen diff excerpts sent with that message:",
        ]
        for index, item in enumerate(attachments, 1):
            lines.extend(
                (
                    f"{index}. workspace "
                    + json.dumps(item.workspace, ensure_ascii=True),
                    "   path "
                    + json.dumps(item.path, ensure_ascii=True)
                    + f" • {item.basis.value}",
                    f"   snapshot {item.snapshot_digest}",
                    "   excerpt (exact JSON string):",
                    "   " + json.dumps(item.excerpt, ensure_ascii=True),
                    "",
                )
            )
        return display_text("\n".join(lines))

    def cancel_attachment_review(self) -> None:
        if self.attachment_send_review is None:
            return
        self.attachment_send_review = None
        self.app.layout.focus(self.editor_control)
        self.set_notice("Diff send review cancelled; draft and excerpts retained.")

    def attachment_preview(self) -> str:
        lines = [
            "Diff excerpts • Enter reviews bytes/destination • Ctrl-X removes latest"
        ]
        if self.diff_attachments:
            lines.append("Workspace: " + self.diff_attachments[0].workspace)
        for index, item in enumerate(self.diff_attachments, 1):
            state = (
                "changed"
                if self.diff_snapshot is not None
                and self.diff_snapshot.digest != item.snapshot_digest
                else "unverified"
                if self.diff_error is not None or self.diff_snapshot is None
                else "current"
            )
            old = "—" if item.old_start is None else f"{item.old_start}-{item.old_end}"
            new = "—" if item.new_start is None else f"{item.new_start}-{item.new_end}"
            lines.append(
                f"{index}. {item.path} • {item.basis.value} "
                f"old {old} new {new} • {state}"
            )
            lines.append(f"   snapshot {item.snapshot_digest}")
        return display_text("\n".join(lines))

    def attach_diff_selection(self) -> None:
        if not self.app.layout.has_focus(self.diff_content):
            self.set_notice("Focus the patch, select lines, then press F12.")
            return
        if len(self.diff_attachments) >= MAX_ATTACHMENTS:
            self.set_notice("At most three diff excerpts can be attached.")
            return
        if self.diff_error or self.diff_snapshot is None or self.diff_patch is None:
            self.set_notice("Wait for a current bounded patch before attaching lines.")
            return
        document = self.diff_content.buffer.document
        if self.diff_content.buffer.selection_state is None:
            first = last = document.cursor_position_row
        else:
            start, end = document.selection_range()
            first = document.translate_index_to_position(start)[0]
            last = document.translate_index_to_position(max(start, end - 1))[0]
        try:
            attachment = select_patch_lines(
                self.diff_snapshot,
                self.diff_patch,
                first,
                last,
                visible_lines=RENDER_LINE_LIMITS[self.diff_limit_index],
            )
        except DiffAttachmentError as error:
            self.set_notice(str(error))
            return
        if attachment in self.diff_attachments:
            self.set_notice("Those diff lines are already attached.")
            return
        self.diff_attachments.append(attachment)
        self.diff_content.buffer.exit_selection()
        self.set_notice(
            "Frozen diff lines attached. Ctrl-X removes the latest excerpt."
        )

    def toggle_diff(self) -> None:
        self.diff_visible = not self.diff_visible
        if self.diff_visible:
            self.diff_loading = True
            self.diff_error = None
            self.set_notice("Diff panel open. F10 closes; Tab moves between panes.")
        else:
            if self.app.layout.has_focus(self.diff_files) or self.app.layout.has_focus(
                self.diff_content
            ):
                self.app.layout.focus(self.editor_control)
            self.set_notice(
                "Diff panel closed. Draft and conversation remain available."
            )
        self.restart_diff_poll()
        self.render_diff()

    def move_diff_selection(self, offset: int) -> None:
        if not self.diff_items:
            return
        selected = max(0, min(self.diff_selected + offset, len(self.diff_items) - 1))
        if selected == self.diff_selected:
            return
        self.diff_selected = selected
        self.diff_patch = None
        self.diff_error = None
        self.diff_limit_index = 0
        self.diff_wakeup.set()
        self.render_diff()

    def render_diff(self) -> None:
        if self.diff_error:
            prefix = "Refresh failed; displayed inventory is stale. " + self.diff_error
        elif self.diff_loading:
            prefix = "Refreshing Git inventory…"
        else:
            prefix = ""
        if self.diff_snapshot is None:
            inventory = prefix or "Open /diff to inspect the selected directory."
        else:
            inventory = "\n".join(
                part
                for part in (
                    prefix,
                    inventory_text(
                        self.diff_snapshot, self.diff_items, self.diff_selected
                    ),
                )
                if part
            )
        inventory = display_text(inventory)
        cursor = min(self.diff_files.buffer.cursor_position, len(inventory))
        if self.diff_items:
            # Keep the selected entry visible after keyboard navigation.
            cursor = len("\n".join(inventory.splitlines()[: self.diff_selected + 3]))
            cursor = min(cursor, len(inventory))
        if inventory != self.diff_files.text:
            self.diff_files.buffer.set_document(
                Document(inventory, cursor), bypass_readonly=True
            )
        selected = self.diff_items[self.diff_selected] if self.diff_items else None
        patch = (
            self.diff_patch
            if selected is not None
            and self.diff_patch is not None
            and self.diff_patch.path == selected.change.path
            and self.diff_patch.basis == selected.basis
            else None
        )
        content = display_text(patch_text(patch, selected, self.diff_limit_index))
        if self.diff_error:
            content = "STALE — " + self.diff_error + "\n\n" + content
        elif self.diff_loading and patch is None:
            content = "Refreshing…\n\n" + content
        position = (
            self.diff_content.buffer.cursor_position
            if content == self.diff_content.text
            else 0
        )
        if content != self.diff_content.text:
            self.diff_content.buffer.set_document(
                Document(content, position), bypass_readonly=True
            )
        self.app.invalidate()

    def _read_diff_snapshot(
        self, workspace: Path
    ) -> tuple[GitWorkspaceReader, GitSnapshot]:
        selection = DirectorySelection.inspect(workspace)
        reader = GitWorkspaceReader(selection, self.git_executable)
        return reader, reader.snapshot()

    async def poll_diff(self) -> None:
        try:
            while (self.diff_visible or self.diff_attachments) and (
                self.directory_target is None
            ):
                generation = self.diff_generation
                workspace = Path(self.controller.state.workspace)
                self.diff_wakeup.clear()
                try:
                    reader, snapshot = await asyncio.get_running_loop().run_in_executor(
                        self.diff_executor, self._read_diff_snapshot, workspace
                    )
                    if not self._diff_current(generation, workspace):
                        continue
                    previous = (
                        self.diff_items[self.diff_selected].key
                        if self.diff_items
                        else None
                    )
                    old_digest = (
                        None
                        if self.diff_snapshot is None
                        else self.diff_snapshot.digest
                    )
                    old_patch = self.diff_patch
                    self.diff_snapshot = snapshot
                    self.diff_items = items(snapshot)
                    self.diff_selected = next(
                        (
                            index
                            for index, item in enumerate(self.diff_items)
                            if item.key == previous
                        ),
                        0,
                    )
                    selected = (
                        self.diff_items[self.diff_selected] if self.diff_items else None
                    )
                    self.diff_patch = (
                        old_patch
                        if selected is not None
                        and old_patch is not None
                        and old_digest == snapshot.digest
                        and old_patch.path == selected.change.path
                        and old_patch.basis == selected.basis
                        else None
                    )
                    self.diff_error = None
                    self.diff_loading = False
                    self.render_diff()
                    if self.diff_visible and selected is not None:
                        item = selected
                        basis = item.basis
                        if basis is not None and self.diff_patch is None:
                            patch = await asyncio.get_running_loop().run_in_executor(
                                self.diff_executor,
                                reader.patch,
                                snapshot,
                                item.change.path,
                                basis,
                            )
                            if not self._diff_current(generation, workspace):
                                continue
                            if self.diff_items[self.diff_selected].key == item.key:
                                self.diff_patch = patch
                                self.render_diff()
                except (GitReadError, DirectorySelectionError) as error:
                    if not self._diff_current(generation, workspace):
                        continue
                    self.diff_error = str(error)
                    self.diff_loading = False
                    self.render_diff()
                with suppress(TimeoutError):
                    await asyncio.wait_for(self.diff_wakeup.wait(), timeout=2.0)
        except asyncio.CancelledError:
            return
        finally:
            if self.diff_task is asyncio.current_task():
                self.diff_task = None

    def _diff_current(self, generation: int, workspace: Path) -> bool:
        return (
            (self.diff_visible or bool(self.diff_attachments))
            and generation == self.diff_generation
            and self.directory_target is None
            and Path(self.controller.state.workspace) == workspace
        )

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
        mode = (
            "live OpenAI chat"
            if state.mode == "openai_live_conversation"
            else "recorded chat / live review"
            if isinstance(self.review_packet, ConversationLiveReviewPacket)
            else "recorded"
        )
        inspection = (
            "\n/inspect QUESTION permits bounded source reads to OpenAI"
            if state.live_chat is not None and state.live_chat.repository_read
            else ""
        )
        return display_text(
            f"Mos Eisley • {mode} • {state.session_name or '(unnamed)'} • "
            f"{state.session_id[:8]} • memory {scopes}\n"
            f"Directory: {abbreviated} • /directory shows full paths\n"
            f"Project root: {root}{inspection}"
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
        live = state.live_chat
        model = (
            f"openai/{live.model} • {live.effort}"
            if live is not None
            else "fixture/tool-reviewer-v1 • high"
        )
        attempts = (
            f"{state.exchanges_consumed} attempts"
            if live is not None
            else (
                f"{state.exchanges_consumed}/"
                f"{len(self.controller.cassette.exchanges)} attempts"
            )
        )
        unit = "tokens" if live is not None else "recorded bytes"
        goal = self.controller.current_goal
        goal_text = "" if goal is None else f" • goal {goal.status}"
        return (
            f" {model} • tools off • {phase} • "
            f"{state.interaction_mode} • {queued} queued • {attempts}{goal_text} • "
            f"{pending}{usage} {unit} • {pressure_text} • "
            f"{pressure.substantial_tool_calls_since_boundary} substantial tools • "
            f"{pressure.repeated_reads_since_boundary} repeated reads "
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
            if entry.interaction_mode == "plan":
                link += " • plan"
            if entry.repository_inspection:
                link += " • repository inspection"
            parts.append(f"You [{index}] • {entry.status}{link}\n{entry.text}")
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
            parts.append(self.review_scope_preview)
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
            if self.app.layout.has_focus(self.transcript) or self.diff_visible
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
                    f"You [{entry.position}] • {content.status}{link}\n{content.text}"
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
        if event["type"] == "conversation.update":
            self.set_notice(str(event["text"]))
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
        if event["type"] == "conversation.loop":
            self.context_preview = (self.controller.state.revision, str(event["text"]))
            self.context_command = "/loop status"
            self.memory_visible = self.directory_visible = False
            self.memory_report = None
            self.set_notice(
                "Loop report shown; timers require an active recorded session."
            )
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
            self.diff_attachments.clear()
            self.attachment_send_review = None
            self.app.layout.focus(self.editor_control)
            self.restart_diff_poll()
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
            if self.diff_attachments:
                self.set_notice("Write a message before sending diff excerpts.")
            return
        literal = literal or self.editor.literal or "\n" in text
        if self.diff_attachments and text.startswith("/") and not literal:
            self.set_notice(
                "Diff excerpts accompany a normal message. "
                "Remove them before a slash command."
            )
            return
        if not literal and text.startswith("/") and submission_command(text) is None:
            if text == "/diff":
                self.editor.clear()
                self.toggle_diff()
                return
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
        attachments = tuple(self.diff_attachments)
        if attachments:
            try:
                attached_prompt(text, attachments)
            except DiffAttachmentError as error:
                self.set_notice(str(error))
                return
            literal = True
            destination = self.attachment_destination()
            review = (text, attachments, destination)
            if self.attachment_send_review != review:
                self.attachment_send_review = review
                self.attachment_review.buffer.set_document(
                    Document(
                        self.attachment_send_preview(text, attachments, destination),
                        0,
                    ),
                    bypass_readonly=True,
                )
                self.app.layout.focus(self.attachment_review)
                self.set_notice(
                    "Review exact diff excerpts and destination. "
                    "Enter queues; Ctrl-G returns to draft."
                )
                return
            self.attachment_send_review = None
            self.app.layout.focus(self.editor_control)
        else:
            self.attachment_send_review = None
        self.sending = True
        self.submission = asyncio.create_task(self.submit(text, literal, attachments))

    async def submit(
        self,
        text: str,
        literal: bool,
        attachments: tuple[DiffAttachment, ...] = (),
    ) -> None:
        accepted: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        try:
            if attachments:
                workspace = Path(self.controller.state.workspace)

                def current_source() -> tuple[GitSnapshot, tuple[str, ...]]:
                    selection = DirectorySelection.inspect(workspace)
                    reader = GitWorkspaceReader(selection, self.git_executable)
                    snapshot = reader.snapshot()
                    patches = tuple(
                        reader.patch(snapshot, item.path, item.basis)
                        for item in attachments
                    )
                    return snapshot, tuple(patch.digest for patch in patches)

                try:
                    (
                        snapshot,
                        patch_digests,
                    ) = await asyncio.get_running_loop().run_in_executor(
                        self.diff_executor, current_source
                    )
                except (GitReadError, DirectorySelectionError):
                    self.set_notice(
                        "Could not verify diff excerpts. "
                        "Draft retained; retry after refresh."
                    )
                    return
                if any(
                    item.workspace != str(workspace)
                    or item.snapshot_digest != snapshot.digest
                    or item.patch_digest != patch_digest
                    for item, patch_digest in zip(
                        attachments, patch_digests, strict=True
                    )
                ):
                    self.diff_snapshot = snapshot
                    self.diff_patch = None
                    self.diff_error = "Diff source changed."
                    self.diff_wakeup.set()
                    self.render_diff()
                    self.set_notice(
                        "Diff source changed. Remove and reselect "
                        "stale excerpts before sending."
                    )
                    return
            self.queue.put_nowait(
                ConversationSubmission(text, literal, accepted, attachments)
            )
            if await accepted and self.editor.text == text:
                self.editor.clear()
                if attachments and tuple(self.diff_attachments) == attachments:
                    self.diff_attachments.clear()
                    self.restart_diff_poll()
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
            self.diff_generation += 1
            self.diff_visible = False
            self.diff_wakeup.set()
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
            self.diff_generation += 1
            if self.diff_task is not None:
                self.diff_task.cancel()
                await asyncio.gather(self.diff_task, return_exceptions=True)
                self.diff_task = None
            for task in (worker, screen, self.submission):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                worker,
                screen,
                *([self.submission] if self.submission is not None else []),
                return_exceptions=True,
            )
            self.diff_executor.shutdown(wait=False, cancel_futures=True)
            self.editor.clear()
            self.diff_attachments.clear()
            self.attachment_send_review = None
            if self.history:
                await self.history.shutdown()
