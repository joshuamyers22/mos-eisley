"""Authenticate an independent observer's account of one completed review probe."""

import base64
import binascii
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    SignedReviewConformanceAuthorization,
    review_conformance_scope,
    verify_review_conformance_authorization,
)
from mos_eisley.run.review_controller import (
    ControllerCriticPreview,
    ControllerJudgePreview,
    ControllerStart,
)
from mos_eisley.run.review_controller_inspection import inspect_review_controller
from mos_eisley.run.review_verdict import verify_retained_review_result
from mos_eisley.run.spend_ledger import SpendLedger

_DOMAIN = b"mos-eisley/review-conformance-observation/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("review observation timestamps require explicit UTC")
    return value


def _signature(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("invalid review observation signature encoding") from None
    if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("noncanonical review observation signature encoding")
    return raw


class ReviewObservationPolicy(Contract):
    """Select before execution; authentication requires the independent policy pin."""

    schema_version: Literal[1] = 1
    mode: Literal["review_observation_policy"] = "review_observation_policy"
    policy_id: Identifier
    authority_policy_sha256: Digest
    critic_preview_sha256: Digest
    valid_from: datetime
    valid_until: datetime
    max_observation_age_seconds: Annotated[int, Field(gt=0, le=2_592_000)]
    live_review_activation_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def window(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("review observation policy window must be positive")
        return self


class ReviewObservedExchange(Contract):
    """Observer-supplied timing and evidence pins; never inferred from a verdict."""

    model_request_sha256: Digest
    count_started_at: datetime
    count_finished_at: datetime
    generation_started_at: datetime
    generation_finished_at: datetime
    transport_evidence_sha256: Digest
    cleanup_evidence_sha256: Digest

    @field_validator(
        "count_started_at",
        "count_finished_at",
        "generation_started_at",
        "generation_finished_at",
    )
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if not (
            self.count_started_at
            <= self.count_finished_at
            <= self.generation_started_at
            <= self.generation_finished_at
        ):
            raise ValueError("review observation exchange times are out of order")
        return self


class ReviewProbeObservation(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_probe_observation"] = "review_probe_observation"
    observation_policy_sha256: Digest
    authority_policy_sha256: Digest
    critic_preview_sha256: Digest
    controller_start_sha256: Digest
    judge_preview_sha256: Digest
    critic_authorization_sha256: Digest
    judge_authorization_sha256: Digest
    result_sha256: Digest
    exchanges: Annotated[
        tuple[ReviewObservedExchange, ...], Field(min_length=2, max_length=9)
    ]
    observed_at: datetime
    charged_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    credentialed_exchange_attested: Literal[True] = True
    explicit_local_approvals_attested: Literal[True] = True
    current_guidance_at_dispatch_attested: Literal[True] = True
    official_sdk_and_bounded_transport_attested: Literal[True] = True
    pinned_isolated_workers_and_cleanup_attested: Literal[True] = True
    automatic_retries: Literal[0] = 0
    provider_storage_requested: Literal[False] = False
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
    repeated_conformance_proven: Literal[False] = False
    live_review_activation_authorized: Literal[False] = False

    @field_validator("observed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)


class SignedReviewProbeObservation(Contract):
    schema_version: Literal[1] = 1
    observation: ReviewProbeObservation
    signer_id: Identifier
    public_key_sha256: Digest
    signature_base64: Annotated[str, Field(min_length=88, max_length=88)]

    @model_validator(mode="after")
    def encoded_signature(self) -> Self:
        _signature(self.signature_base64)
        return self


class AuthenticatedReviewProbe(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_review_probe"] = "authenticated_review_probe"
    signed_observation_sha256: Digest
    observation_policy_sha256: Digest
    controller_sha256: Digest
    result_sha256: Digest
    observer_authenticated: Literal[True] = True
    local_artifacts_verified: Literal[True] = True
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
    repeated_conformance_proven: Literal[False] = False
    live_review_activation_authorized: Literal[False] = False
    retry_authorized: Literal[False] = False


def make_review_probe_observation(
    policy: ReviewObservationPolicy,
    authority_policy: ReviewConformanceAuthorityPolicy,
    critics: ControllerCriticPreview,
    start: ControllerStart,
    judge: ControllerJudgePreview,
    authorizations: tuple[
        SignedReviewConformanceAuthorization, SignedReviewConformanceAuthorization
    ],
    reviewer: ModelReviewer,
    ledger: SpendLedger,
    *,
    expected_result_sha256: str,
    exchanges: tuple[ReviewObservedExchange, ...],
    observed_at: datetime,
) -> ReviewProbeObservation:
    """Reconstruct local provenance; an observer must independently attest runtime."""
    policy = ReviewObservationPolicy.model_validate_json(canonical_bytes(policy))
    authority_policy = ReviewConformanceAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    critics = ControllerCriticPreview.model_validate_json(canonical_bytes(critics))
    start = ControllerStart.model_validate_json(canonical_bytes(start))
    judge = ControllerJudgePreview.model_validate_json(canonical_bytes(judge))
    exchanges = tuple(
        ReviewObservedExchange.model_validate_json(canonical_bytes(item))
        for item in exchanges
    )
    observed_at = _utc(observed_at)
    if (
        policy.authority_policy_sha256 != authority_policy.sha256
        or policy.critic_preview_sha256 != digest(canonical_bytes(critics))
        or not policy.valid_from
        <= _utc(start.started_at)
        <= observed_at
        < policy.valid_until
        or len(exchanges) != len(critics.requests) + 1
        or len(authorizations) != 2
    ):
        raise ValueError(
            "review observation differs from its selected policy or roster"
        )
    signatures = tuple(
        SignedReviewConformanceAuthorization.model_validate_json(canonical_bytes(item))
        for item in authorizations
    )
    runtime = signatures[0].authorization.scope
    critic_scope = review_conformance_scope(
        critics, sdk_version=runtime.sdk_version, image_id=runtime.image_id
    )
    judge_scope = review_conformance_scope(
        critics,
        sdk_version=runtime.sdk_version,
        image_id=runtime.image_id,
        judge=judge,
        start=start,
    )
    for index, exchange in enumerate(exchanges):
        is_judge = index == len(critics.requests)
        request = judge.model_request if is_judge else critics.requests[index]
        signed = signatures[1 if is_judge else 0]
        scope = judge_scope if is_judge else critic_scope
        if (
            exchange.model_request_sha256 != digest(canonical_bytes(request))
            or not start.started_at
            <= exchange.count_started_at
            <= exchange.generation_finished_at
            < start.expires_at
            or exchange.generation_finished_at > observed_at
            or (
                exchange.generation_finished_at - exchange.count_started_at
            ).total_seconds()
            > 60
        ):
            raise ValueError("review observation request or execution window changed")
        # The ordered interval must fit entirely inside the historical grant.
        for at in (exchange.count_started_at, exchange.generation_finished_at):
            verify_review_conformance_authorization(signed, authority_policy, scope, at)
    if (
        max(item.generation_finished_at for item in exchanges[:-1])
        > exchanges[-1].count_started_at
    ):
        raise ValueError("judge observation precedes critic completion")
    for field in ("transport_evidence_sha256", "cleanup_evidence_sha256"):
        if len({getattr(item, field) for item in exchanges}) != len(exchanges):
            raise ValueError("review observations require distinct per-call evidence")
    inventory = inspect_review_controller(
        Path(critics.envelope.artifact_directory),
        start,
        ledger,
        expected_judge_preview_sha256=judge.sha256,
    )
    calls = (*inventory.critics, inventory.judge)
    if (
        inventory.recorded_phase != "finished"
        or not inventory.spending_inventory_complete
        or inventory.result_sha256 != expected_result_sha256
        or any(
            item is None or item.ledger is None or item.ledger.status != "settled"
            for item in calls
        )
    ):
        raise ValueError("review observation requires a completed, settled controller")
    result = verify_retained_review_result(
        critics.envelope, reviewer, ledger, judge.authorization, expected_result_sha256
    )
    if result.result.verdict.decision == "infrastructure_error" or any(
        item.error is not None for item in result.result.critics
    ):
        raise ValueError("review observation requires successful critics and judge")
    return ReviewProbeObservation(
        observation_policy_sha256=digest(canonical_bytes(policy)),
        authority_policy_sha256=authority_policy.sha256,
        critic_preview_sha256=digest(canonical_bytes(critics)),
        controller_start_sha256=digest(canonical_bytes(start)),
        judge_preview_sha256=judge.sha256,
        critic_authorization_sha256=digest(canonical_bytes(signatures[0])),
        judge_authorization_sha256=digest(canonical_bytes(signatures[1])),
        result_sha256=expected_result_sha256,
        exchanges=exchanges,
        observed_at=observed_at,
        charged_microusd=inventory.identified_charged_microusd,
    )


def sign_review_probe_observation(
    observation: ReviewProbeObservation, signer_id: str, key: Ed25519PrivateKey
) -> SignedReviewProbeObservation:
    observation = ReviewProbeObservation.model_validate_json(
        canonical_bytes(observation)
    )
    return SignedReviewProbeObservation(
        observation=observation,
        signer_id=signer_id,
        public_key_sha256=digest(key.public_key().public_bytes_raw()),
        signature_base64=base64.b64encode(
            key.sign(_DOMAIN + canonical_bytes(observation))
        ).decode("ascii"),
    )


def authenticate_review_probe(
    signed: SignedReviewProbeObservation,
    policy: ReviewObservationPolicy,
    authority_policy: ReviewConformanceAuthorityPolicy,
    critics: ControllerCriticPreview,
    start: ControllerStart,
    judge: ControllerJudgePreview,
    authorizations: tuple[
        SignedReviewConformanceAuthorization, SignedReviewConformanceAuthorization
    ],
    reviewer: ModelReviewer,
    ledger: SpendLedger,
    *,
    expected_result_sha256: str,
    now: datetime,
) -> AuthenticatedReviewProbe:
    """Read-only historical verification against independently selected inputs."""
    signed = SignedReviewProbeObservation.model_validate_json(canonical_bytes(signed))
    policy = ReviewObservationPolicy.model_validate_json(canonical_bytes(policy))
    authority_policy = ReviewConformanceAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    now = _utc(now)
    age = (now - signed.observation.observed_at).total_seconds()
    if not 0 <= age <= policy.max_observation_age_seconds:
        raise ValueError("review probe observation is stale or from the future")
    enrolled = [
        item
        for item in authority_policy.observers
        if item.signer_id == signed.signer_id
        and item.key_sha256 == signed.public_key_sha256
    ]
    if len(enrolled) != 1:
        raise ValueError("review probe observer is not independently enrolled")
    try:
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(enrolled[0].public_key_base64)
        ).verify(
            _signature(signed.signature_base64),
            _DOMAIN + canonical_bytes(signed.observation),
        )
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid review probe observation signature") from None
    expected = make_review_probe_observation(
        policy,
        authority_policy,
        critics,
        start,
        judge,
        authorizations,
        reviewer,
        ledger,
        expected_result_sha256=expected_result_sha256,
        exchanges=signed.observation.exchanges,
        observed_at=signed.observation.observed_at,
    )
    if signed.observation != expected:
        raise ValueError("review probe observation differs from reconstructed evidence")
    return AuthenticatedReviewProbe(
        signed_observation_sha256=digest(canonical_bytes(signed)),
        observation_policy_sha256=digest(canonical_bytes(policy)),
        controller_sha256=critics.sha256,
        result_sha256=expected_result_sha256,
    )
