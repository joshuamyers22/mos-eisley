"""Real OS denial probes for the isolated Git subprocess boundary."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_directory import DirectorySelection
from mos_eisley.conversation_git import GitReadError, GitWorkspaceReader
from mos_eisley.conversation_git_isolation import (
    GitIsolationUnavailable,
    isolated_command,
)
from mos_eisley.run.process import bounded_process


class GitIsolationTests(TestCase):
    def test_os_denies_helper_process_and_loopback_network(self) -> None:
        script = """
import errno
import socket
import subprocess

for attempt in (
    lambda: subprocess.run(['/bin/sh', '-c', 'exit 0'], check=True),
    lambda: socket.create_connection(('127.0.0.1', 9), timeout=1),
):
    try:
        attempt()
    except OSError as error:
        assert error.errno in (errno.EPERM, errno.EACCES), error
    else:
        raise AssertionError('OS isolation did not deny the attempt')
print('isolated')
"""
        result = bounded_process(
            isolated_command(Path(sys.executable).resolve(), ["-c", script]),
            timeout=5,
            limit=100,
            environment={"LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"},
            cwd=Path("/"),
        )
        self.assertEqual(result, b"isolated\n")

    def test_unavailable_boundary_refuses_even_non_git_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            selected = DirectorySelection.inspect(Path(temporary))
            with (
                patch(
                    "mos_eisley.conversation_git.isolated_command",
                    side_effect=GitIsolationUnavailable("unavailable"),
                ),
                self.assertRaisesRegex(GitReadError, "isolation is unavailable"),
            ):
                GitWorkspaceReader(selected, Path(sys.executable).resolve())
