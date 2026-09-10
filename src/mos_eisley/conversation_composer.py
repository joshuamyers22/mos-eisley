"""Bounded, in-memory multiline drafts; no storage or execution authority."""

MAX_DRAFT_CHARACTERS = 8000
MAX_DRAFT_LINES = 256


class ConversationComposer:
    def __init__(self) -> None:
        self.active = False
        self.invalid = False
        self.lines: list[str] = []
        self.characters = 0

    def begin(self) -> None:
        if self.active:
            raise ValueError("A draft is already open; use /send or /discard.")
        self.active = True

    def append(self, line: str) -> None:
        if not self.active:
            raise ValueError("Start a draft with /compose.")
        # A rejected paste must never become a silently truncated submission.
        if self.invalid:
            raise ValueError("Draft exceeded its limits; use /discard to restart.")
        size = self.characters + len(line) + bool(self.lines)
        if size > MAX_DRAFT_CHARACTERS or len(self.lines) >= MAX_DRAFT_LINES:
            self.invalid = True
            raise ValueError(
                "Draft exceeds 8,000 characters or 256 lines; use /discard to restart."
            )
        self.lines.append(line)
        self.characters = size

    def message(self) -> str:
        if not self.active:
            raise ValueError("Start a draft with /compose.")
        if self.invalid:
            raise ValueError("Draft exceeded its limits; use /discard to restart.")
        text = "\n".join(self.lines)
        if not text.strip():
            raise ValueError("Draft is empty; add text or use /discard.")
        return text

    def clear(self) -> None:
        self.active = False
        self.invalid = False
        self.lines.clear()
        self.characters = 0
