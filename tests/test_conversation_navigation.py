"""Workspace-scoped session discovery, exact latest selection and locked deletion."""

import asyncio
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.conversation_store import (
    ConversationSnapshot,
    ConversationStore,
    list_conversations,
)
from mos_eisley.run.store import private_write


def save_session(
    root: Path, workspace: Path, *, complete: bool = False
) -> ConversationState:
    cassette = demo_cassette()
    state = ConversationController.fresh(workspace, cassette)
    with ConversationStore(root, state.session_id, workspace) as store:
        store.save(state)
        controller = ConversationController(state, cassette, store.save)
        controller.submit(DEMO_PROMPTS[0] if complete else "PRIVATE-PROMPT")
        if complete:
            asyncio.run(controller.step())
        return controller.state


def invoke(arguments: list[str]) -> tuple[int, str, str]:
    output, errors = io.StringIO(), io.StringIO()
    with redirect_stdout(output), redirect_stderr(errors):
        code = main(arguments)
    return code, output.getvalue(), errors.getvalue()


class ConversationNavigationTests(TestCase):
    def test_scoped_sorted_metadata_without_writing_or_exposing_text(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "sessions"
            other = workspace / "other"
            other.mkdir()
            first = save_session(root, workspace)
            second = save_session(root, workspace)
            foreign = save_session(root, other)
            for state, stamp in ((first, 10), (second, 20), (foreign, 30)):
                os.utime(root / f"{state.session_id}.json", ns=(stamp, stamp))
            before = {
                p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()
            }
            summaries = list_conversations(root, workspace)
            self.assertEqual(
                [s.session_id for s in summaries], [second.session_id, first.session_id]
            )
            self.assertEqual(summaries[0].pending, 1)
            self.assertEqual(
                summaries[0].snapshot_sha256, digest(canonical_bytes(second))
            )
            self.assertNotIn("PRIVATE-PROMPT", str(summaries))
            self.assertEqual(
                before,
                {
                    p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in root.iterdir()
                },
            )

    def test_active_status_and_no_missing_lock_recreation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = save_session(root, root)
            with ConversationStore(root, state.session_id, root, create=False):
                self.assertTrue(list_conversations(root, root)[0].active)
            self.assertFalse(list_conversations(root, root)[0].active)
            lock = root / f"{state.session_id}.lock"
            lock.unlink()
            with self.assertRaises(FileNotFoundError):
                list_conversations(root, root)
            self.assertFalse(lock.exists())

    def test_catalog_rejects_corruption_and_ownership_before_returning_rows(
        self,
    ) -> None:
        for damage in ("digest", "owner", "public", "symlink", "hardlink", "fifo"):
            with self.subTest(damage=damage), TemporaryDirectory() as directory:
                root = Path(directory)
                state = save_session(root, root)
                path = root / f"{state.session_id}.json"
                if damage in {"digest", "owner"}:
                    changed = state.model_copy(update={"owner_uid": os.getuid() + 1})
                    snapshot = ConversationSnapshot(
                        state=changed,
                        sha256=digest(canonical_bytes(changed))
                        if damage == "owner"
                        else "0" * 64,
                    )
                    path.write_bytes(canonical_bytes(snapshot))
                elif damage == "public":
                    path.chmod(0o644)
                elif damage == "symlink":
                    path.rename(root / "target")
                    path.symlink_to(root / "target")
                elif damage == "hardlink":
                    os.link(path, root / "linked")
                else:
                    path.unlink()
                    os.mkfifo(path, 0o600)
                with self.assertRaises((ValueError, OSError)):
                    list_conversations(root, root)

    def test_bounded_directory_session_and_total_payload_scans(self) -> None:
        for name, limit in (
            ("MAX_DIRECTORY_ENTRIES", 1),
            ("MAX_SESSIONS", 0),
            ("MAX_CATALOG_BYTES", 1),
        ):
            with self.subTest(name=name), TemporaryDirectory() as directory:
                root = Path(directory)
                save_session(root, root)
                with (
                    patch(f"mos_eisley.run.conversation_store.{name}", limit),
                    self.assertRaisesRegex(ValueError, "limit"),
                ):
                    list_conversations(root, root)

    def test_empty_missing_and_public_storage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(list_conversations(root, root), ())
            missing = root / "missing"
            with self.assertRaises(FileNotFoundError):
                list_conversations(missing, root)
            self.assertFalse(missing.exists())
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                list_conversations(root, root)
            root.chmod(0o700)

    def test_exact_deletion_cleans_only_target_temps_and_keeps_lock(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = save_session(root, root)
            other = save_session(root, root)
            temporary = root / f".{state.session_id}.{'a' * 32}.tmp"
            private_write(temporary, b"PRIVATE-PARTIAL-SNAPSHOT")
            other_temp = root / f".{other.session_id}.{'b' * 32}.tmp"
            private_write(other_temp, b"OTHER-PRIVATE-SNAPSHOT")
            with ConversationStore(root, state.session_id, root, create=False) as store:
                receipt = store.delete(digest(canonical_bytes(state)))
                self.assertEqual(receipt.removed_temporary_files, 1)
                with self.assertRaisesRegex(ValueError, "deleted"):
                    store.save(state)
                with self.assertRaisesRegex(ValueError, "deleted"):
                    store.load()
                with self.assertRaises(BlockingIOError):
                    ConversationStore(root, state.session_id, root, create=False)
            self.assertFalse(temporary.exists())
            self.assertFalse((root / f"{state.session_id}.json").exists())
            self.assertEqual((root / f"{state.session_id}.lock").read_bytes(), b"")
            self.assertTrue(other_temp.exists())
            self.assertEqual(
                [s.session_id for s in list_conversations(root, root)],
                [other.session_id],
            )

    def test_delete_rejects_active_stale_and_wrong_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = save_session(root, root)
            other = root / "other"
            other.mkdir()
            with ConversationStore(root, state.session_id, root, create=False) as store:
                with self.assertRaises(BlockingIOError):
                    ConversationStore(root, state.session_id, root, create=False)
                with self.assertRaisesRegex(ValueError, "changed"):
                    store.delete("0" * 64)
            with (
                ConversationStore(root, state.session_id, other, create=False) as store,
                self.assertRaisesRegex(ValueError, "workspace"),
            ):
                store.delete(digest(canonical_bytes(state)))
            self.assertTrue((root / f"{state.session_id}.json").exists())

    def test_invalid_orphan_aborts_before_any_removal(self) -> None:
        for damage in ("symlink", "public", "hardlink", "fifo"):
            with self.subTest(damage=damage), TemporaryDirectory() as directory:
                root = Path(directory)
                state = save_session(root, root)
                good = root / f".{state.session_id}.{'a' * 32}.tmp"
                bad = root / f".{state.session_id}.{'b' * 32}.tmp"
                private_write(good, b"partial")
                if damage == "symlink":
                    bad.symlink_to(good)
                elif damage == "hardlink":
                    os.link(good, bad)
                elif damage == "fifo":
                    os.mkfifo(bad, 0o600)
                else:
                    private_write(bad, b"partial")
                    bad.chmod(0o644)
                with (
                    ConversationStore(
                        root, state.session_id, root, create=False
                    ) as store,
                    self.assertRaises((OSError, ValueError)),
                ):
                    store.delete(digest(canonical_bytes(state)))
                self.assertTrue(good.exists())
                self.assertTrue((root / f"{state.session_id}.json").exists())

    def test_cleanup_failure_preserves_snapshot_for_explicit_retry(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = save_session(root, root)
            temporary = root / f".{state.session_id}.{'a' * 32}.tmp"
            private_write(temporary, b"partial")
            unlink = os.unlink

            def fail_snapshot(path: str, *, dir_fd: int) -> None:
                if path.endswith(".json"):
                    raise OSError("unavailable")
                unlink(path, dir_fd=dir_fd)

            with ConversationStore(root, state.session_id, root, create=False) as store:
                with (
                    patch(
                        "mos_eisley.run.conversation_store.os.unlink",
                        side_effect=fail_snapshot,
                    ),
                    self.assertRaises(OSError),
                ):
                    store.delete(digest(canonical_bytes(state)))
                self.assertFalse(temporary.exists())
                self.assertEqual(store.load(), state)
                store.delete(digest(canonical_bytes(state)))


class ConversationNavigationCLITests(TestCase):
    def test_retention_works_after_workspace_directory_is_removed(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            workspace = parent / "workspace"
            workspace.mkdir()
            root = parent / "sessions"
            state = save_session(root, workspace)
            workspace.rmdir()
            options = ["--storage", str(root), "--workspace", str(workspace), "--json"]
            self.assertEqual(invoke(["sessions", *options])[0], 0)
            self.assertEqual(
                invoke(
                    [
                        "session-delete",
                        state.session_id,
                        "--expected-sha256",
                        digest(canonical_bytes(state)),
                        *options,
                    ]
                )[0],
                0,
            )
            self.assertFalse(workspace.exists())

    def test_list_and_delete_cli_return_metadata_only(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = save_session(root, root)
            options = ["--storage", str(root), "--workspace", str(root), "--json"]
            code, output, _ = invoke(["sessions", *options])
            self.assertEqual(code, 0)
            self.assertNotIn("PRIVATE-PROMPT", output)
            selected = json.loads(output)["sessions"][0]
            code, output, _ = invoke(
                [
                    "session-delete",
                    selected["session_id"],
                    "--expected-sha256",
                    selected["snapshot_sha256"],
                    *options,
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(output.splitlines()[-1])["session_id"], state.session_id
            )
            self.assertEqual(
                json.loads(invoke(["sessions", *options])[1])["sessions"], []
            )

    def test_last_resume_in_another_process_keeps_context_and_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "sessions"
            wanted = save_session(root, workspace, complete=True)
            other = workspace / "other"
            other.mkdir()
            foreign = save_session(root, other, complete=True)
            cassette = workspace / "cassette.json"
            cassette.write_bytes(canonical_bytes(demo_cassette()))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "resume",
                    "--last",
                    "--storage",
                    str(root),
                    "--workspace",
                    str(workspace),
                    "--cassette",
                    str(cassette),
                    "--json",
                ],
                input=DEMO_PROMPTS[1] + "\n",
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            self.assertIn(wanted.session_id, result.stdout)
            self.assertNotIn(foreign.session_id, result.stdout)
            self.assertIn("You gave me a boundary of ten.", result.stdout)

    def test_last_does_not_fall_back_from_active_changed_or_wrong_cassette(
        self,
    ) -> None:
        for failure in ("active", "changed", "cassette"):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                root = Path(directory)
                save_session(root, root)
                latest = save_session(root, root)
                os.utime(
                    root / f"{latest.session_id}.json",
                    ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000),
                )
                summaries = list_conversations(root, root)
                cassette = root / "cassette.json"
                cassette.write_bytes(canonical_bytes(demo_cassette()))
                arguments = [
                    "resume",
                    "--last",
                    "--storage",
                    str(root),
                    "--workspace",
                    str(root),
                    "--cassette",
                    str(cassette),
                    "--json",
                ]
                with ConversationStore(
                    root, latest.session_id, root, create=False
                ) as store:
                    if failure == "active":
                        self.assertEqual(invoke(arguments)[0], 2)
                        continue
                    state = store.load()
                    updated = state.model_copy(
                        update={
                            "revision": state.revision + 1,
                            "cassette_sha256": "0" * 64
                            if failure == "cassette"
                            else state.cassette_sha256,
                        }
                    )
                    store.save(updated)
                with patch(
                    "mos_eisley.conversation_cli.list_conversations",
                    return_value=summaries
                    if failure == "changed"
                    else list_conversations(root, root),
                ):
                    code, output, _ = invoke(arguments)
                self.assertEqual(code, 2)
                self.assertNotIn("conversation.opened", output)

    def test_empty_last_and_nonexistent_explicit_resume_do_not_create_files(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = root / "cassette.json"
            cassette.write_bytes(canonical_bytes(demo_cassette()))
            options = [
                "--storage",
                str(root),
                "--workspace",
                str(root),
                "--cassette",
                str(cassette),
                "--json",
            ]
            self.assertEqual(invoke(["resume", "--last", *options])[0], 2)
            self.assertEqual(invoke(["resume", "a" * 32, *options])[0], 2)
            self.assertEqual([p.name for p in root.iterdir()], ["cassette.json"])
