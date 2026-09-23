"""One-use brokered review with a separate evidence-bound judge approval pause."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    CriticSpec,
    Digest,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest
from mos_eisley.providers.brokered_openai import BrokeredOpenAIClient
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_spend import CountedTransport
from mos_eisley.review.pipeline import validate_roster
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import MAX_WIRE_BYTES
from mos_eisley.run.review_broker import PreparedReviewEnvelope, ReviewSpendingEnvelope
from mos_eisley.run.review_campaign_binding import ReviewCampaignBinding
from mos_eisley.run.review_evidence import (
    EvidenceJudgeAuthorization,
    PreparedEvidenceJudgeTransfer,
    ReviewEvidence,
)
from mos_eisley.run.review_verdict import RetainedReviewResult, retain_review_result
from mos_eisley.run.store import private_write

Phase = Literal[
    "prepared",
    "critics_running",
    "awaiting_judge",
    "judge_running",
    "finished",
    "failed",
    "cancelled",
]

FORMAL_JUDGE_APPROVAL_SECONDS = 600.0


def review_exchange_timeout(
    policy_timeout_seconds: float, remaining_seconds: float
) -> float:
    """Derive one count-plus-generation lifecycle from per-operation policy."""
    return min(min(policy_timeout_seconds, 60.0) * 2, remaining_seconds)


class ControllerAuthorization(Contract):
    schema_version: Literal[1, 2] = 1
    mode: Literal["brokered_review_controller"] = "brokered_review_controller"
    envelope_sha256: Digest
    policy: ReviewPolicy
    total_seconds: Annotated[float, Field(gt=0, le=600)]
    judge_approval_seconds: Annotated[float, Field(ge=0, le=600)] = Field(
        default=0, exclude_if=lambda value: value == 0
    )

    @model_validator(mode="after")
    def scoped_judge_approval(self) -> Self:
        if self.schema_version == 2:
            if self.judge_approval_seconds != FORMAL_JUDGE_APPROVAL_SECONDS:
                raise ValueError("controller schema 2 requires the formal grace")
        elif self.judge_approval_seconds != 0:
            raise ValueError("judge approval grace requires controller schema 2")
        return self


class ControllerCriticPreview(Contract):
    authorization: ControllerAuthorization
    envelope: ReviewSpendingEnvelope
    requests: Annotated[tuple[ModelRequest, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def exact_requests(self) -> Self:
        formal_campaign = self.envelope.judge.preparation_scope == "formal_campaign"
        if (
            digest(canonical_bytes(self.envelope)) != self.authorization.envelope_sha256
            or (self.authorization.schema_version == 2) != formal_campaign
            or len(self.requests) != len(self.envelope.critics)
            or any(
                digest(canonical_bytes(request)) != call.model_request_sha256
                for request, call in zip(
                    self.requests, self.envelope.critics, strict=True
                )
            )
            or len(canonical_bytes(self)) > MAX_WIRE_BYTES
        ):
            raise ValueError(
                "critic preview differs from approved envelope or byte limit"
            )
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self.authorization))


class ControllerStart(Contract):
    schema_version: Literal[1, 2] = 1
    authorization: ControllerAuthorization
    started_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def matching_schema(self) -> Self:
        if self.schema_version != self.authorization.schema_version:
            raise ValueError("controller start and authorization schemas differ")
        return self


class ControllerJudgePreview(Contract):
    schema_version: Literal[1] = 1
    controller_sha256: Digest
    evidence: ReviewEvidence
    authorization: EvidenceJudgeAuthorization
    model_request: ModelRequest

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class ControllerTerminal(Contract):
    schema_version: Literal[1, 2] = 1
    controller_sha256: Digest
    phase: Literal["finished", "failed", "cancelled"]
    result_sha256: Digest | None = None
    unused_judge_allowance_retired: bool = Field(
        default=False, exclude_if=lambda value: value is False
    )

    @model_validator(mode="after")
    def cleanup_schema(self) -> Self:
        if self.unused_judge_allowance_retired != (self.schema_version == 2):
            raise ValueError("terminal cleanup marker requires schema 2")
        return self


async def _complete(client: BrokeredOpenAIClient, request: ModelRequest) -> None:
    await client.complete(request)


async def _complete_all(
    jobs: tuple[tuple[BrokeredOpenAIClient, ModelRequest], ...],
) -> None:
    tasks = [asyncio.create_task(_complete(*job)) for job in jobs]
    group = asyncio.gather(*tasks, return_exceptions=True)
    try:
        outcomes = await asyncio.shield(group)
    except BaseException:
        for task in tasks:
            task.cancel()
        # Retain ownership until every child's broker and spending cleanup finishes.
        # Repeated caller cancellation must not detach that cleanup.
        while not group.done():
            try:
                await asyncio.shield(group)
            except asyncio.CancelledError:
                continue
        raise
    if any(
        outcome is not None
        and not isinstance(outcome, (ProviderError, asyncio.CancelledError))
        for outcome in outcomes
    ):
        raise ValueError("Review child did not finish its broker lifecycle.")
    # Complete recorded failures are assessed by evidence/quorum reconstruction.


class BrokeredReviewController:
    """Trusted host composition; no credential loading, implicit approval or retry."""

    def __init__(
        self,
        envelope: PreparedReviewEnvelope,
        reviewer: ModelReviewer,
        policy: ReviewPolicy | None = None,
        *,
        total_seconds: float = 120,
        campaign: ReviewCampaignBinding | None = None,
    ) -> None:
        selected = ReviewPolicy.model_validate_json(
            canonical_bytes(policy if policy is not None else ReviewPolicy())
        )
        roster: list[CriticSpec] = []
        for call in envelope.critics:
            critic = call.critic_spec
            request = call.review_request
            if critic is None or not isinstance(request, CriticRequest):
                raise ValueError("Controller envelope must contain only critics.")
            if (
                reviewer.critic_request(critic, request) != call.model_request
                or len(canonical_bytes(request)) > selected.max_request_bytes
            ):
                raise ValueError("Controller critic projection or byte budget changed.")
            roster.append(critic)
        validate_roster(tuple(roster), selected)
        self._authorization = ControllerAuthorization(
            schema_version=(
                2
                if envelope.envelope.judge.preparation_scope == "formal_campaign"
                else 1
            ),
            envelope_sha256=envelope.approval_sha256,
            policy=selected,
            total_seconds=total_seconds,
            judge_approval_seconds=(
                FORMAL_JUDGE_APPROVAL_SECONDS
                if envelope.envelope.judge.preparation_scope == "formal_campaign"
                else 0
            ),
        )
        self._envelope = envelope
        self._campaign_binding = (
            None
            if campaign is None
            else ReviewCampaignBinding.model_validate_json(canonical_bytes(campaign))
        )
        self._reviewer = reviewer
        self._directory = Path(envelope.envelope.artifact_directory)
        self._phase: Phase = "prepared"
        self._owns_run = False
        self._start: ControllerStart | None = None
        self._deadline: float | None = None
        self._execution_remaining: float | None = None
        self._judge: PreparedEvidenceJudgeTransfer | None = None
        self._preview: ControllerJudgePreview | None = None

    @property
    def authorization(self) -> ControllerAuthorization:
        return self._authorization

    @property
    def approval_sha256(self) -> str:
        return digest(canonical_bytes(self.authorization))

    @property
    def preview(self) -> ControllerCriticPreview:
        """Exact critic content and aggregate limits for a trusted host approval UI."""
        return ControllerCriticPreview(
            authorization=self.authorization,
            envelope=self._envelope.envelope,
            requests=tuple(call.model_request for call in self._envelope.critics),
        )

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def start(self) -> ControllerStart | None:
        """Trusted start binding for independent retention by the owning host."""
        return self._start

    @property
    def campaign_binding(self) -> ReviewCampaignBinding | None:
        """Frozen sealed-slot selection; absent controllers cannot retire allowance."""
        return self._campaign_binding

    def _cleanup_admitted(self) -> bool:
        """Recheck the exact seal and slot before granting cleanup authority."""
        binding = self._campaign_binding
        if binding is None:
            return False
        try:
            # Local import avoids a module cycle: campaign contracts contain
            # controller previews, while cleanup validates a completed commitment.
            from mos_eisley.run.review_campaign import read_campaign_seal

            bundle, seal = read_campaign_seal(
                Path(binding.campaign_directory), binding.expected_seal_sha256
            )
            attempt = bundle.attempts[binding.attempt_index]
            valid_until = min(
                bundle.policy.valid_until,
                attempt.observation_policy.valid_until,
                attempt.authority_policy.valid_until,
                attempt.preview.envelope.expires_at,
            )
            if (
                canonical_bytes(attempt.preview) != canonical_bytes(self.preview)
                or attempt.preview.envelope.judge.preparation_scope != "formal_campaign"
                or Path(attempt.ledger_path).resolve()
                != self._envelope.ledger.path.resolve()
                or any(
                    call.ledger_path != self._envelope.ledger.path.resolve()
                    for call in self._envelope.critics
                )
                or digest(canonical_bytes(self._envelope.ledger.policy))
                != attempt.preview.envelope.ledger_policy_sha256
            ):
                return False
            return (
                self._start is not None
                and seal.sealed_at <= self._start.started_at < valid_until
            )
        except (IndexError, OSError, ValueError):
            return False

    def cancel(self) -> None:
        """Stop an idle controller; active callers cancel and await their coroutine."""
        if self._phase not in {"prepared", "awaiting_judge"}:
            raise ValueError("Cancel active review work through its owning task.")
        self._terminal("cancelled")

    def _remaining(self) -> float:
        assert self._deadline is not None
        remaining = self._deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("Review controller deadline expired.")
        return remaining

    def _exchange_timeout(self) -> float:
        """Bound count and generation separately inside one broker lifecycle."""
        return review_exchange_timeout(
            self.authorization.policy.timeout_seconds, self._remaining()
        )

    def _terminal(
        self,
        phase: Literal["finished", "failed", "cancelled"],
        result: RetainedReviewResult | None = None,
    ) -> None:
        self._phase = phase
        if not self._owns_run:
            return
        retired = False
        if self.authorization.schema_version == 2 and self._cleanup_admitted():
            retired = self._envelope.retire_unused_judge_allowance()
        private_write(
            self._directory / "controller-terminal.json",
            canonical_bytes(
                ControllerTerminal(
                    schema_version=2 if retired else 1,
                    controller_sha256=self.approval_sha256,
                    phase=phase,
                    result_sha256=None
                    if result is None
                    else digest(canonical_bytes(result)),
                    unused_judge_allowance_retired=retired,
                )
            ),
        )

    async def run_critics(
        self,
        *,
        approved_controller_sha256: str,
        transports: tuple[CountedTransport, ...],
        containers: tuple[OfflineContainer, ...],
    ) -> ControllerJudgePreview:
        if self._phase != "prepared":
            raise ValueError("Controller critic attempt already consumed.")
        if approved_controller_sha256 != self.approval_sha256:
            raise ValueError(
                "Exact controller transfer and spending approval required."
            )
        if len(transports) != len(self._envelope.critics):
            raise ValueError("Each approved critic requires one host transport.")
        if len(containers) != len(transports) or len(
            {id(c) for c in containers}
        ) != len(containers):
            raise ValueError("Each critic requires a distinct container instance.")
        self._phase = "critics_running"
        now = datetime.now(UTC)
        expires = min(
            now
            + timedelta(
                seconds=(
                    self.authorization.total_seconds
                    + self.authorization.judge_approval_seconds
                )
            ),
            self._envelope.envelope.expires_at,
        )
        self._deadline = asyncio.get_running_loop().time() + min(
            self.authorization.total_seconds,
            (self._envelope.envelope.expires_at - now).total_seconds(),
        )
        try:
            self._remaining()
            reserved = self._envelope.reserve(
                approved_envelope_sha256=self._envelope.approval_sha256
            )
            self._owns_run = True
            self._start = ControllerStart(
                schema_version=(
                    2 if self.authorization.judge_approval_seconds > 0 else 1
                ),
                authorization=self.authorization,
                started_at=now,
                expires_at=expires,
            )
            private_write(
                self._directory / "controller-start.json",
                canonical_bytes(self._start),
            )
            async with asyncio.timeout(self._remaining()):
                jobs = tuple(
                    (
                        reserved.issue_critic(
                            index,
                            transport=transport,
                            container=containers[index],
                            timeout=self._exchange_timeout(),
                        ),
                        self._envelope.critics[index].model_request,
                    )
                    for index, transport in enumerate(transports)
                )
                await _complete_all(jobs)
                self._judge = PreparedEvidenceJudgeTransfer(
                    self._envelope, self._reviewer, self.authorization.policy
                )
                self._preview = ControllerJudgePreview(
                    controller_sha256=self.approval_sha256,
                    evidence=self._judge.evidence,
                    authorization=self._judge.authorization,
                    model_request=self._judge.model_request,
                )
                raw = canonical_bytes(self._preview)
                if len(raw) > MAX_WIRE_BYTES:
                    raise ValueError(
                        "Controller judge preview exceeds its byte budget."
                    )
                self._remaining()
                private_write(self._directory / "controller-judge-preview.json", raw)
            if self.authorization.judge_approval_seconds > 0:
                self._execution_remaining = self._remaining()
                self._deadline = None
            self._phase = "awaiting_judge"
            return self._preview
        except BaseException as error:
            with suppress(OSError, ValueError):
                self._terminal(
                    "cancelled"
                    if isinstance(error, asyncio.CancelledError)
                    else "failed"
                )
            raise

    async def run_judge(
        self,
        *,
        approved_preview_sha256: str,
        transport: CountedTransport,
        container: OfflineContainer,
    ) -> RetainedReviewResult:
        if self._phase != "awaiting_judge":
            raise ValueError("Controller is not awaiting judge approval.")
        assert self._preview is not None and self._judge is not None
        if approved_preview_sha256 != self._preview.sha256:
            raise ValueError("Exact controller judge preview approval required.")
        self._phase = "judge_running"
        try:
            assert self._start is not None
            if self.authorization.judge_approval_seconds > 0:
                assert self._execution_remaining is not None
                hard_remaining = (
                    self._start.expires_at - datetime.now(UTC)
                ).total_seconds()
                if hard_remaining <= 0:
                    raise TimeoutError("Review controller deadline expired.")
                self._deadline = asyncio.get_running_loop().time() + min(
                    self._execution_remaining, hard_remaining
                )
            if read_bounded(
                self._directory / "controller-start.json", 8192
            ) != canonical_bytes(self._start):
                raise ValueError("Retained controller start changed.")
            if read_bounded(
                self._directory / "controller-judge-preview.json", MAX_WIRE_BYTES
            ) != canonical_bytes(self._preview):
                raise ValueError("Retained controller judge preview changed.")
            async with asyncio.timeout(self._remaining()):
                client = self._judge.issue(
                    approved_evidence_sha256=self._judge.approval_sha256,
                    transport=transport,
                    container=container,
                    timeout=self._exchange_timeout(),
                )
                await _complete_all(((client, self._judge.model_request),))
                for call in self._envelope.critics:
                    if call.guidance is not None:
                        call.guidance.check()
                self._remaining()
                result = retain_review_result(
                    self._envelope.envelope,
                    self._reviewer,
                    self._envelope.ledger,
                    self._judge.authorization,
                )
                self._terminal("finished", result)
            return result
        except BaseException as error:
            with suppress(OSError, ValueError):
                self._terminal(
                    "cancelled"
                    if isinstance(error, asyncio.CancelledError)
                    else "failed"
                )
            raise
