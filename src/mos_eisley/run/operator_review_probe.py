"""Operator-approved, credentialed three-model review without external signers."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    JudgeRequest,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.providers.anthropic_live import EphemeralAnthropicTransport
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_spend import SpendPolicy, spending_request_sha256
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_approval import (
    ApprovalPreview,
    BrokeredReviewApprovalFlow,
    ReviewApprovalUI,
)
from mos_eisley.run.review_broker import (
    PreparedReviewEnvelope,
    review_count_payload,
    review_request_payload,
)
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerCriticPreview,
    ControllerJudgePreview,
)
from mos_eisley.run.review_guidance import ReviewGuidanceAdmission
from mos_eisley.run.review_verdict import RetainedReviewResult


class OperatorReviewIdentity(Contract):
    """Operator-selected author artifact and spending cap, not authorship proof."""

    schema_version: Literal[1] = 1
    mode: Literal["operator_three_model_review"] = "operator_three_model_review"
    author_provider: Identifier
    author_model: Identifier
    author_artifact_sha256: Digest
    max_total_microusd: Annotated[int, Field(gt=0, le=1_000_000)]
    author_identity_operator_declared: Literal[True] = True
    independent_authorization_claimed: Literal[False] = False

    @model_validator(mode="after")
    def valid_author(self) -> Self:
        if not self.author_provider or not self.author_model:
            raise ValueError("operator review requires a selected author model")
        return self


def validate_operator_review_identity(
    identity: OperatorReviewIdentity,
    envelope: PreparedReviewEnvelope,
    reviewer: ModelReviewer,
) -> OperatorReviewIdentity:
    """Bind the operator's three-model declaration to either review executor."""
    identity = OperatorReviewIdentity.model_validate_json(canonical_bytes(identity))
    if (
        envelope.envelope.total_reserved_microusd > identity.max_total_microusd
        or envelope.ledger.policy.ceiling_microusd > identity.max_total_microusd
    ):
        raise ValueError("operator review exceeds the selected spending cap")
    critic_models = {
        (call.model_request.provider, call.model_request.model)
        for call in envelope.critics
    }
    brief = envelope.critics[0].review_request.brief
    if digest(brief.diff.encode()) != identity.author_artifact_sha256 or any(
        call.review_request.brief != brief for call in envelope.critics
    ):
        raise ValueError("operator author artifact differs from review brief")
    judge = reviewer.judge_request(JudgeRequest(brief=brief, findings=()))
    identities = {
        (identity.author_provider, identity.author_model),
        *critic_models,
        (judge.provider, judge.model),
    }
    if (
        len(critic_models) != len(envelope.critics)
        or len(identities) != len(envelope.critics) + 2
        or any(provider != "anthropic" for provider, _ in critic_models)
        or judge.provider != "anthropic"
        or envelope.envelope.judge.spend_policy.provider != "anthropic"
        or envelope.envelope.judge.spend_policy.model != judge.model
    ):
        raise ValueError(
            "operator review requires distinct author, critic and judge models"
        )
    return identity


class OperatorReviewApproval:
    """Keep the exact local approvals in memory for moment-of-use checks."""

    def __init__(self, critic_preview: ControllerCriticPreview, ui: ReviewApprovalUI):
        self._critic_preview = critic_preview
        self._ui = ui
        self._critic: ControllerCriticPreview | None = None
        self._judge: ControllerJudgePreview | None = None

    async def approve(self, preview: ApprovalPreview) -> str | None:
        if isinstance(preview, ControllerCriticPreview):
            if preview != self._critic_preview or self._critic is not None:
                raise ValueError("operator critic preview changed")
        elif self._critic is None or self._judge is not None:
            raise ValueError("operator judge approval is out of order")
        answer = await self._ui.approve(preview)
        if answer == preview.sha256:
            if isinstance(preview, ControllerCriticPreview):
                self._critic = preview
            else:
                self._judge = preview
        return answer

    def approved_request(
        self, phase: Literal["critics", "judge"], index: int
    ) -> tuple[ControllerCriticPreview | ControllerJudgePreview, int]:
        if phase == "critics":
            if self._critic is None:
                raise ValueError("operator critic phase lacks local approval")
            if not 0 <= index < len(self._critic.requests):
                raise ValueError("operator critic index is invalid")
            return self._critic, index
        if self._judge is None:
            raise ValueError("operator judge phase lacks local approval")
        return self._judge, 0

    async def show_result(self, result: RetainedReviewResult) -> None:
        await self._ui.show_result(result)


