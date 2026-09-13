"""One owned review probe with signed admission at credential and provider use."""

import asyncio
import copy
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Literal

from pydantic import JsonValue

from mos_eisley.core.models import ReviewPolicy
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.providers.openai_responses import request_payload
from mos_eisley.providers.openai_spend import count_payload, spending_request_sha256
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_approval import BrokeredReviewApprovalFlow, ReviewApprovalUI
from mos_eisley.run.review_broker import PreparedReviewEnvelope
from mos_eisley.run.review_conformance_admission import (
    ReviewConformanceRuntime,
    SignedReviewApprovalUI,
)
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    ReviewConformanceScope,
    SignedReviewConformanceAuthorization,
)
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerCriticPreview,
    ControllerJudgePreview,
)
from mos_eisley.run.review_guidance import ReviewGuidanceAdmission
from mos_eisley.run.review_verdict import RetainedReviewResult


class _ApprovedReviewTransport:
    """One count and one generation; every attempt consumes its local operation."""

    def __init__(
        self,
        ui: SignedReviewApprovalUI,
        controller: BrokeredReviewController,
        guidance: ReviewGuidanceAdmission,
        load_api_key: Callable[[], str],
        *,
        phase: Literal["critics", "judge"],
        index: int = 0,
    ) -> None:
        self._ui = ui
        self._controller = controller
        self._guidance = guidance
        self._key = load_api_key
        self._phase: Literal["critics", "judge"] = phase
        self._index = index
        self._count_used = False
        self._count_succeeded = False
        self._response_used = False

    def _check(self, payload: dict[str, JsonValue], *, count: bool) -> float:
        preview, authorization = self._ui.approved_phase(self._phase)
        expected_phase = (
            "critics_running" if self._phase == "critics" else "judge_running"
        )
        if self._controller.phase != expected_phase:
            raise ValueError(
                "review conformance controller is outside its active phase"
            )
        start = self._controller.start
        if start is None:
            raise ValueError("review conformance controller has no trusted start")
        if isinstance(preview, ControllerCriticPreview):
            request = preview.requests[self._index]
        else:
            request = preview.model_request
        if self._guidance.prepared.sha256 != authorization.scope.guidance_sha256:
            raise ValueError("review conformance guidance binding changed")
        self._guidance.check()
        expected = request_payload(request)
        expected["service_tier"] = "default"
        if spending_request_sha256(payload) != spending_request_sha256(
            count_payload(expected) if count else expected
        ):
            raise ValueError(
                "review conformance provider payload differs from approval"
            )
        remaining = min(
            60.0,
            (authorization.valid_until - datetime.now(UTC)).total_seconds(),
            (start.expires_at - datetime.now(UTC)).total_seconds(),
        )
        if remaining <= 0:
            raise ValueError("review conformance dispatch authorization expired")
        return remaining

    def _transport(
        self, payload: dict[str, JsonValue], *, count: bool
    ) -> tuple[EphemeralOpenAITransport, float]:
        self._check(payload, count=count)
        # The trusted synchronous loader runs only after signature, local consent,
        # current guidance, runtime and exact-payload checks. It may itself revoke
        # policy, so recheck before constructing any credentialed SDK transport.
        key = self._key()
        remaining = self._check(payload, count=count)
        return EphemeralOpenAITransport(key, remaining), remaining

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        if self._count_used:
            raise ValueError("review conformance token count is already consumed")
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
            raise ValueError("review conformance generation is unavailable or consumed")
        self._response_used = True
        payload = copy.deepcopy(payload)
        transport, remaining = self._transport(payload, count=False)
        async with asyncio.timeout(remaining):
            result = await transport.create_response(payload)
        self._check(payload, count=False)
        return result


class BrokeredReviewConformanceProbe:
    """Paid-capable library composition; construction never reads credentials.

    A successful retained verdict is not authenticated provider conformance.
    The owning caller must await run(), including cancellation cleanup.
    """

    def __init__(
        self,
        envelope: PreparedReviewEnvelope,
        reviewer: ModelReviewer,
        policy: ReviewPolicy,
        ui: ReviewApprovalUI,
        *,
        critic_containers: tuple[OfflineContainer, ...],
        judge_container: OfflineContainer,
        authority_policy: Callable[[], ReviewConformanceAuthorityPolicy],
        load_authorization: Callable[
            [ReviewConformanceScope],
            Awaitable[SignedReviewConformanceAuthorization | None],
        ],
        load_api_key: Callable[[], str],
        total_seconds: float = 30,
    ) -> None:
        if len(critic_containers) != len(envelope.critics) or len(
            {id(container) for container in critic_containers}
        ) != len(critic_containers):
            raise ValueError("review probe requires a distinct worker for every critic")
        guidance = envelope.critics[0].guidance
        if guidance is None:
            raise ValueError("review conformance probe requires current guidance")
        self._containers = (*critic_containers, judge_container)
        self._runtime()  # Validate immutable image agreement before any prompt.
        self.controller = BrokeredReviewController(
            envelope, reviewer, policy, total_seconds=total_seconds
        )
        self.approval_ui = SignedReviewApprovalUI(
            self.controller.preview,
            ui,
            authority_policy=authority_policy,
            runtime=self._runtime,
            controller_start=lambda: self.controller.start,
            load_authorization=load_authorization,
        )
        self._flow = BrokeredReviewApprovalFlow(self.controller, self.approval_ui)
        self._critics = tuple(
            _ApprovedReviewTransport(
                self.approval_ui,
                self.controller,
                guidance,
                load_api_key,
                phase="critics",
                index=index,
            )
            for index in range(len(critic_containers))
        )
        self._judge = _ApprovedReviewTransport(
            self.approval_ui,
            self.controller,
            guidance,
            load_api_key,
            phase="judge",
        )

    def _runtime(self) -> ReviewConformanceRuntime:
        images = {container.image_id for container in self._containers}
        if len(images) != 1:
            raise ValueError("review conformance workers require the same pinned image")
        return ReviewConformanceRuntime(
            sdk_version=version("openai"), image_id=next(iter(images))
        )

    @property
    def judge_preview(self) -> ControllerJudgePreview | None:
        return self._flow.judge_preview

    async def run(self) -> RetainedReviewResult | None:
        return await self._flow.run(
            critic_transports=self._critics,
            critic_containers=self._containers[:-1],
            judge_transport=self._judge,
            judge_container=self._containers[-1],
        )
