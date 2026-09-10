"""Signed post-selection health and drift evidence without runtime authority."""

from __future__ import annotations

import base64
import binascii
import math
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.skills import SkillIdentity, SkillPackageArchive
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan
from mos_eisley.evaluation.skill_comparison import (
    MAX_DELTA_LATENCY_MS,
    MAX_DELTA_MICROUSD,
    SealedSkillComparison,
    SkillComparisonReport,
    SkillHoldoutUseClaim,
)
from mos_eisley.evaluation.skill_promotion import (
    AuthenticatedSkillPromotion,
    SkillEvaluationLineage,
    SkillPromotionAuthorityPolicy,
)
from mos_eisley.run.skill_default import (
    SkillDefaultAuthorityPolicy,
    SkillDefaultPointer,
    SkillDefaultStore,
)
from mos_eisley.run.skill_installation import SkillInstallationAuthorityPolicy
from mos_eisley.run.skill_installed_store import SkillInstalledStore
from mos_eisley.run.skill_release import SkillReleaseEvidence
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAuthorityPolicy,
    authenticate_skill_release_control,
    verify_authenticated_skill_release_control,
)

_POLICY_DOMAIN = b"mos-eisley/skill-health-policy/v1\x00"
_OBSERVATION_DOMAIN = b"mos-eisley/skill-health-observation/v1\x00"
_PPM = 1_000_000
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]
SignedRate = Annotated[int, Field(ge=-_PPM, le=_PPM)]


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


def _lower_ppm(value: float) -> int:
    """Conservatively convert a lower-bound requirement to integer ppm."""
    return math.ceil(value * _PPM)


def _upper_ppm(value: float) -> int:
    """Conservatively convert an upper-bound requirement to integer ppm."""
    return math.floor(value * _PPM)


class TrustedSkillHealthAuthority(Contract):
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


class SkillHealthAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_health_authority_policy"] = "skill_health_authority_policy"
    policy_id: Identifier
    default_authority_policy_sha256: Digest
    default_store_policy_sha256: Digest
    control_anchor_policy_sha256: Digest
    promotion_authority_policy_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    authorities: Annotated[
        tuple[TrustedSkillHealthAuthority, ...], Field(min_length=2, max_length=20)
    ]
    runtime_dispatch_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    automatic_rollback_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("skill health authority window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "skill health authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillHealthThresholds(Contract):
    schema_version: Literal[1] = 1
    minimum_independence_groups: Annotated[int, Field(ge=2, le=5000)]
    max_detection_lower_bound_regression_ppm: Annotated[int, Field(ge=0, le=_PPM)]
    max_clean_false_positive_upper_bound_increase_ppm: Annotated[
        int, Field(ge=0, le=_PPM)
    ]
    max_completion_lower_bound_regression_ppm: Annotated[int, Field(ge=0, le=_PPM)]
    max_mean_cost_delta_increase_microusd: Annotated[
        int, Field(ge=0, le=MAX_DELTA_MICROUSD)
    ]
    max_p95_latency_delta_increase_ms: Annotated[
        int, Field(ge=0, le=MAX_DELTA_LATENCY_MS)
    ]


class SkillHealthPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_post_selection_health_policy"] = (
        "skill_post_selection_health_policy"
    )
    policy_id: Identifier
    authority_policy_sha256: Digest
    default_store_policy_sha256: Digest
    default_pointer_sha256: Digest
    installed_manifest_sha256: Digest
    archive_sha256: Digest
    skill: SkillIdentity
    release_evidence_sha256: Digest
    reference_holdout_report_sha256: Digest
    measurement_protocol_sha256: Digest
    control_anchor_policy_sha256: Digest
    control_anchor_entry_sha256: Digest
    signed_control_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_observation_age_seconds: Annotated[int, Field(gt=0, le=604_800)]
    max_eligibility_lifetime_seconds: Annotated[int, Field(gt=0, le=86_400)]
    thresholds: SkillHealthThresholds
    runtime_dispatch_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    automatic_rollback_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def valid_window_and_skill(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("skill health policy window must be positive")
        if self.skill.kind != "persona":
            raise ValueError("skill health policy requires a persona skill")
        return self

    @property
    def health_policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillHealthMetrics(Contract):
    schema_version: Literal[1] = 1
    detection_independence_groups: Annotated[int, Field(ge=1, le=5000)]
    clean_independence_groups: Annotated[int, Field(ge=1, le=5000)]
    completion_independence_groups: Annotated[int, Field(ge=1, le=5000)]
    detection_lower_bound_ppm: SignedRate
    clean_false_positive_upper_bound_ppm: SignedRate
    completion_lower_bound_ppm: SignedRate
    mean_cost_delta_microusd: (
        Annotated[int, Field(ge=-MAX_DELTA_MICROUSD, le=MAX_DELTA_MICROUSD)] | None
    )
    paired_cost_coverage_ppm: Annotated[int, Field(ge=0, le=_PPM)]
    p95_latency_delta_ms: Annotated[
        int, Field(ge=-MAX_DELTA_LATENCY_MS, le=MAX_DELTA_LATENCY_MS)
    ]

    @model_validator(mode="after")
    def cost_shape(self) -> Self:
        if (self.mean_cost_delta_microusd is None) != (
            self.paired_cost_coverage_ppm == 0
        ):
            raise ValueError("skill health cost value and coverage disagree")
        return self


class SkillHealthGateResult(Contract):
    schema_version: Literal[1] = 1
    health_passed: bool
    drift_passed: bool


class SkillHealthObservation(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_post_selection_health_observation"] = (
        "skill_post_selection_health_observation"
    )
    health_policy_sha256: Digest
    default_pointer_sha256: Digest
    installed_manifest_sha256: Digest
    archive_sha256: Digest
    skill: SkillIdentity
    measurement_protocol_sha256: Digest
    evidence_bundle_sha256: Digest
    observed_from: UtcTimestamp
    observed_through: UtcTimestamp
    valid_until: UtcTimestamp
    metrics: SkillHealthMetrics
    runtime_dispatch_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    automatic_rollback_authorized: Literal[False] = False

    @field_validator("observed_from", "observed_through", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def valid_window_and_skill(self) -> Self:
        if not self.observed_from <= self.observed_through < self.valid_until:
            raise ValueError("skill health observation window is invalid")
        if self.skill.kind != "persona":
            raise ValueError("skill health observation requires a persona skill")
        return self

    @property
    def observation_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillHealthPolicySignature(Contract):
    signer_id: Identifier
    public_key_sha256: Digest
    health_policy_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedSkillHealthPolicy(Contract):
    schema_version: Literal[1] = 1
    policy: SkillHealthPolicy
    signature: SkillHealthPolicySignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.health_policy_sha256 != self.policy.health_policy_sha256:
            raise ValueError("signature does not identify this skill health policy")
        return self

    @property
    def signed_policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillHealthObservationSignature(Contract):
    signer_id: Identifier
    public_key_sha256: Digest
    observation_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedSkillHealthObservation(Contract):
    schema_version: Literal[1] = 1
    observation: SkillHealthObservation
    signature: SkillHealthObservationSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.observation_sha256 != self.observation.observation_sha256:
            raise ValueError(
                "signature does not identify this skill health observation"
            )
        return self

    @property
    def signed_observation_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillHealthEligibility(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_post_selection_health_eligibility"] = (
        "skill_post_selection_health_eligibility"
    )
    authority_policy_sha256: Digest
    signed_health_policy_sha256: Digest
    signed_observation_sha256: Digest
    default_pointer_sha256: Digest
    installed_manifest_sha256: Digest
    archive_sha256: Digest
    skill: SkillIdentity
    control_anchor_entry_sha256: Digest
    evidence_bundle_sha256: Digest
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    health_passed: Literal[True] = True
    drift_passed: Literal[True] = True
    runtime_preflight_eligible: Literal[True] = True
    runtime_dispatch_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    automatic_rollback_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("skill health eligibility window must be positive")
        return self

    @property
    def eligibility_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime) -> None:
        current = _require_utc(now)
        if not self.issued_at <= current < self.valid_until:
            raise ValueError("skill health eligibility is not current")


def trusted_skill_health_authority(
    authority_id: str, public_key: bytes
) -> TrustedSkillHealthAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedSkillHealthAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _sign(payload: Contract, private_key: bytes, domain: bytes) -> str:
    if len(private_key) != 32:
        raise ValueError("Ed25519 private key must contain 32 bytes")
    try:
        signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(
            domain + canonical_bytes(payload)
        )
    except (ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return base64.b64encode(signature).decode("ascii")


def sign_skill_health_policy(
    policy: SkillHealthPolicy, signer_id: str, private_key: bytes
) -> SignedSkillHealthPolicy:
    key = Ed25519PrivateKey.from_private_bytes(private_key)
    key_hash = digest(key.public_key().public_bytes_raw())
    return SignedSkillHealthPolicy(
        policy=policy,
        signature=SkillHealthPolicySignature(
            signer_id=signer_id,
            public_key_sha256=key_hash,
            health_policy_sha256=policy.health_policy_sha256,
            signature_base64=_sign(policy, private_key, _POLICY_DOMAIN),
        ),
    )


def sign_skill_health_observation(
    observation: SkillHealthObservation, signer_id: str, private_key: bytes
) -> SignedSkillHealthObservation:
    key = Ed25519PrivateKey.from_private_bytes(private_key)
    key_hash = digest(key.public_key().public_bytes_raw())
    return SignedSkillHealthObservation(
        observation=observation,
        signature=SkillHealthObservationSignature(
            signer_id=signer_id,
            public_key_sha256=key_hash,
            observation_sha256=observation.observation_sha256,
            signature_base64=_sign(observation, private_key, _OBSERVATION_DOMAIN),
        ),
    )


def _verify_signature(
    signer_id: str,
    key_hash: str,
    signature: str,
    payload: Contract,
    domain: bytes,
    authorities: SkillHealthAuthorityPolicy,
) -> TrustedSkillHealthAuthority:
    matches = [
        item for item in authorities.authorities if item.authority_id == signer_id
    ]
    if len(matches) != 1 or matches[0].public_key_sha256 != key_hash:
        raise ValueError("skill health signer is not enrolled")
    signer = matches[0]
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(signer.public_key_base64, 32, "public key")
        ).verify(_decode(signature, 64, "signature"), domain + canonical_bytes(payload))
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("skill health signature is invalid") from None
    return signer


def _validate_authority_separation(
    health_policy: SkillHealthAuthorityPolicy,
    default_policy: SkillDefaultAuthorityPolicy,
    installation_policy: SkillInstallationAuthorityPolicy,
    control_policy: SkillReleaseControlAuthorityPolicy,
    promotion_policy: SkillPromotionAuthorityPolicy,
    lineages: tuple[SkillEvaluationLineage, SkillEvaluationLineage],
) -> None:
    upstream = (
        *default_policy.authorities,
        *installation_policy.authorities,
        *control_policy.authorities,
        *promotion_policy.authorities,
    )
    excluded_ids = {item.authority_id for item in upstream}
    excluded_keys = {item.public_key_sha256 for item in upstream}
    excluded_ids |= {
        item.adjudicator_id for lineage in lineages for item in lineage[5].adjudicators
    } | {item.adjudicator_id for lineage in lineages for item in lineage[6].resolvers}
    excluded_keys |= {
        item.public_key_sha256
        for lineage in lineages
        for item in lineage[5].adjudicators
    } | {
        item.public_key_sha256 for lineage in lineages for item in lineage[6].resolvers
    }
    if any(
        item.authority_id in excluded_ids or item.public_key_sha256 in excluded_keys
        for item in health_policy.authorities
    ):
        raise ValueError(
            "skill health authorities must be independent of default, installation, "
            "release control, promotion, and evaluation"
        )


def _current_default(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    default_store: SkillDefaultStore,
    default_policy: SkillDefaultAuthorityPolicy,
    now: datetime,
) -> tuple[SkillDefaultPointer, AuthenticatedSkillReleaseControl, str]:
    verify_authenticated_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
    )
    current_control = authenticate_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control.signed_control,
        control_policy,
        control.rollback_archive,
        now,
    )
    with anchor.guard_latest(current_control, control_policy, now) as anchored:
        snapshot = default_store.snapshot(
            default_policy, installed_store, installation_policy
        )
        pointer = snapshot.current
        expected_archive = (
            archive
            if current_control.release_allowed
            else current_control.rollback_archive
        )
        if pointer is None:
            raise ValueError("skill health requires a selected default")
        if (
            expected_archive is None
            or pointer.archive_sha256 != expected_archive.archive_sha256
        ):
            raise ValueError(
                "selected default is not permitted by current release control"
            )
        installed_manifest = installed_store.load(
            pointer.archive_sha256, installation_policy
        )[0]
        if (
            pointer.default_store_policy_sha256 != default_store.policy.policy_sha256
            or pointer.installed_manifest_sha256 != installed_manifest.manifest_sha256
            or pointer.skill != expected_archive.descriptor.identity
        ):
            raise ValueError("selected default provenance is invalid")
        return pointer, current_control, anchored.anchor_entry_sha256


