"""Presentation keeps terminal editing and status inspection independent of work."""

import argparse
import asyncio
import os
import pty
import re
import select
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Size
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.utils import get_cwidth
from test_conversation_tui import controller, until

from mos_eisley.conversation_cli import DEMO_PROMPTS, add_commands, startup_arguments
from mos_eisley.conversation_git_review_tui import GitReviewTUI
from mos_eisley.conversation_presentation import (
    COMPOSER_KEYS,
    TerminalTheme,
    compact_header,
    conversation_style,
    fit_label,
    footer_text,
    hint_line,
    keyboard_help,
)
from mos_eisley.conversation_project import ProjectLocation
from mos_eisley.conversation_state import ConversationEntry
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes


class PresentationTests(TestCase):
    def test_narrow_footer_and_composer_hints_fit_without_extra_rows(self) -> None:
        for width in (112, 80, 64, 48, 40, 32, 24, 16):
            for diff in (None, "files", "git"):
                with self.subTest(width=width, diff=diff):
                    text = footer_text("responding • 项目 " * 30, width, diff=diff)
                    self.assertEqual(len(text.splitlines()), 2 if diff is None else 3)
                    for line in text.splitlines():
                        self.assertLess(get_cwidth(line), width)
                    self.assertIn("responding", text)
                    if diff is not None:
                        self.assertIn("F10 close", text)
            self.assertLess(
                get_cwidth(hint_line(width, (COMPOSER_KEYS, "Enter send"))), width
            )
        narrow = footer_text("idle", 64)
        self.assertIn("Ctrl-O approval", narrow)
        self.assertNotIn("…", narrow)

    def test_omitted_keys_remain_inspectable(self) -> None:
        for diff in ("files", "git"):
            full = keyboard_help(diff)
            for key in ("Ctrl-C stop", "Ctrl-D quit", "F3 review", "F5 history", "F12"):
                self.assertIn(key, full)

    def test_color_selection_and_no_color_do_not_force_terminal_background(
        self,
    ) -> None:
        cases: tuple[tuple[TerminalTheme, dict[str, str]], ...] = (
            ("auto", {"COLORFGBG": "0;15"}),
            ("light", {}),
            ("dark", {}),
            ("plain", {}),
            ("dark", {"NO_COLOR": ""}),
        )
        for selected, env in cases:
            with self.subTest(theme=selected, env=env):
                # Explicit annotations keep the public theme choices checked too.
                style = conversation_style(selected, env)
                for _rule, value in style.style_rules:
                    self.assertNotIn("bg:", value)
                    if "NO_COLOR" in env or selected == "plain":
                        self.assertNotIn("#", value)
        light = conversation_style("light", {})
        self.assertEqual(
            light.style_rules,
            conversation_style("auto", {"COLORFGBG": "0;15"}).style_rules,
        )

    def test_paths_and_names_are_sanitized_and_bounded_in_terminal_cells(self) -> None:
        for width in (20, 40, 80):
            label = fit_label("/tmp/项目/" * 20 + "\x1b[2J\nfile", width, tail=True)
            self.assertLessEqual(get_cwidth(label), width)
            self.assertNotIn("\x1b", label)
            self.assertNotIn("\n", label)
        chat = controller()
        location = ProjectLocation(chat.state.workspace, None, "none")
        header = compact_header(chat.state, location, 40)
        self.assertEqual(len(header.splitlines()), 2)
        self.assertIn("recorded preview", header)
        for line in header.splitlines():
            self.assertLessEqual(get_cwidth(line), 40)

    def test_theme_parses_for_bare_launch_and_resume_without_changing_plain_mode(
        self,
    ) -> None:
        parser = argparse.ArgumentParser()
        add_commands(parser.add_subparsers(dest="command").add_parser)
        args = parser.parse_args(startup_arguments(["--theme", "light", "--plain"]))
        self.assertEqual(
            (args.command, args.theme, args.plain), ("chat", "light", True)
        )
        args = parser.parse_args(["resume", "--last", "--theme", "plain"])
        self.assertEqual(args.theme, "plain")


