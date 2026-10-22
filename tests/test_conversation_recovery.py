"""Real-store fault injection for the shared controller recovery contract."""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_recovery import (
    RecoveryJournal,
    operation_id,
    uncertain_notice,
)
from mos_eisley.conversation_state import LiveChatIdentity
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.agent import AgentConfig, AgentResult, run_agent
from mos_eisley.core.dispatch_guard import dispatch_guard, revalidate_dispatch
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.core.registry import fixture_registry
from mos_eisley.demo_agent import agent_demo_inputs
from mos_eisley.exec_cli import ExecOutput
from mos_eisley.providers.agent_recorded import RecordedAgentClient
from mos_eisley.run.conversation_resume import inspect_sqlite_resume
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.tools.fixture import FixtureDispatcher


class WaitingClient:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        response = demo_cassette().exchanges[0].response
        assert response is not None
        return response


class RecoveryTests(IsolatedAsyncioTestCase):
    async def test_uncertain_live_call_keeps_full_real_ledger_hold(self) -> None:
        for backend in (ConversationStore, SQLiteConversationStore):
            with (
                self.subTest(backend=backend.__name__),
                TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                ledger = SpendLedger.create(root / "spend.sqlite", 100)
                identity = LiveChatIdentity(
                    model="gpt-5.6-luna",
                    effort="medium",
                    max_output_tokens=128,
                    spend_policy_sha256="1" * 64,
                    spend_ledger_id=ledger.policy.ledger_id,
                    artifacts_root=str(root),
                )
                started = asyncio.Event()
                calls = 0

                async def pending(
                    config: AgentConfig,
                    attempt: int,
                    *,
                    ledger: SpendLedger = ledger,
                    started: asyncio.Event = started,
                ) -> AgentResult:
                    nonlocal calls
                    calls += 1
                    ledger.reserve(
                        LedgerEntry(
                            entry_id="2" * 64,
                            reservation_sha256="3" * 64,
                            reserved_microusd=90,
                        )
                    )
                    started.set()
                    await asyncio.Event().wait()
                    raise AssertionError("no response")

                cassette = demo_cassette()
                initial = ConversationController.fresh(
                    root, cassette, live_chat=identity
                )
                with backend(root / "sessions", initial.session_id, root) as store:
                    store.save(initial)
                    chat = ConversationController(
                        initial, cassette, store.save, run_live_chat=pending
                    )
                    chat.submit("Question")
                    work = asyncio.create_task(chat.step())
                    await started.wait()
                    work.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await work
                held = ledger.snapshot()
                self.assertEqual(held.charged_microusd, 90)
                self.assertEqual(held.unresolved_entries, 1)
                with backend(
                    root / "sessions", initial.session_id, root, create=False
                ) as store:
                    recovered = ConversationController(
                        store.load(), cassette, store.save, run_live_chat=pending
                    )
                    self.assertFalse(await recovered.step())
                    self.assertIsNotNone(
                        uncertain_notice(recovered.state.recovery_journal, "turn-0")
                    )
                self.assertEqual(calls, 1)
                self.assertEqual(SpendLedger(root / "spend.sqlite").snapshot(), held)

    async def test_guard_checks_each_tool_and_subsequent_model_request(self) -> None:
        for deny_at in (1, 2, 3):
            with self.subTest(deny_at=deny_at):
                config, fixtures, cassette = agent_demo_inputs()
                dispatcher = FixtureDispatcher(fixtures)
                checks = 0

                def check(deny_at: int = deny_at) -> None:
                    nonlocal checks
                    checks += 1
                    if checks == deny_at:
                        raise ValueError("workspace or capability changed")

                with (
                    dispatch_guard(check),
                    patch.object(
                        dispatcher, "dispatch", wraps=dispatcher.dispatch
                    ) as tool,
                ):
                    with self.assertRaisesRegex(ValueError, "capability changed"):
                        await run_agent(
                            config,
                            fixture_registry(),
                            RecordedAgentClient(cassette),
                            dispatcher,
                        )
                    self.assertEqual(tool.call_count, int(deny_at == 3))

    async def test_both_stores_refuse_other_workspace_or_owner(self) -> None:
        for backend in (ConversationStore, SQLiteConversationStore):
            with (
                self.subTest(backend=backend.__name__),
                TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                other = root / "other"
                other.mkdir()
                cassette = demo_cassette()
                initial = ConversationController.fresh(root, cassette)
                with backend(root / "sessions", initial.session_id, root) as store:
                    store.save(initial)
                    chat = ConversationController(initial, cassette, store.save)
                    chat.submit(DEMO_PROMPTS[0])
                    await chat.step()
                with (
                    self.assertRaises(ValueError),
                    backend(
                        root / "sessions", initial.session_id, other, create=False
                    ) as store,
                ):
                    store.load()
                with (
                    patch("os.getuid", return_value=os.getuid() + 1),
                    self.assertRaises((ValueError, PermissionError)),
                    backend(
                        root / "sessions", initial.session_id, root, create=False
                    ) as store,
                ):
                    store.load()

    async def test_real_store_fault_matrix_never_replays_an_admitted_operation(
        self,
    ) -> None:
        for backend in (ConversationStore, SQLiteConversationStore):
            for boundary in (
                "before_dispatch",
                "dispatch_ack",
                "after_dispatch",
                "result_commit",
                "result_ack",
            ):
                with (
                    self.subTest(backend=backend.__name__, boundary=boundary),
                    TemporaryDirectory() as temporary,
                ):
                    root = Path(temporary)
                    workspace = root / "workspace"
                    workspace.mkdir()
                    cassette = demo_cassette()
                    initial = ConversationController.fresh(workspace, cassette)
                    storage = root / "sessions"
                    sid = initial.session_id
                    with backend(storage, sid, workspace) as store:
                        store.save(initial)
                        chat = ConversationController(initial, cassette, store.save)
                        chat.submit(DEMO_PROMPTS[0])
                        client = WaitingClient()

                        def save(
                            state: ConversationState, boundary: str = boundary
                        ) -> None:
                            status = state.entries[0].status
                            if boundary == "before_dispatch" and status == "running":
                                raise OSError("dispatch transaction failed")
                            if boundary == "result_commit" and status == "completed":
                                raise OSError("result transaction failed")
                            store.save(state)
                            if boundary == "dispatch_ack" and status == "running":
                                raise OSError("dispatch acknowledgement lost")
                            if boundary == "result_ack" and status == "completed":
                                raise OSError("result acknowledgement lost")

                        chat.save = save
                        task = asyncio.create_task(chat.step(client))
                        if boundary in {
                            "after_dispatch",
                            "result_commit",
                            "result_ack",
                        }:
                            await asyncio.wait_for(client.started.wait(), 5)
                            # Steering is a separate retained user action, not a
                            # recoverable sandbox transcript.
                            chat.submit(DEMO_PROMPTS[1])
                            if boundary == "after_dispatch":
                                task.cancel()
                            else:
                                client.release.set()
                        with self.assertRaises((OSError, asyncio.CancelledError)):
                            await task
                        saved = store.load()
                    with backend(storage, sid, workspace, create=False) as reopened:
                        recovered = ConversationController(
                            reopened.load(), cassette, reopened.save
                        )
                        if boundary == "before_dispatch":
                            self.assertEqual(client.calls, 0)
                            self.assertEqual(
                                recovered.state.entries[0].status, "queued"
                            )
                            self.assertEqual(recovered.state.exchanges_consumed, 0)
                            self.assertIsNone(recovered.state.recovery_journal)
                            await recovered.step()
                        else:
                            self.assertEqual(recovered.state.exchanges_consumed, 1)
                            journal = recovered.state.recovery_journal
                            assert journal is not None
                            self.assertEqual(
                                [e.sequence for e in journal.events], [1, 2]
                            )
                            self.assertEqual(journal.cursor, 2)
                            self.assertEqual(
                                journal.events[0].operation_id,
                                operation_id(sid, "turn-0"),
                            )
                            self.assertEqual(
                                journal.events[-1].phase,
                                "completed"
                                if boundary == "result_ack"
                                else "uncertain",
                            )
                            self.assertEqual(
                                client.calls, int(boundary != "dispatch_ack")
                            )
                            self.assertEqual(
                                recovered.state.entries[0].status,
                                "completed"
                                if boundary == "result_ack"
                                else "cancelled"
                                if boundary == "after_dispatch"
                                else "interrupted",
                            )
                            if len(saved.entries) > 1:
                                self.assertEqual(
                                    recovered.state.entries[1].steering_for, 0
                                )
                                following = WaitingClient()
                                following.release.set()
                                await recovered.step(following)
                                self.assertEqual(following.calls, 1)
                                self.assertEqual(
                                    recovered.state.entries[1].status, "completed"
                                )
                            self.assertFalse(await recovered.step(client))
                            self.assertEqual(
                                client.calls, int(boundary != "dispatch_ack")
                            )
                        # Both the full and bounded SQLite reader validate the
                        # same journal; no second log or content cache is needed.
                    if backend is SQLiteConversationStore:
                        inspection = inspect_sqlite_resume(storage, sid, workspace)
                        self.assertIsNotNone(inspection.header.recovery_journal)

    async def test_commit_cursor_is_not_visible_before_result_transaction(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette), cassette, lambda _: None
            )
            chat.submit(DEMO_PROMPTS[0])
            client = WaitingClient()
            task = asyncio.create_task(chat.step(client))
            await client.started.wait()
            journal = chat.state.recovery_journal
            assert journal is not None
            self.assertEqual(journal.cursor, 0)
            self.assertEqual(journal.events[0].phase, "dispatch")
            self.assertIsNotNone(journal.events[0].decision)
            client.release.set()
            await task
            assert chat.state.recovery_journal is not None
            self.assertEqual(chat.state.recovery_journal.cursor, 2)

    async def test_workspace_replacement_after_decision_prevents_provider_call(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(workspace, cassette),
                cassette,
                lambda _: None,
            )
            chat.submit(DEMO_PROMPTS[0])
            client = WaitingClient()

            def replace_workspace() -> None:
                workspace.rename(root / "old-workspace")
                workspace.mkdir()

            with self.assertRaisesRegex(ValueError, "target changed"):
                await chat.step(client, on_started=replace_workspace)
            self.assertEqual(client.calls, 0)
            self.assertIsNotNone(
                uncertain_notice(chat.state.recovery_journal, "turn-0")
            )

    async def test_process_loss_recovers_open_dispatch_and_steering(self) -> None:
        script = """
import asyncio, os, sys
from pathlib import Path
from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette, DEMO_PROMPTS
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
root = Path(sys.argv[1])
backend = SQLiteConversationStore if sys.argv[2] == "sqlite" else ConversationStore
cassette = demo_cassette()
state = ConversationController.fresh(root, cassette)
with backend(root / "sessions", state.session_id, root) as store:
    store.save(state)
    chat = ConversationController(state, cassette, store.save)
    chat.submit(DEMO_PROMPTS[0])
    print(state.session_id, flush=True)
    def crash():
        chat.submit(DEMO_PROMPTS[1])
        os._exit(71)
    asyncio.run(chat.step(on_started=crash))
"""
        for name, backend in (
            ("json", ConversationStore),
            ("sqlite", SQLiteConversationStore),
        ):
            with self.subTest(backend=name), TemporaryDirectory() as temporary:
                root = Path(temporary)
                result = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-c", script, str(root), name],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=root,
                )
                self.assertEqual(result.returncode, 71, result.stderr)
                sid = result.stdout.strip()
                cassette = demo_cassette()
                with backend(root / "sessions", sid, root, create=False) as store:
                    recovered = ConversationController(
                        store.load(), cassette, store.save
                    )
                    journal = recovered.state.recovery_journal
                    assert journal is not None
                    self.assertEqual(journal.events[-1].phase, "uncertain")
                    self.assertEqual(recovered.state.entries[1].steering_for, 0)
                    following = WaitingClient()
                    following.release.set()
                    await recovered.step(following)
                    self.assertEqual(recovered.state.exchanges_consumed, 2)
                    self.assertEqual(following.calls, 1)

    async def test_common_plain_json_and_tui_uncertainty_projection(self) -> None:
        for json_output in (False, True):
            with TemporaryDirectory() as temporary:
                root = Path(temporary)
                cassette = demo_cassette()
                chat = ConversationController(
                    ConversationController.fresh(root, cassette),
                    cassette,
                    lambda _: None,
                )
                chat.submit(DEMO_PROMPTS[0])
                client = WaitingClient()
                task = asyncio.create_task(chat.step(client))
                await client.started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                events: list[dict[str, object]] = []
                queue: asyncio.Queue[str | None] = asyncio.Queue()
                queue.put_nowait("/quit")
                await terminal(chat, queue, events.append)
                notice = next(e for e in events if e["type"] == "operation.uncertain")
                self.assertIn("not be replayed", str(notice["text"]))
                # JSON serialization is the CLI's projection; plain uses `text`.
                self.assertIn("uncertain", json.dumps(events))
                output = ExecOutput(json_output)
                output.capture(chat)
                self.assertEqual(output.result["effect_status"], "uncertain")
                with create_pipe_input() as input:
                    ui = ConversationTUI(chat, input=input, output=DummyOutput())
                    ui.refresh()
                    self.assertIn("Effect uncertain", ui.transcript.text)

    async def test_bad_journal_does_not_load_or_reset_legacy_state(self) -> None:
        with TemporaryDirectory() as temporary:
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(Path(temporary), cassette),
                cassette,
                lambda _: None,
            )
            chat.submit(DEMO_PROMPTS[0])
            await chat.step()
            raw = json.loads(chat.state.model_dump_json())
            mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
                lambda value: value["recovery_journal"]["events"][0].update(sequence=2),
                lambda value: value["recovery_journal"].update(cursor=0),
                lambda value: value["recovery_journal"]["events"][0].update(
                    operation_id="0" * 64
                ),
                lambda value: value.update(session_id="0" * 32),
                lambda value: value["entries"][0].update(answer="uncommitted result"),
            )
            for mutate in mutations:
                value = json.loads(json.dumps(raw))
                mutate(value)
                with self.assertRaises(ValueError):
                    ConversationState.model_validate_json(json.dumps(value))
            legacy = dict(raw)
            del legacy["recovery_journal"]
            loaded = ConversationState.model_validate_json(json.dumps(legacy))
            self.assertEqual(loaded.entries, chat.state.entries)
            self.assertEqual(loaded.exchanges_consumed, 1)
            self.assertNotIn(b"recovery_journal", canonical_bytes(loaded))
            with self.assertRaises(ValueError):
                RecoveryJournal.model_validate_json(
                    '{"schema_version":2,"events":[],"cursor":0}'
                )

    async def test_dispatch_guard_is_task_local_and_restored_after_failure(
        self,
    ) -> None:
        calls: list[str] = []

        def deny() -> None:
            raise ValueError("stale capability")

        async def sibling(check: Callable[[], None]) -> None:
            with dispatch_guard(check):
                await asyncio.sleep(0)
                revalidate_dispatch()

        results = await asyncio.gather(
            sibling(deny),
            sibling(lambda: calls.append("allowed")),
            return_exceptions=True,
        )
        self.assertIsInstance(results[0], ValueError)
        self.assertEqual(calls, ["allowed"])
        revalidate_dispatch()


