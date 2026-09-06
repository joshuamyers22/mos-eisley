"""One-use skill request preparation with no provider dispatch authority."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, JsonValue, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.registry import ModelRegistry
from mos_eisley.core.skills import PromptAsset, SkillIdentity, SkillPackageArchive
from mos_eisley.evaluation.models import EvaluationDataset, RouteCandidate, SweepPlan
from mos_eisley.evaluation.skill_comparison import (
    SealedSkillComparison,
    SkillComparisonReport,
    SkillHoldoutUseClaim,
)
from mos_eisley.evaluation.skill_promotion import (
    AuthenticatedSkillPromotion,
    SkillEvaluationLineage,
    SkillPromotionAuthorityPolicy,
)
from mos_eisley.providers.openai_spend import SpendPolicy, SpendReservation
from mos_eisley.run.provider_broker import MAX_REQUEST_BYTES, ApprovedRequest
from mos_eisley.run.routing_preflight import (
    RoutingRuntimePreflight,
    RoutingRuntimeSources,
    guard_routing_runtime_sources,
    verify_routing_runtime_sources,
)
from mos_eisley.run.skill_default import (
    SkillDefaultAuthorityPolicy,
    SkillDefaultStore,
)
from mos_eisley.run.skill_health import (
    SignedSkillHealthObservation,
    SignedSkillHealthPolicy,
    SkillHealthAuthorityPolicy,
    SkillHealthEligibility,
    verify_skill_health_eligibility,
)
from mos_eisley.run.skill_installation import SkillInstallationAuthorityPolicy
from mos_eisley.run.skill_installed_store import SkillInstalledStore
from mos_eisley.run.skill_release import SkillReleaseEvidence
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAuthorityPolicy,
)
from mos_eisley.run.skills import prompt_asset_from_skill_archive
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerEntryStatus, SpendLedger

_DOMAIN = b"mos-eisley/skill-runtime-preflight/v1\x00"
_ENTRY_DOMAIN = b"mos-eisley/skill-runtime-ledger-entry/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]
UserInput = Annotated[str, Field(min_length=1, max_length=128_000)]


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


@dataclass(frozen=True)
class SkillRuntimeSources:
    dataset: EvaluationDataset
    plan: SweepPlan
    calibration: SkillEvaluationLineage
    holdout: SkillEvaluationLineage
    sealed: SealedSkillComparison
    holdout_claim: SkillHoldoutUseClaim
    calibration_report: SkillComparisonReport
    holdout_report: SkillComparisonReport
    promotion: AuthenticatedSkillPromotion
    promotion_policy: SkillPromotionAuthorityPolicy
    archive: SkillPackageArchive
    release_evidence: SkillReleaseEvidence
    control: AuthenticatedSkillReleaseControl
    control_policy: SkillReleaseControlAuthorityPolicy
    control_anchor: SkillReleaseControlAnchor
    installed_store: SkillInstalledStore
    installation_policy: SkillInstallationAuthorityPolicy
    default_store: SkillDefaultStore
    default_policy: SkillDefaultAuthorityPolicy
    signed_health_policy: SignedSkillHealthPolicy
    signed_health_observation: SignedSkillHealthObservation
    health_authorities: SkillHealthAuthorityPolicy
    health_eligibility: SkillHealthEligibility
    routing: RoutingRuntimeSources


class TrustedSkillRuntimeAuthority(Contract):
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


class SkillRuntimeAuthorityPolicy(Contract):
    schema_version: Literal[2] = 2
    mode: Literal["skill_runtime_preflight_authority_policy"] = (
        "skill_runtime_preflight_authority_policy"
    )
    policy_id: Identifier
    health_authority_policy_sha256: Digest
    default_store_policy_sha256: Digest
    routing_activation_authority_policy_sha256: Digest
    routing_control_anchor_policy_sha256: Digest
    model_registry_sha256: Digest
    spend_ledger_id: Digest
    admission_store_policy_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_decision_lifetime_seconds: Annotated[int, Field(gt=0, le=300)]
    authorities: Annotated[
        tuple[TrustedSkillRuntimeAuthority, ...], Field(min_length=1, max_length=20)
    ]
    may_prepare_one_request: Literal[True] = True
    provider_dispatch_authorized: Literal[False] = False
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
            raise ValueError("skill runtime authority window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "skill runtime authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeRequest(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_request"] = "skill_runtime_request"
    request_id: Digest
    route: RouteCandidate
    user_input: UserInput
    max_output_tokens: Annotated[int, Field(gt=0, le=128_000)]
    routing_preflight_sha256: Digest
    skill_health_eligibility_sha256: Digest
    spend_policy_sha256: Digest
    spend_ledger_id: Digest
    tools_authorized: Literal[False] = False
    external_data_transfer_acknowledged: Literal[True]

    @property
    def request_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeDecision(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_preflight_decision"] = (
        "skill_runtime_preflight_decision"
    )
    authority_policy_sha256: Digest
    runtime_request_sha256: Digest
    default_pointer_sha256: Digest
    installed_manifest_sha256: Digest
    archive_sha256: Digest
    skill: SkillIdentity
    health_eligibility_sha256: Digest
    routing_preflight_sha256: Digest
    route_candidate_id: Digest
    provider_request_sha256: Digest
    broker_request_sha256: Digest
    spend_policy_sha256: Digest
    spend_ledger_id: Digest
    ledger_entry_id: Digest
    spend_reservation_sha256: Digest
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    one_use_required: Literal[True] = True
    may_prepare_request: Literal[True] = True
    provider_dispatch_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    automatic_rollback_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def valid_window_and_skill(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("skill runtime decision window must be positive")
        if self.skill.kind != "persona":
            raise ValueError("skill runtime decision requires a persona skill")
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeSignature(Contract):
    signer_id: Identifier
    public_key_sha256: Digest
    decision_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedSkillRuntimeDecision(Contract):
    schema_version: Literal[1] = 1
    decision: SkillRuntimeDecision
    signature: SkillRuntimeSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.decision_sha256 != self.decision.decision_sha256:
            raise ValueError("signature does not identify this skill runtime decision")
        return self

    @property
    def signed_decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class PreparedSkillRuntimeRequest(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["prepared_skill_runtime_request"] = "prepared_skill_runtime_request"
    signed_decision_sha256: Digest
    decision_sha256: Digest
    runtime_request_sha256: Digest
    default_pointer_sha256: Digest
    archive_sha256: Digest
    skill: SkillIdentity
    route: RouteCandidate
    provider_request: ApprovedRequest
    spend_reservation: SpendReservation
    ledger_entry: LedgerEntry
    prepared_at: UtcTimestamp
    valid_until: UtcTimestamp
    authorization_consumed: Literal[True] = True
    spend_reserved: Literal[True] = True
    prompt_bytes_loaded: Literal[True] = True
    broker_grant_issued: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    provider_request_sent: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    automatic_rollback_authorized: Literal[False] = False

    @field_validator("prepared_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.valid_until <= self.prepared_at:
            raise ValueError("prepared skill runtime request window must be positive")
        if self.route.prompt.skill != self.skill:
            raise ValueError("prepared runtime route does not match its skill")
        if self.spend_reservation.request_sha256 != _provider_request_sha256(
            self.provider_request.payload
        ):
            raise ValueError("prepared runtime spend does not match provider request")
        if self.ledger_entry.reservation_sha256 != digest(
            canonical_bytes(self.spend_reservation)
        ):
            raise ValueError("prepared runtime ledger entry does not match reservation")
        return self

    @property
    def preflight_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime) -> None:
        current = _require_utc(now)
        if not self.prepared_at <= current < self.valid_until:
            raise ValueError("prepared skill runtime request is not current")


class SkillRuntimePreflightStatus(Contract):
    schema_version: Literal[1] = 1
    decision_sha256: Digest
    ledger_entry_id: Digest
    ledger_status: Literal["absent", "held", "settled", "uncertain", "violation"]
    authorization_consumed: bool
    retry_permitted: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False


def trusted_skill_runtime_authority(
    authority_id: str, public_key: bytes
) -> TrustedSkillRuntimeAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedSkillRuntimeAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def sign_skill_runtime_decision(
    decision: SkillRuntimeDecision, signer_id: str, private_key: bytes
) -> SignedSkillRuntimeDecision:
    if len(private_key) != 32:
        raise ValueError("Ed25519 private key must contain 32 bytes")
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(decision))
    except (ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedSkillRuntimeDecision(
        decision=decision,
        signature=SkillRuntimeSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            decision_sha256=decision.decision_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def verify_signed_skill_runtime_decision(
    signed: SignedSkillRuntimeDecision,
    policy: SkillRuntimeAuthorityPolicy,
) -> TrustedSkillRuntimeAuthority:
    matches = [
        item
        for item in policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if (
        len(matches) != 1
        or matches[0].public_key_sha256 != signed.signature.public_key_sha256
        or signed.decision.authority_policy_sha256 != policy.policy_sha256
    ):
        raise ValueError("skill runtime signer is not enrolled")
    signer = matches[0]
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(signer.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(signed.decision),
        )
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("skill runtime signature is invalid") from None
    return signer


def _provider_request_sha256(payload: dict[str, JsonValue]) -> str:
    normalized = dict(payload)
    normalized["store"] = False
    normalized["truncation"] = "disabled"
    normalized["service_tier"] = "default"
    return digest(
        json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def _runtime_prompt(
    sources: SkillRuntimeSources,
) -> tuple[SkillPackageArchive, PromptAsset]:
    manifest, archive, _, _ = sources.installed_store.load(
        sources.health_eligibility.archive_sha256, sources.installation_policy
    )
    if (
        manifest.manifest_sha256 != sources.health_eligibility.installed_manifest_sha256
        or archive.archive_sha256 != sources.health_eligibility.archive_sha256
        or archive.descriptor.identity != sources.health_eligibility.skill
    ):
        raise ValueError("skill runtime installed provenance mismatch")
    return archive, prompt_asset_from_skill_archive(archive)


def _validate_authority_separation(
    runtime_policy: SkillRuntimeAuthorityPolicy, sources: SkillRuntimeSources
) -> None:
    upstream = (
        *sources.health_authorities.authorities,
        *sources.default_policy.authorities,
        *sources.installation_policy.authorities,
        *sources.control_policy.authorities,
        *sources.promotion_policy.authorities,
        *sources.routing.activation_authorities.authorities,
        *sources.routing.promotion_authorities.authorities,
    )
    excluded_ids = {item.authority_id for item in upstream}
    excluded_keys = {item.public_key_sha256 for item in upstream}
    excluded_ids |= (
        {
            item.adjudicator_id
            for lineage in (sources.calibration, sources.holdout)
            for item in lineage[5].adjudicators
        }
        | {
            item.adjudicator_id
            for lineage in (sources.calibration, sources.holdout)
            for item in lineage[6].resolvers
        }
        | {
            item.adjudicator_id
            for lineage in (sources.routing.calibration, sources.routing.holdout)
            for item in lineage[5].adjudicators
        }
        | {
            item.adjudicator_id
            for lineage in (sources.routing.calibration, sources.routing.holdout)
            for item in lineage[6].resolvers
        }
    )
    excluded_keys |= (
        {
            item.public_key_sha256
            for lineage in (sources.calibration, sources.holdout)
            for item in lineage[5].adjudicators
        }
        | {
            item.public_key_sha256
            for lineage in (sources.calibration, sources.holdout)
            for item in lineage[6].resolvers
        }
        | {
            item.public_key_sha256
            for lineage in (sources.routing.calibration, sources.routing.holdout)
            for item in lineage[5].adjudicators
        }
        | {
            item.public_key_sha256
            for lineage in (sources.routing.calibration, sources.routing.holdout)
            for item in lineage[6].resolvers
        }
    )
    if any(
        item.authority_id in excluded_ids or item.public_key_sha256 in excluded_keys
        for item in runtime_policy.authorities
    ):
        raise ValueError("skill runtime authority must be independent of all sources")


def _provider_payload(
    request: SkillRuntimeRequest,
) -> dict[str, JsonValue]:
    return {
        "model": request.route.model,
        "instructions": request.route.prompt.instructions,
        "input": [{"role": "user", "content": request.user_input}],
        "tools": [],
        "reasoning": {"effort": request.route.effort},
        "max_output_tokens": request.max_output_tokens,
        "parallel_tool_calls": False,
        "include": ["reasoning.encrypted_content"],
        "store": False,
        "truncation": "disabled",
    }


def _verified_request(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    now: datetime,
) -> tuple[dict[str, JsonValue], SpendReservation, LedgerEntry]:
    current = _require_utc(now)
    verify_skill_health_eligibility(
        sources.dataset,
        sources.plan,
        sources.calibration,
        sources.holdout,
        sources.sealed,
        sources.holdout_claim,
        sources.calibration_report,
        sources.holdout_report,
        sources.promotion,
        sources.promotion_policy,
        sources.archive,
        sources.release_evidence,
        sources.control,
        sources.control_policy,
        sources.control_anchor,
        sources.installed_store,
        sources.installation_policy,
        sources.default_store,
        sources.default_policy,
        sources.signed_health_policy,
        sources.signed_health_observation,
        sources.health_authorities,
        sources.health_eligibility,
        current,
    )
    verify_routing_runtime_sources(sources.routing, routing_preflight, current)
    spend_policy.check_current(current)
    registry_sha256 = digest(canonical_bytes(registry))
    if (
        runtime_policy.health_authority_policy_sha256
        != sources.health_authorities.policy_sha256
        or runtime_policy.default_store_policy_sha256
        != sources.default_store.policy.policy_sha256
        or runtime_policy.routing_activation_authority_policy_sha256
        != sources.routing.activation_authorities.policy_sha256
        or runtime_policy.routing_control_anchor_policy_sha256
        != sources.routing.control_anchor.policy.policy_sha256
        or runtime_policy.model_registry_sha256 != registry_sha256
        or runtime_policy.spend_ledger_id != ledger.policy.ledger_id
        or request.routing_preflight_sha256 != routing_preflight.preflight_sha256
        or request.skill_health_eligibility_sha256
        != sources.health_eligibility.eligibility_sha256
        or request.spend_policy_sha256 != spend_policy.policy_sha256
        or request.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime request policy provenance mismatch")
    _validate_authority_separation(runtime_policy, sources)
    if not runtime_policy.valid_from <= current < runtime_policy.valid_until:
        raise ValueError("skill runtime authority policy is not current")
    archive, prompt = _runtime_prompt(sources)
    if request.route.prompt != prompt:
        raise ValueError("skill runtime route does not contain exact selected prompt")
    if request.route.candidate_id not in routing_preflight.eligible_candidate_ids:
        raise ValueError("skill runtime route is absent from routing preflight")
    if request.route.registry_sha256 != registry_sha256:
        raise ValueError("skill runtime route registry mismatch")
    resolved = registry.resolve(
        request.route.provider, request.route.model, request.route.effort
    )
    if (
        resolved.substituted
        or resolved.effort != request.route.effort
        or request.route.provider != "openai"
        or request.route.backend != "api"
        or spend_policy.model != request.route.model
        or request.max_output_tokens > spend_policy.max_output_tokens
        or (
            resolved.spec.max_output_tokens is not None
            and request.max_output_tokens > resolved.spec.max_output_tokens
        )
        or (
            resolved.spec.context_tokens is not None
            and spend_policy.max_input_tokens + request.max_output_tokens
            > resolved.spec.context_tokens
        )
    ):
        raise ValueError("skill runtime route, effort, or output limit is not exact")
    payload = _provider_payload(request)
    encoded = canonical_bytes(ApprovedRequest(payload=payload))
    if len(encoded) > min(MAX_REQUEST_BYTES, resolved.spec.context_bytes):
        raise ValueError("skill runtime provider request exceeds byte limit")
    reserved = spend_policy.cost(
        spend_policy.max_input_tokens, request.max_output_tokens
    )
    if reserved > spend_policy.max_cost_microusd:
        raise ValueError("skill runtime worst-case reservation exceeds spending policy")
    reservation = SpendReservation(
        policy_sha256=spend_policy.policy_sha256,
        request_sha256=_provider_request_sha256(payload),
        input_tokens=spend_policy.max_input_tokens,
        max_output_tokens=request.max_output_tokens,
        reserved_microusd=reserved,
    )
    entry = LedgerEntry(
        entry_id=digest(_ENTRY_DOMAIN + bytes.fromhex(request.request_sha256)),
        reservation_sha256=digest(canonical_bytes(reservation)),
        reserved_microusd=reserved,
    )
    if archive.archive_sha256 != sources.health_eligibility.archive_sha256:
        raise ValueError("skill runtime archive changed during preparation")
    return payload, reservation, entry


def make_skill_runtime_decision(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    issued_at: datetime,
    valid_until: datetime,
) -> SkillRuntimeDecision:
    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    payload, _, entry = _verified_request(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        issued,
    )
    if not (
        runtime_policy.valid_from <= issued < expires <= runtime_policy.valid_until
        and expires <= sources.health_eligibility.valid_until
        and expires <= routing_preflight.valid_until
        and expires <= spend_policy.valid_until
    ):
        raise ValueError("skill runtime decision window exceeds a trusted source")
    if (
        expires - issued
    ).total_seconds() > runtime_policy.max_decision_lifetime_seconds:
        raise ValueError("skill runtime decision exceeds its maximum lifetime")
    return SkillRuntimeDecision(
        authority_policy_sha256=runtime_policy.policy_sha256,
        runtime_request_sha256=request.request_sha256,
        default_pointer_sha256=sources.health_eligibility.default_pointer_sha256,
        installed_manifest_sha256=(
            sources.health_eligibility.installed_manifest_sha256
        ),
        archive_sha256=sources.health_eligibility.archive_sha256,
        skill=sources.health_eligibility.skill,
        health_eligibility_sha256=sources.health_eligibility.eligibility_sha256,
        routing_preflight_sha256=routing_preflight.preflight_sha256,
        route_candidate_id=request.route.candidate_id,
        provider_request_sha256=_provider_request_sha256(payload),
        broker_request_sha256=digest(canonical_bytes(ApprovedRequest(payload=payload))),
        spend_policy_sha256=spend_policy.policy_sha256,
        spend_ledger_id=ledger.policy.ledger_id,
        ledger_entry_id=entry.entry_id,
        spend_reservation_sha256=entry.reservation_sha256,
        issued_at=issued,
        valid_until=expires,
    )


def prepare_signed_skill_runtime_request(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    signed: SignedSkillRuntimeDecision,
    now: datetime,
) -> PreparedSkillRuntimeRequest:
    """Burn one signed decision into its worst-case spend reservation; never send."""
    current = _require_utc(now)
    rebuilt = make_skill_runtime_decision(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        signed.decision.issued_at,
        signed.decision.valid_until,
    )
    if rebuilt != signed.decision:
        raise ValueError("skill runtime decision provenance mismatch")
    verify_signed_skill_runtime_decision(signed, runtime_policy)
    if not signed.decision.issued_at <= current < signed.decision.valid_until:
        raise ValueError("skill runtime decision is not current")
    payload, reservation, entry = _verified_request(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        current,
    )
    decision = signed.decision
    if (
        decision.provider_request_sha256 != _provider_request_sha256(payload)
        or decision.broker_request_sha256
        != digest(canonical_bytes(ApprovedRequest(payload=payload)))
        or decision.ledger_entry_id != entry.entry_id
        or decision.spend_reservation_sha256 != entry.reservation_sha256
    ):
        raise ValueError("skill runtime decision request or spend binding changed")
    with (
        guard_routing_runtime_sources(sources.routing, routing_preflight, current),
        sources.control_anchor.guard_latest(
            sources.control, sources.control_policy, current
        ) as anchored,
    ):
        if (
            anchored.anchor_entry_sha256
            != sources.signed_health_policy.policy.control_anchor_entry_sha256
        ):
            raise ValueError("skill runtime release control is no longer health-bound")
        with sources.default_store.guard_current(
            sources.default_policy,
            sources.installed_store,
            sources.installation_policy,
        ) as pointer:
            if pointer.pointer_sha256 != decision.default_pointer_sha256:
                raise ValueError("skill runtime default pointer is no longer current")
            try:
                ledger.reserve(entry)
            except sqlite3.IntegrityError:
                if ledger.entry_status(entry.entry_id) is not None:
                    raise ValueError(
                        "skill runtime authorization was already consumed"
                    ) from None
                raise
    return PreparedSkillRuntimeRequest(
        signed_decision_sha256=signed.signed_decision_sha256,
        decision_sha256=decision.decision_sha256,
        runtime_request_sha256=request.request_sha256,
        default_pointer_sha256=decision.default_pointer_sha256,
        archive_sha256=decision.archive_sha256,
        skill=decision.skill,
        route=request.route,
        provider_request=ApprovedRequest(payload=payload),
        spend_reservation=reservation,
        ledger_entry=entry,
        prepared_at=current,
        valid_until=decision.valid_until,
    )


def verify_prepared_skill_runtime_request(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    signed: SignedSkillRuntimeDecision,
    artifact: PreparedSkillRuntimeRequest,
    now: datetime,
) -> None:
    """Reverify a prepared request and its held one-use reservation without sending."""
    current = _require_utc(now)
    decision = make_skill_runtime_decision(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        signed.decision.issued_at,
        signed.decision.valid_until,
    )
    if decision != signed.decision:
        raise ValueError("prepared skill runtime decision provenance mismatch")
    verify_signed_skill_runtime_decision(signed, runtime_policy)
    payload, reservation, entry = _verified_request(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        current,
    )
    rebuilt = PreparedSkillRuntimeRequest(
        signed_decision_sha256=signed.signed_decision_sha256,
        decision_sha256=decision.decision_sha256,
        runtime_request_sha256=request.request_sha256,
        default_pointer_sha256=decision.default_pointer_sha256,
        archive_sha256=decision.archive_sha256,
        skill=decision.skill,
        route=request.route,
        provider_request=ApprovedRequest(payload=payload),
        spend_reservation=reservation,
        ledger_entry=entry,
        prepared_at=artifact.prepared_at,
        valid_until=decision.valid_until,
    )
    status = ledger.entry_status(entry.entry_id)
    if (
        rebuilt != artifact
        or status is None
        or status.reservation_sha256 != entry.reservation_sha256
        or status.status != "held"
    ):
        raise ValueError("prepared skill runtime request or reservation is not current")
    artifact.check_current(current)


def inspect_skill_runtime_preflight(
    signed: SignedSkillRuntimeDecision,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    ledger: SpendLedger,
) -> SkillRuntimePreflightStatus:
    """Inspect consumption and budget state without retry, send, or release."""
    verify_signed_skill_runtime_decision(signed, runtime_policy)
    decision = signed.decision
    if (
        runtime_policy.spend_ledger_id != ledger.policy.ledger_id
        or decision.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime status ledger identity mismatch")
    entry: LedgerEntryStatus | None = ledger.entry_status(decision.ledger_entry_id)
    if (
        entry is not None
        and entry.reservation_sha256 != decision.spend_reservation_sha256
    ):
        raise ValueError("skill runtime status reservation mismatch")
    return SkillRuntimePreflightStatus(
        decision_sha256=decision.decision_sha256,
        ledger_entry_id=decision.ledger_entry_id,
        ledger_status="absent" if entry is None else entry.status,
        authorization_consumed=entry is not None,
    )
