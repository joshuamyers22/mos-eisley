"""Private host audit boundaries, not authenticated live evaluation evidence."""

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write


class AssignmentAuthorization(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["broker_conformance"] = "broker_conformance"
    plan_sha256: Digest
    batch_sha256: Digest
    sample_id: Digest
    candidate_id: Digest
    evaluation_request_sha256: Digest
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest


class BrokerAdmission(Contract):
    schema_version: Literal[1] = 1
    authorization_sha256: Digest


class BrokerOutcome(Contract):
    schema_version: Literal[1] = 1
    admission_sha256: Digest
    status: Literal["response_received", "failed", "cancelled"]
    response_sha256: Digest | None = None

    @model_validator(mode="after")
    def response_matches_status(self) -> Self:
        if (self.status == "response_received") != (self.response_sha256 is not None):
            raise ValueError("broker outcome response hash mismatch")
        return self


class BrokerAudit:
    """Trusted parent directory required; each audit owns a new private directory."""

    def __init__(self, directory: Path, authorization: AssignmentAuthorization):
        directory.mkdir(mode=0o700)  # Never reuse or overwrite an existing run.
        self.directory = directory
        self.authorization = authorization
        self.authorization_sha256 = digest(canonical_bytes(authorization))
        private_write(directory / "authorization.json", canonical_bytes(authorization))
        self._admission = BrokerAdmission(
            authorization_sha256=self.authorization_sha256
        )

    def admit(self) -> None:
        # Persist intent BEFORE token count or spending admission; not proof of send.
        private_write(
            self.directory / "admission.json", canonical_bytes(self._admission)
        )

    def finish(
        self,
        status: Literal["response_received", "failed", "cancelled"],
        response_sha256: str | None = None,
    ) -> None:
        outcome = BrokerOutcome(
            admission_sha256=digest(canonical_bytes(self._admission)),
            status=status,
            response_sha256=response_sha256,
        )
        private_write(self.directory / "outcome.json", canonical_bytes(outcome))


def verify_broker_audit(
    directory: Path, expected: AssignmentAuthorization
) -> BrokerOutcome:
    """Require an independently trusted expected binding; reject partial audits."""
    authorization = AssignmentAuthorization.model_validate_json(
        read_bounded(directory / "authorization.json", 4096)
    )
    if authorization != expected:
        raise ValueError("broker audit assignment mismatch")
    admission = BrokerAdmission.model_validate_json(
        read_bounded(directory / "admission.json", 4096)
    )
    outcome = BrokerOutcome.model_validate_json(
        read_bounded(directory / "outcome.json", 4096)
    )
    if admission.authorization_sha256 != digest(canonical_bytes(authorization)) or (
        outcome.admission_sha256 != digest(canonical_bytes(admission))
    ):
        raise ValueError("broker audit chain mismatch")
    return outcome
