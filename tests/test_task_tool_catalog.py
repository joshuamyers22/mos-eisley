"""Approved runtime tool-catalog selection for G1 request profiles."""

import os
import subprocess
import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

from test_conversation_review import review_packet
from test_task_profile_acquisition import CapturingClient
from test_task_semantic_discovery import SemanticDiscoveryFixture

from mos_eisley.conversation import (
    ConversationController,
    conversation_config,
    prepare_conversation_request,
)
from mos_eisley.conversation_admission_inspection import inspect_admission
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, ToolDefinition, ToolSchema, Turn
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.task_tool_catalog import (
    RuntimeToolCatalog,
    RuntimeToolCatalogEntry,
    RuntimeToolCatalogSelectingAcquirer,
    RuntimeToolCatalogSelection,
    RuntimeToolChoice,
    RuntimeToolSelectionDecision,
    decode_runtime_tool_catalog,
    decode_runtime_tool_selection,
)


def tool_definition(name: str, description: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        input_schema=ToolSchema(
            type="object",
            properties={"path": ToolSchema(type="string")},
            required=("path",),
        ),
    )


class ToolCatalogFixture(SemanticDiscoveryFixture):
    def prepare_catalog(self, owner: TestCase) -> None:
        self.prepare_discovery(owner)
        self.discovery_path.write_bytes(canonical_bytes(self.discovery()))
        policy_sha = digest(self.policy_path.read_bytes())
        definitions = (
            tool_definition("workspace.read", "Read one approved workspace file."),
            tool_definition("workspace.search", "Search approved workspace text."),
        )
        self.catalog = RuntimeToolCatalog(
            catalog_id="approved-workspace-tools",
            revision=3,
            project_id="mos-eisley",
            policy_sha256=policy_sha,
            tools=tuple(
                RuntimeToolCatalogEntry(
                    tool_id=definition.name,
                    definition=definition,
                    schema_sha256=digest(canonical_bytes(definition)),
                    schema_bytes=len(canonical_bytes(definition)),
                    authorized=True,
                    availability="available",
                    overlaps_with=(
                        ("workspace.search",)
                        if definition.name == "workspace.read"
                        else ("workspace.read",)
                    ),
                )
                for definition in definitions
            ),
        )
        self.catalog_path = self.guidance.base / "runtime-tool-catalog.json"
        self.catalog_path.write_bytes(canonical_bytes(self.catalog))
        self.tool_selection_path = self.guidance.base / "runtime-tool-selection.json"
        self.write_tool_selection()

    def tool_selection(
        self,
        *,
        required_read: bool = True,
        select_read: bool = True,
        catalog_sha: str | None = None,
    ) -> RuntimeToolCatalogSelection:
        return RuntimeToolCatalogSelection(
            expected_catalog_sha256=(
                digest(self.catalog_path.read_bytes())
                if catalog_sha is None
                else catalog_sha
            ),
            expected_catalog_id=self.catalog.catalog_id,
            expected_catalog_revision=self.catalog.revision,
            project_id=self.catalog.project_id,
            expected_policy_sha256=self.catalog.policy_sha256,
            decisions=(
                RuntimeToolSelectionDecision(
                    decision_id="select-exact-runtime-tools",
                    task_text_sha256=digest(DEMO_PROMPTS[0].encode("utf-8")),
                    profile_id=self.candidates[1].profile_id,
                    work_unit=self.candidates[1].work_unit,
                    choices=(
                        RuntimeToolChoice(
                            tool_id="workspace.read",
                            required=required_read,
                            selected=select_read,
                            selection_reason="Required to inspect the target file.",
                        ),
                        RuntimeToolChoice(
                            tool_id="workspace.search",
                            required=False,
                            selected=False,
                            selection_reason="Not needed for this exact task.",
                        ),
                    ),
                ),
            ),
        )

    def write_tool_selection(
        self, selection: RuntimeToolCatalogSelection | None = None
    ) -> None:
        self.tool_selection_path.write_bytes(
            canonical_bytes(selection or self.tool_selection())
        )

    def catalog_acquirer(self) -> RuntimeToolCatalogSelectingAcquirer:
        return RuntimeToolCatalogSelectingAcquirer.from_paths(
            self.semantic_acquirer(), self.catalog_path, self.tool_selection_path
        )


