"""Explicit checkpoint selection starts one bounded, fresh-context continuation."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

from test_conversation_checkpoint_closure import scoped_bundle
from test_conversation_context import CapturingClient

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_admission_inspection import inspect_admission
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.task_checkpoint_store import (
    ContinuationClaimError,
    ResolvedContinuation,
    TaskCheckpointStore,
)
from mos_eisley.run.task_state_store import ProfileAssessment, TaskStateBundle
from mos_eisley.task_profile import (
    InstructionProfileEntry,
    ProfileSizes,
    TaskInstructionContent,
    TaskProfileManifest,
    ToolProfileEntry,
    diagnose_task_profile,
)
from mos_eisley.task_state import (
    ContinuationSelection,
    OwnerProjectScope,
    TaskContinuationClaim,
    WorkspaceState,
)
from mos_eisley.tools.fixture import FixtureDispatcher, FixtureValues


def enabled_bundle(
    root: Path,
) -> tuple[TaskStateBundle, OwnerProjectScope, bytes]:
    bundle, scope, payload = scoped_bundle(root)
    selected = bundle.checkpoint.next_actions[0]
    work_units = tuple(
        item.model_copy(update={"task_profile_id": "g1-runtime-owned"})
        if item.reference == selected
        else item
        for item in bundle.work_units
    )
    work_unit = next(item for item in work_units if item.reference == selected)
    instruction_text = "Continue only the selected checkpoint work unit."
    instruction = InstructionProfileEntry(
        rule_id="selected-work-unit",
        source_sha256=digest(b"selected work-unit source"),
        content_sha256=digest(instruction_text.encode("utf-8")),
        bytes=len(instruction_text.encode("utf-8")),
        scope="selected checkpoint work unit",
        required=True,
        selected=True,
        selection_reason="Owned by the selected continuation work unit.",
        location="reference",
        classification="stable_rule",
    )
    manifest = TaskProfileManifest(
        scope=scope,
        profile_id="g1-runtime-owned",
        work_unit=work_unit.reference,
        policy_sha256=work_unit.policy_sha256,
        instructions=(instruction,),
        sizes=ProfileSizes(
            root_instruction_bytes=0,
            instruction_bytes=instruction.bytes,
            tool_schema_bytes=0,
            total_bytes=instruction.bytes,
        ),
    )
    assessment = ProfileAssessment(
        schema_version=2,
        manifest=manifest,
        report=diagnose_task_profile(manifest),
        instructions=(
            TaskInstructionContent(rule_id=instruction.rule_id, text=instruction_text),
        ),
    )
    enabled = TaskStateBundle.model_validate(
        bundle.model_copy(
            update={
                "schema_version": 2,
                "work_units": work_units,
                "profiles": bundle.profiles + (assessment,),
                "runtime_continuation_enabled": True,
            }
        ).model_dump(mode="python")
    )
    return enabled, scope, payload


def selection_for(bundle: TaskStateBundle) -> ContinuationSelection:
    checkpoint = bundle.checkpoint
    work_units = {item.reference: item for item in bundle.work_units}
    work_unit = work_units[checkpoint.next_actions[0]]
    return ContinuationSelection(
        scope=bundle.scope,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_revision=checkpoint.revision,
        checkpoint_sha256=checkpoint.sha256,
        selected_work_unit=work_unit.reference,
        workspace=checkpoint.workspace,
        required_inputs=work_unit.required_inputs,
        context_baseline=checkpoint.context_metrics,
        ledger_baseline=checkpoint.task_ledger,
    )


def tool_enabled_bundle(
    root: Path,
) -> tuple[TaskStateBundle, OwnerProjectScope, bytes]:
    bundle, scope, payload = enabled_bundle(root)
    definition = FixtureDispatcher(FixtureValues(values={"answer": "42"})).definitions[
        0
    ]
    schema = canonical_bytes(definition.input_schema)
    assessment = bundle.profiles[-1]
    manifest = assessment.manifest.model_copy(
        update={
            "tools": (
                ToolProfileEntry(
                    tool_id=definition.name,
                    schema_sha256=digest(schema),
                    schema_bytes=len(schema),
                    required=True,
                    selected=True,
                    authorized=True,
                    availability="available",
                    selection_reason="Required by the owned work unit.",
                ),
            ),
            "sizes": assessment.manifest.sizes.model_copy(
                update={
                    "tool_schema_bytes": len(schema),
                    "total_bytes": assessment.manifest.sizes.instruction_bytes
                    + len(schema),
                }
            ),
        }
    )
    updated = ProfileAssessment(
        schema_version=2,
        manifest=manifest,
        report=diagnose_task_profile(manifest),
        instructions=assessment.instructions,
    )
    return (
        TaskStateBundle.model_validate(
            bundle.model_copy(
                update={"profiles": bundle.profiles[:-1] + (updated,)}
            ).model_dump(mode="python")
        ),
        scope,
        payload,
    )


class ContinuationStoreTests(TestCase):
    def test_runtime_next_action_requires_exact_owned_profile_material(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            unowned, scope, payload = scoped_bundle(root)
            legacy = TaskStateBundle.model_validate(
                unowned.model_copy(
                    update={"runtime_continuation_enabled": True}
                ).model_dump(mode="python")
            )
            self.assertEqual(legacy.schema_version, 1)
            with TaskCheckpointStore(
                root / "legacy-checkpoints",
                scope,
                legacy.checkpoint.checkpoint_id,
            ) as store:
                store.close_milestone(
                    legacy, {digest(payload): payload}, expected_revision=0
                )
                with self.assertRaisesRegex(
                    ContinuationClaimError, "no owned task profile"
                ):
                    store.claim_continuation(
                        selection_for(legacy),
                        session_id="f" * 32,
                        observed_workspace=legacy.checkpoint.workspace,
                    )
            with self.assertRaisesRegex(ValueError, "owned task profiles"):
                TaskStateBundle.model_validate(
                    unowned.model_copy(
                        update={
                            "schema_version": 2,
                            "runtime_continuation_enabled": True,
                        }
                    ).model_dump(mode="python")
                )

            owned, _, _ = enabled_bundle(root)
            assessment = owned.profiles[-1]
            substituted = assessment.instructions[0].model_copy(
                update={"text": "substituted"}
            )
            bad_assessment = assessment.model_copy(
                update={"instructions": (substituted,)}
            )
            with self.assertRaisesRegex(ValueError, "instruction content"):
                TaskStateBundle.model_validate(
                    owned.model_copy(
                        update={"profiles": owned.profiles[:-1] + (bad_assessment,)}
                    ).model_dump(mode="python")
                )

            stale_units = tuple(
                item.model_copy(update={"policy_sha256": digest(b"changed policy")})
                if item.reference == owned.checkpoint.next_actions[0]
                else item
                for item in owned.work_units
            )
            with self.assertRaisesRegex(ValueError, "binding is stale"):
                TaskStateBundle.model_validate(
                    owned.model_copy(update={"work_units": stale_units}).model_dump(
                        mode="python"
                    )
                )

    def test_claim_is_idempotent_for_one_session_and_exclusive_between_sessions(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = enabled_bundle(root)
            selection = selection_for(bundle)
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as store:
                store.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )
                first = store.claim_continuation(
                    selection,
                    session_id="a" * 32,
                    observed_workspace=bundle.checkpoint.workspace,
                )
                repeated = store.claim_continuation(
                    selection,
                    session_id="a" * 32,
                    observed_workspace=bundle.checkpoint.workspace,
                )
                self.assertEqual(repeated, first)
                with self.assertRaisesRegex(ContinuationClaimError, "already claimed"):
                    store.claim_continuation(
                        selection,
                        session_id="b" * 32,
                        observed_workspace=bundle.checkpoint.workspace,
                    )

    def test_changed_workspace_names_stale_tests_without_changing_claim_state(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = enabled_bundle(root)
            changed = bundle.checkpoint.workspace.model_copy(
                update={
                    "tree_sha256": digest(b"changed tree"),
                    "dirty_state_sha256": digest(b"changed dirty state"),
                }
            )
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as store:
                head = store.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )
                with self.assertRaisesRegex(
                    ContinuationClaimError, "stale verification IDs: focused-tests"
                ):
                    store.claim_continuation(
                        selection_for(bundle),
                        session_id="c" * 32,
                        observed_workspace=changed,
                    )
                self.assertEqual(store.load_current()[0], head)  # type: ignore[index]


class ConversationContinuationTests(IsolatedAsyncioTestCase):
    async def test_owned_profile_admission_round_trips_through_sqlite(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = enabled_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with (
                SQLiteConversationStore(
                    root / "sessions", state.session_id, root
                ) as sessions,
                TaskCheckpointStore(
                    root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
                ) as checkpoints,
            ):
                sessions.save(state)
                checkpoints.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )
                controller = ConversationController(
                    state,
                    cassette,
                    sessions.save,
                    task_scope=scope,
                    claim_task_continuation=checkpoints.claim_continuation,
                    resolve_task_continuation=checkpoints.resolve_continuation,
                    observe_task_workspace=lambda: bundle.checkpoint.workspace,
                )
                controller.begin_continuation(selection_for(bundle))
                controller.submit(DEMO_PROMPTS[0])
                await controller.step(CapturingClient())
                expected = controller.state.entries[0].request_admission
                restored = sessions.load()

            self.assertEqual(restored.entries[0].request_admission, expected)
            assert expected is not None
            self.assertEqual(expected.schema_version, 6)

    async def test_owned_profile_selects_only_its_bound_tool_schema(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = tool_enabled_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            dispatcher = FixtureDispatcher(FixtureValues(values={"answer": "42"}))
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as checkpoints:
                checkpoints.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )
                controller = ConversationController(
                    state,
                    cassette,
                    lambda _: None,
                    task_scope=scope,
                    tool_dispatcher=dispatcher,
                    claim_task_continuation=checkpoints.claim_continuation,
                    resolve_task_continuation=checkpoints.resolve_continuation,
                    observe_task_workspace=lambda: bundle.checkpoint.workspace,
                )
                controller.begin_continuation(selection_for(bundle))
                controller.submit(DEMO_PROMPTS[0])
                client = CapturingClient()
                await controller.step(client)

                self.assertEqual(
                    tuple(item.name for item in client.requests[0].tools),
                    ("fixture_lookup",),
                )
                admission = controller.state.entries[0].request_admission
                assert admission is not None
                assert admission.task_profile is not None
                self.assertEqual(
                    admission.task_profile.selected_tool_ids, ("fixture_lookup",)
                )

    async def test_fresh_claim_is_revalidated_and_admitted_before_dispatch(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = enabled_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            observed = [bundle.checkpoint.workspace]
            with (
                ConversationStore(
                    root / "sessions", state.session_id, root
                ) as sessions,
                TaskCheckpointStore(
                    root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
                ) as checkpoints,
            ):
                sessions.save(state)
                checkpoints.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )
                controller = ConversationController(
                    state,
                    cassette,
                    sessions.save,
                    task_scope=scope,
                    claim_task_continuation=checkpoints.claim_continuation,
                    resolve_task_continuation=checkpoints.resolve_continuation,
                    observe_task_workspace=lambda: observed[0],
                )
                claim = controller.begin_continuation(selection_for(bundle))
                boundary = controller.state.context_pressure_boundary
                assert boundary is not None
                self.assertEqual(boundary.kind, "continuation")
                self.assertEqual(boundary.next_message_position, 0)
                revision = controller.state.revision
                self.assertEqual(
                    controller.begin_continuation(selection_for(bundle)), claim
                )
                self.assertEqual(controller.state.revision, revision)
                controller.submit(DEMO_PROMPTS[0])
                client = CapturingClient()
                await controller.step(client)

                admission = controller.state.entries[0].request_admission
                assert admission is not None
                assert admission.context_classification is not None
                assert admission.task_continuation is not None
                assert admission.task_profile is not None
                self.assertEqual(admission.schema_version, 6)
                self.assertTrue(admission.context_classification.checkpoint_selected)
                self.assertEqual(admission.task_continuation.claim_id, claim.claim_id)
                self.assertEqual(admission.task_profile.profile_id, "g1-runtime-owned")
                self.assertEqual(admission.task_profile.schema_version, 2)
                acquisition = admission.task_profile.acquisition
                assert acquisition is not None
                self.assertEqual(acquisition.bundle_sha256, bundle.sha256)
                self.assertEqual(
                    acquisition.work_unit,
                    admission.task_continuation.selected_work_unit,
                )
                self.assertIn(bundle.checkpoint.view.summary, client.requests[0].system)
                self.assertIn(bundle.work_units[1].objective, client.requests[0].system)
                self.assertIn(
                    "Continue only the selected checkpoint work unit.",
                    client.requests[0].system,
                )
                self.assertNotIn(
                    "Continue only the selected checkpoint work unit.",
                    admission.model_dump_json(),
                )
                description = inspect_admission(controller.state, 0).describe()
                self.assertIn("Profile acquisition: work-unit-owned", description)
                self.assertNotIn(
                    "Continue only the selected checkpoint work unit.", description
                )
                restored = sessions.load()
                self.assertEqual(restored.task_continuation, claim)

    def test_continue_request_supplies_selection_without_another_confirmation(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = enabled_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as checkpoints:
                checkpoints.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )
                controller = ConversationController(
                    state,
                    cassette,
                    lambda _state: None,
                    task_scope=scope,
                    claim_task_continuation=checkpoints.claim_continuation,
                    resolve_task_continuation=checkpoints.resolve_continuation,
                    observe_task_workspace=lambda: bundle.checkpoint.workspace,
                )
                claim = controller.submit_continuation(
                    "Continue the selected work.", selection_for(bundle)
                )
                self.assertEqual(controller.state.task_continuation, claim)
                self.assertEqual(
                    controller.state.entries[0].text, "Continue the selected work."
                )
                self.assertEqual(controller.state.entries[0].status, "queued")

    async def test_workspace_change_after_claim_stops_before_provider_dispatch(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = enabled_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            observed: list[WorkspaceState] = [bundle.checkpoint.workspace]
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as checkpoints:
                checkpoints.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )
                controller = ConversationController(
                    state,
                    cassette,
                    lambda _state: None,
                    task_scope=scope,
                    claim_task_continuation=checkpoints.claim_continuation,
                    resolve_task_continuation=checkpoints.resolve_continuation,
                    observe_task_workspace=lambda: observed[0],
                )
                controller.begin_continuation(selection_for(bundle))
                controller.submit(DEMO_PROMPTS[0])
                observed[0] = observed[0].model_copy(
                    update={"branch": "changed-after-claim"}
                )
                client = CapturingClient()
                with self.assertRaisesRegex(
                    ContinuationClaimError, "workspace changed"
                ):
                    await controller.step(client)
                self.assertEqual(client.requests, [])
                self.assertEqual(controller.state.entries[0].status, "queued")
                self.assertIsNotNone(controller.state.task_continuation)

    async def test_substituted_profile_acquisition_stops_before_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = enabled_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as checkpoints:
                checkpoints.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )

                def substituted(
                    claim: TaskContinuationClaim,
                    *,
                    observed_workspace: WorkspaceState,
                ) -> ResolvedContinuation:
                    resolved = checkpoints.resolve_continuation(
                        claim, observed_workspace=observed_workspace
                    )
                    source = resolved.profile.acquisition.model_copy(
                        update={"checkpoint_sha256": digest(b"other checkpoint")}
                    )
                    profile = type(resolved.profile).model_validate(
                        {"profile": resolved.profile.profile, "acquisition": source}
                    )
                    return resolved._replace(profile=profile)

                controller = ConversationController(
                    state,
                    cassette,
                    lambda _: None,
                    task_scope=scope,
                    claim_task_continuation=checkpoints.claim_continuation,
                    resolve_task_continuation=substituted,
                    observe_task_workspace=lambda: bundle.checkpoint.workspace,
                )
                controller.begin_continuation(selection_for(bundle))
                controller.submit(DEMO_PROMPTS[0])
                client = CapturingClient()

                with self.assertRaisesRegex(ValueError, "profile acquisition differs"):
                    await controller.step(client)
                self.assertEqual(controller.state.exchanges_consumed, 0)
                self.assertIsNone(controller.state.entries[0].request_admission)
                self.assertEqual(client.requests, [])

    def test_existing_history_cannot_acquire_a_fresh_context_claim(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = enabled_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as checkpoints:
                checkpoints.close_milestone(
                    bundle, {digest(payload): payload}, expected_revision=0
                )
                controller = ConversationController(
                    state,
                    cassette,
                    lambda _state: None,
                    task_scope=scope,
                    claim_task_continuation=checkpoints.claim_continuation,
                    resolve_task_continuation=checkpoints.resolve_continuation,
                    observe_task_workspace=lambda: bundle.checkpoint.workspace,
                )
                controller.submit("ambient old history")
                with self.assertRaisesRegex(ContinuationClaimError, "fresh"):
                    controller.begin_continuation(selection_for(bundle))
                self.assertIsNone(controller.state.task_continuation)
