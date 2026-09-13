"""Fresh campaign verification and proposed launch profile comparison; no authority."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    Digest,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import TextBlock
from mos_eisley.run.review_campaign import (
    CampaignEvidenceSubmission,
    campaign_reviewer,
    decode_campaign_submission,
    read_campaign_seal,
    review_campaign_evidence,
)
from mos_eisley.run.review_conformance_acceptance import (
    ReviewAcceptanceResult,
    ReviewRoleProfile,
    review_role_profile,
)
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_launch import (
    ReviewLaunchConfiguration,
    ReviewLaunchPreview,
    decode_launch_configuration,
)


class ReviewLaunchConformanceCheck(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_launch_conformance_check"] = "review_launch_conformance_check"
    configuration_sha256: Digest
    launch_preview_sha256: Digest
    seal_sha256: Digest
    canonical_submission_sha256: Digest
    runtime: ReviewConformanceRuntime
    conformance: ReviewAcceptanceResult
    launch_review_required: Literal[True] = True
    live_launch_available: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    reservation_created: Literal[False] = False


def check_review_launch_conformance(
    configuration: ReviewLaunchConfiguration,
    launch: ReviewLaunchPreview,
    campaign_directory: Path,
    expected_seal_sha256: str,
    submission: CampaignEvidenceSubmission,
    *,
    runtime: ReviewConformanceRuntime,
    now: datetime,
) -> ReviewLaunchConformanceCheck:
    """Caller supplies a freshly prepared launch; saved checks never admit dispatch."""
    configuration = decode_launch_configuration(canonical_bytes(configuration))
    launch = ReviewLaunchPreview.model_validate_json(canonical_bytes(launch))
    submission = decode_campaign_submission(canonical_bytes(submission))
    runtime = ReviewConformanceRuntime.model_validate_json(canonical_bytes(runtime))
    bundle, _ = read_campaign_seal(campaign_directory, expected_seal_sha256)
    preview, policy = launch.preview, bundle.policy
    if (
        launch.configuration_sha256 != digest(canonical_bytes(configuration))
        or launch.registry_sha256 != digest(canonical_bytes(configuration.registry))
        or configuration.policy != preview.authorization.policy
        or configuration.total_seconds != preview.authorization.total_seconds
        or configuration.policy != policy.review_policy
        or configuration.total_seconds != policy.total_seconds
        or runtime != policy.runtime
        or len(configuration.critics) != len(preview.requests)
        or len(preview.requests) != len(preview.envelope.critics)
    ):
        raise ValueError(
            "proposed launch differs from the selected conformance profile"
        )
    reviewer = campaign_reviewer(configuration)
    roles: list[ReviewRoleProfile] = []
    brief = None
    for selected, request, call in zip(
        configuration.critics, preview.requests, preview.envelope.critics, strict=True
    ):
        if (
            len(request.turns) != 1
            or request.turns[0].role != "user"
            or any(
                not isinstance(block, TextBlock) for block in request.turns[0].blocks
            )
        ):
            raise ValueError("launch conformance requires canonical review text")
        content = "".join(
            block.text
            for block in request.turns[0].blocks
            if isinstance(block, TextBlock)
        )
        review = CriticRequest.model_validate_json(content)
        if (
            call.critic_sha256 != digest(canonical_bytes(selected.critic))
            or reviewer.critic_request(selected.critic, review) != request
            or (brief is not None and brief != review.brief)
        ):
            raise ValueError("launch role differs from its selected configuration")
        brief = review.brief
        roles.append(review_role_profile(request, call.critic_sha256))
    if brief is None:
        raise ValueError("launch conformance requires a critic brief")
    judge = reviewer.judge_request(JudgeRequest(brief=brief, findings=()))
    if tuple(roles) != policy.critics or review_role_profile(judge) != policy.judge:
        raise ValueError("proposed launch roles differ from the conformance profile")
    reviewed = review_campaign_evidence(
        campaign_directory, expected_seal_sha256, submission, now=now
    )
    return ReviewLaunchConformanceCheck(
        configuration_sha256=launch.configuration_sha256,
        launch_preview_sha256=digest(canonical_bytes(launch)),
        seal_sha256=expected_seal_sha256,
        canonical_submission_sha256=digest(canonical_bytes(submission)),
        runtime=runtime,
        conformance=reviewed,
    )
