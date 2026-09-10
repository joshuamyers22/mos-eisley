"""Line-oriented recorded conversation preview; renderer owns no execution tools."""

from __future__ import annotations

import argparse
import asyncio
import codecs
import json
import os
import signal
import stat
import sys
import termios
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from mos_eisley.conversation import (
    ConversationController,
    ConversationState,
    conversation_config,
)
from mos_eisley.conversation_composer import ConversationComposer
from mos_eisley.conversation_context import ContextBudgetError
from mos_eisley.conversation_input import (
    ConversationInput,
    ConversationInputQueue,
    ConversationSubmission,
)
from mos_eisley.conversation_limits import (
    catalog_byte_limit,
    context_byte_limit,
    snapshot_byte_limit,
)
from mos_eisley.conversation_memory import (
    MEMORY_CHANGED_MESSAGE,
    ConversationMemory,
    MemoryChangedError,
    MemoryRefreshError,
    MemoryStore,
)
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_review import (
    MAX_REVIEW_PACKET_BYTES,
    REVIEW_FOLLOWUP,
    REVIEW_PROMPT,
    ConversationReviewPacket,
    review_summary,
    run_conversation_review,
)
from mos_eisley.core.agent import AgentFailure, RequestBudgetError, build_request
from mos_eisley.core.budget import resolve_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelResponse, TextBlock, Turn, Usage
from mos_eisley.core.registry import fixture_registry
from mos_eisley.demo import demo_inputs
from mos_eisley.memory_cli import add_command as add_memory_command
from mos_eisley.memory_cli import add_memory_options
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_artifacts import (
    DEFAULT_ARTIFACT_BYTES,
    read_sqlite_artifact,
)
from mos_eisley.run.conversation_migration import ConversationMigration
from mos_eisley.run.conversation_resume import inspect_sqlite_resume
from mos_eisley.run.conversation_sqlite import (
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import (
    ConversationStore,
    ConversationSummary,
    list_conversations,
)
from mos_eisley.run.conversation_transcript import read_sqlite_transcript
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write
from mos_eisley.tools.none import NoToolsDispatcher

DEMO_PROMPTS = (
    "Remember that the fixture boundary is ten.",
    "What boundary did I give you?",
)
MULTILINE_PROMPT = "Remember this fixture boundary:\n\n```python\nboundary = 10\n```"


def startup_arguments(argv: list[str]) -> list[str]:
    """Route a bare launch and session options without hiding command typos."""
    launch_options = {
        "-C",
        "--workspace",
        "--storage",
        "--cassette",
        "--review-packet",
        "--tui",
        "--plain",
        "--json",
        "--no-memory",
        "--memory-storage",
        "--session-max-bytes",
        "--context-max-bytes",
        "--storage-backend",
    }
    if not argv or argv[0].split("=", 1)[0] in launch_options:
        return ["chat", *argv]
    return argv


def demo_cassette(
    review_text: str | None = None,
    *,
    multiline: bool = False,
    memory: ConversationMemory | None = None,
) -> AgentCassette:
    turns: tuple[Turn, ...] = ()
    exchanges: list[AgentExchange] = []
    for prompt, answer in zip(
        DEMO_PROMPTS,
        ("The fixture boundary is ten.", "You gave me a boundary of ten."),
        strict=True,
    ):
        if prompt == DEMO_PROMPTS[0] and multiline:
            prompt = MULTILINE_PROMPT
        if prompt == DEMO_PROMPTS[1] and review_text is not None:
            turns += (
                Turn(role="user", blocks=(TextBlock(text=REVIEW_PROMPT),)),
                Turn(role="assistant", blocks=(TextBlock(text=review_text),)),
            )
            prompt = REVIEW_FOLLOWUP
            answer = "Restore quantity >= 10."
        turns += (Turn(role="user", blocks=(TextBlock(text=prompt),)),)
        config = conversation_config(turns, memory)
        resolved = fixture_registry().resolve(
            config.provider, config.model, config.effort
        )
        request = build_request(
            config,
            resolved,
            resolve_budget(resolved.spec, resolved.effort, config.budget),
            NoToolsDispatcher(),
            turns,
        )
        response_turn = Turn(role="assistant", blocks=(TextBlock(text=answer),))
        exchanges.append(
            AgentExchange(
                request_sha256=digest(canonical_bytes(request)),
                response=ModelResponse(
                    turn=response_turn,
                    stop_reason="end_turn",
                    usage=Usage(
                        input=len(canonical_bytes(request)),
                        output=len(canonical_bytes(response_turn)),
                    ),
                ),
            )
        )
        turns += (response_turn,)
    return AgentCassette(exchanges=tuple(exchanges))


def add_commands(add_parser: Callable[..., argparse.ArgumentParser]) -> None:
    artifact = add_parser(
        "session-artifact", help="Expand one selected SQLite artifact"
    )
    artifact.add_argument(
        "selection", help="Artifact selection token from session-transcript"
    )
    artifact.add_argument(
        "--storage", type=Path, default=Path.home() / ".mos-eisley-sessions"
    )
    artifact.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    artifact.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_ARTIFACT_BYTES,
        help="Explicit artifact read budget (default 512000; max 32000000)",
    )
    artifact.add_argument("--json", action="store_true", help="Print JSON")
    transcript = add_parser(
        "session-transcript", help="Read verified SQLite transcript pages"
    )
    transcript.add_argument("session_id")
    transcript.add_argument(
        "--storage", type=Path, default=Path.home() / ".mos-eisley-sessions"
    )
    transcript.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    transcript.add_argument(
        "--limit", type=int, help="Messages per page (1–16; default 4)"
    )
    transcript.add_argument("--cursor", help="Continue a transcript page")
    transcript.add_argument(
        "--prepare",
        action="store_true",
        help="Verify and index an older SQLite session",
    )
    transcript.add_argument(
        "--expected-sha256", help="Exact session hash for --prepare"
    )
    transcript.add_argument("--json", action="store_true", help="Print JSON")
    migration = add_parser(
        "session-migrate", help="Preview or apply a JSON session import into SQLite"
    )
    migration.add_argument("session_id")
    migration.add_argument(
        "--storage", type=Path, default=Path.home() / ".mos-eisley-sessions"
    )
    migration.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    migration.add_argument("--expected-sha256", help="Source hash from the preview")
    migration.add_argument(
        "--apply", action="store_true", help="Import the selected hash"
    )
    migration.add_argument("--json", action="store_true", help="Print a JSON receipt")
    add_memory_command(
        add_parser("memory", help="Inspect or change user/project memory")
    )
    demo = add_parser("conversation-demo", help="Write a synthetic chat cassette")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument(
        "--multiline", action="store_true", help="Record a multiline code-block prompt"
    )
    review_demo = add_parser(
        "conversation-review-demo", help="Write a synthetic chat and review packet"
    )
    review_demo.add_argument("--output", type=Path, required=True)
    review_demo.add_argument("--review-output", type=Path, required=True)
    for generator in (demo, review_demo):
        add_memory_options(generator)
        generator.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    for name in ("chat", "resume", "sessions", "session-delete"):
        command = add_parser(name, help="Recorded conversation terminal preview")
        if name == "resume":
            selection = command.add_mutually_exclusive_group(required=True)
            selection.add_argument("session_id", nargs="?")
            selection.add_argument("--last", action="store_true")
            command.add_argument(
                "--inspect",
                action="store_true",
                help="Inspect a bounded SQLite working set without resuming work",
            )
            command.add_argument(
                "--refresh-memory",
                action="store_true",
                help="Apply current memory, or disable it with --no-memory",
            )
            command.add_argument(
                "--refresh-cassette",
                type=Path,
                help="Replacement recording preserving consumed exchanges",
            )
        if name == "session-delete":
            command.add_argument("session_id")
            command.add_argument("--expected-sha256", required=True)
        if name in {"chat", "resume"}:
            add_memory_options(command)
            command.add_argument(
                "--session-max-bytes",
                type=snapshot_byte_limit,
                help="Save a per-session snapshot budget (64000–32000000 bytes)",
            )
            command.add_argument(
                "--context-max-bytes",
                type=context_byte_limit,
                help="Save a chat context budget (4000–1000000 bytes; default 256000)",
            )
            command.add_argument(
                "--cassette",
                type=Path,
                help="Use an explicit recording instead of the built-in preview",
            )
            command.add_argument("--review-packet", type=Path)
            display = command.add_mutually_exclusive_group()
            display.add_argument(
                "--tui",
                action="store_true",
                help="Open the full-screen recorded terminal",
            )
            display.add_argument(
                "--plain", action="store_true", help="Use line-oriented terminal input"
            )
        if name in {"sessions", "resume"}:
            command.add_argument(
                "--catalog-max-bytes",
                type=catalog_byte_limit,
                help="Bound listing/latest scan bytes (default 8000000; max 128000000)",
            )
        if name == "sessions":
            command.add_argument("--limit", type=int, help="SQLite page size (1–100)")
            command.add_argument("--cursor", help="Continue a SQLite metadata page")
        command.add_argument(
            "--storage-backend",
            choices=("snapshot", "sqlite"),
            default="snapshot",
            help="Session backend (default: snapshot; SQLite is opt-in)",
        )
        command.add_argument(
            "--storage",
            type=Path,
            default=Path.home() / ".mos-eisley-sessions",
            help="Private session directory (default: ~/.mos-eisley-sessions)",
        )
        command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
        command.add_argument(
            "--json", action="store_true", help="Print NDJSON lifecycle events"
        )


