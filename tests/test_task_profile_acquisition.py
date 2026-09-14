"""Automatic G1 profile acquisition from frozen author guidance."""

import os
import subprocess
import sys
from pathlib import Path
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase

import test_project_guidance_role as role_fixture

from mos_eisley.conversation import (
    ConversationController,
    conversation_config,
    prepare_conversation_request,
)
from mos_eisley.conversation_admission_inspection import inspect_admission
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock, Turn
from mos_eisley.project_guidance_role_admission import RoleContextSelection
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.task_profile_acquisition import (
    FrozenRoleTaskProfileAcquirer,
    FrozenRoleTaskProfileSelection,
    decode_task_profile_selection,
)
from mos_eisley.task_state import WorkUnitReference


class CapturingClient:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        response = demo_cassette().exchanges[0].response
        assert response is not None
        return response


class AcquisitionFixture:
    def prepare_role_fixture(self, owner: TestCase) -> None:
        self.guidance = role_fixture.RoleContextTests()
        self.guidance.setUp()
        owner.addCleanup(self.guidance.doCleanups)
        self.workspace = self.guidance.workspace
        self.storage = self.guidance.storage
        self.policy_path = self.guidance.policy_path
        self.selection_path = self.guidance.base / "task-profile-selection.json"

    def select(self, receipt: dict[str, object]) -> FrozenRoleTaskProfileSelection:
        snapshot = self.guidance.snapshot(receipt)
        selection = FrozenRoleTaskProfileSelection(
            profile_id="recorded-author-guidance",
            project_id="mos-eisley",
            work_unit=WorkUnitReference(
                work_unit_id="automatic-profile-acquisition", revision=1
            ),
            guidance=RoleContextSelection(
                snapshot_sha256=cast(str, receipt["snapshot_sha256"]),
                context_sha256=cast(str, receipt["context_sha256"]),
                role=snapshot.context.role,
                scope=snapshot.context.scope,
            ),
            expected_policy_sha256=digest(self.policy_path.read_bytes()),
        )
        self.selection_path.write_bytes(canonical_bytes(selection))
        return selection

    def acquirer(self) -> FrozenRoleTaskProfileAcquirer:
        return FrozenRoleTaskProfileAcquirer.from_paths(
            self.storage, self.selection_path, self.policy_path
        )


class AutomaticProfileAdmissionTests(AcquisitionFixture, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_role_fixture(self)

    async def test_current_frozen_author_context_is_acquired_per_request(self) -> None:
        receipt = self.guidance.freeze()
        selection = self.select(receipt)
        acquirer = self.acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile_acquirer=acquirer
        )
        controller.submit(DEMO_PROMPTS[0])
        preview = preview_context(controller.state, task_profile_acquirer=acquirer)
        client = CapturingClient()

        await controller.step(client)

        admission = controller.state.entries[0].request_admission
        assert admission is not None and admission.task_profile is not None
        profile = admission.task_profile
        assert profile.acquisition is not None
        self.assertEqual(profile, preview.task_profile)
        self.assertEqual(
            profile.acquisition.role_context_snapshot_sha256,
            selection.guidance.snapshot_sha256,
        )
        self.assertEqual(
            profile.acquisition.selection_source_sha256,
            digest(self.selection_path.read_bytes()),
        )
        self.assertEqual(profile.manifest.work_unit, selection.work_unit)
        self.assertIn("Use batch execution.", client.requests[0].system)
        self.assertIn("Review implementation", client.requests[0].system)
        self.assertNotIn("PRIVATE-POLICY-PROSE-CANARY", client.requests[0].system)
        self.assertEqual(client.requests[0].tools, ())
        described = inspect_admission(controller.state, 0).describe()
        self.assertIn("Automatically acquired creator guidance", described)

    async def test_changed_guidance_rejects_before_attempt(self) -> None:
        self.select(self.guidance.freeze())
        acquirer = self.acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile_acquirer=acquirer
        )
        controller.submit(DEMO_PROMPTS[0])
        self.guidance.add_requirement()
        client = CapturingClient()

        with self.assertRaisesRegex(ValueError, "no longer current"):
            await controller.step(client)

        self.assertEqual(controller.state.entries[0].status, "queued")
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertEqual(client.requests, [])

    async def test_sqlite_preserves_acquisition_without_fake_memory(
        self,
    ) -> None:
        self.select(self.guidance.freeze())
        acquirer = self.acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        with SQLiteConversationStore(
            self.guidance.base / "sessions", state.session_id, self.workspace
        ) as store:
            store.save(state)
            controller = ConversationController(
                state,
                cassette,
                store.save,
                load_entry=store.load_working_entry,
                task_profile_acquirer=acquirer,
            )
            controller.submit(DEMO_PROMPTS[0])

            await controller.step(CapturingClient())
            working = store.load_working()

        restored = working.entries[0]
        assert restored.request_admission is not None
        assert restored.request_admission.task_profile is not None
        self.assertIsNotNone(restored.request_admission.task_profile.acquisition)
        self.assertIsNone(
            restored.request_admission.task_profile.reusable_memory_context_sha256
        )
        self.assertIsNone(restored.memory_context)


