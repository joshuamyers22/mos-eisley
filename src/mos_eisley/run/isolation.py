"""No-mount, offline container boundary for recorded evaluation conformance."""

from __future__ import annotations

import os
import re
import selectors
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from pydantic import JsonValue, TypeAdapter

from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.evaluation.execution import (
    EvaluationCassette,
    ExecutionBatch,
    RawResultSet,
    run_recorded_evaluation,
)

MAX_WIRE_BYTES = 16_000_000


class RecordedJob(Contract):
    batch: ExecutionBatch
    cassette: EvaluationCassette


def bounded_process(
    command: list[str],
    payload: bytes = b"",
    timeout: float = 30,
    limit: int = MAX_WIRE_BYTES,
) -> bytes:
    """Drain both pipes; terminate the client on limits or cancellation."""
    if len(payload) > MAX_WIRE_BYTES:
        raise ValueError("isolated input exceeds byte limit")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in (
            "PATH",
            "HOME",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        )
    }
    with tempfile.TemporaryFile() as source:
        source.write(payload)
        source.seek(0)
        with (
            subprocess.Popen(
                command,
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
            ) as process,
            selectors.DefaultSelector() as selector,
        ):
            assert process.stdout is not None and process.stderr is not None
            streams = {process.stdout: bytearray(), process.stderr: bytearray()}
            for stream in streams:
                selector.register(stream, selectors.EVENT_READ)
            deadline = time.monotonic() + timeout
            try:
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError("isolated process deadline exceeded")
                    for key, _ in selector.select(min(remaining, 0.1)):
                        stream = (
                            process.stdout
                            if key.fileobj is process.stdout
                            else process.stderr
                        )
                        block = os.read(stream.fileno(), 65536)
                        if not block:
                            selector.unregister(stream)
                            continue
                        buffer = streams[stream]
                        cap = limit if stream is process.stdout else 65536
                        if len(buffer) + len(block) > cap:
                            raise ValueError(
                                "isolated process output exceeds byte limit"
                            )
                        buffer.extend(block)
                remaining = deadline - time.monotonic()
                if remaining <= 0 or process.wait(timeout=remaining) != 0:
                    raise ValueError("isolated process failed")
                return bytes(streams[process.stdout])
            except BaseException as error:
                process.kill()
                process.wait()
                if isinstance(error, subprocess.TimeoutExpired):
                    raise ValueError("isolated process deadline exceeded") from None
                raise


class OfflineContainer:
    """Docker daemon/image are trusted; worker gets stdin only, never host mounts."""

    def __init__(self, docker: Path, image_id: str):
        if not docker.is_absolute() or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", image_id
        ):
            raise ValueError(
                "explicit Docker executable and immutable image ID required"
            )
        self.docker = str(docker)
        self.image_id = image_id

    def execute(
        self, arguments: tuple[str, ...], payload: bytes, timeout: float = 30
    ) -> bytes:
        if len(payload) > MAX_WIRE_BYTES or not 0 < timeout <= 60:
            raise ValueError("invalid isolated execution bounds")
        metadata = TypeAdapter(list[dict[str, JsonValue]]).validate_json(
            bounded_process(
                [self.docker, "image", "inspect", self.image_id], limit=1_000_000
            )
        )
        if len(metadata) != 1 or metadata[0].get("Id") != self.image_id:
            raise ValueError(
                "image identity or implicit volume configuration is invalid"
            )
        config = metadata[0].get("Config")
        if not isinstance(config, dict) or config.get("Volumes"):
            raise ValueError("image configuration permits implicit volumes")
        name = "mos-eval-" + uuid4().hex
        try:
            bounded_process(
                [
                    self.docker,
                    "create",
                    "--name",
                    name,
                    "--pull",
                    "never",
                    "--interactive",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges=true",
                    "--user",
                    "10001:10001",
                    "--pids-limit",
                    "32",
                    "--memory",
                    "512m",
                    "--memory-swap",
                    "512m",
                    "--cpus",
                    "1",
                    "--ulimit",
                    "nofile=64:64",
                    "--ipc",
                    "none",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
                    "--log-driver",
                    "none",
                    "--entrypoint",
                    "/app/.venv/bin/python",
                    self.image_id,
                    *arguments,
                ],
                limit=65536,
            )
            output = bounded_process(
                [self.docker, "start", "--attach", "--interactive", name],
                payload,
                timeout,
            )
            exit_code = bounded_process(
                [self.docker, "inspect", "--format", "{{.State.ExitCode}}", name],
                limit=65536,
            )
            if exit_code.strip() != b"0":
                raise ValueError("isolated worker failed")
            return output
        finally:
            # Killing an attached client does not guarantee container termination.
            # A failed removal is surfaced; never claim successful cleanup then.
            bounded_process(
                [self.docker, "rm", "--force", name], timeout=10, limit=65536
            )


def run_isolated_recorded(
    batch: ExecutionBatch, cassette: EvaluationCassette, container: OfflineContainer
) -> RawResultSet:
    expected = run_recorded_evaluation(batch, cassette)
    payload = canonical_bytes(RecordedJob(batch=batch, cassette=cassette))
    response = container.execute(("-m", "mos_eisley.run.evaluation_worker"), payload)
    actual = RawResultSet.model_validate_json(response)
    if actual != expected:
        raise ValueError("isolated recorded output differs from fixture contract")
    return actual