def _input_reader(
    fd: int, queue: asyncio.Queue[str | Exception | None]
) -> Callable[[], None]:
    loop = asyncio.get_running_loop()
    regular = stat.S_ISREG(os.fstat(fd).st_mode)

    async def produce() -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        pending = ""
        try:
            while True:
                if not regular:
                    ready: asyncio.Future[None] = loop.create_future()

                    def readable(waiter: asyncio.Future[None] = ready) -> None:
                        if not waiter.done():
                            waiter.set_result(None)

                    loop.add_reader(fd, readable)
                    try:
                        await ready
                    finally:
                        loop.remove_reader(fd)
                chunk = os.read(fd, 4096)
                pending += decoder.decode(chunk, final=not chunk)
                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    line = line.rstrip("\r")
                    if len(line) > 8000:
                        raise ValueError("terminal message exceeds text limit")
                    # Pause reading while the bounded consumer queue is full.
                    await queue.put(line)
                if len(pending) > 8000:
                    raise ValueError("terminal message exceeds text limit")
                if not chunk:
                    if pending:
                        await queue.put(pending)
                    await queue.put(None)
                    return
                if regular:
                    await asyncio.sleep(0)
        except (OSError, UnicodeError, ValueError):
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(ValueError("invalid or excessive terminal input"))

    task = asyncio.create_task(produce())

    def stop() -> None:
        task.cancel()

    return stop


