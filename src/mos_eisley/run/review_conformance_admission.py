"""Require independent phase signatures in addition to the local review prompts."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from mos_eisley.core.models import Contract, Identifier, canonical_bytes
from mos_eisley.run.review_approval import ApprovalPreview, ReviewApprovalUI
from mos_eisley.run.review_conformance_authorization import (
    ImageID,
    ReviewConformanceAuthorityPolicy,
    ReviewConformanceScope,
    SignedReviewConformanceAuthorization,
    review_conformance_scope,
    verify_review_conformance_authorization,
)
from mos_eisley.run.review_controller import ControllerCriticPreview, ControllerStart
from mos_eisley.run.review_verdict import RetainedReviewResult


class ReviewConformanceRuntime(Contract):
    sdk_version: Identifier
    image_id: ImageID


def _now() -> datetime:
    return datetime.now(UTC)


class SignedReviewApprovalUI:
    """Trusted host adapter; no credentials, automatic signatures or dispatch.

    Readers select current authority policy and runtime bindings outside stored
    artifacts. The executor must recheck authorization at credential/provider use.
    """

    def __init__(
        self,
        critics: ControllerCriticPreview,
        ui: ReviewApprovalUI,
        *,
        authority_policy: Callable[[], ReviewConformanceAuthorityPolicy],
        runtime: Callable[[], ReviewConformanceRuntime],
        controller_start: Callable[[], ControllerStart | None],
        load_authorization: Callable[
            [ReviewConformanceScope],
            Awaitable[SignedReviewConformanceAuthorization | None],
        ],
        now: Callable[[], datetime] = _now,
    ):
        self._critics = ControllerCriticPreview.model_validate_json(
            canonical_bytes(critics)
        )
        self._ui = ui
        self._policy = authority_policy
        self._runtime = runtime
        self._start = controller_start
        self._load = load_authorization
        self._now = now
        self._authorizations: list[SignedReviewConformanceAuthorization] = []

    @property
    def authorizations(self) -> tuple[SignedReviewConformanceAuthorization, ...]:
        """Verified host outputs, not evidence that a provider call occurred."""
        return tuple(self._authorizations)

    def _scope(self, preview: ApprovalPreview) -> ReviewConformanceScope:
        runtime = self._runtime()
        if isinstance(preview, ControllerCriticPreview):
            if canonical_bytes(preview) != canonical_bytes(self._critics):
                raise ValueError("conformance UI received a different critic preview")
            judge = None
        else:
            judge = preview
        return review_conformance_scope(
            self._critics,
            sdk_version=runtime.sdk_version,
            image_id=runtime.image_id,
            judge=judge,
            start=self._start(),
        )

    async def approve(self, preview: ApprovalPreview) -> str | None:
        scope = self._scope(preview)
        signed = await self._load(scope)
        if signed is None:
            return None
        verify_review_conformance_authorization(
            signed, self._policy(), self._scope(preview), self._now()
        )
        answer = await self._ui.approve(preview)
        if answer is None:
            return None
        verify_review_conformance_authorization(
            signed, self._policy(), self._scope(preview), self._now()
        )
        if answer == preview.sha256:
            self._authorizations.append(signed)
        return answer

    async def show_result(self, result: RetainedReviewResult) -> None:
        await self._ui.show_result(result)
