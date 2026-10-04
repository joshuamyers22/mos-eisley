"""OS-enforced process and network boundary for untrusted-workspace Git reads."""

import os
import re
import sys
from pathlib import Path

from mos_eisley.run.process import bounded_process

SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
XCRUN = Path("/usr/bin/xcrun")
APPLE_GIT_SHIM = Path("/usr/bin/git")
_SAFE_PROFILE_PATH = re.compile(r"[A-Za-z0-9_./+ -]+\Z")


class GitIsolationUnavailable(OSError):
    """The host cannot enforce the required Git process boundary."""


def executable_for_host(selected: Path) -> Path:
    """Resolve Apple's Git shim before the Seatbelt profile binds an executable."""
    if sys.platform == "darwin" and selected == APPLE_GIT_SHIM:
        try:
            raw = bounded_process(
                [str(XCRUN), "--find", "git"],
                timeout=3,
                limit=4096,
                environment={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
                cwd=Path("/"),
            )
            value = raw.decode("utf-8").removesuffix("\n")
            path = Path(value)
            if not path.is_absolute() or not value.isprintable():
                raise ValueError("invalid Git path")
            return path
        except (OSError, UnicodeError, ValueError):
            raise GitIsolationUnavailable("Trusted Apple Git is unavailable.") from None
    return selected


def isolated_command(executable: Path, arguments: list[str]) -> list[str]:
    """Launch one command with child creation and networking denied by the OS."""
    if not executable.is_absolute():
        raise GitIsolationUnavailable("An absolute executable is required.")
    if sys.platform == "darwin":
        path = str(executable)
        if not _SAFE_PROFILE_PATH.fullmatch(path) or not os.access(
            SANDBOX_EXEC, os.X_OK
        ):
            raise GitIsolationUnavailable("macOS Git isolation is unavailable.")
        profile = (
            "(version 1)\n"
            "(allow default)\n"
            "(deny network*)\n"
            "(deny process-fork)\n"
            "(deny process-exec)\n"
            f'(allow process-exec (literal "{path}"))\n'
        )
        return [str(SANDBOX_EXEC), "-p", profile, path, *arguments]
    if sys.platform == "linux":
        if not sys.executable or not Path(sys.executable).is_absolute():
            raise GitIsolationUnavailable("Linux Git isolation is unavailable.")
        return [
            sys.executable,
            "-I",
            "-m",
            "mos_eisley._git_read_linux",
            str(executable),
            *arguments,
        ]
    raise GitIsolationUnavailable("Git reads are unsupported on this host.")