def _passes_health(metrics: SkillHealthMetrics, report: SkillComparisonReport) -> bool:
    gate = report.gate
    return all(
        (
            metrics.detection_lower_bound_ppm
            >= _lower_ppm(-gate.max_detection_regression),
            metrics.clean_false_positive_upper_bound_ppm
            <= _upper_ppm(gate.max_false_positive_increase),
            metrics.completion_lower_bound_ppm
            >= _lower_ppm(-gate.max_completion_regression),
            gate.max_mean_cost_increase_microusd is None
            or (
                metrics.paired_cost_coverage_ppm == _PPM
                and metrics.mean_cost_delta_microusd is not None
                and metrics.mean_cost_delta_microusd
                <= gate.max_mean_cost_increase_microusd
            ),
            gate.max_p95_latency_increase_ms is None
            or metrics.p95_latency_delta_ms <= gate.max_p95_latency_increase_ms,
        )
    )


def _passes_drift(
    metrics: SkillHealthMetrics,
    report: SkillComparisonReport,
    thresholds: SkillHealthThresholds,
) -> bool:
    reference_cost = report.mean_cost_delta_microusd
    return all(
        (
            metrics.detection_lower_bound_ppm
            >= _lower_ppm(report.detection_delta.lower)
            - thresholds.max_detection_lower_bound_regression_ppm,
            metrics.clean_false_positive_upper_bound_ppm
            <= _upper_ppm(report.clean_false_positive_delta.upper)
            + thresholds.max_clean_false_positive_upper_bound_increase_ppm,
            metrics.completion_lower_bound_ppm
            >= _lower_ppm(report.completion_delta.lower)
            - thresholds.max_completion_lower_bound_regression_ppm,
            reference_cost is None
            or (
                metrics.mean_cost_delta_microusd is not None
                and metrics.mean_cost_delta_microusd
                <= math.floor(reference_cost)
                + thresholds.max_mean_cost_delta_increase_microusd
            ),
            metrics.p95_latency_delta_ms
            <= report.p95_latency_delta_ms
            + thresholds.max_p95_latency_delta_increase_ms,
        )
    )


