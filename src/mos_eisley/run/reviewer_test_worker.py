"""Validated controller for one isolated reviewer-test child process."""

from __future__ import annotations

import sys
from pathlib import Path

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_test_execution import (
    decode_execution_job,
    decode_execution_observation,
)
from mos_eisley.run.process import MAX_WIRE_BYTES, bounded_process


def main() -> int:
    payload = sys.stdin.buffer.read(MAX_WIRE_BYTES + 1)
    if len(payload) > MAX_WIRE_BYTES:
        raise ValueError("isolated reviewer-test job exceeds the wire limit")
    job = decode_execution_job(payload)
    child = Path(__file__).with_name("reviewer_test_child.py")
    response = bounded_process(
        [sys.executable, "-I", str(child)],
        canonical_bytes(job),
        timeout=float(job.request.timeout_seconds - 1),
        limit=256_000,
    )
    observation = decode_execution_observation(response)
    if observation.job_sha256 != job.job_sha256:
        raise ValueError("reviewer-test child observed a different job")
    sys.stdout.buffer.write(canonical_bytes(observation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
