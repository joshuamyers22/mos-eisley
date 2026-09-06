"""Offline IPC conformance worker; acknowledges bytes, not evaluation quality."""

import sys

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.broker_wire import BrokerAck, BrokerReply
from mos_eisley.run.process import MAX_WIRE_BYTES


def main() -> int:
    try:
        # The offer is opaque: worker has no provider client or host configuration.
        offer = sys.stdin.buffer.readline(1026)
        if not offer.endswith(b"\n") or len(offer) > 1025:
            raise ValueError("invalid offer")
        sys.stdout.buffer.write(offer)
        sys.stdout.buffer.flush()
        reply = sys.stdin.buffer.readline(MAX_WIRE_BYTES + 2)
        if not reply.endswith(b"\n") or len(reply) > MAX_WIRE_BYTES + 1:
            raise ValueError("invalid reply")
        BrokerReply.model_validate_json(reply)
        ack = BrokerAck(response_sha256=digest(reply[:-1]))
        sys.stdout.buffer.write(canonical_bytes(ack) + b"\n")
        sys.stdout.buffer.flush()
        return 0
    except ValueError:
        print("broker worker failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
