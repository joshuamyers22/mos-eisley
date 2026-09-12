"""Persistent mapping review, hostile storage, startup and resume boundaries."""

import argparse
import asyncio
import fcntl
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.cli import parser
from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette, run_command
from mos_eisley.conversation_directory import (
    DirectoryPicker,
    DirectorySelection,
    DirectorySelectionError,
)
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_registry import (
    MAX_MAPPINGS,
    REGISTRY_BYTES,
    REGISTRY_NAME,
    MappedDirectory,
    MemoryMappingRegistry,
    MemoryMappingResolver,
    MemoryMappingStore,
    SavedMemoryMapping,
)
from mos_eisley.conversation_switch import fresh_directory_arguments
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


class MemoryRegistryTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "workspace"
        self.target = self.base / "shared"
        self.other = self.base / "other"
        for path in (self.workspace, self.target, self.other):
            path.mkdir()
        self.storage = self.base / "memory"
        self.registry = MemoryMappingStore(self.storage)

    def save(self, workspace: Path | None = None, target: Path | None = None) -> None:
        workspace = workspace or self.workspace
        target = target or self.target
        receipt = self.registry.change(workspace, target)
        self.registry.change(
            workspace, target, expected_sha256=str(receipt["preview_sha256"])
        )

    def launch(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *arguments],
            input="/quit\n",
            capture_output=True,
            text=True,
            cwd=self.base,
            timeout=20,
        )

    def test_bootstrap_review_is_read_only_and_bad_hash_does_not_create(self) -> None:
        self.assertEqual(self.registry.read().mappings, ())
        receipt = self.registry.change(self.workspace, self.target)
        self.assertFalse(self.storage.exists())
        with self.assertRaises(ValueError):
            self.registry.change(self.workspace, self.target, expected_sha256="0" * 64)
        self.assertFalse(self.storage.exists())
        applied = self.registry.change(
            self.workspace, self.target, expected_sha256=str(receipt["preview_sha256"])
        )
        self.assertTrue(applied["applied"])
        self.assertEqual(applied["preview_sha256"], receipt["preview_sha256"])
        self.assertEqual(self.storage.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.storage / REGISTRY_NAME).stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            set(p.name for p in self.storage.iterdir()), {"memory.lock", REGISTRY_NAME}
        )

    def test_full_registry_change_invalidates_old_review(self) -> None:
        self.save()
        pending = self.registry.change(self.workspace, self.other)
        self.save(self.other, self.target)
        before = (self.storage / REGISTRY_NAME).read_bytes()
        with self.assertRaises(ValueError):
            self.registry.change(
                self.workspace,
                self.other,
                expected_sha256=str(pending["preview_sha256"]),
            )
        self.assertEqual((self.storage / REGISTRY_NAME).read_bytes(), before)

    def test_atomic_publish_failure_preserves_old_registry(self) -> None:
        self.save()
        pending = self.registry.change(self.workspace, self.other)
        before = (self.storage / REGISTRY_NAME).read_bytes()
        with (
            patch(
                "mos_eisley.conversation_memory_registry.os.replace",
                side_effect=OSError("interrupted"),
            ),
            self.assertRaises(OSError),
        ):
            self.registry.change(
                self.workspace,
                self.other,
                expected_sha256=str(pending["preview_sha256"]),
            )
        self.assertEqual((self.storage / REGISTRY_NAME).read_bytes(), before)
        self.assertFalse(tuple(self.storage.glob(".memory-mappings-*.tmp")))

    def test_post_replace_flush_failure_requires_fresh_review(self) -> None:
        self.save()
        pending = self.registry.change(self.workspace, self.other)
        fsync = os.fsync
        count = 0

        def fail_directory(fd: int) -> None:
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("directory flush failed")
            fsync(fd)

        with (
            patch(
                "mos_eisley.conversation_memory_registry.os.fsync",
                side_effect=fail_directory,
            ),
            self.assertRaises(OSError),
        ):
            self.registry.change(
                self.workspace,
                self.other,
                expected_sha256=str(pending["preview_sha256"]),
            )
        self.assertEqual(self.registry.read().mappings[0].target.path, str(self.other))
        with self.assertRaises(ValueError):
            self.registry.change(
                self.workspace,
                self.other,
                expected_sha256=str(pending["preview_sha256"]),
            )

    def test_late_directory_replacement_cannot_publish_reviewed_mapping(self) -> None:
        self.save()
        pending = self.registry.change(self.workspace, self.other)
        before = (self.storage / REGISTRY_NAME).read_bytes()
        fsync = os.fsync

        def replace_directory(fd: int) -> None:
            fsync(fd)
            self.other.rename(self.base / "moved-other")
            self.other.mkdir()

        with (
            patch(
                "mos_eisley.conversation_memory_registry.os.fsync",
                side_effect=replace_directory,
            ),
            self.assertRaises(DirectorySelectionError),
        ):
            self.registry.change(
                self.workspace,
                self.other,
                expected_sha256=str(pending["preview_sha256"]),
            )
        self.assertEqual((self.storage / REGISTRY_NAME).read_bytes(), before)

    def test_process_death_leaves_complete_old_or_new_registry(self) -> None:
        script = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_registry import MemoryMappingStore
