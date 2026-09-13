"""Append independently signed evidence to one fixed campaign slot, without keys."""

import json
from datetime import datetime
from pathlib import Path

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, canonical_bytes, digest
from mos_eisley.run.review_campaign import (
    CAMPAIGN_BYTES,
    CampaignAttemptSubmission,
    CampaignEvidenceSubmission,
    decode_campaign_submission,
    review_campaign_evidence,
)
from mos_eisley.run.review_campaign_observation import (
    CampaignObservationPreview,
    decode_observation_preview,
    decode_probe_completion,
)
from mos_eisley.run.review_campaign_runner import CampaignProbeCompletion
from mos_eisley.run.review_conformance_acceptance import ReviewAcceptanceResult
from mos_eisley.run.review_conformance_observation import SignedReviewProbeObservation


def decode_signed_observation(raw: bytes) -> SignedReviewProbeObservation:
    if len(raw) > CAMPAIGN_BYTES:
        raise ValueError("signed observation exceeds its byte limit")
    try:
        json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        return SignedReviewProbeObservation.model_validate_json(raw)
    except (ValueError, RecursionError):
        raise ValueError("invalid signed observation JSON") from None


class CampaignEvidenceAppend(Contract):
    submission: CampaignEvidenceSubmission
    review: ReviewAcceptanceResult


def append_campaign_observation(
    campaign_directory: Path,
    expected_seal_sha256: str,
    completion: CampaignProbeCompletion,
    preview: CampaignObservationPreview,
    signed_observation: SignedReviewProbeObservation,
    *,
    lifecycle_directories: tuple[Path, ...],
    previous: CampaignEvidenceSubmission | None = None,
    now: datetime,
) -> CampaignEvidenceAppend:
    completion = decode_probe_completion(canonical_bytes(completion))
    preview = decode_observation_preview(canonical_bytes(preview))
    signed = decode_signed_observation(canonical_bytes(signed_observation))
    if (
        preview.seal_sha256 != expected_seal_sha256
        or completion.seal_sha256 != expected_seal_sha256
        or preview.canonical_completion_sha256 != digest(canonical_bytes(completion))
        or canonical_bytes(signed.observation)
        != canonical_bytes(preview.unsigned_observation)
    ):
        raise ValueError(
            "signed observation differs from its selected preview or completion"
        )
    prior = (
        CampaignEvidenceSubmission(
            seal_sha256=expected_seal_sha256, attempts=(None, None, None)
        )
        if previous is None
        else decode_campaign_submission(canonical_bytes(previous))
    )
    index = completion.attempt_index
    if (
        prior.seal_sha256 != expected_seal_sha256
        or any(slot is None for slot in prior.attempts[:index])
        or any(slot is not None for slot in prior.attempts[index:])
    ):
        raise ValueError(
            "campaign evidence must append the next empty slot without replacement"
        )
    supplied = CampaignAttemptSubmission(
        start=completion.start,
        judge=completion.judge,
        authorizations=completion.authorizations,
        signed_observation=signed,
        expected_result_sha256=completion.expected_result_sha256,
        lifecycle_directories=tuple(str(path) for path in lifecycle_directories),
    )
    slots = list(prior.attempts)
    slots[index] = supplied
    candidate = CampaignEvidenceSubmission(
        seal_sha256=expected_seal_sha256, attempts=tuple(slots)
    )
    reviewed = review_campaign_evidence(
        campaign_directory, expected_seal_sha256, candidate, now=now
    )
    if reviewed.qualifying_attempts != index + 1:
        raise ValueError(
            "campaign evidence did not verify the complete supplied prefix"
        )
    return CampaignEvidenceAppend(submission=candidate, review=reviewed)
