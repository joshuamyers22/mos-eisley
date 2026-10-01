"""Creator-signed, one-use G4 OpenAI critic transfer and spending grant."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, JsonValue, field_validator, model_validator

from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    CriticResult,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ModelClient, ProviderError
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_responses import (
    request_payload,
    response_from_payload,
)
from mos_eisley.providers.openai_spend import (
    CountedTransport,
    PreReservedOpenAITransport,
    SpendPolicy,
    SpendReservation,
    prepare_full_reservation,
    spending_request_sha256,
)
from mos_eisley.review.citations import validate_evidence
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_independent_review import G4ReviewSubject
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    verify_provenance_signature,
)
from mos_eisley.reviewer_review_spend import verify_review_reservation
from mos_eisley.reviewer_single_operator_review import (
    G4SingleOperatorCriticObservation,
    SignedG4SingleOperatorReviewAuthority,
)
from mos_eisley.run.broker_audit import BrokerAudit, BrokerAuthorization
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write

_GRANT_DOMAIN = b"mos-eisley/g4-openai-critic-live-grant/v1\x00"
_AUTHORITY_DOMAIN = b"mos-eisley/g4-single-operator-review-authority/v1\x00"
MAX_G4_REVIEW_TASK_MICROUSD = 10_000_000
OPENAI_LUNA_PRICING = "https://developers.openai.com/api/docs/models/gpt-5.6-luna"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("G4 OpenAI call timestamps require UTC")
    return value


def payload_bytes(payload: dict[str, JsonValue]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class G4OpenAICriticLiveGrant(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_openai_critic_live_grant"] = "g4_openai_critic_live_grant"
    grant_id: Identifier
    provenance_policy_sha256: Digest
    subject_sha256: Digest
    review_authority_sha256: Digest
    critic_id: Identifier
    critic_request_sha256: Digest
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    reservation_sha256: Digest
    reserved_microusd: Annotated[int, Field(gt=0, le=MAX_G4_REVIEW_TASK_MICROUSD)]
    ledger_id: Digest
    ledger_policy_sha256: Digest
    ledger_entry_id: Digest
    provider: Literal["openai"] = "openai"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    data_transfer_scope: Literal["exact_critic_token_count_and_response_once"] = (
        "exact_critic_token_count_and_response_once"
    )
    issued_at: datetime
    expires_at: datetime
    single_operator_self_review_risk_accepted: Literal[True] = True
    network_authorized: Literal[True] = True
    credential_access_authorized: Literal[True] = True
    provider_dispatch_authorized: Literal[True] = True
    independent_review_evidence_passed: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=1):
            raise ValueError("G4 OpenAI live grant exceeds one hour")
        return self


class SignedG4OpenAICriticLiveGrant(Contract):
    grant: G4OpenAICriticLiveGrant
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4OpenAICriticCallAudit(BrokerAuthorization):
    schema_version: Literal[1] = 1
    mode: Literal["g4_openai_critic"] = "g4_openai_critic"
    grant_sha256: Digest
    subject_sha256: Digest
    critic_request_sha256: Digest


def sign_openai_critic_grant(
    grant: G4OpenAICriticLiveGrant,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4OpenAICriticLiveGrant:
    return SignedG4OpenAICriticLiveGrant(
        grant=grant,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_GRANT_DOMAIN + canonical_bytes(grant))
            ).decode("ascii"),
        ),
    )


def prepare_openai_critic_grant(
    *,
    grant_id: str,
    subject: G4ReviewSubject,
    provenance: AuthenticatedG4ProvenanceRecord,
    authority: SignedG4SingleOperatorReviewAuthority,
    request: CriticRequest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    ledger_entry_id: str,
    issued_at: datetime,
    expires_at: datetime,
) -> tuple[G4OpenAICriticLiveGrant, dict[str, JsonValue], SpendReservation]:
    """Freeze the exact standard-tier Responses body and full cost envelope."""
    verify_provenance_signature(
        authority.authority,
        authority.signature,
        provenance.policy,
        "creator",
        _AUTHORITY_DOMAIN,
    )
    roster = authority.authority.critics
    matches = [
        (index, spec)
        for index, spec in enumerate(roster)
        if spec.id == "openai-critic"
        and spec.provider == "openai"
        and spec.model == "gpt-5.6-luna"
    ]
    if len(matches) != 1:
        raise ValueError("OpenAI critic is not in the signed review roster")
    index, spec = matches[0]
    if (
        provenance.policy.operator_mode != "single_operator"
        or subject.provenance_sha256 != provenance.record_sha256
        or authority.authority.subject_sha256 != subject.subject_sha256
        or authority.authority.provenance_policy_sha256
        != provenance.policy.policy_sha256
        or request.brief != subject.brief
        or request.schema_version != 2
        or request.persona != spec.persona
        or digest(canonical_bytes(request))
        != authority.authority.critic_request_sha256s[index]
        or spend_policy.schema_version != 2
        or spend_policy.model != spec.model
        or spend_policy.pricing_source != OPENAI_LUNA_PRICING
        or spend_policy.input_microusd_per_million != 200_000
        or spend_policy.cache_write_microusd_per_million != 250_000
        or spend_policy.output_microusd_per_million != 1_200_000
        or spend_policy.max_input_tokens != 64_000
        or spend_policy.max_output_tokens != 4096
        or spend_policy.max_cost_microusd > 50_000
        or spend_policy.service_tier != "default"
        or ledger.policy.ceiling_microusd > MAX_G4_REVIEW_TASK_MICROUSD
        or not spend_policy.valid_from
        <= issued_at
        < expires_at
        <= spend_policy.valid_until
        or not provenance.policy.valid_from
        <= authority.authority.issued_at
        <= issued_at
        < expires_at
        <= min(authority.authority.expires_at, provenance.policy.valid_until)
    ):
        raise ValueError("OpenAI call differs from signed G4 review lineage")
    reviewer = ModelReviewer(
        cast(ModelClient, None),
        openai_registry(),
        judge_provider="openai",
        judge_model="gpt-5.6-luna",
        effort="low",
    )
    model_request = reviewer.critic_request(spec, request)
    payload = request_payload(model_request)
    payload["service_tier"] = "default"
    payload["parallel_tool_calls"] = False
    if (
        payload.get("model") != "gpt-5.6-luna"
        or payload.get("reasoning") != {"effort": "low"}
        or payload.get("tools") != []
        or payload.get("store") is not False
        or payload.get("truncation") != "disabled"
        or payload.get("max_output_tokens") != 4096
        or len(payload_bytes(payload)) > 128_000
    ):
        raise ValueError("OpenAI critic payload is outside the approved scope")
    reservation = prepare_full_reservation(payload, spend_policy)
    if (
        reservation.request_sha256 != spending_request_sha256(payload)
        or reservation.reserved_microusd != 20_916
    ):
        raise ValueError("shared OpenAI critic spending allowance is unavailable")
    verify_review_reservation(ledger, ledger_entry_id, reservation)
    grant = G4OpenAICriticLiveGrant(
        grant_id=grant_id,
        provenance_policy_sha256=provenance.policy.policy_sha256,
        subject_sha256=subject.subject_sha256,
        review_authority_sha256=authority.artifact_sha256,
        critic_id="openai-critic",
        critic_request_sha256=digest(canonical_bytes(request)),
        provider_request_sha256=digest(payload_bytes(payload)),
        spend_policy_sha256=spend_policy.policy_sha256,
        reservation_sha256=digest(canonical_bytes(reservation)),
        reserved_microusd=reservation.reserved_microusd,
        ledger_id=ledger.policy.ledger_id,
        ledger_policy_sha256=digest(canonical_bytes(ledger.policy)),
        ledger_entry_id=ledger_entry_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    return grant, payload, reservation


def verify_openai_critic_grant(
    signed: SignedG4OpenAICriticLiveGrant,
    *,
    subject: G4ReviewSubject,
    provenance: AuthenticatedG4ProvenanceRecord,
    authority: SignedG4SingleOperatorReviewAuthority,
    request: CriticRequest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    now: datetime | None = None,
) -> tuple[dict[str, JsonValue], SpendReservation, LedgerEntry]:
    signer = verify_provenance_signature(
        signed.grant,
        signed.signature,
        provenance.policy,
        "creator",
        _GRANT_DOMAIN,
    )
    if (
        signer.signer_id != authority.signature.signer_id
        or signer.public_key_sha256 != authority.signature.public_key_sha256
    ):
        raise ValueError("OpenAI call signer differs from review owner")
    grant = signed.grant
    expected, payload, reservation = prepare_openai_critic_grant(
        grant_id=grant.grant_id,
        subject=subject,
        provenance=provenance,
        authority=authority,
        request=request,
        spend_policy=spend_policy,
        ledger=ledger,
        ledger_entry_id=grant.ledger_entry_id,
        issued_at=grant.issued_at,
        expires_at=grant.expires_at,
    )
    current = _utc(now if now is not None else datetime.now(UTC))
    if grant != expected or not grant.issued_at <= current < grant.expires_at:
        raise ValueError("OpenAI critic grant changed or expired")
    return (
        payload,
        reservation,
        LedgerEntry(
            entry_id=grant.ledger_entry_id,
            reservation_sha256=grant.reservation_sha256,
            reserved_microusd=grant.reserved_microusd,
        ),
    )


async def run_openai_critic_once(
    signed: SignedG4OpenAICriticLiveGrant,
    *,
    subject: G4ReviewSubject,
    provenance: AuthenticatedG4ProvenanceRecord,
    authority: SignedG4SingleOperatorReviewAuthority,
    request: CriticRequest,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    claim_store: Path,
    run_directory: Path,
    transport: CountedTransport,
) -> G4SingleOperatorCriticObservation:
    """Burn the signed grant before count or generation; retain private audit."""
    payload, reservation, entry = verify_openai_critic_grant(
        signed,
        subject=subject,
        provenance=provenance,
        authority=authority,
        request=request,
        spend_policy=spend_policy,
        ledger=ledger,
    )
    spend_policy.check_current()
    if run_directory.parent.resolve() != claim_store.resolve():
        raise ValueError("OpenAI run directory must be inside the claim store")
    store_fd = open_private_dispatch_store(claim_store)
    try:
        claim_fd = os.open(
            f"{signed.artifact_sha256}.claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=store_fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(signed))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(store_fd)
    finally:
        os.close(store_fd)
    ledger.reserve(entry)
    audit = BrokerAudit(
        run_directory,
        G4OpenAICriticCallAudit(
            provider_request_sha256=signed.grant.provider_request_sha256,
            spend_policy_sha256=spend_policy.policy_sha256,
            ledger_id=ledger.policy.ledger_id,
            ledger_entry_id=entry.entry_id,
            grant_sha256=signed.artifact_sha256,
            subject_sha256=subject.subject_sha256,
            critic_request_sha256=digest(canonical_bytes(request)),
        ),
    )
    private_write(run_directory / "signed-grant.json", canonical_bytes(signed))
    private_write(run_directory / "review-request.json", canonical_bytes(request))
    private_write(run_directory / "provider-request.json", payload_bytes(payload))
    private_write(run_directory / "spend-policy.json", canonical_bytes(spend_policy))
    audit.admit()
    controller = PreReservedOpenAITransport(
        transport, spend_policy, run_directory, ledger, reservation, entry
    )
    started = time.monotonic()
    try:
        async with asyncio.timeout(120):
            response = await controller.create_response(payload)
    except BaseException as error:
        cancelled = isinstance(error, asyncio.CancelledError)
        with contextlib.suppress(Exception):
            audit.finish(
                "cancelled" if cancelled else "failed",
                latency_ms=min(86_400_000, round((time.monotonic() - started) * 1000)),
                error="cancelled" if cancelled else "provider_error",
                failure_stage="exchange",
            )
        raise
    audit.finish(
        "response_received",
        digest(canonical_bytes(BrokerReply(response=response))),
        latency_ms=min(86_400_000, round((time.monotonic() - started) * 1000)),
    )
    private_write(run_directory / "provider-response.json", payload_bytes(response))
    try:
        canonical_response = response_from_payload(response)
        critic = next(
            spec
            for spec in authority.authority.critics
            if spec.id == signed.grant.critic_id
        )
        reviewer = ModelReviewer(
            cast(ModelClient, None),
            openai_registry(),
            judge_provider="openai",
            judge_model="gpt-5.6-luna",
            effort="low",
        )
        critique = reviewer.parse_critique(critic, request, canonical_response)
        validate_evidence(request, critique.findings)
    except (ValueError, ProviderError, StopIteration):
        raise ProviderError(
            "OpenAI critic returned invalid citation evidence"
        ) from None
    observation = G4SingleOperatorCriticObservation(
        result=CriticResult(critic=critic, status="completed", critique=critique),
        request_sha256=digest(canonical_bytes(request)),
        response_sha256=digest(payload_bytes(response)),
        audit_sha256=digest((run_directory / "outcome.json").read_bytes()),
        observed_at=datetime.now(UTC),
        full_subject_review_claimed=True,
    )
    private_write(
        run_directory / "critic-observation.json", canonical_bytes(observation)
    )
    return observation
