"""First G1 slice: scoped task profiles at recorded request admission."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from unittest import IsolatedAsyncioTestCase, TestCase

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_admission_inspection import inspect_admission
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_state import ArchivedConversationEntry
from mos_eisley.core.agent import AgentFailure
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    ToolCallBlock,
    ToolDefinition,
    ToolSchema,
    Turn,
    Usage,
)
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.task_profile import (
    InstructionProfileEntry,
    MaterializedInstruction,
    ProfileSizes,
    RuntimeTaskProfile,
    TaskProfileManifest,
    ToolProfileEntry,
    conversation_workspace_sha256,
)
from mos_eisley.task_state import OwnerProjectScope, WorkUnitReference


class CapturingClient:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        response = demo_cassette().exchanges[0].response
        assert response is not None
        return response


def task_profile(
    state: ConversationState,
    *,
    guidance: str = "Keep the answer concise.",
    tool_availability: Literal["available", "unavailable", "unknown"] = "available",
) -> RuntimeTaskProfile:
    definition = ToolDefinition(
        name="bounded-read",
        description="Read a preselected bounded fixture.",
        input_schema=ToolSchema(type="object"),
    )
    tool_payload = canonical_bytes(definition)
    instruction_payload = guidance.encode("utf-8")
    manifest = TaskProfileManifest(
        scope=OwnerProjectScope(
            owner_uid=state.owner_uid,
            project_id="mos-eisley",
            workspace_sha256=conversation_workspace_sha256(state.workspace),
        ),
        profile_id="g1-recorded-chat",
        work_unit=WorkUnitReference(work_unit_id="g1-profile-admission", revision=1),
        policy_sha256=digest(b"g1 recorded policy"),
        instructions=(
            InstructionProfileEntry(
                rule_id="concise-answer",
                source_sha256=digest(b"approved guidance source"),
                content_sha256=digest(instruction_payload),
                bytes=len(instruction_payload),
                scope="recorded chat response",
                required=True,
                selected=True,
                selection_reason="Required by this recorded work unit.",
                location="nested",
                classification="stable_rule",
            ),
        ),
        tools=(
            ToolProfileEntry(
                tool_id=definition.name,
                schema_sha256=digest(tool_payload),
                schema_bytes=len(tool_payload),
                required=True,
                selected=True,
                authorized=True,
                availability=tool_availability,
                selection_reason="Expose its schema without execution authority.",
            ),
        ),
        sizes=ProfileSizes(
            root_instruction_bytes=0,
            instruction_bytes=len(instruction_payload),
            tool_schema_bytes=len(tool_payload),
            total_bytes=len(instruction_payload) + len(tool_payload),
        ),
    )
    return RuntimeTaskProfile(
        manifest=manifest,
        instructions=(
            MaterializedInstruction(rule_id="concise-answer", content=guidance),
        ),
        tool_definitions=(definition,),
    )


class ToolCallingClient:
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            turn=Turn(
                role="assistant",
                blocks=(ToolCallBlock(id="call-1", name="bounded-read", args={}),),
            ),
            stop_reason="tool_use",
            usage=Usage(input=1, output=1),
        )


class TaskProfileAdmissionTests(IsolatedAsyncioTestCase):
    async def test_profile_binds_preview_admission_and_exact_request(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(Path.cwd(), cassette)
        profile = task_profile(state)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile=profile
        )
        controller.submit(DEMO_PROMPTS[0])
        preview = preview_context(controller.state, profile)
        client = CapturingClient()

        await controller.step(client)

        admission = controller.state.entries[0].request_admission
        assert admission is not None and admission.task_profile is not None
        self.assertEqual(admission.task_profile, preview.task_profile)
        self.assertEqual(admission.request, preview.request)
        self.assertEqual(
            admission.task_profile.request_sha256, admission.request.sha256
        )
        self.assertEqual(client.requests[0].tools, profile.tool_definitions)
        self.assertIn("Keep the answer concise.", client.requests[0].system)
        self.assertFalse(admission.task_profile.grants_authority)
        self.assertFalse(admission.task_profile.tool_execution_enabled)
        self.assertIsNone(admission.task_profile.temporary_task_state_sha256)
        described = inspect_admission(controller.state, 0).describe()
        self.assertIn("g1-recorded-chat", described)
        self.assertIn("Temporary task-state source: none", described)

    async def test_memory_is_separate_and_not_copied_into_manifest(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            memory_store = MemoryStore(workspace / "memory", workspace)
            memory_store.change("user", "set", text="PRIVATE reusable preference")
            memory = memory_store.load()
            assert memory is not None
            cassette = demo_cassette(memory=memory)
            state = ConversationController.fresh(workspace, cassette, memory)
            profile = task_profile(state)
            controller = ConversationController(
                state, cassette, lambda _: None, task_profile=profile
            )
            controller.submit(DEMO_PROMPTS[0])

            await controller.step(CapturingClient())

            admission = controller.state.entries[0].request_admission
            assert admission is not None and admission.task_profile is not None
            memory_context = controller.state.entries[0].memory_context
            assert memory_context is not None
            self.assertEqual(
                admission.task_profile.reusable_memory_context_sha256,
                digest(canonical_bytes(memory_context)),
            )
            self.assertNotIn(
                "PRIVATE reusable preference",
                admission.task_profile.model_dump_json(),
            )
            self.assertIsNone(admission.task_profile.temporary_task_state_sha256)
            changed_profile = admission.task_profile.model_copy(
                update={"reusable_memory_context_sha256": "0" * 64}
            )
            changed_admission = admission.model_copy(
                update={"task_profile": changed_profile}
            )
            changed_entry = controller.state.entries[0].model_copy(
                update={"request_admission": changed_admission}
            )
            changed_state = controller.state.model_copy(
                update={"entries": (changed_entry,)}
            )
            with self.assertRaisesRegex(ValueError, "saved memory context"):
                ConversationState.model_validate_json(changed_state.model_dump_json())

    async def test_failing_profile_stops_before_attempt_or_dispatch(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(Path.cwd(), cassette)
        with self.assertRaisesRegex(ValueError, "failing task profile"):
            task_profile(state, tool_availability="unavailable")

        valid = task_profile(state)
        unavailable = valid.manifest.tools[0].model_copy(
            update={"availability": "unavailable"}
        )
        manifest = valid.manifest.model_copy(update={"tools": (unavailable,)})
        forged = RuntimeTaskProfile.model_construct(
            manifest=manifest,
            instructions=valid.instructions,
            tool_definitions=valid.tool_definitions,
        )
        client = CapturingClient()

        with self.assertRaisesRegex(ValueError, "failing task profile"):
            ConversationController(state, cassette, lambda _: None, task_profile=forged)

        self.assertEqual(state.entries, ())
        self.assertEqual(state.exchanges_consumed, 0)
        self.assertEqual(client.requests, [])

    async def test_schema_selection_cannot_dispatch_a_tool(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(Path.cwd(), cassette)
        profile = task_profile(state)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile=profile
        )
        controller.submit(DEMO_PROMPTS[0])

        with self.assertRaisesRegex(AgentFailure, "tool-call limit"):
            await controller.step(ToolCallingClient())

        entry = controller.state.entries[0]
        self.assertEqual(entry.status, "failed")
        self.assertIsNotNone(entry.request_admission)
        self.assertEqual(controller.state.exchanges_consumed, 1)


class TaskProfileBoundaryTests(TestCase):
    def test_materialization_rejects_temporary_state_and_unselected_schemas(
        self,
    ) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(Path.cwd(), cassette)
        valid = task_profile(state)
        temporary = valid.manifest.instructions[0].model_copy(
            update={"classification": "temporary_state"}
        )
        temporary_manifest = valid.manifest.model_copy(
            update={"instructions": (temporary,)}
        )
        with self.assertRaisesRegex(ValueError, "temporary task state"):
            RuntimeTaskProfile(
                manifest=temporary_manifest,
                instructions=valid.instructions,
                tool_definitions=valid.tool_definitions,
            )
        extra_definition = valid.tool_definitions[0].model_copy(
            update={"name": "unselected-tool"}
        )
        with self.assertRaisesRegex(ValueError, "selected profile inventory"):
            RuntimeTaskProfile(
                manifest=valid.manifest,
                instructions=valid.instructions,
                tool_definitions=valid.tool_definitions + (extra_definition,),
            )

    def test_cross_owner_or_workspace_profile_is_rejected(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(Path.cwd(), cassette)
        valid = task_profile(state)
        changes = (
            {"owner_uid": state.owner_uid + 1},
            {"workspace_sha256": "0" * 64},
        )
        for change in changes:
            changed_scope = valid.manifest.scope.model_copy(update=change)
            changed_manifest = valid.manifest.model_copy(
                update={"scope": changed_scope}
            )
            changed = valid.model_copy(update={"manifest": changed_manifest})
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(ValueError, "different conversation scope"),
            ):
                ConversationController(
                    state, cassette, lambda _: None, task_profile=changed
                )

    def test_forged_material_is_revalidated_at_controller_boundary(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(Path.cwd(), cassette)
        valid = task_profile(state)
        changed_instruction = valid.instructions[0].model_copy(
            update={"content": "Unapproved replacement guidance."}
        )
        changed_tool = valid.tool_definitions[0].model_copy(
            update={"description": "Unapproved replacement schema."}
        )
        for changed in (
            valid.model_copy(update={"instructions": (changed_instruction,)}),
            valid.model_copy(update={"tool_definitions": (changed_tool,)}),
        ):
            with (
                self.subTest(changed=changed),
                self.assertRaisesRegex(ValueError, "differs from its selected"),
            ):
                ConversationController(
                    state, cassette, lambda _: None, task_profile=changed
                )

    def test_profile_admission_round_trips_and_rejects_request_rebinding(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(Path.cwd(), cassette)
        profile = task_profile(state)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile=profile
        )
        controller.submit(DEMO_PROMPTS[0])
        asyncio.run(controller.step(CapturingClient()))
        encoded = controller.state.model_dump_json()

        restored = ConversationState.model_validate_json(encoded)

        admission = restored.entries[0].request_admission
        assert admission is not None and admission.task_profile is not None
        self.assertEqual(restored, controller.state)
        data = json.loads(encoded)
        data["entries"][0]["request_admission"]["task_profile"]["request_sha256"] = (
            "0" * 64
        )
        with self.assertRaisesRegex(ValueError, "does not bind"):
            ConversationState.model_validate_json(json.dumps(data))

    def test_sqlite_archive_retains_profile_and_memory_context_binding(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            memory_store = MemoryStore(workspace / "memory", workspace)
            memory_store.change("user", "set", text="PRIVATE reusable preference")
            memory = memory_store.load()
            assert memory is not None
            cassette = demo_cassette(memory=memory)
            state = ConversationController.fresh(workspace, cassette, memory)
            profile = task_profile(state)
            with SQLiteConversationStore(
                workspace / "sessions", state.session_id, workspace
            ) as store:
                store.save(state)
                controller = ConversationController(
                    state, cassette, store.save, task_profile=profile
                )
                controller.submit(DEMO_PROMPTS[0])
                asyncio.run(controller.step(CapturingClient()))

                working = store.load_working()

                archived = working.entries[0]
                assert isinstance(archived, ArchivedConversationEntry)
                self.assertEqual(
                    archived.request_admission,
                    controller.state.entries[0].request_admission,
                )
                assert archived.request_admission is not None
                assert archived.request_admission.task_profile is not None
                self.assertEqual(
                    archived.request_admission.task_profile.reusable_memory_context_sha256,
                    archived.artifact_refs["memory_context"],
                )