class PresentationKeyboardTests(IsolatedAsyncioTestCase):
    async def test_resize_and_output_keep_draft_focus_and_transcript_anchor(
        self,
    ) -> None:
        class ResizableOutput(DummyOutput):
            columns = 64
            rows = 24

            def get_size(self) -> Size:
                return Size(rows=self.rows, columns=self.columns)

        for kind in (ConversationTUI, GitReviewTUI):
            for theme in ("dark", "light", "plain"):
                with (
                    self.subTest(renderer=kind.__name__, theme=theme),
                    create_pipe_input() as input,
                ):
                    chat = controller()
                    chat.submit(DEMO_PROMPTS[0])
                    await chat.step()
                    chat.state = chat.state.model_copy(
                        update={
                            "entries": (
                                chat.state.entries[0].model_copy(
                                    update={"answer": "line\n" * 80}
                                ),
                            )
                        }
                    )
                    output = ResizableOutput()
                    ui = kind(chat, input=input, output=output, theme=theme)
                    ui.editor.set_document(Document("Keep this\nDraft two", 5))
                    ui.transcript.buffer.set_document(
                        Document(ui.transcript.text, 12), bypass_readonly=True
                    )
                    task = asyncio.create_task(ui.run())
                    try:
                        await until(lambda ui=ui: ui.app.is_running)
                        for width, height in (
                            (64, 24),
                            (48, 20),
                            (40, 18),
                            (32, 16),
                            (80, 28),
                        ):
                            output.columns, output.rows = width, height
                            ui.app.invalidate()
                            await asyncio.sleep(0.05)
                            chat.state = chat.state.model_copy(
                                update={
                                    "entries": chat.state.entries
                                    + (
                                        ConversationEntry(
                                            text="New output", status="queued"
                                        ),
                                    )
                                }
                            )
                            ui.refresh()
                            self.assertEqual(
                                ui.editor.document, Document("Keep this\nDraft two", 5)
                            )
                            self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                            self.assertEqual(ui.transcript.buffer.cursor_position, 12)
                            self.assertEqual(len(ui.footer().splitlines()), 2)
                            for line in ui.footer().splitlines():
                                self.assertLess(get_cwidth(line), width)
                            footer = next(
                                window
                                for window in ui.app.layout.find_all_windows()
                                if getattr(window.content, "text", None) == ui.footer
                            )
                            for visible in (False, True):
                                ui.diff_visible = visible
                                with set_app(ui.app):
                                    dimension = footer.preferred_height(width, height)
                                self.assertEqual(dimension.min, 3 if visible else 2)
                            ui.diff_visible = False
                        input.send_text("\x1bOQ")
                        await until(
                            lambda ui=ui: "Keyboard controls" in ui.transcript.text
                        )
                        self.assertIn("F3 review", ui.transcript.text)
                        self.assertEqual(
                            ui.editor.document, Document("Keep this\nDraft two", 5)
                        )
                    finally:
                        input.send_text("\x04")
                        await asyncio.wait_for(task, 3)
                        if isinstance(ui, ConversationTUI):
                            ui.diff_executor.shutdown(wait=False)

    async def test_composer_stays_compact_and_grows_with_multiline_drafts(self) -> None:
        for kind in (ConversationTUI, GitReviewTUI):
            with self.subTest(renderer=kind.__name__), create_pipe_input() as input:
                ui = kind(controller(), input=input, output=DummyOutput())
                window = next(
                    window
                    for window in ui.app.layout.find_all_windows()
                    if window.content is ui.editor_control
                )
                with set_app(ui.app):
                    empty = window.preferred_height(60, 30)
                    self.assertEqual((empty.preferred, empty.max), (3, 3))
                    ui.editor.text = "\n".join("Draft line" for _ in range(8))
                    multiline = window.preferred_height(60, 30)
                    self.assertGreater(multiline.preferred, empty.preferred)
                    self.assertLessEqual(multiline.max, 10)
                if isinstance(ui, ConversationTUI):
                    ui.diff_executor.shutdown(wait=False)

    async def test_f2_opens_complete_details_without_submitting_or_losing_draft(
        self,
    ) -> None:
        for kind in (ConversationTUI, GitReviewTUI):
            with self.subTest(renderer=kind.__name__), create_pipe_input() as input:
                chat = controller()
                before = canonical_bytes(chat.state)
                ui = kind(
                    chat,
                    welcome="Recorded preview\nSession snapshot budget: 2000000 bytes.",
                    input=input,
                    output=DummyOutput(),
                )
                ui.editor.set_document(Document("Unsent draft", 5))
                self.assertNotIn("Session snapshot budget", ui.transcript.text)
                task = asyncio.create_task(ui.run())
                try:
                    await until(lambda ui=ui: ui.app.is_running)
                    input.send_text("\x1bOQ")
                    await until(lambda ui=ui: "Launch details" in ui.transcript.text)
                    self.assertIn(
                        "Session snapshot budget: 2000000", ui.transcript.text
                    )
                    self.assertIn(chat.state.session_id, ui.transcript.text)
                    self.assertEqual(ui.editor.document, Document("Unsent draft", 5))
                    self.assertEqual(canonical_bytes(chat.state), before)
                    input.send_text("\x1bOQ")
                    await until(
                        lambda ui=ui: "Launch details" not in ui.transcript.text
                    )
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)

    async def test_browsing_history_survives_return_to_composer_and_new_output(
        self,
    ) -> None:
        for kind in (ConversationTUI, GitReviewTUI):
            with self.subTest(renderer=kind.__name__), create_pipe_input() as input:
                chat = controller()
                chat.submit(DEMO_PROMPTS[0])
                await chat.step()
                chat.state = chat.state.model_copy(
                    update={
                        "entries": (
                            chat.state.entries[0].model_copy(
                                update={"answer": "line\n" * 50}
                            ),
                        )
                    }
                )
                ui = kind(chat, input=input, output=DummyOutput())
                ui.transcript.buffer.set_document(
                    Document(ui.transcript.text, 12), bypass_readonly=True
                )
                ui.app.layout.focus(ui.editor_control)
                ui.editor.set_document(Document("A draft\nwith two lines", 4))
                chat.state = chat.state.model_copy(
                    update={
                        "entries": chat.state.entries
                        + (ConversationEntry(text="New output", status="queued"),)
                    }
                )
                ui.refresh()
                self.assertEqual(ui.transcript.buffer.cursor_position, 12)
                self.assertEqual(
                    ui.editor.document, Document("A draft\nwith two lines", 4)
                )
                self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                self.assertEqual(chat.state.entries[-1].status, "queued")
                if isinstance(ui, ConversationTUI):
                    ui.diff_executor.shutdown(wait=False)


