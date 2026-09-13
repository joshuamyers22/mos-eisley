"""Offline unsigned observation proposals from independently selected evidence."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.review_campaign import (
    CAMPAIGN_BYTES,
    campaign_reviewer,
    read_campaign_seal,
)
from mos_eisley.run.review_campaign_runner import CampaignProbeCompletion
from mos_eisley.run.review_conformance_acceptance import review_role_profile
from mos_eisley.run.review_conformance_authorization import (
    review_conformance_scope,
    verify_review_conformance_authorization,
)
from mos_eisley.run.review_conformance_observation import (
    ReviewProbeObservation,
    make_review_probe_observation,
)
from mos_eisley.run.review_runtime_evidence import collect_review_runtime_exchange
from mos_eisley.run.spend_ledger import SpendLedger


def decode_probe_completion(raw: bytes) -> CampaignProbeCompletion:
    if len(raw) > CAMPAIGN_BYTES:
        raise ValueError("campaign completion exceeds its byte limit")
    try:
        json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        completion = CampaignProbeCompletion.model_validate_json(raw)
    except (ValueError, RecursionError):
        raise ValueError("invalid campaign completion JSON") from None
    if (
        any(
            value.tzinfo is None or value.utcoffset() != timedelta(0)
            for value in (completion.start.started_at, completion.start.expires_at)
        )
        or completion.start.started_at >= completion.start.expires_at
    ):
        raise ValueError("campaign completion requires an ordered UTC start window")
    return completion


class CampaignObservationPreview(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_campaign_observation_preview"] = (
        "review_campaign_observation_preview"
    )
    seal_sha256: Digest
    canonical_completion_sha256: Digest
    unsigned_observation: ReviewProbeObservation
    observer_authenticated: Literal[False] = False
    signature_created: Literal[False] = False
    requires_independent_attestation: Literal[True] = True
    provider_dispatch_authorized: Literal[False] = False
    live_review_activation_authorized: Literal[False] = False

    @property
    def observation_sha256(self) -> str:
        return digest(canonical_bytes(self.unsigned_observation))


def preview_campaign_observation(
    campaign_directory: Path,
    expected_seal_sha256: str,
    completion: CampaignProbeCompletion,
    *,
    lifecycle_directories: tuple[Path, ...],
    now: datetime,
) -> CampaignObservationPreview:
    completion = decode_probe_completion(canonical_bytes(completion))
    if completion.seal_sha256 != expected_seal_sha256:
        raise ValueError("campaign completion targets another seal")
    bundle, seal = read_campaign_seal(campaign_directory, expected_seal_sha256)
    attempt = bundle.attempts[completion.attempt_index]
    if (
        now.tzinfo is None
        or now.utcoffset() != timedelta(0)
        or not seal.sealed_at
        <= completion.start.started_at
        <= now
        < bundle.policy.valid_until
        or completion.start.authorization != attempt.preview.authorization
        or review_role_profile(completion.judge.model_request) != bundle.policy.judge
        or len(lifecycle_directories) != len(attempt.preview.requests) + 1
        or any(not path.is_absolute() for path in lifecycle_directories)
    ):
        raise ValueError(
            "campaign completion differs from its committed slot or evidence scope"
        )
    critics = attempt.preview
    scopes = (
        review_conformance_scope(critics, **bundle.policy.runtime.model_dump()),
        review_conformance_scope(
            critics,
            **bundle.policy.runtime.model_dump(),
            judge=completion.judge,
            start=completion.start,
        ),
    )
    for signed, scope in zip(completion.authorizations, scopes, strict=True):
        verify_review_conformance_authorization(
            signed, attempt.authority_policy, scope, signed.authorization.issued_at
        )
    directory = Path(critics.envelope.artifact_directory)
    call_directories = (
        *(directory / call.ledger_entry_id for call in critics.envelope.critics),
        directory / "judge",
    )
    requests = (*critics.requests, completion.judge.model_request)
    exchanges = tuple(
        collect_review_runtime_exchange(
            call_directory,
            lifecycle,
            request,
            completion.authorizations[
                1 if index == len(critics.requests) else 0
            ].authorization,
        )
        for index, (call_directory, lifecycle, request) in enumerate(
            zip(call_directories, lifecycle_directories, requests, strict=True)
        )
    )
    observation = make_review_probe_observation(
        attempt.observation_policy,
        attempt.authority_policy,
        critics,
        completion.start,
        completion.judge,
        completion.authorizations,
        campaign_reviewer(attempt.configuration),
        SpendLedger(Path(attempt.ledger_path)),
        expected_result_sha256=completion.expected_result_sha256,
        exchanges=exchanges,
        observed_at=now,
    )
    return CampaignObservationPreview(
        seal_sha256=expected_seal_sha256,
        canonical_completion_sha256=digest(canonical_bytes(completion)),
        unsigned_observation=observation,
    )
