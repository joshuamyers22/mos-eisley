"""Ephemeral operation display; observes state without dispatching or persisting."""

from collections.abc import Callable
from time import monotonic

from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import TextArea

from mos_eisley.conversation_presentation import fit_label, model_route
from mos_eisley.conversation_state import RuntimeConversationState
from mos_eisley.terminal_text import safe_label


class ConversationActivity:
    """Retain one operation and one failure, bounded independently of transcript."""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self.clock = clock
        self.expanded = False
        self.key: int | None = None
        self.started: float | None = None
        self.elapsed = 0
        self.phase = "Idle"
        self.action = "No active operation"
        self.scope = "No active tool access"
        self.route = "recorded"
        self.queued = 0
        self.error: tuple[str, str] | None = None
        self.detail = ""
        self.detail_view = TextArea(
            read_only=True,
            scrollbar=True,
            wrap_lines=True,
            height=Dimension(min=1, max=7),
            style="class:muted",
        )
        self.detail_view.window.dont_extend_height = Condition(lambda: True)

    def observe(self, state: RuntimeConversationState) -> None:
        self.queued = sum(e.status == "queued" for e in state.entries)
        running = next(
            ((i, e) for i, e in enumerate(state.entries) if e.status == "running"),
            None,
        )
        if running is not None:
            index, entry = running
            if self.key != index:
                self.key = index
                self.started = self.clock()
                self.elapsed = 0
            self.phase = "Working"
            self.action = (
                "Repository inspection"
                if entry.repository_inspection
                else "Review"
                if entry.is_review
                else "Implementation"
                if entry.implementation_request
                else "Response"
            )
            self.scope = (
                "Bounded repository reads; no writes"
                if entry.repository_inspection
                else "Selected implementation workflow; existing approvals apply"
                if entry.implementation_request
                else "No repository tool access for this operation"
            )
            self.route = model_route(state)
            self.detail = f"Message [{index}]: " + fit_label(entry.text, 800)
        elif self.key is not None:
            if self.started is not None:
                self.elapsed = max(0, int(self.clock() - self.started))
                self.started = None
            self.phase = state.entries[self.key].status.capitalize()
        else:
            self.phase = "Queued" if self.queued else "Idle"
        self.sync_details()

    def sync_details(self) -> None:
        text = self.expanded_text()
        if text != self.detail_view.text:
            self.detail_view.buffer.set_document(
                Document(text, min(self.detail_view.buffer.cursor_position, len(text))),
                bypass_readonly=True,
            )

    def summary(self, width: int) -> str:
        elapsed = (
            max(0, int(self.clock() - self.started))
            if self.started is not None
            else self.elapsed
        )
        duration = f" • {elapsed}s observed" if self.key is not None else ""
        return (
            fit_label(
                f"{self.phase} • {self.action}{duration} • {self.queued} queued", width
            )
            + "\nCtrl-T "
            + ("hide" if self.expanded else "show")
            + " activity details"
        )

    def details(self) -> str:
        return "\n".join(
            (
                self.scope,
                "Route: " + self.route,
                self.detail,
                "Elapsed time covers this launch only. "
                "Individual calls are not streamed.",
            )
        )

    def receive(self, event: dict[str, object]) -> bool:
        kind = str(event.get("type", ""))
        if kind in {"conversation.error", "conversation.unavailable", "composer.error"}:
            next_step = (
                "Inspect /status and /context. Resolve the cause before /continue; "
                "failed messages are not retried automatically."
                if kind == "conversation.error"
                else "Use /help to check the command and its prerequisites, "
                "then try again."
            )
            self.error = (safe_label(str(event.get("text", "")))[:1200], next_step)
            self.sync_details()
            return True
        return False

    def notice_text(self, text: str) -> str:
        """Avoid showing the same failure again below the composer."""
        if (
            self.error is not None
            and safe_label(text) == self.error[0][: len(safe_label(text))]
        ):
            return ""
        return text

    def error_text(self, width: int) -> str:
        if self.error is None:
            return ""
        reason, next_step = self.error
        return (
            fit_label("Error • " + reason, width)
            + "\n"
            + fit_label("Next: " + next_step, width)
            + "\nCtrl-T details • Ctrl-Y dismiss"
        )

    def expanded_text(self) -> str:
        text = self.details()
        if self.error is not None:
            text += "\nError: " + self.error[0] + "\nNext: " + self.error[1]
        return text

    def panel(
        self, width: Callable[[], int], *, compact: Callable[[], bool] = lambda: False
    ) -> HSplit:
        return HSplit(
            [
                ConditionalContainer(
                    Window(
                        FormattedTextControl(lambda: self.summary(width())),
                        height=2,
                        style="class:status",
                    ),
                    filter=Condition(lambda: not compact()),
                ),
                ConditionalContainer(
                    HSplit(
                        [
                            Window(
                                FormattedTextControl("Alt-↑/↓ scroll activity details"),
                                height=1,
                                style="class:muted",
                            ),
                            self.detail_view,
                        ]
                    ),
                    filter=Condition(lambda: self.expanded and not compact()),
                ),
                ConditionalContainer(
                    Window(
                        FormattedTextControl(lambda: self.error_text(width())),
                        height=3,
                        style="class:error",
                    ),
                    filter=Condition(lambda: self.error is not None),
                ),
            ]
        )
