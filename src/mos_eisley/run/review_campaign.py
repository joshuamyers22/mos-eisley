"""Explicit offline commitment custody and fresh review of campaign evidence."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    Digest,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.run.files import read_bounded
from mos_eisley.run.review_conformance_acceptance import (
    ReviewAcceptancePolicy,
    ReviewAcceptanceResult,
    ReviewAttemptEvidence,
    evaluate_review_conformance,
    review_role_profile,
)
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    SignedReviewConformanceAuthorization,
)
from mos_eisley.run.review_conformance_observation import (
    ReviewObservationPolicy,
    SignedReviewProbeObservation,
)
from mos_eisley.run.review_controller import (
    ControllerCriticPreview,
    ControllerJudgePreview,
    ControllerStart,
)
from mos_eisley.run.review_launch import ReviewLaunchConfiguration
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write

CAMPAIGN_BYTES = 8_000_000
AbsolutePath = Annotated[str, Field(min_length=1, max_length=4096)]


class _NoDispatch:
    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise ValueError("campaign ceremony cannot dispatch provider requests")


def campaign_reviewer(configuration: ReviewLaunchConfiguration) -> ModelReviewer:
    """Reconstruct sealed review projections through a dispatch-refusing client."""
    return ModelReviewer(
        _NoDispatch(),
        configuration.registry,
        judge_provider=configuration.judge_provider,
        judge_model=configuration.judge_model,
        effort=configuration.effort,
        budget=configuration.budget,
    )


class CampaignAttempt(Contract):
    configuration: ReviewLaunchConfiguration
    preview: ControllerCriticPreview
    authority_policy: ReviewConformanceAuthorityPolicy
    observation_policy: ReviewObservationPolicy
    ledger_path: AbsolutePath

    @model_validator(mode="after")
    def exact_configuration(self) -> Self:
        if not Path(self.ledger_path).is_absolute():
            raise ValueError("campaign ledger paths must be absolute")
        config, preview = self.configuration, self.preview
        if (
            config.policy != preview.authorization.policy
            or config.total_seconds != preview.authorization.total_seconds
            or config.judge_spending != preview.envelope.judge.spend_policy
            or config.judge_model != config.judge_spending.model
            or config.max_total_microusd != preview.envelope.max_total_microusd
            or len(config.critics) != len(preview.requests)
        ):
            raise ValueError("campaign configuration differs from its preview")
        reviewer = campaign_reviewer(config)
        for selected, request, call in zip(
            config.critics, preview.requests, preview.envelope.critics, strict=True
        ):
            if (
                len(request.turns) != 1
                or request.turns[0].role != "user"
                or any(
                    not isinstance(block, TextBlock)
                    for block in request.turns[0].blocks
                )
            ):
                raise ValueError("campaign preview requires canonical review text")
            text = "".join(
                block.text
                for block in request.turns[0].blocks
                if isinstance(block, TextBlock)
            )
            review = CriticRequest.model_validate_json(text)
            if (
                digest(canonical_bytes(selected.critic)) != call.critic_sha256
                or selected.spending.policy_sha256 != call.spend_policy_sha256
                or review.brief.brief_id != call.brief_sha256
                or reviewer.critic_request(selected.critic, review) != request
            ):
                raise ValueError(
                    "campaign critic projection differs from approved content"
                )
        return self


class ReviewCampaignBundle(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_campaign_bundle"] = "review_campaign_bundle"
    policy: ReviewAcceptancePolicy
    attempts: Annotated[tuple[CampaignAttempt, ...], Field(min_length=3, max_length=3)]
    provider_dispatch_authorized: Literal[False] = False
    live_review_activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def committed_slots(self) -> Self:
        paths: set[str] = set()
        for slot, attempt in zip(self.policy.attempts, self.attempts, strict=True):
            preview = attempt.preview
            observation = attempt.observation_policy
            if (
                slot.critic_preview_sha256 != digest(canonical_bytes(preview))
                or slot.observation_policy_sha256
                != digest(canonical_bytes(observation))
                or slot.authority_policy_sha256 != attempt.authority_policy.sha256
                or observation.critic_preview_sha256 != slot.critic_preview_sha256
                or observation.authority_policy_sha256 != slot.authority_policy_sha256
                or preview.authorization.policy != self.policy.review_policy
                or preview.authorization.total_seconds != self.policy.total_seconds
                or tuple(
                    review_role_profile(request, call.critic_sha256)
                    for request, call in zip(
                        preview.requests, preview.envelope.critics, strict=True
                    )
                )
                != self.policy.critics
                or preview.envelope.artifact_directory in paths
            ):
                raise ValueError(
                    "campaign bundle differs from committed slots or profile"
                )
            paths.add(preview.envelope.artifact_directory)
            request = preview.requests[0]
            text = "".join(
                block.text
                for block in request.turns[0].blocks
                if isinstance(block, TextBlock)
            )
            brief = CriticRequest.model_validate_json(text).brief
            judge = campaign_reviewer(attempt.configuration).judge_request(
                JudgeRequest(brief=brief, findings=())
            )
            if review_role_profile(judge) != self.policy.judge:
                raise ValueError("campaign judge profile differs from commitment")
        return self


def _decode(raw: bytes) -> None:
    if len(raw) > CAMPAIGN_BYTES:
        raise ValueError("campaign input exceeds its byte limit")
    try:
        json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        raise ValueError("invalid campaign JSON") from None


def decode_campaign_bundle(raw: bytes) -> ReviewCampaignBundle:
    _decode(raw)
    return ReviewCampaignBundle.model_validate_json(raw)


class CampaignSeal(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_campaign_seal"] = "review_campaign_seal"
    bundle_sha256: Digest
    policy_sha256: Digest
    sealed_at: datetime
    independently_timestamped: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    live_review_activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def utc(self) -> Self:
        if self.sealed_at.tzinfo is None or self.sealed_at.utcoffset() != timedelta(0):
            raise ValueError("campaign seal requires UTC")
        return self


def validate_campaign_preflight(bundle: ReviewCampaignBundle, now: datetime) -> None:
    if (
        now.tzinfo is None
        or now.utcoffset() != timedelta(0)
        or not bundle.policy.committed_at <= now < bundle.policy.valid_until
    ):
        raise ValueError("campaign commitment is outside its UTC window")
    planned: dict[str, int] = {}
    ledgers: dict[str, SpendLedger] = {}
    directories: set[Path] = set()
    for attempt in bundle.attempts:
        directory = Path(attempt.preview.envelope.artifact_directory)
        if (
            not directory.is_absolute()
            or directory.exists()
            or directory.is_symlink()
            or not directory.parent.is_dir()
        ):
            raise ValueError(
                "campaign requires unused run directories in existing parents"
            )
        resolved = directory.resolve()
        if resolved in directories:
            raise ValueError("campaign requires distinct resolved run directories")
        directories.add(resolved)
        if (
            now >= attempt.preview.envelope.expires_at
            or not attempt.authority_policy.valid_from
            <= now
            < attempt.authority_policy.valid_until
            or not attempt.observation_policy.valid_from
            <= now
            < attempt.observation_policy.valid_until
        ):
            raise ValueError("campaign attempt policies are outside their windows")
        ledger = SpendLedger(Path(attempt.ledger_path))
        ledger_id = ledger.policy.ledger_id
        if digest(
            canonical_bytes(ledger.policy)
        ) != attempt.preview.envelope.ledger_policy_sha256 or any(
            call.ledger_id != ledger_id for call in attempt.preview.envelope.critics
        ):
            raise ValueError("campaign ledger differs from its committed preview")
        if (
            ledger_id in ledgers
            and ledgers[ledger_id].path.resolve() != ledger.path.resolve()
        ):
            raise ValueError("campaign ledger identity has conflicting paths")
        ledgers[ledger_id] = ledger
        planned[ledger_id] = (
            planned.get(ledger_id, 0) + attempt.preview.envelope.total_reserved_microusd
        )
    for ledger_id, ledger in ledgers.items():
        snapshot = ledger.snapshot()
        if (
            snapshot.entries
            or snapshot.blocked
            or snapshot.available_microusd < planned[ledger_id]
        ):
            raise ValueError(
                "campaign requires empty ledgers covering all planned allowances"
            )


def seal_review_campaign(
    bundle: ReviewCampaignBundle,
    destination: Path,
    *,
    expected_bundle_sha256: str,
    now: datetime,
) -> CampaignSeal:
    raw = canonical_bytes(bundle)
    bundle = decode_campaign_bundle(raw)
    if digest(raw) != expected_bundle_sha256:
        raise ValueError("campaign bundle changed before sealing")
    validate_campaign_preflight(bundle, now)
    if destination.is_symlink():
        raise ValueError("campaign seal destination must not be a symlink")
    destination = destination.resolve()
    for attempt in bundle.attempts:
        run = Path(attempt.preview.envelope.artifact_directory).resolve()
        if destination.is_relative_to(run) or run.is_relative_to(destination):
            raise ValueError("campaign seal must be outside planned run directories")
    seal = CampaignSeal(
        bundle_sha256=digest(raw),
        policy_sha256=digest(canonical_bytes(bundle.policy)),
        sealed_at=now,
    )
    destination.mkdir(mode=0o700)
    private_write(destination / "bundle.json", raw)
    private_write(destination / "seal.json", canonical_bytes(seal))
    return seal


def read_campaign_seal(
    directory: Path, expected_seal_sha256: str
) -> tuple[ReviewCampaignBundle, CampaignSeal]:
    if directory.is_symlink():
        raise ValueError("campaign seal directory must not be a symlink")
    raw = read_bounded(directory / "seal.json", 4096)
    if digest(raw) != expected_seal_sha256:
        raise ValueError("campaign seal differs from its independent pin")
    seal = CampaignSeal.model_validate_json(raw)
    bundle_raw = read_bounded(directory / "bundle.json", CAMPAIGN_BYTES)
    bundle = decode_campaign_bundle(bundle_raw)
    if (
        digest(bundle_raw) != seal.bundle_sha256
        or digest(canonical_bytes(bundle.policy)) != seal.policy_sha256
        or not bundle.policy.committed_at <= seal.sealed_at < bundle.policy.valid_until
    ):
        raise ValueError("campaign bundle differs from its retained seal")
    return bundle, seal


class CampaignAttemptSubmission(Contract):
    start: ControllerStart
    judge: ControllerJudgePreview
    authorizations: tuple[
        SignedReviewConformanceAuthorization, SignedReviewConformanceAuthorization
    ]
    signed_observation: SignedReviewProbeObservation
    expected_result_sha256: Digest
    lifecycle_directories: Annotated[
        tuple[AbsolutePath, ...], Field(min_length=2, max_length=9)
    ]

    @model_validator(mode="after")
    def utc_start(self) -> Self:
        if (
            any(
                value.tzinfo is None or value.utcoffset() != timedelta(0)
                for value in (self.start.started_at, self.start.expires_at)
            )
            or self.start.started_at >= self.start.expires_at
        ):
            raise ValueError("campaign controller start requires an ordered UTC window")
        return self


class CampaignEvidenceSubmission(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_campaign_evidence_submission"] = (
        "review_campaign_evidence_submission"
    )
    seal_sha256: Digest
    attempts: Annotated[
        tuple[CampaignAttemptSubmission | None, ...], Field(min_length=3, max_length=3)
    ]


def decode_campaign_submission(raw: bytes) -> CampaignEvidenceSubmission:
    _decode(raw)
    return CampaignEvidenceSubmission.model_validate_json(raw)


def review_campaign_evidence(
    directory: Path,
    expected_seal_sha256: str,
    submission: CampaignEvidenceSubmission,
    *,
    now: datetime,
) -> ReviewAcceptanceResult:
    submission = decode_campaign_submission(canonical_bytes(submission))
    if submission.seal_sha256 != expected_seal_sha256:
        raise ValueError("campaign evidence targets another retained seal")
    bundle, seal = read_campaign_seal(directory, expected_seal_sha256)
    evidence: list[ReviewAttemptEvidence | None] = []
    for committed, supplied in zip(bundle.attempts, submission.attempts, strict=True):
        if supplied is None:
            evidence.append(None)
            continue
        if supplied.start.started_at < seal.sealed_at or any(
            not Path(path).is_absolute() for path in supplied.lifecycle_directories
        ):
            raise ValueError(
                "campaign evidence predates sealing or uses relative lifecycle paths"
            )
        evidence.append(
            ReviewAttemptEvidence(
                observation_policy=committed.observation_policy,
                authority_policy=committed.authority_policy,
                critics=committed.preview,
                start=supplied.start,
                judge=supplied.judge,
                authorizations=supplied.authorizations,
                signed_observation=supplied.signed_observation,
                expected_result_sha256=supplied.expected_result_sha256,
                lifecycle_directories=tuple(
                    Path(path) for path in supplied.lifecycle_directories
                ),
                reviewer=campaign_reviewer(committed.configuration),
                ledger=SpendLedger(Path(committed.ledger_path)),
            )
        )
    return evaluate_review_conformance(bundle.policy, tuple(evidence), now=now)
