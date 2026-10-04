"""Planning admission, immutable queued intent and restart/tool boundaries."""

import asyncio
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation import WaitingClient
from test_conversation_context import CapturingClient
from test_conversation_task_profile import selected_profile

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_context import ContextBudgetError
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_diff import (
    attach_lines,
    attachment_suffix,
    capture_diff,
    patch_lines,
)
from mos_eisley.conversation_input import ConversationInput, ConversationSubmission
from mos_eisley.conversation_pending import PendingTextBudgetError, PendingTextLimits
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    ConversationEntry,
    ConversationState,
)
from mos_eisley.conversation_task_profile import ScopedTaskProfile
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.conversation_transcript import read_sqlite_transcript
from mos_eisley.tools.fixture import FixtureDispatcher, FixtureValues


class PlanningTests(IsolatedAsyncioTestCase):
    def chat(self, root: Path | None = None) -> ConversationController:
        cassette = demo_cassette()
        return ConversationController(
            ConversationController.fresh(root or Path.cwd(), cassette),
            cassette,
            lambda _: None,
        )

    async def test_plan_constraints_and_preview_match_actual_admission(self) -> None:
        chat = self.chat()
        chat.submit("Investigate caching", planning_request=True)
        preview = preview_context(chat.state)
        client = CapturingClient()
        await chat.step(client)
        request = client.requests[0]
        self.assertIn("Planning mode", request.system)
        for requirement in (
            "scope",
            "assumptions",
            "interfaces",
            "subtasks",
            "verification",
            "ceilings",
            "exploratory draft",
        ):
            self.assertIn(requirement, request.system)
        self.assertIn("Do not write repository files", request.system)
        self.assertEqual(request.tools, ())
        self.assertEqual(chat.state.entries[0].interaction_mode, "plan")
        admission = chat.state.entries[0].request_admission
        assert admission is not None
        self.assertEqual(preview.request.sha256, admission.request.sha256)
        self.assertEqual(preview.context_bytes, admission.context_bytes)
        self.assertEqual(chat.state.exchanges_consumed, 1)
        self.assertTrue(all(not entry.is_review for entry in chat.state.entries))

    async def test_active_and_queued_modes_cannot_be_retargeted(self) -> None:
        chat = self.chat()
        chat.submit(DEMO_PROMPTS[0])
        waiting = WaitingClient()
        active = asyncio.create_task(chat.step(waiting))
        await waiting.started.wait()
        chat.set_interaction_mode("plan")
        chat.submit("Clarify the assumptions")
        chat.set_interaction_mode("conversation")
        self.assertEqual(
            [e.interaction_mode for e in chat.state.entries], ["conversation", "plan"]
        )
        waiting.release.set()
        await active
        client = CapturingClient()
        await chat.step(client)
        self.assertIn("Planning mode", client.requests[0].system)
        self.assertEqual(chat.state.interaction_mode, "conversation")

    async def test_explicit_implementation_handoff_is_atomic_and_bounded(self) -> None:
        chat = self.chat()
        chat.set_interaction_mode("plan")
        chat.submit("Implement the cache", implementation_request=True)
        self.assertEqual(chat.state.interaction_mode, "conversation")
        client = CapturingClient()
        await chat.step(client)
        self.assertIn("creator-led workflow", client.requests[0].system)
        self.assertIn("exact revisions", client.requests[0].system)
        self.assertIn("Changed plans/tests invalidate", client.requests[0].system)
        self.assertIn(
            "Do not request routine human confirmation", client.requests[0].system
        )
        self.assertEqual(client.requests[0].tools, ())
        self.assertTrue(chat.state.entries[0].implementation_request)
        chat.set_interaction_mode("plan")
        self.assertEqual(chat.state.interaction_mode, "plan")

    async def test_selected_task_tools_fail_before_dispatch_in_both_modes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, scope = selected_profile(root)
            for implementation in (False, True):
                chat = self.chat(root)
                chat.task_scope = scope

                def resolve_profile(_position: int) -> ScopedTaskProfile:
                    return profile

                chat.resolve_task_profile = resolve_profile
                chat.tool_dispatcher = FixtureDispatcher(
                    FixtureValues(values={"answer": "42"})
                )
                chat.submit(
                    "Explore",
                    planning_request=not implementation,
                    implementation_request=implementation,
                )
                client = CapturingClient()
                with self.assertRaisesRegex(ValueError, "cannot dispatch task tools"):
                    await chat.step(client)
                self.assertEqual(client.requests, [])
                self.assertEqual(chat.state.exchanges_consumed, 0)
                self.assertEqual(chat.state.entries[0].status, "queued")

    async def test_budget_rejection_preserves_mode_and_queue(self) -> None:
        chat = self.chat()
        chat.pending_limits = PendingTextLimits(max_bytes=4000)
        chat.set_interaction_mode("plan")
        chat.submit("q" * 3999)
        before = canonical_bytes(chat.state)
        with self.assertRaises(PendingTextBudgetError):
            chat.submit("Implement now", implementation_request=True)
        self.assertEqual(canonical_bytes(chat.state), before)
        chat.set_interaction_mode("conversation")
        before = canonical_bytes(chat.state)
        with self.assertRaises(PendingTextBudgetError):
            chat.submit("Plan now", planning_request=True)
        self.assertEqual(canonical_bytes(chat.state), before)

    async def test_json_sqlite_resume_keeps_mode_and_archived_entry_intent(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in (ConversationStore, SQLiteConversationStore):
                chat = self.chat(root)
                # Retained memory context forces a SQLite runtime artifact reference.
                chat.state = chat.state.model_copy(
                    update={"retained_cassette": chat.cassette}
                )
                with kind(root / kind.__name__, chat.state.session_id, root) as store:
                    store.save(chat.state)
                    chat.save = store.save
                    chat.set_interaction_mode("plan")
                    chat.submit("Investigate the interface")
                    await chat.step(CapturingClient())
                    resumed = store.load()
                    self.assertEqual(resumed.interaction_mode, "plan")
                    self.assertEqual(resumed.entries[0].interaction_mode, "plan")
                    if isinstance(store, SQLiteConversationStore):
                        working = store.load_working()
                        self.assertEqual(working.interaction_mode, "plan")
                        self.assertEqual(working.entries[0].interaction_mode, "plan")
                        assert isinstance(working.entries[0], ArchivedConversationEntry)
                        entry = store.load_working_entry(0, working.entries[0])
                        self.assertEqual(entry.interaction_mode, "plan")
                        page = read_sqlite_transcript(
                            root / kind.__name__, chat.state.session_id, root
                        )
                        self.assertEqual(
                            page.entries[0].content.interaction_mode, "plan"
                        )
                    chat.submit("Implement the interface", implementation_request=True)
                    await chat.step(CapturingClient())
                    resumed = store.load()
                    self.assertEqual(resumed.interaction_mode, "conversation")
                    self.assertTrue(resumed.entries[1].implementation_request)
                    if isinstance(store, SQLiteConversationStore):
                        page = read_sqlite_transcript(
                            root / kind.__name__, chat.state.session_id, root
                        )
                        self.assertTrue(page.entries[1].content.implementation_request)
                        working = store.load_working()
                        self.assertTrue(working.entries[1].implementation_request)

    async def test_old_snapshots_keep_identical_bytes_and_invalid_modes_fail(
        self,
    ) -> None:
        chat = self.chat()
        before = canonical_bytes(chat.state)
        self.assertNotIn(b"interaction_mode", before)
        restored = ConversationState.model_validate_json(before)
        self.assertEqual(canonical_bytes(restored), before)
        with self.assertRaises(ValueError):
            ConversationEntry(
                text="Bad", interaction_mode="plan", implementation_request=True
            )
        with self.assertRaises(ValueError):
            ConversationState.model_validate_json(
                before.replace(b"recorded_conversation", b"plan")
            )

    async def test_cli_controls_are_local_and_literal_paste_stays_text(self) -> None:
        chat = self.chat()
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        events: list[dict[str, object]] = []
        queue.put_nowait("/plan")
        queue.put_nowait("/plan status")
        queue.put_nowait("/mode conversation")
        queue.put_nowait(None)
        await terminal(chat, queue, events.append)
        self.assertEqual(chat.state.entries, ())
        self.assertEqual(chat.state.exchanges_consumed, 0)
        self.assertEqual(
            [e["interaction_mode"] for e in events if e["type"] == "conversation.mode"],
            ["plan", "plan", "conversation"],
        )
        for literal in (False, True):
            chat = self.chat()
            queue = asyncio.Queue()
            accepted = asyncio.get_running_loop().create_future()
            queue.put_nowait(
                ConversationSubmission("/plan investigate", literal, accepted)
            )
            queue.put_nowait(None)
            await terminal(chat, queue, events.append)
            self.assertTrue(accepted.result())
            self.assertEqual(
                chat.state.entries[0].interaction_mode,
                "conversation" if literal else "plan",
            )
            self.assertEqual(
                chat.state.entries[0].text,
                "/plan investigate" if literal else "investigate",
            )

    async def test_cli_implementation_rejection_preserves_editor_and_mode(self) -> None:
        chat = self.chat()
        chat.pending_limits = PendingTextLimits(max_bytes=4000)
        chat.set_interaction_mode("plan")
        chat.submit("q" * 3999)
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        accepted = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/implement cache", False, accepted))
        queue.put_nowait("/quit")
        await terminal(chat, queue, lambda _: None)
        self.assertFalse(accepted.result())
        self.assertEqual(chat.state.interaction_mode, "plan")
        self.assertEqual(len(chat.state.entries), 1)
        self.assertEqual(chat.state.exchanges_consumed, 0)

    async def test_tui_displays_selected_mode_and_submission_retains_intent(
        self,
    ) -> None:
        with create_pipe_input() as input:
            chat = self.chat()
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            chat.set_interaction_mode("plan")
            self.assertIn("• plan •", ui.status())
            chat.submit("Retained exploratory draft")
            ui.refresh()
            self.assertIn("• queued • plan", ui.transcript.text)
            ui.editor.insert_text("/implement cache")
            ui.send()
            await asyncio.sleep(0)
            submission = ui.queue.get_nowait()
            self.assertIsInstance(submission, ConversationSubmission)
            assert isinstance(submission, ConversationSubmission)
            self.assertFalse(submission.literal)
            submission.accepted.set_result(False)
            assert ui.submission is not None
            await ui.submission
            self.assertEqual(ui.editor.text, "/implement cache")

    async def test_recorded_planning_replay_and_clarification_share_attempt_budget(
        self,
    ) -> None:
        source = self.chat()
        source.set_interaction_mode("plan")
        client = CapturingClient()
        exchanges: list[AgentExchange] = []
        for prompt in ("Plan a cache", "Revise the plan to use ten entries"):
            source.submit(prompt)
            await source.step(client)
            exchanges.append(
                AgentExchange(
                    request_sha256=digest(canonical_bytes(client.requests[-1])),
                    response=source.cassette.exchanges[0].response,
                )
            )
        cassette = AgentCassette(exchanges=tuple(exchanges))
        chat = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette),
            cassette,
            lambda _: None,
        )
        chat.set_interaction_mode("plan")
        for prompt in ("Plan a cache", "Revise the plan to use ten entries"):
            chat.submit(prompt)
            self.assertTrue(await chat.step())
        self.assertEqual(chat.state.exchanges_consumed, 2)
        self.assertEqual(chat.state.interaction_mode, "plan")
        self.assertTrue(all(e.interaction_mode == "plan" for e in chat.state.entries))
        with self.assertRaisesRegex(ValueError, "no remaining exchange"):
            chat.submit("Another revision")
            await chat.step()

    async def test_context_budget_includes_mode_constraints_before_dispatch(
        self,
    ) -> None:
        chat = self.chat()
        chat.state = chat.state.model_copy(update={"context_max_bytes": 4000})
        chat.submit("x" * 3500, planning_request=True)
        preview = preview_context(chat.state)
        self.assertFalse(preview.within_context_budget)
        client = CapturingClient()
        with self.assertRaises(ContextBudgetError):
            await chat.step(client)
        self.assertEqual(client.requests, [])
        self.assertEqual(chat.state.exchanges_consumed, 0)
        self.assertEqual(chat.state.entries[0].status, "queued")

    async def test_composer_commands_remain_literal_and_blank_implementation_rejects(
        self,
    ) -> None:
        chat = self.chat()
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        for line in ("/compose", "/plan", "/implement cache", "/send", None):
            queue.put_nowait(line)
        await terminal(chat, queue, lambda _: None)
        self.assertEqual(chat.state.entries[0].text, "/plan\n/implement cache")
        self.assertEqual(chat.state.interaction_mode, "conversation")
        self.assertFalse(chat.state.entries[0].implementation_request)
        chat = self.chat()
        chat.set_interaction_mode("plan")
        queue = asyncio.Queue()
        accepted = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/implement   ", False, accepted))
        queue.put_nowait(None)
        await terminal(chat, queue, lambda _: None)
        self.assertFalse(accepted.result())
        self.assertEqual(chat.state.entries, ())
        self.assertEqual(chat.state.interaction_mode, "plan")

    async def test_storage_failure_does_not_acknowledge_or_change_mode(self) -> None:
        chat = self.chat()
        chat.set_interaction_mode("plan")
        before = canonical_bytes(chat.state)

        def fail(_state: ConversationState) -> None:
            raise ValueError("storage changed")

        chat.save = fail
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        accepted = asyncio.get_running_loop().create_future()
        queue.put_nowait(ConversationSubmission("/implement cache", False, accepted))
        with self.assertRaisesRegex(ValueError, "storage changed"):
            await terminal(chat, queue, lambda _: None)
        self.assertTrue(accepted.cancelled())
        self.assertEqual(canonical_bytes(chat.state), before)

    async def test_resume_displays_planning_without_dispatch(self) -> None:
        chat = self.chat()
        chat.set_interaction_mode("plan")
        chat.submit("Unfinished exploratory plan")
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        await terminal(chat, queue, events.append)
        self.assertTrue(
            any(
                e["type"] == "conversation.mode" and e["interaction_mode"] == "plan"
                for e in events
            )
        )
        self.assertEqual(chat.state.entries[0].status, "queued")
        self.assertEqual(chat.state.exchanges_consumed, 0)

    async def test_planning_source_attachments_survive_archived_history(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "init", "-q"], cwd=root, check=True, capture_output=True
            )
            (root / "cache.py").write_text("cache_size = 10\n")
            snapshot = capture_diff(root)
            row = next(
                i + 1
                for i, line in enumerate(patch_lines(snapshot.scope.files[0]))
                if line.new == 1
            )
            attachment = attach_lines(snapshot, "cache.py", row, row)
            chat = self.chat(root)
            with SQLiteConversationStore(
                root / "sessions", chat.state.session_id, root
            ) as store:
                store.save(chat.state)
                chat.save = store.save
                chat.submit(
                    "Plan the cache" + attachment_suffix((attachment,)),
                    planning_request=True,
                    diff_attachments=(attachment,),
                )
                client = CapturingClient()
                await chat.step(client)
                self.assertEqual(client.requests[0].tools, ())
                self.assertIn(
                    attachment.excerpt_sha256, client.requests[0].model_dump_json()
                )
                page = read_sqlite_transcript(
                    root / "sessions", chat.state.session_id, root
                )
                self.assertEqual(page.entries[0].content.interaction_mode, "plan")
                self.assertEqual(
                    page.entries[0].content.diff_attachments, (attachment,)
                )
