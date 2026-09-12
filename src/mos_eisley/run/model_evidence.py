"""Private completion receipts for an already authorized model exchange."""

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes
from mos_eisley.run.store import private_write


class ModelCompletion(Contract):
    schema_version: Literal[1] = 1
    request_sha256: Digest
    status: Literal["received", "failed", "cancelled"]
    broker_response_sha256: Digest | None = None
    model_response_sha256: Digest | None = None

    @model_validator(mode="after")
    def consistent_response(self) -> Self:
        if (self.status == "received") != (self.model_response_sha256 is not None):
            raise ValueError("model completion response/status mismatch")
        if (
            self.model_response_sha256 is not None
            and self.broker_response_sha256 is None
        ):
            raise ValueError("canonical response requires a broker response")
        return self


def save_completion(directory: Path | None, completion: ModelCompletion) -> None:
    if directory is not None:
        private_write(directory / "model-completion.json", canonical_bytes(completion))
