"""Recompute judge findings from retained request-bound critic responses."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    CriticResult,
    CriticSpec,
    Digest,
    JudgeRequest,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.providers.brokered_openai import BrokeredOpenAIClient
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.providers.openai_responses import response_from_payload
from mos_eisley.providers.openai_spend import CountedTransport
from mos_eisley.review.pipeline import (
    critic_quorum_met,
    judge_findings,
    validate_evidence,
    validate_roster,
)
from mos_eisley.run.broker_audit import BrokerOutcome
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.model_evidence import ModelCompletion
from mos_eisley.run.process import MAX_WIRE_BYTES
from mos_eisley.run.provider_broker import MAX_REQUEST_BYTES
from mos_eisley.run.review_broker import (
    JudgeTransferAuthorization,
    PreparedJudgeTransfer,
    PreparedReviewEnvelope,
    ReviewAuthorization,
    ReviewSpendingEnvelope,
    verify_judge_transfer,
    verify_review_broker_audit,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write


class CriticEvidence(Contract):
    authorization_sha256: Digest
    completion_sha256: Digest
    outcome_sha256: Digest
    result: CriticResult


class ReviewEvidence(Contract):
    schema_version: Literal[1] = 1
    envelope_sha256: Digest
    policy: ReviewPolicy
    critics: Annotated[tuple[CriticEvidence, ...], Field(min_length=1, max_length=8)]
    judge_request: JudgeRequest


class EvidenceJudgeAuthorization(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["evidence_bound_review_judge"] = "evidence_bound_review_judge"
    evidence_sha256: Digest
    transfer_sha256: Digest


def _response_artifact(
    directory: Path, name: str, expected: str | None, limit: int
) -> bytes | None:
    path = directory / name
    if expected is None:
        if path.exists():
            raise ValueError("unexpected partial model evidence")
        return None
    raw = read_bounded(path, limit)
    if digest(raw) != expected:
        raise ValueError("retained model evidence hash mismatch")
    return raw


def _critic_evidence(
    authorization: ReviewAuthorization,
    directory: Path,
    reviewer: ModelReviewer,
    policy: ReviewPolicy,
) -> tuple[CriticEvidence, CriticRequest]:
    if authorization.role != "critic":
        raise ValueError("critic evidence requires an approved critic")
    outcome = verify_review_broker_audit(directory, authorization)
    critic = CriticSpec.model_validate_json(
        read_bounded(directory / "critic.json", MAX_REQUEST_BYTES)
    )
    model_request = ModelRequest.model_validate_json(
        read_bounded(directory / "model-request.json", MAX_REQUEST_BYTES)
    )
    request = CriticRequest.model_validate_json(
        read_bounded(directory / "review-input.json", MAX_REQUEST_BYTES)
    )
    if (
        request.brief.brief_id != authorization.brief_sha256
        or reviewer.critic_request(critic, request) != model_request
    ):
        raise ValueError("critic response projection or brief changed")
    raw_completion = read_bounded(directory / "model-completion.json", 4096)
    completion = ModelCompletion.model_validate_json(raw_completion)
    if (
        raw_completion != canonical_bytes(completion)
        or completion.request_sha256 != authorization.model_request_sha256
    ):
        raise ValueError("model completion request identity mismatch")
    raw_reply = _response_artifact(
        directory,
        "broker-response.json",
        completion.broker_response_sha256,
        MAX_WIRE_BYTES,
    )
    raw_response = _response_artifact(
        directory,
        "model-response.json",
        completion.model_response_sha256,
        model_request.max_output,
    )
    reply: BrokerReply | None = None
    if raw_reply is not None:
        reply = BrokerReply.model_validate_json(raw_reply)
        if (
            raw_reply != canonical_bytes(reply)
            or outcome.response_sha256 != completion.broker_response_sha256
        ):
            raise ValueError("retained reply differs from the broker outcome")
    result = CriticResult(critic=critic, status="error", error="provider_error")
    if completion.status == "received":
        if (
            reply is None
            or raw_response is None
            or outcome.status != "response_received"
            or reply.response.get("model") != model_request.model
        ):
            raise ValueError("received completion has no matching host reply")
        response = ModelResponse.model_validate_json(raw_response)
        if raw_response != canonical_bytes(
            response
        ) or response != response_from_payload(reply.response):
            raise ValueError("canonical model response differs from retained reply")
        try:
            critique = reviewer.parse_critique(critic, request, response)
        except ValueError:
            pass  # A complete but invalid model answer cannot satisfy quorum.
        else:
            try:
                validate_evidence(request.brief, critique.findings)
            except ValueError:
                result = CriticResult(
                    critic=critic, status="error", error="invalid_evidence"
                )
            else:
                result = CriticResult(
                    critic=critic, status="completed", critique=critique
                )
    if len(canonical_bytes(request)) > policy.max_request_bytes:
        result = CriticResult(critic=critic, status="error", error="budget_exceeded")
    return CriticEvidence(
        authorization_sha256=digest(canonical_bytes(authorization)),
        completion_sha256=digest(raw_completion),
        outcome_sha256=digest(canonical_bytes(outcome)),
        result=result,
    ), request


def verify_review_evidence(
    envelope: ReviewSpendingEnvelope,
    reviewer: ModelReviewer,
    ledger: SpendLedger,
    policy: ReviewPolicy,
) -> ReviewEvidence:
    """Reconstruct against a trusted envelope; incomplete artifacts fail closed."""
    envelope = ReviewSpendingEnvelope.model_validate_json(canonical_bytes(envelope))
    policy = ReviewPolicy.model_validate_json(canonical_bytes(policy))
    directory = Path(envelope.artifact_directory)
    if read_bounded(directory / "envelope.json", 32_768) != canonical_bytes(envelope):
        raise ValueError("retained review envelope changed")
    if digest(canonical_bytes(ledger.policy)) != envelope.ledger_policy_sha256:
        raise ValueError("review evidence spending scope changed")
    records: list[CriticEvidence] = []
    brief = None
    for call in envelope.critics:
        status = ledger.entry_status(call.ledger_entry_id)
        if (
            status is None
            or status.status == "held"
            or status.reservation_sha256 != call.reservation_sha256
            or status.reserved_microusd != call.reserved_microusd
        ):
            raise ValueError("critic evidence requires exact terminal accounting")
        record, request = _critic_evidence(
            call, directory / call.ledger_entry_id, reviewer, policy
        )
        if brief is not None and brief != request.brief:
            raise ValueError("critic evidence mixes briefs")
        brief = request.brief
        if record.result.status == "completed" and status.status != "settled":
            raise ValueError("usable critic response requires settled spending")
        records.append(record)
    results = tuple(record.result for record in records)
    validate_roster(tuple(result.critic for result in results), policy)
    if not critic_quorum_met(results, policy):
        raise ValueError("verified critic quorum was not met")
    assert brief is not None
    request = JudgeRequest(brief=brief, findings=judge_findings(results))
    if len(canonical_bytes(request)) > policy.max_request_bytes:
        raise ValueError("verified judge request exceeds the review budget")
    evidence = ReviewEvidence(
        envelope_sha256=digest(canonical_bytes(envelope)),
        policy=policy,
        critics=tuple(records),
        judge_request=request,
    )
    if len(canonical_bytes(evidence)) > MAX_WIRE_BYTES:
        raise ValueError("review evidence exceeds its artifact budget")
    return evidence


class PreparedEvidenceJudgeTransfer:
    """Bind judge approval to freshly verified retained critic evidence."""

    def __init__(
        self,
        envelope: PreparedReviewEnvelope,
        reviewer: ModelReviewer,
        policy: ReviewPolicy | None = None,
    ) -> None:
        self._envelope = envelope
        self._reviewer = reviewer
        self._evidence = verify_review_evidence(
            envelope.envelope,
            reviewer,
            envelope.ledger,
            policy if policy is not None else ReviewPolicy(),
        )
        self._transfer = PreparedJudgeTransfer(
            envelope, reviewer, self._evidence.judge_request
        )
        self._authorization = EvidenceJudgeAuthorization(
            evidence_sha256=digest(canonical_bytes(self._evidence)),
            transfer_sha256=self._transfer.approval_sha256,
        )

    @property
    def evidence(self) -> ReviewEvidence:
        return self._evidence

    @property
    def authorization(self) -> EvidenceJudgeAuthorization:
        return self._authorization

    @property
    def model_request(self) -> ModelRequest:
        return self._transfer.model_request

    @property
    def approval_sha256(self) -> str:
        return digest(canonical_bytes(self._authorization))

    def issue(
        self,
        *,
        approved_evidence_sha256: str,
        transport: CountedTransport,
        container: OfflineContainer,
        timeout: float = 30,
    ) -> BrokeredOpenAIClient:
        if approved_evidence_sha256 != self.approval_sha256:
            raise ValueError("exact evidence-bound judge approval required")
        current = verify_review_evidence(
            self._envelope.envelope,
            self._reviewer,
            self._envelope.ledger,
            self._evidence.policy,
        )
        if current != self._evidence:
            raise ValueError("critic evidence changed after judge approval")
        client = self._transfer.issue(
            approved_transfer_sha256=self._transfer.approval_sha256,
            transport=transport,
            container=container,
            timeout=timeout,
        )
        directory = Path(self._envelope.envelope.artifact_directory)
        private_write(
            directory / "review-evidence.json", canonical_bytes(self._evidence)
        )
        private_write(
            directory / "review-evidence-approval.json",
            canonical_bytes(self._authorization),
        )
        return client


def verify_evidence_judge_transfer(
    envelope: ReviewSpendingEnvelope,
    reviewer: ModelReviewer,
    ledger: SpendLedger,
    expected: EvidenceJudgeAuthorization,
) -> BrokerOutcome:
    """Verify critic lineage and judge audit without provider or retry authority."""
    directory = Path(envelope.artifact_directory)
    expected = EvidenceJudgeAuthorization.model_validate_json(canonical_bytes(expected))
    if (
        EvidenceJudgeAuthorization.model_validate_json(
            read_bounded(directory / "review-evidence-approval.json", 4096)
        )
        != expected
    ):
        raise ValueError("evidence approval mismatch")
    raw = read_bounded(directory / "review-evidence.json", MAX_WIRE_BYTES)
    evidence = ReviewEvidence.model_validate_json(raw)
    if raw != canonical_bytes(evidence) or digest(raw) != expected.evidence_sha256:
        raise ValueError("retained review evidence mismatch")
    if verify_review_evidence(envelope, reviewer, ledger, evidence.policy) != evidence:
        raise ValueError("retained critic evidence changed")
    transfer = JudgeTransferAuthorization.model_validate_json(
        read_bounded(directory / "judge-transfer.json", 8192)
    )
    if digest(
        canonical_bytes(transfer)
    ) != expected.transfer_sha256 or transfer.call.review_input_sha256 != digest(
        canonical_bytes(evidence.judge_request)
    ):
        raise ValueError("judge transfer differs from verified findings")
    return verify_judge_transfer(directory, transfer, ledger)