class RuntimeToolCatalogAdmissionTests(ToolCatalogFixture, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_catalog(self)

    async def test_selected_schema_enters_only_matching_author_request(self) -> None:
        acquirer = self.catalog_acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile_acquirer=acquirer
        )
        controller.submit(DEMO_PROMPTS[0])
        preview = preview_context(controller.state, task_profile_acquirer=acquirer)
        client = CapturingClient()

        await controller.step(client)

        self.assertEqual(
            tuple(item.name for item in client.requests[0].tools), ("workspace.read",)
        )
        self.assertNotIn("workspace.search", client.requests[0].model_dump_json())
        admission = controller.state.entries[0].request_admission
        assert admission is not None and admission.task_profile is not None
        self.assertEqual(admission.task_profile, preview.task_profile)
        evidence = admission.task_profile.acquisition
        assert evidence is not None and evidence.tool_catalog is not None
        self.assertEqual(evidence.tool_catalog.selected_tool_ids, ("workspace.read",))
        self.assertEqual(evidence.tool_catalog.omitted_tool_ids, ("workspace.search",))
        self.assertEqual(admission.task_profile.report.status, "warning")
        saved_json = admission.task_profile.model_dump_json()
        self.assertIn("Not needed for this exact task.", saved_json)
        self.assertNotIn("Search approved workspace text.", saved_json)
        described = inspect_admission(controller.state, 0).describe()
        self.assertIn("Runtime tool catalog: approved-workspace-tools@3", described)
        self.assertIn("tool execution remains disabled", described)

    async def test_required_omission_fails_before_attempt(self) -> None:
        self.write_tool_selection(
            self.tool_selection(required_read=True, select_read=False)
        )
        acquirer = self.catalog_acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile_acquirer=acquirer
        )
        controller.submit(DEMO_PROMPTS[0])
        client = CapturingClient()

        with self.assertRaisesRegex(ValueError, "failing task profile"):
            await controller.step(client)

        self.assertEqual(controller.state.entries[0].status, "queued")
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertEqual(client.requests, [])

    async def test_review_does_not_acquire_or_expose_author_tools(self) -> None:
        acquirer = self.catalog_acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile_acquirer=acquirer
        )
        controller.submit_review(review_packet())

        await controller.step()

        self.assertIsNone(controller.state.entries[0].request_admission)
        self.assertIsNotNone(controller.state.entries[0].review_result)


