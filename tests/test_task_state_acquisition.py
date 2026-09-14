"""Current G1 task-state acquisition and request-admission fixtures."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic import JsonValue
from test_conversation_review import review_packet
from test_task_profile_admission import CapturingClient, task_profile
from test_task_state_g0 import g0_fixture

from mos_eisley.conversation import (
    ConversationController,
    conversation_config,
    prepare_conversation_request,
)
from mos_eisley.conversation_admission_inspection import inspect_admission
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    ConversationState,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.task_state_store import TaskStateBundle, save_task_state
from mos_eisley.task_state_acquisition import (
    CurrentTaskStateAcquirer,
    CurrentTaskStateSelection,
    decode_task_state_selection,
)


def _replace_scope(value: JsonValue, *, workspace_sha256: str) -> JsonValue:
    if isinstance(value, list):
        return [
            _replace_scope(item, workspace_sha256=workspace_sha256) for item in value
        ]
    if not isinstance(value, dict):
        return value
    replaced = {
        key: _replace_scope(item, workspace_sha256=workspace_sha256)
        for key, item in value.items()
    }
    if {"owner_uid", "project_id", "workspace_sha256"} <= replaced.keys():
        replaced["owner_uid"] = os.getuid()
        replaced["project_id"] = "mos-eisley"
        replaced["workspace_sha256"] = workspace_sha256
    return replaced


class TaskStateFixture:
    def prepare_task_state(self, owner: TestCase) -> None:
        temporary = TemporaryDirectory()
        owner.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        from mos_eisley.task_profile import conversation_workspace_sha256

        source = g0_fixture()
        rebound = _replace_scope(
            cast(dict[str, JsonValue], source.bundle.model_dump(mode="json")),
            workspace_sha256=conversation_workspace_sha256(
                str(self.workspace.resolve())
            ),
        )
        assert isinstance(rebound, dict)
        rebound["profiles"] = []
        self.bundle = TaskStateBundle.model_validate_json(json.dumps(rebound))
        self.storage = self.base / "task-state"
        self.archive = save_task_state(
            self.storage,
            self.bundle,
            {source.artifact.sha256: source.artifact_payload},
        )
        self.selection = CurrentTaskStateSelection(
            project_id=self.bundle.scope.project_id,
            bundle_sha256=self.bundle.sha256,
            bundle_revision=self.bundle.revision,
            checkpoint_id=self.bundle.checkpoint.checkpoint_id,
            checkpoint_revision=self.bundle.checkpoint.revision,
            checkpoint_sha256=self.bundle.checkpoint.sha256,
            current_work_unit=self.bundle.checkpoint.current_work_unit,
        )
        self.selection_path = self.base / "current-task-state.json"
        self.write_selection(self.selection)

    def write_selection(self, selection: CurrentTaskStateSelection) -> None:
        self.selection_path.write_bytes(canonical_bytes(selection))
        self.selection_path.chmod(0o600)

    def acquirer(self) -> CurrentTaskStateAcquirer:
        return CurrentTaskStateAcquirer.from_paths(self.storage, self.selection_path)


class CurrentTaskStateAdmissionTests(TaskStateFixture, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_task_state(self)

    async def test_current_archive_is_acquired_and_bound_before_dispatch(self) -> None:
        acquirer = self.acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_state_acquirer=acquirer
        )
        controller.submit(DEMO_PROMPTS[0])
        preview = preview_context(controller.state, task_state_acquirer=acquirer)
        client = CapturingClient()

        await controller.step(client)

        entry = controller.state.entries[0]
        admission = entry.request_admission
        assert admission is not None and admission.task_state is not None
        assert entry.task_state_context is not None
        self.assertEqual(admission.task_state, preview.task_state)
        self.assertEqual(
            admission.task_state.context_sha256,
            digest(canonical_bytes(entry.task_state_context)),
        )
        self.assertEqual(
            admission.task_state.current_work_unit,
            self.bundle.checkpoint.current_work_unit,
        )
        self.assertIn("Complete G0 only.", client.requests[0].system)
        self.assertIn("G0 records and deterministic", client.requests[0].system)
        self.assertNotIn("8 tests passed", client.requests[0].system)
        self.assertEqual(
            admission.task_state.acquisition.omitted_evidence_view_ids,
            ("focused-tests",),
        )
        self.assertFalse(admission.task_state.grants_authority)
        self.assertFalse(admission.task_state.continuation_enabled)
        self.assertFalse(
            admission.task_state.acquisition.live_workspace_freshness_verified
        )
        described = inspect_admission(controller.state, 0).describe()
        self.assertIn("Task-state bundle:", described)
        self.assertIn("Live workspace freshness is not yet verified", described)

    async def test_changed_current_selection_fails_before_attempt_or_mutation(
        self,
    ) -> None:
        acquirer = self.acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_state_acquirer=acquirer
        )
        controller.submit(DEMO_PROMPTS[0])
        queued = controller.state
        changed = self.selection.model_copy(update={"bundle_revision": 2})
        self.write_selection(changed)
        client = CapturingClient()

        with self.assertRaisesRegex(ValueError, "changed since launch"):
            await controller.step(client)

        self.assertEqual(controller.state, queued)
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertEqual(client.requests, [])

    async def test_changed_archive_fails_before_attempt_or_mutation(self) -> None:
        acquirer = self.acquirer()
        state_file = self.archive / "state.json"
        state_file.write_bytes(state_file.read_bytes() + b" ")
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_state_acquirer=acquirer
        )
        controller.submit(DEMO_PROMPTS[0])
        queued = controller.state
        client = CapturingClient()

        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            await controller.step(client)

        self.assertEqual(controller.state, queued)
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertEqual(client.requests, [])

    async def test_review_request_does_not_acquire_author_task_state(self) -> None:
        acquirer = self.acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_state_acquirer=acquirer
        )
        controller.submit_review(review_packet())
        self.write_selection(self.selection.model_copy(update={"bundle_revision": 2}))

        await controller.step()

        entry = controller.state.entries[0]
        self.assertTrue(entry.is_review)
        self.assertIsNone(entry.request_admission)
        self.assertIsNone(entry.task_state_context)

    async def test_profile_and_current_state_must_select_the_same_work(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        profile = task_profile(state)
        controller = ConversationController(
            state,
            cassette,
            lambda _: None,
            task_profile=profile,
            task_state_acquirer=self.acquirer(),
        )
        controller.submit(DEMO_PROMPTS[0])
        queued = controller.state

        with self.assertRaisesRegex(ValueError, "select different work"):
            await controller.step(CapturingClient())

        self.assertEqual(controller.state, queued)
        self.assertEqual(controller.state.exchanges_consumed, 0)

    async def test_matching_profile_binds_separate_task_state_source(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        profile = task_profile(state)
        profile = profile.model_copy(
            update={
                "manifest": profile.manifest.model_copy(
                    update={"work_unit": self.bundle.checkpoint.current_work_unit}
                )
            }
        )
        controller = ConversationController(
            state,
            cassette,
            lambda _: None,
            task_profile=profile,
            task_state_acquirer=self.acquirer(),
        )
        controller.submit(DEMO_PROMPTS[0])

        await controller.step(CapturingClient())

        admission = controller.state.entries[0].request_admission
        assert admission is not None
        assert admission.task_profile is not None
        assert admission.task_state is not None
        self.assertEqual(
            admission.task_profile.temporary_task_state_sha256,
            admission.task_state.context_sha256,
        )

    async def test_sqlite_retains_task_state_as_a_separate_artifact(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        sessions = self.base / "sessions"
        with SQLiteConversationStore(
            sessions, state.session_id, self.workspace
        ) as store:
            store.save(state)
            controller = ConversationController(
                state,
                cassette,
                store.save,
                task_state_acquirer=self.acquirer(),
            )
            controller.submit(DEMO_PROMPTS[0])

            await controller.step(CapturingClient())

            working = store.load_working()
            archived = working.entries[0]
            assert isinstance(archived, ArchivedConversationEntry)
            admission = archived.request_admission
            assert admission is not None and admission.task_state is not None
            self.assertEqual(
                archived.artifact_refs["task_state_context"],
                admission.task_state.context_sha256,
            )
            hydrated = store.load_working_entry(0, archived)
            assert hydrated.task_state_context is not None
            self.assertEqual(
                hydrated.task_state_context.task_state.bundle_sha256,
                self.bundle.sha256,
            )

    async def test_saved_admission_rejects_rebound_task_state_metadata(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_state_acquirer=self.acquirer()
        )
        controller.submit(DEMO_PROMPTS[0])
        await controller.step(CapturingClient())
        saved = json.loads(controller.state.model_dump_json())
        task_state = saved["entries"][0]["request_admission"]["task_state"]
        task_state["context_bytes"] += 1

        with self.assertRaisesRegex(ValueError, "differs from the saved context"):
            ConversationState.model_validate_json(json.dumps(saved))


class CurrentTaskStateBoundaryTests(TaskStateFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_task_state(self)

    def test_selection_must_name_the_checkpoint_current_work_unit(self) -> None:
        queued = self.bundle.checkpoint.outstanding_work[0]
        self.write_selection(
            self.selection.model_copy(update={"current_work_unit": queued})
        )

        with self.assertRaisesRegex(ValueError, "differs from its archive"):
            self.acquirer().acquire(
                owner_uid=os.getuid(), workspace=str(self.workspace.resolve())
            )

    def test_private_canonical_selection_is_required(self) -> None:
        self.selection_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "private owned file"):
            CurrentTaskStateAcquirer.from_paths(self.storage, self.selection_path)
        self.selection_path.chmod(0o600)
        duplicate = self.selection_path.read_text().replace(
            '"schema_version":1', '"schema_version":1,"schema_version":1', 1
        )
        with self.assertRaisesRegex(ValueError, "Invalid current"):
            decode_task_state_selection(duplicate.encode())
        pretty = json.dumps(
            json.loads(self.selection_path.read_bytes()), indent=2
        ).encode()
        self.assertEqual(decode_task_state_selection(pretty), self.selection)

    def test_cross_workspace_archive_is_rejected(self) -> None:
        other = self.base / "other-workspace"
        other.mkdir()

        with self.assertRaisesRegex(ValueError, "owner or project boundary"):
            self.acquirer().acquire(
                owner_uid=os.getuid(), workspace=str(other.resolve())
            )

    def test_runtime_projection_rejects_evidence_text(self) -> None:
        task_state = self.acquirer().acquire(
            owner_uid=os.getuid(), workspace=str(self.workspace.resolve())
        )
        source_work = next(
            item
            for item in self.bundle.work_units
            if item.reference == self.bundle.checkpoint.current_work_unit
        )
        forged = task_state.model_copy(update={"current_work_unit": source_work})

        with self.assertRaisesRegex(ValueError, "cannot materialize evidence text"):
            type(task_state).model_validate(forged.model_dump())

    def test_editable_selection_example_decodes(self) -> None:
        selection = decode_task_state_selection(
            (Path("templates") / "TASK_STATE_SELECTION_EXAMPLE.json").read_bytes()
        )

        self.assertEqual(selection.kind, "current_task_state")
        self.assertEqual(selection.current_work_unit.revision, 1)

    def test_plain_terminal_acquires_current_task_state(self) -> None:
        task_state = self.acquirer().acquire(
            owner_uid=os.getuid(), workspace=str(self.workspace.resolve())
        )
        turns = (Turn(role="user", blocks=(TextBlock(text=DEMO_PROMPTS[0]),)),)
        request, _budget = prepare_conversation_request(
            conversation_config(turns, task_state=task_state)
        )
        response = demo_cassette().exchanges[0].response
        assert response is not None
        cassette = AgentCassette(
            exchanges=(
                AgentExchange(
                    request_sha256=digest(canonical_bytes(request)), response=response
                ),
            )
        )
        cassette_path = self.base / "task-state-cassette.json"
        cassette_path.write_bytes(canonical_bytes(cassette))

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "--plain",
                "--no-memory",
                "-C",
                str(self.workspace),
                "--storage",
                str(self.base / "sessions"),
                "--cassette",
                str(cassette_path),
                "--task-state-selection",
                str(self.selection_path),
                "--task-state-storage",
                str(self.storage),
            ],
            input=DEMO_PROMPTS[0] + "\n",
            text=True,
            capture_output=True,
            timeout=20,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("The fixture boundary is ten.", result.stdout)
