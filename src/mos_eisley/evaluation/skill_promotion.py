"""Independent, expiring authorization for persona-skill evidence promotion."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.skills import SkillIdentity
from mos_eisley.evaluation.adjudication import GradingBatch
from mos_eisley.evaluation.authentication import GradingTrustPolicy
from mos_eisley.evaluation.execution import BlindingMap, ExecutionBatch, RawResultSet
from mos_eisley.evaluation.lineage import DualGradedObservationSet
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionTrustPolicy,
)
from mos_eisley.evaluation.skill_comparison import (
    SealedSkillComparison,
    SkillComparisonReport,
    SkillHoldoutUseClaim,
    verify_authenticated_skill_comparison_report,
    verify_sealed_skill_comparison,
)

_DOMAIN = b"mos-eisley/skill-promotion/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]

type SkillEvaluationLineage = tuple[
    ExecutionBatch,
    BlindingMap,
    RawResultSet,
    GradingBatch,
    DualGradingResolution,
    GradingTrustPolicy,
    ResolutionTrustPolicy,
    DualGradedObservationSet,
]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class TrustedSkillPromotionAuthority(Contract):
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


class SkillPromotionAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_promotion_authority_policy"] = (
        "skill_promotion_authority_policy"
    )
    policy_id: Identifier
    activation_authorized: Literal[False] = False
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_decision_lifetime_seconds: Annotated[int, Field(gt=0, le=604_800)]
    authorities: Annotated[
        tuple[TrustedSkillPromotionAuthority, ...], Field(min_length=1, max_length=20)
    ]

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("skill promotion authority window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "skill promotion authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillPromotionDecision(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_promotion_decision"] = "skill_promotion_decision"
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    authority_policy_sha256: Digest
    sealed_comparison_sha256: Digest
    calibration_report_sha256: Digest
    holdout_report_sha256: Digest
    baseline_prompt_sha256: Digest
    candidate_prompt_sha256: Digest
    candidate_skill: SkillIdentity
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    calibration_gate_passed: bool
    holdout_gate_passed: bool
    criteria_satisfied: bool

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("skill promotion decision window must be positive")
        if self.criteria_satisfied != (
            self.calibration_gate_passed and self.holdout_gate_passed
        ):
            raise ValueError("skill promotion result differs from split gates")
        if self.baseline_prompt_sha256 == self.candidate_prompt_sha256:
            raise ValueError("skill promotion prompts must differ")
        if self.candidate_skill.kind != "persona":
            raise ValueError("skill promotion requires a persona skill")
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillPromotionSignature(Contract):
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


class SignedSkillPromotionDecision(Contract):
    schema_version: Literal[1] = 1
    decision: SkillPromotionDecision
    signature: SkillPromotionSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.decision_sha256 != self.decision.decision_sha256:
            raise ValueError("signature does not identify this skill promotion")
        return self

    @property
    def signed_decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedSkillPromotion(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_skill_promotion"] = "authenticated_skill_promotion"
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    authority_policy_sha256: Digest
    sealed_comparison_sha256: Digest
    calibration_report_sha256: Digest
    holdout_report_sha256: Digest
    candidate_skill: SkillIdentity
    signed_decision: SignedSkillPromotionDecision
    authenticated_at: UtcTimestamp
    valid_until: UtcTimestamp
    promotion_ready: bool

    @field_validator("authenticated_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_sources(self) -> Self:
        decision = self.signed_decision.decision
        if (
            self.authority_policy_sha256 != decision.authority_policy_sha256
            or self.sealed_comparison_sha256 != decision.sealed_comparison_sha256
            or self.calibration_report_sha256 != decision.calibration_report_sha256
            or self.holdout_report_sha256 != decision.holdout_report_sha256
            or self.candidate_skill != decision.candidate_skill
            or self.valid_until != decision.valid_until
            or self.promotion_ready != decision.criteria_satisfied
            or not decision.issued_at <= self.authenticated_at < self.valid_until
        ):
            raise ValueError("authenticated skill promotion source mismatch")
        return self

    @property
    def promotion_receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_skill_promotion_authority(
    authority_id: str, public_key: bytes
) -> TrustedSkillPromotionAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain exactly 32 bytes")
    return TrustedSkillPromotionAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _candidate_skill(sealed: SealedSkillComparison, plan: SweepPlan) -> SkillIdentity:
    matches = [
        route
        for route in plan.routes
        if route.candidate_id == sealed.protocol.candidate_candidate_id
    ]
    if len(matches) != 1 or matches[0].prompt.skill is None:
        raise ValueError("sealed comparison candidate skill is unavailable")
    return matches[0].prompt.skill


def _validate_report_pair(
    sealed: SealedSkillComparison,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
) -> None:
    if calibration_report.split != "calibration" or holdout_report.split != "holdout":
        raise ValueError("skill promotion requires calibration and holdout reports")
    if (
        calibration_report.sealed_comparison_sha256 != sealed.sealed_comparison_sha256
        or holdout_report.sealed_comparison_sha256 != sealed.sealed_comparison_sha256
        or calibration_report.dataset_sha256 != holdout_report.dataset_sha256
        or calibration_report.plan_sha256 != holdout_report.plan_sha256
        or calibration_report.baseline_prompt_sha256
        != holdout_report.baseline_prompt_sha256
        or calibration_report.candidate_prompt_sha256
        != holdout_report.candidate_prompt_sha256
        or calibration_report.dataset_sha256 != sealed.dataset_sha256
        or calibration_report.plan_sha256 != sealed.plan_sha256
        or calibration_report.baseline_candidate_id
        != sealed.protocol.baseline_candidate_id
        or holdout_report.baseline_candidate_id != sealed.protocol.baseline_candidate_id
        or calibration_report.candidate_candidate_id
        != sealed.protocol.candidate_candidate_id
        or holdout_report.candidate_candidate_id
        != sealed.protocol.candidate_candidate_id
        or calibration_report.baseline_prompt_sha256 != sealed.baseline_prompt_sha256
        or calibration_report.candidate_prompt_sha256 != sealed.candidate_prompt_sha256
        or calibration_report.gate != sealed.protocol.gate
        or holdout_report.gate != sealed.protocol.gate
    ):
        raise ValueError("skill promotion report pair provenance mismatch")


def make_skill_promotion_decision(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    sealed: SealedSkillComparison,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    authority_policy: SkillPromotionAuthorityPolicy,
    issued_at: datetime,
    valid_until: datetime,
) -> SkillPromotionDecision:
    """Derive the only signable result from both registered split reports."""

    verify_sealed_skill_comparison(dataset, plan, sealed)
    _validate_report_pair(sealed, calibration_report, holdout_report)
    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    if not (
        authority_policy.valid_from <= issued < expires <= authority_policy.valid_until
    ):
        raise ValueError("skill promotion window exceeds its authority policy")
    if (
        expires - issued
    ).total_seconds() > authority_policy.max_decision_lifetime_seconds:
        raise ValueError("skill promotion decision exceeds its maximum lifetime")
    return SkillPromotionDecision(
        authority_policy_sha256=authority_policy.policy_sha256,
        sealed_comparison_sha256=sealed.sealed_comparison_sha256,
        calibration_report_sha256=(calibration_report.skill_comparison_report_sha256),
        holdout_report_sha256=holdout_report.skill_comparison_report_sha256,
        baseline_prompt_sha256=sealed.baseline_prompt_sha256,
        candidate_prompt_sha256=sealed.candidate_prompt_sha256,
        candidate_skill=_candidate_skill(sealed, plan),
        issued_at=issued,
        valid_until=expires,
        calibration_gate_passed=calibration_report.passes_registered_gate,
        holdout_gate_passed=holdout_report.passes_registered_gate,
        criteria_satisfied=(
            calibration_report.passes_registered_gate
            and holdout_report.passes_registered_gate
        ),
    )


def sign_skill_promotion_decision(
    decision: SkillPromotionDecision,
    signer_id: str,
    private_key: bytes,
) -> SignedSkillPromotionDecision:
    """Sign a derived decision; the CLI never accepts private key material."""

    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (UnsupportedAlgorithm, ValueError):
        raise ValueError("Ed25519 signing unavailable or private key invalid") from None
    public_key = key.public_key().public_bytes_raw()
    return SignedSkillPromotionDecision(
        decision=decision,
        signature=SkillPromotionSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            decision_sha256=decision.decision_sha256,
            signature_base64=base64.b64encode(
                key.sign(_DOMAIN + canonical_bytes(decision))
            ).decode("ascii"),
        ),
    )


def _validate_authority_separation(
    authority_policy: SkillPromotionAuthorityPolicy,
    lineages: tuple[SkillEvaluationLineage, SkillEvaluationLineage],
) -> None:
    excluded_ids = {
        item.adjudicator_id for lineage in lineages for item in lineage[5].adjudicators
    } | {item.adjudicator_id for lineage in lineages for item in lineage[6].resolvers}
    excluded_keys = {
        item.public_key_sha256
        for lineage in lineages
        for item in lineage[5].adjudicators
    } | {
        item.public_key_sha256 for lineage in lineages for item in lineage[6].resolvers
    }
    if any(
        item.authority_id in excluded_ids or item.public_key_sha256 in excluded_keys
        for item in authority_policy.authorities
    ):
        raise ValueError("skill promotion authority must be independent of evaluation")


def authenticate_skill_promotion(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    signed: SignedSkillPromotionDecision,
    authority_policy: SkillPromotionAuthorityPolicy,
    at: datetime,
) -> AuthenticatedSkillPromotion:
    """Recompute both reports, enforce separation/expiry, and verify signature."""

    current = _require_utc(at)
    decision = signed.decision
    if not (
        authority_policy.valid_from
        <= decision.issued_at
        <= current
        < decision.valid_until
        <= authority_policy.valid_until
    ):
        raise ValueError("skill promotion decision or authority policy is not current")
    if (
        decision.valid_until - decision.issued_at
    ).total_seconds() > authority_policy.max_decision_lifetime_seconds:
        raise ValueError("skill promotion decision exceeds its maximum lifetime")
    verify_authenticated_skill_comparison_report(
        dataset,
        plan,
        *calibration,
        sealed,
        None,
        calibration_report,
    )
    verify_authenticated_skill_comparison_report(
        dataset,
        plan,
        *holdout,
        sealed,
        holdout_claim,
        holdout_report,
    )
    expected = make_skill_promotion_decision(
        dataset,
        plan,
        sealed,
        calibration_report,
        holdout_report,
        authority_policy,
        signed.decision.issued_at,
        signed.decision.valid_until,
    )
    if signed.decision != expected:
        raise ValueError("signed skill promotion decision differs from recomputation")
    _validate_authority_separation(authority_policy, (calibration, holdout))
    matches = [
        item
        for item in authority_policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("signer is not trusted by the skill promotion policy")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("signature key differs from skill promotion policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(decision),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("skill promotion signature verification failed") from None
    return AuthenticatedSkillPromotion(
        authority_policy_sha256=authority_policy.policy_sha256,
        sealed_comparison_sha256=sealed.sealed_comparison_sha256,
        calibration_report_sha256=(calibration_report.skill_comparison_report_sha256),
        holdout_report_sha256=holdout_report.skill_comparison_report_sha256,
        candidate_skill=decision.candidate_skill,
        signed_decision=signed,
        authenticated_at=current,
        valid_until=decision.valid_until,
        promotion_ready=decision.criteria_satisfied,
    )


def verify_authenticated_skill_promotion(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    artifact: AuthenticatedSkillPromotion,
    authority_policy: SkillPromotionAuthorityPolicy,
) -> None:
    """Recompute a receipt at its recorded authentication time."""

    rebuilt = authenticate_skill_promotion(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        artifact.signed_decision,
        authority_policy,
        artifact.authenticated_at,
    )
    if rebuilt != artifact:
        raise ValueError("authenticated skill promotion provenance mismatch")
