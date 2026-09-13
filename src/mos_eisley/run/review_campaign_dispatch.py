"""Bind an owned probe to an independently pinned campaign commitment."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    Digest,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import TextBlock
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.run.review_approval import ApprovalPreview
from mos_eisley.run.review_broker import PreparedReviewEnvelope
from mos_eisley.run.review_campaign import read_campaign_seal
from mos_eisley.run.review_conformance_acceptance import review_role_profile
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
)
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerCriticPreview,
)


class ReviewCampaignBinding(Contract):
    campaign_directory: Annotated[str, Field(min_length=1, max_length=4096)]
    expected_seal_sha256: Digest
    attempt_index: Annotated[int, Field(ge=0, le=2)]

    @model_validator(mode="after")
    def absolute_directory(self) -> Self:
        if not Path(self.campaign_directory).is_absolute():
            raise ValueError("campaign dispatch binding requires an absolute directory")
        return self


class ReviewCampaignAdmission:
    """Additional restriction, never a signature, local approval or retry grant."""

    def __init__(
        self,
        binding: ReviewCampaignBinding,
        controller: BrokeredReviewController,
        envelope: PreparedReviewEnvelope,
        reviewer: ModelReviewer,
        *,
        authority_policy: Callable[[], ReviewConformanceAuthorityPolicy],
        runtime: Callable[[], ReviewConformanceRuntime],
    ) -> None:
        self._binding = ReviewCampaignBinding.model_validate_json(
            canonical_bytes(binding)
        )
        self._controller = controller
        self._envelope = envelope
        self._reviewer = reviewer
        self._authority = authority_policy
        self._runtime = runtime
        bundle, _ = read_campaign_seal(
            Path(self._binding.campaign_directory), self._binding.expected_seal_sha256
        )
        attempt = bundle.attempts[self._binding.attempt_index]
        self._expires_at = min(
            bundle.policy.valid_until,
            attempt.observation_policy.valid_until,
            attempt.authority_policy.valid_until,
            attempt.preview.envelope.expires_at,
        )
        self.check(controller.preview)

    @property
    def expires_at(self) -> datetime:
        """Pinned deadline; check() reauthenticates the bytes at every use."""
        return self._expires_at

    def check(self, preview: ApprovalPreview) -> None:
        bundle, seal = read_campaign_seal(
            Path(self._binding.campaign_directory), self._binding.expected_seal_sha256
        )
        attempt = bundle.attempts[self._binding.attempt_index]
        now = datetime.now(UTC)
        if (
            not seal.sealed_at <= now < self.expires_at
            or not attempt.authority_policy.valid_from <= now
            or not attempt.observation_policy.valid_from <= now
        ):
            raise ValueError("campaign dispatch is outside its sealed policy windows")
        if (
            canonical_bytes(self._controller.preview)
            != canonical_bytes(attempt.preview)
            or self._runtime() != bundle.policy.runtime
            or canonical_bytes(self._authority())
            != canonical_bytes(attempt.authority_policy)
        ):
            raise ValueError("campaign dispatch preview, runtime or authority changed")
        expected_ledger = Path(attempt.ledger_path).resolve()
        if (
            self._envelope.ledger.path.resolve() != expected_ledger
            or any(
                call.ledger_path != expected_ledger for call in self._envelope.critics
            )
            or digest(canonical_bytes(self._envelope.ledger.policy))
            != attempt.preview.envelope.ledger_policy_sha256
        ):
            raise ValueError(
                "campaign dispatch ledger differs from its sealed path or policy"
            )
        start = self._controller.start
        if start is None:
            directory = Path(attempt.preview.envelope.artifact_directory)
            if (
                self._controller.phase != "prepared"
                or directory.exists()
                or directory.is_symlink()
            ):
                raise ValueError(
                    "campaign dispatch requires an unused prepared controller"
                )
        elif start.started_at < seal.sealed_at:
            raise ValueError("campaign dispatch controller predates sealing")
        # Check the owning reviewer's judge projection before the first paid critic.
        request = attempt.preview.requests[0]
        text = "".join(
            block.text
            for block in request.turns[0].blocks
            if isinstance(block, TextBlock)
        )
        brief = CriticRequest.model_validate_json(text).brief
        projected = self._reviewer.judge_request(JudgeRequest(brief=brief, findings=()))
        if review_role_profile(projected) != bundle.policy.judge:
            raise ValueError("campaign dispatch judge configuration changed")
        if isinstance(preview, ControllerCriticPreview):
            if canonical_bytes(preview) != canonical_bytes(attempt.preview):
                raise ValueError("campaign dispatch selected another critic preview")
        elif (
            preview.controller_sha256 != self._controller.approval_sha256
            or review_role_profile(preview.model_request) != bundle.policy.judge
        ):
            raise ValueError(
                "campaign dispatch judge differs from its committed profile"
            )
