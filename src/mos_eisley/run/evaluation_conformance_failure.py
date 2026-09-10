"""Retained evidence for failures before OpenAI credential access."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.execution import ExecutionBatch
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.evaluation_conformance import EvaluationConformancePolicy
from mos_eisley.run.evaluation_conformance_authorization import (
    EvaluationConformanceAuthorityPolicy,
    SignedEvaluationConformanceAuthorization,
)
from mos_eisley.run.spend_ledger import LedgerEntryStatus, LedgerSnapshot


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class EvaluationConformancePrecredentialRejection(Contract):
    """Content-addressed F1 evidence with literal downstream denials."""

    schema_version: Literal[1] = 1
    mode: Literal["evaluation_conformance_precredential_rejection"] = (
        "evaluation_conformance_precredential_rejection"
    )
    boundary_id: Literal["F1"] = "F1"
    observed_at: datetime
    rejection_stage: Literal["authorization_verification"] = (
        "authorization_verification"
    )
    rejection_kind: Literal["expired_or_exact_binding_mismatch"] = (
        "expired_or_exact_binding_mismatch"
    )
    plan_sha256: Digest
    batch_sha256: Digest
    sample_id: Digest
    candidate_id: Digest
    evaluation_request_sha256: Digest
    provider_request_sha256: Digest
    spend_policy_sha256: Digest
    conformance_policy_sha256: Digest
    authority_policy_sha256: Digest
    signed_authorization_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    ledger_snapshot_before: LedgerSnapshot
    ledger_snapshot_after: LedgerSnapshot
    mos_eisley_version: Identifier
    sdk_package: Literal["openai"] = "openai"
    sdk_version: Identifier
    provider: Literal["openai"] = "openai"
    command: Literal["openai-conformance"] = "openai-conformance"
    explicit_local_data_transfer_consent: Literal[True] = True
    precredential_rejection_proven: Literal[True] = True
    ledger_entry_absent_before: Literal[True] = True
    ledger_entry_absent_after: Literal[True] = True
    credential_accessed: Literal[False] = False
    audit_created: Literal[False] = False
    assignment_authorization_written: Literal[False] = False
    conformance_artifact_written: Literal[False] = False
    container_started: Literal[False] = False
    container_lifecycle_created: Literal[False] = False
    provider_request_sent: Literal[False] = False
    spend_reserved: Literal[False] = False
    retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    batch_conversion_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("observed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def unchanged_ledger(self) -> Self:
        if self.ledger_snapshot_before != self.ledger_snapshot_after:
            raise ValueError("precredential rejection changed the spending ledger")
        if self.ledger_snapshot_before.policy.ledger_id != self.ledger_id:
            raise ValueError("precredential rejection ledger identity mismatch")
        return self

    @property
    def receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


def make_precredential_rejection(
    *,
    batch: ExecutionBatch,
    spend_policy: SpendPolicy,
    conformance_policy: EvaluationConformancePolicy,
    authority_policy: EvaluationConformanceAuthorityPolicy,
    signed_authorization: SignedEvaluationConformanceAuthorization,
    ledger_before: LedgerSnapshot,
    ledger_after: LedgerSnapshot,
    ledger_entry_before: LedgerEntryStatus | None,
    ledger_entry_after: LedgerEntryStatus | None,
    audit_exists: bool,
    assignment_authorization_exists: bool,
    conformance_artifact_exists: bool,
    container_lifecycle_created: bool,
    observed_at: datetime,
    mos_eisley_version: str,
    sdk_version: str,
) -> EvaluationConformancePrecredentialRejection:
    """Issue F1 evidence only when every pre-credential invariant is observed."""

    if (
        ledger_before != ledger_after
        or ledger_entry_before is not None
        or ledger_entry_after is not None
        or audit_exists
        or assignment_authorization_exists
        or conformance_artifact_exists
        or container_lifecycle_created
    ):
        raise ValueError("cannot attest a side-effect-free precredential rejection")
    return EvaluationConformancePrecredentialRejection(
        observed_at=observed_at,
        plan_sha256=conformance_policy.plan_sha256,
        batch_sha256=batch.batch_sha256,
        sample_id=conformance_policy.sample_id,
        candidate_id=conformance_policy.candidate_id,
        evaluation_request_sha256=conformance_policy.evaluation_request_sha256,
        provider_request_sha256=conformance_policy.provider_request_sha256,
        spend_policy_sha256=spend_policy.policy_sha256,
        conformance_policy_sha256=conformance_policy.policy_sha256,
        authority_policy_sha256=authority_policy.policy_sha256,
        signed_authorization_sha256=signed_authorization.signed_authorization_sha256,
        ledger_id=conformance_policy.ledger_id,
        ledger_entry_id=conformance_policy.ledger_entry_id,
        ledger_snapshot_before=ledger_before,
        ledger_snapshot_after=ledger_after,
        mos_eisley_version=mos_eisley_version,
        sdk_version=sdk_version,
    )
