"""Independent authorization for a pre-registered routing promotion decision."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.evaluation.authentication import GradingTrustPolicy
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan
from mos_eisley.evaluation.resolution import ResolutionTrustPolicy
from mos_eisley.evaluation.routing_calibration import RoutingCalibrationReport
from mos_eisley.evaluation.routing_holdout import (
    FrozenPolicyHoldoutReport,
    HoldoutUseClaim,
    RoutingLineage,
    verify_frozen_policy_holdout_report,
)
from mos_eisley.evaluation.routing_policy import FrozenCandidateRoutingPolicy
from mos_eisley.evaluation.routing_promotion_policy import RoutingPromotionPolicy
from mos_eisley.evaluation.routing_protocol import (
    PromptFeatureManifest,
    SealedRoutingStudy,
)

_DOMAIN = b"mos-eisley/routing-promotion/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
CheckName = Literal[
    "calibrated_policy_coverage",
    "selected_adequacy_rate",
    "under_routing_rate",
    "fail_closed_rate",
    "missed_adequate_alternative_rate",
    "regret_observation_rate",
    "mean_cost_regret_microusd",
    "mean_latency_regret_ms",
]
Comparator = Literal["greater_than_or_equal", "less_than_or_equal"]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


class TrustedPromotionAuthority(Contract):
    authority_id: Identifier
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32, "public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32, "public key"))


class RoutingPromotionAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    policy_id: Identifier
    authorities: Annotated[
        tuple[TrustedPromotionAuthority, ...], Field(min_length=1, max_length=20)
    ]

    @model_validator(mode="after")
    def canonical_unique_authorities(self) -> Self:
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "promotion authorities must have sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class RoutingPromotionCheck(Contract):
    name: CheckName
    comparator: Comparator
    observed: Annotated[float, Field(ge=0, le=1_000_000_000_000_000)] | None
    threshold: Annotated[float, Field(ge=0, le=1_000_000_000_000_000)]
    passed: bool


class RoutingPromotionDecision(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["pre_registered_routing_promotion_decision"] = (
        "pre_registered_routing_promotion_decision"
    )
    candidate_policy_sha256: Digest
    holdout_report_sha256: Digest
    promotion_policy_sha256: Digest
    checks: Annotated[
        tuple[RoutingPromotionCheck, ...], Field(min_length=8, max_length=8)
    ]
    threshold_result: Literal["satisfied", "failed"]
    criteria_satisfied: bool
    activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def canonical_and_consistent(self) -> Self:
        names = tuple(item.name for item in self.checks)
        expected = (
            "calibrated_policy_coverage",
            "selected_adequacy_rate",
            "under_routing_rate",
            "fail_closed_rate",
            "missed_adequate_alternative_rate",
            "regret_observation_rate",
            "mean_cost_regret_microusd",
            "mean_latency_regret_ms",
        )
        if names != expected:
            raise ValueError("routing promotion checks are incomplete or out of order")
        passed = all(item.passed for item in self.checks)
        if (
            self.criteria_satisfied != passed
            or (self.threshold_result == "satisfied") != passed
        ):
            raise ValueError("routing promotion result differs from its checks")
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class RoutingPromotionSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    decision_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedRoutingPromotionDecision(Contract):
    schema_version: Literal[1] = 1
    decision: RoutingPromotionDecision
    signature: RoutingPromotionSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.decision_sha256 != self.decision.decision_sha256:
            raise ValueError("signature does not identify this promotion decision")
        return self

    @property
    def signed_decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedRoutingPromotion(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_routing_promotion"] = "authenticated_routing_promotion"
    candidate_policy_sha256: Digest
    holdout_report_sha256: Digest
    promotion_policy_sha256: Digest
    authority_policy_sha256: Digest
    signed_decision: SignedRoutingPromotionDecision
    promotion_ready: bool
    activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bound_sources(self) -> Self:
        decision = self.signed_decision.decision
        if (
            self.candidate_policy_sha256 != decision.candidate_policy_sha256
            or self.holdout_report_sha256 != decision.holdout_report_sha256
            or self.promotion_policy_sha256 != decision.promotion_policy_sha256
            or self.promotion_ready != decision.criteria_satisfied
        ):
            raise ValueError("authenticated routing promotion source mismatch")
        return self

    @property
    def promotion_receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_promotion_authority(
    authority_id: str, public_key: bytes
) -> TrustedPromotionAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain exactly 32 bytes")
    return TrustedPromotionAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _check(
    name: CheckName,
    comparator: Comparator,
    observed: float | None,
    threshold: float,
) -> RoutingPromotionCheck:
    passed = observed is not None and (
        observed >= threshold
        if comparator == "greater_than_or_equal"
        else observed <= threshold
    )
    return RoutingPromotionCheck(
        name=name,
        comparator=comparator,
        observed=observed,
        threshold=threshold,
        passed=passed,
    )


def make_routing_promotion_decision(
    report: FrozenPolicyHoldoutReport,
    policy: RoutingPromotionPolicy,
) -> RoutingPromotionDecision:
    """Apply only the thresholds pinned into the holdout report."""
    if (
        report.promotion_policy_sha256 != policy.promotion_policy_sha256
        or report.candidate_policy_sha256 != policy.candidate_policy_sha256
    ):
        raise ValueError("routing promotion decision provenance mismatch")
    summary = report.summary
    profiles = summary.profiles
    checks = (
        _check(
            "calibrated_policy_coverage",
            "greater_than_or_equal",
            summary.calibrated_policy_coverage,
            policy.min_calibrated_policy_coverage,
        ),
        _check(
            "selected_adequacy_rate",
            "greater_than_or_equal",
            summary.selected_adequacy_rate,
            policy.min_selected_adequacy_rate,
        ),
        _check(
            "under_routing_rate",
            "less_than_or_equal",
            summary.under_routing_rate,
            policy.max_under_routing_rate,
        ),
        _check(
            "fail_closed_rate",
            "less_than_or_equal",
            summary.fail_closed_profiles / profiles,
            policy.max_fail_closed_rate,
        ),
        _check(
            "missed_adequate_alternative_rate",
            "less_than_or_equal",
            (
                summary.under_routed_profiles
                + summary.unserved_with_adequate_alternative_profiles
            )
            / profiles,
            policy.max_missed_adequate_alternative_rate,
        ),
        _check(
            "regret_observation_rate",
            "greater_than_or_equal",
            summary.regret_observed_profiles / profiles,
            policy.min_regret_observation_rate,
        ),
        _check(
            "mean_cost_regret_microusd",
            "less_than_or_equal",
            summary.mean_cost_regret_microusd,
            policy.max_mean_cost_regret_microusd,
        ),
        _check(
            "mean_latency_regret_ms",
            "less_than_or_equal",
            summary.mean_latency_regret_ms,
            policy.max_mean_latency_regret_ms,
        ),
    )
    passed = all(item.passed for item in checks)
    return RoutingPromotionDecision(
        candidate_policy_sha256=report.candidate_policy_sha256,
        holdout_report_sha256=report.holdout_report_sha256,
        promotion_policy_sha256=policy.promotion_policy_sha256,
        checks=checks,
        threshold_result="satisfied" if passed else "failed",
        criteria_satisfied=passed,
    )


def sign_routing_promotion_decision(
    decision: RoutingPromotionDecision,
    signer_id: str,
    private_key: bytes,
) -> SignedRoutingPromotionDecision:
    """Sign a derived decision; the CLI never accepts private key material."""
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (UnsupportedAlgorithm, ValueError):
        raise ValueError("Ed25519 signing unavailable or private key invalid") from None
    public_key = key.public_key().public_bytes_raw()
    return SignedRoutingPromotionDecision(
        decision=decision,
        signature=RoutingPromotionSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            decision_sha256=decision.decision_sha256,
            signature_base64=base64.b64encode(
                key.sign(_DOMAIN + canonical_bytes(decision))
            ).decode("ascii"),
        ),
    )


def _validate_authority_separation(
    authority_policy: RoutingPromotionAuthorityPolicy,
    grading_policies: tuple[GradingTrustPolicy, ...],
    resolution_policies: tuple[ResolutionTrustPolicy, ...],
) -> None:
    excluded_ids = {
        item.adjudicator_id
        for policy in grading_policies
        for item in policy.adjudicators
    } | {
        item.adjudicator_id
        for policy in resolution_policies
        for item in policy.resolvers
    }
    excluded_keys = {
        item.public_key_sha256
        for policy in grading_policies
        for item in policy.adjudicators
    } | {
        item.public_key_sha256
        for policy in resolution_policies
        for item in policy.resolvers
    }
    if any(
        item.authority_id in excluded_ids or item.public_key_sha256 in excluded_keys
        for item in authority_policy.authorities
    ):
        raise ValueError(
            "promotion authorities must be independent of graders and resolvers"
        )


def authenticate_routing_promotion(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: RoutingLineage,
    holdout: RoutingLineage,
    manifest: PromptFeatureManifest,
    sealed_study: SealedRoutingStudy,
    calibration_report: RoutingCalibrationReport,
    candidate_policy: FrozenCandidateRoutingPolicy,
    claim: HoldoutUseClaim,
    report: FrozenPolicyHoldoutReport,
    promotion_policy: RoutingPromotionPolicy,
    signed: SignedRoutingPromotionDecision,
    authority_policy: RoutingPromotionAuthorityPolicy,
) -> AuthenticatedRoutingPromotion:
    """Recompute thresholds, enforce independence, and verify one trusted signature."""
    verify_frozen_policy_holdout_report(
        dataset,
        plan,
        *calibration,
        *holdout,
        manifest,
        sealed_study,
        calibration_report,
        candidate_policy,
        promotion_policy,
        claim,
        report,
    )
    expected = make_routing_promotion_decision(report, promotion_policy)
    if signed.decision != expected:
        raise ValueError("signed routing promotion decision differs from recomputation")
    _validate_authority_separation(
        authority_policy,
        (calibration[5], holdout[5]),
        (calibration[6], holdout[6]),
    )
    matches = [
        item
        for item in authority_policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("signer is not trusted by the promotion authority policy")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("signature public key differs from promotion authority policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(signed.decision),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("routing promotion signature verification failed") from None
    return AuthenticatedRoutingPromotion(
        candidate_policy_sha256=report.candidate_policy_sha256,
        holdout_report_sha256=report.holdout_report_sha256,
        promotion_policy_sha256=promotion_policy.promotion_policy_sha256,
        authority_policy_sha256=authority_policy.policy_sha256,
        signed_decision=signed,
        promotion_ready=signed.decision.criteria_satisfied,
    )


def verify_authenticated_routing_promotion(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: RoutingLineage,
    holdout: RoutingLineage,
    manifest: PromptFeatureManifest,
    sealed_study: SealedRoutingStudy,
    calibration_report: RoutingCalibrationReport,
    candidate_policy: FrozenCandidateRoutingPolicy,
    claim: HoldoutUseClaim,
    report: FrozenPolicyHoldoutReport,
    promotion_policy: RoutingPromotionPolicy,
    artifact: AuthenticatedRoutingPromotion,
    authority_policy: RoutingPromotionAuthorityPolicy,
) -> None:
    rebuilt = authenticate_routing_promotion(
        dataset,
        plan,
        calibration,
        holdout,
        manifest,
        sealed_study,
        calibration_report,
        candidate_policy,
        claim,
        report,
        promotion_policy,
        artifact.signed_decision,
        authority_policy,
    )
    if rebuilt != artifact:
        raise ValueError("authenticated routing promotion provenance mismatch")
