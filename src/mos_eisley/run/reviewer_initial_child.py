"""No-network worker for one signed G4 initial-child source proposal."""

from __future__ import annotations

import sys

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_correction_dispatch import MAX_JOB_BYTES
from mos_eisley.reviewer_initial_child import (
    G4InitialChildJob,
    validate_initial_child_proposal,
)


def main() -> int:
    try:
        payload = sys.stdin.buffer.read(MAX_JOB_BYTES + 1)
        if len(payload) > MAX_JOB_BYTES:
            raise ValueError("initial-child job exceeds limit")
        job = G4InitialChildJob.model_validate_json(payload)
        if payload != canonical_bytes(job):
            raise ValueError("initial-child job must be canonical")
        result = validate_initial_child_proposal(
            job.offer, job.signed_proposal, job.policy
        )
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except ValueError:
        print("initial-child job rejected", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