store = MemoryMappingStore(Path(sys.argv[1]))
workspace, target = Path(sys.argv[2]), Path(sys.argv[3])
receipt = store.change(workspace, target)
replace = os.replace
def die(*args, **kwargs):
    if sys.argv[4] == 'after':
        replace(*args, **kwargs)
    os._exit(73)
with patch('mos_eisley.conversation_memory_registry.os.replace', side_effect=die):
    store.change(workspace, target, expected_sha256=receipt['preview_sha256'])
"""
        for phase in ("before", "after"):
            self.save()
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(self.storage),
                    str(self.workspace),
                    str(self.other),
                    phase,
                ],
                capture_output=True,
                timeout=15,
            )
            self.assertEqual(child.returncode, 73, child.stderr)
            expected = self.target if phase == "before" else self.other
            self.assertEqual(
                self.registry.read().mappings[0].target.path, str(expected)
            )
            self.assertEqual(
                MemoryMappingResolver(self.storage).resolve(self.workspace),
                DirectorySelection.inspect(expected),
            )
        self.assertTrue(tuple(self.storage.glob(".memory-mappings-*.tmp")))

    def test_aliases_are_pinned_and_mapping_is_exact_not_inherited(self) -> None:
        alias = self.base / "alias"
        alias.symlink_to(self.target, target_is_directory=True)
        self.save(target=alias)
        alias.unlink()
        alias.symlink_to(self.other, target_is_directory=True)
        resolver = MemoryMappingResolver(self.storage)
        self.assertEqual(
            resolver.resolve(self.workspace), DirectorySelection.inspect(self.target)
        )
        nested = self.workspace / "nested"
        nested.mkdir()
        self.assertIsNone(resolver.resolve(nested))
        self.assertIsNone(resolver.resolve(self.other))

    def test_directory_replacement_fails_until_reviewed_again(self) -> None:
        for replaced in (self.workspace, self.target):
            with self.subTest(path=replaced):
                self.save()
                moved = replaced.with_name(replaced.name + "-old")
                replaced.rename(moved)
                replaced.mkdir()
                with self.assertRaises(DirectorySelectionError):
                    MemoryMappingResolver(self.storage).resolve(self.workspace)
                self.save()
                self.assertIsNotNone(
                    MemoryMappingResolver(self.storage).resolve(self.workspace)
                )

    def test_deleted_workspace_mapping_can_be_removed_without_target_access(
        self,
    ) -> None:
        self.save()
        self.workspace.rmdir()
        self.target.rmdir()
        receipt = self.registry.change(self.workspace, None)
        self.registry.change(
            self.workspace, None, expected_sha256=str(receipt["preview_sha256"])
        )
        self.assertEqual(self.registry.read().mappings, ())
        with self.assertRaises(ValueError):
            self.registry.change(self.workspace, None)
        with self.assertRaises(ValueError):
            self.registry.change(Path("relative"), None)

    def test_owner_canonical_encoding_and_bounds_are_enforced(self) -> None:
        self.save()
        path = self.storage / REGISTRY_NAME
        original = path.read_bytes()
        data = json.loads(original)
        bad_owner = MemoryMappingRegistry.model_validate_json(
            json.dumps(dict(data, owner_uid=os.getuid() + 1))
        )
        for payload in (
            canonical_bytes(bad_owner),
            original + b"\n",
            original.replace(b'"revision":1', b'"revision":1,"revision":1'),
            b"x" * (REGISTRY_BYTES + 1),
        ):
            with self.subTest(payload_length=len(payload)):
                path.write_bytes(payload)
                with self.assertRaises(ValueError):
                    self.registry.read()
        path.write_bytes(original)
        mapping = self.registry.read().mappings[0]
        with self.assertRaises(ValueError):
            MemoryMappingRegistry(owner_uid=os.getuid(), mappings=(mapping, mapping))
        mappings = tuple(
            SavedMemoryMapping(
                workspace=MappedDirectory(path=f"/work/{i:03}", device=1, inode=i),
                target=mapping.target,
            )
            for i in range(MAX_MAPPINGS + 1)
        )
        with self.assertRaises(ValueError):
            MemoryMappingRegistry(owner_uid=os.getuid(), mappings=mappings)

    def test_unsafe_registry_types_and_permissions_fail_closed(self) -> None:
        self.save()
        path = self.storage / REGISTRY_NAME
        backup = self.storage / "backup"
        path.rename(backup)
        for kind in ("symlink", "hardlink", "fifo", "public"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    path.symlink_to(backup)
                elif kind == "hardlink":
                    os.link(backup, path)
                elif kind == "fifo":
                    os.mkfifo(path, 0o600)
                else:
                    path.write_bytes(backup.read_bytes())
                    path.chmod(0o644)
                with self.assertRaises((OSError, ValueError)):
                    self.registry.read()
                path.unlink()
        backup.rename(path)
        self.storage.chmod(0o755)
        with self.assertRaises(ValueError):
            self.registry.read()
        self.storage.chmod(0o700)

    def test_lock_contention_fails_without_mutation(self) -> None:
        self.save()
        before = (self.storage / REGISTRY_NAME).read_bytes()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.registry.read()
            with self.assertRaises(BlockingIOError):
                self.registry.change(self.workspace, self.other)
        self.assertEqual((self.storage / REGISTRY_NAME).read_bytes(), before)

    def test_launch_snapshot_retains_reviewed_mapping_after_registry_changes(
        self,
    ) -> None:
        self.save()
        resolver = MemoryMappingResolver(self.storage)
        with create_pipe_input() as pipe:
            picker = DirectoryPicker(
                self.workspace,
                input=pipe,
                output=DummyOutput(),
                memory_resolver=resolver.resolve,
            )
            picker.preview()
            self.assertIn(str(self.target), picker.details())
            self.assertIn("Mapped project memory identity", picker.details())
            self.save(target=self.other)
            self.assertEqual(resolver.resolve(self.workspace), picker.memory_selection)
            self.assertEqual(
                MemoryMappingResolver(self.storage).resolve(self.workspace),
                DirectorySelection.inspect(self.other),
            )

    def test_both_backends_save_mapping_and_resume_ignores_corrupt_registry(
        self,
    ) -> None:
        self.save()
        MemoryStore(self.storage, self.target).change(
            "project", "set", text="Shared decisions"
        )
        registry_path = self.storage / REGISTRY_NAME
        original = registry_path.read_bytes()
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend):
                registry_path.write_bytes(original)
                sessions = self.base / backend
                args = [
                    "-C",
                    str(self.workspace),
                    "--memory-storage",
                    str(self.storage),
                    "--storage",
                    str(sessions),
                    "--storage-backend",
                    backend,
                    "--json",
                ]
                launched = self.launch(args)
                self.assertEqual(launched.returncode, 0, launched.stderr)
                opened = next(
                    json.loads(line)
                    for line in launched.stdout.splitlines()
                    if json.loads(line)["type"] == "conversation.opened"
                )
                self.assertEqual(opened["memory_workspace"], str(self.target))
                sid = str(opened["session_id"])
                store_type = (
                    SQLiteConversationStore
                    if backend == "sqlite"
                    else ConversationStore
                )
                with store_type(sessions, sid, self.workspace, create=False) as store:
                    state = store.load()
                self.assertEqual(state.memory_project_mapping, str(self.target))
                self.assertEqual(state.workspace, str(self.workspace))
                registry_path.write_bytes(b"corrupt")
                resumed = self.launch(["resume", sid, *args])
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                rejected = self.launch(args)
                self.assertEqual(rejected.returncode, 2)
                bypassed = self.launch(["--memory-project-local", *args])
                self.assertEqual(bypassed.returncode, 0, bypassed.stderr)
                explicit = self.launch(
                    ["chat", "--memory-project-map", str(self.other), *args]
                )
                self.assertEqual(explicit.returncode, 0, explicit.stderr)
                ancestor = self.launch(
                    ["chat", "--memory-project-root", str(self.base), *args]
                )
                self.assertEqual(ancestor.returncode, 0, ancestor.stderr)

    def test_workspace_alias_is_pinned_before_memory_load(self) -> None:
        self.save()
        MemoryStore(self.storage, self.target).change(
            "project", "set", text="Shared decisions"
        )
        alias = self.base / "workspace-alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        sessions = self.base / "sessions"
        args = parser().parse_args(
            [
                "chat",
                "-C",
                str(alias),
                "--memory-storage",
                str(self.storage),
                "--storage",
                str(sessions),
                "--json",
            ]
        )
        load = MemoryStore.load

        def retarget(store: MemoryStore):
            alias.unlink()
            alias.symlink_to(self.other, target_is_directory=True)
            return load(store)

        output = io.StringIO()
        with (
            patch.object(MemoryStore, "load", retarget),
            patch("mos_eisley.conversation_cli._run_terminal", new_callable=AsyncMock),
            redirect_stdout(output),
        ):
            self.assertEqual(run_command(args), 0)
        opened = next(
            json.loads(line)
            for line in output.getvalue().splitlines()
            if json.loads(line)["type"] == "conversation.opened"
        )
        with ConversationStore(
            sessions, opened["session_id"], self.workspace, create=False
        ) as store:
            state = store.load()
        self.assertEqual(state.workspace, str(self.workspace))
        self.assertEqual(state.memory_project_mapping, str(self.target))
        self.assertEqual(alias.resolve(), self.other)

    def test_no_memory_bypasses_registry_but_preserves_explicit_mapping(
        self,
    ) -> None:
        sessions = self.base / "sessions"
        args = [
            "chat",
            "-C",
            str(self.workspace),
            "--memory-storage",
            str(self.storage),
            "--storage",
            str(sessions),
            "--json",
            "--no-memory",
        ]
        result = self.launch(args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.storage.exists())
        self.save()
        before = (self.storage / REGISTRY_NAME).read_bytes()
        result = self.launch(args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(str(self.target), result.stdout)
        explicit = self.launch([*args, "--memory-project-map", str(self.target)])
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertIn(str(self.target), explicit.stdout)
        self.assertEqual((self.storage / REGISTRY_NAME).read_bytes(), before)
        self.assertEqual(
            {p.name for p in self.storage.iterdir()}, {REGISTRY_NAME, "memory.lock"}
        )

    def test_cli_review_apply_remove_and_argument_guards(self) -> None:
        base = [
            "memory-project-mapping",
            "set",
            "-C",
            str(self.workspace),
            "--target",
            str(self.target),
            "--memory-storage",
            str(self.storage),
            "--json",
        ]
        preview = self.launch(base)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        receipt = json.loads(preview.stdout)
        applied = self.launch(
            [*base, "--apply", "--expected-sha256", receipt["preview_sha256"]]
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        shown = self.launch(
            [
                "memory-project-mapping",
                "show",
                "--memory-storage",
                str(self.storage),
                "--json",
            ]
        )
        self.assertEqual(json.loads(shown.stdout)["registry"]["revision"], 1)
        self.assertEqual(self.launch([*base, "--apply"]).returncode, 2)
        self.assertEqual(
            self.launch(
                [
                    "chat",
                    "--memory-project-local",
                    "--memory-project-map",
                    str(self.target),
                ]
            ).returncode,
            2,
        )
        remove = [
            "memory-project-mapping",
            "remove",
            "-C",
            str(self.workspace),
            "--memory-storage",
            str(self.storage),
            "--json",
        ]
        receipt = json.loads(self.launch(remove).stdout)
        self.assertEqual(
            self.launch(
                [*remove, "--apply", "--expected-sha256", receipt["preview_sha256"]]
            ).returncode,
            0,
        )
        self.assertEqual(self.registry.read().mappings, ())

    def test_generators_use_saved_mapping_and_local_override(self) -> None:
        self.save()
        MemoryStore(self.storage, self.target).change(
            "project", "set", text="Shared decisions"
        )
        for command in ("conversation-demo", "conversation-review-demo"):
            output = self.base / (command + ".json")
            args = [
                command,
                "--output",
                str(output),
                "-C",
                str(self.workspace),
                "--memory-storage",
                str(self.storage),
            ]
            if command == "conversation-review-demo":
                args += ["--review-output", str(self.base / "review.json")]
            result = self.launch(args)
            self.assertEqual(result.returncode, 0, result.stderr)
            mapped = output.read_bytes()
            output.unlink()
            if command == "conversation-review-demo":
                (self.base / "review.json").unlink()
            result = self.launch([*args, "--memory-project-local"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual(mapped, output.read_bytes())

    def test_switch_checks_destination_mapping_and_handoff_retains_preview(
        self,
    ) -> None:
        self.save(self.other, self.target)
        resolver = MemoryMappingResolver(self.storage)
        controller = ConversationController(
            ConversationController.fresh(self.workspace, demo_cassette()),
            demo_cassette(),
            lambda state: None,
        )
        with create_pipe_input() as pipe:
            ui = ConversationTUI(
                controller,
                allow_directory_switch=True,
                memory_resolver=resolver.resolve,
                input=pipe,
                output=DummyOutput(),
            )
            self.assertTrue(
                asyncio.run(ui.switch_directory("/directory switch " + str(self.other)))
            )
            args = fresh_directory_arguments(
                argparse.Namespace(
                    saved_mapping_resolver=resolver,
                    memory_project_mapping=self.workspace,
                ),
                DirectorySelection.inspect(self.other),
            )
            self.assertIs(args.saved_mapping_resolver, resolver)
            self.assertIsNone(args.memory_project_mapping)
            self.assertEqual(
                resolver.resolve(args.workspace),
                DirectorySelection.inspect(self.target),
            )
        self.target.rename(self.base / "old-target")
        self.target.mkdir()
        with create_pipe_input() as pipe:
            ui = ConversationTUI(
                controller,
                allow_directory_switch=True,
                memory_resolver=MemoryMappingResolver(self.storage).resolve,
                input=pipe,
                output=DummyOutput(),
            )
            self.assertFalse(
                asyncio.run(ui.switch_directory("/directory switch " + str(self.other)))
            )
            self.assertIsNone(ui.directory_target)
        self.assertEqual(controller.state.entries, ())