class RuntimeToolCatalogBoundaryTests(ToolCatalogFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_catalog(self)

    def test_stale_catalog_and_incomplete_inventory_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "stale or different catalog"):
            RuntimeToolCatalogSelectingAcquirer(
                base_acquirer=self.semantic_acquirer(),
                catalog_payload=self.catalog_path.read_bytes(),
                selection_payload=canonical_bytes(
                    self.tool_selection(catalog_sha="f" * 64)
                ),
            )
        decision = (
            self.tool_selection()
            .decisions[0]
            .model_copy(
                update={"choices": self.tool_selection().decisions[0].choices[:1]}
            )
        )
        incomplete = self.tool_selection().model_copy(update={"decisions": (decision,)})
        with self.assertRaisesRegex(ValueError, "ordered catalog inventory"):
            RuntimeToolCatalogSelectingAcquirer(
                base_acquirer=self.semantic_acquirer(),
                catalog_payload=self.catalog_path.read_bytes(),
                selection_payload=canonical_bytes(incomplete),
            )

    def test_unavailable_or_unauthorized_selected_tool_fails(self) -> None:
        for update in (
            {"availability": "unavailable"},
            {"authorized": False},
        ):
            first = self.catalog.tools[0].model_copy(update=update)
            catalog = self.catalog.model_copy(
                update={"tools": (first, self.catalog.tools[1])}
            )
            catalog_payload = canonical_bytes(catalog)
            selection = self.tool_selection(
                catalog_sha=digest(catalog_payload)
            ).model_copy(
                update={
                    "expected_catalog_id": catalog.catalog_id,
                    "expected_catalog_revision": catalog.revision,
                }
            )
            acquirer = RuntimeToolCatalogSelectingAcquirer(
                base_acquirer=self.semantic_acquirer(),
                catalog_payload=catalog_payload,
                selection_payload=canonical_bytes(selection),
            )

            with self.assertRaisesRegex(ValueError, "failing task profile"):
                acquirer.acquire(
                    owner_uid=os.getuid(),
                    workspace=str(Path(self.workspace).resolve()),
                    task_text=DEMO_PROMPTS[0],
                )

    def test_exact_task_profile_and_schema_metadata_are_required(self) -> None:
        acquirer = self.catalog_acquirer()
        with self.assertRaisesRegex(ValueError, "no exact queued-task decision"):
            acquirer.acquire(
                owner_uid=os.getuid(),
                workspace=str(Path(self.workspace).resolve()),
                task_text=DEMO_PROMPTS[1],
            )
        definition = self.catalog.tools[0].definition
        with self.assertRaisesRegex(ValueError, "schema metadata"):
            RuntimeToolCatalogEntry(
                tool_id=definition.name,
                definition=definition,
                schema_sha256="f" * 64,
                schema_bytes=len(canonical_bytes(definition)),
                authorized=True,
                availability="available",
            )

    def test_duplicate_keys_and_editable_examples_are_validated(self) -> None:
        duplicate = self.catalog_path.read_bytes().replace(
            b'"schema_version":1',
            b'"schema_version":1,"schema_version":1',
            1,
        )
        with self.assertRaisesRegex(ValueError, "Invalid runtime tool catalog"):
            decode_runtime_tool_catalog(duplicate)
        self.assertEqual(
            decode_runtime_tool_catalog(
                (Path("templates") / "RUNTIME_TOOL_CATALOG_EXAMPLE.json").read_bytes()
            ).catalog_id,
            "approved-workspace-tools",
        )
        self.assertEqual(
            decode_runtime_tool_selection(
                (Path("templates") / "RUNTIME_TOOL_SELECTION_EXAMPLE.json").read_bytes()
            )
            .decisions[0]
            .choices[0]
            .tool_id,
            "workspace.read",
        )

    def test_plain_terminal_uses_selected_schema_without_dispatch(self) -> None:
        acquirer = self.catalog_acquirer()
        profile = acquirer.acquire(
            owner_uid=os.getuid(),
            workspace=str(Path(self.workspace).resolve()),
            task_text=DEMO_PROMPTS[0],
        )
        turn = Turn(role="user", blocks=(TextBlock(text=DEMO_PROMPTS[0]),))
        request, _ = prepare_conversation_request(
            conversation_config((turn,), task_profile=profile), profile
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
        cassette_path = self.guidance.base / "tool-catalog-cassette.json"
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
                str(self.guidance.base / "sessions"),
                "--cassette",
                str(cassette_path),
                "--task-profile-selection",
                str(self.discovery_path),
                "--task-profile-policy",
                str(self.policy_path),
                "--task-guidance-storage",
                str(self.storage),
                "--task-tool-catalog",
                str(self.catalog_path),
                "--task-tool-selection",
                str(self.tool_selection_path),
            ],
            input=DEMO_PROMPTS[0] + "\n",
            text=True,
            capture_output=True,
            timeout=20,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("The fixture boundary is ten.", result.stdout)