async def terminal(
    controller: ConversationController,
    queue: ConversationInputQueue,
    emit: Callable[[dict[str, object]], None],
    review_packet: ConversationReviewPacket | None = None,
    refresh_memory: Callable[[bool], None] | None = None,
) -> None:
    """The same controller serves the human and NDJSON renderers."""
    seen: dict[int, str] = {}
    composer = ConversationComposer()

    def discard_draft(reason: str) -> None:
        if composer.active:
            composer.clear()
            emit({"type": "composer.discarded", "text": reason})

    def has_capacity() -> bool:
        if len(controller.state.entries) >= 16:
            emit(
                {
                    "type": "conversation.unavailable",
                    "text": "Session message limit reached; start a new conversation.",
                }
            )
            return False
        return True

    def submit_review() -> bool:
        if review_packet is None:
            emit(
                {
                    "type": "conversation.unavailable",
                    "text": ("Review requires an explicit --review-packet at startup."),
                }
            )
            return False
        if not has_capacity():
            return False
        controller.submit_review(review_packet)
        render()
        return True

    def submit_text(text: str, *, require_active: bool = False) -> bool:
        if not text.strip() or len(text) > 8000 or text.count("\n") >= 256:
            emit(
                {
                    "type": "conversation.unavailable",
                    "text": (
                        "Message requires text within 8,000 characters and 256 lines."
                    ),
                }
            )
            return False
        if require_active and (
            controller.active_chat_index is None or not text.strip()
        ):
            emit(
                {
                    "type": "conversation.unavailable",
                    "text": "/steer TEXT requires text and an active chat request.",
                }
            )
            return False
        if not has_capacity():
            return False
        if require_active:
            controller.steer(text)
        else:
            controller.submit(text)
        render()
        return True

    def compose(line: str) -> bool:
        """Handle drafts before intent routing; submitted draft text stays literal."""
        nonlocal enabled
        message: str | None = None
        try:
            if line == "/compose":
                composer.begin()
                emit(
                    {
                        "type": "composer.started",
                        "text": (
                            "Draft open. /send submits; /discard clears. "
                            "Use // to escape a leading slash."
                        ),
                    }
                )
            elif line == "/discard":
                if not composer.active:
                    raise ValueError("No draft is open; use /compose to start one.")
                discard_draft("Unsent draft discarded.")
            elif line == "/send":
                message = composer.message()
            elif composer.active:
                composer.append(line[1:] if line.startswith("//") else line)
                emit(
                    {
                        "type": "composer.updated",
                        "lines": len(composer.lines),
                        "characters": composer.characters,
                        "text": (
                            f"Draft: {len(composer.lines)} lines, "
                            f"{composer.characters} characters. /send or /discard."
                        ),
                    }
                )
            else:
                return False
        except ValueError as exc:
            emit({"type": "composer.error", "text": str(exc)})
            return True
        # Storage errors propagate; only input errors become recoverable notices.
        if message is not None and submit_text(message):
            composer.clear()
            emit({"type": "composer.sent", "text": "Draft queued."})
            enabled = True
        return True

    def render() -> None:
        for index, entry in enumerate(controller.state.entries):
            if seen.get(index) != entry.status:
                seen[index] = entry.status
                event: dict[str, object] = {
                    "type": f"message.{entry.status}",
                    "index": index,
                    "text": entry.text,
                    "answer": entry.answer,
                }
                if entry.steering_for is not None:
                    event["steering_for"] = entry.steering_for
                if entry.review_packet is not None:
                    event["review_brief_id"] = entry.review_packet.brief.brief_id
                if entry.review_result is not None:
                    event["review_result"] = entry.review_result.model_dump(mode="json")
                emit(event)

    render()
    incoming: asyncio.Task[ConversationInput] | None = asyncio.create_task(queue.get())
    active: asyncio.Task[bool] | None = None
    enabled = False  # Resume displays pending input; only explicit input starts work.
    eof = False
    try:
        while True:
            if (
                enabled
                and active is None
                and any(entry.status == "queued" for entry in controller.state.entries)
            ):
                active = asyncio.create_task(controller.step(on_started=render))
            if eof and active is None:
                return
            if incoming is None and active is not None:
                # Keep accepting Ctrl-C while finishing work after stdin closes.
                incoming = asyncio.create_task(queue.get())
            pending = {task for task in (incoming, active) if task is not None}
            if not pending:
                return
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            if active in done:
                assert active is not None
                try:
                    active.result()
                except (AgentFailure, ValueError) as exc:
                    enabled = False
                    message = "Recorded request failed; continuation is paused."
                    if isinstance(exc, MemoryChangedError):
                        message = MEMORY_CHANGED_MESSAGE
                    elif isinstance(exc, ContextBudgetError):
                        message = str(exc)
                    elif isinstance(exc, RequestBudgetError):
                        message = (
                            f"Model request needs {exc.required_bytes} bytes; "
                            f"provider input limit is {exc.maximum_bytes}. "
                            "Message remains queued; no attempt was consumed. "
                            "Storage/context resizing cannot raise this limit. "
                            "Start a fresh session with the required task context."
                        )
                    emit(
                        {
                            "type": "conversation.error",
                            "text": message,
                        }
                    )
                active = None
                render()
            if incoming in done:
                assert incoming is not None
                line = incoming.result()
                incoming = None
                if isinstance(line, Exception):
                    raise line
                if isinstance(line, ConversationSubmission):
                    if line.accepted.cancelled():
                        incoming = asyncio.create_task(queue.get())
                        continue
                    try:
                        if (
                            not line.literal
                            and len(line.text) <= 8000
                            and line.text.count("\n") < 256
                            and line.text.strip().casefold().rstrip(".")
                            == "review this change"
                        ):
                            accepted = submit_review()
                        else:
                            accepted = submit_text(line.text)
                        if not line.accepted.done():
                            line.accepted.set_result(accepted)
                        enabled = enabled or accepted
                    except BaseException:
                        line.accepted.cancel()
                        raise
                    incoming = asyncio.create_task(queue.get())
                    continue
                if line is None:
                    discard_draft("Input closed; unsent draft discarded.")
                    eof = True
                    continue  # Finish already enabled messages on EOF, then save/exit.
                if line in {"/stop", "/quit"}:
                    discard_draft("Unsent draft discarded.")
                    enabled = False
                    if active is not None:
                        active.cancel()
                        with suppress(asyncio.CancelledError):
                            await active
                        active = None
                    if line == "/stop":
                        controller.cancel_queued()
                    render()
                    if line == "/quit":
                        return
                elif compose(line):
                    pass
                elif line == "/continue":
                    enabled = True
                elif line in {"/memory refresh", "/memory off"}:
                    if active is not None:
                        emit(
                            {
                                "type": "conversation.unavailable",
                                "text": "Stop active work before refreshing memory.",
                            }
                        )
                    elif refresh_memory is None:
                        emit(
                            {
                                "type": "conversation.unavailable",
                                "text": "Memory refresh is not configured here.",
                            }
                        )
                    else:
                        try:
                            refresh_memory(line == "/memory off")
                        except MemoryRefreshError as exc:
                            emit({"type": "conversation.unavailable", "text": str(exc)})
                        else:
                            enabled = False
                            emit(
                                {
                                    "type": "conversation.memory.updated",
                                    "text": (
                                        "Memory selection saved. Work is paused; "
                                        "/continue resumes queued messages."
                                    ),
                                }
                            )
                elif line == "/memory":
                    emit(
                        {
                            "type": "conversation.memory",
                            "text": (
                                controller.state.memory.describe()
                                if controller.state.memory is not None
                                else "No memory is active in this session."
                            ),
                        }
                    )
                elif line == "/directory":
                    emit(
                        {
                            "type": "conversation.directory",
                            "text": controller.state.workspace,
                        }
                    )
                elif line == "/steer" or line.startswith("/steer "):
                    if submit_text(
                        line.removeprefix("/steer").lstrip(), require_active=True
                    ):
                        enabled = True
                elif line.strip().casefold().rstrip(".") in {
                    "/review",
                    "review this change",
                }:
                    enabled = submit_review() or enabled
                elif line.strip():
                    if line.startswith("/"):
                        emit(
                            {
                                "type": "conversation.help",
                                "text": (
                                    "Commands: /compose, /send, /discard, "
                                    "/steer TEXT, /review, /memory, /directory, "
                                    "/stop, /continue, /quit"
                                ),
                            }
                        )
                    else:
                        if submit_text(line):
                            enabled = True
                incoming = asyncio.create_task(queue.get())
    finally:
        discard_draft("Session closed; unsent draft discarded.")
        for task in (active, incoming):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        render()