class SandboxRecoveryTests(TestCase):
    def test_replacement_recipe_rejects_expanded_mounts_and_changed_image(self) -> None:
        for change in ("mount", "image", "docker", "arguments"):
            with self.subTest(change=change):
                container = OfflineContainer(
                    Path("/usr/bin/docker"), "sha256:" + "1" * 64
                )
                original = container.create_command
                if change == "image":
                    container.image_id = "sha256:" + "2" * 64
                elif change == "docker":
                    container.docker = "/other/docker"
                elif change == "mount":
                    container.create_command = (
                        lambda name, arguments, original=original: [
                            *original(name, arguments),
                            "--volume",
                            "/:/host",
                        ]
                    )
                else:
                    container.create_command = (
                        lambda name, arguments, original=original: [
                            *original(name, arguments),
                            *(["--privileged"] if arguments else []),
                        ]
                    )
                with self.assertRaisesRegex(ValueError, "recipe"):
                    container.verified_create_command("mos-test", ("-m", "worker"))

    def test_replacement_is_fresh_no_mount_and_preserves_exact_arguments(self) -> None:
        first = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "1" * 64)
        replacement = OfflineContainer(Path("/usr/bin/docker"), first.image_id)
        self.assertEqual(replacement.recipe_sha256, first.recipe_sha256)
        command = replacement.verified_create_command("mos-new", ("-m", "worker"))
        self.assertIn("--read-only", command)
        self.assertNotIn("--volume", command)
        self.assertNotIn("--mount", command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command[-3:], [first.image_id, "-m", "worker"])
        self.assertNotEqual(
            first.verified_create_command("mos-old", ()),
            replacement.verified_create_command("mos-new", ()),
        )