def evaluate_skill_health_metrics(
    metrics: SkillHealthMetrics,
    reference: SkillComparisonReport,
    thresholds: SkillHealthThresholds,
) -> SkillHealthGateResult:
    """Recompute absolute health and reference drift without accepting labels."""
    return SkillHealthGateResult(
        health_passed=_passes_health(metrics, reference),
        drift_passed=_passes_drift(metrics, reference, thresholds),
    )


def issue_skill_health_eligibility(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    default_store: SkillDefaultStore,
    default_policy: SkillDefaultAuthorityPolicy,
    signed_policy: SignedSkillHealthPolicy,
    signed_observation: SignedSkillHealthObservation,
    health_authorities: SkillHealthAuthorityPolicy,
    now: datetime,
) -> SkillHealthEligibility:
    """Derive expiring evidence eligibility; never dispatch or mutate state."""
    current = _require_utc(now)
    pointer, current_control, anchor_entry_sha256 = _current_default(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        installed_store,
        installation_policy,
        default_store,
        default_policy,
        current,
    )
    _validate_authority_separation(
        health_authorities,
        default_policy,
        installation_policy,
        control_policy,
        promotion_policy,
        (calibration, holdout),
    )
    authority = health_authorities
    policy = signed_policy.policy
    observation = signed_observation.observation
    if (
        authority.default_authority_policy_sha256 != default_policy.policy_sha256
        or authority.default_store_policy_sha256 != default_store.policy.policy_sha256
        or authority.control_anchor_policy_sha256 != anchor.policy.policy_sha256
        or authority.promotion_authority_policy_sha256 != promotion_policy.policy_sha256
        or policy.authority_policy_sha256 != authority.policy_sha256
        or policy.default_store_policy_sha256 != default_store.policy.policy_sha256
        or policy.default_pointer_sha256 != pointer.pointer_sha256
        or policy.installed_manifest_sha256 != pointer.installed_manifest_sha256
        or policy.archive_sha256 != pointer.archive_sha256
        or policy.skill != pointer.skill
        or policy.release_evidence_sha256 != evidence.release_evidence_sha256
        or policy.reference_holdout_report_sha256
        != holdout_report.skill_comparison_report_sha256
        or policy.control_anchor_policy_sha256 != anchor.policy.policy_sha256
        or policy.control_anchor_entry_sha256 != anchor_entry_sha256
        or policy.signed_control_sha256
        != current_control.signed_control.signed_control_sha256
    ):
        raise ValueError("skill health policy provenance mismatch")
    if not (
        authority.valid_from <= current < authority.valid_until
        and policy.valid_from <= current < policy.valid_until
    ):
        raise ValueError("skill health policy is outside its validity window")
    policy_signer = _verify_signature(
        signed_policy.signature.signer_id,
        signed_policy.signature.public_key_sha256,
        signed_policy.signature.signature_base64,
        policy,
        _POLICY_DOMAIN,
        authority,
    )
    observation_signer = _verify_signature(
        signed_observation.signature.signer_id,
        signed_observation.signature.public_key_sha256,
        signed_observation.signature.signature_base64,
        observation,
        _OBSERVATION_DOMAIN,
        authority,
    )
    if (
        policy_signer.authority_id == observation_signer.authority_id
        or policy_signer.public_key_sha256 == observation_signer.public_key_sha256
    ):
        raise ValueError("skill health policy and observation need distinct signers")
    if (
        observation.health_policy_sha256 != policy.health_policy_sha256
        or observation.default_pointer_sha256 != pointer.pointer_sha256
        or observation.installed_manifest_sha256 != pointer.installed_manifest_sha256
        or observation.archive_sha256 != pointer.archive_sha256
        or observation.skill != pointer.skill
        or observation.measurement_protocol_sha256 != policy.measurement_protocol_sha256
    ):
        raise ValueError("skill health observation provenance mismatch")
    if (
        observation.observed_from < pointer.selected_at
        or observation.observed_through > current
        or not current < observation.valid_until
        or (current - observation.observed_through).total_seconds()
        > policy.max_observation_age_seconds
    ):
        raise ValueError("skill health observation is stale, future, or pre-selection")
    metrics = observation.metrics
    minimum = max(
        policy.thresholds.minimum_independence_groups,
        holdout_report.minimum_groups_per_metric,
    )
    if (
        min(
            metrics.detection_independence_groups,
            metrics.clean_independence_groups,
            metrics.completion_independence_groups,
        )
        < minimum
    ):
        raise ValueError("skill health evidence has insufficient independent groups")
    gate_result = evaluate_skill_health_metrics(
        metrics, holdout_report, policy.thresholds
    )
    if not gate_result.health_passed:
        raise ValueError("post-selection skill health evidence failed")
    if not gate_result.drift_passed:
        raise ValueError("post-selection skill drift evidence failed")
    valid_until = min(
        authority.valid_until,
        policy.valid_until,
        observation.valid_until,
        current_control.valid_until,
        current + timedelta(seconds=policy.max_eligibility_lifetime_seconds),
    )
    return SkillHealthEligibility(
        authority_policy_sha256=authority.policy_sha256,
        signed_health_policy_sha256=signed_policy.signed_policy_sha256,
        signed_observation_sha256=signed_observation.signed_observation_sha256,
        default_pointer_sha256=pointer.pointer_sha256,
        installed_manifest_sha256=pointer.installed_manifest_sha256,
        archive_sha256=pointer.archive_sha256,
        skill=pointer.skill,
        control_anchor_entry_sha256=anchor_entry_sha256,
        evidence_bundle_sha256=observation.evidence_bundle_sha256,
        issued_at=current,
        valid_until=valid_until,
    )


def verify_skill_health_eligibility(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    default_store: SkillDefaultStore,
    default_policy: SkillDefaultAuthorityPolicy,
    signed_policy: SignedSkillHealthPolicy,
    signed_observation: SignedSkillHealthObservation,
    health_authorities: SkillHealthAuthorityPolicy,
    artifact: SkillHealthEligibility,
    now: datetime,
) -> None:
    rebuilt = issue_skill_health_eligibility(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        installed_store,
        installation_policy,
        default_store,
        default_policy,
        signed_policy,
        signed_observation,
        health_authorities,
        artifact.issued_at,
    )
    if rebuilt != artifact:
        raise ValueError("skill health eligibility provenance mismatch")
    artifact.check_current(now)
