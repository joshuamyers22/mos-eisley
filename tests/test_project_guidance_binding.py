import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import patch

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_binding import (
    BindingAction,
    GuidanceBindingStore,
    ProjectGuidanceBindings,
    project_name,
    snapshot_name,
)
from mos_eisley.project_guidance_storage import GUIDANCE_FILE_BYTES, publish_file


class BindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "private"
        self.store = GuidanceBindingStore(self.storage)
        self.descriptor = self.base / "guidance.json"
        self.markdown = self.base / "guidance.md"
        self.source()

    def source(
        self, text: str = "Use explicit inputs.", template: str = "engineering"
    ) -> None:
        self.markdown.write_text(text + "\n", encoding="utf-8")
        self.descriptor.write_text(
            json.dumps(
                {
                    "template_id": template,
                    "version": "1.0.0",
                    "source_revision": "local-v1",
                    "content_sha256": digest(self.markdown.read_bytes()),
                    "rules": [
                        {
                            "id": "ENG001",
                            "text": text,
                            "applies_when": "Writing code",
                            "rationale": "Make intent visible",
                            "checks": ["Review inputs"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def change(
        self,
        action: BindingAction = "attach",
        *,
        token: str | None = None,
        template: str = "engineering",
        workspace: Path | None = None,
    ) -> dict[str, object]:
        return self.store.change(
            self.workspace if workspace is None else workspace,
            action,
            template,
            descriptor_path=None if action == "detach" else self.descriptor,
            markdown_path=None if action == "detach" else self.markdown,
            expected_sha256=token,
        )

    def apply(
        self, action: BindingAction = "attach", *, template: str = "engineering"
    ) -> dict[str, object]:
        preview = self.change(action, template=template)
        return self.change(
            action, token=cast(str, preview["preview_sha256"]), template=template
        )

    def record_path(self) -> Path:
        return self.storage / project_name(MappedDirectory.inspect(self.workspace))

    def snapshot_hash(self) -> str:
        record = ProjectGuidanceBindings.model_validate_json(
            self.record_path().read_bytes()
        )
        return record.templates[0].snapshot_sha256

    def test_preview_show_are_read_only_and_apply_creates_private_pinned_binding(
        self,
    ) -> None:
        preview = self.change()
        self.assertIn("Use explicit inputs", cast(str, preview["diff"]))
        self.assertFalse(preview["applied"])
        self.assertFalse(self.storage.exists())
        self.assertEqual(self.store.show(self.workspace)["snapshots"], [])
        self.assertFalse(self.storage.exists())
        result = self.change(token=cast(str, preview["preview_sha256"]))
        self.assertTrue(result["applied"])
        self.assertEqual(result["preview_sha256"], preview["preview_sha256"])
        self.assertEqual(self.storage.stat().st_mode & 0o777, 0o700)
        self.assertTrue(
            all(path.stat().st_mode & 0o777 == 0o600 for path in self.storage.iterdir())
        )
        self.assertEqual(
            len(cast(list[object], self.store.show(self.workspace)["snapshots"])), 1
        )
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_update_and_detach_retain_old_snapshot_without_loading_sources(
        self,
    ) -> None:
        self.apply()
        old_hash = self.snapshot_hash()
        old_bytes = (self.storage / snapshot_name(old_hash)).read_bytes()
        self.source("Keep updates explicit.")
        update = self.change("update")
        self.assertIn("Use explicit inputs", cast(str, update["diff"]))
        self.assertIn("Keep updates explicit", cast(str, update["diff"]))
        self.change("update", token=cast(str, update["preview_sha256"]))
        new_hash = self.snapshot_hash()
        self.assertNotEqual(old_hash, new_hash)
        self.descriptor.unlink()
        self.markdown.unlink()
        self.assertEqual(
            len(cast(list[object], self.store.show(self.workspace)["snapshots"])), 1
        )
        self.apply("detach")
        self.assertEqual(self.store.show(self.workspace)["snapshots"], [])
        for sha256 in (old_hash, new_hash):
            historical = self.store.show(self.workspace, snapshot_sha256=sha256)
            self.assertTrue(historical["historical_snapshot"])
        self.assertEqual(
            (self.storage / snapshot_name(old_hash)).read_bytes(), old_bytes
        )
        record = ProjectGuidanceBindings.model_validate_json(
            self.record_path().read_bytes()
        )
        self.assertEqual(record.revision, 3)
        self.assertFalse(record.context_materialized)

    def test_two_projects_nested_project_and_other_user_are_isolated(self) -> None:
        self.apply()
        original = self.record_path().read_bytes()
        second = self.base / "second"
        second.mkdir()
        nested = self.workspace / "nested"
        nested.mkdir()
        for workspace in (second, nested):
            self.assertEqual(self.store.show(workspace)["snapshots"], [])
            with self.assertRaises(ValueError):
                self.store.show(workspace, snapshot_sha256=self.snapshot_hash())
        preview = self.change(workspace=second)
        self.change(workspace=second, token=cast(str, preview["preview_sha256"]))
        detach = self.change("detach", workspace=second)
        self.change(
            "detach", workspace=second, token=cast(str, detach["preview_sha256"])
        )
        self.assertEqual(self.record_path().read_bytes(), original)
        with (
            patch("os.getuid", return_value=os.getuid() + 1),
            self.assertRaises(ValueError),
        ):
            self.store.show(self.workspace)

    def test_changed_source_or_changed_storage_rejects_old_review(self) -> None:
        preview = self.change()
        self.source("Use a different input.")
        with self.assertRaises(ValueError):
            self.change(token=cast(str, preview["preview_sha256"]))
        self.assertFalse(self.storage.exists())
        self.apply()
        self.source("Another revision.")
        preview = self.change("update")
        self.apply("update")
        with self.assertRaises(ValueError):
            self.change("update", token=cast(str, preview["preview_sha256"]))

    def test_concurrent_creation_and_detach_reattach_invalidate_reviews(self) -> None:
        preview = self.change()
        self.apply()
        with self.assertRaises(ValueError):
            self.change(token=cast(str, preview["preview_sha256"]))
        detach = self.change("detach")
        self.apply("detach")
        self.apply()
        with self.assertRaises(ValueError):
            self.change("detach", token=cast(str, detach["preview_sha256"]))

    def test_replaced_directory_and_storage_identity_reject(self) -> None:
        self.apply()
        self.workspace.rename(self.base / "old-project")
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        self.workspace.rmdir()
        (self.base / "old-project").rename(self.workspace)
        preview = self.change("detach")
        old_root = self.base / "old-storage"
        self.storage.rename(old_root)
        self.storage.mkdir(mode=0o700)
        for path in old_root.iterdir():
            new = self.storage / path.name
            new.write_bytes(path.read_bytes())
            new.chmod(0o600)
        with self.assertRaises(ValueError):
            self.change("detach", token=cast(str, preview["preview_sha256"]))

    def test_unsafe_files_and_roots_are_rejected(self) -> None:
        self.apply()
        record = self.record_path()
        payload = record.read_bytes()
        record.chmod(0o644)
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        record.chmod(0o600)
        linked = self.base / "linked"
        os.link(record, linked)
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        linked.unlink()
        record.unlink()
        outside = self.base / "outside"
        outside.write_bytes(payload)
        record.symlink_to(outside)
        with self.assertRaises((OSError, ValueError)):
            self.store.show(self.workspace)
        record.unlink()
        os.mkfifo(record, 0o600)
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        record.unlink()
        record.write_bytes(payload)
        record.chmod(0o600)
        self.storage.chmod(0o755)
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        self.storage.chmod(0o700)
        alias = self.base / "alias"
        alias.symlink_to(self.storage, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            GuidanceBindingStore(alias).show(self.workspace)

    def test_tampered_owner_snapshot_and_noncanonical_record_reject(self) -> None:
        self.apply()
        path = self.record_path()
        payload = path.read_bytes()
        record = ProjectGuidanceBindings.model_validate_json(payload)
        path.write_bytes(
            canonical_bytes(record.model_copy(update={"owner_uid": os.getuid() + 1}))
        )
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        path.write_bytes(payload + b"\n")
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        path.write_bytes(payload)
        snapshot = self.storage / snapshot_name(self.snapshot_hash())
        snapshot.write_bytes(
            snapshot.read_bytes().replace(
                b"Use explicit inputs", b"Use implicit inputs"
            )
        )
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        with self.assertRaises(ValueError):
            self.change("detach")

    def test_action_and_template_bounds_and_missing_snapshot(self) -> None:
        with self.assertRaises(ValueError):
            self.change("update")
        with self.assertRaises(ValueError):
            self.change("detach")
        with self.assertRaises(ValueError):
            self.change(template="different")
        for index in range(8):
            template = f"profile{index}"
            self.source(template=template)
            self.apply(template=template)
        self.source(template="overflow")
        with self.assertRaises(ValueError):
            self.change(template="overflow")
        (self.storage / snapshot_name(self.snapshot_hash())).unlink()
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        for value in ("../private", "A" * 64, "a" * 63):
            with self.assertRaises(ValueError):
                self.store.show(self.workspace, snapshot_sha256=value)

    def test_sources_rechecked_during_publication_and_failure_keeps_binding(
        self,
    ) -> None:
        self.apply()
        before = self.record_path().read_bytes()
        self.source("Reviewed update.")
        preview = self.change("update")

        def mutate(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            self.source("Changed after review.")
            publish_file(root, name, payload, verify, immutable=immutable)

        with (
            patch(
                "mos_eisley.project_guidance_binding.publish_file", side_effect=mutate
            ),
            self.assertRaises(ValueError),
        ):
            self.change("update", token=cast(str, preview["preview_sha256"]))
        self.assertEqual(self.record_path().read_bytes(), before)

    def test_oversized_storage_and_locked_storage_fail_closed(self) -> None:
        self.apply()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.store.show(self.workspace)
        self.record_path().write_bytes(b"x" * (GUIDANCE_FILE_BYTES + 1))
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)

    def test_failed_publication_keeps_previous_binding_and_pinned_versions(
        self,
    ) -> None:
        self.apply()
        before = self.record_path().read_bytes()
        self.source("New snapshot, not yet bound.")
        preview = self.change("update")
        with (
            patch("os.replace", side_effect=OSError("injected publication failure")),
            self.assertRaises(OSError),
        ):
            self.change("update", token=cast(str, preview["preview_sha256"]))
        self.assertEqual(self.record_path().read_bytes(), before)
        self.assertEqual(len(list(self.storage.glob("snapshot-*.json"))), 2)
        self.assertEqual(list(self.storage.glob(".guidance-*.tmp")), [])
        # An identical reviewed retry can safely reuse the immutable staged snapshot.
        self.change("update", token=cast(str, preview["preview_sha256"]))

    def test_post_publication_sync_failure_requires_inspection_before_retry(
        self,
    ) -> None:
        self.apply()
        self.source("Saved before the final sync error.")
        preview = self.change("update")
        real_fsync = os.fsync
        directory_syncs = 0

        def fail_final_sync(fd: int) -> None:
            nonlocal directory_syncs
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                directory_syncs += 1
                if directory_syncs == 2:
                    raise OSError("injected directory sync failure")
            real_fsync(fd)

        with patch("os.fsync", side_effect=fail_final_sync), self.assertRaises(OSError):
            self.change("update", token=cast(str, preview["preview_sha256"]))
        shown = json.dumps(self.store.show(self.workspace))
        self.assertIn("Saved before the final sync error", shown)
        with self.assertRaises(ValueError):
            self.change("update", token=cast(str, preview["preview_sha256"]))

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "guidance",
                *args,
                "-C",
                str(self.workspace),
                "--guidance-storage",
                str(self.storage),
            ],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "HOME": str(self.base)},
        )

    def test_cli_review_apply_update_detach_and_history_without_session_activation(
        self,
    ) -> None:
        inputs = [
            "--template-id",
            "engineering",
            "--descriptor",
            str(self.descriptor),
            "--markdown",
            str(self.markdown),
        ]
        preview = self.cli("attach", *inputs, "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        event = json.loads(preview.stdout)
        self.assertEqual(event["type"], "guidance.binding")
        self.assertFalse(self.storage.exists())
        applied = self.cli(
            "attach", *inputs, "--apply", "--expected-sha256", event["preview_sha256"]
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        old_hash = self.snapshot_hash()
        self.source("Updated through the terminal.")
        preview = self.cli("update", *inputs)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        event = json.loads(preview.stdout)
        applied = self.cli(
            "update", *inputs, "--apply", "--expected-sha256", event["preview_sha256"]
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        shown = self.cli("show", "--json")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Updated through the terminal", shown.stdout)
        preview = self.cli("detach", "--template-id", "engineering", "--json")
        event = json.loads(preview.stdout)
        applied = self.cli(
            "detach",
            "--template-id",
            "engineering",
            "--apply",
            "--expected-sha256",
            event["preview_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        historical = self.cli("show", "--snapshot-sha256", old_hash, "--json")
        self.assertEqual(historical.returncode, 0, historical.stderr)
        self.assertIn("Use explicit inputs", historical.stdout)
        self.assertEqual(list(self.workspace.iterdir()), [])
        self.assertFalse((self.base / ".mos-eisley-conversations").exists())
        self.assertFalse((self.base / ".mos-eisley-memory").exists())

    def test_cli_invalid_combinations_and_rejected_content_are_safe(self) -> None:
        for args in (
            ("show", "--apply"),
            ("attach",),
            ("detach", "--template-id", "engineering", "--apply"),
            ("attach", "--template-id", "engineering", "--snapshot-sha256", "a" * 64),
        ):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(self.storage.exists())
        canary = "PRIVATE_REJECTED_GUIDANCE_CANARY"
        self.descriptor.write_text(json.dumps({"tools": [canary]}))
        result = self.cli(
            "attach",
            "--template-id",
            "engineering",
            "--descriptor",
            str(self.descriptor),
            "--markdown",
            str(self.markdown),
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(canary, result.stdout + result.stderr)
        self.assertFalse(self.storage.exists())
        self.source("Escaped terminal controls: \x1b[31m.")
        result = self.cli(
            "attach",
            "--template-id",
            "engineering",
            "--descriptor",
            str(self.descriptor),
            "--markdown",
            str(self.markdown),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("\x1b", result.stdout)


if __name__ == "__main__":
    unittest.main()
