"""A bounded, metadata-only resume picker with explicit selection."""

import json
import sys
import termios
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import Output
from prompt_toolkit.styles import Style

from mos_eisley.conversation_name import name_key
from mos_eisley.run.conversation_names import ResumeCatalog
from mos_eisley.run.conversation_store import ConversationSummary
from mos_eisley.run.conversation_transfer import TransferLocation

PAGE_SIZE = 20


def safe_label(value: str) -> str:
    return "".join(
        char if char.isprintable() else json.dumps(char)[1:-1] for char in value
    )


@dataclass(frozen=True)
class ResumeSelection:
    location: TransferLocation
    workspace: str
    summary: ConversationSummary


class ResumePicker:
    def __init__(
        self,
        catalog: ResumeCatalog,
        reload: Callable[[], ResumeCatalog],
        *,
        query: str = "",
        input: Input | None = None,
        output: Output | None = None,
    ) -> None:
        self.catalog = catalog
        self.reload = reload
        self.query = query
        self.index = 0
        self.valid = True
        self.rows: tuple[ConversationSummary, ...] = ()
        self.notice = "Enter selects. Queued work stays paused after resume."
        self.filter_rows()
        keys = KeyBindings()

        def _up(event: KeyPressEvent) -> None:
            self.index = max(0, self.index - 1)

        def _down(event: KeyPressEvent) -> None:
            self.index = min(max(0, len(self.rows) - 1), self.index + 1)

        def _previous(event: KeyPressEvent) -> None:
            self.index = max(0, self.index - PAGE_SIZE)

        def _next_page(event: KeyPressEvent) -> None:
            self.index = min(max(0, len(self.rows) - 1), self.index + PAGE_SIZE)

        def _select(event: KeyPressEvent) -> None:
            self.select()

        def _cancel(event: KeyPressEvent) -> None:
            self.app.exit(result=None)

        def _refresh(event: KeyPressEvent) -> None:
            self.refresh()

        def _erase(event: KeyPressEvent) -> None:
            self.query = self.query[:-1]
            self.filter_rows()

        def _clear(event: KeyPressEvent) -> None:
            self.query = ""
            self.filter_rows()

        def _text(event: KeyPressEvent) -> None:
            if event.data.isprintable() and len(self.query + event.data) <= 120:
                self.query += event.data
                self.filter_rows()

        keys.add("up")(_up)
        keys.add("down")(_down)
        keys.add("pageup")(_previous)
        keys.add("pagedown")(_next_page)
        keys.add("enter")(_select)
        keys.add("escape")(_cancel)
        keys.add("c-c")(_cancel)
        keys.add("c-d")(_cancel)
        keys.add("f5")(_refresh)
        keys.add("backspace")(_erase)
        keys.add("c-u")(_clear)
        keys.add("<any>")(_text)

        control = FormattedTextControl(
            self.render_rows,
            focusable=True,
            get_cursor_position=lambda: Point(0, self.index % PAGE_SIZE),
        )
        self.app: Application[ResumeSelection | None] = Application(
            layout=Layout(
                HSplit(
                    [
                        Window(FormattedTextControl(self.header), height=4),
                        Window(control, wrap_lines=False, always_hide_cursor=True),
                        Window(
                            FormattedTextControl(self.selection_details),
                            height=5,
                            wrap_lines=True,
                        ),
                        Window(
                            FormattedTextControl(lambda: safe_label(self.notice)),
                            height=2,
                        ),
                        Window(
                            FormattedTextControl(
                                "↑/↓ select • PgUp/PgDn page • type to filter • "
                                "Ctrl-U clear • F5 refresh • Esc cancel"
                            ),
                            height=2,
                        ),
                    ]
                ),
                focused_element=control,
            ),
            key_bindings=keys,
            full_screen=True,
            mouse_support=False,
            style=Style.from_dict({"selected": "reverse"}),
            input=input,
            output=output,
        )

    def filter_rows(self) -> None:
        query = name_key(self.query)
        self.rows = tuple(
            s
            for s in self.catalog.sessions
            if self.valid
            and (query in name_key(s.session_name or "") or query in s.session_id)
        )
        self.index = 0

    def header(self) -> str:
        pages = max(1, (len(self.rows) + PAGE_SIZE - 1) // PAGE_SIZE)
        return (
            "Resume a saved session\n"
            f"Workspace: {safe_label(self.catalog.workspace)}\n"
            f"Filter name/ID: {safe_label(self.query)}\n"
            f"{len(self.rows)} matches • page {self.index // PAGE_SIZE + 1}/{pages}"
        )

    def render_rows(self) -> StyleAndTextTuples:
        if not self.rows:
            return [("", "No matching saved sessions. F5 refreshes; Esc cancels.")]
        start = self.index // PAGE_SIZE * PAGE_SIZE
        result: StyleAndTextTuples = []
        for index, summary in enumerate(self.rows[start : start + PAGE_SIZE], start):
            try:
                saved = datetime.fromtimestamp(
                    summary.modified_ns // 1_000_000_000, UTC
                ).strftime("%Y-%m-%d %H:%M UTC")
            except (OverflowError, OSError, ValueError):
                saved = "Unknown saved time"
            name = summary.session_name or "(unnamed)"
            compact_name = name if len(name) <= 24 else name[:23] + "…"
            label = (
                f"{compact_name} | {summary.session_id} | "
                f"{saved} | {summary.messages} messages, {summary.pending} queued"
            )
            if summary.active:
                label += " | ACTIVE"
            result.append(
                (
                    "class:selected" if index == self.index else "",
                    safe_label(label) + "\n",
                )
            )
        return result

    def selection_details(self) -> str:
        if not self.rows:
            return ""
        selected = self.rows[self.index]
        return (
            f"Session ID: {selected.session_id}\n"
            f"Name: {safe_label(selected.session_name or '(unnamed)')}\n"
            f"{selected.messages} messages • {selected.pending} queued • "
            f"{'active' if selected.active else 'available'}"
        )

    def select(self) -> None:
        if not self.rows or not self.valid:
            return
        summary = self.rows[self.index]
        if summary.active:
            self.notice = (
                "That session is active. Select another or refresh after it closes."
            )
            return
        self.app.exit(
            result=ResumeSelection(
                self.catalog.location, self.catalog.workspace, summary
            )
        )

    def refresh(self) -> None:
        try:
            self.catalog = self.reload()
        except (OSError, ValueError):
            self.valid = False
            self.notice = (
                "Catalog changed or is unavailable. Refresh again or cancel; "
                "selection is disabled."
            )
        else:
            self.valid = True
            self.notice = "Catalog refreshed. Enter selects; queued work stays paused."
        self.filter_rows()


def pick_session(
    catalog: ResumeCatalog, reload: Callable[[], ResumeCatalog], *, query: str = ""
) -> ResumeSelection | None:
    fd = sys.stdin.fileno()
    modes = termios.tcgetattr(fd)
    try:
        return ResumePicker(catalog, reload, query=query).app.run()
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, modes)
