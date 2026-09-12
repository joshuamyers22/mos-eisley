"""Reconstruct and retain final review results without provider authority."""

from pathlib import Path
from typing import Literal

from mos_eisley.core.models import (
    Contract,
    Digest,
    ReviewResult,
    Verdict,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import ModelRequest
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.review.pipeline import judge_verdict
from mos_eisley.run.files import read_bounded
from mos_eisley.run.process import MAX_WIRE_BYTES
from mos_eisley.run.provider_broker import MAX_REQUEST_BYTES
from mos_eisley.run.review_broker import (
    JudgeTransferAuthorization,
    ReviewSpendingEnvelope,
)
from mos_eisley.run.review_evidence import (
    EvidenceJudgeAuthorization,
    ReviewEvidence,
    verify_evidence_judge_transfer,
    verify_model_completion,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write


class RetainedReviewResult(Contract):
    schema_version: Literal[1] = 1
    approval_sha256: Digest
    judge_completion_sha256: Digest
    judge_outcome_sha256: Digest
    result: ReviewResult


def reconstruct_review_result(
    envelope: ReviewSpendingEnvelope,
    reviewer: ModelReviewer,
    ledger: SpendLedger,
    expected: EvidenceJudgeAuthorization,
) -> RetainedReviewResult:
    """Recompute from trusted approval; incomplete or corrupt records raise."""
    outcome = verify_evidence_judge_transfer(envelope, reviewer, ledger, expected)
    directory = Path(envelope.artifact_directory)
    raw = read_bounded(directory / "review-evidence.json", MAX_WIRE_BYTES)
    if digest(raw) != expected.evidence_sha256:
        raise ValueError("review evidence changed during reconstruction")
    evidence = ReviewEvidence.model_validate_json(raw)
    transfer = JudgeTransferAuthorization.model_validate_json(
        read_bounded(directory / "judge-transfer.json", 8192)
    )
    if digest(canonical_bytes(transfer)) != expected.transfer_sha256:
        raise ValueError("judge transfer changed during reconstruction")
    request = ModelRequest.model_validate_json(
        read_bounded(directory / "judge" / "model-request.json", MAX_REQUEST_BYTES)
    )
    if (
        digest(canonical_bytes(request)) != transfer.call.model_request_sha256
        or reviewer.judge_request(evidence.judge_request) != request
    ):
        raise ValueError("judge response projection changed")
    completion, response = verify_model_completion(
        directory / "judge", request, outcome
    )
    status = ledger.entry_status(transfer.call.ledger_entry_id)
    if status is None or status.status == "held":
        raise ValueError("judge result requires terminal accounting")
    if response is not None and status.status != "settled":
        raise ValueError("received judge response requires settled spending")
    critics = tuple(item.result for item in evidence.critics)
    result = ReviewResult(
        critics=critics,
        judge_request=evidence.judge_request,
        verdict=Verdict(
            brief_id=evidence.judge_request.brief.brief_id,
            decision="infrastructure_error",
            rationale="Judge did not return a valid decision.",
        ),
    )
    if response is not None:
        try:
            decision = reviewer.parse_judge(evidence.judge_request, response)
        except ValueError:
            pass
        else:
            try:
                verdict = judge_verdict(evidence.judge_request, decision)
            except ValueError:
                result = result.model_copy(
                    update={
                        "verdict": Verdict(
                            brief_id=evidence.judge_request.brief.brief_id,
                            decision="infrastructure_error",
                            rationale=(
                                "Judge returned duplicate or unknown finding IDs."
                            ),
                        )
                    }
                )
            else:
                result = ReviewResult(
                    critics=critics,
                    judge_request=evidence.judge_request,
                    judge_decision=decision,
                    verdict=verdict,
                )
    retained = RetainedReviewResult(
        approval_sha256=digest(canonical_bytes(expected)),
        judge_completion_sha256=digest(canonical_bytes(completion)),
        judge_outcome_sha256=digest(canonical_bytes(outcome)),
        result=result,
    )
    if len(canonical_bytes(retained)) > MAX_WIRE_BYTES:
        raise ValueError("review result exceeds its artifact budget")
    return retained


def retain_review_result(
    envelope: ReviewSpendingEnvelope,
    reviewer: ModelReviewer,
    ledger: SpendLedger,
    expected: EvidenceJudgeAuthorization,
) -> RetainedReviewResult:
    """Save one freshly reconstructed result; never issue or retry a call."""
    result = reconstruct_review_result(envelope, reviewer, ledger, expected)
    private_write(
        Path(envelope.artifact_directory) / "review-result.json",
        canonical_bytes(result),
    )
    return result


def verify_retained_review_result(
    envelope: ReviewSpendingEnvelope,
    reviewer: ModelReviewer,
    ledger: SpendLedger,
    expected: EvidenceJudgeAuthorization,
    expected_result_sha256: str,
) -> RetainedReviewResult:
    """Verify a pinned final artifact and recompute its complete evidence chain."""
    raw = read_bounded(
        Path(envelope.artifact_directory) / "review-result.json", MAX_WIRE_BYTES
    )
    if digest(raw) != expected_result_sha256:
        raise ValueError("retained review result hash mismatch")
    result = reconstruct_review_result(envelope, reviewer, ledger, expected)
    if raw != canonical_bytes(result):
        raise ValueError("retained review result differs from reconstructed evidence")
    return result
