"""Private recorded replay admission, independent of content hash verification."""

import asyncio
import io
import os
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, cast
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.core.models import ReviewPolicy
from mos_eisley.demo import demo_inputs
from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.identity import IdentityContextError
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run.private_replay import ReplayDirectory, private_replay
from mos_eisley.run.store import Manifest, load_run, load_skill_run_manifest, save_run


class PrivateReplayTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        brief, cassette = demo_inputs()
        policy = ReviewPolicy()
        result = asyncio.run(
            review(
                brief,
                tuple(item.critic for item in cassette.critics),
                RecordedReviewer(cassette),
                policy,
            )
        )
        self.expected = brief, cassette, policy, result
        self.run_path = save_run(self.root, *self.expected)

    def test_owner_private_and_readonly_replay_succeed_without_writes(self) -> None:
        before = {p.name: p.read_bytes() for p in self.run_path.iterdir()}
        self.assertEqual(load_run(self.run_path), self.expected)
        self.assertIsNone(load_skill_run_manifest(self.run_path))
        for item in self.run_path.iterdir():
            item.chmod(0o400)
        self.run_path.chmod(0o500)
        self.addCleanup(self.run_path.chmod, 0o700)
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["replay", str(self.run_path)]), 0)
        self.assertIn("replay.verified", output.getvalue())
        self.assertEqual(
            before, {p.name: p.read_bytes() for p in self.run_path.iterdir()}
        )

    def test_readable_root_and_files_refuse_before_decoding(self) -> None:
        for mode in (0o755, 0o750, 0o701):
            with self.subTest(root_mode=oct(mode)):
                self.run_path.chmod(mode)
                with (
                    patch.object(Manifest, "model_validate_json") as decode,
                    self.assertRaisesRegex(ValueError, "private storage"),
                ):
                    load_run(self.run_path)
                decode.assert_not_called()
        self.run_path.chmod(0o700)
        for name in ("manifest.json", "brief.json"):
            item = self.run_path / name
            for mode in (0o644, 0o640, 0o601):
                with self.subTest(name=name, mode=oct(mode)):
                    item.chmod(mode)
                    with self.assertRaisesRegex(ValueError, "private storage"):
                        load_run(self.run_path)
                    item.chmod(0o600)

    def test_foreign_owner_refuses_even_when_modes_are_private(self) -> None:
        actual_fstat = os.fstat
        for item in (
            self.run_path,
            self.run_path / "manifest.json",
            self.run_path / "brief.json",
        ):
            inode = item.stat().st_ino

            def foreign(fd: int, inode: int = inode) -> os.stat_result:
                info = actual_fstat(fd)
                if info.st_ino != inode:
                    return info
                fields = list(info)
                fields[4] = os.getuid() + 1
                return os.stat_result(fields)

            with (
                self.subTest(item=item.name),
                patch("mos_eisley.run.private_replay.os.fstat", side_effect=foreign),
                self.assertRaisesRegex(ValueError, "private storage"),
            ):
                load_run(self.run_path)

    def test_symlink_root_and_artifacts_refuse(self) -> None:
        link = self.root / "linked-run"
        link.symlink_to(self.run_path, target_is_directory=True)
        with self.assertRaises(OSError):
            load_run(link)
        artifact = self.run_path / "brief.json"
        saved = self.root / "saved-brief"
        artifact.rename(saved)
        artifact.symlink_to(saved)
        with self.assertRaises(OSError):
            load_run(self.run_path)

    def test_hardlinked_artifact_and_fifo_refuse(self) -> None:
        item = self.run_path / "brief.json"
        os.link(item, self.root / "alias")
        with self.assertRaisesRegex(ValueError, "private storage"):
            load_run(self.run_path)
        item.unlink()
        os.mkfifo(item, 0o600)
        with self.assertRaisesRegex(ValueError, "private storage"):
            load_run(self.run_path)

    def test_artifact_directory_entry_substitution_refuses(self) -> None:
        item = self.run_path / "brief.json"
        original_fdopen = os.fdopen

        def replace(fd: int, mode: str, *, closefd: bool = True) -> BinaryIO:
            if os.fstat(fd).st_ino == item.stat().st_ino:
                moved = self.root / "old-brief"
                item.rename(moved)
                shutil.copyfile(moved, item)
                item.chmod(0o600)
            return cast(BinaryIO, original_fdopen(fd, mode, closefd=closefd))

        with (
            patch("mos_eisley.run.private_replay.os.fdopen", side_effect=replace),
            self.assertRaisesRegex(ValueError, "artifact changed"),
        ):
            load_run(self.run_path)

    def test_root_substitution_does_not_redirect_artifact_reads(self) -> None:
        original_read = ReplayDirectory.read
        moved = self.root / "moved-run"

        def replace(root: ReplayDirectory, name: str, limit: int) -> bytes:
            if name == "manifest.json":
                self.run_path.rename(moved)
                self.run_path.mkdir(mode=0o700)
                (self.run_path / "manifest.json").write_text("must not decode")
            return original_read(root, name, limit)

        with (
            patch.object(ReplayDirectory, "read", replace),
            self.assertRaisesRegex(ValueError, "directory changed"),
        ):
            load_run(self.run_path)

    def test_bounds_names_and_context_are_checked(self) -> None:
        with private_replay(self.run_path) as root:
            with self.assertRaisesRegex(ValueError, "byte limit"):
                root.read("manifest.json", 1)
            for name in ("../brief.json", "/brief.json", "..", "a\\b"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    root.read(name, 100)
        with (
            patch("os.geteuid", return_value=os.getuid() + 1),
            self.assertRaises(IdentityContextError),
        ):
            load_run(self.run_path)
        with (
            patch.object(sys, "platform", "win32"),
            patch("mos_eisley.run.private_replay.os.open") as opened,
            self.assertRaises(UnsupportedPlatformError),
        ):
            load_run(self.run_path)
        opened.assert_not_called()

    def test_cli_refusal_does_not_echo_artifact_content(self) -> None:
        (self.run_path / "manifest.json").write_text("secret-owner-canary")
        self.run_path.chmod(0o755)
        with redirect_stderr(io.StringIO()) as error, redirect_stdout(io.StringIO()):
            self.assertEqual(main(["replay", str(self.run_path)]), 2)
        self.assertNotIn("secret-owner-canary", error.getvalue())
