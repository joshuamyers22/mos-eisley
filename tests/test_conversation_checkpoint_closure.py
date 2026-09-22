"""Completed milestones close into one private revision-checked task checkpoint."""

import os
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Never, cast
from unittest import IsolatedAsyncioTestCase, TestCase

from test_conversation_context import CapturingClient
from test_task_state_g0 import g0_fixture

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.core.models import digest
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.task_checkpoint_store import (
    ARCHIVE_DIRECTORY,
    HEAD_FILE,
    LOCK_FILE,
    CheckpointClosureError,
    CheckpointClosureReason,
    TaskCheckpointStore,
)
from mos_eisley.run.task_state_store import ProfileAssessment, TaskStateBundle
from mos_eisley.task_profile import TaskProfileManifest, diagnose_task_profile
from mos_eisley.task_state import OwnerProjectScope, WorkspaceState


def _replace_scope(
    value: object, before: dict[str, object], after: dict[str, object]
) -> object:
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        if mapping == before:
            return after
        return {
            key: _replace_scope(item, before, after) for key, item in mapping.items()
        }
    if isinstance(value, tuple):
        items = cast(tuple[object, ...], value)
        return tuple(_replace_scope(item, before, after) for item in items)
    if isinstance(value, list):
        items = cast(list[object], value)
        return [_replace_scope(item, before, after) for item in items]
    return value


def scoped_bundle(root: Path) -> tuple[TaskStateBundle, OwnerProjectScope, bytes]:
    fixture = g0_fixture()
    scope = OwnerProjectScope(
        owner_uid=os.getuid(),
        project_id="checkpoint-closure",
        workspace_sha256=digest(str(root.resolve()).encode("utf-8")),
    )
    data = cast(
        dict[str, object],
        _replace_scope(
            fixture.bundle.model_dump(mode="python"),
            fixture.scope.model_dump(mode="python"),
            scope.model_dump(mode="python"),
        ),
    )
    manifest = TaskProfileManifest.model_validate(
        _replace_scope(
            fixture.profile.model_dump(mode="python"),
            fixture.scope.model_dump(mode="python"),
            scope.model_dump(mode="python"),
        )
    )
    data["profiles"] = (
        ProfileAssessment(
            manifest=manifest,
            report=diagnose_task_profile(manifest),
        ),
    )
    return TaskStateBundle.model_validate(data), scope, fixture.artifact_payload


def next_bundle(previous: TaskStateBundle, *, durable: bool = True) -> TaskStateBundle:
    checkpoint = previous.checkpoint
    workspace = checkpoint.workspace
    if durable:
        workspace = WorkspaceState(
            repository_sha256=workspace.repository_sha256,
            branch=workspace.branch,
            revision="fixture-tree-2",
            tree_sha256=digest(b"tree revision 2"),
            dirty_state_sha256=digest(b"dirty state revision 2"),
        )
    verifications = tuple(
        item.model_copy(
            update={
                "bound_workspace_sha256": workspace.sha256,
                "bound_input_sha256": workspace.dirty_state_sha256,
            }
        )
        for item in checkpoint.verifications
    )
    changed = checkpoint.model_copy(
        update={
            "revision": checkpoint.revision + 1,
            "previous_checkpoint_sha256": checkpoint.sha256,
            "workspace": workspace,
            "verifications": verifications,
            "lineage_sha256": (
                digest(b"lineage revision 2") if durable else checkpoint.lineage_sha256
            ),
        }
    )
    return TaskStateBundle.model_validate(
        previous.model_copy(
            update={
                "revision": previous.revision + 1,
                "previous_bundle_sha256": previous.sha256,
                "checkpoint": changed,
            }
        ).model_dump(mode="python")
    )