class PresentationPTYTests(TestCase):
    def test_plain_theme_and_no_color_cover_default_widget_styles(self) -> None:
        for theme, no_color in (("plain", False), ("dark", True)):
            with self.subTest(theme=theme), TemporaryDirectory() as temporary:
                root = Path(temporary)
                master, slave = pty.openpty()
                env = {**os.environ, "TERM": "xterm-256color"}
                if no_color:
                    env["NO_COLOR"] = ""
                else:
                    env.pop("NO_COLOR", None)
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "chat",
                        "--workspace",
                        str(root),
                        "--storage",
                        str(root / "sessions"),
                        "--memory-storage",
                        str(root / "memory"),
                        "--no-memory",
                        "--theme",
                        theme,
                    ],
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    env=env,
                )
                raw = bytearray()

                def read(
                    *, terminal_fd: int = master, captured: bytearray = raw
                ) -> None:
                    ready, _, _ = select.select([terminal_fd], [], [], 0.1)
                    if ready:
                        data = os.read(terminal_fd, 65536)
                        captured.extend(data)
                        if b"\x1b[6n" in data:
                            os.write(terminal_fd, b"\x1b[1;1R")

                try:
                    deadline = time.monotonic() + 10
                    while b"F2 details" not in raw:
                        if time.monotonic() > deadline:
                            self.fail("Monochrome terminal did not start")
                        read()
                    os.write(master, b"\x04")
                    while b"conversation.saved" not in raw:
                        if time.monotonic() > deadline:
                            self.fail("Monochrome terminal did not save and exit")
                        read()
                    self.assertEqual(process.wait(timeout=5), 0)
                    for params in re.findall(rb"\x1b\[([0-9;]*)m", raw):
                        for value in params.split(b";"):
                            if not value:
                                continue
                            number = int(value)
                            self.assertFalse(
                                number in {38, 48}
                                or 30 <= number <= 37
                                or 40 <= number <= 47
                                or 90 <= number <= 97
                                or 100 <= number <= 107,
                                f"Unexpected terminal color code {number}",
                            )
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    os.close(master)
                    os.close(slave)
