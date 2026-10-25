"""Build an inert review launch preview from explicit host-selected inputs."""

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.budget import BudgetPolicy, resolve_budget
from mos_eisley.core.models import (
    Contract,
    CriticSpec,
    Digest,
    Identifier,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import Effort, ModelRequest, ModelResponse
from mos_eisley.core.registry import ModelRegistry
from mos_eisley.git_review import GitReviewScope
from mos_eisley.project_guidance_review import PreparedGuidanceReview
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.review.citations import citation_bound_request
from mos_eisley.run.review_broker import (
    PreparedReviewCall,
    PreparedReviewEnvelope,
    ReviewPreparationScope,
)
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerCriticPreview,
)
from mos_eisley.run.review_guidance import ReviewGuidanceAdmission
from mos_eisley.run.review_source import check_review_source
from mos_eisley.run.spend_ledger import SpendLedger

CONFIGURATION_BYTES = 256_000


class LaunchCritic(Contract):
    critic: CriticSpec
    spending: SpendPolicy

    @model_validator(mode="after")
    def same_model(self) -> Self:
        if (
            self.critic.model != self.spending.model
            or self.critic.provider != self.spending.provider
        ):
            raise ValueError("critic spending policy differs from the selected model")
        return self


class ReviewLaunchConfiguration(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["brokered_review_launch_configuration"] = (
        "brokered_review_launch_configuration"
    )
    registry: ModelRegistry
    critics: Annotated[tuple[LaunchCritic, ...], Field(min_length=1, max_length=8)]
    judge_provider: Literal["openai", "anthropic"] = "openai"
    judge_model: Identifier
    judge_spending: SpendPolicy
    effort: Effort
    critic_effort: Effort | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    budget: BudgetPolicy
    max_text_output_bytes: Annotated[int, Field(gt=0, le=64_000)] = 8_000
    policy: ReviewPolicy = Field(default_factory=ReviewPolicy)
    total_seconds: Annotated[float, Field(gt=0, le=600)] = 120
    max_total_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    preparation_scope: ReviewPreparationScope = Field(
        default="standard", exclude_if=lambda value: value == "standard"
    )


class ReviewIntentPreview(Contract):
    """Bounded user-facing projection; never a dispatch or posting capability."""

    schema_version: Literal[1] = 1
    brief_id: Digest
    prepared_sha256: Digest
    configuration_sha256: Digest
    guidance_policy_sha256: Digest
    target: dict[str, object]
    critics: Annotated[tuple[CriticSpec, ...], Field(min_length=1, max_length=8)]
    judge_provider: Literal["openai", "anthropic"]
    judge_model: Identifier
    policy: ReviewPolicy
    remaining_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    reserved_upper_bound_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    total_seconds: Annotated[float, Field(gt=0, le=600)]
    estimated_cost_microusd: None = None
    read_only: Literal[True] = True
    posting_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(canonical_bytes(self)) > CONFIGURATION_BYTES:
            raise ValueError("Review intent preview exceeds its byte limit")
        return self

    def describe(self) -> str:
        return (
            f"Live review preview • brief {self.brief_id}\n"
            f"Target: {json.dumps(self.target, ensure_ascii=True, sort_keys=True)}\n"
            "Critics: "
            + ", ".join(f"{c.provider}/{c.model}: {c.persona}" for c in self.critics)
            + f"\nJudge: {self.judge_provider}/{self.judge_model}\n"
            f"Policy: {self.policy.model_dump_json()}\n"
            f"Remaining ceiling: {self.remaining_microusd} microusd; "
            f"reserved upper bound: {self.reserved_upper_bound_microusd} microusd; "
            f"estimate: unknown; execution limit: {self.total_seconds:g}s.\n"
            "Read-only review; edits and outward posting are not authorized. "
            "Existing signed launch and phase admission remain required."
        )


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
    intent: ReviewIntentPreview | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


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
    git_scope: GitReviewScope | None = None,
    owner_remaining_microusd: int | None = None,
) -> ReviewLaunchPreview:
    """No credentials, containers, reservations or authority from registry labels.

    Current guidance is mandatory. Existing evaluation conformance receipts do
    not establish credentialed conformance for this review-controller path.
    """
    configuration = decode_launch_configuration(canonical_bytes(configuration))
    if git_scope is not None:
        check_review_source(git_scope, workspace, prepared.source_brief)
    envelope, reviewer, admission = prepare_review_launch_components(
        configuration,
        prepared=prepared,
        expected_prepared_sha256=expected_prepared_sha256,
        workspace=workspace,
        guidance_store=guidance_store,
        guidance_policy_path=guidance_policy_path,
        expected_guidance_policy_sha256=expected_guidance_policy_sha256,
        ledger=ledger,
        review_directory=review_directory,
    )
    controller = BrokeredReviewController(
        envelope,
        reviewer,
        configuration.policy,
        total_seconds=configuration.total_seconds,
    )
    preview = controller.preview
    admission.check()
    if git_scope is not None:
        check_review_source(git_scope, workspace, prepared.source_brief)
    snapshot = ledger.snapshot()
    remaining = min(configuration.max_total_microusd, snapshot.available_microusd)
    if owner_remaining_microusd is not None:
        remaining = min(remaining, owner_remaining_microusd)
    if snapshot.blocked or preview.envelope.total_reserved_microusd > remaining:
        raise ValueError("Review exceeds the remaining task spending ceiling.")
    return ReviewLaunchPreview(
        configuration_sha256=digest(canonical_bytes(configuration)),
        registry_sha256=digest(canonical_bytes(configuration.registry)),
        guidance_sha256=prepared.sha256,
        preview=preview,
        intent=ReviewIntentPreview(
            brief_id=prepared.brief.brief_id,
            prepared_sha256=prepared.sha256,
            configuration_sha256=digest(canonical_bytes(configuration)),
            guidance_policy_sha256=expected_guidance_policy_sha256,
            target=git_scope.preview()
            if git_scope is not None
            else {"basis": "prepared brief"},
            critics=tuple(c.critic for c in configuration.critics),
            judge_provider=configuration.judge_provider,
            judge_model=configuration.judge_model,
            policy=configuration.policy,
            remaining_microusd=remaining,
            reserved_upper_bound_microusd=preview.envelope.total_reserved_microusd,
            total_seconds=configuration.total_seconds,
        ),
    )


