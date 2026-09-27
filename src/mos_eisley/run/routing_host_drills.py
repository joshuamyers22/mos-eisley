"""Metadata-only G6-05 inert target-host drill index; grants no authority."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest

REQUIRED_FAULTS: dict[str, tuple[str, ...]] = {
    "O01": (
        "enrolled_genesis",
        "unknown_genesis",
        "duplicate_epoch",
        "substituted_root",
        "older_anchor",
    ),
    "O02": ("duplicate_attempt", "changed_request", "last_headroom", "cloned_writer"),
    "O03": (
        "before_journal",
        "after_journal",
        "after_checkpoint",
        "after_receipt",
        "after_intent",
        "at_transport",
    ),
    "O04": ("before_claim", "after_claim", "before_final_read", "after_final_read"),
    "O05": (
        "witness_outage",
        "checkpoint_outage",
        "monitor_outage",
        "audit_outage",
        "clock_outage",
        "network_partition",
    ),
    "O06": (
        "stale_preflight",
        "stale_receipt",
        "expired_route",
        "revoked_policy",
        "removed_capability",
        "route_drift",
        "unavailable_fallback",
    ),
    "O07": (
        "signer_rotation",
        "witness_rotation",
        "witness_rollback",
        "local_rollback",
        "checkpoint_loss",
        "new_epoch",
    ),
    "O08": (
        "timeout",
        "cancellation",
        "invalid_usage",
        "invalid_price",
        "settlement_fault",
        "outcome_fault",
    ),
    "O09": ("cross_owner", "worker_key_access", "direct_transport", "missing_audit"),
    "O10": (
        "operator_stop",
        "alert_handoff",
        "backup_restore",
        "compromise",
        "rollback",
        "reentry",
    ),
}
_STATUS_OVERRIDES: dict[tuple[str, str], str] = {
    ("O01", "enrolled_genesis"): "read_only",
    ("O02", "duplicate_attempt"): "one_entry",
    ("O02", "last_headroom"): "one_entry",
    ("O03", "before_journal"): "read_only",
    ("O03", "after_journal"): "read_only",
    ("O03", "after_checkpoint"): "read_only",
    ("O03", "after_receipt"): "read_only",
    ("O03", "after_intent"): "read_only",
    ("O03", "at_transport"): "one_entry",
    ("O04", "after_claim"): "abandon",
    ("O04", "before_final_read"): "abandon",
    ("O04", "after_final_read"): "one_entry",
    **{("O08", fault): "one_entry" for fault in REQUIRED_FAULTS["O08"]},
    ("O10", "operator_stop"): "stop_acknowledged",
    ("O10", "alert_handoff"): "read_only",
    ("O10", "backup_restore"): "read_only",
    ("O10", "compromise"): "read_only",
    ("O10", "rollback"): "read_only",
}
REQUIRED_STATUSES: dict[tuple[str, str], str] = {
    (case, fault): _STATUS_OVERRIDES.get((case, fault), "deny")
    for case, faults in REQUIRED_FAULTS.items()
    for fault in faults
}

FaultStatus = Literal["deny", "abandon", "one_entry", "read_only", "stop_acknowledged"]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("drill time must use explicit UTC")
    return value


class HostDrillOracle(Contract):
    case_id: Literal[
        "O01", "O02", "O03", "O04", "O05", "O06", "O07", "O08", "O09", "O10"
    ]
    fault_id: Identifier
    expected_status: FaultStatus
    expected_state_sha256: Digest
    max_claims: Annotated[int, Field(ge=0, le=1)]
    max_intents: Annotated[int, Field(ge=0, le=1)]
    max_transport_entries: Annotated[int, Field(ge=0, le=1)]
    min_retained_exposure_microusd: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def coherent_bounds(self) -> Self:
        if (
            self.max_transport_entries > self.max_intents
            or self.max_intents > self.max_claims
        ):
            raise ValueError("drill oracle count ordering is invalid")
        if self.expected_status == "one_entry" and self.max_transport_entries != 1:
            raise ValueError("one-entry oracle must permit one entry")
        if (
            self.expected_status
            in ("deny", "abandon", "read_only", "stop_acknowledged")
            and self.max_transport_entries != 0
        ):
            raise ValueError("non-send oracle cannot permit transport")
        return self


class HostDrillProtocol(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["g6_05_inert_host_drills"] = "g6_05_inert_host_drills"
    qualification_packet_sha256: Digest
    broker_build_sha256: Digest
    target_host_id: Identifier
    witness_deployment_id: Identifier
    test_protocol_sha256: Digest
    operator_id: Identifier
    independent_checker_id: Identifier
    frozen_at: datetime
    valid_until: datetime
    max_workers: Annotated[int, Field(gt=0, le=1024)]
    max_crash_cases: Annotated[int, Field(gt=0, le=10_000)]
    max_synthetic_admissions: Annotated[int, Field(gt=0, le=1_000_000)]
    max_stop_latency_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    max_alert_latency_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    paid_provider_calls: Literal[0] = 0
    oracles: Annotated[tuple[HostDrillOracle, ...], Field(min_length=1, max_length=100)]

    @field_validator("frozen_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def frozen_matrix(self) -> Self:
        expected = tuple(
            (case, fault)
            for case, faults in REQUIRED_FAULTS.items()
            for fault in faults
        )
        actual = tuple((item.case_id, item.fault_id) for item in self.oracles)
        if (
            actual != expected
            or self.valid_until <= self.frozen_at
            or self.operator_id == self.independent_checker_id
            or any(
                item.expected_status != REQUIRED_STATUSES[(item.case_id, item.fault_id)]
                for item in self.oracles
            )
        ):
            raise ValueError("drill protocol matrix, window or roles are invalid")
        return self

    @property
    def protocol_sha256(self) -> str:
        return digest(canonical_bytes(self))


class HostDrillObservation(Contract):
    case_id: Literal[
        "O01", "O02", "O03", "O04", "O05", "O06", "O07", "O08", "O09", "O10"
    ]
    fault_id: Identifier
    status: Literal["pass", "fail", "unavailable"]
    observed_status: FaultStatus
    expected_state_sha256: Digest
    source_sha256: Digest | None = None
    producer_id: Identifier
    checker_id: Identifier
    observed_at: datetime
    checkpoint_generation_before: Annotated[int, Field(ge=0)]
    checkpoint_generation_after: Annotated[int, Field(ge=0)]
    claim_count: Annotated[int, Field(ge=0)]
    intent_count: Annotated[int, Field(ge=0)]
    transport_entries_for_attempt: Annotated[int, Field(ge=0)]
    retained_exposure_microusd: Annotated[int, Field(ge=0)]
    audit_event_count: Annotated[int, Field(ge=0)]
    alert_event_count: Annotated[int, Field(ge=0)]
    paid_provider_calls: Literal[0] = 0

    @field_validator("observed_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def bounded_source(self) -> Self:
        if self.producer_id == self.checker_id or (
            self.status == "pass" and self.source_sha256 is None
        ):
            raise ValueError(
                "drill observation needs distinct checker and a source digest"
            )
        return self


class HostDrillEvidenceIndex(Contract):
    schema_version: Literal[1] = 1
    protocol_sha256: Digest
    qualification_packet_sha256: Digest
    broker_build_sha256: Digest
    target_host_id: Identifier
    witness_deployment_id: Identifier
    assembled_at: datetime
    workers_used: Annotated[int, Field(gt=0)]
    crash_cases_run: Annotated[int, Field(gt=0)]
    synthetic_admissions: Annotated[int, Field(gt=0)]
    measured_max_stop_latency_ms: Annotated[int, Field(ge=0)]
    measured_max_alert_latency_ms: Annotated[int, Field(ge=0)]
    paid_provider_calls: Literal[0] = 0
    observations: Annotated[tuple[HostDrillObservation, ...], Field(max_length=100)]

    @field_validator("assembled_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def unique_observations(self) -> Self:
        keys = tuple((item.case_id, item.fault_id) for item in self.observations)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("drill observations must be unique and sorted")
        return self

    @property
    def evidence_sha256(self) -> str:
        return digest(canonical_bytes(self))


class HostDrillIndexAssessment(Contract):
    schema_version: Literal[1] = 1
    protocol_sha256: Digest
    evidence_sha256: Digest
    reviewable: bool
    reasons: tuple[Identifier, ...]
    target_host_verified: Literal[False] = False
    qualification_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def validate_inert_host_drill_index(
    *, protocol: HostDrillProtocol, evidence: HostDrillEvidenceIndex, now: datetime
) -> HostDrillIndexAssessment:
    """Check frozen bounded metadata, never attest the host or artifact contents."""
    _utc(now)
    reasons: set[str] = set()
    if (
        not protocol.frozen_at <= now < protocol.valid_until
        or not protocol.frozen_at <= evidence.assembled_at <= now
    ):
        reasons.add("window_invalid")
    for name in (
        "protocol_sha256",
        "qualification_packet_sha256",
        "broker_build_sha256",
        "target_host_id",
        "witness_deployment_id",
    ):
        expected = (
            protocol.protocol_sha256
            if name == "protocol_sha256"
            else getattr(protocol, name)
        )
        if getattr(evidence, name) != expected:
            reasons.add("binding_mismatch")
    if (
        evidence.workers_used > protocol.max_workers
        or evidence.crash_cases_run > protocol.max_crash_cases
        or evidence.synthetic_admissions > protocol.max_synthetic_admissions
        or evidence.measured_max_stop_latency_ms > protocol.max_stop_latency_ms
        or evidence.measured_max_alert_latency_ms > protocol.max_alert_latency_ms
    ):
        reasons.add("limit_exceeded")
    observed = {(item.case_id, item.fault_id): item for item in evidence.observations}
    expected_keys = {(item.case_id, item.fault_id) for item in protocol.oracles}
    if set(observed) != expected_keys:
        reasons.add("coverage_invalid")
    for oracle in protocol.oracles:
        item = observed.get((oracle.case_id, oracle.fault_id))
        if item is None:
            continue
        if (
            item.status != "pass"
            or item.observed_status != oracle.expected_status
            or item.expected_state_sha256 != oracle.expected_state_sha256
        ):
            reasons.add("oracle_not_met")
        if not protocol.frozen_at <= item.observed_at <= evidence.assembled_at:
            reasons.add("observation_time_invalid")
        if (
            item.producer_id != protocol.operator_id
            or item.checker_id != protocol.independent_checker_id
        ):
            reasons.add("role_mismatch")
        if (
            item.checkpoint_generation_after < item.checkpoint_generation_before
            or item.claim_count > oracle.max_claims
            or item.intent_count > oracle.max_intents
            or item.transport_entries_for_attempt > oracle.max_transport_entries
            or item.transport_entries_for_attempt > item.intent_count
            or item.intent_count > item.claim_count
            or item.retained_exposure_microusd < oracle.min_retained_exposure_microusd
        ):
            reasons.add("state_invariant_failed")
        if (
            oracle.expected_status == "one_entry"
            and item.transport_entries_for_attempt != 1
        ):
            reasons.add("state_invariant_failed")
        if oracle.expected_status == "abandon" and item.claim_count != 1:
            reasons.add("state_invariant_failed")
        if (
            oracle.expected_status == "stop_acknowledged"
            and item.checkpoint_generation_after <= item.checkpoint_generation_before
        ):
            reasons.add("state_invariant_failed")
        if item.status == "pass" and item.source_sha256 is None:
            reasons.add("source_missing")
    return HostDrillIndexAssessment(
        protocol_sha256=protocol.protocol_sha256,
        evidence_sha256=evidence.evidence_sha256,
        reviewable=not reasons,
        reasons=tuple(sorted(reasons)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a G6-05 inert target-host drill evidence index"
    )
    parser.add_argument("protocol", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--now", required=True, help="Explicit ISO-8601 UTC time")
    args = parser.parse_args()
    for path in (args.protocol, args.evidence):
        if path.stat().st_size > 2_000_000:
            parser.error("drill JSON exceeds the 2 MB metadata limit")
    protocol = HostDrillProtocol.model_validate_json(args.protocol.read_bytes())
    evidence = HostDrillEvidenceIndex.model_validate_json(args.evidence.read_bytes())
    result = validate_inert_host_drill_index(
        protocol=protocol, evidence=evidence, now=datetime.fromisoformat(args.now)
    )
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0 if result.reviewable else 1


if __name__ == "__main__":
    raise SystemExit(main())
