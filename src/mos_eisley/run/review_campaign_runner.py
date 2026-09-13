"""Owned fixed-order campaign execution with independent evidence handoff."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.review_campaign import (
    CampaignAttemptSubmission,
    CampaignEvidenceSubmission,
    read_campaign_seal,
    review_campaign_evidence,
)
from mos_eisley.run.review_campaign_dispatch import ReviewCampaignBinding
from mos_eisley.run.review_conformance_acceptance import ReviewAcceptanceResult
from mos_eisley.run.review_conformance_authorization import (
    SignedReviewConformanceAuthorization,
)
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_controller import ControllerJudgePreview, ControllerStart
from mos_eisley.run.review_verdict import RetainedReviewResult

CampaignPhase = Literal[
    "prepared",
    "running",
    "awaiting_observer",
    "accepted",
    "incomplete",
    "failed",
    "cancelled",
]


def _check_cancellation() -> None:
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError


class CampaignProbeCompletion(Contract):
    """Trusted in-process outputs offered for independent observer assessment."""

    seal_sha256: Digest
    attempt_index: Annotated[int, Field(ge=0, le=2)]
    start: ControllerStart
    judge: ControllerJudgePreview
    authorizations: tuple[
        SignedReviewConformanceAuthorization, SignedReviewConformanceAuthorization
    ]
    expected_result_sha256: Digest
    lifecycle_directories: Annotated[tuple[str, ...], Field(min_length=2, max_length=9)]


class OwnedReviewCampaign:
    """Invoke each bound probe once, requiring verified evidence before the next.

    The host must await run(), including cancellation. This object neither signs
    observations nor supplies phase approvals, reconstructs probes or resumes work.
    """

    def __init__(
        self,
        campaign_directory: Path,
        expected_seal_sha256: str,
        probes: tuple[BrokeredReviewConformanceProbe, ...],
        observe: Callable[
            [CampaignProbeCompletion], Awaitable[CampaignAttemptSubmission | None]
        ],
        *,
        observer_timeout_seconds: float = 120,
    ) -> None:
        if (
            len(probes) != 3
            or len({id(probe) for probe in probes}) != 3
            or not math.isfinite(observer_timeout_seconds)
            or not 0 < observer_timeout_seconds <= 600
        ):
            raise ValueError(
                "campaign requires three distinct probes and a bounded observer wait"
            )
        bundle, _ = read_campaign_seal(campaign_directory, expected_seal_sha256)
        for index, (probe, attempt) in enumerate(
            zip(probes, bundle.attempts, strict=True)
        ):
            expected = ReviewCampaignBinding(
                campaign_directory=str(campaign_directory),
                expected_seal_sha256=expected_seal_sha256,
                attempt_index=index,
            )
            if (
                probe.campaign_binding != expected
                or probe.controller.phase != "prepared"
                or canonical_bytes(probe.controller.preview)
                != canonical_bytes(attempt.preview)
            ):
                raise ValueError(
                    "campaign requires fresh probes bound to its exact ordered slots"
                )
        self._directory = campaign_directory
        self._seal_sha = expected_seal_sha256
        self._probes = tuple(probes)
        self._observe = observe
        self._observer_timeout = observer_timeout_seconds
        self._expires_at = bundle.policy.valid_until
        self._phase: CampaignPhase = "prepared"
        self._submission = CampaignEvidenceSubmission(
            seal_sha256=self._seal_sha, attempts=(None, None, None)
        )
        self._completion: CampaignProbeCompletion | None = None

    @property
    def phase(self) -> CampaignPhase:
        return self._phase

    @property
    def submission(self) -> CampaignEvidenceSubmission:
        """Current verified slots; callers may independently retain this snapshot."""
        return CampaignEvidenceSubmission.model_validate_json(
            canonical_bytes(self._submission)
        )

    @property
    def last_completion(self) -> CampaignProbeCompletion | None:
        """Available even if observer handoff fails; it grants no replay authority."""
        return (
            None
            if self._completion is None
            else CampaignProbeCompletion.model_validate_json(
                canonical_bytes(self._completion)
            )
        )

    def _review(self, submission: CampaignEvidenceSubmission) -> ReviewAcceptanceResult:
        return review_campaign_evidence(
            self._directory, self._seal_sha, submission, now=datetime.now(UTC)
        )

    def _completed(
        self,
        index: int,
        probe: BrokeredReviewConformanceProbe,
        result: RetainedReviewResult,
    ) -> CampaignProbeCompletion:
        start, judge = probe.controller.start, probe.judge_preview
        authorizations = probe.approval_ui.authorizations
        paths = probe.lifecycle_paths
        if (
            start is None
            or judge is None
            or len(authorizations) != 2
            or any(path is None for path in paths)
        ):
            raise ValueError("campaign probe lacks complete owned handoff evidence")
        return CampaignProbeCompletion(
            seal_sha256=self._seal_sha,
            attempt_index=index,
            start=start,
            judge=judge,
            authorizations=(authorizations[0], authorizations[1]),
            expected_result_sha256=digest(canonical_bytes(result)),
            lifecycle_directories=tuple(str(path) for path in paths),
        )

    def _candidate(
        self, completion: CampaignProbeCompletion, supplied: CampaignAttemptSubmission
    ) -> CampaignEvidenceSubmission:
        supplied = CampaignAttemptSubmission.model_validate_json(
            canonical_bytes(supplied)
        )
        if (
            canonical_bytes(supplied.start) != canonical_bytes(completion.start)
            or canonical_bytes(supplied.judge) != canonical_bytes(completion.judge)
            or any(
                canonical_bytes(given) != canonical_bytes(expected)
                for given, expected in zip(
                    supplied.authorizations, completion.authorizations, strict=True
                )
            )
            or supplied.expected_result_sha256 != completion.expected_result_sha256
        ):
            raise ValueError(
                "campaign observer submission differs from the owned probe completion"
            )
        # The observer independently selects lifecycle paths; the existing runtime
        # verifier must authenticate those records against the signed evidence pins.
        slots = list(self._submission.attempts)
        slots[completion.attempt_index] = supplied
        return CampaignEvidenceSubmission(
            seal_sha256=self._seal_sha, attempts=tuple(slots)
        )

    async def run(self) -> ReviewAcceptanceResult:
        if self._phase != "prepared":
            raise ValueError("campaign runner is already consumed")
        self._phase = "running"
        reviewed: ReviewAcceptanceResult | None = None
        try:
            for index, probe in enumerate(self._probes):
                _check_cancellation()
                previous = self._review(self.submission)
                if previous.qualifying_attempts != index:
                    raise ValueError("campaign prior slots are not completely verified")
                self._phase = "running"
                result = await probe.run()
                _check_cancellation()
                if result is None:
                    self._phase = "incomplete"
                    return self._review(self.submission)
                completion = self._completed(index, probe, result)
                self._completion = completion
                self._phase = "awaiting_observer"
                remaining = min(
                    self._observer_timeout,
                    (self._expires_at - datetime.now(UTC)).total_seconds(),
                )
                if remaining <= 0:
                    raise ValueError("campaign expired before observer handoff")
                try:
                    limit = asyncio.timeout(remaining)
                    async with limit:
                        supplied = await self._observe(
                            CampaignProbeCompletion.model_validate_json(
                                canonical_bytes(completion)
                            )
                        )
                    if limit.expired():
                        supplied = None
                except TimeoutError:
                    supplied = None
                _check_cancellation()
                if supplied is None:
                    self._phase = "incomplete"
                    return self._review(self.submission)
                candidate = self._candidate(completion, supplied)
                reviewed = self._review(candidate)
                if reviewed.qualifying_attempts != index + 1:
                    raise ValueError(
                        "campaign observer evidence did not qualify its slot"
                    )
                self._submission = candidate
            if reviewed is None or reviewed.status != "accepted":
                raise ValueError("campaign did not verify all three committed attempts")
            self._phase = "accepted"
            return reviewed
        except BaseException as error:
            self._phase = (
                "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
            )
            raise
