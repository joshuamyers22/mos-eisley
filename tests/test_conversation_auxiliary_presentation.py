"""Shared selection presentation retains identity, Unicode and editing controls."""

import argparse
import asyncio
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Size
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import ColorDepth, DummyOutput
from prompt_toolkit.utils import get_cwidth
from test_conversation_tui import until

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import add_commands, demo_cassette, run_command
from mos_eisley.conversation_directory import DirectoryPicker
from mos_eisley.conversation_picker import ResumePicker
from mos_eisley.conversation_presentation import (
    DiffLexer,
    conversation_style,
    fit_label,
)
from mos_eisley.run.conversation_names import resume_catalog
from mos_eisley.run.conversation_store import ConversationStore


class SizedOutput(DummyOutput):
    size = Size(rows=24, columns=64)

    def get_size(self) -> Size:
        return self.size


class AuxiliaryPresentationTests(TestCase):
    def test_patch_lexer_preserves_bytes_and_coordinate_prefixes(self) -> None:
        text = "\n".join(
            (
                "diff --git a/file b/file",
                "--- a/file",
                "+++ b/file",
                "@@ -1 +1 @@",
                "-old | literal",
                "+new | literal",
                "   8 staged       -     2 | +source | literal",
                "   9 unstaged     3     - | -deleted",
            )
        )
        document = Document(text)
        line = DiffLexer().lex_document(document)
        self.assertEqual(
            "\n".join(
                "".join(fragment[1] for fragment in line(i))
                for i in range(document.line_count)
            ),
            text,
        )
        self.assertEqual(line(4)[0][0], "class:diff.removed")
        self.assertEqual(line(5)[0][0], "class:diff.added")
        self.assertEqual(line(6)[0][0], "class:diff.added")
        self.assertEqual(line(7)[0][0], "class:diff.removed")
        self.assertEqual(line(99), [])
        self.assertEqual(fit_label("项目", 0), "")

    def test_startup_directory_selection_receives_explicit_theme(self) -> None:
        parser = argparse.ArgumentParser()
        add_commands(parser.add_subparsers(dest="command").add_parser)
        args = parser.parse_args(
            ["chat", "--choose-directory", "--theme", "light", "--no-memory"]
        )
        with (
            patch("mos_eisley.conversation_cli.sys.stdin.isatty", return_value=True),
            patch("mos_eisley.conversation_cli.sys.stdout.isatty", return_value=True),
            patch(
                "mos_eisley.conversation_cli.pick_directory", return_value=None
            ) as choose,
        ):
            self.assertEqual(run_command(args), 0)
        self.assertEqual(choose.call_args.kwargs["theme"], "light")


class AuxiliaryKeyboardTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.loop_errors: list[dict[str, object]] = []
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, context: self.loop_errors.append(context)
        )

    async def asyncTearDown(self) -> None:
        self.assertEqual(self.loop_errors, [])

    async def test_narrow_unicode_picker_paging_details_refresh_and_resize(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary, create_pipe_input() as input:
            root = Path(temporary)
            state = ConversationController.fresh(root, demo_cassette())
            with ConversationStore(root / "sessions", state.session_id, root) as store:
                store.save(state)
            catalog = resume_catalog(root / "sessions", root, sqlite=False)
            original = catalog.sessions[0]
            rows = tuple(
                original.model_copy(
                    update={
                        "session_id": f"{i:032x}",
                        "session_name": f"任务 {i:02d} " + "项目" * 40,
                        "active": i == 0,
                    }
                )
                for i in range(45)
            )
            catalog = replace(catalog, sessions=rows, workspace="/tmp/" + "项目/" * 30)
            output = SizedOutput()
            ui = ResumePicker(
                catalog,
                lambda: replace(catalog, sessions=rows[::-1]),
                input=input,
                output=output,
                theme="plain",
            )
            task = asyncio.create_task(ui.app.run_async(set_exception_handler=False))
            try:
                await until(lambda: ui.app.is_running)
                self.assertEqual(ui.app.color_depth, ColorDepth.DEPTH_1_BIT)
                self.assertLess(ui.page_size, 20)
                for fragment in ui.render_rows():
                    line = fragment[1]
                    self.assertLessEqual(get_cwidth(line.rstrip("\n")), 64)
                for line in ui.header().splitlines():
                    self.assertLessEqual(get_cwidth(line), 64)
                input.send_text("\r")
                await until(lambda: "active" in ui.notice)
                self.assertFalse(task.done())
                step = ui.page_size
                input.send_text("\x1b[6~")
                await until(lambda: ui.index == step)
                selected = ui.rows[ui.index].session_id
                self.assertIn(selected, ui.detail_area.text)
                input.send_text("\x1b\x1b[B")
                await until(lambda: ui.detail_area.buffer.cursor_position > 0)
                self.assertFalse(ui.app.layout.has_focus(ui.detail_area))
                input.send_text("\x1b[15~")
                await until(
                    lambda: (
                        ui.rows[ui.index].session_id == selected
                        and ui.catalog.sessions[0] == rows[-1]
                    )
                )
                output.size = Size(rows=36, columns=112)
                ui.app.invalidate()
                await asyncio.sleep(0.1)
                self.assertEqual(ui.rows[ui.index].session_id, selected)
                self.assertIn(selected, ui.detail_area.text)
                self.assertEqual(ui.page_size, 20)
            finally:
                input.send_text("\x04")
                self.assertIsNone(await asyncio.wait_for(task, 3))

    async def test_directory_preview_edit_focus_and_cancel_at_narrow_width(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary, create_pipe_input() as input:
            root = Path(temporary).resolve()
            selected = root / ("项目" * 20)
            selected.mkdir()
            ui = DirectoryPicker(
                selected, base=root, theme="light", input=input, output=SizedOutput()
            )
            task = asyncio.create_task(ui.app.run_async(set_exception_handler=False))
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("\r")
                await until(lambda: ui.selection is not None)
                self.assertIn(str(selected), ui.details())
                style = ui.app.style
                assert style is not None
                self.assertEqual(
                    style.style_rules, conversation_style("light").style_rules
                )
                input.send_text("\x1bOQ")
                await until(lambda: ui.app.layout.has_focus(ui.preview_area))
                input.send_text("\x1bOQ")
                await until(lambda: not ui.app.layout.has_focus(ui.preview_area))
                draft = ui.editor.document
                input.send_text("x")
                await until(lambda: ui.selection is None)
                input.send_text("\x13")
                await until(lambda: "Press Enter" in ui.notice)
                self.assertFalse(task.done())
                with set_app(ui.app):
                    self.assertLessEqual(
                        ui.app.layout.container.preferred_height(64, 24).min, 24
                    )
                input.send_text("\x04")
                self.assertIsNone(await asyncio.wait_for(task, 3))
                self.assertEqual(ui.editor.text, draft.text + "x")
            finally:
                if not task.done():
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)
