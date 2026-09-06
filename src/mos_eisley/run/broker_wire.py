"""Wire contracts contain no credentials, endpoint or spending authority."""

from typing import Literal

from pydantic import JsonValue

from mos_eisley.core.models import Contract, Digest


class BrokerReply(Contract):
    schema_version: Literal[1] = 1
    response: dict[str, JsonValue]


class BrokerAck(Contract):
    schema_version: Literal[1] = 1
    response_sha256: Digest
