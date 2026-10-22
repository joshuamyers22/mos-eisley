"""One-shot rendering of the existing conversation controller, without a REPL."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import signal
import sys
from collections.abc import Sequence
from contextlib import redirect_stderr

from pydantic import ValidationError

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_context import ContextBudgetError
from mos_eisley.conversation_pending import PendingTextBudgetError
from mos_eisley.conversation_review import ReviewPacket
from mos_eisley.core.agent import AgentFailure, RequestBudgetError
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderBudgetError
from mos_eisley.run.spend_ledger import SpendBudgetError

MAX_INPUT_BYTES = 8_000


class ExecInputError(ValueError):
    """Invalid CLI input, before session creation or provider admission."""


def read_input(args: argparse.Namespace) -> str | None:
    """Read at most one extra byte; never decode with replacement or strip input."""
    prompt: str | None = args.prompt
    selected_stdin = args.stdin or prompt == "-"
    if prompt == "-":
        prompt = None
    if selected_stdin and prompt is not None:
        raise ExecInputError("Choose stdin or positional input.")
    if args.review and (selected_stdin or prompt is not None):
        raise ExecInputError("Review uses its frozen packet, not prompt text.")
    if selected_stdin and sys.stdin.isatty():
        raise ExecInputError("Stdin requires a pipe or redirected file.")
    raw = b"" if sys.stdin.isatty() else sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ExecInputError("Input exceeds 8,000 UTF-8 bytes.")
    if raw and (prompt is not None or args.review):
        raise ExecInputError(
            "Piped input cannot be combined with positional input or review."
        )
    if args.review:
        return None
    try:
        text = raw.decode("utf-8", errors="strict") if prompt is None else prompt
        encoded = text.encode("utf-8", errors="strict")
    except UnicodeError:
        raise ExecInputError("Input must be valid UTF-8.") from None
    if not text.strip() or len(encoded) > MAX_INPUT_BYTES or text.count("\n") >= 256:
        raise ExecInputError(
            "Input requires text within 8,000 UTF-8 bytes and 256 lines."
        )
    return text


class ExecOutput:
    """Bounded lifecycle output; the outer owner emits the terminal result once."""

    def __init__(self, json_output: bool) -> None:
        self.json_output = json_output
        self.sequence = 0
        self.started = False
        self.result: dict[str, object] = {
            "status": "failed",
            "review_status": "not_requested",
            "review_verdict": None,
            "session_id": None,
            "artifact_ids": [],
            "usage": None,
            "usage_status": "unavailable",
            "omissions": [],
            "omissions_status": "unavailable",
            "answer": None,
        }

    def event(self, payload: dict[str, object]) -> None:
        self.sequence += 1
        if self.json_output:
            print(
                json.dumps(
                    {**payload, "schema_version": 1, "sequence": self.sequence},
                    ensure_ascii=True,
                ),
                flush=True,
            )

    def capture(self, controller: RuntimeConversationController) -> None:
        state = controller.state
        self.result.update(
            session_id=state.session_id,
            mode=state.mode,
            persistence_status="uncertain"
            if controller.persistence_broken
            else "committed",
        )
        if not state.entries:
            return
        entry = state.entries[-1]
        # These are identities within the retained session, not new output files.
        self.result["artifact_ids"] = [
            f"{state.session_id}:entry:{len(state.entries) - 1}"
        ]
        if controller.persistence_broken:
            return
        self.result["answer"] = entry.answer
        self.result["usage"] = (
            None if entry.usage is None else entry.usage.model_dump(mode="json")
        )
        self.result["usage_status"] = (
            "observed" if entry.usage is not None else "unavailable"
        )
        if entry.request_admission is not None:
            self.result["omissions"] = [
                item.model_dump(mode="json")
                for item in entry.request_admission.selection.omitted
            ]
            self.result["omissions_status"] = "known"
        if entry.review_result is not None:
            verdict = entry.review_result.verdict.decision
            self.result["review_verdict"] = verdict
            self.result["review_status"] = (
                "incomplete" if verdict == "infrastructure_error" else "completed"
            )
            self.result["review_result_sha256"] = digest(
                canonical_bytes(entry.review_result)
            )

    def finish(self, code: int, status: str) -> int:
        self.result.update(status=status, exit_code=code)
        if self.json_output:
            self.event({"type": "exec.result", **self.result})
        elif self.result["answer"] is not None:
            # Escape terminal control characters as the conversation renderer does.
            print(
                json.dumps(str(self.result["answer"]), ensure_ascii=True)[1:-1],
                flush=True,
            )
        return code


async def execute(
    controller: RuntimeConversationController,
    output: ExecOutput,
    prompt: str | None,
    packet: ReviewPacket | None,
) -> int:
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    assert task is not None
    stopping = False

    def cancel() -> None:
        nonlocal stopping
        if not stopping:
            stopping = True
            task.cancel()

    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        loop.add_signal_handler(sig, cancel)
    try:
        output.result["review_mode"] = None if packet is None else packet.mode
        if packet is not None:
            controller.submit_review(packet)
        else:
            assert prompt is not None
            controller.submit(prompt)

        def started() -> None:
            output.started = True
            output.event(
                {
                    "type": "exec.started",
                    "session_id": controller.state.session_id,
                    "mode": controller.state.mode,
                    "operation": "review" if packet is not None else "chat",
                }
            )

        if not await controller.step(on_started=started):
            raise AgentFailure("No work was dispatched.")
        return 0
    finally:
        try:
            output.capture(controller)
        finally:
            for sig, handler in previous.items():
                loop.remove_signal_handler(sig)
                signal.signal(sig, handler)


def error_code(error: BaseException, output: ExecOutput) -> tuple[int, str]:
    if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)):
        return 130, "cancelled"
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(
            cause,
            (
                ContextBudgetError,
                PendingTextBudgetError,
                RequestBudgetError,
                SpendBudgetError,
                ProviderBudgetError,
            ),
        ):
            return 4, "budget_exhausted"
        cause = cause.__cause__
    if output.started and output.result["review_status"] == "incomplete":
        return 5, "review_incomplete"
    if isinstance(error, (ExecInputError, ValidationError)) and not output.started:
        return 2, "invalid_input"
    if isinstance(error, ValueError) and not output.started:
        return 3, "policy_denied"
    return 1, "failed"


def main(argv: Sequence[str]) -> int:
    try:
        return invoke(argv)
    except BrokenPipeError:
        # Prevent Python's final stdout flush from changing the exit to 120.
        # The consumer is gone; no terminal record or replay is possible.
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
        return 1


def invoke(argv: Sequence[str]) -> int:
    from mos_eisley.app_update_session import active_client
    from mos_eisley.cli import parser
    from mos_eisley.conversation_cli import run_command

    output = ExecOutput("--json" in argv)
    try:
        # argparse errors may echo rejected arguments; emit fixed diagnostics below.
        with redirect_stderr(io.StringIO()):
            try:
                args = parser().parse_args(["exec", *argv])
            except SystemExit as error:
                if error.code == 0:  # --help is a documentation request.
                    return 0
                raise ExecInputError(
                    "Invalid exec arguments; use mos exec --help."
                ) from None
        output.json_output = args.json
        if args.tui or args.choose_directory or args.git_review_panel:
            raise ExecInputError(
                "Exec requires noninteractive options; select a workspace with -C."
            )
        selected_reviews = sum(
            (args.review_packet is not None, args.live_review_selection is not None)
        )
        if args.review != bool(selected_reviews) or selected_reviews > 1:
            raise ExecInputError(
                "Use --review with one explicit review packet or live selection."
            )
        if args.live_coding_selection is not None or args.allow_live_coding:
            raise ExecInputError(
                "Exec does not dispatch the interactive implementation workflow."
            )
        input_source = (
            "stdin" if args.stdin or args.prompt in (None, "-") else "positional"
        )
        output.event(
            {
                "type": "exec.input_requested",
                "source": input_source,
                "max_bytes": MAX_INPUT_BYTES,
            }
        )
        args.prompt = read_input(args)
        if args.prompt is not None:
            output.result["input"] = {
                "source": input_source,
                "bytes": len(args.prompt.encode("utf-8")),
                "sha256": digest(args.prompt.encode("utf-8")),
            }
        if args.review:
            output.result["review_status"] = "incomplete"
        args.command = "chat"
        args.exec_output = output
        with active_client():
            code = run_command(args)
        if code != 0:
            raise OSError("Conversation startup did not complete.")
        return output.finish(0, "completed")
    except BrokenPipeError:
        raise
    except (Exception, KeyboardInterrupt, asyncio.CancelledError) as error:
        # This boundary owns the terminal record, including unexpected failures.
        # Never serialize exception payloads, source text or provider diagnostics.
        code, status = error_code(error, output)
        detail = (
            str(error)
            if isinstance(error, ExecInputError)
            else "See the retained session when available."
        )
        print(
            f"mos exec: {status}. {detail}",
            file=sys.stderr,
            flush=True,
        )
        return output.finish(code, status)