class AutomaticProfileBoundaryTests(AcquisitionFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_role_fixture(self)

    def test_explicit_requirement_omission_stays_out_of_model_profile(self) -> None:
        self.guidance.add_requirement()
        self.guidance.selection["omitted_requirements"] = [
            {
                "rule_id": "REQ2",
                "reason": "Storage implementation is outside this work unit.",
            }
        ]
        self.guidance.write_selection()
        self.select(self.guidance.freeze())

        profile = self.acquirer().acquire(
            owner_uid=os.getuid(),
            workspace=str(Path(self.workspace).resolve()),
        )

        assert profile.acquisition is not None
        self.assertEqual(profile.acquisition.omitted_requirement_ids, ("REQ2",))
        materialized = profile.system_suffix
        self.assertIn("Use batch execution.", materialized)
        self.assertNotIn("Retain data locally.", materialized)
        self.assertNotIn("PRIVATE-BRIEF-CANARY", materialized)

    def test_critic_context_and_malformed_selection_are_rejected(self) -> None:
        receipt = self.guidance.freeze()
        selection = self.select(receipt)
        critic_guidance = selection.guidance.model_copy(update={"role": "critic"})
        with self.assertRaisesRegex(ValueError, "creator or coder"):
            FrozenRoleTaskProfileSelection(
                profile_id=selection.profile_id,
                project_id=selection.project_id,
                work_unit=selection.work_unit,
                guidance=critic_guidance,
                expected_policy_sha256=selection.expected_policy_sha256,
            )
        duplicate = self.selection_path.read_text().replace(
            '"schema_version":1', '"schema_version":1,"schema_version":1', 1
        )
        with self.assertRaisesRegex(ValueError, "Invalid automatic"):
            decode_task_profile_selection(duplicate.encode())

    def test_editable_selection_example_decodes(self) -> None:
        example = Path("templates") / "TASK_PROFILE_SELECTION_EXAMPLE.json"

        selection = decode_task_profile_selection(example.read_bytes())

        self.assertEqual(selection.guidance.role, "coder")
        self.assertEqual(selection.work_unit.revision, 1)

    def test_forged_critic_selection_is_rejected_by_concrete_acquirer(self) -> None:
        receipt = self.guidance.freeze()
        selection = self.select(receipt)
        forged = FrozenRoleTaskProfileSelection.model_construct(
            schema_version=selection.schema_version,
            kind=selection.kind,
            profile_id=selection.profile_id,
            project_id=selection.project_id,
            work_unit=selection.work_unit,
            guidance=selection.guidance.model_copy(update={"role": "critic"}),
            expected_policy_sha256=selection.expected_policy_sha256,
        )
        with self.assertRaisesRegex(ValueError, "Invalid automatic"):
            FrozenRoleTaskProfileAcquirer(
                guidance_storage=self.storage,
                policy_path=self.policy_path,
                selection_payload=canonical_bytes(forged),
            )

    def test_controller_rejects_fixed_and_automatic_profile_sources(self) -> None:
        self.select(self.guidance.freeze())
        acquirer = self.acquirer()
        profile = acquirer.acquire(
            owner_uid=os.getuid(), workspace=str(Path(self.workspace).resolve())
        )
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)

        with self.assertRaisesRegex(ValueError, "fixed or automatically acquired"):
            ConversationController(
                state,
                cassette,
                lambda _: None,
                task_profile=profile,
                task_profile_acquirer=acquirer,
            )

    def test_plain_terminal_acquires_selected_profile(self) -> None:
        self.select(self.guidance.freeze())
        profile = self.acquirer().acquire(
            owner_uid=os.getuid(), workspace=str(Path(self.workspace).resolve())
        )
        turns = (
            Turn(
                role="user",
                blocks=(TextBlock(text=DEMO_PROMPTS[0]),),
            ),
        )
        request, _ = prepare_conversation_request(
            conversation_config(turns, task_profile=profile), profile
        )
        response = demo_cassette().exchanges[0].response
        assert response is not None
        cassette = AgentCassette(
            exchanges=(
                AgentExchange(
                    request_sha256=digest(canonical_bytes(request)),
                    response=response,
                ),
            )
        )
        cassette_path = self.guidance.base / "profile-cassette.json"
        cassette_path.write_bytes(canonical_bytes(cassette))
        sessions = self.guidance.base / "sessions"

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
                str(sessions),
                "--cassette",
                str(cassette_path),
                "--task-profile-selection",
                str(self.selection_path),
                "--task-profile-policy",
                str(self.policy_path),
                "--task-guidance-storage",
                str(self.storage),
            ],
            input=DEMO_PROMPTS[0] + "\n",
            text=True,
            capture_output=True,
            timeout=20,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("The fixture boundary is ten.", result.stdout)
