"""Durable admission metadata across dispatch, recovery and storage boundaries."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from test_conversation import WaitingClient
from test_conversation_context import CapturingClient

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_context import ContextBudgetError
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_request_admission import RequestAdmission
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    WorkingConversationState,
    validate_runtime_state,
)
from mos_eisley.core.agent import AgentFailure
from mos_eisley.core.models import canonical_bytes, canonical_fingerprint
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_migration import ConversationMigration
from mos_eisley.run.conversation_resume import inspect_sqlite_resume
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.conversation_transcript import read_sqlite_transcript


def chat() -> ConversationController:
    cassette = demo_cassette()
    return ConversationController(
        ConversationController.fresh(Path.cwd(), cassette), cassette, lambda _: None
    )


class RequestAdmissionTests(IsolatedAsyncioTestCase):
    async def test_pre_dispatch_record_matches_preview_and_actual_request(self) -> None:
        controller = chat()
        controller.submit('PRIVATE question é "')
        controller.submit("PRIVATE later question")
        before = preview_context(controller.state)
        saved: list[ConversationState] = []
        controller.save = saved.append
        client = CapturingClient()
        await controller.step(client)
        admission = saved[0].entries[0].request_admission
        assert admission is not None
        self.assertEqual(saved[0].entries[0].status, "running")
        self.assertEqual(saved[0].exchanges_consumed, 1)
        self.assertEqual(admission.source_revision, before.revision)
        self.assertEqual(admission.message_count, 2)
        self.assertEqual(admission.exchange_index, 0)
        self.assertEqual(admission.selection, before.selection)
        self.assertEqual(admission.context_sha256, before.context_sha256)
        self.assertEqual(admission.context_bytes, before.context_bytes)
        self.assertEqual(admission.request, before.request)
        fingerprint = canonical_fingerprint(client.requests[0])
        self.assertEqual(admission.request.sha256, fingerprint.sha256)
        self.assertEqual(admission.request.bytes, fingerprint.bytes)
        self.assertNotIn("PRIVATE", admission.model_dump_json())
        self.assertEqual(controller.state.entries[0].request_admission, admission)
        self.assertIsNone(controller.state.entries[1].request_admission)

    async def test_cancellation_preserves_record_and_later_steering_is_separate(
        self,
    ) -> None:
        controller = chat()
        controller.submit("original")
        client = WaitingClient()
        task = asyncio.create_task(controller.step(client))
        await client.started.wait()
        admission = controller.state.entries[0].request_admission
        assert admission is not None
        controller.steer("refinement")
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(controller.state.entries[0].request_admission, admission)
        self.assertEqual(admission.message_count, 1)
        self.assertEqual(admission.selection.omitted, ())
        await controller.step(CapturingClient())
        refinement = controller.state.entries[1].request_admission
        assert refinement is not None
        self.assertEqual(refinement.exchange_index, 1)
        self.assertEqual(refinement.selection.turn_sources[0].positions, (0, 1))
        self.assertEqual(controller.state.entries[0].request_admission, admission)

    async def test_rejection_and_pre_dispatch_save_failure_create_no_saved_record(
        self,
    ) -> None:
        controller = chat()
        controller.resize_context(4000)
        controller.submit("é" * 3000)
        before = controller.state
        client = CapturingClient()
        with self.assertRaises(ContextBudgetError):
            await controller.step(client)
        self.assertIs(controller.state, before)
        self.assertIsNone(controller.state.entries[0].request_admission)
        controller.resize_context(100_000)
        before = controller.state
        with (
            patch.object(controller, "save", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            await controller.step(client)
        self.assertIs(controller.state, before)
        self.assertEqual(client.requests, [])
        self.assertEqual(controller.state.exchanges_consumed, 0)

    async def test_failed_recorded_response_retains_admission(self) -> None:
        controller = chat()
        controller.submit("does not match the recording")
        with self.assertRaises(AgentFailure):
            await controller.step()
        entry = controller.state.entries[0]
        self.assertEqual(entry.status, "failed")
        self.assertIsNotNone(entry.request_admission)

    async def test_reply_save_failure_keeps_the_admitted_running_record(self) -> None:
        controller = chat()
        controller.submit(DEMO_PROMPTS[0])
        saved: list[ConversationState] = []

        def save(state: ConversationState) -> None:
            if state.entries[0].status == "completed":
                raise OSError("completion write failed")
            saved.append(state)

        controller.save = save
        client = CapturingClient()
        with self.assertRaisesRegex(OSError, "completion write"):
            await controller.step(client)
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(len(saved), 1)
        self.assertEqual(controller.state, saved[0])
        admission = saved[0].entries[0].request_admission
        self.assertIsNotNone(admission)
        restored = ConversationController(saved[0], demo_cassette(), lambda _: None)
        self.assertEqual(restored.state.entries[0].request_admission, admission)
        self.assertEqual(restored.state.entries[0].status, "interrupted")
        self.assertFalse(await restored.step(client))
        self.assertEqual(len(client.requests), 1)

    async def test_review_has_no_chat_admission(self) -> None:
        controller = chat()
        brief, cassette = demo_inputs()
        controller.submit_review(
            ConversationReviewPacket(brief=brief, cassette=cassette)
        )
        await controller.step()
        self.assertIsNone(controller.state.entries[0].request_admission)
        self.assertEqual(controller.state.exchanges_consumed, 0)

    async def test_all_sixteen_messages_have_bounded_complete_selection_records(
        self,
    ) -> None:
        cassette = AgentCassette(exchanges=demo_cassette().exchanges * 8)
        controller = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette), cassette, lambda _: None
        )
        for index in range(16):
            controller.submit(f"question {index}")
        for index in range(16):
            preview = preview_context(controller.state)
            await controller.step(CapturingClient())
            admission = controller.state.entries[index].request_admission
            assert admission is not None
            self.assertEqual(admission.selection, preview.selection)
            self.assertEqual(admission.exchange_index, index)
            self.assertEqual(admission.message_count, 16)
            self.assertLess(len(canonical_bytes(admission)), 8000)
        final = controller.state.entries[-1].request_admission
        assert final is not None
        self.assertEqual(len(final.selection.turn_sources), 31)
        self.assertEqual(final.selection.omitted, ())


class RequestAdmissionStorageTests(TestCase):
    def test_both_stores_recover_admitted_but_unsent_attempt_without_retry(
        self,
    ) -> None:
        for backend in (ConversationStore, SQLiteConversationStore):
            with (
                self.subTest(backend=backend.__name__),
                TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                cassette = demo_cassette()
                state = ConversationController.fresh(root, cassette)
                with backend(root / "sessions", state.session_id, root) as store:
                    store.save(state)
                    controller = ConversationController(state, cassette, store.save)
                    controller.refresh_memory(None, cassette)
                    controller.submit(DEMO_PROMPTS[0])
                    client = CapturingClient()

                    def crash() -> None:
                        raise RuntimeError("crash after durable admission")

                    with self.assertRaisesRegex(RuntimeError, "crash"):
                        asyncio.run(controller.step(client, on_started=crash))
                    saved = store.load()
                    admission = saved.entries[0].request_admission
                    self.assertIsNotNone(admission)
                    self.assertEqual(saved.entries[0].status, "running")
                    self.assertEqual(client.requests, [])
                with backend(
                    root / "sessions", state.session_id, root, create=False
                ) as reopened:
                    if isinstance(reopened, SQLiteConversationStore):
                        loaded = reopened.load_working()
                        assert isinstance(loaded, WorkingConversationState)
                        self.assertIsInstance(
                            loaded.entries[0], ArchivedConversationEntry
                        )
                        recovered = ConversationController(
                            loaded, cassette, reopened.save_working
                        ).state
                    else:
                        recovered = ConversationController(
                            reopened.load(), cassette, reopened.save
                        ).state
                    self.assertEqual(recovered.entries[0].status, "interrupted")
                    self.assertEqual(recovered.entries[0].request_admission, admission)
                    self.assertEqual(recovered.exchanges_consumed, 1)
                    self.assertEqual(
                        reopened.load().entries[0].request_admission, admission
                    )

    def test_archived_records_pages_refresh_and_migration_preserve_exact_admission(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory_store = MemoryStore(root / "memory", root)
            memory_store.change("user", "set", text="PRIVATE original memory")
            memory = memory_store.load()
            cassette = demo_cassette(memory=memory)
            state = ConversationController.fresh(root, cassette, memory)
            storage = root / "sessions"
            with ConversationStore(storage, state.session_id, root) as store:
                store.save(state)
                controller = ConversationController(state, cassette, store.save)
                controller.refresh_memory(memory, cassette)
                controller.submit(DEMO_PROMPTS[0])
                asyncio.run(controller.step())
                admission = controller.state.entries[0].request_admission
                assert admission is not None
                self.assertTrue(admission.memory_selected)
                self.assertNotIn("PRIVATE", admission.model_dump_json())
                original = canonical_bytes(controller.state)
            with ConversationMigration(storage, state.session_id, root) as migration:
                preview = migration.migrate()
                migration.migrate(apply=True, expected_sha256=preview.snapshot_sha256)
            with SQLiteConversationStore(
                storage, state.session_id, root, create=False
            ) as store:
                self.assertEqual(canonical_bytes(store.load()), original)
                working = store.load_working()
                assert isinstance(working, WorkingConversationState)
                self.assertIsInstance(working.entries[0], ArchivedConversationEntry)
                self.assertEqual(working.entries[0].request_admission, admission)
                active = ConversationController(
                    working,
                    cassette,
                    store.save_working,
                    load_entry=store.load_working_entry,
                )
                active.refresh_memory(None, cassette, disabled=True)
                self.assertEqual(active.state.entries[0].request_admission, admission)
                self.assertEqual(store.load().entries[0].request_admission, admission)
                with patch.object(
                    SQLiteConversationStore,
                    "_artifact_chunks",
                    side_effect=AssertionError("unexpected artifact read"),
                ):
                    page = read_sqlite_transcript(storage, state.session_id, root)
                    inspection = inspect_sqlite_resume(storage, state.session_id, root)
                self.assertEqual(page.entries[0].content.request_admission, admission)
                self.assertIn(admission.request.sha256, inspection.model_dump_json())
                archived = active.state.entries[0]
                assert isinstance(archived, ArchivedConversationEntry)
                changed = admission.model_copy(update={"context_sha256": "0" * 64})
                forged = active.state.model_copy(
                    update={
                        "revision": active.state.revision + 1,
                        "entries": (
                            archived.model_copy(update={"request_admission": changed}),
                        ),
                    }
                )
                with self.assertRaisesRegex(
                    ValueError, "archived message content changed"
                ):
                    store.save_working(forged)

    def test_legacy_entries_keep_identical_serialization_without_backfill(self) -> None:
        controller = chat()
        controller.submit(DEMO_PROMPTS[0])
        asyncio.run(controller.step())
        data = controller.state.model_dump(mode="json")
        data["entries"][0].pop("request_admission")
        encoded = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        legacy = ConversationState.model_validate_json(encoded)
        self.assertEqual(canonical_bytes(legacy), encoded)
        resumed = ConversationController(legacy, demo_cassette(), lambda _: None)
        self.assertEqual(canonical_bytes(resumed.state), encoded)

    def test_malformed_or_misbound_admissions_are_rejected(self) -> None:
        controller = chat()
        controller.submit(DEMO_PROMPTS[0])
        controller.submit(DEMO_PROMPTS[1])
        asyncio.run(controller.step())
        admission = controller.state.entries[0].request_admission
        assert admission is not None
        changes: tuple[dict[str, object], ...] = (
            {"schema_version": 2},
            {"message_count": 1},
            {"context_max_bytes": 4000, "context_bytes": 4001},
            {
                "request": {
                    **admission.request.model_dump(mode="json"),
                    "within_budget": False,
                }
            },
            {
                "selection": {
                    **admission.selection.model_dump(mode="json"),
                    "omitted": [],
                }
            },
            {
                "selection": {
                    **admission.selection.model_dump(mode="json"),
                    "turn_sources": [{"role": "assistant", "positions": [0]}],
                }
            },
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                RequestAdmission.model_validate_json(
                    json.dumps({**admission.model_dump(mode="json"), **change})
                )
        for change in (
            {"source_revision": controller.state.revision},
            {"exchange_index": controller.state.exchanges_consumed},
        ):
            entry = controller.state.entries[0].model_copy(
                update={"request_admission": admission.model_copy(update=change)}
            )
            changed = controller.state.model_copy(
                update={"entries": (entry, controller.state.entries[1])}
            )
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_runtime_state(changed)
        queued = controller.state.entries[1].model_copy(
            update={"request_admission": admission}
        )
        with self.assertRaisesRegex(ValueError, "dispatched chat"):
            validate_runtime_state(
                controller.state.model_copy(
                    update={"entries": (controller.state.entries[0], queued)}
                )
            )

    def test_duplicate_exchange_or_rebound_message_rejected_on_native_validation(
        self,
    ) -> None:
        controller = chat()
        for prompt in DEMO_PROMPTS:
            controller.submit(prompt)
            asyncio.run(controller.step())
        first, second = controller.state.entries
        admission = second.request_admission
        assert admission is not None
        changes = (
            admission.model_copy(update={"exchange_index": 0}),
            first.request_admission,
        )
        for changed in changes:
            state = controller.state.model_copy(
                update={
                    "entries": (
                        first,
                        second.model_copy(update={"request_admission": changed}),
                    )
                }
            )
            with (
                self.subTest(changed=changed),
                self.assertRaisesRegex(ValueError, "saved attempt"),
            ):
                validate_runtime_state(state)
