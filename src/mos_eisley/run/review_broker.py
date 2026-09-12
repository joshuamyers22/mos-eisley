"""Explicit host approval and durable spend admission for one read-only review call."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import model_validator

from mos_eisley.core.models import (
    CriticRequest,
    CriticSpec,
    Digest,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import ModelRequest
from mos_eisley.providers.brokered_openai import BrokeredOpenAIClient
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_responses import request_payload
from mos_eisley.providers.openai_spend import (
    CountedTransport,
    Money,
    PreReservedOpenAITransport,
    SpendPolicy,
    prepare_full_reservation,
)
from mos_eisley.run.broker_audit import (
    BrokerAdmission,
    BrokerAudit,
    BrokerAuthorization,
    BrokerOutcome,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.provider_broker import (
    MAX_REQUEST_BYTES,
    ApprovedRequest,
    RequestBoundBroker,
)
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write


class ReviewAuthorization(BrokerAuthorization):
    schema_version: Literal[1] = 1
    mode: Literal["read_only_review"] = "read_only_review"
    role: Literal["critic", "judge"]
    brief_sha256: Digest
    review_input_sha256: Digest
    critic_sha256: Digest | None = None
    model_request_sha256: Digest
    reservation_sha256: Digest
    reserved_microusd: Money
    ledger_policy_sha256: Digest
    expires_at: datetime

    @model_validator(mode="after")
    def coherent_role(self) -> Self:
        if (self.role == "critic") != (self.critic_sha256 is not None):
            raise ValueError("review authorization critic identity mismatch")
        if self.expires_at.tzinfo is None:
            raise ValueError("review approval expiry must include a timezone")
        return self


class PreparedReviewCall:
    """Trusted host only: preview is not approval, credential access or dispatch.

    The caller verifies guidance and judge lineage separately. Never populate the
    approval argument from model output or automatically echo a preview hash.
    """

    def __init__(
        self,
        reviewer: ModelReviewer,
        request: CriticRequest | JudgeRequest,
        policy: SpendPolicy,
        ledger: SpendLedger,
        *,
        critic: CriticSpec | None = None,
    ) -> None:
        if isinstance(request, CriticRequest) and critic is not None:
            model_request = reviewer.critic_request(critic, request)
            role = "critic"
        elif isinstance(request, JudgeRequest) and critic is None:
            model_request = reviewer.judge_request(request)
            role = "judge"
        else:
            raise ValueError("review call role and critic do not match")
        frozen = canonical_bytes(model_request)
        if (
            len(frozen) > MAX_REQUEST_BYTES
            or model_request.provider != "openai"
            or model_request.max_output > 16_000_000
        ):
            raise ValueError("review call exceeds the brokered text scope")
        policy = SpendPolicy.model_validate_json(canonical_bytes(policy))
        if policy.schema_version != 2:
            raise ValueError(
                "review spending requires conservative cache-write pricing"
            )
        payload = request_payload(model_request)
        provider_bytes = canonical_bytes(ApprovedRequest(payload=payload))
        if len(provider_bytes) > MAX_REQUEST_BYTES:
            raise ValueError("review provider request exceeds the broker limit")
        reservation = prepare_full_reservation(payload, policy)
        snapshot = ledger.snapshot()
        if (
            snapshot.blocked
            or reservation.reserved_microusd > snapshot.available_microusd
        ):
            raise ValueError("review spending envelope is unavailable")
        self._authorization = ReviewAuthorization(
            role=role,
            brief_sha256=request.brief.brief_id,
            review_input_sha256=digest(canonical_bytes(request)),
            critic_sha256=None if critic is None else digest(canonical_bytes(critic)),
            model_request_sha256=digest(frozen),
            provider_request_sha256=digest(provider_bytes),
            spend_policy_sha256=policy.policy_sha256,
            reservation_sha256=digest(canonical_bytes(reservation)),
            reserved_microusd=reservation.reserved_microusd,
            ledger_id=ledger.policy.ledger_id,
            ledger_policy_sha256=digest(canonical_bytes(ledger.policy)),
            ledger_entry_id=digest(uuid4().bytes),
            expires_at=min(
                datetime.now(UTC) + timedelta(minutes=10), policy.valid_until
            ),
        )
        self._request = frozen
        self._input = canonical_bytes(request)
        self._critic = None if critic is None else canonical_bytes(critic)
        self._policy = policy
        self._reservation = reservation
        self._ledger = ledger

    @property
    def authorization(self) -> ReviewAuthorization:
        return self._authorization

    @property
    def approval_sha256(self) -> str:
        """Confirmation identifies content, destination/model, limits and expiry."""
        return digest(canonical_bytes(self._authorization))

    @property
    def model_request(self) -> ModelRequest:
        return ModelRequest.model_validate_json(self._request)

    def issue(
        self,
        *,
        approved_transfer_sha256: str,
        transport: CountedTransport,
        directory: Path,
        container: OfflineContainer,
        timeout: float = 30,
    ) -> BrokeredOpenAIClient:
        """Reserve once before grant issuance; any subsequent crash retains the hold.

        Approval includes token counting and generation. Transport and filesystem
        parent are trusted host dependencies; this function never obtains credentials.
        """
        authorization = self._authorization
        if approved_transfer_sha256 != self.approval_sha256:
            raise ValueError("exact review transfer and spending approval required")
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError(
                "review broker timeout must be between zero and 60 seconds"
            )
        self._policy.check_current()
        if datetime.now(UTC) >= authorization.expires_at:
            raise ValueError("review approval expired")
        if (
            digest(canonical_bytes(self._ledger.policy))
            != authorization.ledger_policy_sha256
        ):
            raise ValueError("review spending scope changed")
        entry = LedgerEntry(
            entry_id=authorization.ledger_entry_id,
            reservation_sha256=authorization.reservation_sha256,
            reserved_microusd=authorization.reserved_microusd,
        )
        # SQLite's unique entry and serialized ceiling check burn this approval
        # across concurrent issuers, even if they choose different artifact paths.
        self._ledger.reserve(entry)
        audit = BrokerAudit(directory, authorization)
        private_write(directory / "model-request.json", self._request)
        private_write(directory / "review-input.json", self._input)
        if self._critic is not None:
            private_write(directory / "critic.json", self._critic)
        private_write(directory / "spend-policy.json", canonical_bytes(self._policy))
        private_write(directory / "spend-plan.json", canonical_bytes(self._reservation))
        remaining = (authorization.expires_at - datetime.now(UTC)).total_seconds()
        controller = PreReservedOpenAITransport(
            transport, self._policy, directory, self._ledger, self._reservation, entry
        )
        broker = RequestBoundBroker(
            request_payload(self.model_request),
            controller,
            lifetime_seconds=min(timeout, remaining),
            audit=audit,
        )
        return BrokeredOpenAIClient(
            self.model_request, broker, container, timeout=timeout
        )


def verify_review_broker_audit(
    directory: Path, expected: ReviewAuthorization
) -> BrokerOutcome:
    """Verify one completed host audit against independently trusted approval.

    Response receipt is not proof of accepted review output or pipeline quorum.
    Missing artifacts fail closed; verification never issues or retries a grant.
    """
    expected = ReviewAuthorization.model_validate_json(canonical_bytes(expected))
    actual = ReviewAuthorization.model_validate_json(
        read_bounded(directory / "authorization.json", 4096)
    )
    if actual != expected:
        raise ValueError("review audit authorization mismatch")
    artifacts = {
        "model-request.json": expected.model_request_sha256,
        "review-input.json": expected.review_input_sha256,
        "spend-policy.json": expected.spend_policy_sha256,
        "spend-plan.json": expected.reservation_sha256,
    }
    if expected.critic_sha256 is not None:
        artifacts["critic.json"] = expected.critic_sha256
    elif (directory / "critic.json").exists():
        raise ValueError("judge audit contains a critic identity")
    for name, sha256 in artifacts.items():
        if digest(read_bounded(directory / name, MAX_REQUEST_BYTES)) != sha256:
            raise ValueError("review audit artifact mismatch")
    admission = BrokerAdmission.model_validate_json(
        read_bounded(directory / "admission.json", 4096)
    )
    outcome = BrokerOutcome.model_validate_json(
        read_bounded(directory / "outcome.json", 4096)
    )
    if outcome.schema_version != 4:
        raise ValueError("review audit requires the current outcome schema")
    if admission.authorization_sha256 != digest(canonical_bytes(expected)) or (
        outcome.admission_sha256 != digest(canonical_bytes(admission))
    ):
        raise ValueError("review audit chain mismatch")
    return outcome
