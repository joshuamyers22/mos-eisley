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
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from mos_eisley.conversation import (
    ConversationController,
    ConversationState,
    conversation_config,
)
from mos_eisley.core.agent import AgentFailure, build_request
from mos_eisley.core.budget import resolve_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelResponse, TextBlock, Turn, Usage
from mos_eisley.core.registry import fixture_registry
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write
from mos_eisley.tools.none import NoToolsDispatcher

DEMO_PROMPTS = (
    "Remember that the fixture boundary is ten.",
    "What boundary did I give you?",
)


def demo_cassette() -> AgentCassette:
    turns: tuple[Turn, ...] = ()
    exchanges: list[AgentExchange] = []
    for prompt, answer in zip(
        DEMO_PROMPTS,
        ("The fixture boundary is ten.", "You gave me a boundary of ten."),
        strict=True,
    ):
        turns += (Turn(role="user", blocks=(TextBlock(text=prompt),)),)
        config = conversation_config(turns)
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
    demo = add_parser("conversation-demo", help="Write a synthetic chat cassette")
    demo.add_argument("--output", type=Path, required=True)
    for name in ("chat", "resume"):
        command = add_parser(name, help="Recorded conversation terminal preview")
        if name == "resume":
            command.add_argument("session_id")
        command.add_argument("--cassette", type=Path, required=True)
        command.add_argument("--storage", type=Path, required=True)
        command.add_argument("--workspace", type=Path, default=Path.cwd())
        command.add_argument(
            "--json", action="store_true", help="Print NDJSON lifecycle events"
        )


def _input_reader(
    fd: int, queue: asyncio.Queue[str | Exception | None]
) -> Callable[[], None]:
    loop = asyncio.get_running_loop()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    pending = ""
    regular = stat.S_ISREG(os.fstat(fd).st_mode)
    stopped = False

    def stop() -> None:
        nonlocal stopped
        stopped = True
        if not regular:
            loop.remove_reader(fd)

    def readable() -> None:
        nonlocal pending
        if stopped:
            return
        try:
            chunk = os.read(fd, 4096)
            pending += decoder.decode(chunk, final=not chunk)
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                queue.put_nowait(line.rstrip("\r"))
            if len(pending) > 8000:
                raise ValueError("terminal message exceeds text limit")
            if not chunk:
                if pending:
                    queue.put_nowait(pending)
                queue.put_nowait(None)
                stop()
            elif regular:
                loop.call_soon(readable)
        except (OSError, UnicodeError, ValueError, asyncio.QueueFull):
            stop()
            # Reserve a terminal failure even when input overwhelmed the bounded queue.
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(ValueError("invalid or excessive terminal input"))

    if regular:
        loop.call_soon(readable)
    else:
        loop.add_reader(fd, readable)
    return stop


async def terminal(
    controller: ConversationController,
    queue: asyncio.Queue[str | Exception | None],
    emit: Callable[[dict[str, object]], None],
) -> None:
    """The same controller serves the human and NDJSON renderers."""
    seen: dict[int, str] = {}

    def render() -> None:
        for index, entry in enumerate(controller.state.entries):
            if seen.get(index) != entry.status:
                seen[index] = entry.status
                emit(
                    {
                        "type": f"message.{entry.status}",
                        "index": index,
                        "text": entry.text,
                        "answer": entry.answer,
                    }
                )

    render()
    incoming: asyncio.Task[str | Exception | None] | None = asyncio.create_task(
        queue.get()
    )
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
                except (AgentFailure, ValueError):
                    enabled = False
                    emit(
                        {
                            "type": "conversation.error",
                            "text": "Recorded request failed; continuation is paused.",
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
                if line is None:
                    eof = True
                    continue  # Finish already enabled messages on EOF, then save/exit.
                if line in {"/stop", "/quit"}:
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
                elif line == "/continue":
                    enabled = True
                elif line.strip():
                    if line.startswith("/"):
                        emit(
                            {
                                "type": "conversation.help",
                                "text": "Commands: /stop, /continue, /quit",
                            }
                        )
                    else:
                        controller.submit(line)
                        render()
                        enabled = True
                incoming = asyncio.create_task(queue.get())
    finally:
        for task in (active, incoming):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        render()


async def _run_terminal(
    controller: ConversationController, emit: Callable[[dict[str, object]], None]
) -> None:
    queue: asyncio.Queue[str | Exception | None] = asyncio.Queue(maxsize=32)
    stop = _input_reader(sys.stdin.fileno(), queue)
    loop = asyncio.get_running_loop()
    previous = signal.getsignal(signal.SIGINT)

    def interrupt() -> None:
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
        await terminal(controller, queue, emit)
    finally:
        stop()
        loop.remove_signal_handler(signal.SIGINT)
        signal.signal(signal.SIGINT, previous)


def run_command(args: argparse.Namespace) -> int:
    if args.command == "conversation-demo":
        private_write(args.output, canonical_bytes(demo_cassette()))
        print(json.dumps({"cassette": str(args.output), "prompts": DEMO_PROMPTS}))
        return 0

    def emit(event: dict[str, object]) -> None:
        if args.json:
            print(json.dumps(event, ensure_ascii=True), flush=True)
        else:
            # Escape control sequences in all untrusted terminal text.
            value = str(event.get("answer") or event.get("text") or event)
            safe = json.dumps(value, ensure_ascii=True)[1:-1]
            print(f"{event['type']}: {safe}", flush=True)

    cassette = AgentCassette.model_validate_json(read_bounded(args.cassette))
    fresh: ConversationState | None = None
    if args.command == "chat":
        fresh = ConversationController.fresh(args.workspace, cassette)
        session_id = fresh.session_id
    else:
        session_id = args.session_id
    emit({"type": "conversation.storage", "text": str(args.storage.absolute())})
    with ConversationStore(args.storage, session_id, args.workspace) as store:
        if fresh is not None:
            store.save(fresh)
        state = fresh if fresh is not None else store.load()
        controller = ConversationController(state, cassette, store.save)
        emit(
            {
                "type": "conversation.opened",
                "session_id": session_id,
                "text": (
                    f"Session {session_id}. Recorded preview. "
                    "Commands: /stop, /continue, /quit. "
                    "Ctrl-C stops work."
                ),
            }
        )
        asyncio.run(_run_terminal(controller, emit))
        emit(
            {
                "type": "conversation.saved",
                "session_id": session_id,
                "text": f"Saved session {session_id}.",
            }
        )
    return 0
