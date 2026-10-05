"""Offline fresh-brief child; bounded wire input and digest-only acknowledgement."""

import asyncio
import sys

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.local_child import (
    ChildWire,
    LocalChildAck,
    LocalChildOffer,
    replay_child,
)


def main() -> int:
    try:
        offer_raw = sys.stdin.buffer.readline(1026)
        if not offer_raw.endswith(b"\n") or len(offer_raw) > 1025:
            raise ValueError("Invalid child offer.")
        offer = LocalChildOffer.model_validate_json(offer_raw)
        sys.stdout.buffer.write(canonical_bytes(offer) + b"\n")
        sys.stdout.buffer.flush()
        payload = sys.stdin.buffer.readline(128_002)
        if not payload.endswith(b"\n") or len(payload) > 128_001:
            raise ValueError("Invalid child wire size.")
        wire = ChildWire.model_validate_json(payload)
        if digest(canonical_bytes(wire.job)) != offer.job_sha256:
            raise ValueError("Child brief differs from its offer.")
        execution = asyncio.run(replay_child(wire.job, wire.image_id))
        ack = LocalChildAck(
            job_sha256=offer.job_sha256,
            execution_sha256=digest(canonical_bytes(execution)),
        )
        sys.stdout.buffer.write(canonical_bytes(ack) + b"\n")
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        print("Local child validation/execution failed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
