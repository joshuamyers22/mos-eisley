"""Real disk/SQLite boundaries and command exit semantics."""

import asyncio
import io
import os
import sqlite3
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.core.models import ReviewPolicy, canonical_bytes
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import index_run, load_run, private_write, save_run


class StoreTests(TestCase):
    def test_roundtrip_private_artifacts_index_and_tampering(self) -> None:
        brief, cassette = demo_inputs()
        policy = ReviewPolicy()
        result = asyncio.run(
            review(
                brief,
                tuple(r.critic for r in cassette.critics),
                RecordedReviewer(cassette),
                policy,
            )
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run = save_run(root, brief, cassette, policy, result)
            self.assertEqual(load_run(run), (brief, cassette, policy, result))
            self.assertEqual(run.stat().st_mode & 0o777, 0o700)
            self.assertEqual((run / "result.json").stat().st_mode & 0o777, 0o600)
            index_run(root, run, result)
            index_run(root, run, result)
            with sqlite3.connect(root / "index.sqlite") as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1
                )
            (run / "brief.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                load_run(run)

    def test_input_rejects_symlinks_special_files_and_oversize(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "input"
            private_write(file, b"1234")
            link = root / "link"
            link.symlink_to(file)
            with self.assertRaises(OSError):
                read_bounded(link)
            with self.assertRaises(ValueError):
                read_bounded(file, 3)
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                read_bounded(fifo)
            with self.assertRaises(FileExistsError):
                private_write(file, b"overwrite")
            self.assertEqual(file.read_bytes(), b"1234")


class CliTests(TestCase):
    def test_demo_review_and_replay_exit_codes(self) -> None:
        with (
            TemporaryDirectory() as directory,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(["demo", "--output", directory, "--json"]), 1)
            self.assertIn('"mode": "recorded"', output.getvalue())
            run = next(path for path in Path(directory).iterdir() if path.is_dir())
            self.assertEqual(main(["replay", str(run)]), 0)
            self.assertEqual(
                main(
                    [
                        "review",
                        "--brief",
                        str(run / "brief.json"),
                        "--cassette",
                        str(run / "cassette.json"),
                        "--output",
                        directory,
                    ]
                ),
                1,
            )

    def test_errors_do_not_echo_rejected_inputs(self) -> None:
        with (
            TemporaryDirectory() as directory,
            redirect_stderr(io.StringIO()) as errors,
        ):
            brief = Path(directory) / "brief"
            brief.write_text('{"secret":"sensitive-value"}')
            self.assertEqual(
                main(["review", "--brief", str(brief), "--cassette", str(brief)]), 2
            )
            self.assertNotIn("sensitive-value", errors.getvalue())
            self.assertEqual(main(["replay", str(Path(directory) / "missing")]), 2)

    def test_index_failure_keeps_completed_artifacts(self) -> None:
        with (
            TemporaryDirectory() as directory,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as errors,
        ):
            with patch(
                "mos_eisley.cli.index_run", side_effect=sqlite3.OperationalError
            ):
                self.assertEqual(main(["demo", "--output", directory]), 1)
            self.assertIn("preserved", errors.getvalue())
            run = next(Path(directory).iterdir())
            self.assertEqual(main(["replay", str(run)]), 0)

    def test_brief_cassette_mismatch(self) -> None:
        brief, cassette = demo_inputs()
        with TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            root = Path(directory)
            (root / "brief").write_bytes(
                canonical_bytes(brief.model_copy(update={"spec": "new"}))
            )
            (root / "cassette").write_bytes(canonical_bytes(cassette))
            self.assertEqual(
                main(
                    [
                        "review",
                        "--brief",
                        str(root / "brief"),
                        "--cassette",
                        str(root / "cassette"),
                    ]
                ),
                2,
            )
