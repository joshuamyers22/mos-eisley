"""Whole-registry import policy, ownership, stale review and durability tests."""

import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_directory import DirectorySelectionError
from mos_eisley.conversation_memory_registry import (
    MAX_MAPPINGS,
    REGISTRY_BYTES,
    REGISTRY_NAME,
    MemoryMappingStore,
    mapping_backup_name,
)
from mos_eisley.conversation_memory_registry_import import (
    ConflictPolicy,
    ImportMode,
    MappingImportError,
    MemoryMappingImporter,
    read_import_manifest,
)


def data(value: object) -> Any:
    return json.loads(json.dumps(value))


class MappingImportTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "workspace"
        self.target = self.base / "target"
        self.other = self.base / "other"
        self.input_dir = self.base / "input"
        for path in (self.workspace, self.target, self.other, self.input_dir):
            path.mkdir()
        self.manifest = self.input_dir / "mappings.json"
        self.storage = self.base / "memory"
        self.current = self.storage / REGISTRY_NAME
        self.store = MemoryMappingStore(self.storage)
        self.importer = MemoryMappingImporter(self.storage)

    def write_manifest(self, mappings: list[tuple[Path, Path]] | None = None) -> bytes:
        if mappings is None:
            mappings = [(self.workspace, self.target)]
        payload = json.dumps(
            {
                "schema_version": 1,
                "owner_uid": os.getuid(),
                "mappings": [
                    {"workspace": str(w), "target": str(t)} for w, t in mappings
                ],
            },
            indent=2,
        ).encode()
        self.manifest.write_bytes(payload)
        self.manifest.chmod(0o600)
        return payload

    def save(self, workspace: Path | None = None, target: Path | None = None) -> None:
        workspace, target = workspace or self.workspace, target or self.other
        preview = self.store.change(workspace, target)
        self.store.change(
            workspace, target, expected_sha256=str(preview["preview_sha256"])
        )

    def test_bootstrap_review_and_invalid_hash_leave_storage_absent(self) -> None:
        payload = self.write_manifest()
        preview = self.importer.import_mappings(self.manifest)
        self.assertFalse(self.storage.exists())
        self.assertTrue(preview["can_apply"])
        self.assertEqual(data(preview)["after"]["revision"], 1)
        self.assertEqual(
            base64.b64decode(data(preview)["input"]["raw_bytes_base64"]), payload
        )
        with self.assertRaises(ValueError):
            self.importer.import_mappings(self.manifest, expected_sha256="0" * 64)
        self.assertFalse(self.storage.exists())
        applied = self.importer.import_mappings(
            self.manifest, expected_sha256=str(preview["preview_sha256"])
        )
        self.assertTrue(applied["published"])
        self.assertTrue(applied["synced"])
        self.assertFalse(applied["backup_synced"])
        self.assertEqual(self.store.read().mappings[0].target.path, str(self.target))
        self.assertEqual(self.current.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.storage.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.manifest.read_bytes(), payload)

    def test_default_conflicts_are_reviewable_and_apply_is_blocked(self) -> None:
        self.save()
        self.write_manifest([(self.workspace, self.target), (self.other, self.target)])
        before = self.current.read_bytes()
        preview = self.importer.import_mappings(self.manifest)
        self.assertEqual(preview["status"], "conflicts")
        self.assertFalse(preview["can_apply"])
        self.assertIsNone(preview["after"])
        self.assertEqual(preview["conflict_count"], 1)
        self.assertEqual(
            {r["disposition"] for r in data(preview)["changes"]}, {"conflict", "added"}
        )
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest, expected_sha256=str(preview["preview_sha256"])
            )
        self.assertEqual(self.current.read_bytes(), before)
        self.assertFalse(tuple(self.storage.glob("mapping-backup-*")))

    def test_merge_keep_replace_and_unchanged_preserve_unselected_entries(self) -> None:
        self.save()
        self.save(self.target, self.other)
        self.write_manifest([(self.workspace, self.target), (self.other, self.target)])
        for policy in ("keep", "replace"):
            before = self.current.read_bytes()
            review = self.importer.import_mappings(self.manifest, on_conflict=policy)
            receipt = self.importer.import_mappings(
                self.manifest,
                on_conflict=policy,
                expected_sha256=str(review["preview_sha256"]),
            )
            self.assertTrue(receipt["backup_synced"])
            self.assertEqual(
                (self.storage / mapping_backup_name(before)).read_bytes(), before
            )
            actual = {
                r.workspace.path: r.target.path for r in self.store.read().mappings
            }
            self.assertEqual(
                actual[str(self.workspace)],
                str(self.other if policy == "keep" else self.target),
            )
            self.assertEqual(actual[str(self.other)], str(self.target))
            self.assertEqual(actual[str(self.target)], str(self.other))
        review = self.importer.import_mappings(self.manifest)
        self.assertEqual(
            {r["disposition"] for r in data(review)["changes"]}, {"unchanged"}
        )
        self.assertTrue(review["can_apply"])

    def test_full_replace_and_explicit_empty_import_show_removals(self) -> None:
        self.save()
        self.write_manifest([(self.other, self.target)])
        review = self.importer.import_mappings(self.manifest, mode="replace")
        self.assertEqual(
            {r["disposition"] for r in data(review)["changes"]}, {"added", "removed"}
        )
        self.importer.import_mappings(
            self.manifest, mode="replace", expected_sha256=str(review["preview_sha256"])
        )
        self.assertEqual(len(self.store.read().mappings), 1)
        self.assertEqual(self.store.read().mappings[0].workspace.path, str(self.other))
        self.write_manifest([])
        review = self.importer.import_mappings(self.manifest, mode="replace")
        self.importer.import_mappings(
            self.manifest, mode="replace", expected_sha256=str(review["preview_sha256"])
        )
        self.assertEqual(self.store.read().mappings, ())
        self.assertTrue(self.current.exists())

    def test_duplicate_keys_unknown_fields_owners_versions_and_paths_rejected(
        self,
    ) -> None:
        payload = self.write_manifest()
        obj = json.loads(payload)
        bad = [
            payload.replace(
                b'"schema_version": 1', b'"schema_version": 1,"schema_version": 1'
            ),
            payload.replace(b'"workspace":', b'"workspace": "ignored", "workspace":'),
            json.dumps(dict(obj, owner_uid=os.getuid() + 1)).encode(),
            json.dumps(dict(obj, owner_uid=True)).encode(),
            json.dumps(dict(obj, schema_version=True)).encode(),
            json.dumps(dict(obj, schema_version=2)).encode(),
            json.dumps(dict(obj, unknown="value")).encode(),
            b"null",
            b"[" * 1100 + b"]" * 1100,
        ]
        for path in ("relative", "~/project", "/tmp/line\nbreak", "/" + "x" * 4096):
            invalid = dict(
                obj, mappings=[{"workspace": path, "target": str(self.target)}]
            )
            bad.append(json.dumps(invalid).encode())
        for value in bad:
            self.manifest.write_bytes(value)
            with self.assertRaises(ValueError):
                self.importer.import_mappings(self.manifest)
            self.assertFalse(self.storage.exists())

    def test_aliases_resolve_but_duplicate_workspaces_and_retargets_fail(self) -> None:
        alias = self.base / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        self.write_manifest([(self.workspace, self.target), (alias, self.other)])
        with self.assertRaises(ValueError):
            self.importer.import_mappings(self.manifest)
        self.write_manifest([(alias, self.target)])
        review = self.importer.import_mappings(self.manifest)
        self.assertEqual(
            data(review)["after"]["mappings"][0]["workspace"]["path"],
            str(self.workspace),
        )
        alias.unlink()
        alias.symlink_to(self.other, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest, expected_sha256=str(review["preview_sha256"])
            )
        self.assertFalse(self.storage.exists())

    def test_stale_input_metadata_parent_and_directory_identity_block_apply(
        self,
    ) -> None:
        self.write_manifest()
        review = self.importer.import_mappings(self.manifest)
        os.utime(self.manifest, ns=(1, 1))
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest, expected_sha256=str(review["preview_sha256"])
            )
        review = self.importer.import_mappings(self.manifest)
        old = self.input_dir.with_name("old-input")
        self.input_dir.rename(old)
        self.input_dir.mkdir()
        (old / self.manifest.name).rename(self.manifest)
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest, expected_sha256=str(review["preview_sha256"])
            )
        review = self.importer.import_mappings(self.manifest)
        self.target.rename(self.base / "old-target")
        self.target.mkdir()
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest, expected_sha256=str(review["preview_sha256"])
            )
        self.assertFalse(self.storage.exists())

    def test_stale_registry_policy_and_storage_lock_reject_review(self) -> None:
        self.save()
        self.write_manifest()
        review = self.importer.import_mappings(self.manifest, on_conflict="replace")
        choices: tuple[tuple[ImportMode, ConflictPolicy], ...] = (
            ("replace", "error"),
            ("merge", "keep"),
        )
        for mode, policy in choices:
            with self.assertRaises(ValueError):
                self.importer.import_mappings(
                    self.manifest,
                    expected_sha256=str(review["preview_sha256"]),
                    mode=mode,
                    on_conflict=policy,
                )
        self.save(self.target, self.other)
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest,
                on_conflict="replace",
                expected_sha256=str(review["preview_sha256"]),
            )
        review = self.importer.import_mappings(self.manifest, on_conflict="replace")
        lock = self.storage / "memory.lock"
        lock.rename(self.storage / "old.lock")
        lock.touch(mode=0o600)
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest,
                on_conflict="replace",
                expected_sha256=str(review["preview_sha256"]),
            )

    def test_unsafe_source_and_corrupt_destination_are_never_overwritten(self) -> None:
        payload = self.write_manifest()
        self.save()
        before = self.current.read_bytes()
        original = self.input_dir / "original"
        self.manifest.rename(original)
        for kind in ("symlink", "hardlink", "fifo", "directory", "public"):
            if kind == "symlink":
                self.manifest.symlink_to(original)
            elif kind == "hardlink":
                os.link(original, self.manifest)
            elif kind == "fifo":
                os.mkfifo(self.manifest, 0o600)
            elif kind == "directory":
                self.manifest.mkdir()
            else:
                self.manifest.write_bytes(payload)
                self.manifest.chmod(0o644)
            with self.assertRaises((OSError, ValueError)):
                self.importer.import_mappings(self.manifest)
            self.assertEqual(self.current.read_bytes(), before)
            if kind == "directory":
                self.manifest.rmdir()
            else:
                self.manifest.unlink()
        original.rename(self.manifest)
        self.current.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.importer.import_mappings(self.manifest, mode="replace")
        self.assertEqual(self.current.read_bytes(), b"corrupt")

    def test_real_input_count_byte_and_combined_registry_limits(self) -> None:
        original = self.write_manifest()
        self.manifest.write_bytes(original + b" " * (REGISTRY_BYTES - len(original)))
        self.assertTrue(self.importer.import_mappings(self.manifest)["can_apply"])
        self.manifest.write_bytes(self.manifest.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.importer.import_mappings(self.manifest)
        self.write_manifest([(self.workspace, self.target)] * (MAX_MAPPINGS + 1))
        with self.assertRaises(ValueError):
            self.importer.import_mappings(self.manifest)
        directories: list[tuple[Path, Path]] = []
        for i in range(MAX_MAPPINGS):
            path = self.base / f"work-{i:03}"
            path.mkdir()
            directories.append((path, self.target))
        self.write_manifest(directories)
        preview = self.importer.import_mappings(self.manifest)
        self.importer.import_mappings(
            self.manifest, expected_sha256=str(preview["preview_sha256"])
        )
        self.assertEqual(len(self.store.read().mappings), MAX_MAPPINGS)
        self.write_manifest()
        before = self.current.read_bytes()
        with self.assertRaises(ValueError):
            self.importer.import_mappings(self.manifest)
        self.assertEqual(self.current.read_bytes(), before)

    def test_late_input_or_directory_mutation_preserves_current(self) -> None:
        self.save()
        original = self.write_manifest()
        fsync = os.fsync
        for kind in ("input", "directory"):
            self.manifest.write_bytes(original)
            preview = self.importer.import_mappings(
                self.manifest, on_conflict="replace"
            )
            before = self.current.read_bytes()
            fired = False

            def mutate(fd: int, kind: str = kind) -> None:
                nonlocal fired
                fsync(fd)
                if not fired:
                    fired = True
                    if kind == "input":
                        self.manifest.write_bytes(original + b"\n")
                    else:
                        self.target.rename(self.base / "moved-target")
                        self.target.mkdir()

            with (
                patch(
                    "mos_eisley.conversation_memory_registry.os.fsync",
                    side_effect=mutate,
                ),
                self.assertRaises(MappingImportError) as caught,
            ):
                self.importer.import_mappings(
                    self.manifest,
                    on_conflict="replace",
                    expected_sha256=str(preview["preview_sha256"]),
                )
            self.assertFalse(caught.exception.receipt["published"])
            self.assertEqual(self.current.read_bytes(), before)
        with self.assertRaises(DirectorySelectionError):
            self.target.rmdir()
            self.importer.import_mappings(self.manifest, on_conflict="replace")

    def test_post_publication_flush_failure_returns_progress_and_stales_review(
        self,
    ) -> None:
        self.save()
        self.write_manifest()
        preview = self.importer.import_mappings(self.manifest, on_conflict="replace")
        fsync = os.fsync

        def fail(fd: int) -> None:
            if (
                stat.S_ISDIR(os.fstat(fd).st_mode)
                and json.loads(self.current.read_bytes())["revision"] == 2
            ):
                raise OSError("interrupted directory flush")
            fsync(fd)

        with (
            patch("mos_eisley.conversation_memory_registry.os.fsync", side_effect=fail),
            self.assertRaises(MappingImportError) as caught,
        ):
            self.importer.import_mappings(
                self.manifest,
                on_conflict="replace",
                expected_sha256=str(preview["preview_sha256"]),
            )
        self.assertTrue(caught.exception.receipt["published"])
        self.assertTrue(caught.exception.receipt["backup_synced"])
        self.assertFalse(caught.exception.receipt["synced"])
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest,
                on_conflict="replace",
                expected_sha256=str(preview["preview_sha256"]),
            )

    def test_process_death_before_after_publish_preserves_complete_registries(
        self,
    ) -> None:
        script = """
import os,sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_registry_import import MemoryMappingImporter
store=MemoryMappingImporter(Path(sys.argv[1]))
source=Path(sys.argv[2])
preview=store.import_mappings(source,on_conflict="replace")
replace=os.replace
def die(*args,**kwargs):
    if sys.argv[3]=="after":
        replace(*args,**kwargs)
    os._exit(73)
with patch("os.replace",side_effect=die):
    store.import_mappings(source,on_conflict="replace",
                          expected_sha256=preview["preview_sha256"])
"""
        for phase in ("before", "after"):
            self.save()
            self.write_manifest()
            before = self.current.read_bytes()
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(self.storage),
                    str(self.manifest),
                    phase,
                ],
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(child.returncode, 73, child.stderr)
            self.assertEqual(
                (self.storage / mapping_backup_name(before)).read_bytes(), before
            )
            self.assertEqual(
                self.store.read().mappings[0].target.path,
                str(self.target if phase == "after" else self.other),
            )
            if phase == "before":
                self.assertTrue(tuple(self.storage.glob(".memory-mappings-*.tmp")))

    def test_input_parent_alias_retarget_during_read_is_rejected(self) -> None:
        self.write_manifest()
        alias = self.base / "input-alias"
        alias.symlink_to(self.input_dir, target_is_directory=True)
        verify = read_import_manifest
        original_fstat = os.fstat
        fired = False

        def retarget(fd: int):
            nonlocal fired
            info = original_fstat(fd)
            if stat.S_ISREG(info.st_mode) and not fired:
                fired = True
                alias.unlink()
                alias.symlink_to(self.other, target_is_directory=True)
            return info

        with patch("os.fstat", side_effect=retarget), self.assertRaises(ValueError):
            verify(alias / self.manifest.name)

    def test_cli_conflicts_apply_and_option_scope(self) -> None:
        self.save()
        self.write_manifest()

        def cli(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "memory-project-mapping",
                    *args,
                    "--memory-storage",
                    str(self.storage),
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )

        base = ["import", "--input", str(self.manifest)]
        preview = cli(*base)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(json.loads(preview.stdout)["status"], "conflicts")
        replacement = cli(*base, "--on-conflict", "replace")
        self.assertEqual(replacement.returncode, 0, replacement.stderr)
        receipt = json.loads(replacement.stdout)
        applied = cli(
            *base,
            "--on-conflict",
            "replace",
            "--apply",
            "--expected-sha256",
            receipt["preview_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(json.loads(applied.stdout)["status"], "completed")
        for args in (
            ("import",),
            (*base, "--apply"),
            (*base, "--mode", "replace", "--on-conflict", "keep"),
            (*base, "-C", str(self.workspace)),
            ("history", "--input", str(self.manifest)),
            ("show", "--mode", "merge"),
            ("set", "--on-conflict", "keep"),
        ):
            self.assertEqual(cli(*args).returncode, 2, args)

    def test_retained_historical_mappings_do_not_require_old_directories(self) -> None:
        self.save()
        self.other.rmdir()
        self.write_manifest([(self.target, self.workspace)])
        review = self.importer.import_mappings(self.manifest)
        self.importer.import_mappings(
            self.manifest, expected_sha256=str(review["preview_sha256"])
        )
        entries = {m.workspace.path: m.target.path for m in self.store.read().mappings}
        self.assertEqual(entries[str(self.workspace)], str(self.other))
        self.assertEqual(entries[str(self.target)], str(self.workspace))

    def test_source_replacement_and_destination_root_change_invalidate_review(
        self,
    ) -> None:
        self.save()
        payload = self.write_manifest()
        review = self.importer.import_mappings(self.manifest, on_conflict="replace")
        self.manifest.rename(self.input_dir / "old-manifest")
        self.manifest.write_bytes(payload)
        self.manifest.chmod(0o600)
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest,
                on_conflict="replace",
                expected_sha256=str(review["preview_sha256"]),
            )
        review = self.importer.import_mappings(self.manifest, on_conflict="replace")
        moved = self.base / "moved-storage"
        self.storage.rename(moved)
        self.storage.mkdir(mode=0o700)
        for path in moved.iterdir():
            path.rename(self.storage / path.name)
        with self.assertRaises(ValueError):
            self.importer.import_mappings(
                self.manifest,
                on_conflict="replace",
                expected_sha256=str(review["preview_sha256"]),
            )

    def test_source_filesystem_owner_is_required(self) -> None:
        self.write_manifest()
        source_inode = self.manifest.stat().st_ino
        fstat = os.fstat

        def foreign(fd: int) -> os.stat_result:
            info = fstat(fd)
            if info.st_ino == source_inode and stat.S_ISREG(info.st_mode):
                values = list(info)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return info

        with patch("os.fstat", side_effect=foreign), self.assertRaises(ValueError):
            self.importer.import_mappings(self.manifest)
        self.assertFalse(self.storage.exists())

    def test_both_backend_resumes_keep_identity_after_import(self) -> None:
        from mos_eisley.conversation_memory import MemoryStore

        self.write_manifest()
        MemoryStore(self.storage, self.target).change(
            "project", "set", text="Target memory"
        )
        MemoryStore(self.storage, self.workspace).change(
            "user", "set", text="User preferences"
        )
        for backend in ("snapshot", "sqlite"):
            self.save()
            documents = {
                p.name: p.read_bytes()
                for p in self.storage.glob("*.json")
                if p.name != REGISTRY_NAME and not p.name.startswith("mapping-backup-")
            }
            sessions = self.base / backend

            def launch(
                command: list[str], backend: str = backend, sessions: Path = sessions
            ):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        *command,
                        "-C",
                        str(self.workspace),
                        "--memory-storage",
                        str(self.storage),
                        "--storage",
                        str(sessions),
                        "--storage-backend",
                        backend,
                        "--json",
                    ],
                    input="/quit\n",
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return next(
                    json.loads(line)
                    for line in result.stdout.splitlines()
                    if json.loads(line)["type"] == "conversation.opened"
                )

            opened = launch(["chat"])
            self.assertEqual(opened["memory_workspace"], str(self.other))
            review = self.importer.import_mappings(self.manifest, on_conflict="replace")
            self.importer.import_mappings(
                self.manifest,
                on_conflict="replace",
                expected_sha256=str(review["preview_sha256"]),
            )
            resumed = launch(["resume", opened["session_id"]])
            self.assertEqual(resumed["memory_workspace"], str(self.other))
            self.assertEqual(launch(["chat"])["memory_workspace"], str(self.target))
            for name, payload in documents.items():
                self.assertEqual((self.storage / name).read_bytes(), payload)