async def _run_terminal(
    controller: ConversationController,
    emit: Callable[[dict[str, object]], None],
    review_packet: ConversationReviewPacket | None = None,
    refresh_memory: Callable[[bool], None] | None = None,
) -> None:
    queue: asyncio.Queue[str | Exception | None] = asyncio.Queue(maxsize=32)
    stop = _input_reader(sys.stdin.fileno(), queue)
    loop = asyncio.get_running_loop()
    previous = signal.getsignal(signal.SIGINT)

    def interrupt() -> None:
        nonlocal stop
        # Drop the reader's pending paste as well as the queued input on Ctrl-C.
        stop()
        stop = _input_reader(sys.stdin.fileno(), queue)
        # Ctrl-C must remain effective even when pasted input fills the queue.
        terminal_input: Exception | None = None
        input_ended = False
        while not queue.empty():
            item = queue.get_nowait()
            if item is None or isinstance(item, Exception):
                input_ended = True
                terminal_input = item
        queue.put_nowait("/stop")
        if input_ended:
            queue.put_nowait(terminal_input)

    loop.add_signal_handler(signal.SIGINT, interrupt)
    try:
        await terminal(controller, queue, emit, review_packet, refresh_memory)
    finally:
        stop()
        loop.remove_signal_handler(signal.SIGINT)
        signal.signal(signal.SIGINT, previous)


