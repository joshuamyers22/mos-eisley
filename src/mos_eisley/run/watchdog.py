"""Detached, finite container cleanup lease; no prompt data or provider secrets."""

from __future__ import annotations

import argparse
import os
import re
import selectors
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.files import read_bounded
from mos_eisley.run.process import bounded_process, docker_environment
from mos_eisley.run.store import private_write


class CleanupLease(Contract):
    schema_version: Literal[1] = 1
    container_id: Digest
    max_runtime_seconds: Annotated[float, Field(gt=0, le=65)]


class CleanupRecord(Contract):
    schema_version: Literal[1] = 1
    lease_sha256: Digest
    container_id: Digest
    state: Literal["armed", "removed", "cleanup_failed"]
    attempts: Annotated[int, Field(ge=0, le=3)]


def remove_exact(docker: str, container_id: str) -> None:
    if not Path(docker).is_absolute() or not re.fullmatch(
        r"[0-9a-f]{64}", container_id
    ):
        raise ValueError("cleanup requires an absolute client and full container ID")
    try:
        bounded_process([docker, "rm", "--force", container_id], timeout=3, limit=65536)
    except (ValueError, OSError):
        # A prior removal can race this one. Only a successful, empty listing
        # establishes absence; daemon/permission failures never mean 'gone'.
        remaining = bounded_process(
            [
                docker,
                "ps",
                "--all",
                "--no-trunc",
                "--format",
                "{{.ID}}",
                "--filter",
                "id=" + container_id,
            ],
            timeout=3,
            limit=65536,
        )
        if remaining.strip():
            raise ValueError("exact container cleanup failed") from None


def supervise(
    docker: str,
    lease: CleanupLease,
    directory: Path,
    lease_fd: int,
    ready: Callable[[], None],
) -> CleanupRecord:
    lease_hash = digest(canonical_bytes(lease))
    armed = CleanupRecord(
        lease_sha256=lease_hash,
        container_id=lease.container_id,
        state="armed",
        attempts=0,
    )
    with selectors.DefaultSelector() as selector:
        selector.register(lease_fd, selectors.EVENT_READ)
        private_write(directory / "armed.json", canonical_bytes(armed))
        deadline = time.monotonic() + lease.max_runtime_seconds
        ready()
        # EOF means the launcher closed its non-inheritable lease writer or died.
        # Any unexpected byte also revokes the lease; this is not a command socket.
        while time.monotonic() < deadline:
            if selector.select(max(0, deadline - time.monotonic())):
                break
    state: Literal["removed", "cleanup_failed"] = "cleanup_failed"
    attempts = 0
    for attempts in range(1, 4):
        try:
            remove_exact(docker, lease.container_id)
        except (ValueError, OSError):
            if attempts < 3:
                time.sleep(0.2)
        else:
            state = "removed"
            break
    result = CleanupRecord(
        lease_sha256=lease_hash,
        container_id=lease.container_id,
        state=state,
        attempts=attempts,
    )
    private_write(directory / "result.json", canonical_bytes(result))
    return result


class WatchdogHandle:
    def __init__(
        self,
        process: subprocess.Popen[bytes],
        writer: int,
        directory: Path,
        lease: CleanupLease,
    ):
        self.process = process
        self.writer: int | None = writer
        self.directory = directory
        self.lease = lease

    def finish(self) -> None:
        if self.writer is not None:
            os.close(self.writer)
            self.writer = None
        try:
            exit_code = self.process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            # Do not kill the independent cleanup process when cleanup is slow.
            raise ValueError("watchdog cleanup did not finish in time") from None
        result = CleanupRecord.model_validate_json(
            read_bounded(self.directory / "result.json", 4096)
        )
        if (
            exit_code != 0
            or result.state != "removed"
            or result.container_id != self.lease.container_id
            or result.lease_sha256 != digest(canonical_bytes(self.lease))
        ):
            raise ValueError("watchdog did not confirm exact container removal")


def arm_watchdog(
    docker: str,
    container_id: str,
    root: Path,
    max_runtime_seconds: float,
) -> WatchdogHandle:
    lease = CleanupLease(
        container_id=container_id, max_runtime_seconds=max_runtime_seconds
    )
    if not Path(docker).is_absolute():
        raise ValueError("watchdog requires an absolute Docker executable")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = root.absolute() / uuid4().hex
    directory.mkdir(mode=0o700)
    private_write(directory / "lease.json", canonical_bytes(lease))
    reader, writer = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mos_eisley.run.watchdog",
                "--docker",
                docker,
                "--directory",
                str(directory),
                "--lease-fd",
                str(reader),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            pass_fds=(reader,),
            env=docker_environment(),
        )
        os.close(reader)
        reader = -1
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(5) or os.read(process.stdout.fileno(), 1) != b"R":
                raise ValueError("watchdog readiness failed; worker was not started")
        process.stdout.close()
        return WatchdogHandle(process, writer, directory, lease)
    except BaseException:
        os.close(writer)
        if reader >= 0:
            os.close(reader)
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            # Leave the finite guardian alive; caller also attempts cleanup.
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=25)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--lease-fd", type=int, required=True)
    args = parser.parse_args()

    def ready() -> None:
        sys.stdout.buffer.write(b"R")
        sys.stdout.buffer.flush()

    try:
        lease = CleanupLease.model_validate_json(
            read_bounded(args.directory / "lease.json", 4096)
        )
        result = supervise(
            args.docker,
            lease,
            args.directory,
            args.lease_fd,
            ready,
        )
        return 0 if result.state == "removed" else 2
    except (ValueError, OSError):
        return 2
    finally:
        os.close(args.lease_fd)


if __name__ == "__main__":
    raise SystemExit(main())
