"""Read-only acceptance of three precommitted, independently observed review probes."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import Effort, ModelRequest
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.files import read_bounded
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    SignedReviewConformanceAuthorization,
)
from mos_eisley.run.review_conformance_observation import (
    ReviewObservationPolicy,
    SignedReviewProbeObservation,
    authenticate_review_probe,
)
from mos_eisley.run.review_controller import (
    ControllerCriticPreview,
    ControllerJudgePreview,
    ControllerStart,
)
from mos_eisley.run.review_controller_inspection import inspect_review_controller
from mos_eisley.run.review_runtime_evidence import verify_review_runtime_exchange
from mos_eisley.run.spend_ledger import SpendLedger


class ReviewRoleProfile(Contract):
    provider: Literal["openai"] = "openai"
    model: Identifier
    effort: Effort
    system_sha256: Digest
    max_output_tokens: Annotated[int, Field(gt=0)]
    max_output_bytes: Annotated[int, Field(gt=0)]
    critic_sha256: Digest | None = None


def review_role_profile(
    request: ModelRequest, critic_sha256: str | None = None
) -> ReviewRoleProfile:
    request = ModelRequest.model_validate_json(canonical_bytes(request))
    if (
        request.provider != "openai"
        or request.tools
        or request.max_output_tokens is None
    ):
        raise ValueError("review acceptance requires bounded tool-free OpenAI roles")
    return ReviewRoleProfile(
        model=request.model,
        effort=request.effort,
        system_sha256=digest(request.system.encode()),
        max_output_tokens=request.max_output_tokens,
        max_output_bytes=request.max_output,
        critic_sha256=critic_sha256,
    )


class ReviewAttemptCommitment(Contract):
    critic_preview_sha256: Digest
    observation_policy_sha256: Digest
    authority_policy_sha256: Digest


class ReviewAcceptancePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_conformance_acceptance_policy"] = (
        "review_conformance_acceptance_policy"
    )
    policy_id: Identifier
    committed_at: datetime
    valid_until: datetime
    max_observation_age_seconds: Annotated[int, Field(gt=0, le=2_592_000)]
    runtime: ReviewConformanceRuntime
    review_policy: ReviewPolicy
    total_seconds: Annotated[float, Field(gt=0, le=600)]
    critics: Annotated[tuple[ReviewRoleProfile, ...], Field(min_length=1, max_length=8)]
    judge: ReviewRoleProfile
    attempts: Annotated[
        tuple[ReviewAttemptCommitment, ...], Field(min_length=3, max_length=3)
    ]
    required_successes: Literal[3] = 3
    live_review_activation_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False

    @field_validator("committed_at", "valid_until")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("review acceptance timestamps require explicit UTC")
        return value

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.valid_until <= self.committed_at:
            raise ValueError("review acceptance window must be positive")
        if (
            len({item.critic_preview_sha256 for item in self.attempts}) != 3
            or len({item.observation_policy_sha256 for item in self.attempts}) != 3
        ):
            raise ValueError(
                "review acceptance requires three distinct committed attempts"
            )
        if (
            any(item.critic_sha256 is None for item in self.critics)
            or self.judge.critic_sha256 is not None
        ):
            raise ValueError("review acceptance role identities are inconsistent")
        if (
            self.review_policy.min_critics > len(self.critics)
            or self.review_policy.min_providers > 1
        ):
            raise ValueError(
                "review acceptance profile cannot meet the selected quorum"
            )
        return self


@dataclass(frozen=True)
class ReviewAttemptEvidence:
    """Trusted caller-selected inputs and paths; never populated from a saved report."""

    observation_policy: ReviewObservationPolicy
    authority_policy: ReviewConformanceAuthorityPolicy
    critics: ControllerCriticPreview
    start: ControllerStart
    judge: ControllerJudgePreview
    authorizations: tuple[
        SignedReviewConformanceAuthorization, SignedReviewConformanceAuthorization
    ]
    signed_observation: SignedReviewProbeObservation
    expected_result_sha256: str
    lifecycle_directories: tuple[Path, ...]
    reviewer: ModelReviewer
    ledger: SpendLedger


class ReviewAcceptanceResult(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_conformance_acceptance_result"] = (
        "review_conformance_acceptance_result"
    )
    policy_sha256: Digest
    evaluated_at: datetime
    status: Literal["accepted", "incomplete"]
    qualifying_attempts: Annotated[int, Field(ge=0, le=3)]
    authenticated_observation_sha256s: tuple[Digest, ...]
    live_review_activation_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    retry_authorized: Literal[False] = False
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False


def evaluate_review_conformance(
    policy: ReviewAcceptancePolicy,
    attempts: tuple[ReviewAttemptEvidence | None, ...],
    *,
    now: datetime,
) -> ReviewAcceptanceResult:
    """Freshly verify every supplied slot; incomplete/corrupt evidence never passes.

    Acceptance covers this exact fixed tranche and role/runtime/quorum profile.
    Commitment custody and independent observer assessment remain external duties.
    """
    policy = ReviewAcceptancePolicy.model_validate_json(canonical_bytes(policy))
    if (
        now.tzinfo is None
        or now.utcoffset() != timedelta(0)
        or not policy.committed_at <= now < policy.valid_until
    ):
        raise ValueError("review acceptance evaluation is outside its UTC window")
    if len(attempts) != 3:
        raise ValueError("review acceptance requires all three committed slots")
    observations: set[str] = set()
    controllers: set[str] = set()
    provider_ids: set[str] = set()
    cleanup_pins: set[str] = set()
    ledger_entries: dict[str, set[str]] = {}
    ledger_costs: dict[str, int] = {}
    ledgers: dict[str, SpendLedger] = {}
    previous_finish: datetime | None = None
    accepted: list[str] = []
    for commitment, attempt in zip(policy.attempts, attempts, strict=True):
        if attempt is None:
            continue
        critics = ControllerCriticPreview.model_validate_json(
            canonical_bytes(attempt.critics)
        )
        signed = SignedReviewProbeObservation.model_validate_json(
            canonical_bytes(attempt.signed_observation)
        )
        if (
            digest(canonical_bytes(critics)) != commitment.critic_preview_sha256
            or digest(canonical_bytes(attempt.observation_policy))
            != commitment.observation_policy_sha256
            or attempt.authority_policy.sha256 != commitment.authority_policy_sha256
            or critics.authorization.policy != policy.review_policy
            or critics.authorization.total_seconds != policy.total_seconds
            or tuple(
                review_role_profile(request, call.critic_sha256)
                for request, call in zip(
                    critics.requests, critics.envelope.critics, strict=True
                )
            )
            != policy.critics
            or review_role_profile(attempt.judge.model_request) != policy.judge
            or len(attempt.authorizations) != 2
            or any(
                item.authorization.scope.sdk_version != policy.runtime.sdk_version
                or item.authorization.scope.image_id != policy.runtime.image_id
                for item in attempt.authorizations
            )
            or attempt.start.started_at < policy.committed_at
            or (now - signed.observation.observed_at).total_seconds()
            > policy.max_observation_age_seconds
            or (
                previous_finish is not None
                and attempt.start.started_at < previous_finish
            )
        ):
            raise ValueError(
                "review attempt differs from its commitment, profile or chronology"
            )
        authenticated = authenticate_review_probe(
            signed,
            attempt.observation_policy,
            attempt.authority_policy,
            critics,
            attempt.start,
            attempt.judge,
            attempt.authorizations,
            attempt.reviewer,
            attempt.ledger,
            expected_result_sha256=attempt.expected_result_sha256,
            now=now,
        )
        previous_finish = signed.observation.observed_at
        if (
            authenticated.signed_observation_sha256 in observations
            or authenticated.controller_sha256 in controllers
        ):
            raise ValueError("review acceptance cannot count duplicate probe evidence")
        observations.add(authenticated.signed_observation_sha256)
        controllers.add(authenticated.controller_sha256)
        directory = Path(critics.envelope.artifact_directory)
        directories = (
            *(directory / call.ledger_entry_id for call in critics.envelope.critics),
            directory / "judge",
        )
        requests = (*critics.requests, attempt.judge.model_request)
        if len(attempt.lifecycle_directories) != len(requests):
            raise ValueError("review acceptance requires every worker lifecycle")
        for index, (call_directory, lifecycle, request, exchange) in enumerate(
            zip(
                directories,
                attempt.lifecycle_directories,
                requests,
                signed.observation.exchanges,
                strict=True,
            )
        ):
            authorization = attempt.authorizations[
                1 if index == len(critics.requests) else 0
            ].authorization
            verify_review_runtime_exchange(
                exchange, call_directory, lifecycle, request, authorization
            )
            reply = BrokerReply.model_validate_json(
                read_bounded(call_directory / "broker-response.json")
            )
            provider_id = reply.response.get("id")
            if (
                not isinstance(provider_id, str)
                or not provider_id
                or provider_id in provider_ids
                or exchange.cleanup_evidence_sha256 in cleanup_pins
            ):
                raise ValueError(
                    "review acceptance requires distinct responses and workers"
                )
            provider_ids.add(provider_id)
            cleanup_pins.add(exchange.cleanup_evidence_sha256)
        inventory = inspect_review_controller(
            directory,
            attempt.start,
            attempt.ledger,
            expected_judge_preview_sha256=attempt.judge.sha256,
        )
        entries = [item.ledger for item in inventory.critics] + [
            inventory.judge_allowance,
            None if inventory.judge is None else inventory.judge.ledger,
        ]
        ledger_id = attempt.ledger.policy.ledger_id
        if (
            ledger_id in ledgers
            and ledgers[ledger_id].path.resolve() != attempt.ledger.path.resolve()
        ):
            raise ValueError("review acceptance ledger identity has conflicting paths")
        ledgers[ledger_id] = attempt.ledger
        known = ledger_entries.setdefault(ledger_id, set())
        for entry in entries:
            if entry is None or entry.entry_id in known or entry.status != "settled":
                raise ValueError("review acceptance requires distinct settled entries")
            known.add(entry.entry_id)
        ledger_costs[ledger_id] = (
            ledger_costs.get(ledger_id, 0) + inventory.identified_charged_microusd
        )
        accepted.append(authenticated.signed_observation_sha256)
    # A dedicated tranche ledger cannot hide failed/uncertain or unrelated entries.
    # Incomplete inputs remain incomplete; exact ledger coverage is required to pass.
    if len(accepted) == 3:
        for ledger_id, ledger in ledgers.items():
            snapshot = ledger.snapshot()
            if (
                snapshot.blocked
                or snapshot.unresolved_entries
                or snapshot.entries != len(ledger_entries[ledger_id])
                or snapshot.charged_microusd != ledger_costs[ledger_id]
            ):
                raise ValueError(
                    "review acceptance ledger contains unexplained exposure"
                )
    return ReviewAcceptanceResult(
        policy_sha256=digest(canonical_bytes(policy)),
        evaluated_at=now,
        status="accepted" if len(accepted) == 3 else "incomplete",
        qualifying_attempts=len(accepted),
        authenticated_observation_sha256s=tuple(accepted),
    )