def run_command(args: argparse.Namespace) -> int:
    if args.command == "session-artifact":
        artifact = read_sqlite_artifact(
            args.storage, args.workspace, args.selection, max_bytes=args.max_bytes
        )
        print(
            json.dumps(
                {"type": "conversation.artifact", **artifact.model_dump(mode="json")},
                ensure_ascii=True,
                indent=None if args.json else 2,
            )
        )
        return 0
    if args.command == "session-transcript":
        if args.prepare:
            if (
                args.expected_sha256 is None
                or args.cursor is not None
                or args.limit is not None
            ):
                raise ValueError(
                    "--prepare requires --expected-sha256 "
                    "and cannot use --cursor or --limit"
                )
            with SQLiteConversationStore(
                args.storage,
                args.session_id,
                args.workspace,
                create=False,
                require_workspace=False,
            ) as store:
                summary = store.prepare_transcript(args.expected_sha256)
            result = {
                "type": "conversation.transcript_prepared",
                **summary.model_dump(),
            }
        else:
            if args.expected_sha256 is not None:
                raise ValueError("--expected-sha256 requires --prepare")
            page = read_sqlite_transcript(
                args.storage,
                args.session_id,
                args.workspace,
                limit=4 if args.limit is None else args.limit,
                cursor=args.cursor,
            )
            result = {"type": "conversation.transcript", **page.model_dump(mode="json")}
        print(json.dumps(result, ensure_ascii=True, indent=None if args.json else 2))
        return 0
    if args.command == "session-migrate":
        if args.apply and args.expected_sha256 is None:
            raise ValueError("--apply requires --expected-sha256 from a preview")
        with ConversationMigration(
            args.storage, args.session_id, args.workspace
        ) as migration:
            receipt = migration.migrate(
                expected_sha256=args.expected_sha256, apply=args.apply
            )
        payload = {"type": "conversation.migration", **receipt.model_dump(mode="json")}
        print(json.dumps(payload, ensure_ascii=True, indent=None if args.json else 2))
        return 0
    if args.command == "memory":
        from mos_eisley.memory_cli import run_command as run_memory

        return run_memory(args)
    sqlite_backend = getattr(args, "storage_backend", "snapshot") == "sqlite"
    if getattr(args, "catalog_max_bytes", None) is not None and sqlite_backend:
        raise ValueError(
            "--catalog-max-bytes applies to snapshot storage; SQLite uses --limit"
        )
    if args.command == "resume" and args.inspect:
        if not sqlite_backend:
            raise ValueError("--inspect requires --storage-backend sqlite")
        if (
            args.refresh_memory
            or args.refresh_cassette is not None
            or args.session_max_bytes is not None
            or args.context_max_bytes is not None
            or args.cassette is not None
            or args.review_packet is not None
            or args.no_memory
            or args.tui
            or args.plain
        ):
            raise ValueError("--inspect cannot use session changes or terminal options")
        latest = None
        if args.last:
            page = list_sqlite_conversations(args.storage, args.workspace, limit=1)
            if not page.sessions:
                raise ValueError("No saved conversations in this workspace.")
            latest = page.sessions[0]
        inspection = inspect_sqlite_resume(
            args.storage,
            args.session_id if latest is None else latest.session_id,
            args.workspace,
            expected_sha256=None if latest is None else latest.snapshot_sha256,
        )
        print(
            json.dumps(
                {
                    "type": "conversation.resume_inspected",
                    **inspection.model_dump(mode="json"),
                },
                ensure_ascii=True,
                indent=None if args.json else 2,
            )
        )
        return 0
    if (
        args.command == "sessions"
        and (args.limit is not None or args.cursor is not None)
        and not sqlite_backend
    ):
        raise ValueError("--limit and --cursor require --storage-backend sqlite")
    store_type = SQLiteConversationStore if sqlite_backend else ConversationStore
    if getattr(args, "tui", False) and (
        args.json or not sys.stdin.isatty() or not sys.stdout.isatty()
    ):
        print(
            "mos-eisley: --tui requires terminal input/output and cannot use --json",
            file=sys.stderr,
        )
        return 2
    if (
        args.command == "resume"
        and args.refresh_cassette is not None
        and not args.refresh_memory
    ):
        print("--refresh-cassette requires --refresh-memory", file=sys.stderr)
        return 2
    memory = None
    if (
        args.command in {"chat", "conversation-demo", "conversation-review-demo"}
        and not args.no_memory
    ):
        memory = MemoryStore(args.memory_storage, args.workspace).load()
    if args.command == "conversation-review-demo":
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        result = asyncio.run(run_conversation_review(packet))
        private_write(
            args.output,
            canonical_bytes(demo_cassette(review_summary(result), memory=memory)),
        )
        private_write(args.review_output, canonical_bytes(packet))
        print(
            json.dumps(
                {
                    "cassette": str(args.output),
                    "review_packet": str(args.review_output),
                    "prompts": [DEMO_PROMPTS[0], "/review", REVIEW_FOLLOWUP],
                }
            )
        )
        return 0

    if args.command == "conversation-demo":
        private_write(
            args.output,
            canonical_bytes(demo_cassette(multiline=args.multiline, memory=memory)),
        )
        prompts = (
            (MULTILINE_PROMPT, DEMO_PROMPTS[1]) if args.multiline else DEMO_PROMPTS
        )
        print(json.dumps({"cassette": str(args.output), "prompts": prompts}))
        return 0

    def emit(event: dict[str, object]) -> None:
        if args.json:
            print(json.dumps(event, ensure_ascii=True), flush=True)
        else:
            # Escape control sequences in all untrusted terminal text.
            value = str(event.get("answer") or event.get("text") or event)
            safe = json.dumps(value, ensure_ascii=True)[1:-1]
            target = event.get("steering_for")
            label = "" if target is None else f" (steering message {target})"
            index = event.get("index")
            message_id = "" if index is None else f" [{index}]"
            print(f"{event['type']}{message_id}{label}: {safe}", flush=True)

    if args.command == "sessions":
        next_cursor = None
        if sqlite_backend:
            page = list_sqlite_conversations(
                args.storage,
                args.workspace,
                limit=50 if args.limit is None else args.limit,
                cursor=args.cursor,
            )
            summaries, next_cursor = page.sessions, page.next_cursor
        else:
            summaries = list_conversations(
                args.storage, args.workspace, max_bytes=args.catalog_max_bytes
            )
        if args.json:
            emit(
                {
                    "type": "conversations.listed",
                    "sessions": [
                        summary.model_dump(mode="json") for summary in summaries
                    ],
                    **({"next_cursor": next_cursor} if sqlite_backend else {}),
                }
            )
        elif not summaries:
            emit(
                {
                    "type": "conversations.listed",
                    "text": "No saved conversations in this workspace.",
                }
            )
        else:
            for summary in summaries:
                saved = datetime.fromtimestamp(
                    summary.modified_ns / 1e9, UTC
                ).isoformat()
                emit(
                    {
                        "type": "conversation.summary",
                        "text": (
                            f"{summary.session_id} | {saved} | "
                            f"{summary.messages} messages | "
                            f"{'active' if summary.active else 'available'} | "
                            f"{summary.snapshot_bytes}/"
                            f"{summary.snapshot_max_bytes} bytes | "
                            f"snapshot {summary.snapshot_sha256}"
                        ),
                    }
                )
        if next_cursor is not None and not args.json:
            emit(
                {
                    "type": "conversations.next",
                    "text": f"Next page: --cursor {next_cursor}",
                }
            )
        return 0
    if args.command == "session-delete":
        emit({"type": "conversation.storage", "text": str(args.storage.absolute())})
        with store_type(
            args.storage,
            args.session_id,
            args.workspace,
            create=False,
            require_workspace=False,
        ) as store:
            receipt = store.delete(args.expected_sha256)
        emit(
            {
                "type": "conversation.deleted",
                **receipt.model_dump(mode="json"),
                "text": f"Deleted saved session {receipt.session_id}.",
            }
        )
        return 0

    explicit_cassette = (
        None
        if args.cassette is None
        else AgentCassette.model_validate_json(read_bounded(args.cassette))
    )
    review_packet = (
        ConversationReviewPacket.model_validate_json(
            read_bounded(args.review_packet, MAX_REVIEW_PACKET_BYTES)
        )
        if args.review_packet is not None
        else None
    )
    fresh: ConversationState | None = None
    selected: ConversationSummary | None = None
    if args.command == "chat":
        cassette = explicit_cassette or demo_cassette(memory=memory)
        fresh = ConversationController.fresh(
            args.workspace,
            cassette,
            memory,
            memory_disabled=args.no_memory,
            snapshot_max_bytes=args.session_max_bytes,
            context_max_bytes=args.context_max_bytes,
        )
        session_id = fresh.session_id
    elif args.last:
        summaries = (
            list_sqlite_conversations(args.storage, args.workspace, limit=1).sessions
            if sqlite_backend
            else list_conversations(
                args.storage, args.workspace, max_bytes=args.catalog_max_bytes
            )
        )
        if not summaries:
            emit(
                {
                    "type": "conversation.unavailable",
                    "text": "No saved conversations in this workspace.",
                }
            )
            return 2
        selected = summaries[0]
        session_id = selected.session_id
    else:
        session_id = args.session_id
    emit({"type": "conversation.storage", "text": str(args.storage.absolute())})
    with store_type(
        args.storage, session_id, args.workspace, create=fresh is not None
    ) as store:
        if fresh is not None:
            store.save(fresh)
        state = fresh if fresh is not None else store.load()
        if (
            selected is not None
            and digest(canonical_bytes(state)) != selected.snapshot_sha256
        ):
            raise ValueError("selected latest conversation changed; list again")
        selected_refresh = args.command == "resume" and args.refresh_memory
        ignore_memory = args.no_memory or (
            state.memory_disabled and not selected_refresh
        )
        memory_store = MemoryStore(args.memory_storage, args.workspace)
        if args.command == "resume":
            memory = None if ignore_memory else memory_store.load()
        cassette = (
            explicit_cassette
            or state.retained_cassette
            or demo_cassette(memory=state.memory)
        )
        if state.memory != memory and not selected_refresh:
            print(MEMORY_CHANGED_MESSAGE, file=sys.stderr)
            return 2
        controller = ConversationController(state, cassette, store.save)
        memory_runtime = ConversationMemoryRuntime(
            controller,
            memory_store,
            lambda selected: demo_cassette(memory=selected),
            ignore_memory=ignore_memory,
        )
        controller.validate_memory = memory_runtime.check
        if selected_refresh:
            replacement = (
                None
                if args.refresh_cassette is None
                else AgentCassette.model_validate_json(
                    read_bounded(args.refresh_cassette)
                )
            )
            try:
                memory_runtime.refresh(
                    args.no_memory,
                    replacement=replacement,
                    snapshot_max_bytes=args.session_max_bytes,
                )
            except MemoryRefreshError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        elif args.command == "resume" and args.session_max_bytes is not None:
            controller.resize_storage(args.session_max_bytes)
        if args.command == "resume" and args.context_max_bytes is not None:
            controller.resize_context(args.context_max_bytes)
        emit(
            {
                "type": "conversation.opened",
                "session_id": session_id,
                "text": (
                    f"Session {session_id}. Recorded preview. "
                    "Commands: /compose, /send, /discard, "
                    "/steer TEXT, /review, /stop, /continue, /quit. "
                    "Ctrl-C stops work."
                ),
            }
        )
        welcome = "Recorded preview: live conversations are not connected yet.\n" + (
            "Try these messages in order:\n" + "\n".join(DEMO_PROMPTS)
            if memory_runtime.builtin
            else "Use the messages expected by your selected recording."
        )
        welcome += (
            "\nMemory was disabled at startup."
            if memory_runtime.ignore_memory
            else f"\nMemory storage: {args.memory_storage.absolute()}"
        )
        welcome += (
            "\n/memory inspects context; /memory refresh applies changes; "
            "/memory off disables it."
        )
        welcome += (
            f"\nSession snapshot budget: {controller.state.snapshot_byte_limit} bytes."
        )
        welcome += (
            f"\nChat context budget: {controller.state.context_byte_limit} bytes "
            "(system and history JSON; separate from storage and tokens)."
        )
        if sqlite_backend:
            welcome += (
                "\nStorage: SQLite (logical snapshot budget; incremental records)."
            )
        if args.tui or (
            not args.plain
            and not args.json
            and sys.stdin.isatty()
            and sys.stdout.isatty()
        ):
            from mos_eisley.conversation_tui import ConversationTUI

            fd = sys.stdin.fileno()
            original_modes = termios.tcgetattr(fd)
            try:
                asyncio.run(
                    ConversationTUI(
                        controller,
                        review_packet,
                        welcome=welcome,
                        refresh_memory=memory_runtime.refresh,
                        load_transcript=store.transcript_page
                        if isinstance(store, SQLiteConversationStore)
                        else None,
                        load_artifact=store.transcript_artifact
                        if isinstance(store, SQLiteConversationStore)
                        else None,
                    ).run()
                )
            finally:
                termios.tcsetattr(fd, termios.TCSANOW, original_modes)
        else:
            emit({"type": "conversation.welcome", "text": welcome})
            asyncio.run(
                _run_terminal(controller, emit, review_packet, memory_runtime.refresh)
            )
        emit(
            {
                "type": "conversation.saved",
                "session_id": session_id,
                "text": f"Saved session {session_id}.",
            }
        )
    return 0
