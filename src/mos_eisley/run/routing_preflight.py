"""Trusted read-only preflight against the latest anchored control state."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan
from mos_eisley.evaluation.routing_activation import (
    RoutingActivationAuthorityPolicy,
    RoutingActivationEligibility,
    SignedRoutingActivationControl,
    SignedRoutingActivationPolicy,
    SignedRoutingOperationalSnapshot,
    verify_routing_activation_eligibility,
)
from mos_eisley.evaluation.routing_calibration import RoutingCalibrationReport
from mos_eisley.evaluation.routing_holdout import (
    FrozenPolicyHoldoutReport,
    HoldoutUseClaim,
    RoutingLineage,
)
from mos_eisley.evaluation.routing_policy import FrozenCandidateRoutingPolicy
from mos_eisley.evaluation.routing_promotion import (
    AuthenticatedRoutingPromotion,
    RoutingPromotionAuthorityPolicy,
)
from mos_eisley.evaluation.routing_promotion_policy import RoutingPromotionPolicy
from mos_eisley.evaluation.routing_protocol import (
    PromptFeatureManifest,
    SealedRoutingStudy,
)
from mos_eisley.run.activation_control import RoutingControlAnchor

UtcTimestamp = Annotated[datetime, Field()]


@dataclass(frozen=True)
class RoutingRuntimeSources:
    dataset: EvaluationDataset
    plan: SweepPlan
    calibration: RoutingLineage
    holdout: RoutingLineage
    manifest: PromptFeatureManifest
    sealed_study: SealedRoutingStudy
    calibration_report: RoutingCalibrationReport
    candidate_policy: FrozenCandidateRoutingPolicy
    promotion_policy: RoutingPromotionPolicy
    claim: HoldoutUseClaim
    holdout_report: FrozenPolicyHoldoutReport
    promotion: AuthenticatedRoutingPromotion
    promotion_authorities: RoutingPromotionAuthorityPolicy
    signed_activation_policy: SignedRoutingActivationPolicy
    signed_snapshot: SignedRoutingOperationalSnapshot
    signed_control: SignedRoutingActivationControl
    activation_authorities: RoutingActivationAuthorityPolicy
    eligibility: RoutingActivationEligibility
    control_anchor: RoutingControlAnchor


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class RoutingRuntimePreflight(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["routing_runtime_preflight"] = "routing_runtime_preflight"
    candidate_policy_sha256: Digest
    promotion_receipt_sha256: Digest
    activation_eligibility_sha256: Digest
    control_anchor_policy_sha256: Digest
    anchored_control_entry_sha256: Digest
    checked_at: UtcTimestamp
    valid_until: UtcTimestamp
    eligible_candidate_ids: Annotated[
        tuple[Digest, ...], Field(min_length=1, max_length=256)
    ]
    unavailable_action: Literal["role_fallback", "fail_closed"]
    preflight_passed: Literal[True] = True
    allow_model_substitution: Literal[False] = False
    dispatch_authorized: Literal[False] = False
    runtime_activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("checked_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_current_window(self) -> Self:
        if self.valid_until <= self.checked_at:
            raise ValueError("runtime preflight validity window must be positive")
        if (
            tuple(sorted(set(self.eligible_candidate_ids)))
            != self.eligible_candidate_ids
        ):
            raise ValueError("runtime preflight candidates must be unique and sorted")
        return self

    @property
    def preflight_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime | None = None) -> None:
        current = now if now is not None else datetime.now(UTC)
        _require_utc(current)
        if not self.checked_at <= current < self.valid_until:
            raise ValueError("routing runtime preflight is outside its validity window")


def perform_routing_runtime_preflight(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: RoutingLineage,
    holdout: RoutingLineage,
    manifest: PromptFeatureManifest,
    sealed_study: SealedRoutingStudy,
    calibration_report: RoutingCalibrationReport,
    candidate_policy: FrozenCandidateRoutingPolicy,
    promotion_policy: RoutingPromotionPolicy,
    claim: HoldoutUseClaim,
    holdout_report: FrozenPolicyHoldoutReport,
    promotion: AuthenticatedRoutingPromotion,
    promotion_authorities: RoutingPromotionAuthorityPolicy,
    signed_activation_policy: SignedRoutingActivationPolicy,
    signed_snapshot: SignedRoutingOperationalSnapshot,
    signed_control: SignedRoutingActivationControl,
    activation_authorities: RoutingActivationAuthorityPolicy,
    eligibility: RoutingActivationEligibility,
    control_anchor: RoutingControlAnchor,
    now: datetime,
) -> RoutingRuntimePreflight:
    """Reverify every source and require the exact latest anchored control state."""
    _require_utc(now)
    verify_routing_activation_eligibility(
        dataset,
        plan,
        calibration,
        holdout,
        manifest,
        sealed_study,
        calibration_report,
        candidate_policy,
        promotion_policy,
        claim,
        holdout_report,
        promotion,
        promotion_authorities,
        signed_activation_policy,
        signed_snapshot,
        signed_control,
        activation_authorities,
        eligibility,
        now,
    )
    if (
        control_anchor.policy.policy_sha256
        != signed_activation_policy.policy.control_anchor_policy_sha256
    ):
        raise ValueError("routing control anchor policy is not the signed policy")
    anchored = control_anchor.require_latest(
        signed_control, activation_authorities, now
    )
    valid_until = min(
        eligibility.valid_until,
        signed_control.control.valid_until,
        now
        + timedelta(
            seconds=(signed_activation_policy.policy.max_runtime_preflight_age_seconds)
        ),
    )
    return RoutingRuntimePreflight(
        candidate_policy_sha256=candidate_policy.candidate_policy_sha256,
        promotion_receipt_sha256=promotion.promotion_receipt_sha256,
        activation_eligibility_sha256=eligibility.eligibility_sha256,
        control_anchor_policy_sha256=control_anchor.policy.policy_sha256,
        anchored_control_entry_sha256=anchored.anchor_entry_sha256,
        checked_at=now,
        valid_until=valid_until,
        eligible_candidate_ids=eligibility.eligible_candidate_ids,
        unavailable_action=eligibility.unavailable_action,
    )


def verify_routing_runtime_preflight(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: RoutingLineage,
    holdout: RoutingLineage,
    manifest: PromptFeatureManifest,
    sealed_study: SealedRoutingStudy,
    calibration_report: RoutingCalibrationReport,
    candidate_policy: FrozenCandidateRoutingPolicy,
    promotion_policy: RoutingPromotionPolicy,
    claim: HoldoutUseClaim,
    holdout_report: FrozenPolicyHoldoutReport,
    promotion: AuthenticatedRoutingPromotion,
    promotion_authorities: RoutingPromotionAuthorityPolicy,
    signed_activation_policy: SignedRoutingActivationPolicy,
    signed_snapshot: SignedRoutingOperationalSnapshot,
    signed_control: SignedRoutingActivationControl,
    activation_authorities: RoutingActivationAuthorityPolicy,
    eligibility: RoutingActivationEligibility,
    control_anchor: RoutingControlAnchor,
    artifact: RoutingRuntimePreflight,
    now: datetime | None = None,
) -> None:
    rebuilt = perform_routing_runtime_preflight(
        dataset,
        plan,
        calibration,
        holdout,
        manifest,
        sealed_study,
        calibration_report,
        candidate_policy,
        promotion_policy,
        claim,
        holdout_report,
        promotion,
        promotion_authorities,
        signed_activation_policy,
        signed_snapshot,
        signed_control,
        activation_authorities,
        eligibility,
        control_anchor,
        artifact.checked_at,
    )
    if rebuilt != artifact:
        raise ValueError("routing runtime preflight provenance mismatch")
    artifact.check_current(now)


def verify_routing_runtime_sources(
    sources: RoutingRuntimeSources,
    artifact: RoutingRuntimePreflight,
    now: datetime,
) -> None:
    """Reverify a runtime preflight from its complete empirical source chain."""

    verify_routing_runtime_preflight(
        sources.dataset,
        sources.plan,
        sources.calibration,
        sources.holdout,
        sources.manifest,
        sources.sealed_study,
        sources.calibration_report,
        sources.candidate_policy,
        sources.promotion_policy,
        sources.claim,
        sources.holdout_report,
        sources.promotion,
        sources.promotion_authorities,
        sources.signed_activation_policy,
        sources.signed_snapshot,
        sources.signed_control,
        sources.activation_authorities,
        sources.eligibility,
        sources.control_anchor,
        artifact,
        now,
    )


@contextmanager
def guard_routing_runtime_sources(
    sources: RoutingRuntimeSources,
    artifact: RoutingRuntimePreflight,
    now: datetime,
) -> Generator[None, None, None]:
    """Reverify full lineage, then hold its exact latest control through a commit."""

    verify_routing_runtime_sources(sources, artifact, now)
    with sources.control_anchor.guard_latest(
        sources.signed_control, sources.activation_authorities, now
    ) as latest:
        if latest.anchor_entry_sha256 != artifact.anchored_control_entry_sha256:
            raise ValueError("routing preflight is no longer bound to latest control")
        yield
