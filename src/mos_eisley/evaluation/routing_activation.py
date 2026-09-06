"""Short-lived routing activation eligibility from signed operational evidence."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.models import EvaluationDataset, RouteCandidate, SweepPlan
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
    verify_authenticated_routing_promotion,
)
from mos_eisley.evaluation.routing_promotion_policy import RoutingPromotionPolicy
from mos_eisley.evaluation.routing_protocol import (
    PromptFeatureManifest,
    SealedRoutingStudy,
)

_SNAPSHOT_DOMAIN = b"mos-eisley/routing-operational-snapshot/v1\x00"
_CONTROL_DOMAIN = b"mos-eisley/routing-activation-control/v1\x00"
_POLICY_DOMAIN = b"mos-eisley/routing-activation-policy/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]


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


class RouteOperationalRequirement(Contract):
    candidate_id: Digest
    route: RouteCandidate
    pricing_basis: Identifier
    max_normalized_cost_microusd: Annotated[
        float, Field(ge=0, le=1_000_000_000_000_000)
    ]

    @model_validator(mode="after")
    def matching_route(self) -> Self:
        if self.candidate_id != self.route.candidate_id:
            raise ValueError("activation route requirement identity mismatch")
        return self


class RoutingActivationPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["routing_activation_eligibility_policy"] = (
        "routing_activation_eligibility_policy"
    )
    policy_id: Identifier
    activation_authorized: Literal[False] = False
    allow_model_substitution: Literal[False] = False
    candidate_policy_sha256: Digest
    promotion_receipt_sha256: Digest
    control_anchor_policy_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_evidence_age_seconds: Annotated[int, Field(gt=0, le=604_800)]
    max_eligibility_lifetime_seconds: Annotated[int, Field(gt=0, le=86_400)]
    max_runtime_preflight_age_seconds: Annotated[int, Field(gt=0, le=300)]
    minimum_control_sequence: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
    unavailable_action: Literal["role_fallback", "fail_closed"]
    route_requirements: Annotated[
        tuple[RouteOperationalRequirement, ...], Field(min_length=1, max_length=256)
    ]

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("activation policy validity window must be positive")
        candidate_ids = tuple(item.candidate_id for item in self.route_requirements)
        if tuple(sorted(set(candidate_ids))) != candidate_ids:
            raise ValueError("activation route requirements must be unique and sorted")
        return self

    @property
    def activation_policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class RouteOperationalEvidence(Contract):
    candidate_id: Digest
    route: RouteCandidate
    pricing_basis: Identifier
    normalized_cost_microusd: Annotated[float, Field(ge=0, le=1_000_000_000_000_000)]
    catalog_status: Literal["available", "unavailable"]
    catalog_evidence_sha256: Digest
    pricing_evidence_sha256: Digest
    conformance_status: Literal["passed", "failed"]
    conformance_evidence_sha256: Digest
    drift_status: Literal["passed", "failed"]
    drift_evidence_sha256: Digest
    observed_at: UtcTimestamp
    valid_until: UtcTimestamp

    @field_validator("observed_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def matching_route_and_window(self) -> Self:
        if self.candidate_id != self.route.candidate_id:
            raise ValueError("operational evidence route identity mismatch")
        if self.valid_until <= self.observed_at:
            raise ValueError("operational evidence validity window must be positive")
        return self


class RoutingOperationalSnapshot(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["routing_operational_readiness_snapshot"] = (
        "routing_operational_readiness_snapshot"
    )
    activation_authorized: Literal[False] = False
    candidate_policy_sha256: Digest
    promotion_receipt_sha256: Digest
    activation_policy_sha256: Digest
    routes: Annotated[
        tuple[RouteOperationalEvidence, ...], Field(min_length=1, max_length=256)
    ]

    @model_validator(mode="after")
    def canonical_routes(self) -> Self:
        candidate_ids = tuple(item.candidate_id for item in self.routes)
        if tuple(sorted(set(candidate_ids))) != candidate_ids:
            raise ValueError("operational snapshot routes must be unique and sorted")
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


class RoutingActivationControlState(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["routing_activation_control_state"] = (
        "routing_activation_control_state"
    )
    activation_authorized: Literal[False] = False
    sequence: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    emergency_stop: bool
    revoked_candidate_policy_sha256: Annotated[
        tuple[Digest, ...], Field(max_length=10_000)
    ] = ()
    revoked_promotion_receipt_sha256: Annotated[
        tuple[Digest, ...], Field(max_length=10_000)
    ] = ()

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("activation control validity window must be positive")
        for values in (
            self.revoked_candidate_policy_sha256,
            self.revoked_promotion_receipt_sha256,
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError("activation revocations must be unique and sorted")
        return self

    @property
    def control_state_sha256(self) -> str:
        return digest(canonical_bytes(self))


class TrustedActivationAuthority(Contract):
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


class RoutingActivationAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    policy_id: Identifier
    authorities: Annotated[
        tuple[TrustedActivationAuthority, ...], Field(min_length=3, max_length=20)
    ]

    @model_validator(mode="after")
    def canonical_unique_authorities(self) -> Self:
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "activation authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OperationalSnapshotSignature(Contract):
    signer_id: Identifier
    public_key_sha256: Digest
    snapshot_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedRoutingOperationalSnapshot(Contract):
    schema_version: Literal[1] = 1
    snapshot: RoutingOperationalSnapshot
    signature: OperationalSnapshotSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.snapshot_sha256 != self.snapshot.snapshot_sha256:
            raise ValueError("signature does not identify this operational snapshot")
        return self

    @property
    def signed_snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ActivationPolicySignature(Contract):
    signer_id: Identifier
    public_key_sha256: Digest
    activation_policy_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedRoutingActivationPolicy(Contract):
    schema_version: Literal[1] = 1
    policy: RoutingActivationPolicy
    signature: ActivationPolicySignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if (
            self.signature.activation_policy_sha256
            != self.policy.activation_policy_sha256
        ):
            raise ValueError("signature does not identify this activation policy")
        return self

    @property
    def signed_policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ActivationControlSignature(Contract):
    signer_id: Identifier
    public_key_sha256: Digest
    control_state_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedRoutingActivationControl(Contract):
    schema_version: Literal[1] = 1
    control: RoutingActivationControlState
    signature: ActivationControlSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.control_state_sha256 != self.control.control_state_sha256:
            raise ValueError("signature does not identify this activation control")
        return self

    @property
    def signed_control_sha256(self) -> str:
        return digest(canonical_bytes(self))


class RoutingActivationEligibility(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["routing_activation_eligibility"] = "routing_activation_eligibility"
    candidate_policy_sha256: Digest
    promotion_receipt_sha256: Digest
    activation_policy_sha256: Digest
    signed_activation_policy_sha256: Digest
    control_anchor_policy_sha256: Digest
    activation_authority_policy_sha256: Digest
    signed_operational_snapshot_sha256: Digest
    signed_control_state_sha256: Digest
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    eligible_candidate_ids: Annotated[
        tuple[Digest, ...], Field(min_length=1, max_length=256)
    ]
    unavailable_action: Literal["role_fallback", "fail_closed"]
    allow_model_substitution: Literal[False] = False
    activation_eligible: Literal[True] = True
    runtime_activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("activation eligibility validity window must be positive")
        if (
            tuple(sorted(set(self.eligible_candidate_ids)))
            != self.eligible_candidate_ids
        ):
            raise ValueError("eligible activation candidates must be unique and sorted")
        return self

    @property
    def eligibility_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime | None = None) -> None:
        current = now if now is not None else datetime.now(UTC)
        _require_utc(current)
        if not self.issued_at <= current < self.valid_until:
            raise ValueError(
                "routing activation eligibility is outside its validity window"
            )


def trusted_activation_authority(
    authority_id: str, public_key: bytes
) -> TrustedActivationAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain exactly 32 bytes")
    return TrustedActivationAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _sign(payload: Contract, domain: bytes, private_key: bytes) -> tuple[bytes, str]:
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (UnsupportedAlgorithm, ValueError):
        raise ValueError("Ed25519 signing unavailable or private key invalid") from None
    public_key = key.public_key().public_bytes_raw()
    signature = base64.b64encode(key.sign(domain + canonical_bytes(payload))).decode(
        "ascii"
    )
    return public_key, signature


def sign_routing_operational_snapshot(
    snapshot: RoutingOperationalSnapshot, signer_id: str, private_key: bytes
) -> SignedRoutingOperationalSnapshot:
    public_key, signature = _sign(snapshot, _SNAPSHOT_DOMAIN, private_key)
    return SignedRoutingOperationalSnapshot(
        snapshot=snapshot,
        signature=OperationalSnapshotSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            snapshot_sha256=snapshot.snapshot_sha256,
            signature_base64=signature,
        ),
    )


def sign_routing_activation_policy(
    policy: RoutingActivationPolicy, signer_id: str, private_key: bytes
) -> SignedRoutingActivationPolicy:
    public_key, signature = _sign(policy, _POLICY_DOMAIN, private_key)
    return SignedRoutingActivationPolicy(
        policy=policy,
        signature=ActivationPolicySignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            activation_policy_sha256=policy.activation_policy_sha256,
            signature_base64=signature,
        ),
    )


def sign_routing_activation_control(
    control: RoutingActivationControlState, signer_id: str, private_key: bytes
) -> SignedRoutingActivationControl:
    public_key, signature = _sign(control, _CONTROL_DOMAIN, private_key)
    return SignedRoutingActivationControl(
        control=control,
        signature=ActivationControlSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            control_state_sha256=control.control_state_sha256,
            signature_base64=signature,
        ),
    )


def _verify_signature(
    signer_id: str,
    public_key_sha256: str,
    signature_base64: str,
    payload: Contract,
    domain: bytes,
    authority_policy: RoutingActivationAuthorityPolicy,
) -> TrustedActivationAuthority:
    matches = [
        item for item in authority_policy.authorities if item.authority_id == signer_id
    ]
    if len(matches) != 1:
        raise ValueError("signer is not trusted by the activation authority policy")
    trusted = matches[0]
    if public_key_sha256 != trusted.public_key_sha256:
        raise ValueError(
            "signature public key differs from activation authority policy"
        )
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signature_base64, 64, "signature"),
            domain + canonical_bytes(payload),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("routing activation signature verification failed") from None
    return trusted


def verify_signed_routing_activation_control(
    signed_control: SignedRoutingActivationControl,
    authority_policy: RoutingActivationAuthorityPolicy,
) -> TrustedActivationAuthority:
    """Verify one control signature against an independently trusted policy."""
    return _verify_signature(
        signed_control.signature.signer_id,
        signed_control.signature.public_key_sha256,
        signed_control.signature.signature_base64,
        signed_control.control,
        _CONTROL_DOMAIN,
        authority_policy,
    )


def _required_routes(
    candidate_policy: FrozenCandidateRoutingPolicy,
    plan: SweepPlan,
) -> dict[str, RouteCandidate]:
    plan_routes = {route.candidate_id: route for route in plan.routes}
    required_ids = {
        decision.selected_candidate_id
        for decision in candidate_policy.decisions
        if decision.selected_candidate_id is not None
    }
    if candidate_policy.uncalibrated_action == "role_fallback":
        required_ids.update(
            decision.fallback_candidate_id for decision in candidate_policy.decisions
        )
    return {candidate_id: plan_routes[candidate_id] for candidate_id in required_ids}


def _verify_activation_policy(
    activation_policy: RoutingActivationPolicy,
    candidate_policy: FrozenCandidateRoutingPolicy,
    promotion: AuthenticatedRoutingPromotion,
    plan: SweepPlan,
) -> dict[str, RouteCandidate]:
    required = _required_routes(candidate_policy, plan)
    requirements = {
        item.candidate_id: item for item in activation_policy.route_requirements
    }
    if (
        not promotion.promotion_ready
        or activation_policy.candidate_policy_sha256
        != candidate_policy.candidate_policy_sha256
        or activation_policy.promotion_receipt_sha256
        != promotion.promotion_receipt_sha256
        or activation_policy.unavailable_action != candidate_policy.uncalibrated_action
        or set(requirements) != set(required)
        or any(requirements[key].route != route for key, route in required.items())
    ):
        raise ValueError("routing activation policy provenance mismatch")
    return required


def _verify_authority_separation(
    activation_authorities: RoutingActivationAuthorityPolicy,
    promotion_authorities: RoutingPromotionAuthorityPolicy,
    calibration: RoutingLineage,
    holdout: RoutingLineage,
) -> None:
    excluded_ids = (
        {item.authority_id for item in promotion_authorities.authorities}
        | {
            item.adjudicator_id
            for policy in (calibration[5], holdout[5])
            for item in policy.adjudicators
        }
        | {
            item.adjudicator_id
            for policy in (calibration[6], holdout[6])
            for item in policy.resolvers
        }
    )
    excluded_keys = (
        {item.public_key_sha256 for item in promotion_authorities.authorities}
        | {
            item.public_key_sha256
            for policy in (calibration[5], holdout[5])
            for item in policy.adjudicators
        }
        | {
            item.public_key_sha256
            for policy in (calibration[6], holdout[6])
            for item in policy.resolvers
        }
    )
    if any(
        item.authority_id in excluded_ids or item.public_key_sha256 in excluded_keys
        for item in activation_authorities.authorities
    ):
        raise ValueError(
            "activation authorities must be independent of evaluation and promotion"
        )


def issue_routing_activation_eligibility(
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
    now: datetime,
) -> RoutingActivationEligibility:
    """Issue short-lived eligibility after full evidence and signature checks."""
    _require_utc(now)
    activation_policy = signed_activation_policy.policy
    verify_authenticated_routing_promotion(
        dataset,
        plan,
        calibration,
        holdout,
        manifest,
        sealed_study,
        calibration_report,
        candidate_policy,
        claim,
        holdout_report,
        promotion_policy,
        promotion,
        promotion_authorities,
    )
    required = _verify_activation_policy(
        activation_policy, candidate_policy, promotion, plan
    )
    _verify_authority_separation(
        activation_authorities, promotion_authorities, calibration, holdout
    )
    policy_signer = _verify_signature(
        signed_activation_policy.signature.signer_id,
        signed_activation_policy.signature.public_key_sha256,
        signed_activation_policy.signature.signature_base64,
        activation_policy,
        _POLICY_DOMAIN,
        activation_authorities,
    )
    snapshot_signer = _verify_signature(
        signed_snapshot.signature.signer_id,
        signed_snapshot.signature.public_key_sha256,
        signed_snapshot.signature.signature_base64,
        signed_snapshot.snapshot,
        _SNAPSHOT_DOMAIN,
        activation_authorities,
    )
    control_signer = verify_signed_routing_activation_control(
        signed_control,
        activation_authorities,
    )
    signer_ids = {
        policy_signer.authority_id,
        snapshot_signer.authority_id,
        control_signer.authority_id,
    }
    signer_keys = {
        policy_signer.public_key_sha256,
        snapshot_signer.public_key_sha256,
        control_signer.public_key_sha256,
    }
    if len(signer_ids) != 3 or len(signer_keys) != 3:
        raise ValueError(
            "activation policy, readiness, and control need distinct signers"
        )
    if not activation_policy.valid_from <= now < activation_policy.valid_until:
        raise ValueError("routing activation policy is outside its validity window")

    snapshot = signed_snapshot.snapshot
    control = signed_control.control
    evidence = {item.candidate_id: item for item in snapshot.routes}
    requirements = {
        item.candidate_id: item for item in activation_policy.route_requirements
    }
    if (
        snapshot.candidate_policy_sha256 != candidate_policy.candidate_policy_sha256
        or snapshot.promotion_receipt_sha256 != promotion.promotion_receipt_sha256
        or snapshot.activation_policy_sha256
        != activation_policy.activation_policy_sha256
        or set(evidence) != set(required)
    ):
        raise ValueError("routing operational snapshot provenance mismatch")
    if (
        control.emergency_stop
        or control.sequence < activation_policy.minimum_control_sequence
        or candidate_policy.candidate_policy_sha256
        in control.revoked_candidate_policy_sha256
        or promotion.promotion_receipt_sha256
        in control.revoked_promotion_receipt_sha256
    ):
        raise ValueError(
            "routing activation is stopped, revoked, or below control sequence"
        )
    if (
        not control.issued_at <= now < control.valid_until
        or (now - control.issued_at).total_seconds()
        > activation_policy.max_evidence_age_seconds
    ):
        raise ValueError("routing activation control state is stale or not current")

    expirations = [activation_policy.valid_until, control.valid_until]
    for candidate_id, route in required.items():
        item = evidence[candidate_id]
        requirement = requirements[candidate_id]
        if item.route != route or item.pricing_basis != requirement.pricing_basis:
            raise ValueError("routing operational route or pricing basis mismatch")
        if (
            item.catalog_status != "available"
            or item.conformance_status != "passed"
            or item.drift_status != "passed"
            or item.normalized_cost_microusd > requirement.max_normalized_cost_microusd
        ):
            raise ValueError("routing operational evidence did not pass every gate")
        if (
            not item.observed_at <= now < item.valid_until
            or (now - item.observed_at).total_seconds()
            > activation_policy.max_evidence_age_seconds
        ):
            raise ValueError("routing operational evidence is stale or not current")
        expirations.append(item.valid_until)

    valid_until = min(
        *expirations,
        now + timedelta(seconds=activation_policy.max_eligibility_lifetime_seconds),
    )
    return RoutingActivationEligibility(
        candidate_policy_sha256=candidate_policy.candidate_policy_sha256,
        promotion_receipt_sha256=promotion.promotion_receipt_sha256,
        activation_policy_sha256=activation_policy.activation_policy_sha256,
        signed_activation_policy_sha256=signed_activation_policy.signed_policy_sha256,
        control_anchor_policy_sha256=activation_policy.control_anchor_policy_sha256,
        activation_authority_policy_sha256=activation_authorities.policy_sha256,
        signed_operational_snapshot_sha256=signed_snapshot.signed_snapshot_sha256,
        signed_control_state_sha256=signed_control.signed_control_sha256,
        issued_at=now,
        valid_until=valid_until,
        eligible_candidate_ids=tuple(sorted(required)),
        unavailable_action=activation_policy.unavailable_action,
    )


def verify_routing_activation_eligibility(
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
    artifact: RoutingActivationEligibility,
    now: datetime | None = None,
) -> None:
    rebuilt = issue_routing_activation_eligibility(
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
        artifact.issued_at,
    )
    if rebuilt != artifact:
        raise ValueError("routing activation eligibility provenance mismatch")
    artifact.check_current(now)
