"""Shared terminal presentation; no controller or execution authority."""

import os
from collections.abc import Callable, Mapping
from typing import Literal

from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.layout import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.processors import BeforeInput, ConditionalProcessor
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth

from mos_eisley.conversation_project import ProjectLocation
from mos_eisley.conversation_state import RuntimeConversationState
from mos_eisley.conversation_subscription import SubscriptionChatIdentity
from mos_eisley.terminal_text import safe_label

TerminalTheme = Literal["auto", "dark", "light", "plain"]


def conversation_color_depth(theme: TerminalTheme) -> ColorDepth | None:
    # Monochrome must also cover prompt-toolkit's built-in widget styles.
    if theme == "plain" or "NO_COLOR" in os.environ:
        return ColorDepth.DEPTH_1_BIT
    return None


def conversation_style(
    theme: TerminalTheme, environment: Mapping[str, str] | None = None
) -> Style:
    env = os.environ if environment is None else environment
    if "NO_COLOR" in env or theme == "plain":
        return Style.from_dict({"user": "bold", "header": "bold"})
    if theme == "auto":
        background = env.get("COLORFGBG", "").rsplit(";", 1)[-1]
        theme = "light" if background in {"7", "15"} else "dark"
    accent, muted, line = (
        ("#176c5b", "#566371", "#9ca6af")
        if theme == "light"
        else ("#83cdbf", "#a4afbc", "#44505e")
    )
    return Style.from_dict(
        {
            "header": f"{accent} bold",
            "user": f"{accent} bold",
            "assistant": muted,
            "muted": muted,
            "separator": line,
            "status": muted,
            "error": "#a33b32" if theme == "light" else "#e6a097",
            "frame.border": line,
            "frame.label": muted,
        }
    )


def fit_label(text: str, width: int, *, tail: bool = False) -> str:
    """Bound a sanitized label in terminal cells, including wide characters."""
    text = safe_label(text)
    if get_cwidth(text) <= width:
        return text
    remaining = max(0, width - 1)
    chars: list[str] = []
    used = 0
    for char in reversed(text) if tail else text:
        cells = get_cwidth(char)
        if used + cells > remaining:
            break
        chars.append(char)
        used += cells
    return "…" + "".join(reversed(chars)) if tail else "".join(chars) + "…"


def conversation_mode(state: RuntimeConversationState, *, live_review: bool) -> str:
    if state.mode == "subscription_conversation":
        return "subscription chat"
    if state.mode == "openai_live_conversation":
        return "live OpenAI chat"
    return "recorded chat / live review" if live_review else "recorded preview"


def header_fragments(text: str) -> StyleAndTextTuples:
    lines = text.splitlines()
    if not lines:
        return []
    fragments: StyleAndTextTuples = [("class:header", lines[0])]
    for line in lines[1:]:
        fragments.append(("class:muted", "\n" + line))
    return fragments


def compact_header(
    state: RuntimeConversationState,
    location: ProjectLocation,
    width: int,
    *,
    live_review: bool = False,
) -> str:
    width = max(20, width)
    mode = conversation_mode(state, live_review=live_review)
    title = fit_label(f"Mos Eisley • {mode}", width)
    name = safe_label(state.session_name or "New session")
    if get_cwidth(title) + 5 < width:
        title += " • " + fit_label(name, width - get_cwidth(title) - 3)
    lines = [title, "Directory: " + fit_label(state.workspace, width - 11, tail=True)]
    if location.root is not None and location.root != state.workspace:
        lines.append("Project root: " + fit_label(location.root, width - 14, tail=True))
    if state.live_chat is not None and state.live_chat.repository_read:
        lines.append(
            fit_label("/inspect explicitly permits bounded source reads", width)
        )
    return "\n".join(lines)


def model_route(state: RuntimeConversationState) -> str:
    live = state.live_chat
    if live is None:
        return "fixture/tool-reviewer-v1 • high"
    provider = live.provider if isinstance(live, SubscriptionChatIdentity) else "openai"
    return safe_label(f"{provider}/{live.model} • {live.effort}")


def tool_availability(state: RuntimeConversationState) -> str:
    live = state.live_chat
    return (
        "reads via /inspect"
        if live is not None and live.repository_read
        else "tools off"
    )


def compact_status(
    state: RuntimeConversationState, *, queue_full: bool, goal_status: str | None
) -> str:
    active = next((e for e in state.entries if e.status == "running"), None)
    phase = (
        "reviewing"
        if active is not None and active.is_review
        else ("responding" if active is not None else "idle")
    )
    queued = sum(e.status == "queued" for e in state.entries)
    live = state.live_chat
    route = "recorded" if live is None else model_route(state)
    tools = tool_availability(state)
    parts = [phase, state.interaction_mode, f"{queued} queued", tools, route]
    if queue_full:
        parts.append("queue text budget full")
    if goal_status is not None:
        parts.append(f"goal {goal_status}")
    return safe_label(" • ".join(parts))


def compact_welcome(welcome: str, *, recorded: bool, memory_disabled: bool) -> str:
    if not welcome:
        return ""
    if recorded:
        lines = welcome.splitlines()
        start = next(
            (
                i
                for i, line in enumerate(lines)
                if line == "Try these messages in order:"
            ),
            None,
        )
        prompts = [] if start is None else lines[start : start + 3]
        text = ["Recorded preview. This session uses local fixtures.", *prompts]
        if start is None:
            text.append("Use the messages expected by your selected recording.")
    else:
        # Keep the actual provider/session description instead of assuming its mode.
        text = welcome.splitlines()[:2]
    if memory_disabled:
        text.append("Memory is off for this session.")
    text.append("/status shows session details and limits. /memory inspects context.")
    return "\n".join(text)


class ConversationLexer(Lexer):
    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        def line(index: int) -> StyleAndTextTuples:
            if not 0 <= index < len(document.lines):
                return []
            text = document.lines[index]
            style = (
                "class:user"
                if text == "You" or text.startswith(("You •", "You ["))
                else ("class:assistant" if text == "Mos" else "")
            )
            return [(style, text)]

        return line


def composer(control: BufferControl) -> HSplit:
    control.input_processors = [
        *(control.input_processors or []),
        ConditionalProcessor(
            BeforeInput([("class:muted", "Type a message…")]),
            filter=Condition(lambda: not control.buffer.text),
        ),
    ]
    return HSplit(
        [
            Window(height=1, char="─", style="class:separator"),
            VSplit(
                [
                    Window(FormattedTextControl("› "), width=2, style="class:user"),
                    Window(
                        control,
                        height=Dimension(min=3, max=10),
                        dont_extend_height=True,
                        wrap_lines=True,
                    ),
                ]
            ),
            Window(height=1, char="─", style="class:separator"),
            Window(
                FormattedTextControl(
                    "Enter send • Alt-Enter newline • Ctrl-C stop • Ctrl-D quit"
                ),
                height=1,
                style="class:muted",
            ),
        ]
    )
