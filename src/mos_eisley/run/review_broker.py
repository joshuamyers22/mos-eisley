"""Explicit host approval and durable spend admission for one read-only review call."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
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
        reserved_allowance: DeferredJudgeAllowance | None = None,
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
        credit = 0
        if reserved_allowance is not None:
            reserved_allowance = DeferredJudgeAllowance.model_validate_json(
                canonical_bytes(reserved_allowance)
            )
            if (
                role != "judge"
                or reserved_allowance.brief_sha256 != request.brief.brief_id
                or reserved_allowance.spend_policy != policy
            ):
                raise ValueError("judge request differs from its reserved allowance")
            with ledger.guard_held(reserved_allowance.ledger_entry):
                credit = reserved_allowance.reserved_microusd
        self._allowance = reserved_allowance
        snapshot = ledger.snapshot()
        if (
            snapshot.blocked
            or reservation.reserved_microusd > snapshot.available_microusd + credit
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
        if self._allowance is not None:
            raise ValueError("reserved judge requires envelope transfer approval")
        if approved_transfer_sha256 != self.approval_sha256:
            raise ValueError("exact review transfer and spending approval required")
        self.check_current(timeout)
        self._ledger.reserve(self.ledger_entry)
        return self._issue_reserved(transport, directory, container, timeout)

    @property
    def ledger_entry(self) -> LedgerEntry:
        return LedgerEntry(
            entry_id=self._authorization.ledger_entry_id,
            reservation_sha256=self._authorization.reservation_sha256,
            reserved_microusd=self._authorization.reserved_microusd,
        )

    @property
    def ledger_path(self) -> Path:
        return self._ledger.path.resolve()

    @property
    def critic_spec(self) -> CriticSpec | None:
        return (
            None
            if self._critic is None
            else CriticSpec.model_validate_json(self._critic)
        )

    def check_current(self, timeout: float) -> None:
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError(
                "review broker timeout must be between zero and 60 seconds"
            )
        self._policy.check_current()
        if datetime.now(UTC) >= self._authorization.expires_at:
            raise ValueError("review approval expired")
        if (
            digest(canonical_bytes(self._ledger.policy))
            != self._authorization.ledger_policy_sha256
        ):
            raise ValueError("review spending scope changed")

    def _issue_reserved(
        self,
        transport: CountedTransport,
        directory: Path,
        container: OfflineContainer,
        timeout: float,
    ) -> BrokeredOpenAIClient:
        """Internal composition: caller owns approval and a fixed one-use path."""
        self.check_current(timeout)
        authorization = self._authorization
        entry = self.ledger_entry
        # Pin the exact hold while committing the exclusive issuance directory.
        # The spending controller rechecks it before any provider operation.
        with self._ledger.guard_held(entry):
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
            self.model_request,
            broker,
            container,
            timeout=timeout,
            response_directory=directory,
        )


class DeferredJudgeAllowance(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["deferred_review_judge"] = "deferred_review_judge"
    brief_sha256: Digest
    spend_policy: SpendPolicy
    ledger_entry_id: Digest
    reserved_microusd: Money
    transfer_authorized: Literal[False] = False

    @model_validator(mode="after")
    def full_allowance(self) -> Self:
        policy = self.spend_policy
        if (
            policy.schema_version != 2
            or self.reserved_microusd
            != policy.reservation_cost(
                policy.max_input_tokens, policy.max_output_tokens
            )
            or self.reserved_microusd > policy.max_cost_microusd
        ):
            raise ValueError("judge allowance must cover the full conservative policy")
        return self

    @property
    def ledger_entry(self) -> LedgerEntry:
        # This is an allowance commitment, deliberately not a provider request.
        return LedgerEntry(
            entry_id=self.ledger_entry_id,
            reservation_sha256=digest(canonical_bytes(self)),
            reserved_microusd=self.reserved_microusd,
        )


class ReviewSpendingEnvelope(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_spending_envelope"] = "review_spending_envelope"
    critics: Annotated[
        tuple[ReviewAuthorization, ...], Field(min_length=1, max_length=8)
    ]
    judge: DeferredJudgeAllowance
    ledger_policy_sha256: Digest
    artifact_directory: Annotated[str, Field(min_length=1, max_length=4096)]
    total_reserved_microusd: Money
    max_total_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    expires_at: datetime

    @model_validator(mode="after")
    def coherent_envelope(self) -> Self:
        first = self.critics[0]
        if any(
            call.role != "critic"
            or call.brief_sha256 != self.judge.brief_sha256
            or call.ledger_policy_sha256 != self.ledger_policy_sha256
            or call.ledger_id != first.ledger_id
            for call in self.critics
        ):
            raise ValueError("review envelope mixes role, brief or spending scopes")
        ids = [call.ledger_entry_id for call in self.critics] + [
            self.judge.ledger_entry_id
        ]
        if len(set(ids)) != len(ids) or len(
            {call.critic_sha256 for call in self.critics}
        ) != len(self.critics):
            raise ValueError("review envelope duplicates a call or critic")
        total = (
            sum(call.reserved_microusd for call in self.critics)
            + self.judge.reserved_microusd
        )
        if self.total_reserved_microusd != total or total > self.max_total_microusd:
            raise ValueError("review envelope exceeds its aggregate spending limit")
        if self.expires_at.tzinfo is None or self.expires_at > min(
            *(call.expires_at for call in self.critics),
            self.judge.spend_policy.valid_until,
        ):
            raise ValueError("review envelope expiry exceeds its approvals or pricing")
        return self


class PreparedReviewEnvelope:
    """Preview all critic transfers and a spend-only allowance for a later judge."""

    def __init__(
        self,
        critics: tuple[PreparedReviewCall, ...],
        judge_policy: SpendPolicy,
        ledger: SpendLedger,
        *,
        max_total_microusd: int,
        directory: Path,
    ) -> None:
        if not 1 <= len(critics) <= 8:
            raise ValueError("review envelope requires one to eight critics")
        judge_policy = SpendPolicy.model_validate_json(canonical_bytes(judge_policy))
        judge_policy.check_current()
        critic_ids: set[str] = set()
        for call in critics:
            call.check_current(30)
            if call.ledger_path != ledger.path.resolve() or call.critic_spec is None:
                raise ValueError("review envelope requires critics on the same ledger")
            critic = call.critic_spec
            assert critic is not None
            if critic.id in critic_ids:
                raise ValueError("review envelope repeats a critic identifier")
            critic_ids.add(critic.id)
        judge = DeferredJudgeAllowance(
            brief_sha256=critics[0].authorization.brief_sha256,
            spend_policy=judge_policy,
            ledger_entry_id=digest(uuid4().bytes),
            reserved_microusd=judge_policy.reservation_cost(
                judge_policy.max_input_tokens, judge_policy.max_output_tokens
            ),
        )
        self._envelope = ReviewSpendingEnvelope(
            critics=tuple(call.authorization for call in critics),
            artifact_directory=str(directory.resolve()),
            judge=judge,
            ledger_policy_sha256=digest(canonical_bytes(ledger.policy)),
            total_reserved_microusd=sum(
                call.authorization.reserved_microusd for call in critics
            )
            + judge.reserved_microusd,
            max_total_microusd=max_total_microusd,
            expires_at=min(
                *(call.authorization.expires_at for call in critics),
                judge_policy.valid_until,
            ),
        )
        snapshot = ledger.snapshot()
        if (
            snapshot.blocked
            or self.envelope.total_reserved_microusd > snapshot.available_microusd
        ):
            raise ValueError("aggregate review allowance is unavailable")
        self._critics = critics
        self._ledger = ledger

    @property
    def ledger(self) -> SpendLedger:
        return self._ledger

    @property
    def critics(self) -> tuple[PreparedReviewCall, ...]:
        return self._critics

    @property
    def envelope(self) -> ReviewSpendingEnvelope:
        return self._envelope

    @property
    def approval_sha256(self) -> str:
        return digest(canonical_bytes(self.envelope))

    def reserve(
        self,
        *,
        approved_envelope_sha256: str,
    ) -> ReservedReviewEnvelope:
        """Burn the complete approval atomically before any grant or token count."""
        if approved_envelope_sha256 != self.approval_sha256:
            raise ValueError("exact aggregate review approval required")
        self.envelope.judge.spend_policy.check_current()
        for call in self._critics:
            call.check_current(30)
        if (
            datetime.now(UTC) >= self.envelope.expires_at
            or digest(canonical_bytes(self._ledger.policy))
            != self.envelope.ledger_policy_sha256
        ):
            raise ValueError("review envelope expired or spending scope changed")
        self._ledger.reserve_many(
            tuple(call.ledger_entry for call in self._critics)
            + (self.envelope.judge.ledger_entry,)
        )
        # Failed local persistence leaves every hold in place, with no dispatch.
        directory = Path(self.envelope.artifact_directory)
        directory.mkdir(mode=0o700)
        private_write(directory / "envelope.json", canonical_bytes(self.envelope))
        return ReservedReviewEnvelope(self)


class ReservedReviewEnvelope:
    """Trusted host handle; fixed child paths make every critic issuance exclusive."""

    def __init__(self, prepared: PreparedReviewEnvelope) -> None:
        self._prepared = prepared
        self._directory = Path(prepared.envelope.artifact_directory)

    def issue_critic(
        self,
        index: int,
        *,
        transport: CountedTransport,
        container: OfflineContainer,
        timeout: float = 30,
    ) -> BrokeredOpenAIClient:
        prepared = self._prepared
        if type(index) is not int or not 0 <= index < len(prepared.critics):
            raise ValueError("critic index is outside the approved envelope")
        if datetime.now(UTC) >= prepared.envelope.expires_at:
            raise ValueError("review envelope expired")
        if read_bounded(self._directory / "envelope.json", 32_768) != canonical_bytes(
            prepared.envelope
        ):
            raise ValueError("retained review envelope changed")
        call = prepared.critics[index]
        # This module's reserved handle is the only composite issuer. Keep the
        # held-reservation entry point private to prevent ordinary callers from
        # bypassing the public single-call reservation/approval path.
        with prepared.ledger.guard_held(prepared.envelope.judge.ledger_entry):
            return call._issue_reserved(  # pyright: ignore[reportPrivateUsage]
                transport,
                self._directory / call.authorization.ledger_entry_id,
                container,
                timeout,
            )


class JudgeTransferAuthorization(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["reserved_review_judge"] = "reserved_review_judge"
    envelope_sha256: Digest
    allowance: LedgerEntry
    call: ReviewAuthorization

    @model_validator(mode="after")
    def coherent_transfer(self) -> Self:
        if (
            self.call.role != "judge"
            or self.call.reserved_microusd != self.allowance.reserved_microusd
            or self.call.ledger_entry_id == self.allowance.entry_id
        ):
            raise ValueError("judge transfer must preserve the exact reserved exposure")
        return self


class PreparedJudgeTransfer:
    """Exact judge transfer preview; finding lineage/quorum remain caller duties."""

    def __init__(
        self,
        envelope: PreparedReviewEnvelope,
        reviewer: ModelReviewer,
        request: JudgeRequest,
    ) -> None:
        self._envelope = envelope
        self._directory = Path(envelope.envelope.artifact_directory)
        self._check_envelope()
        self._call = PreparedReviewCall(
            reviewer,
            request,
            envelope.envelope.judge.spend_policy,
            envelope.ledger,
            reserved_allowance=envelope.envelope.judge,
        )
        self._authorization = JudgeTransferAuthorization(
            envelope_sha256=envelope.approval_sha256,
            allowance=envelope.envelope.judge.ledger_entry,
            call=self._call.authorization,
        )

    @property
    def authorization(self) -> JudgeTransferAuthorization:
        return self._authorization

    @property
    def approval_sha256(self) -> str:
        return digest(canonical_bytes(self._authorization))

    @property
    def model_request(self) -> ModelRequest:
        return self._call.model_request

    def _check_envelope(self) -> None:
        if (
            digest(canonical_bytes(self._envelope.ledger.policy))
            != self._envelope.envelope.ledger_policy_sha256
        ):
            raise ValueError("judge spending scope changed")
        for call in self._envelope.critics:
            status = self._envelope.ledger.entry_status(
                call.authorization.ledger_entry_id
            )
            if (
                status is None
                or status.status == "held"
                or status.reservation_sha256 != call.authorization.reservation_sha256
                or status.reserved_microusd != call.authorization.reserved_microusd
            ):
                raise ValueError(
                    "judge transfer requires terminal critic spending states"
                )
        if datetime.now(UTC) >= self._envelope.envelope.expires_at:
            raise ValueError("review envelope expired")
        if read_bounded(self._directory / "envelope.json", 32_768) != canonical_bytes(
            self._envelope.envelope
        ):
            raise ValueError("retained review envelope changed")

    def issue(
        self,
        *,
        approved_transfer_sha256: str,
        transport: CountedTransport,
        container: OfflineContainer,
        timeout: float = 30,
    ) -> BrokeredOpenAIClient:
        if approved_transfer_sha256 != self.approval_sha256:
            raise ValueError("exact judge transfer approval required")
        self._check_envelope()
        self._call.check_current(timeout)
        ledger = self._envelope.ledger
        ledger.transfer_held(self._authorization.allowance, self._call.ledger_entry)
        # Crash or storage failure after the transfer keeps the new full hold.
        # The old allowance is spent, so no second transfer or grant can issue.
        private_write(
            self._directory / "judge-transfer.json",
            canonical_bytes(self._authorization),
        )
        remaining = (
            self._envelope.envelope.expires_at - datetime.now(UTC)
        ).total_seconds()
        return self._call._issue_reserved(  # pyright: ignore[reportPrivateUsage]
            transport, self._directory / "judge", container, min(timeout, remaining)
        )


def verify_judge_transfer(
    directory: Path,
    expected: JudgeTransferAuthorization,
    ledger: SpendLedger,
) -> BrokerOutcome:
    """Read a completed transfer/audit chain against trusted expected identities."""
    expected = JudgeTransferAuthorization.model_validate_json(canonical_bytes(expected))
    if (
        JudgeTransferAuthorization.model_validate_json(
            read_bounded(directory / "judge-transfer.json", 8192)
        )
        != expected
    ):
        raise ValueError("judge transfer authorization mismatch")
    if (
        digest(read_bounded(directory / "envelope.json", 32_768))
        != expected.envelope_sha256
        or ledger.policy.ledger_id != expected.call.ledger_id
    ):
        raise ValueError("judge transfer envelope or ledger mismatch")
    source = ledger.entry_status(expected.allowance.entry_id)
    target = ledger.entry_status(expected.call.ledger_entry_id)
    if (
        source is None
        or source.reservation_sha256 != expected.allowance.reservation_sha256
        or source.reserved_microusd != expected.allowance.reserved_microusd
        or source.status != "settled"
        or source.charged_microusd != 0
    ):
        raise ValueError("judge allowance was not retired by a transfer")
    if (
        target is None
        or target.reservation_sha256 != expected.call.reservation_sha256
        or target.reserved_microusd != expected.call.reserved_microusd
    ):
        raise ValueError("judge request reservation mismatch")
    return verify_review_broker_audit(directory / "judge", expected.call)


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
