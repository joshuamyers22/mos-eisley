"""Scoped task profiles enter chat requests without becoming reusable memory."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_conversation_context import CapturingClient

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_admission_inspection import inspect_admission
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_state import validate_runtime_state
from mos_eisley.conversation_task_profile import (
    ScopedTaskProfile,
    ScopedTaskProfileError,
    TaskInstructionContent,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    TextBlock,
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolSchema,
    Turn,
    Usage,
)
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.task_profile import (
    InstructionProfileEntry,
    ProfileSizes,
    TaskProfileManifest,
    ToolProfileEntry,
)
from mos_eisley.task_state import OwnerProjectScope, WorkUnitReference
from mos_eisley.tools.fixture import FixtureDispatcher, FixtureValues


def selected_profile(root: Path) -> tuple[ScopedTaskProfile, OwnerProjectScope]:
    stable = "Prefer explicit admission boundaries."
    temporary = "The current task is scoped profile wiring."
    dispatcher = FixtureDispatcher(FixtureValues(values={"answer": "42"}))
    definition = dispatcher.definitions[0]
    schema = canonical_bytes(definition.input_schema)
    scope = OwnerProjectScope(
        owner_uid=os.getuid(),
        project_id="profile-tests",
        workspace_sha256=digest(str(root.resolve()).encode()),
    )
    instructions = (
        InstructionProfileEntry(
            rule_id="stable-guidance",
            source_sha256=digest(b"stable source"),
            content_sha256=digest(stable.encode()),
            bytes=len(stable.encode()),
            scope="conversation admission",
            required=True,
            selected=True,
            selection_reason="Required by the test profile.",
            location="root",
            classification="stable_rule",
        ),
        InstructionProfileEntry(
            rule_id="temporary-task-state",
            source_sha256=digest(b"temporary source"),
            content_sha256=digest(temporary.encode()),
            bytes=len(temporary.encode()),
            scope="this work unit only",
            required=False,
            selected=True,
            selection_reason="Needed only for this task.",
            location="reference",
            classification="temporary_state",
        ),
    )
    tools = (
        ToolProfileEntry(
            tool_id=definition.name,
            schema_sha256=digest(schema),
            schema_bytes=len(schema),
            required=True,
            selected=True,
            authorized=True,
            availability="available",
            selection_reason="The trusted fixture catalog supplies this tool.",
        ),
        ToolProfileEntry(
            tool_id="unused-tool",
            schema_sha256=digest(canonical_bytes(ToolSchema(type="object"))),
            schema_bytes=len(canonical_bytes(ToolSchema(type="object"))),
            required=False,
            selected=False,
            authorized=False,
            availability="unavailable",
            selection_reason="Not applicable to this work unit.",
        ),
    )
    manifest = TaskProfileManifest(
        scope=scope,
        profile_id="conversation-profile",
        work_unit=WorkUnitReference(work_unit_id="profile-admission", revision=1),
        policy_sha256=digest(b"trusted profile policy"),
        instructions=instructions,
        tools=tools,
        omitted_tool_ids=("unused-tool",),
        sizes=ProfileSizes(
            root_instruction_bytes=len(stable.encode()),
            instruction_bytes=len(stable.encode()) + len(temporary.encode()),
            tool_schema_bytes=len(schema),
            total_bytes=len(stable.encode()) + len(temporary.encode()) + len(schema),
        ),
    )
    return (
        ScopedTaskProfile(
            manifest=manifest,
            instructions=(
                TaskInstructionContent(rule_id="stable-guidance", text=stable),
                TaskInstructionContent(rule_id="temporary-task-state", text=temporary),
            ),
        ),
        scope,
    )


class ScopedTaskProfileAdmissionTests(IsolatedAsyncioTestCase):
    async def test_selected_profile_and_memory_are_bound_before_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory_store = MemoryStore(root / "memory", root)
            memory_store.change("user", "set", text="Use stable user preference.")
            memory = memory_store.load()
            cassette = demo_cassette(memory=memory)
            profile, scope = selected_profile(root)
            dispatcher = FixtureDispatcher(FixtureValues(values={"answer": "42"}))
            controller = ConversationController(
                ConversationController.fresh(root, cassette, memory),
                cassette,
                lambda _: None,
                task_scope=scope,
                resolve_task_profile=lambda _index: profile,
                tool_dispatcher=dispatcher,
            )
            controller.submit(DEMO_PROMPTS[0])
            client = CapturingClient()

            await controller.step(client)

            request = client.requests[0]
            self.assertEqual(
                tuple(tool.name for tool in request.tools), ("fixture_lookup",)
            )
            self.assertIn("Prefer explicit admission boundaries.", request.system)
            self.assertIn("current task is scoped profile wiring", request.system)
            self.assertIn("Use stable user preference.", request.system)
            admission = controller.state.entries[0].request_admission
            assert admission is not None
            self.assertEqual(admission.schema_version, 5)
            assert admission.task_profile is not None
            self.assertEqual(
                admission.task_profile.profile_sha256, profile.manifest.sha256
            )
            self.assertEqual(
                admission.task_profile.selected_instruction_ids,
                ("stable-guidance", "temporary-task-state"),
            )
            self.assertEqual(
                admission.task_profile.selected_tool_ids, ("fixture_lookup",)
            )
            classification = admission.context_classification
            assert classification is not None
            self.assertEqual(classification.task_instruction_ids, ("stable-guidance",))
            self.assertEqual(
                classification.temporary_task_state_ids,
                ("temporary-task-state",),
            )
            self.assertEqual(
                tuple(item.scope for item in classification.reusable_memory), ("user",)
            )
            self.assertFalse(classification.checkpoint_selected)
            encoded = admission.model_dump_json()
            self.assertNotIn("Use stable user preference", encoded)
            self.assertNotIn("explicit admission boundaries", encoded)
            self.assertNotIn("current task is scoped", encoded)
            description = inspect_admission(controller.state, 0).describe()
            self.assertIn("Task profile: conversation-profile", description)
            self.assertIn("1 temporary-state item", description)
            self.assertNotIn("explicit admission boundaries", description)
            forged_profile = admission.task_profile.model_copy(
                update={
                    "scope": admission.task_profile.scope.model_copy(
                        update={"workspace_sha256": digest(b"another workspace")}
                    )
                }
            )
            forged_admission = admission.model_copy(
                update={"task_profile": forged_profile}
            )
            forged_entry = controller.state.entries[0].model_copy(
                update={"request_admission": forged_admission}
            )
            with self.assertRaisesRegex(ValueError, "conversation scope"):
                validate_runtime_state(
                    controller.state.model_copy(update={"entries": (forged_entry,)})
                )

    async def test_selected_existing_tool_executes_through_scoped_dispatcher(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, scope = selected_profile(root)
            dispatcher = FixtureDispatcher(FixtureValues(values={"answer": "42"}))
            case = self

            class ToolClient:
                def __init__(self) -> None:
                    self.requests: list[ModelRequest] = []

                async def complete(self, request: ModelRequest) -> ModelResponse:
                    self.requests.append(request)
                    if len(self.requests) == 1:
                        return ModelResponse(
                            turn=Turn(
                                role="assistant",
                                blocks=(
                                    ToolCallBlock(
                                        id="lookup-1",
                                        name="fixture_lookup",
                                        args={"key": "answer"},
                                    ),
                                ),
                            ),
                            stop_reason="tool_use",
                            usage=Usage(input=1, output=1),
                        )
                    result = request.turns[-1].blocks[0]
                    case.assertIsInstance(result, ToolResultBlock)
                    assert isinstance(result, ToolResultBlock)
                    case.assertIn('"value": "42"', result.content)
                    return ModelResponse(
                        turn=Turn(
                            role="assistant",
                            blocks=(TextBlock(text="The selected value is 42."),),
                        ),
                        stop_reason="end_turn",
                        usage=Usage(input=1, output=1),
                    )

            cassette = demo_cassette()
            controller = ConversationController(
                ConversationController.fresh(root, cassette),
                cassette,
                lambda _: None,
                task_scope=scope,
                resolve_task_profile=lambda _index: profile,
                tool_dispatcher=dispatcher,
            )
            controller.submit(DEMO_PROMPTS[0])
            client = ToolClient()

            await controller.step(client)

            self.assertEqual(len(client.requests), 2)
            self.assertEqual(
                tuple(tool.name for tool in client.requests[0].tools),
                ("fixture_lookup",),
            )
            self.assertEqual(
                controller.state.entries[0].answer, "The selected value is 42."
            )

    async def test_profile_failure_is_before_persistence_attempt_or_dispatch(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, scope = selected_profile(root)
            required = profile.manifest.tools[0]
            invalid_manifest = TaskProfileManifest.model_validate(
                profile.manifest.model_copy(
                    update={
                        "tools": (
                            required.model_copy(update={"selected": False}),
                            profile.manifest.tools[1],
                        ),
                        "omitted_tool_ids": ("fixture_lookup", "unused-tool"),
                        "sizes": profile.manifest.sizes.model_copy(
                            update={
                                "tool_schema_bytes": 0,
                                "total_bytes": profile.manifest.sizes.instruction_bytes,
                            }
                        ),
                    }
                ).model_dump()
            )
            invalid = profile.model_copy(update={"manifest": invalid_manifest})
            cassette = demo_cassette()
            saved: list[object] = []
            controller = ConversationController(
                ConversationController.fresh(root, cassette),
                cassette,
                saved.append,
                task_scope=scope,
                resolve_task_profile=lambda _index: invalid,
                tool_dispatcher=FixtureDispatcher(
                    FixtureValues(values={"answer": "42"})
                ),
            )
            controller.submit(DEMO_PROMPTS[0])
            before = controller.state
            saved.clear()
            client = CapturingClient()

            with self.assertRaisesRegex(
                ScopedTaskProfileError, "required_tool_omitted"
            ):
                await controller.step(client)

            self.assertIs(controller.state, before)
            self.assertEqual(saved, [])
            self.assertEqual(client.requests, [])

    async def test_scope_content_and_catalog_mismatches_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, scope = selected_profile(root)
            cassette = demo_cassette()
            cases = (
                (
                    scope.model_copy(update={"project_id": "another-project"}),
                    profile,
                    FixtureDispatcher(FixtureValues(values={"answer": "42"})),
                    "scope",
                ),
                (
                    scope,
                    profile.model_copy(
                        update={
                            "instructions": (
                                profile.instructions[0].model_copy(
                                    update={"text": "tampered instruction"}
                                ),
                                profile.instructions[1],
                            )
                        }
                    ),
                    FixtureDispatcher(FixtureValues(values={"answer": "42"})),
                    "content",
                ),
                (scope, profile, None, "tool"),
            )
            for expected_scope, selected, dispatcher, message in cases:
                controller = ConversationController(
                    ConversationController.fresh(root, cassette),
                    cassette,
                    lambda _: None,
                    task_scope=expected_scope,
                    resolve_task_profile=lambda _index, value=selected: value,
                    tool_dispatcher=dispatcher,
                )
                controller.submit(DEMO_PROMPTS[0])
                with (
                    self.subTest(message=message),
                    self.assertRaisesRegex(ScopedTaskProfileError, message),
                ):
                    await controller.step(CapturingClient())
                self.assertEqual(controller.state.exchanges_consumed, 0)
                self.assertIsNone(controller.state.entries[0].request_admission)

    async def test_unselected_catalog_tools_never_enter_the_request(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, scope = selected_profile(root)
            selected_definition = FixtureDispatcher(
                FixtureValues(values={"answer": "42"})
            ).definitions[0]

            class CatalogDispatcher:
                @property
                def definitions(self) -> tuple[ToolDefinition, ...]:
                    extra = selected_definition.model_copy(
                        update={"name": "extra-tool"}
                    )
                    return (selected_definition, extra)

                async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
                    raise AssertionError(f"unexpected tool call {call.name}")

            cassette = demo_cassette()
            controller = ConversationController(
                ConversationController.fresh(root, cassette),
                cassette,
                lambda _: None,
                task_scope=scope,
                resolve_task_profile=lambda _index: profile,
                tool_dispatcher=CatalogDispatcher(),
            )
            controller.submit(DEMO_PROMPTS[0])
            client = CapturingClient()

            await controller.step(client)

            self.assertEqual(
                tuple(tool.name for tool in client.requests[0].tools),
                ("fixture_lookup",),
            )

    async def test_legacy_admission_remains_schema_one(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            controller = ConversationController(
                ConversationController.fresh(root, cassette), cassette, lambda _: None
            )
            controller.submit(DEMO_PROMPTS[0])
            await controller.step(CapturingClient())
            admission = controller.state.entries[0].request_admission
            assert admission is not None
            data = admission.model_dump(mode="json")
            data["schema_version"] = 1
            data.pop("context_classification")
            data.pop("task_profile", None)
            data.pop("pressure")
            data.pop("pressure_advisory", None)
            legacy = type(admission).model_validate_json(json.dumps(data))
            self.assertEqual(legacy.schema_version, 1)
            self.assertIsNone(legacy.context_classification)
            self.assertIsNone(legacy.task_profile)

    async def test_profile_admission_round_trips_through_both_stores(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, scope = selected_profile(root)
            cassette = demo_cassette()
            for name, store_type in (
                ("snapshot", ConversationStore),
                ("sqlite", SQLiteConversationStore),
            ):
                with self.subTest(store=name):
                    state = ConversationController.fresh(root, cassette)
                    with store_type(
                        root / name,
                        state.session_id,
                        root,
                    ) as store:
                        store.save(state)
                        controller = ConversationController(
                            state,
                            cassette,
                            store.save,
                            task_scope=scope,
                            resolve_task_profile=lambda _index: profile,
                            tool_dispatcher=FixtureDispatcher(
                                FixtureValues(values={"answer": "42"})
                            ),
                        )
                        controller.submit(DEMO_PROMPTS[0])
                        await controller.step(CapturingClient())
                        expected = controller.state.entries[0].request_admission
                        restored = store.load()
                    self.assertEqual(
                        restored.entries[0].request_admission,
                        expected,
                    )
