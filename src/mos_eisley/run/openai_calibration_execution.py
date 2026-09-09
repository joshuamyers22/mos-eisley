"""Independent signed authority for one exact calibration campaign attempt."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, JsonValue, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.execution import ExecutionBatch
from mos_eisley.providers.openai_spend import SpendPolicy, SpendReservation
from mos_eisley.run.broker_audit import AssignmentAuthorization
from mos_eisley.run.evaluation_broker import make_assignment_authorization
from mos_eisley.run.openai_calibration_campaign import (
    OpenAICalibrationCampaignAssignment,
    OpenAICalibrationCampaignManifest,
    OpenAICalibrationCampaignPolicy,
    OpenAICalibrationProfilePlan,
    plan_openai_calibration_campaign,
)
from mos_eisley.run.openai_conformance import build_openai_conformance_payload
from mos_eisley.run.openai_conformance_conversion import (
    OpenAIConformanceCalibrationSeed,
)
from mos_eisley.run.provider_broker import ApprovedRequest
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerEntryStatus, SpendLedger

_DOMAIN = b"mos-eisley/openai-calibration-execution/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


class TrustedOpenAICalibrationExecutionAuthority(Contract):
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


class OpenAICalibrationExecutionAuthorityPolicy(Contract):
    """Trust and freshness policy for one-assignment execution decisions."""

    schema_version: Literal[1] = 1
    mode: Literal["openai_calibration_execution_authority_policy"] = (
        "openai_calibration_execution_authority_policy"
    )
    policy_id: Identifier
    campaign_policy_sha256: Digest
    campaign_manifest_sha256: Digest
    calibration_seed_sha256: Digest
    spend_ledger_id: Digest
    spend_ledger_policy_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_decision_lifetime_seconds: Annotated[int, Field(gt=0, le=300)]
    max_request_timeout_seconds: Annotated[int, Field(gt=0, le=120)]
    authorities: Annotated[
        tuple[TrustedOpenAICalibrationExecutionAuthority, ...],
        Field(min_length=1, max_length=20),
    ]
    provider: Literal["openai"] = "openai"
    command: Literal["eval-authenticate-openai-calibration-execution"] = (
        "eval-authenticate-openai-calibration-execution"
    )
    independent_signature_required: Literal[True] = True
    exact_campaign_assignment_required: Literal[True] = True
    exact_provider_request_required: Literal[True] = True
    schema_two_spending_required: Literal[True] = True
    one_use_ledger_entry_required: Literal[True] = True
    explicit_local_consent_also_required: Literal[True] = True
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("calibration execution authority window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "calibration execution authorities need sorted unique "
                "identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OpenAICalibrationExecutionDecision(Contract):
    """One exact future attempt, still requiring atomic spending admission."""

    schema_version: Literal[1] = 1
    mode: Literal["openai_calibration_execution_decision"] = (
        "openai_calibration_execution_decision"
    )
    authority_policy_sha256: Digest
    campaign_policy_sha256: Digest
    campaign_manifest_sha256: Digest
    calibration_seed_sha256: Digest
    sequence: Annotated[int, Field(ge=1, le=342)]
    batch_position: Annotated[int, Field(ge=1, le=360)]
    profile_plan_sha256: Digest
    spend_ledger_policy_sha256: Digest
    assignment_authorization: AssignmentAuthorization
    audit_directory_sha256: Digest
    max_cost_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    request_timeout_seconds: Annotated[int, Field(gt=0, le=120)]
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    provider: Literal["openai"] = "openai"
    service_tier: Literal["default"] = "default"
    one_exact_attempt_authorized: Literal[True] = True
    one_use_ledger_entry_required: Literal[True] = True
    blinded_data_transfer_authorized: Literal[True] = True
    credential_access_authorized: Literal[True] = True
    spend_reservation_authorized: Literal[True] = True
    provider_request_authorized: Literal[True] = True
    tool_access_authorized: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    batch_conversion_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def positive_window_and_bound_audit(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("calibration execution decision window must be positive")
        if self.assignment_authorization.ledger_entry_id != self.audit_directory_sha256:
            raise ValueError(
                "calibration execution ledger entry must bind the audit path"
            )
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OpenAICalibrationExecutionSignature(Contract):
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


class SignedOpenAICalibrationExecutionDecision(Contract):
    schema_version: Literal[1] = 1
    decision: OpenAICalibrationExecutionDecision
    signature: OpenAICalibrationExecutionSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.decision_sha256 != self.decision.decision_sha256:
            raise ValueError("signature does not identify this execution decision")
        return self

    @property
    def signed_decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedOpenAICalibrationExecution(Contract):
    """Verified authority that has not accessed a credential or consumed spend."""

    schema_version: Literal[1] = 1
    mode: Literal["authenticated_openai_calibration_execution"] = (
        "authenticated_openai_calibration_execution"
    )
    authority_policy_sha256: Digest
    campaign_manifest_sha256: Digest
    sequence: Annotated[int, Field(ge=1, le=342)]
    assignment_authorization: AssignmentAuthorization
    max_cost_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    signed_decision: SignedOpenAICalibrationExecutionDecision
    authenticated_at: UtcTimestamp
    valid_until: UtcTimestamp
    one_exact_attempt_authorized: Literal[True] = True
    one_use_ledger_entry_required: Literal[True] = True
    ledger_entry_absent_verified: Literal[True] = True
    explicit_local_consent_still_required: Literal[True] = True
    credential_accessed: Literal[False] = False
    spend_reserved: Literal[False] = False
    provider_request_sent: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("authenticated_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_sources(self) -> Self:
        decision = self.signed_decision.decision
        if (
            self.authority_policy_sha256 != decision.authority_policy_sha256
            or self.campaign_manifest_sha256 != decision.campaign_manifest_sha256
            or self.sequence != decision.sequence
            or self.assignment_authorization != decision.assignment_authorization
            or self.max_cost_microusd != decision.max_cost_microusd
            or self.valid_until != decision.valid_until
            or not decision.issued_at <= self.authenticated_at < self.valid_until
        ):
            raise ValueError("authenticated calibration execution source mismatch")
        return self

    @property
    def authorization_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime) -> None:
        current = _require_utc(now)
        if not self.authenticated_at <= current < self.valid_until:
            raise ValueError("calibration execution authorization is not current")


class PreparedOpenAICalibrationExecution(Contract):
    """Consumed one-use authority with held spend, but no credential or send."""

    schema_version: Literal[1] = 1
    mode: Literal["prepared_openai_calibration_execution"] = (
        "prepared_openai_calibration_execution"
    )
    authenticated_execution: AuthenticatedOpenAICalibrationExecution
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    spend_ledger_policy_sha256: Digest
    spend_reservation: SpendReservation
    ledger_entry: LedgerEntry
    prepared_at: UtcTimestamp
    valid_until: UtcTimestamp
    data_transfer_consent_acknowledged: Literal[True] = True
    spend_reservation_consent_acknowledged: Literal[True] = True
    authenticated_receipt_is_historical: Literal[True] = True
    execution_authority_consumed: Literal[True] = True
    spend_reserved: Literal[True] = True
    credential_accessed: Literal[False] = False
    provider_request_sent: Literal[False] = False
    broker_grant_issued: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    credential_access_still_requires_reverification: Literal[True] = True
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("prepared_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_reservation(self) -> Self:
        decision = self.authenticated_execution.signed_decision.decision
        authorization = self.authenticated_execution.assignment_authorization
        if (
            self.valid_until <= self.prepared_at
            or self.authenticated_execution.authenticated_at > self.prepared_at
            or self.valid_until != self.authenticated_execution.valid_until
            or self.provider_request_sha256 != authorization.provider_request_sha256
            or self.spend_policy_sha256 != authorization.spend_policy_sha256
            or self.spend_ledger_policy_sha256 != decision.spend_ledger_policy_sha256
            or self.ledger_entry.entry_id != authorization.ledger_entry_id
            or self.ledger_entry.reservation_sha256
            != digest(canonical_bytes(self.spend_reservation))
            or self.ledger_entry.reserved_microusd
            != self.spend_reservation.reserved_microusd
            or self.spend_reservation.policy_sha256 != self.spend_policy_sha256
            or self.spend_reservation.reserved_microusd
            != self.authenticated_execution.max_cost_microusd
        ):
            raise ValueError("prepared calibration reservation binding is invalid")
        return self

    @property
    def preparation_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime) -> None:
        current = _require_utc(now)
        if not self.prepared_at <= current < self.valid_until:
            raise ValueError("prepared calibration execution is not current")


def trusted_openai_calibration_execution_authority(
    authority_id: str, public_key: bytes
) -> TrustedOpenAICalibrationExecutionAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedOpenAICalibrationExecutionAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def _verified_assignment(
    batch: ExecutionBatch,
    seed: OpenAIConformanceCalibrationSeed,
    campaign_policy: OpenAICalibrationCampaignPolicy,
    manifest: OpenAICalibrationCampaignManifest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    authority_policy: OpenAICalibrationExecutionAuthorityPolicy,
    sequence: int,
    *,
    require_available_budget: bool,
) -> tuple[OpenAICalibrationCampaignAssignment, OpenAICalibrationProfilePlan]:
    batch = ExecutionBatch.model_validate_json(canonical_bytes(batch))
    seed = OpenAIConformanceCalibrationSeed.model_validate_json(canonical_bytes(seed))
    campaign_policy = OpenAICalibrationCampaignPolicy.model_validate_json(
        canonical_bytes(campaign_policy)
    )
    manifest = OpenAICalibrationCampaignManifest.model_validate_json(
        canonical_bytes(manifest)
    )
    spend_policy = SpendPolicy.model_validate_json(canonical_bytes(spend_policy))
    authority_policy = OpenAICalibrationExecutionAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    if manifest != plan_openai_calibration_campaign(batch, seed, campaign_policy):
        raise ValueError("campaign manifest differs from its fully reverified sources")
    if (
        authority_policy.campaign_policy_sha256
        != campaign_policy.campaign_policy_sha256
        or authority_policy.campaign_manifest_sha256
        != manifest.campaign_manifest_sha256
        or authority_policy.calibration_seed_sha256 != seed.calibration_seed_sha256
        or authority_policy.spend_ledger_id != ledger.policy.ledger_id
        or authority_policy.spend_ledger_policy_sha256
        != digest(canonical_bytes(ledger.policy))
    ):
        raise ValueError("calibration execution authority policy source mismatch")
    matches = [item for item in manifest.assignments if item.sequence == sequence]
    if len(matches) != 1:
        raise ValueError("calibration execution requires one exact campaign sequence")
    assignment = matches[0]
    request = batch.requests[assignment.batch_position - 1]
    if (
        request.sample_id != assignment.sample_id
        or request.route.candidate_id != assignment.candidate_id
        or request.request_sha256 != assignment.evaluation_request_sha256
        or request.route.model != assignment.model
        or request.route.effort != assignment.effort
        or request.route.provider != "openai"
    ):
        raise ValueError("campaign assignment differs from the frozen batch")
    profile_matches = [
        item
        for item in campaign_policy.profiles
        if item.profile_plan_sha256 == assignment.profile_plan_sha256
    ]
    if len(profile_matches) != 1:
        raise ValueError("campaign assignment profile is not uniquely defined")
    profile = profile_matches[0]
    if (
        profile.model != assignment.model
        or profile.effort != assignment.effort
        or profile.max_cost_microusd != assignment.max_cost_microusd
        or spend_policy.schema_version != 2
        or spend_policy.model != profile.model
        or spend_policy.service_tier != campaign_policy.service_tier
        or spend_policy.pricing_source != profile.pricing_source
        or spend_policy.input_microusd_per_million != profile.input_microusd_per_million
        or spend_policy.cache_write_microusd_per_million
        != profile.cache_write_microusd_per_million
        or spend_policy.output_microusd_per_million
        != profile.output_microusd_per_million
        or spend_policy.max_input_tokens != profile.max_input_tokens
        or spend_policy.max_output_tokens != profile.max_output_tokens
        or spend_policy.max_cost_microusd != profile.max_cost_microusd
        or spend_policy.reservation_cost(
            spend_policy.max_input_tokens, spend_policy.max_output_tokens
        )
        != profile.max_cost_microusd
    ):
        raise ValueError("schema-2 spending policy differs from the campaign profile")
    snapshot = ledger.snapshot()
    if (
        snapshot.policy.ceiling_microusd > campaign_policy.aggregate_max_cost_microusd
        or snapshot.blocked
        or (
            require_available_budget
            and snapshot.available_microusd < profile.max_cost_microusd
        )
    ):
        raise ValueError("campaign execution spending ledger is not admissible")
    return assignment, profile


def _make_openai_calibration_execution_decision(
    batch: ExecutionBatch,
    seed: OpenAIConformanceCalibrationSeed,
    campaign_policy: OpenAICalibrationCampaignPolicy,
    manifest: OpenAICalibrationCampaignManifest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    authority_policy: OpenAICalibrationExecutionAuthorityPolicy,
    sequence: int,
    audit_directory: Path,
    request_timeout_seconds: int,
    issued_at: datetime,
    valid_until: datetime,
    *,
    require_unused_ledger_entry: bool,
) -> OpenAICalibrationExecutionDecision:
    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    assignment, profile = _verified_assignment(
        batch,
        seed,
        campaign_policy,
        manifest,
        spend_policy,
        ledger,
        authority_policy,
        sequence,
        require_available_budget=require_unused_ledger_entry,
    )
    if audit_directory.exists() or not audit_directory.parent.is_dir():
        raise ValueError("calibration execution requires a fresh audit directory")
    if type(request_timeout_seconds) is not int or not (
        0 < request_timeout_seconds <= authority_policy.max_request_timeout_seconds
    ):
        raise ValueError("calibration execution timeout exceeds authority policy")
    if not (
        authority_policy.valid_from <= issued < expires <= authority_policy.valid_until
        and spend_policy.valid_from <= issued < expires <= spend_policy.valid_until
        and (expires - issued).total_seconds()
        <= authority_policy.max_decision_lifetime_seconds
    ):
        raise ValueError("calibration execution window exceeds a source policy")
    audit_sha256 = digest(str(audit_directory.resolve()).encode())
    if require_unused_ledger_entry and ledger.entry_status(audit_sha256) is not None:
        raise ValueError("calibration execution ledger entry already exists")
    payload = build_openai_conformance_payload(
        batch, assignment.sample_id, spend_policy
    )
    authorization = make_assignment_authorization(
        batch,
        assignment.sample_id,
        payload,
        spend_policy,
        ledger,
        audit_sha256,
    )
    if (
        authorization.sample_id != assignment.sample_id
        or authorization.candidate_id != assignment.candidate_id
        or authorization.evaluation_request_sha256
        != assignment.evaluation_request_sha256
    ):
        raise ValueError(
            "provider request authorization differs from campaign assignment"
        )
    return OpenAICalibrationExecutionDecision(
        authority_policy_sha256=authority_policy.policy_sha256,
        campaign_policy_sha256=campaign_policy.campaign_policy_sha256,
        campaign_manifest_sha256=manifest.campaign_manifest_sha256,
        calibration_seed_sha256=seed.calibration_seed_sha256,
        sequence=assignment.sequence,
        batch_position=assignment.batch_position,
        profile_plan_sha256=profile.profile_plan_sha256,
        spend_ledger_policy_sha256=digest(canonical_bytes(ledger.policy)),
        assignment_authorization=authorization,
        audit_directory_sha256=audit_sha256,
        max_cost_microusd=profile.max_cost_microusd,
        request_timeout_seconds=request_timeout_seconds,
        issued_at=issued,
        valid_until=expires,
    )


def make_openai_calibration_execution_decision(
    batch: ExecutionBatch,
    seed: OpenAIConformanceCalibrationSeed,
    campaign_policy: OpenAICalibrationCampaignPolicy,
    manifest: OpenAICalibrationCampaignManifest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    authority_policy: OpenAICalibrationExecutionAuthorityPolicy,
    sequence: int,
    audit_directory: Path,
    request_timeout_seconds: int,
    issued_at: datetime,
    valid_until: datetime,
) -> OpenAICalibrationExecutionDecision:
    """Derive an exact signable decision without credentials, spend, or dispatch."""

    return _make_openai_calibration_execution_decision(
        batch,
        seed,
        campaign_policy,
        manifest,
        spend_policy,
        ledger,
        authority_policy,
        sequence,
        audit_directory,
        request_timeout_seconds,
        issued_at,
        valid_until,
        require_unused_ledger_entry=True,
    )


def sign_openai_calibration_execution_decision(
    decision: OpenAICalibrationExecutionDecision,
    signer_id: str,
    private_key: bytes,
) -> SignedOpenAICalibrationExecutionDecision:
    """Sign the exact decision; command-line paths never accept private keys."""

    if len(private_key) != 32:
        raise ValueError("Ed25519 private key must contain 32 bytes")
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(decision))
    except (ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedOpenAICalibrationExecutionDecision(
        decision=decision,
        signature=OpenAICalibrationExecutionSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            decision_sha256=decision.decision_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def verify_signed_openai_calibration_execution_decision(
    signed: SignedOpenAICalibrationExecutionDecision,
    authority_policy: OpenAICalibrationExecutionAuthorityPolicy,
) -> None:
    signed = SignedOpenAICalibrationExecutionDecision.model_validate_json(
        canonical_bytes(signed)
    )
    authority_policy = OpenAICalibrationExecutionAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    matches = [
        item
        for item in authority_policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if (
        len(matches) != 1
        or matches[0].public_key_sha256 != signed.signature.public_key_sha256
        or signed.decision.authority_policy_sha256 != authority_policy.policy_sha256
    ):
        raise ValueError("calibration execution signer is not enrolled")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(matches[0].public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(signed.decision),
        )
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("calibration execution signature is invalid") from None


def authenticate_openai_calibration_execution(
    batch: ExecutionBatch,
    seed: OpenAIConformanceCalibrationSeed,
    campaign_policy: OpenAICalibrationCampaignPolicy,
    manifest: OpenAICalibrationCampaignManifest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    authority_policy: OpenAICalibrationExecutionAuthorityPolicy,
    signed: SignedOpenAICalibrationExecutionDecision,
    audit_directory: Path,
    now: datetime,
) -> AuthenticatedOpenAICalibrationExecution:
    """Reverify all sources and authenticate one still-unused exact attempt."""

    current = _require_utc(now)
    verify_signed_openai_calibration_execution_decision(signed, authority_policy)
    expected = make_openai_calibration_execution_decision(
        batch,
        seed,
        campaign_policy,
        manifest,
        spend_policy,
        ledger,
        authority_policy,
        signed.decision.sequence,
        audit_directory,
        signed.decision.request_timeout_seconds,
        signed.decision.issued_at,
        signed.decision.valid_until,
    )
    if signed.decision != expected:
        raise ValueError("signed calibration execution decision differs from sources")
    if not signed.decision.issued_at <= current < signed.decision.valid_until:
        raise ValueError("signed calibration execution decision is not current")
    return AuthenticatedOpenAICalibrationExecution(
        authority_policy_sha256=authority_policy.policy_sha256,
        campaign_manifest_sha256=manifest.campaign_manifest_sha256,
        sequence=signed.decision.sequence,
        assignment_authorization=signed.decision.assignment_authorization,
        max_cost_microusd=signed.decision.max_cost_microusd,
        signed_decision=signed,
        authenticated_at=current,
        valid_until=signed.decision.valid_until,
    )


def _spend_request_sha256(payload: dict[str, JsonValue]) -> str:
    return digest(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    )


def _calibration_reservation(
    batch: ExecutionBatch,
    spend_policy: SpendPolicy,
    authenticated: AuthenticatedOpenAICalibrationExecution,
) -> tuple[SpendReservation, LedgerEntry]:
    authorization = authenticated.assignment_authorization
    payload = build_openai_conformance_payload(
        batch, authorization.sample_id, spend_policy
    )
    if (
        digest(canonical_bytes(ApprovedRequest(payload=payload)))
        != authorization.provider_request_sha256
    ):
        raise ValueError("prepared calibration provider request binding changed")
    reserved = spend_policy.reservation_cost(
        spend_policy.max_input_tokens, spend_policy.max_output_tokens
    )
    if reserved != authenticated.max_cost_microusd:
        raise ValueError("prepared calibration spend envelope changed")
    reservation = SpendReservation(
        policy_sha256=spend_policy.policy_sha256,
        request_sha256=_spend_request_sha256(payload),
        input_tokens=spend_policy.max_input_tokens,
        max_output_tokens=spend_policy.max_output_tokens,
        reserved_microusd=reserved,
    )
    return reservation, LedgerEntry(
        entry_id=authorization.ledger_entry_id,
        reservation_sha256=digest(canonical_bytes(reservation)),
        reserved_microusd=reserved,
    )


def _prepared_openai_calibration_execution(
    batch: ExecutionBatch,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    authenticated: AuthenticatedOpenAICalibrationExecution,
    prepared_at: datetime,
) -> PreparedOpenAICalibrationExecution:
    reservation, entry = _calibration_reservation(batch, spend_policy, authenticated)
    return PreparedOpenAICalibrationExecution(
        authenticated_execution=authenticated,
        provider_request_sha256=(
            authenticated.assignment_authorization.provider_request_sha256
        ),
        spend_policy_sha256=spend_policy.policy_sha256,
        spend_ledger_policy_sha256=digest(canonical_bytes(ledger.policy)),
        spend_reservation=reservation,
        ledger_entry=entry,
        prepared_at=prepared_at,
        valid_until=authenticated.valid_until,
    )


def consume_openai_calibration_execution(
    batch: ExecutionBatch,
    seed: OpenAIConformanceCalibrationSeed,
    campaign_policy: OpenAICalibrationCampaignPolicy,
    manifest: OpenAICalibrationCampaignManifest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    authority_policy: OpenAICalibrationExecutionAuthorityPolicy,
    authenticated: AuthenticatedOpenAICalibrationExecution,
    audit_directory: Path,
    now: datetime,
    *,
    data_transfer_consent: bool,
    spend_reservation_consent: bool,
) -> PreparedOpenAICalibrationExecution:
    """Burn one exact authority into worst-case held spend without credentials."""

    if data_transfer_consent is not True:
        raise ValueError("calibration data transfer was not acknowledged")
    if spend_reservation_consent is not True:
        raise ValueError("calibration spend reservation was not acknowledged")
    current = _require_utc(now)
    authenticated = AuthenticatedOpenAICalibrationExecution.model_validate_json(
        canonical_bytes(authenticated)
    )
    decision = authenticated.signed_decision.decision
    rebuilt = _make_openai_calibration_execution_decision(
        batch,
        seed,
        campaign_policy,
        manifest,
        spend_policy,
        ledger,
        authority_policy,
        decision.sequence,
        audit_directory,
        decision.request_timeout_seconds,
        decision.issued_at,
        decision.valid_until,
        require_unused_ledger_entry=False,
    )
    if rebuilt != decision:
        raise ValueError("authenticated calibration execution provenance changed")
    verify_signed_openai_calibration_execution_decision(
        authenticated.signed_decision, authority_policy
    )
    authenticated.check_current(current)
    spend_policy.check_current(current)
    if (
        current
        + timedelta(
            seconds=authenticated.signed_decision.decision.request_timeout_seconds
        )
        > authenticated.valid_until
    ):
        raise ValueError("calibration execution cannot cover its request timeout")
    prepared = _prepared_openai_calibration_execution(
        batch, spend_policy, ledger, authenticated, current
    )
    try:
        ledger.reserve(prepared.ledger_entry)
    except sqlite3.IntegrityError:
        if ledger.entry_status(prepared.ledger_entry.entry_id) is not None:
            raise ValueError(
                "calibration execution authority was already consumed"
            ) from None
        raise
    return prepared


def verify_prepared_openai_calibration_execution(
    batch: ExecutionBatch,
    seed: OpenAIConformanceCalibrationSeed,
    campaign_policy: OpenAICalibrationCampaignPolicy,
    manifest: OpenAICalibrationCampaignManifest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    authority_policy: OpenAICalibrationExecutionAuthorityPolicy,
    prepared: PreparedOpenAICalibrationExecution,
    audit_directory: Path,
    now: datetime,
) -> None:
    """Reverify exact held preparation without credential access or dispatch."""

    current = _require_utc(now)
    prepared = PreparedOpenAICalibrationExecution.model_validate_json(
        canonical_bytes(prepared)
    )
    authenticated = prepared.authenticated_execution
    decision = authenticated.signed_decision.decision
    rebuilt = _make_openai_calibration_execution_decision(
        batch,
        seed,
        campaign_policy,
        manifest,
        spend_policy,
        ledger,
        authority_policy,
        decision.sequence,
        audit_directory,
        decision.request_timeout_seconds,
        decision.issued_at,
        decision.valid_until,
        require_unused_ledger_entry=False,
    )
    if rebuilt != decision:
        raise ValueError("prepared calibration execution provenance changed")
    verify_signed_openai_calibration_execution_decision(
        authenticated.signed_decision, authority_policy
    )
    authenticated.check_current(prepared.prepared_at)
    spend_policy.check_current(current)
    expected = _prepared_openai_calibration_execution(
        batch, spend_policy, ledger, authenticated, prepared.prepared_at
    )
    status = ledger.entry_status(prepared.ledger_entry.entry_id)
    required_status = LedgerEntryStatus(
        entry_id=prepared.ledger_entry.entry_id,
        reservation_sha256=prepared.ledger_entry.reservation_sha256,
        reserved_microusd=prepared.ledger_entry.reserved_microusd,
        charged_microusd=prepared.ledger_entry.reserved_microusd,
        status="held",
    )
    if expected != prepared or status != required_status:
        raise ValueError("prepared calibration reservation is not the exact held entry")
    prepared.check_current(current)
    if (
        current + timedelta(seconds=decision.request_timeout_seconds)
        > decision.valid_until
    ):
        raise ValueError("prepared calibration cannot cover its request timeout")
