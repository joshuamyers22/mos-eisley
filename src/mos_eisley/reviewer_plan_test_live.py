"""Separately authorized, one-use critics over a pre-delegation plan/test packet."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import stat
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue, field_validator, model_validator

from mos_eisley.core.models import (
    Contract,
    CriticResult,
    Critique,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ModelClient, ProviderError
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.anthropic_review import (
    AnthropicReviewHTTPTransport,
    critic_payload,
    payload_bytes,
)
from mos_eisley.providers.anthropic_review_spend import (
    PreReservedAnthropicReviewTransport,
    prepare_anthropic_reservation,
)
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_responses import request_payload, response_from_payload
from mos_eisley.providers.openai_spend import (
    CountedTransport,
    PreReservedOpenAITransport,
    SpendPolicy,
    SpendReceipt,
    SpendReservation,
    prepare_full_reservation,
)
from mos_eisley.review.citations import validate_evidence
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_plan_test_review import (
    G4PlanTestReviewPacket,
    SignedG4PlanTestReviewAuthority,
    plan_test_requests,
    verify_plan_test_authority,
)
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    verify_provenance_signature,
)
from mos_eisley.reviewer_review_spend import verify_review_reservation
from mos_eisley.reviewer_single_operator_review import G4SingleOperatorCriticObservation
from mos_eisley.run.broker_audit import (
    BrokerAdmission,
    BrokerAudit,
    BrokerAuthorization,
    BrokerOutcome,
)
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write

DOMAIN = b"mos-eisley/g4-plan-test-critic-live-grant/v1\x00"
Provider = Literal["anthropic", "openai"]


def private_review_bytes(path: Path) -> bytes:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size > 1_000_000
    ):
        raise ValueError("review artifact must be bounded and owner-private")
    return path.read_bytes()


class G4PlanTestCriticLiveGrant(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_pre_delegation_plan_test_critic_live_grant"] = (
        "g4_pre_delegation_plan_test_critic_live_grant"
    )
    grant_id: Identifier
    provider: Provider
    packet_sha256: Digest
    review_authority_sha256: Digest
    provenance_policy_sha256: Digest
    critic_request_sha256: Digest
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    reservation_sha256: Digest
    reserved_microusd: Literal[109_000, 20_916]
    ledger_id: Digest
    ledger_policy_sha256: Digest
    ledger_entry_id: Digest
    issued_at: datetime
    expires_at: datetime
    network_authorized: Literal[True] = True
    credential_access_authorized: Literal[True] = True
    provider_dispatch_authorized: Literal[True] = True
    count_requests: Literal[1] = 1
    generation_requests: Literal[1] = 1
    retries_authorized: Literal[False] = False
    coding_delegation_authorized: Literal[False] = False
    plan_and_tests_approved: Literal[False] = False
    task_acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("critic grant timestamps require UTC")
        return value

    @model_validator(mode="after")
    def window(self) -> G4PlanTestCriticLiveGrant:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=1):
            raise ValueError("critic grant exceeds one hour")
        return self


class SignedG4PlanTestCriticLiveGrant(Contract):
    grant: G4PlanTestCriticLiveGrant
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4PlanTestCriticAudit(BrokerAuthorization):
    schema_version: Literal[1] = 1
    mode: Literal["g4_plan_test_critic"] = "g4_plan_test_critic"
    grant_sha256: Digest
    packet_sha256: Digest
    review_authority_sha256: Digest
    critic_request_sha256: Digest


def prepare_plan_test_critic_grant(
    *,
    grant_id: str,
    provider: Provider,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    spend: SpendPolicy,
    ledger: SpendLedger,
    entry_id: str,
    issued: datetime,
    expires: datetime,
) -> tuple[G4PlanTestCriticLiveGrant, dict[str, JsonValue], SpendReservation]:
    verify_plan_test_authority(authority, packet, policy, now=issued)
    index = 0 if provider == "anthropic" else 1
    spec = authority.authority.critics[index]
    request = plan_test_requests(packet, authority.authority.critics)[index]
    if (
        provider != spec.provider
        or spend.schema_version != 2
        or spend.model != spec.model
        or spend.service_tier != "default"
        or ledger.policy.ceiling_microusd
        != authority.authority.proposed_review_ceiling_microusd
        or not spend.valid_from <= issued < expires <= spend.valid_until
        or expires > authority.authority.expires_at
    ):
        raise ValueError("critic spending or provider differs from authority")
    spend.check_current(issued)
    if provider == "anthropic":
        if (
            spend.pricing_source
            != "https://platform.claude.com/docs/en/about-claude/pricing"
            or spend.input_microusd_per_million != 2_000_000
            or spend.cache_write_microusd_per_million != 4_000_000
            or spend.output_microusd_per_million != 10_000_000
            or spend.max_input_tokens != 17_500
            or spend.max_output_tokens != 3900
            or spend.max_cost_microusd != 200_000
        ):
            raise ValueError("Anthropic plan-review envelope changed")
        body = critic_payload(request, spec.model, spend.max_output_tokens)
        reservation = prepare_anthropic_reservation(body, spend)
    else:
        if (
            spend.pricing_source
            != "https://developers.openai.com/api/docs/models/gpt-5.6-luna"
            or spend.input_microusd_per_million != 200_000
            or spend.cache_write_microusd_per_million != 250_000
            or spend.output_microusd_per_million != 1_200_000
            or spend.max_input_tokens != 64_000
            or spend.max_output_tokens != 4096
            or spend.max_cost_microusd != 50_000
        ):
            raise ValueError("OpenAI plan-review envelope changed")
        reviewer = ModelReviewer(
            cast(ModelClient, None),
            openai_registry(),
            judge_provider="openai",
            judge_model="gpt-5.6-luna",
            effort="low",
        )
        body = request_payload(reviewer.critic_request(spec, request))
        body["service_tier"] = "default"
        body["parallel_tool_calls"] = False
        reservation = prepare_full_reservation(body, spend)
    verify_review_reservation(ledger, entry_id, reservation)
    grant = G4PlanTestCriticLiveGrant(
        grant_id=grant_id,
        provider=provider,
        packet_sha256=packet.packet_sha256,
        review_authority_sha256=authority.artifact_sha256,
        provenance_policy_sha256=policy.policy_sha256,
        critic_request_sha256=digest(canonical_bytes(request)),
        provider_request_sha256=digest(payload_bytes(body)),
        spend_policy_sha256=spend.policy_sha256,
        reservation_sha256=digest(canonical_bytes(reservation)),
        reserved_microusd=cast(Literal[109_000, 20_916], reservation.reserved_microusd),
        ledger_id=ledger.policy.ledger_id,
        ledger_policy_sha256=digest(canonical_bytes(ledger.policy)),
        ledger_entry_id=entry_id,
        issued_at=issued,
        expires_at=expires,
    )
    return grant, body, reservation


def sign_plan_test_critic_grant(
    grant: G4PlanTestCriticLiveGrant, key: Ed25519PrivateKey
) -> SignedG4PlanTestCriticLiveGrant:
    return SignedG4PlanTestCriticLiveGrant(
        grant=grant,
        signature=G4ArtifactSignature(
            signer_id="joshua-myers",
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(DOMAIN + canonical_bytes(grant))
            ).decode("ascii"),
        ),
    )


def verify_plan_test_critic_grant(
    signed: SignedG4PlanTestCriticLiveGrant,
    *,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    spend: SpendPolicy,
    ledger: SpendLedger,
    now: datetime,
) -> tuple[dict[str, JsonValue], SpendReservation, LedgerEntry]:
    signer = verify_provenance_signature(
        signed.grant, signed.signature, policy, "creator", DOMAIN
    )
    if (
        signer.signer_id != authority.signature.signer_id
        or signer.public_key_sha256 != authority.signature.public_key_sha256
    ):
        raise ValueError("live critic signer differs from review owner")
    grant = signed.grant
    expected, body, reservation = prepare_plan_test_critic_grant(
        grant_id=grant.grant_id,
        provider=grant.provider,
        packet=packet,
        policy=policy,
        authority=authority,
        spend=spend,
        ledger=ledger,
        entry_id=grant.ledger_entry_id,
        issued=grant.issued_at,
        expires=grant.expires_at,
    )
    if grant != expected or not grant.issued_at <= now < grant.expires_at:
        raise ValueError("live plan-review critic grant changed or expired")
    return (
        body,
        reservation,
        LedgerEntry(
            entry_id=grant.ledger_entry_id,
            reservation_sha256=grant.reservation_sha256,
            reserved_microusd=grant.reserved_microusd,
        ),
    )


async def run_plan_test_critic_once(
    signed: SignedG4PlanTestCriticLiveGrant,
    *,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    spend: SpendPolicy,
    ledger: SpendLedger,
    claims: Path,
    run: Path,
    transport: CountedTransport | AnthropicReviewHTTPTransport,
) -> G4SingleOperatorCriticObservation:
    body, reservation, entry = verify_plan_test_critic_grant(
        signed,
        packet=packet,
        policy=policy,
        authority=authority,
        spend=spend,
        ledger=ledger,
        now=datetime.now(UTC),
    )
    spend.check_current()
    if run.parent.resolve() != claims.resolve():
        raise ValueError("critic run must be inside its private claim store")
    fd = open_private_dispatch_store(claims)
    try:
        claim = os.open(
            f"{signed.artifact_sha256}.claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim, "wb") as stream:
            stream.write(canonical_bytes(signed))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)
    ledger.reserve(entry)
    index = 0 if signed.grant.provider == "anthropic" else 1
    spec = authority.authority.critics[index]
    request = plan_test_requests(packet, authority.authority.critics)[index]
    audit = BrokerAudit(
        run,
        G4PlanTestCriticAudit(
            provider_request_sha256=signed.grant.provider_request_sha256,
            spend_policy_sha256=spend.policy_sha256,
            ledger_id=ledger.policy.ledger_id,
            ledger_entry_id=entry.entry_id,
            grant_sha256=signed.artifact_sha256,
            packet_sha256=packet.packet_sha256,
            review_authority_sha256=authority.artifact_sha256,
            critic_request_sha256=digest(canonical_bytes(request)),
        ),
    )
    for name, blob in (
        ("signed-grant.json", canonical_bytes(signed)),
        ("review-request.json", canonical_bytes(request)),
        ("provider-request.json", payload_bytes(body)),
        ("spend-policy.json", canonical_bytes(spend)),
    ):
        private_write(run / name, blob)
    audit.admit()
    controller: PreReservedAnthropicReviewTransport | PreReservedOpenAITransport
    if signed.grant.provider == "anthropic":
        controller = PreReservedAnthropicReviewTransport(
            cast(AnthropicReviewHTTPTransport, transport),
            spend,
            run,
            ledger,
            reservation,
            entry,
            signed.grant.expires_at,
        )
    else:
        controller = PreReservedOpenAITransport(
            cast(CountedTransport, transport),
            spend,
            run,
            ledger,
            reservation,
            entry,
        )
    started = time.monotonic()
    try:
        async with asyncio.timeout(120):
            response = await controller.create_response(body)
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
    response_path = run / "provider-response.json"
    response_bytes = payload_bytes(response)
    if response_path.exists() or response_path.is_symlink():
        if response_path.is_symlink() or response_path.read_bytes() != response_bytes:
            raise ProviderError("retained critic response differs from transport")
    else:
        private_write(response_path, response_bytes)
    try:
        if signed.grant.provider == "anthropic":
            content = response.get("content")
            if (
                response.get("type") != "message"
                or response.get("role") != "assistant"
                or response.get("stop_reason") != "end_turn"
                or not isinstance(content, list)
                or len(content) != 1
                or not isinstance(content[0], dict)
                or content[0].get("type") != "text"
                or not isinstance(content[0].get("text"), str)
            ):
                raise ValueError(
                    "Anthropic response was not a complete JSON text block"
                )
            critique = Critique.model_validate_json(cast(str, content[0]["text"]))
        else:
            reviewer = ModelReviewer(
                cast(ModelClient, None),
                openai_registry(),
                judge_provider="openai",
                judge_model="gpt-5.6-luna",
                effort="low",
            )
            critique = reviewer.parse_critique(
                spec, request, response_from_payload(response)
            )
        validate_evidence(request, critique.findings)
    except (ValueError, ProviderError):
        raise ProviderError(
            "plan/test critic returned invalid citation evidence"
        ) from None
    observation = G4SingleOperatorCriticObservation(
        result=CriticResult(critic=spec, status="completed", critique=critique),
        request_sha256=digest(canonical_bytes(request)),
        response_sha256=digest(payload_bytes(response)),
        audit_sha256=digest((run / "outcome.json").read_bytes()),
        observed_at=datetime.now(UTC),
        full_subject_review_claimed=True,
    )
    private_write(run / "critic-observation.json", canonical_bytes(observation))
    return observation


def verify_plan_test_critic_audit(
    signed: SignedG4PlanTestCriticLiveGrant,
    *,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    spend: SpendPolicy,
    ledger: SpendLedger,
    claims: Path,
    run: Path,
) -> G4SingleOperatorCriticObservation:
    """Replay the full response, claim, measured settlement and broker chain."""
    if run.parent.resolve() != claims.resolve():
        raise ValueError("critic audit lies outside its claim store")
    body, reservation, entry = verify_plan_test_critic_grant(
        signed,
        packet=packet,
        policy=policy,
        authority=authority,
        spend=spend,
        ledger=ledger,
        now=signed.grant.issued_at,
    )
    files = {
        name: private_review_bytes(run / name)
        for name in (
            "critic-observation.json",
            "authorization.json",
            "admission.json",
            "outcome.json",
            "spend-receipt.json",
            "spend-reservation.json",
            "provider-response.json",
            "provider-request.json",
            "review-request.json",
            "spend-policy.json",
            "signed-grant.json",
        )
    }
    observation = G4SingleOperatorCriticObservation.model_validate_json(
        files["critic-observation.json"]
    )
    audit = G4PlanTestCriticAudit.model_validate_json(files["authorization.json"])
    admission = BrokerAdmission.model_validate_json(files["admission.json"])
    outcome = BrokerOutcome.model_validate_json(files["outcome.json"])
    receipt = SpendReceipt.model_validate_json(files["spend-receipt.json"])
    held = SpendReservation.model_validate_json(files["spend-reservation.json"])
    for name, value in (
        ("critic-observation.json", observation),
        ("authorization.json", audit),
        ("admission.json", admission),
        ("outcome.json", outcome),
        ("spend-receipt.json", receipt),
        ("spend-reservation.json", held),
    ):
        if files[name] != canonical_bytes(value):
            raise ValueError("critic audit contains noncanonical evidence")
    response = cast(dict[str, JsonValue], json.loads(files["provider-response.json"]))
    index = 0 if signed.grant.provider == "anthropic" else 1
    spec = authority.authority.critics[index]
    request = plan_test_requests(packet, authority.authority.critics)[index]
    if signed.grant.provider == "anthropic":
        content = response.get("content")
        if (
            response.get("type") != "message"
            or response.get("role") != "assistant"
            or response.get("stop_reason") != "end_turn"
            or not isinstance(content, list)
            or len(content) != 1
            or not isinstance(content[0], dict)
            or content[0].get("type") != "text"
            or not isinstance(content[0].get("text"), str)
        ):
            raise ValueError("retained Anthropic critic is incomplete")
        critique = Critique.model_validate_json(cast(str, content[0]["text"]))
    else:
        reviewer = ModelReviewer(
            cast(ModelClient, None),
            openai_registry(),
            judge_provider="openai",
            judge_model="gpt-5.6-luna",
            effort="low",
        )
        critique = reviewer.parse_critique(
            spec, request, response_from_payload(response)
        )
    validate_evidence(request, critique.findings)
    status = ledger.entry_status(entry.entry_id)
    if (
        private_review_bytes(claims / f"{signed.artifact_sha256}.claim")
        != canonical_bytes(signed)
        or observation.result
        != CriticResult(critic=spec, status="completed", critique=critique)
        or observation.request_sha256 != digest(canonical_bytes(request))
        or observation.response_sha256 != digest(files["provider-response.json"])
        or files["provider-response.json"] != payload_bytes(response)
        or observation.audit_sha256 != digest(files["outcome.json"])
        or audit.grant_sha256 != signed.artifact_sha256
        or audit.packet_sha256 != packet.packet_sha256
        or audit.review_authority_sha256 != authority.artifact_sha256
        or audit.critic_request_sha256 != digest(canonical_bytes(request))
        or audit.provider_request_sha256 != signed.grant.provider_request_sha256
        or audit.spend_policy_sha256 != spend.policy_sha256
        or audit.ledger_id != ledger.policy.ledger_id
        or audit.ledger_entry_id != entry.entry_id
        or admission.authorization_sha256 != digest(canonical_bytes(audit))
        or outcome.admission_sha256 != digest(canonical_bytes(admission))
        or outcome.status != "response_received"
        or outcome.response_sha256
        != digest(canonical_bytes(BrokerReply(response=response)))
        or files["provider-request.json"] != payload_bytes(body)
        or files["review-request.json"] != canonical_bytes(request)
        or files["spend-policy.json"] != canonical_bytes(spend)
        or files["signed-grant.json"] != canonical_bytes(signed)
        or held != reservation
        or receipt.status != "settled"
        or receipt.reservation_sha256 != entry.reservation_sha256
        or receipt.ledger_id != ledger.policy.ledger_id
        or receipt.ledger_entry_id != entry.entry_id
        or receipt.input_tokens is None
        or receipt.output_tokens is None
        or receipt.cache_write_tokens is None
        or receipt.retained_microusd
        != spend.cost(
            receipt.input_tokens, receipt.output_tokens, receipt.cache_write_tokens
        )
        or status is None
        or status.status != "settled"
        or status.reservation_sha256 != entry.reservation_sha256
        or status.reserved_microusd != entry.reserved_microusd
        or status.charged_microusd != receipt.retained_microusd
        or not signed.grant.issued_at
        <= observation.observed_at
        < signed.grant.expires_at
    ):
        raise ValueError("critic observation differs from its full retained audit")
    return observation
