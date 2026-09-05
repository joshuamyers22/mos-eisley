"""No-mount, offline container boundary for recorded evaluation conformance."""

from __future__ import annotations

import re
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
from mos_eisley.run.process import MAX_WIRE_BYTES as MAX_WIRE_BYTES
from mos_eisley.run.process import bounded_process as bounded_process
from mos_eisley.run.watchdog import WatchdogHandle, arm_watchdog, remove_exact


class RecordedJob(Contract):
    batch: ExecutionBatch
    cassette: EvaluationCassette


class OfflineContainer:
    """Docker daemon/image are trusted; worker gets stdin only, never host mounts."""

    def __init__(
        self,
        docker: Path,
        image_id: str,
        lifecycle_root: Path = Path(".mos-eisley/container-lifecycles"),
    ):
        if not docker.is_absolute() or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", image_id
        ):
            raise ValueError(
                "explicit Docker executable and immutable image ID required"
            )
        self.docker = str(docker)
        self.image_id = image_id
        self.lifecycle_root = lifecycle_root
        self.lifecycle_path: Path | None = None

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
        container_id: str | None = None
        watchdog: WatchdogHandle | None = None
        self.lifecycle_path = None
        try:
            created = bounded_process(
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
            candidate_id = created.decode("ascii").strip()
            if not re.fullmatch(r"[0-9a-f]{64}", candidate_id):
                raise ValueError("Docker did not return a full container ID")
            container_id = candidate_id
            watchdog = arm_watchdog(
                self.docker,
                container_id,
                self.lifecycle_root,
                timeout + 5,
            )
            self.lifecycle_path = watchdog.directory
            output = bounded_process(
                [self.docker, "start", "--attach", "--interactive", container_id],
                payload,
                timeout,
            )
            exit_code = bounded_process(
                [
                    self.docker,
                    "inspect",
                    "--format",
                    "{{.State.ExitCode}}",
                    container_id,
                ],
                limit=65536,
            )
            if exit_code.strip() != b"0":
                raise ValueError("isolated worker failed")
            return output
        finally:
            if watchdog is not None:
                # Keep launcher cleanup too: a dead guardian must not remove the
                # launcher's ability to terminate its own worker.
                try:
                    assert container_id is not None
                    remove_exact(self.docker, container_id)
                finally:
                    watchdog.finish()
            elif container_id is not None:
                remove_exact(self.docker, container_id)
            else:
                # Creation may have reached Docker despite a lost response.
                # This name was generated by this invocation, never caller input.
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
