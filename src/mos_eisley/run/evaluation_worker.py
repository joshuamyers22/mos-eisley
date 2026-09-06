"""Bounded stdin/stdout entrypoint; recorded fixtures only, no live credentials."""

import sys

from mos_eisley.core.models import canonical_bytes
from mos_eisley.evaluation.execution import run_recorded_evaluation
from mos_eisley.run.isolation import MAX_WIRE_BYTES, RecordedJob


def main() -> int:
    try:
        payload = sys.stdin.buffer.read(MAX_WIRE_BYTES + 1)
        if len(payload) > MAX_WIRE_BYTES:
            raise ValueError("input too large")
        job = RecordedJob.model_validate_json(payload)
        output = canonical_bytes(run_recorded_evaluation(job.batch, job.cassette))
        if len(output) > MAX_WIRE_BYTES:
            raise ValueError("output too large")
        sys.stdout.buffer.write(output)
        return 0
    except ValueError:
        print("isolated worker validation failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