class _OperatorAnthropicTransport:
    def __init__(
        self,
        controller: BrokeredReviewController,
        approval: OperatorReviewApproval,
        guidance: ReviewGuidanceAdmission,
        spending: SpendPolicy,
        load_api_key: Callable[[], str],
        container: OfflineContainer,
        image_id: str,
        *,
        phase: Literal["critics", "judge"],
        index: int = 0,
    ) -> None:
        self._controller = controller
        self._approval = approval
        self._guidance = guidance
        self._spending = spending
        self._key = load_api_key
        self._container = container
        self._image_id = image_id
        self._phase: Literal["critics", "judge"] = phase
        self._index = index
        self._count_used = False
        self._count_succeeded = False
        self._response_used = False

    def _check(self, payload: dict[str, JsonValue], *, count: bool) -> float:
        preview, index = self._approval.approved_request(self._phase, self._index)
        expected_phase = (
            "critics_running" if self._phase == "critics" else "judge_running"
        )
        if self._controller.phase != expected_phase:
            raise ValueError("operator review is outside its approved phase")
        start = self._controller.start
        if start is None:
            raise ValueError("operator review has no controller start")
        request = (
            preview.requests[index]
            if isinstance(preview, ControllerCriticPreview)
            else preview.model_request
        )
        if (
            request.provider != "anthropic"
            or self._spending.provider != "anthropic"
            or self._spending.model != request.model
            or self._container.image_id != self._image_id
        ):
            raise ValueError("operator Anthropic model selection changed")
        self._guidance.check()
        self._spending.check_current()
        expected = (
            review_count_payload(request) if count else review_request_payload(request)
        )
        if spending_request_sha256(payload) != spending_request_sha256(expected):
            raise ValueError("operator review payload differs from local approval")
        remaining = min(
            60.0,
            (start.expires_at - datetime.now(UTC)).total_seconds(),
            (self._spending.valid_until - datetime.now(UTC)).total_seconds(),
        )
        if remaining <= 0:
            raise ValueError("operator review approval expired")
        return remaining

    def _transport(
        self, payload: dict[str, JsonValue], *, count: bool
    ) -> tuple[EphemeralAnthropicTransport, float]:
        self._check(payload, count=count)
        key = self._key()
        remaining = self._check(payload, count=count)
        return EphemeralAnthropicTransport(key, remaining), remaining

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        if self._count_used:
            raise ValueError("operator review token count is consumed")
        self._count_used = True
        payload = copy.deepcopy(payload)
        transport, remaining = self._transport(payload, count=True)
        async with asyncio.timeout(remaining):
            result = await transport.count_input_tokens(payload)
        self._check(payload, count=True)
        self._count_succeeded = True
        return result

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if not self._count_succeeded or self._response_used:
            raise ValueError("operator review generation is unavailable or consumed")
        self._response_used = True
        payload = copy.deepcopy(payload)
        transport, remaining = self._transport(payload, count=False)
        async with asyncio.timeout(remaining):
            result = await transport.create_response(payload)
        self._check(payload, count=False)
        return result


class OperatorReviewProbe:
    """One live critic/judge run with exact local approval at both phases."""

    def __init__(
        self,
        identity: OperatorReviewIdentity,
        envelope: PreparedReviewEnvelope,
        reviewer: ModelReviewer,
        policy: ReviewPolicy,
        ui: ReviewApprovalUI,
        *,
        critic_containers: tuple[OfflineContainer, ...],
        judge_container: OfflineContainer,
        load_api_key: Callable[[], str],
        total_seconds: float = 120,
    ) -> None:
        identity = validate_operator_review_identity(identity, envelope, reviewer)
        if len(critic_containers) != len(envelope.critics) or len(
            {id(container) for container in critic_containers}
        ) != len(critic_containers):
            raise ValueError("operator review requires a distinct worker per critic")
        images = {
            container.image_id for container in (*critic_containers, judge_container)
        }
        if len(images) != 1:
            raise ValueError("operator review requires one pinned worker image")
        first = envelope.critics[0]
        guidance = first.guidance
        if guidance is None:
            raise ValueError("operator review requires current shared guidance")
        if any(
            call.guidance is None
            or call.guidance.prepared.sha256 != guidance.prepared.sha256
            for call in envelope.critics
        ):
            raise ValueError("operator critics require the same current guidance")
        self.identity = identity
        self.controller = BrokeredReviewController(
            envelope, reviewer, policy, total_seconds=total_seconds
        )
        self.approval = OperatorReviewApproval(self.controller.preview, ui)
        self._flow = BrokeredReviewApprovalFlow(self.controller, self.approval)
        self._critics = tuple(
            _OperatorAnthropicTransport(
                self.controller,
                self.approval,
                guidance,
                call.spend_policy,
                load_api_key,
                critic_containers[index],
                next(iter(images)),
                phase="critics",
                index=index,
            )
            for index, call in enumerate(envelope.critics)
        )
        self._judge = _OperatorAnthropicTransport(
            self.controller,
            self.approval,
            guidance,
            envelope.envelope.judge.spend_policy,
            load_api_key,
            judge_container,
            next(iter(images)),
            phase="judge",
        )
        self._critic_containers = critic_containers
        self._judge_container = judge_container

    @property
    def judge_preview(self) -> ControllerJudgePreview | None:
        return self._flow.judge_preview

    async def run(self) -> RetainedReviewResult | None:
        return await self._flow.run(
            critic_transports=self._critics,
            critic_containers=self._critic_containers,
            judge_transport=self._judge,
            judge_container=self._judge_container,
        )
