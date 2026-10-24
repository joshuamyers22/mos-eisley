"""Capture an EOF or /quit startup outcome before checking application success.

Output is private diagnostic data. Use a new output directory for every child.
This utility does not send model messages or retry a failed command.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal


def capture(
    command: list[str],
    output: Path,
    *,
    cwd: Path,
    ending: Literal["quit", "eof"],
    timeout: float = 90,
) -> dict[str, object]:
    if ending not in ("quit", "eof") or not 0 < timeout <= 90:
        raise ValueError("Choose quit/EOF and a timeout within 90 seconds")
    output.mkdir(mode=0o700)  # Refuse to overwrite earlier evidence.
    record: dict[str, object] = {
        "started_at": datetime.now(UTC).isoformat(),
        "input": ending,
        "timed_out": False,
        "pid": None,
        "returncode": None,
        "signal": None,
    }
    started = time.monotonic()
    stdout, stderr = b"", b""
    try:
        with subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            record["pid"] = process.pid
            try:
                stdout, stderr = process.communicate(
                    input=b"/quit\n" if ending == "quit" else b"", timeout=timeout
                )
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                # Kill the child group, including descendants holding pipe ends.
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=5)
            record["returncode"] = process.returncode
            if process.returncode < 0:
                record["signal"] = signal.Signals(-process.returncode).name
    except OSError as error:
        record["spawn_error"] = type(error).__name__
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
        record["finished_at"] = datetime.now(UTC).isoformat()
        # Persist status first: neither output decoding nor a success assertion
        # may discard the actual outcome, as the earlier rc.7 harness did.
        (output / "status.json").write_text(json.dumps(record, indent=2) + "\n")
        (output / "stdout").write_bytes(stdout)
        (output / "stderr").write_bytes(stderr)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--ending", choices=("quit", "eof"), default="quit")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    record = capture(
        command, args.output, cwd=args.cwd, ending=args.ending, timeout=args.timeout
    )
    print(json.dumps(record))
    return 0 if record["returncode"] == 0 and not record["timed_out"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