class TaskCheckpointStoreTests(TestCase):
    def test_completed_milestone_is_private_replayable_and_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = scoped_bundle(root)
            artifacts = {digest(payload): payload}
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as store:
                head = store.close_milestone(bundle, artifacts, expected_revision=0)
                repeated = store.close_milestone(bundle, artifacts, expected_revision=0)
                loaded = store.load_current()

            self.assertEqual(repeated, head)
            assert loaded is not None
            self.assertEqual(loaded[0], head)
            self.assertEqual(loaded[1], bundle)
            self.assertEqual(head.closure_reason, "completed_milestone")
            self.assertFalse(head.grants_authority)
            checkpoint_root = root / "checkpoints"
            self.assertEqual(
                {item.name for item in checkpoint_root.iterdir()},
                {ARCHIVE_DIRECTORY, HEAD_FILE, LOCK_FILE},
            )
            for path in checkpoint_root.rglob("*"):
                self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_revision_lineage_and_durable_change_are_compare_and_swap(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = scoped_bundle(root)
            artifacts = {digest(payload): payload}
            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as store:
                first = store.close_milestone(bundle, artifacts, expected_revision=0)
                updated = next_bundle(bundle)
                with self.assertRaisesRegex(CheckpointClosureError, "revision changed"):
                    store.close_milestone(updated, artifacts, expected_revision=0)
                self.assertEqual(store.load_current()[0], first)  # type: ignore[index]
                second = store.close_milestone(updated, artifacts, expected_revision=1)
                self.assertEqual(second.checkpoint_revision, 2)
                unchanged = next_bundle(updated, durable=False)
                with self.assertRaisesRegex(
                    CheckpointClosureError, "no durable state change"
                ):
                    store.close_milestone(unchanged, artifacts, expected_revision=2)
                self.assertEqual(store.load_current()[0], second)  # type: ignore[index]

    def test_incomplete_or_oversized_closure_never_publishes_a_head(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = scoped_bundle(root)
            queued = bundle.work_units[1]
            incomplete_checkpoint = bundle.checkpoint.model_copy(
                update={
                    "current_work_unit": queued.reference,
                    "task_ledger": queued.ledger,
                }
            )
            incomplete = TaskStateBundle.model_validate(
                bundle.model_copy(
                    update={"checkpoint": incomplete_checkpoint}
                ).model_dump(mode="python")
            )
            artifacts = {digest(payload): payload}
            with TaskCheckpointStore(
                root / "incomplete", scope, bundle.checkpoint.checkpoint_id
            ) as store:
                with self.assertRaisesRegex(
                    CheckpointClosureError, "completed current work unit"
                ):
                    store.close_milestone(incomplete, artifacts, expected_revision=0)
                self.assertIsNone(store.load_current())
            active = queued.model_copy(update={"status": "active"})
            handoff_checkpoint = bundle.checkpoint.model_copy(
                update={
                    "current_work_unit": active.reference,
                    "task_ledger": active.ledger,
                }
            )
            handoff = TaskStateBundle.model_validate(
                bundle.model_copy(
                    update={
                        "work_units": (bundle.work_units[0], active),
                        "checkpoint": handoff_checkpoint,
                    }
                ).model_dump(mode="python")
            )
            with TaskCheckpointStore(
                root / "handoff", scope, bundle.checkpoint.checkpoint_id
            ) as store:
                head = store.close_milestone(
                    handoff,
                    artifacts,
                    expected_revision=0,
                    reason="deliberate_handoff",
                )
                self.assertEqual(head.closure_reason, "deliberate_handoff")
            with TaskCheckpointStore(
                root / "oversized",
                scope,
                bundle.checkpoint.checkpoint_id,
                max_view_bytes=8,
            ) as store:
                with self.assertRaisesRegex(CheckpointClosureError, "closure limit"):
                    store.close_milestone(bundle, artifacts, expected_revision=0)
                self.assertIsNone(store.load_current())

    def test_store_lock_rejects_a_concurrent_closer(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, _payload = scoped_bundle(root)
            with (
                TaskCheckpointStore(
                    root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
                ),
                self.assertRaises(BlockingIOError),
            ):
                TaskCheckpointStore(
                    root / "checkpoints",
                    scope,
                    bundle.checkpoint.checkpoint_id,
                )


class ConversationCheckpointClosureTests(IsolatedAsyncioTestCase):
    async def test_controller_closes_links_and_does_not_load_checkpoint_as_memory(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = scoped_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with (
                ConversationStore(
                    root / "sessions", state.session_id, root
                ) as conversation_store,
                TaskCheckpointStore(
                    root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
                ) as checkpoint_store,
            ):
                conversation_store.save(state)
                controller = ConversationController(
                    state,
                    cassette,
                    conversation_store.save,
                    task_scope=scope,
                    close_task_checkpoint=checkpoint_store.close_milestone,
                )
                head = controller.close_milestone(
                    bundle,
                    {digest(payload): payload},
                    expected_checkpoint_revision=0,
                )
                self.assertEqual(controller.state.task_checkpoint, head)
                boundary = controller.state.context_pressure_boundary
                assert boundary is not None
                self.assertEqual(boundary.kind, "checkpoint")
                self.assertEqual(
                    boundary.conversation_revision, controller.state.revision
                )
                revision = controller.state.revision
                self.assertEqual(
                    controller.close_milestone(
                        bundle,
                        {digest(payload): payload},
                        expected_checkpoint_revision=1,
                    ),
                    head,
                )
                self.assertEqual(controller.state.revision, revision)
                restored = conversation_store.load()
                self.assertEqual(restored.task_checkpoint, head)

                controller.submit(DEMO_PROMPTS[0])
                client = CapturingClient()
                await controller.step(client)
                admission = controller.state.entries[0].request_admission
                assert admission is not None
                classification = admission.context_classification
                assert classification is not None
                self.assertFalse(classification.checkpoint_selected)
                self.assertNotIn(
                    bundle.checkpoint.view.summary, client.requests[0].system
                )

    async def test_scope_and_conversation_save_failures_are_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, scope, payload = scoped_bundle(root)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            wrong_scope = scope.model_copy(update={"project_id": "another-project"})

            def unexpected_store(
                bundle: TaskStateBundle,
                artifacts: Mapping[str, bytes],
                *,
                expected_revision: int,
                reason: CheckpointClosureReason = "completed_milestone",
            ) -> Never:
                del bundle, artifacts, expected_revision, reason
                raise AssertionError("store must not run")

            controller = ConversationController(
                state,
                cassette,
                lambda _state: None,
                task_scope=wrong_scope,
                close_task_checkpoint=unexpected_store,
            )
            with self.assertRaisesRegex(CheckpointClosureError, "task scope"):
                controller.close_milestone(
                    bundle,
                    {digest(payload): payload},
                    expected_checkpoint_revision=0,
                )
            self.assertIsNone(controller.state.task_checkpoint)

            with TaskCheckpointStore(
                root / "checkpoints", scope, bundle.checkpoint.checkpoint_id
            ) as checkpoint_store:

                def fail_save(_state: object) -> None:
                    raise OSError("save failed")

                failing = ConversationController(
                    state,
                    cassette,
                    fail_save,
                    task_scope=scope,
                    close_task_checkpoint=checkpoint_store.close_milestone,
                )
                with self.assertRaisesRegex(
                    CheckpointClosureError, "conversation link is uncertain"
                ):
                    failing.close_milestone(
                        bundle,
                        {digest(payload): payload},
                        expected_checkpoint_revision=0,
                    )
                self.assertIsNone(failing.state.task_checkpoint)
                current = checkpoint_store.load_current()
                assert current is not None
                self.assertEqual(current[0].bundle_sha256, bundle.sha256)
