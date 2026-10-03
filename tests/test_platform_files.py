"""Isolated bounded-reader tests; importing the CLI is deliberately unnecessary."""

import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mos_eisley.run.files import read_bounded


@unittest.skipUnless(sys.platform in {"darwin", "linux"}, "qualified POSIX reader")
class PosixFileReaderTests(unittest.TestCase):
    def test_bytes_and_boundaries(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"")
            self.assertEqual(read_bounded(path, 0), b"")
            path.write_bytes(b"\x00\xffabc")
            self.assertEqual(read_bounded(path), b"\x00\xffabc")
            self.assertEqual(read_bounded(path, 5), b"\x00\xffabc")
            for limit in (0, 4):
                with (
                    self.subTest(limit=limit),
                    self.assertRaisesRegex(ValueError, "input exceeds the byte limit"),
                ):
                    read_bounded(path, limit)

    def test_missing_directory_and_final_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                read_bounded(root / "missing")
            with self.assertRaises(IsADirectoryError):
                read_bounded(root)
            target = root / "target"
            target.write_bytes(b"private")
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                read_bounded(link)

    def test_fifo_refusal_has_external_deadline(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fifo"
            os.mkfifo(path)
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; "
                    "from mos_eisley.run.files import read_bounded; "
                    "read_bounded(Path(__import__('sys').argv[1]))",
                    str(path),
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"input must be a regular file", result.stderr)

    def test_hardlinks_and_ancestor_symlinks_remain_allowed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actual = root / "actual"
            actual.mkdir()
            path = actual / "input"
            path.write_bytes(b"data")
            hardlink = root / "hardlink"
            os.link(path, hardlink)
            ancestor = root / "ancestor"
            ancestor.symlink_to(actual, target_is_directory=True)
            self.assertEqual(read_bounded(hardlink), b"data")
            self.assertEqual(read_bounded(ancestor / "input"), b"data")


class PlatformFileContractTests(unittest.TestCase):
    def test_invalid_limits_refuse_before_io(self) -> None:
        for limit in (-1, True, 1.5, "2", None):
            with self.subTest(limit=limit), patch("os.open") as opening:
                with self.assertRaisesRegex(ValueError, "nonnegative integer"):
                    read_bounded(Path("never-open"), limit)  # type: ignore[arg-type]
                opening.assert_not_called()

    def test_unsupported_platform_refuses_before_io(self) -> None:
        from mos_eisley.platform.files import UnsupportedPlatformError

        for platform in ("win32", "unqualified"):
            with (
                self.subTest(platform=platform),
                patch("sys.platform", platform),
                patch("os.open") as opening,
            ):
                with self.assertRaises(UnsupportedPlatformError):
                    read_bounded(Path("never-open"))
                opening.assert_not_called()

    def test_actual_host_selection(self) -> None:
        from mos_eisley.platform.files import UnsupportedPlatformError

        if sys.platform in {"darwin", "linux"}:
            with TemporaryDirectory() as directory:
                path = Path(directory) / "input"
                path.write_bytes(b"qualified")
                self.assertEqual(read_bounded(path), b"qualified")
        else:
            with patch("os.open") as opening:
                with self.assertRaises(UnsupportedPlatformError):
                    read_bounded(Path("never-open"))
                opening.assert_not_called()

    def test_clean_import_and_refusal_do_not_load_posix(self) -> None:
        code = """
import os
import sys
from unittest.mock import patch
sys.platform = 'win32'
for name in ('O_NOFOLLOW', 'O_NONBLOCK'):
    if hasattr(os, name):
        delattr(os, name)
with patch('os.open', side_effect=AssertionError('unexpected I/O')):
    from mos_eisley.run.files import read_bounded
    from mos_eisley.platform.files import UnsupportedPlatformError
    from pathlib import Path
    assert 'mos_eisley.platform.posix_files' not in sys.modules
    try:
        read_bounded(Path('never-open'))
    except UnsupportedPlatformError:
        pass
    else:
        raise AssertionError('platform was admitted')
    assert 'mos_eisley.platform.posix_files' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", code], check=True, timeout=5)


class FaultStream(io.BytesIO):
    def __init__(self, fd: int, outcome: str, testcase: unittest.TestCase) -> None:
        super().__init__(b"abc")
        self.fd = fd
        self.outcome = outcome
        self.testcase = testcase

    def fileno(self) -> int:
        return self.fd

    def read(self, size: int | None = -1) -> bytes:
        if self.outcome == "read":
            raise OSError("injected read failure")
        self.testcase.assertEqual(size, 3 if self.outcome == "overflow" else 4)
        return super().read(size)

    def close(self) -> None:
        if not self.closed:
            os.close(self.fd)
        super().close()


@unittest.skipUnless(sys.platform in {"darwin", "linux"}, "qualified POSIX reader")
class PosixFileFaultTests(unittest.TestCase):
    def test_descriptor_cleanup_on_all_exit_paths(self) -> None:
        from mos_eisley.platform import posix_files

        with TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"abc")
            for outcome in ("success", "overflow", "fdopen", "fstat", "type", "read"):
                with self.subTest(outcome=outcome):
                    fd = os.open(path, os.O_RDONLY)

                    stream = FaultStream(fd, outcome, self)
                    with (
                        patch.object(posix_files.os, "open", return_value=fd),
                        patch.object(
                            posix_files.os, "fdopen", return_value=stream
                        ) as wrapping,
                        patch.object(
                            posix_files.os, "fstat", wraps=os.fstat
                        ) as stating,
                    ):
                        if outcome == "fdopen":
                            wrapping.side_effect = OSError("injected wrapping failure")
                        elif outcome == "fstat":
                            stating.side_effect = OSError("injected stat failure")
                        elif outcome == "type":
                            stating.return_value = os.stat_result((0,) * 10)
                            stating.side_effect = None
                        if outcome == "success":
                            self.assertEqual(read_bounded(path, 3), b"abc")
                        else:
                            with self.assertRaises((OSError, ValueError)):
                                read_bounded(path, 2 if outcome == "overflow" else 3)
                    with self.assertRaises(OSError):
                        os.fstat(fd)
                    # fdopen failure leaves this test's fake stream unowned.
                    if outcome == "fdopen":
                        io.BytesIO.close(stream)

    def test_final_path_replacement_with_symlink_is_refused(self) -> None:
        from mos_eisley.platform import posix_files

        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input"
            path.write_bytes(b"original")
            target = root / "target"
            target.write_bytes(b"private")
            real_open = os.open

            def replace_then_open(pathname: Path, flags: int) -> int:
                pathname.unlink()
                pathname.symlink_to(target)
                return real_open(pathname, flags)

            with (
                patch.object(posix_files.os, "open", side_effect=replace_then_open),
                self.assertRaises(OSError),
            ):
                read_bounded(path)


if __name__ == "__main__":
    unittest.main()
