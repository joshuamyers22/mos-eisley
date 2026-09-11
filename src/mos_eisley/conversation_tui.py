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
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.output import Output
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_cli import terminal
from mos_eisley.conversation_directory import (
    DirectoryPicker,
    DirectorySelection,
    DirectorySelectionError,
)
from mos_eisley.conversation_history import TranscriptHistory
from mos_eisley.conversation_input import (
    ConversationInput,
    ConversationSubmission,
    submission_command,
)
from mos_eisley.conversation_project import ProjectLocation
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
        self.directory_visible = False
        self.context_preview: tuple[int, str] | None = None
        self.context_command = "/context"
        self.submission: asyncio.Task[None] | None = None
        self.editor = EditorBuffer(self.set_notice, lambda: self.sending)
        self.transcript = TextArea(read_only=True, scrollbar=True, wrap_lines=True)
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
                self.set_notice("Unsent draft discarded.")

        def focus(event: KeyPressEvent) -> None:
            self.app.layout.focus(
                self.editor_control
                if self.app.layout.has_focus(self.transcript)
                else self.transcript
            )

        def previous_page(event: KeyPressEvent) -> None:
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

        layout = HSplit(
            [
                Window(
                    FormattedTextControl(self.header),
                    height=3,
                    style="class:title",
                ),
                Frame(
                    self.transcript,
                    title="Conversation • Tab / PgUp / PgDn • F3 review • F5 history",
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
        )
        self.refresh()

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
        return (
            f" fixture/tool-reviewer-v1 • high • tools off • {phase} • "
            f"{queued} queued • {state.exchanges_consumed}/"
            f"{len(self.controller.cassette.exchanges)} attempts • "
            f"{pending}{usage} recorded bytes "
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
            if self.app.layout.has_focus(self.transcript)
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
        if event["type"] in {"conversation.context", "conversation.context_admission"}:
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
            selected = (revision, str(event["text"]))
            self.context_preview = (
                None if self.context_preview == selected else selected
            )
            self.context_command = command
            self.memory_visible = self.directory_visible = False
            self.set_notice(f"Context report toggled. {command} shows or hides it.")
            self.refresh()
            return
        if event["type"] == "conversation.memory":
            if self.history:
                self.history.close()
            self.memory_visible = not self.memory_visible
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
            self.queue.put_nowait(ConversationSubmission(text, literal, accepted))
            if await accepted and self.editor.text == text:
                self.editor.clear()
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
        if self.editor.text or self.sending or not self.queue.empty():
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
        worker = asyncio.create_task(
            terminal(
                self.controller,
                self.queue,
                self.emit,
                self.review_packet,
                self.refresh_memory,
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
            for task in (worker, screen, self.submission):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                worker,
                screen,
                *([self.submission] if self.submission is not None else []),
                return_exceptions=True,
            )
            self.editor.clear()
            if self.history:
                await self.history.shutdown()
