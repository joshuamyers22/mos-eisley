"""Full-screen recorded conversation; execution stays in the shared terminal."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress

from prompt_toolkit.application import Application
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

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import terminal
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_review import ConversationReviewPacket


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
        controller: ConversationController,
        review_packet: ConversationReviewPacket | None = None,
        *,
        welcome: str = "",
        input: Input | None = None,
        output: Output | None = None,
    ) -> None:
        self.controller = controller
        self.review_packet = review_packet
        self.welcome = welcome
        self.queue: asyncio.Queue[ConversationInput] = asyncio.Queue(maxsize=32)
        self.notice = (
            "Enter sends • Alt-Enter adds a line • Ctrl-C stops • Ctrl-D quits"
        )
        self.sending = False
        self.details = False
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
            self.transcript.buffer.cursor_up(count=10)

        def next_page(event: KeyPressEvent) -> None:
            self.app.layout.focus(self.transcript)
            self.transcript.buffer.cursor_down(count=10)

        def details(event: KeyPressEvent) -> None:
            self.details = not self.details
            self.refresh()

        def continue_work(event: KeyPressEvent) -> None:
            self.control("/continue")

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

        layout = HSplit(
            [
                Window(
                    FormattedTextControl(
                        lambda: display_text(
                            "Mos Eisley • recorded conversation • "
                            f"{controller.state.session_id[:8]}"
                        )
                    ),
                    height=1,
                    style="class:title",
                ),
                Frame(
                    self.transcript,
                    title="Conversation • Tab / PgUp / PgDn • F3 review details",
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
            if active.review_packet
            else "responding"
        )
        usage = sum(
            entry.usage.billed_input + entry.usage.billed_output
            for entry in state.entries
            if entry.usage is not None
        )
        return (
            f" fixture/tool-reviewer-v1 • high • tools off • {phase} • "
            f"{queued} queued • {state.exchanges_consumed}/"
            f"{len(self.controller.cassette.exchanges)} attempts • "
            f"{usage} recorded bytes "
        )

    def refresh(self) -> None:
        state = self.controller.state
        parts = [
            f"Mos Eisley\nDirectory: {state.workspace}\nSession: {state.session_id}"
        ]
        if self.welcome:
            parts.append(self.welcome)
        for index, entry in enumerate(self.controller.state.entries):
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

    def emit(self, event: dict[str, object]) -> None:
        if str(event["type"]).startswith("conversation."):
            self.set_notice(str(event.get("text", "")))
        self.refresh()

    def control(self, command: str, *, priority: bool = False) -> bool:
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
        if not literal and text.startswith("/"):
            if text in {"/compose", "/send", "/discard"}:
                self.set_notice(
                    "Use Enter to send, Alt-Enter for a newline, and Ctrl-U to discard."
                )
                return
            if self.control(text, priority=text in {"/stop", "/quit"}):
                self.editor.clear()
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

    async def run(self) -> None:
        worker = asyncio.create_task(
            terminal(self.controller, self.queue, self.emit, self.review_packet)
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
