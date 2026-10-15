"""A bounded, metadata-only resume picker with explicit selection."""

import sys
import termios
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.output import Output
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import TextArea

from mos_eisley.conversation_name import name_key
from mos_eisley.conversation_presentation import (
    SelectionLexer,
    TerminalTheme,
    conversation_color_depth,
    conversation_style,
    fit_label,
    header_fragments,
)
from mos_eisley.run.conversation_names import ResumeCatalog
from mos_eisley.run.conversation_store import ConversationSummary
from mos_eisley.run.conversation_transfer import TransferLocation
from mos_eisley.terminal_text import safe_label as safe_label

PAGE_SIZE = 20


def saved_time(summary: ConversationSummary) -> str:
    try:
        return datetime.fromtimestamp(
            summary.modified_ns // 1_000_000_000, UTC
        ).strftime("%Y-%m-%d %H:%M UTC")
    except (OverflowError, OSError, ValueError):
        return "Unknown saved time"


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
        theme: TerminalTheme = "auto",
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
        self.detail_area = TextArea(
            read_only=True,
            focusable=False,
            scrollbar=True,
            wrap_lines=True,
            lexer=SelectionLexer(),
            height=Dimension(min=3, max=5),
        )
        self.detail_area.window.dont_extend_height = Condition(lambda: True)
        self.filter_rows()
        keys = KeyBindings()

        def _up(event: KeyPressEvent) -> None:
            self.index = max(0, self.index - 1)
            self.sync_details()

        def _down(event: KeyPressEvent) -> None:
            self.index = min(max(0, len(self.rows) - 1), self.index + 1)
            self.sync_details()

        def _previous(event: KeyPressEvent) -> None:
            self.index = max(0, self.index - self.page_size)
            self.sync_details()

        def _next_page(event: KeyPressEvent) -> None:
            self.index = min(max(0, len(self.rows) - 1), self.index + self.page_size)
            self.sync_details()

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

        def details_up(event: KeyPressEvent) -> None:
            self.detail_area.buffer.cursor_up(count=3)

        def details_down(event: KeyPressEvent) -> None:
            self.detail_area.buffer.cursor_down(count=3)

        keys.add("escape", "up")(details_up)
        keys.add("escape", "down")(details_down)
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
            get_cursor_position=lambda: Point(0, self.index % self.page_size),
        )
        self.app: Application[ResumeSelection | None] = Application(
            layout=Layout(
                HSplit(
                    [
                        Window(
                            FormattedTextControl(
                                lambda: header_fragments(self.header())
                            ),
                            height=4,
                        ),
                        Window(control, wrap_lines=False, always_hide_cursor=True),
                        Window(height=1, char="─", style="class:separator"),
                        self.detail_area,
                        Window(
                            FormattedTextControl(lambda: safe_label(self.notice)),
                            height=Dimension(min=1, max=2),
                            dont_extend_height=True,
                            wrap_lines=True,
                            style="class:status",
                        ),
                        Window(
                            FormattedTextControl(
                                "↑/↓ select • PgUp/PgDn page • type to filter • "
                                "Ctrl-U clear • F5 refresh • Esc cancel • "
                                "Alt-↑/↓ details"
                            ),
                            height=2,
                            wrap_lines=True,
                            style="class:muted",
                        ),
                    ]
                ),
                focused_element=control,
            ),
            key_bindings=keys,
            full_screen=True,
            mouse_support=False,
            style=conversation_style(theme),
            color_depth=conversation_color_depth(theme),
            input=input,
            output=output,
        )

    @property
    def page_size(self) -> int:
        return max(1, min(PAGE_SIZE, self.app.output.get_size().rows - 15))

    def sync_details(self) -> None:
        text = self.selection_details()
        if text != self.detail_area.text:
            self.detail_area.buffer.set_document(
                Document(text, 0), bypass_readonly=True
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
        self.sync_details()

    def header(self) -> str:
        pages = max(1, (len(self.rows) + self.page_size - 1) // self.page_size)
        width = self.app.output.get_size().columns
        return (
            "Resume a saved session\n"
            "Workspace: "
            + fit_label(self.catalog.workspace, width - 11, tail=True)
            + "\n"
            "Filter name/ID: "
            + fit_label(self.query or "Type to search…", width - 16, tail=True)
            + "\n"
            f"{len(self.rows)} matches • "
            f"page {self.index // self.page_size + 1}/{pages}"
        )

    def render_rows(self) -> StyleAndTextTuples:
        if not self.rows:
            return [("", "No matching saved sessions. F5 refreshes; Esc cancels.")]
        start = self.index // self.page_size * self.page_size
        result: StyleAndTextTuples = []
        for index, summary in enumerate(
            self.rows[start : start + self.page_size], start
        ):
            saved = saved_time(summary)
            width = self.app.output.get_size().columns
            name = summary.session_name or "(unnamed)"
            state = "ACTIVE" if summary.active else "ready"
            meta = f"{summary.pending} queued • {state}"
            if width >= 52:
                meta = f"{summary.messages} msg • " + meta
            if width >= 95:
                meta += " • " + saved
            name_width = max(1, width - get_cwidth(meta) - 5)
            name = fit_label(name, name_width)
            name += " " * max(0, name_width - get_cwidth(name))
            marker = "› " if index == self.index else "  "
            label = fit_label(marker + name + "   " + meta, width)
            result.append(
                (
                    "class:list-selected" if index == self.index else "",
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
            f"{'active' if selected.active else 'available'}\n"
            f"Saved: {saved_time(selected)}\n"
            f"Workspace: {safe_label(self.catalog.workspace)}"
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
        selected_id = self.rows[self.index].session_id if self.rows else None
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
        self.index = next(
            (i for i, row in enumerate(self.rows) if row.session_id == selected_id), 0
        )
        self.sync_details()


def pick_session(
    catalog: ResumeCatalog,
    reload: Callable[[], ResumeCatalog],
    *,
    query: str = "",
    theme: TerminalTheme = "auto",
) -> ResumeSelection | None:
    fd = sys.stdin.fileno()
    modes = termios.tcgetattr(fd)
    try:
        return ResumePicker(catalog, reload, query=query, theme=theme).app.run()
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, modes)
