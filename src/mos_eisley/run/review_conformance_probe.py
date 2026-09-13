"""One owned review probe with signed admission at credential and provider use."""

import asyncio
import copy
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from mos_eisley.core.models import ReviewPolicy, canonical_bytes
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.providers.openai_responses import request_payload
from mos_eisley.providers.openai_spend import count_payload, spending_request_sha256
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_approval import BrokeredReviewApprovalFlow, ReviewApprovalUI
from mos_eisley.run.review_broker import PreparedReviewEnvelope
from mos_eisley.run.review_campaign_dispatch import (
    ReviewCampaignAdmission,
    ReviewCampaignBinding,
)
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
from mos_eisley.run.review_runtime_evidence import RuntimeOperationRecorder
from mos_eisley.run.review_verdict import RetainedReviewResult


class _ApprovedReviewTransport:
    """One count and one generation; every attempt consumes its local operation."""

    def __init__(
        self,
        ui: SignedReviewApprovalUI,
        controller: BrokeredReviewController,
        guidance: ReviewGuidanceAdmission,
        load_api_key: Callable[[], str],
        container: OfflineContainer,
        directory: Path,
        *,
        phase: Literal["critics", "judge"],
        index: int = 0,
        campaign_deadline: datetime | None = None,
    ) -> None:
        self._ui = ui
        self._controller = controller
        self._guidance = guidance
        self._key = load_api_key
        self._container = container
        self._directory = directory
        self.lifecycle_path: Path | None = None
        self._phase: Literal["critics", "judge"] = phase
        self._index = index
        self._campaign_deadline = campaign_deadline
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
        if self._campaign_deadline is not None:
            remaining = min(
                remaining,
                (self._campaign_deadline - datetime.now(UTC)).total_seconds(),
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

    def _record(
        self, payload: dict[str, JsonValue], *, count: bool
    ) -> RuntimeOperationRecorder:
        preview, authorization = self._ui.approved_phase(self._phase)
        request = (
            preview.requests[self._index]
            if isinstance(preview, ControllerCriticPreview)
            else preview.model_request
        )
        recorder = RuntimeOperationRecorder(
            self._directory,
            "count" if count else "generation",
            request,
            authorization,
            payload,
            self._container,
        )
        self.lifecycle_path = self._container.lifecycle_path
        return recorder

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        if self._count_used:
            raise ValueError("review conformance token count is already consumed")
        self._count_used = True
        payload = copy.deepcopy(payload)
        transport, remaining = self._transport(payload, count=True)
        recorder = self._record(payload, count=True)
        try:
            remaining = self._check(payload, count=True)
            async with asyncio.timeout(remaining):
                result = await transport.count_input_tokens(payload)
            self._check(payload, count=True)
        except BaseException as error:
            with suppress(OSError, ValueError):
                recorder.finish(error)
            raise
        recorder.finish(result)
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
        recorder = self._record(payload, count=False)
        try:
            remaining = self._check(payload, count=False)
            async with asyncio.timeout(remaining):
                result = await transport.create_response(payload)
            self._check(payload, count=False)
        except BaseException as error:
            with suppress(OSError, ValueError):
                recorder.finish(error)
            raise
        recorder.finish(result)
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
        campaign: ReviewCampaignBinding | None = None,
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
        self._campaign_binding = (
            None
            if campaign is None
            else ReviewCampaignBinding.model_validate_json(canonical_bytes(campaign))
        )
        campaign_admission = (
            None
            if self._campaign_binding is None
            else ReviewCampaignAdmission(
                self._campaign_binding,
                self.controller,
                envelope,
                reviewer,
                authority_policy=authority_policy,
                runtime=self._runtime,
            )
        )
        campaign_deadline = (
            None if campaign_admission is None else campaign_admission.expires_at
        )
        self.approval_ui = SignedReviewApprovalUI(
            self.controller.preview,
            ui,
            authority_policy=authority_policy,
            runtime=self._runtime,
            controller_start=lambda: self.controller.start,
            load_authorization=load_authorization,
            campaign=campaign_admission,
        )
        self._flow = BrokeredReviewApprovalFlow(self.controller, self.approval_ui)
        self._critics = tuple(
            _ApprovedReviewTransport(
                self.approval_ui,
                self.controller,
                guidance,
                load_api_key,
                critic_containers[index],
                Path(envelope.envelope.artifact_directory)
                / envelope.critics[index].authorization.ledger_entry_id,
                phase="critics",
                index=index,
                campaign_deadline=campaign_deadline,
            )
            for index in range(len(critic_containers))
        )
        self._judge = _ApprovedReviewTransport(
            self.approval_ui,
            self.controller,
            guidance,
            load_api_key,
            judge_container,
            Path(envelope.envelope.artifact_directory) / "judge",
            phase="judge",
            campaign_deadline=campaign_deadline,
        )

    def _runtime(self) -> ReviewConformanceRuntime:
        images = {container.image_id for container in self._containers}
        if len(images) != 1:
            raise ValueError("review conformance workers require the same pinned image")
        return ReviewConformanceRuntime(
            sdk_version=version("openai"), image_id=next(iter(images))
        )

    @property
    def campaign_binding(self) -> ReviewCampaignBinding | None:
        """Frozen host selection, not evidence of approval or execution."""
        return self._campaign_binding

    @property
    def judge_preview(self) -> ControllerJudgePreview | None:
        return self._flow.judge_preview

    @property
    def lifecycle_paths(self) -> tuple[Path | None, ...]:
        """Captured worker paths in critic/judge order; unavailable paths stay None."""
        return tuple(
            transport.lifecycle_path for transport in (*self._critics, self._judge)
        )

    async def run(self) -> RetainedReviewResult | None:
        return await self._flow.run(
            critic_transports=self._critics,
            critic_containers=self._containers[:-1],
            judge_transport=self._judge,
            judge_container=self._containers[-1],
        )