def prepare_review_launch_components(
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
    committed_preview: ControllerCriticPreview | None = None,
) -> tuple[PreparedReviewEnvelope, ModelReviewer, ReviewGuidanceAdmission]:
    """Compose fresh inputs or restore an exact sealed, still-current preview."""
    configuration = decode_launch_configuration(canonical_bytes(configuration))
    if committed_preview is not None:
        committed_preview = ControllerCriticPreview.model_validate_json(
            canonical_bytes(committed_preview)
        )
        if len(committed_preview.envelope.critics) != len(configuration.critics):
            raise ValueError("committed critic count differs from configuration")
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
    roles: tuple[tuple[str, str, Effort], ...] = (
        *(
            (
                item.critic.provider,
                item.critic.model,
                configuration.critic_effort or configuration.effort,
            )
            for item in configuration.critics
        ),
        (
            configuration.judge_provider,
            configuration.judge_model,
            configuration.effort,
        ),
    )
    for provider, model, effort in roles:
        if provider not in ("openai", "anthropic"):
            raise ValueError("brokered review launch provider is unsupported")
        resolved = configuration.registry.resolve(provider, model, effort)
        if resolved.substituted:
            raise ValueError(
                "review launch cannot silently substitute reasoning effort"
            )
    if (
        configuration.judge_spending.model != configuration.judge_model
        or configuration.judge_spending.provider != configuration.judge_provider
    ):
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
        critic_effort=configuration.critic_effort,
        budget=configuration.budget,
        max_text_output_bytes=configuration.max_text_output_bytes,
    )
    calls = tuple(
        PreparedReviewCall(
            reviewer,
            citation_bound_request(prepared.brief, item.critic.persona),
            item.spending,
            ledger,
            critic=item.critic,
            guidance=admission,
            preparation_scope=configuration.preparation_scope,
            committed_authorization=(
                None
                if committed_preview is None
                else committed_preview.envelope.critics[index]
            ),
        )
        for index, item in enumerate(configuration.critics)
    )
    envelope = PreparedReviewEnvelope(
        calls,
        configuration.judge_spending,
        ledger,
        max_total_microusd=configuration.max_total_microusd,
        directory=review_directory,
        committed_judge=(
            None if committed_preview is None else committed_preview.envelope.judge
        ),
    )
    if committed_preview is not None:
        controller = BrokeredReviewController(
            envelope,
            reviewer,
            configuration.policy,
            total_seconds=configuration.total_seconds,
        )
        if canonical_bytes(controller.preview) != canonical_bytes(committed_preview):
            raise ValueError("committed critic preview differs from current inputs")
    admission.check()
    return envelope, reviewer, admission
