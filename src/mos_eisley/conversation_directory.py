"""Explicit startup directory selection before session or memory access."""

import os
import stat
import sys
import termios
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import DummyHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import Float, FloatContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.output import Output
from prompt_toolkit.widgets import TextArea

from mos_eisley.conversation_picker import safe_label

MAX_PATH_BYTES = 4096
MAX_DIRECTORY_ENTRIES = 1024
MAX_COMPLETIONS = 100


class DirectorySelectionError(ValueError):
    """Fixed guidance safe to display without rejected paths or OS diagnostics."""


def valid_path_text(text: str) -> bool:
    return (
        bool(text)
        and text.isprintable()
        and len(text.encode("utf-8")) <= MAX_PATH_BYTES
    )


@dataclass(frozen=True)
class DirectorySelection:
    path: Path
    device: int
    inode: int

    @classmethod
    def inspect(cls, path: Path) -> "DirectorySelection":
        try:
            resolved = path.expanduser().resolve(strict=True)
            if not valid_path_text(str(resolved)):
                raise ValueError("invalid path")
            info = resolved.stat(follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("not a directory")
        except (OSError, ValueError, RuntimeError):
            raise DirectorySelectionError(
                "Choose an accessible existing directory with a printable path "
                "of at most 4,096 UTF-8 bytes."
            ) from None
        return cls(resolved, info.st_dev, info.st_ino)

    def verify(self) -> None:
        try:
            current = self.inspect(self.path)
        except DirectorySelectionError:
            raise DirectorySelectionError(
                "The selected directory is unavailable; choose it again."
            ) from None
        if current != self:
            raise DirectorySelectionError(
                "The selected directory changed; choose it again."
            )


class DirectoryCompleter(Completer):
    def __init__(self, base: Path, notice: Callable[[str], None]) -> None:
        self.base = base
        self.notice = notice

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        if not text or not valid_path_text(text):
            return
        try:
            expanded = Path(text).expanduser()
            if not expanded.is_absolute():
                expanded = self.base / expanded
            prefix = text.rsplit(os.sep, 1)[-1]
            if prefix in {".", ".."} or (text.startswith("~") and os.sep not in text):
                if expanded.is_dir():
                    yield Completion(os.sep)
                return
            parent = expanded if text.endswith(os.sep) else expanded.parent
            matches: list[str] = []
            with os.scandir(parent) as entries:
                for count, entry in enumerate(entries, 1):
                    if count > MAX_DIRECTORY_ENTRIES:
                        raise DirectorySelectionError("directory entry limit")
                    if (
                        entry.name.startswith(prefix)
                        and entry.name.isprintable()
                        and entry.is_dir()
                    ):
                        matches.append(entry.name)
                        if len(matches) > MAX_COMPLETIONS:
                            raise DirectorySelectionError("completion limit")
        except (OSError, ValueError, RuntimeError):
            self.notice("Completion unavailable or too large. Type the path directly.")
            return
        for name in sorted(matches):
            yield Completion(name + os.sep, start_position=-len(prefix))


class DirectoryBuffer(Buffer):
    def __init__(
        self,
        changed: Callable[[], None],
        notice: Callable[[str], None],
        completer: Completer,
    ) -> None:
        self.changed_selection = changed
        self.notice = notice
        self.previous = Document()
        self.restoring = False
        self.undo_documents: list[Document] = []
        self.redo_documents: list[Document] = []
        super().__init__(
            multiline=False,
            history=DummyHistory(),
            completer=completer,
            complete_while_typing=False,
            on_text_changed=self.changed,
        )

    def changed(self, buffer: Buffer) -> None:
        if self.restoring:
            return
        self.changed_selection()
        if self.text and not valid_path_text(self.text):
            self.restoring = True
            try:
                self.set_document(self.previous, bypass_readonly=True)
            finally:
                self.restoring = False
            self.notice("Use a single printable path of at most 4,096 UTF-8 bytes.")
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


class DirectoryPicker:
    def __init__(
        self,
        initial: Path,
        *,
        input: Input | None = None,
        output: Output | None = None,
        base: Path | None = None,
    ) -> None:
        self.base = Path.cwd() if base is None else base
        self.selection: DirectorySelection | None = None
        self.notice = "Enter previews the resolved path. Ctrl-S uses that directory."
        self.preview_area = TextArea(
            text=self.details(), read_only=True, scrollbar=True, wrap_lines=True
        )
        self.editor = DirectoryBuffer(
            self.invalidate_selection,
            self.set_notice,
            DirectoryCompleter(self.base, self.set_notice),
        )
        self.editor.set_document(Document(str(initial), len(str(initial))))
        keys = KeyBindings()

        def preview(event: KeyPressEvent) -> None:
            self.preview()

        def choose(event: KeyPressEvent) -> None:
            if self.selection is None:
                self.set_notice(
                    "Press Enter to preview the directory before selecting."
                )
                return
            try:
                self.selection.verify()
            except DirectorySelectionError as error:
                self.invalidate_selection()
                self.set_notice(str(error))
            else:
                self.app.exit(result=self.selection)

        def cancel(event: KeyPressEvent) -> None:
            self.app.exit(result=None)

        def clear(event: KeyPressEvent) -> None:
            self.app.layout.focus(control)
            self.editor.set_document(Document())

        def complete(event: KeyPressEvent) -> None:
            self.app.layout.focus(control)
            if self.editor.complete_state:
                self.editor.complete_next()
            else:
                self.editor.start_completion(select_first=False)

        def paste(event: KeyPressEvent) -> None:
            self.app.layout.focus(control)
            self.editor.insert_text(event.data)

        def focus(event: KeyPressEvent) -> None:
            self.app.layout.focus(
                control
                if self.app.layout.has_focus(self.preview_area)
                else self.preview_area
            )

        keys.add("enter")(preview)
        keys.add("c-s")(choose)
        keys.add("escape")(cancel)
        keys.add("c-c")(cancel)
        keys.add("c-d")(cancel)
        keys.add("c-u")(clear)
        keys.add("tab")(complete)
        keys.add("f2")(focus)
        keys.add(Keys.BracketedPaste)(paste)
        control = BufferControl(buffer=self.editor)
        self.app: Application[DirectorySelection | None] = Application(
            layout=Layout(
                FloatContainer(
                    content=HSplit(
                        [
                            Window(
                                FormattedTextControl("Choose a session directory"),
                                height=2,
                            ),
                            Window(
                                FormattedTextControl(
                                    lambda: (
                                        "Relative paths start at: "
                                        + safe_label(str(self.base))
                                    )
                                ),
                                height=2,
                                wrap_lines=True,
                            ),
                            Window(control, height=3, wrap_lines=True),
                            self.preview_area,
                            Window(
                                FormattedTextControl(lambda: safe_label(self.notice)),
                                height=3,
                                wrap_lines=True,
                            ),
                            Window(
                                FormattedTextControl(
                                    "Enter preview • Ctrl-S select • Tab complete • "
                                    "F2 inspect path/edit • Ctrl-U clear • Esc cancel"
                                ),
                                height=2,
                                wrap_lines=True,
                            ),
                        ]
                    ),
                    floats=[
                        Float(
                            xcursor=True,
                            ycursor=True,
                            content=CompletionsMenu(max_height=8),
                        )
                    ],
                ),
                focused_element=control,
            ),
            key_bindings=keys,
            full_screen=True,
            mouse_support=False,
            input=input,
            output=output,
        )

    def set_notice(self, message: str) -> None:
        self.notice = message

    def invalidate_selection(self) -> None:
        self.selection = None
        self.preview_area.text = self.details()

    def preview(self) -> None:
        self.selection = None
        try:
            text = self.editor.text
            if not valid_path_text(text):
                raise DirectorySelectionError("Enter an existing directory path.")
            candidate = Path(text).expanduser()
            if not candidate.is_absolute():
                candidate = self.base / candidate
            self.selection = DirectorySelection.inspect(candidate)
        except (OSError, ValueError, RuntimeError):
            self.notice = "Directory unavailable or invalid. Edit the path and retry."
        else:
            self.notice = "Resolved directory preview is ready. Ctrl-S selects it."
        self.preview_area.text = self.details()

    def details(self) -> str:
        if self.selection is None:
            return "Resolved directory: preview required"
        return "Resolved directory:\n" + safe_label(str(self.selection.path))


def pick_directory(initial: Path) -> DirectorySelection | None:
    fd = sys.stdin.fileno()
    modes = termios.tcgetattr(fd)
    try:
        return DirectoryPicker(initial).app.run()
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, modes)
