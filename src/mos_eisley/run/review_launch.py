"""Build an inert review launch preview from explicit host-selected inputs."""

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.budget import BudgetPolicy, resolve_budget
from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    CriticSpec,
    Digest,
    Identifier,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import Effort, ModelRequest, ModelResponse
from mos_eisley.core.registry import ModelRegistry
from mos_eisley.project_guidance_review import PreparedGuidanceReview
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.review_broker import PreparedReviewCall, PreparedReviewEnvelope
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerCriticPreview,
)
from mos_eisley.run.review_guidance import ReviewGuidanceAdmission
from mos_eisley.run.spend_ledger import SpendLedger

CONFIGURATION_BYTES = 256_000


class LaunchCritic(Contract):
    critic: CriticSpec
    spending: SpendPolicy

    @model_validator(mode="after")
    def same_model(self) -> Self:
        if self.critic.model != self.spending.model:
            raise ValueError("critic spending policy differs from the selected model")
        return self


class ReviewLaunchConfiguration(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["brokered_review_launch_configuration"] = (
        "brokered_review_launch_configuration"
    )
    registry: ModelRegistry
    critics: Annotated[tuple[LaunchCritic, ...], Field(min_length=1, max_length=8)]
    judge_provider: Literal["openai"] = "openai"
    judge_model: Identifier
    judge_spending: SpendPolicy
    effort: Effort
    budget: BudgetPolicy
    policy: ReviewPolicy = Field(default_factory=ReviewPolicy)
    total_seconds: Annotated[float, Field(gt=0, le=600)] = 120
    max_total_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]


class ReviewLaunchPreview(Contract):
    schema_version: Literal[1] = 1
    configuration_sha256: Digest
    registry_sha256: Digest
    guidance_sha256: Digest
    preview: ControllerCriticPreview
    conformance_status: Literal["review_controller_conformance_required"] = (
        "review_controller_conformance_required"
    )
    live_launch_available: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    reservation_created: Literal[False] = False


class _ProjectionOnlyClient:
    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise ValueError("launch preview cannot execute a model request")


def decode_launch_configuration(raw: bytes) -> ReviewLaunchConfiguration:
    if len(raw) > CONFIGURATION_BYTES:
        raise ValueError("review launch configuration exceeds its byte limit")
    try:
        raw.decode("utf-8")
        json.loads(raw, object_pairs_hook=unique_object)
        return ReviewLaunchConfiguration.model_validate_json(raw)
    except (ValueError, RecursionError):
        raise ValueError("invalid review launch configuration") from None


def prepare_review_launch_preview(
    configuration: ReviewLaunchConfiguration,
    *,
    prepared: PreparedGuidanceReview,
    expected_prepared_sha256: str,
    workspace: Path,
    guidance_store: RoleContextAdmissionStore,
    guidance_policy_path: Path,
    expected_guidance_policy_sha256: str,
    ledger: SpendLedger,
    review_directory: Path,
) -> ReviewLaunchPreview:
    """No credentials, containers, reservations or authority from registry labels.

    Current guidance is mandatory. Existing evaluation conformance receipts do
    not establish credentialed conformance for this review-controller path.
    """
    configuration = decode_launch_configuration(canonical_bytes(configuration))
    if prepared.sha256 != expected_prepared_sha256:
        raise ValueError("selected prepared review hash mismatch")
    if (
        review_directory.exists()
        or review_directory.is_symlink()
        or not review_directory.parent.is_dir()
    ):
        raise ValueError(
            "review preview requires an unused directory in an existing parent"
        )
    admission = ReviewGuidanceAdmission(
        guidance_store,
        workspace,
        prepared,
        guidance_policy_path,
        expected_guidance_policy_sha256,
    )
    for provider, model in (
        *((item.critic.provider, item.critic.model) for item in configuration.critics),
        (configuration.judge_provider, configuration.judge_model),
    ):
        if provider != "openai":
            raise ValueError("brokered review launch supports only OpenAI")
        resolved = configuration.registry.resolve(provider, model, configuration.effort)
        if resolved.substituted:
            raise ValueError(
                "review launch cannot silently substitute reasoning effort"
            )
    if configuration.judge_spending.model != configuration.judge_model:
        raise ValueError("judge spending policy differs from the selected model")
    judge_model = configuration.registry.resolve(
        configuration.judge_provider, configuration.judge_model, configuration.effort
    )
    output_tokens = resolve_budget(
        judge_model.spec, judge_model.effort, configuration.budget
    ).max_output_tokens
    if (
        output_tokens is None
        or output_tokens > configuration.judge_spending.max_output_tokens
    ):
        raise ValueError("judge output budget exceeds its spending policy")
    reviewer = ModelReviewer(
        _ProjectionOnlyClient(),
        configuration.registry,
        judge_provider=configuration.judge_provider,
        judge_model=configuration.judge_model,
        effort=configuration.effort,
        budget=configuration.budget,
    )
    calls = tuple(
        PreparedReviewCall(
            reviewer,
            CriticRequest(brief=prepared.brief, persona=item.critic.persona),
            item.spending,
            ledger,
            critic=item.critic,
            guidance=admission,
        )
        for item in configuration.critics
    )
    envelope = PreparedReviewEnvelope(
        calls,
        configuration.judge_spending,
        ledger,
        max_total_microusd=configuration.max_total_microusd,
        directory=review_directory,
    )
    controller = BrokeredReviewController(
        envelope,
        reviewer,
        configuration.policy,
        total_seconds=configuration.total_seconds,
    )
    preview = controller.preview
    admission.check()
    return ReviewLaunchPreview(
        configuration_sha256=digest(canonical_bytes(configuration)),
        registry_sha256=digest(canonical_bytes(configuration.registry)),
        guidance_sha256=prepared.sha256,
        preview=preview,
    )
