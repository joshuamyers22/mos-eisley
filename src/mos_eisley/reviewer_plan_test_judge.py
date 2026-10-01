"""One-use judge authority over two replayed pre-delegation judge audits."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue, field_validator, model_validator

from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ModelClient, ProviderError
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.anthropic_review import payload_bytes
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
from mos_eisley.review.pipeline import judge_findings, judge_verdict
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_plan_test_live import (
    SignedG4PlanTestCriticLiveGrant,
    private_review_bytes,
    verify_plan_test_critic_audit,
)
from mos_eisley.reviewer_plan_test_review import (
    G4PlanTestReviewPacket,
    SignedG4PlanTestReviewAuthority,
    plan_test_brief,
    verify_plan_test_authority,
)
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    verify_provenance_signature,
)
from mos_eisley.reviewer_review_spend import verify_review_reservation
from mos_eisley.reviewer_single_operator_review import G4SingleOperatorJudgeObservation
from mos_eisley.run.broker_audit import (
    BrokerAdmission,
    BrokerAudit,
    BrokerAuthorization,
    BrokerOutcome,
)
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write

DOMAIN = b"mos-eisley/g4-plan-test-judge-live-grant/v1\x00"


class G4PlanTestJudgeLiveGrant(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_pre_delegation_plan_test_judge_live_grant"] = (
        "g4_pre_delegation_plan_test_judge_live_grant"
    )
    grant_id: Identifier
    provider: Literal["openai"] = "openai"
    critic_observation_sha256: tuple[Digest, Digest]
    packet_sha256: Digest
    review_authority_sha256: Digest
    provenance_policy_sha256: Digest
    judge_request_sha256: Digest
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    reservation_sha256: Digest
    reserved_microusd: Literal[20_916]
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
            raise ValueError("judge grant timestamps require UTC")
        return value

    @model_validator(mode="after")
    def window(self) -> G4PlanTestJudgeLiveGrant:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=1):
            raise ValueError("judge grant exceeds one hour")
        return self


class SignedG4PlanTestJudgeLiveGrant(Contract):
    grant: G4PlanTestJudgeLiveGrant
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4PlanTestJudgeAudit(BrokerAuthorization):
    schema_version: Literal[1] = 1
    mode: Literal["g4_plan_test_judge"] = "g4_plan_test_judge"
    grant_sha256: Digest
    packet_sha256: Digest
    review_authority_sha256: Digest
    judge_request_sha256: Digest


@dataclass(frozen=True)
class PlanTestCriticAuditInput:
    signed: SignedG4PlanTestCriticLiveGrant
    spend: SpendPolicy
    claims: Path
    run: Path


def verified_plan_test_judge_request(
    *,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    ledger: SpendLedger,
    critics: tuple[PlanTestCriticAuditInput, PlanTestCriticAuditInput],
) -> tuple[JudgeRequest, tuple[str, str]]:
    if tuple(item.signed.grant.provider for item in critics) != ("anthropic", "openai"):
        raise ValueError("judge requires both authorized critics in roster order")
    observations = tuple(
        verify_plan_test_critic_audit(
            item.signed,
            packet=packet,
            policy=policy,
            authority=authority,
            spend=item.spend,
            ledger=ledger,
            claims=item.claims,
            run=item.run,
        )
        for item in critics
    )
    if any(item.result.status != "completed" for item in observations):
        raise ValueError("judge requires two completed critics")
    request = JudgeRequest(
        brief=plan_test_brief(packet),
        findings=judge_findings(tuple(item.result for item in observations)),
    )
    return request, (observations[0].artifact_sha256, observations[1].artifact_sha256)


def prepare_plan_test_judge_grant(
    *,
    grant_id: str,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    critics: tuple[PlanTestCriticAuditInput, PlanTestCriticAuditInput],
    spend: SpendPolicy,
    ledger: SpendLedger,
    entry_id: str,
    issued: datetime,
    expires: datetime,
) -> tuple[G4PlanTestJudgeLiveGrant, dict[str, JsonValue], SpendReservation]:
    verify_plan_test_authority(authority, packet, policy, now=issued)
    request, observations = verified_plan_test_judge_request(
        packet=packet,
        policy=policy,
        authority=authority,
        ledger=ledger,
        critics=critics,
    )
    if (
        authority.authority.judge_provider != "openai"
        or authority.authority.judge_model != "gpt-5.6-luna"
        or spend.schema_version != 2
        or spend.model != "gpt-5.6-luna"
        or spend.service_tier != "default"
        or spend.pricing_source
        != "https://developers.openai.com/api/docs/models/gpt-5.6-luna"
        or spend.input_microusd_per_million != 200_000
        or spend.cache_write_microusd_per_million != 250_000
        or spend.output_microusd_per_million != 1_200_000
        or spend.max_input_tokens != 64_000
        or spend.max_output_tokens != 4096
        or spend.max_cost_microusd != 50_000
        or ledger.policy.ceiling_microusd
        != authority.authority.proposed_review_ceiling_microusd
        or not spend.valid_from <= issued < expires <= spend.valid_until
        or expires > authority.authority.expires_at
    ):
        raise ValueError("plan judge spending envelope differs from authority")
    spend.check_current(issued)
    reviewer = ModelReviewer(
        cast(ModelClient, None),
        openai_registry(),
        judge_provider="openai",
        judge_model="gpt-5.6-luna",
        effort="low",
    )
    body = request_payload(reviewer.judge_request(request))
    body["service_tier"] = "default"
    body["parallel_tool_calls"] = False
    reservation = prepare_full_reservation(body, spend)
    if reservation.reserved_microusd != 20_916:
        raise ValueError("plan judge reservation changed")
    verify_review_reservation(ledger, entry_id, reservation)
    grant = G4PlanTestJudgeLiveGrant(
        grant_id=grant_id,
        critic_observation_sha256=observations,
        packet_sha256=packet.packet_sha256,
        review_authority_sha256=authority.artifact_sha256,
        provenance_policy_sha256=policy.policy_sha256,
        judge_request_sha256=digest(canonical_bytes(request)),
        provider_request_sha256=digest(payload_bytes(body)),
        spend_policy_sha256=spend.policy_sha256,
        reservation_sha256=digest(canonical_bytes(reservation)),
        reserved_microusd=20_916,
        ledger_id=ledger.policy.ledger_id,
        ledger_policy_sha256=digest(canonical_bytes(ledger.policy)),
        ledger_entry_id=entry_id,
        issued_at=issued,
        expires_at=expires,
    )
    return grant, body, reservation


def sign_plan_test_judge_grant(
    grant: G4PlanTestJudgeLiveGrant, key: Ed25519PrivateKey
) -> SignedG4PlanTestJudgeLiveGrant:
    return SignedG4PlanTestJudgeLiveGrant(
        grant=grant,
        signature=G4ArtifactSignature(
            signer_id="joshua-myers",
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(DOMAIN + canonical_bytes(grant))
            ).decode("ascii"),
        ),
    )


def verify_plan_test_judge_grant(
    signed: SignedG4PlanTestJudgeLiveGrant,
    *,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    critics: tuple[PlanTestCriticAuditInput, PlanTestCriticAuditInput],
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
        raise ValueError("live judge signer differs from review owner")
    grant = signed.grant
    expected, body, reservation = prepare_plan_test_judge_grant(
        grant_id=grant.grant_id,
        packet=packet,
        policy=policy,
        authority=authority,
        critics=critics,
        spend=spend,
        ledger=ledger,
        entry_id=grant.ledger_entry_id,
        issued=grant.issued_at,
        expires=grant.expires_at,
    )
    if grant != expected or not grant.issued_at <= now < grant.expires_at:
        raise ValueError("live plan-review judge grant changed or expired")
    return (
        body,
        reservation,
        LedgerEntry(
            entry_id=grant.ledger_entry_id,
            reservation_sha256=grant.reservation_sha256,
            reserved_microusd=grant.reserved_microusd,
        ),
    )


async def run_plan_test_judge_once(
    signed: SignedG4PlanTestJudgeLiveGrant,
    *,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    critics: tuple[PlanTestCriticAuditInput, PlanTestCriticAuditInput],
    spend: SpendPolicy,
    ledger: SpendLedger,
    claims: Path,
    run: Path,
    transport: CountedTransport,
) -> G4SingleOperatorJudgeObservation:
    body, reservation, entry = verify_plan_test_judge_grant(
        signed,
        packet=packet,
        policy=policy,
        authority=authority,
        critics=critics,
        spend=spend,
        ledger=ledger,
        now=datetime.now(UTC),
    )
    spend.check_current()
    if run.parent.resolve() != claims.resolve():
        raise ValueError("judge run must be inside its private claim store")
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
    request, _ = verified_plan_test_judge_request(
        packet=packet,
        policy=policy,
        authority=authority,
        ledger=ledger,
        critics=critics,
    )
    audit = BrokerAudit(
        run,
        G4PlanTestJudgeAudit(
            provider_request_sha256=signed.grant.provider_request_sha256,
            spend_policy_sha256=spend.policy_sha256,
            ledger_id=ledger.policy.ledger_id,
            ledger_entry_id=entry.entry_id,
            grant_sha256=signed.artifact_sha256,
            packet_sha256=packet.packet_sha256,
            review_authority_sha256=authority.artifact_sha256,
            judge_request_sha256=digest(canonical_bytes(request)),
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
    controller = PreReservedOpenAITransport(
        transport, spend, run, ledger, reservation, entry
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
            raise ProviderError("retained judge response differs from transport")
    else:
        private_write(response_path, response_bytes)
    reviewer = ModelReviewer(
        cast(ModelClient, None),
        openai_registry(),
        judge_provider="openai",
        judge_model="gpt-5.6-luna",
        effort="low",
    )
    decision = reviewer.parse_judge(request, response_from_payload(response))
    judge_verdict(request, decision)
    observation = G4SingleOperatorJudgeObservation(
        provider="openai",
        model="gpt-5.6-luna",
        decision=decision,
        request_sha256=digest(canonical_bytes(request)),
        response_sha256=digest(payload_bytes(response)),
        audit_sha256=digest((run / "outcome.json").read_bytes()),
        observed_at=datetime.now(UTC),
    )
    private_write(run / "judge-observation.json", canonical_bytes(observation))
    return observation


def verify_plan_test_judge_audit(
    signed: SignedG4PlanTestJudgeLiveGrant,
    *,
    packet: G4PlanTestReviewPacket,
    policy: G4ProvenanceTrustPolicy,
    authority: SignedG4PlanTestReviewAuthority,
    critics: tuple[PlanTestCriticAuditInput, PlanTestCriticAuditInput],
    spend: SpendPolicy,
    ledger: SpendLedger,
    claims: Path,
    run: Path,
) -> G4SingleOperatorJudgeObservation:
    """Replay the full response, claim, measured settlement and broker chain."""
    if run.parent.resolve() != claims.resolve():
        raise ValueError("judge audit lies outside its claim store")
    body, reservation, entry = verify_plan_test_judge_grant(
        signed,
        packet=packet,
        policy=policy,
        authority=authority,
        critics=critics,
        spend=spend,
        ledger=ledger,
        now=signed.grant.issued_at,
    )
    files = {
        name: private_review_bytes(run / name)
        for name in (
            "judge-observation.json",
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
    observation = G4SingleOperatorJudgeObservation.model_validate_json(
        files["judge-observation.json"]
    )
    audit = G4PlanTestJudgeAudit.model_validate_json(files["authorization.json"])
    admission = BrokerAdmission.model_validate_json(files["admission.json"])
    outcome = BrokerOutcome.model_validate_json(files["outcome.json"])
    receipt = SpendReceipt.model_validate_json(files["spend-receipt.json"])
    held = SpendReservation.model_validate_json(files["spend-reservation.json"])
    for name, value in (
        ("judge-observation.json", observation),
        ("authorization.json", audit),
        ("admission.json", admission),
        ("outcome.json", outcome),
        ("spend-receipt.json", receipt),
        ("spend-reservation.json", held),
    ):
        if files[name] != canonical_bytes(value):
            raise ValueError("judge audit contains noncanonical evidence")
    response = cast(dict[str, JsonValue], json.loads(files["provider-response.json"]))
    request, _ = verified_plan_test_judge_request(
        packet=packet,
        policy=policy,
        authority=authority,
        ledger=ledger,
        critics=critics,
    )
    reviewer = ModelReviewer(
        cast(ModelClient, None),
        openai_registry(),
        judge_provider="openai",
        judge_model="gpt-5.6-luna",
        effort="low",
    )
    decision = reviewer.parse_judge(request, response_from_payload(response))
    judge_verdict(request, decision)
    status = ledger.entry_status(entry.entry_id)
    if (
        private_review_bytes(claims / f"{signed.artifact_sha256}.claim")
        != canonical_bytes(signed)
        or observation.decision != decision
        or observation.provider != "openai"
        or observation.model != "gpt-5.6-luna"
        or observation.request_sha256 != digest(canonical_bytes(request))
        or observation.response_sha256 != digest(files["provider-response.json"])
        or files["provider-response.json"] != payload_bytes(response)
        or observation.audit_sha256 != digest(files["outcome.json"])
        or audit.grant_sha256 != signed.artifact_sha256
        or audit.packet_sha256 != packet.packet_sha256
        or audit.review_authority_sha256 != authority.artifact_sha256
        or audit.judge_request_sha256 != digest(canonical_bytes(request))
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
        raise ValueError("judge observation differs from its full retained audit")
    return observation
