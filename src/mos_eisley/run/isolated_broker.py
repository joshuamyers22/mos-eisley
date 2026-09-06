"""Fixture-tested private worker exchange; no paid command is exposed."""

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.broker_wire import BrokerAck, BrokerReply
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.provider_broker import RequestBoundBroker


def run_isolated_broker(
    broker: RequestBoundBroker, container: OfflineContainer, *, timeout: float = 30
) -> BrokerReply:
    reply: BrokerReply | None = None

    async def handle(wire: bytes) -> bytes:
        nonlocal reply
        reply = BrokerReply(response=await broker.redeem(wire))
        return canonical_bytes(reply)

    output = container.execute(
        ("-m", "mos_eisley.run.broker_worker"),
        canonical_bytes(broker.claim()),
        timeout,
        exchange_handler=handle,
    )
    ack = BrokerAck.model_validate_json(output)
    if reply is None or ack.response_sha256 != digest(canonical_bytes(reply)):
        raise ValueError("broker worker acknowledgement mismatch")
    # Return host-held data, never worker-authored provider output.
    return reply
