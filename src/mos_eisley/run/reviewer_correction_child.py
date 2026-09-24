"""No-mount offline validation worker for one bounded correction proposal."""

from __future__ import annotations

import sys

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_correction_dispatch import (
    MAX_JOB_BYTES,
    G4CorrectionChildJob,
    validate_correction_child_job,
)


def main() -> int:
    try:
        payload = sys.stdin.buffer.read(MAX_JOB_BYTES + 1)
        if len(payload) > MAX_JOB_BYTES:
            raise ValueError("correction child job exceeds limit")
        job = G4CorrectionChildJob.model_validate_json(payload)
        if payload != canonical_bytes(job):
            raise ValueError("correction child job must be canonical")
        sys.stdout.buffer.write(canonical_bytes(validate_correction_child_job(job)))
        return 0
    except ValueError:
        print("correction child job rejected", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
