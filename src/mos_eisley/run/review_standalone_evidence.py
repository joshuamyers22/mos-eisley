"""One-file retention and replay verification for a standalone review probe."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.run.review_campaign import (
    CAMPAIGN_BYTES,
    CampaignAttempt,
    CampaignAttemptSubmission,
    campaign_reviewer,
)
from mos_eisley.run.review_conformance_observation import (
    AuthenticatedReviewProbe,
    authenticate_review_probe,
)
from mos_eisley.run.review_runtime_evidence import verify_review_runtime_exchange
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write


class StandaloneReviewEvidence(Contract):
    """Complete serialized inputs for replaying one probe authentication."""

    schema_version: Literal[1] = 1
    mode: Literal["standalone_review_evidence"] = "standalone_review_evidence"
    attempt: CampaignAttempt
    submission: CampaignAttemptSubmission
    provider_dispatch_authorized: Literal[False] = False
    live_review_activation_authorized: Literal[False] = False
    retry_authorized: Literal[False] = False


def decode_standalone_review_evidence(raw: bytes) -> StandaloneReviewEvidence:
    if len(raw) > CAMPAIGN_BYTES:
        raise ValueError("standalone review evidence exceeds its byte limit")
    try:
        json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        return StandaloneReviewEvidence.model_validate_json(raw)
    except (ValueError, RecursionError):
        raise ValueError("invalid standalone review evidence JSON") from None


def verify_standalone_review_evidence(
    evidence: StandaloneReviewEvidence, *, now: datetime
) -> AuthenticatedReviewProbe:
    """Freshly authenticate a retained standalone probe without dispatch authority."""
    evidence = decode_standalone_review_evidence(canonical_bytes(evidence))
    attempt, supplied = evidence.attempt, evidence.submission
    lifecycles = tuple(Path(path) for path in supplied.lifecycle_directories)
    if any(not path.is_absolute() for path in lifecycles) or len(
        set(lifecycles)
    ) != len(lifecycles):
        raise ValueError(
            "standalone review evidence requires distinct absolute lifecycle paths"
        )
    reviewer = campaign_reviewer(attempt.configuration)
    authenticated = authenticate_review_probe(
        supplied.signed_observation,
        attempt.observation_policy,
        attempt.authority_policy,
        attempt.preview,
        supplied.start,
        supplied.judge,
        supplied.authorizations,
        reviewer,
        SpendLedger(Path(attempt.ledger_path)),
        expected_result_sha256=supplied.expected_result_sha256,
        now=now,
    )
    directory = Path(attempt.preview.envelope.artifact_directory)
    call_directories = (
        *(
            directory / call.ledger_entry_id
            for call in attempt.preview.envelope.critics
        ),
        directory / "judge",
    )
    requests = (*attempt.preview.requests, supplied.judge.model_request)
    if len(lifecycles) != len(requests):
        raise ValueError("standalone review evidence requires every worker lifecycle")
    for index, (call_directory, lifecycle, request, exchange) in enumerate(
        zip(
            call_directories,
            lifecycles,
            requests,
            supplied.signed_observation.observation.exchanges,
            strict=True,
        )
    ):
        authorization = supplied.authorizations[
            1 if index == len(attempt.preview.requests) else 0
        ].authorization
        verify_review_runtime_exchange(
            exchange, call_directory, lifecycle, request, authorization
        )
    return authenticated


def retain_standalone_review_evidence(
    output: Path, evidence: StandaloneReviewEvidence, *, now: datetime
) -> AuthenticatedReviewProbe:
    """Verify, then exclusively retain, one complete private replay bundle."""
    evidence = decode_standalone_review_evidence(canonical_bytes(evidence))
    authenticated = verify_standalone_review_evidence(evidence, now=now)
    parent = output.parent
    parent_stat = parent.stat()
    if (
        not output.is_absolute()
        or output.exists()
        or output.is_symlink()
        or not parent.is_dir()
        or parent.is_symlink()
        or parent_stat.st_uid != os.geteuid()
        or parent_stat.st_mode & 0o077
    ):
        raise ValueError("standalone review evidence requires a new private output")
    protected = (
        Path(evidence.attempt.preview.envelope.artifact_directory),
        *(Path(path) for path in evidence.submission.lifecycle_directories),
    )
    resolved = output.resolve()
    if any(resolved.is_relative_to(path.resolve()) for path in protected):
        raise ValueError("standalone review evidence must be outside runtime evidence")
    private_write(output, canonical_bytes(evidence))
    return authenticated
