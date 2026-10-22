"""Public exec journeys run unchanged from source and the installed wheel."""

import asyncio
import io
import json
import os
import signal
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from mos_eisley.conversation import (
    ConversationController,
    conversation_config,
    prepare_conversation_request,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.core.models import JudgeDecision, canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.demo import demo_inputs
from mos_eisley.exec_cli import ExecOutput, error_code, execute
from mos_eisley.exec_cli import main as exec_main
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot
from mos_eisley.run.spend_ledger import LedgerEntry, SpendBudgetError, SpendLedger
from mos_eisley.tools.none import NoToolsDispatcher


class ExecProcessTests(TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory(prefix="mos-exec-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def command(self, *args: str) -> list[str]:
        return [
            str(Path(sys.executable).with_name("mos")),
            "exec",
            "--json",
            "--no-memory",
            "--storage",
            str(self.root / "sessions"),
            "-C",
            str(self.root),
            *args,
        ]

    def invoke(
        self, *args: str, data: bytes = b""
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            self.command(*args),
            input=data,
            capture_output=True,
            cwd=self.root,
            env={**os.environ, "HOME": str(self.root)},
            timeout=20,
        )

    def result(
        self, process: subprocess.CompletedProcess[bytes], code: int
    ) -> dict[str, object]:
        self.assertEqual(process.returncode, code, process.stderr.decode())
        events = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(
            [event["sequence"] for event in events], list(range(1, len(events) + 1))
        )
        self.assertTrue(all(event["schema_version"] == 1 for event in events))
        self.assertEqual(sum(event["type"] == "exec.result" for event in events), 1)
        self.assertEqual(events[-1]["type"], "exec.result")
        self.assertEqual(events[-1]["exit_code"], code)
        self.assertEqual(bool(process.stderr), code != 0)
        return events[-1]

    def test_positional_and_pipe_use_identical_controller_on_both_stores(self) -> None:
        for backend in ("snapshot", "sqlite"):
            for piped in (False, True):
                with self.subTest(backend=backend, piped=piped):
                    args = ["--storage-backend", backend]
                    data = b""
                    if piped:
                        args.append("--stdin")
                        data = DEMO_PROMPTS[0].encode()
                    else:
                        args.append(DEMO_PROMPTS[0])
                    result = self.result(self.invoke(*args, data=data), 0)
                    self.assertEqual(result["answer"], "The fixture boundary is ten.")
                    self.assertEqual(result["status"], "completed")
                    self.assertEqual(result["review_status"], "not_requested")
                    self.assertIsNone(result["review_verdict"])
                    self.assertEqual(result["usage_status"], "observed")
                    self.assertEqual(result["omissions_status"], "known")
                    self.assertEqual(result["omissions"], [])
                    session = str(result["session_id"])
                    if backend == "sqlite":
                        with SQLiteConversationStore(
                            self.root / "sessions",
                            session,
                            self.root,
                            create=False,
                            writable=False,
                        ) as store:
                            state = store.inspect_snapshot()[0].state
                    else:
                        state = ConversationSnapshot.model_validate_json(
                            (self.root / "sessions" / f"{session}.json").read_bytes()
                        ).state
                    self.assertEqual(state.entries[0].text, DEMO_PROMPTS[0])
                    self.assertEqual(state.entries[0].status, "completed")
                    self.assertEqual(state.exchanges_consumed, 1)

    def test_invalid_input_never_creates_session(self) -> None:
        cases: list[tuple[list[str], bytes]] = [
            ([], b""),
            ([], b"\xff"),
            ([], b"x" * 8001),
            ([], "é".encode() * 4001),
            ([], b" \n"),
            ([DEMO_PROMPTS[0]], b"another input"),
            (["--stdin", DEMO_PROMPTS[0]], b""),
            (["--unknown", "PRIVATE-REJECTED-INPUT"], b""),
            (["--tui", DEMO_PROMPTS[0]], b""),
            (["--stdin"], b"line\n" * 257),
        ]
        for args, data in cases:
            with self.subTest(args=args, size=len(data)):
                result = self.result(self.invoke(*args, data=data), 2)
                self.assertEqual(result["status"], "invalid_input")
                self.assertIsNone(result["session_id"])
                self.assertFalse((self.root / "sessions").exists())

    def test_implicit_stdin_and_dash_are_literal_inputs(self) -> None:
        for args in ((), ("-",)):
            self.result(self.invoke(*args, data=DEMO_PROMPTS[0].encode()), 0)
        # A slash command in input is never evaluated by a command interpreter.
        result = self.result(self.invoke(data=b"/review"), 1)
        self.assertEqual(result["review_status"], "not_requested")
        self.assertIsNone(result["review_verdict"])

    def test_exact_utf8_boundary_and_newlines_survive_stdin(self) -> None:
        text = "é" * 3999 + "\nZ"
        self.assertEqual(len(text.encode()), 8000)
        request, _ = prepare_conversation_request(
            conversation_config((Turn(role="user", blocks=(TextBlock(text=text),)),)),
            NoToolsDispatcher(),
        )
        original = demo_cassette()
        recording = original.model_copy(
            update={
                "exchanges": (
                    original.exchanges[0].model_copy(
                        update={"request_sha256": digest(canonical_bytes(request))}
                    ),
                )
            }
        )
        path = self.root / "unicode.json"
        path.write_bytes(canonical_bytes(recording))
        result = self.result(
            self.invoke("--stdin", "--cassette", str(path), data=text.encode()), 0
        )
        retained = ConversationSnapshot.model_validate_json(
            (self.root / "sessions" / f"{result['session_id']}.json").read_bytes()
        )
        self.assertEqual(retained.state.entries[0].text, text)
        # Context admission must refuse before consuming the recorded exchange.
        limited = self.result(
            self.invoke(
                "--stdin",
                "--cassette",
                str(path),
                "--context-max-bytes",
                "4000",
                data=text.encode(),
            ),
            4,
        )
        saved = ConversationSnapshot.model_validate_json(
            (self.root / "sessions" / f"{limited['session_id']}.json").read_bytes()
        )
        self.assertEqual(saved.state.exchanges_consumed, 0)
        self.assertEqual(saved.state.entries[0].status, "queued")

    def test_plain_output_contains_only_answer(self) -> None:
        command = self.command(DEMO_PROMPTS[0])
        command.remove("--json")
        process = subprocess.run(
            command, input=b"", capture_output=True, cwd=self.root, timeout=20
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, b"")
        self.assertEqual(process.stdout, b"The fixture boundary is ten.\n")

    def test_provider_failure_retains_consumed_attempt(self) -> None:
        cassette = demo_cassette()
        broken = cassette.model_copy(
            update={
                "exchanges": (
                    cassette.exchanges[0].model_copy(update={"response": None}),
                )
            }
        )
        path = self.root / "failure.json"
        path.write_bytes(canonical_bytes(broken))
        result = self.result(self.invoke("--cassette", str(path), DEMO_PROMPTS[0]), 1)
        state = ConversationSnapshot.model_validate_json(
            (self.root / "sessions" / f"{result['session_id']}.json").read_bytes()
        ).state
        self.assertEqual(state.exchanges_consumed, 1)
        self.assertEqual(state.entries[0].status, "failed")
        self.assertEqual(result["usage_status"], "unavailable")
        self.assertIsNone(result["answer"])

    def test_complete_review_verdict_is_distinct_from_exit_success(self) -> None:
        brief, cassette = demo_inputs()
        for verdict in ("accept", "revise", "infrastructure_error"):
            with self.subTest(verdict=verdict):
                selected = cassette
                if verdict == "accept":
                    selected = cassette.model_copy(
                        update={
                            "judge_response": JudgeDecision(
                                upheld=(), rationale="Synthetic dismissed finding."
                            )
                        }
                    )
                elif verdict == "infrastructure_error":
                    selected = cassette.model_copy(
                        update={
                            "critics": (
                                cassette.critics[0].model_copy(
                                    update={"response": None}
                                ),
                                cassette.critics[1],
                            )
                        }
                    )
                packet = ConversationReviewPacket(brief=brief, cassette=selected)
                path = self.root / "review.json"
                path.write_bytes(canonical_bytes(packet))
                result = self.result(
                    self.invoke("--review", "--review-packet", str(path)),
                    5 if verdict == "infrastructure_error" else 0,
                )
                self.assertEqual(result["review_verdict"], verdict)
                self.assertEqual(
                    result["review_status"],
                    "incomplete" if verdict == "infrastructure_error" else "completed",
                )
                self.assertEqual(result["review_mode"], "recorded_conversation_review")
                self.assertIsNone(result["usage"])
                retained = (
                    ConversationSnapshot.model_validate_json(
                        (
                            self.root / "sessions" / f"{result['session_id']}.json"
                        ).read_bytes()
                    )
                    .state.entries[0]
                    .review_result
                )
                assert retained is not None
                self.assertEqual(
                    result["review_result_sha256"], digest(canonical_bytes(retained))
                )

    def test_budget_and_policy_denial_have_distinct_codes(self) -> None:
        result = self.result(
            self.invoke("--pending-text-max-bytes", "4000", "x" * 4001), 4
        )
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertFalse((self.root / "sessions").exists())
        result = self.result(self.invoke("--live-openai", DEMO_PROMPTS[0]), 3)
        self.assertEqual(result["status"], "policy_denied")
        self.assertFalse((self.root / "sessions").exists())

    def test_interrupt_while_reading_pipe_has_one_terminal_result(self) -> None:
        process = subprocess.Popen(
            self.command("--stdin"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.root,
            env={**os.environ, "HOME": str(self.root)},
        )
        try:
            assert process.stdout is not None
            first = process.stdout.readline()
            self.assertEqual(json.loads(first)["type"], "exec.input_requested")
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=10)
            result = self.result(
                subprocess.CompletedProcess(
                    process.args, process.returncode, first + stdout, stderr
                ),
                130,
            )
            self.assertEqual(result["status"], "cancelled")
            self.assertFalse((self.root / "sessions").exists())
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

    def test_closed_output_during_error_returns_failure_without_traceback(self) -> None:
        process = subprocess.Popen(
            self.command("--stdin"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.root,
        )
        try:
            assert process.stdout is not None and process.stdin is not None
            self.assertEqual(
                json.loads(process.stdout.readline())["type"], "exec.input_requested"
            )
            process.stdout.close()
            process.stdin.write(b"\xff")
            process.stdin.close()
            self.assertEqual(process.wait(timeout=15), 1)
            assert process.stderr is not None
            self.assertNotIn(b"Traceback", process.stderr.read())
            self.assertFalse((self.root / "sessions").exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


class ExecControllerTests(IsolatedAsyncioTestCase):
    async def test_lost_completion_save_does_not_claim_a_durable_answer(self) -> None:
        saves = 0

        def save(_state: object) -> None:
            nonlocal saves
            saves += 1
            if saves == 3:
                raise OSError("synthetic lost acknowledgement")

        cassette = demo_cassette()
        controller = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette), cassette, save
        )
        output = ExecOutput(True)
        with redirect_stdout(io.StringIO()), self.assertRaises(OSError):
            await execute(controller, output, DEMO_PROMPTS[0], None)
        self.assertEqual(output.result["persistence_status"], "uncertain")
        self.assertIsNone(output.result["answer"])
        self.assertIsNone(output.result["usage"])
        self.assertEqual(controller.state.entries[0].status, "running")
        self.assertEqual(controller.state.exchanges_consumed, 1)

    async def test_unexpected_startup_failure_emits_one_sanitized_result(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b""))),
            patch(
                "mos_eisley.conversation_cli.run_command",
                side_effect=RuntimeError("PRIVATE-EXCEPTION-PAYLOAD"),
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = exec_main(["--json", "--no-memory", DEMO_PROMPTS[0]])
        self.assertEqual(code, 1)
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(sum(event["type"] == "exec.result" for event in events), 1)
        self.assertEqual(events[-1]["status"], "failed")
        self.assertNotIn(
            "PRIVATE-EXCEPTION-PAYLOAD", stdout.getvalue() + stderr.getvalue()
        )

    async def test_cancellation_retains_attempt_and_waits_for_cleanup(self) -> None:
        started, cleaned = asyncio.Event(), asyncio.Event()

        async def waiting(*_args: object, **_kwargs: object) -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        cassette: AgentCassette = demo_cassette()
        controller = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette), cassette, lambda _: None
        )
        output = ExecOutput(True)
        with (
            patch("mos_eisley.conversation.run_agent", side_effect=waiting),
            redirect_stdout(io.StringIO()),
        ):
            task = asyncio.create_task(
                execute(controller, output, DEMO_PROMPTS[0], None)
            )
            await started.wait()
            # Exercise real OS handlers and repeated signals during cleanup.
            os.kill(os.getpid(), signal.SIGINT)
            os.kill(os.getpid(), signal.SIGINT)
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(cleaned.is_set())
        self.assertEqual(controller.state.entries[0].status, "cancelled")
        self.assertEqual(controller.state.exchanges_consumed, 1)
        self.assertFalse(await controller.step())
        self.assertEqual(
            error_code(asyncio.CancelledError(), output), (130, "cancelled")
        )

    async def test_aggregate_budget_error_keeps_existing_ledger_and_typed_cause(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            ledger = SpendLedger.create(Path(directory) / "ledger.sqlite", 10)
            entry = LedgerEntry(
                entry_id="1" * 64,
                reservation_sha256="2" * 64,
                reserved_microusd=9,
            )
            ledger.reserve(entry)
            with self.assertRaises(SpendBudgetError) as caught:
                ledger.reserve(entry.model_copy(update={"entry_id": "3" * 64}))
            self.assertEqual(ledger.snapshot().charged_microusd, 9)
            self.assertEqual(ledger.snapshot().unresolved_entries, 1)
            wrapped = ValueError("safe transport error")
            wrapped.__cause__ = caught.exception
            self.assertEqual(
                error_code(wrapped, ExecOutput(True)), (4, "budget_exhausted")
            )
