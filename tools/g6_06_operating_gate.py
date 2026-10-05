"""Offline G606-04 operating-gate packet screen; grants no live authority."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.routing_host_drills import (
    HostDrillEvidenceIndex,
    HostDrillProtocol,
    validate_inert_host_drill_index,
)
from mos_eisley.run.store import private_write
from mos_eisley.run.witnessed_admission import CohortManifest

COHORT_FAULTS: dict[str, tuple[str, ...]] = {
    "C01": ("missing_go", "changed_manifest", "changed_build", "unsigned_release"),
    "C02": ("outside_owner", "duplicate_task", "fresh_session"),
    "C03": ("last_slot", "concurrent_claim", "killed_assignment", "ambiguous_claim"),
    "C04": ("audit_outage", "alert_loss", "stale_clock", "stop_inflight"),
    "C05": (
        "route_before_claim",
        "route_after_claim",
        "route_after_final_read",
        "stale_fallback",
    ),
    "C06": (
        "stop_before_claim",
        "stop_after_claim",
        "stop_after_final_read",
        "recovery_reentry",
    ),
    "C07": ("early_close", "missing_followup", "cancelled_task", "replacement_draw"),
    "C08": (
        "witness_rollback",
        "local_rollback",
        "audit_rollback",
        "combined_rollback",
    ),
    "C09": (
        "changed_rubric",
        "changed_policy",
        "early_assessment",
        "unregistered_claim",
    ),
}
ONE_ENTRY_FAULTS = frozenset(
    {
        ("C03", "last_slot"),
        ("C03", "concurrent_claim"),
        ("C04", "stop_inflight"),
        ("C05", "route_after_final_read"),
        ("C06", "stop_after_final_read"),
    }
)
FULL_EXPOSURE_FAULTS = frozenset(
    {
        ("C03", "ambiguous_claim"),
        ("C04", "stop_inflight"),
        ("C05", "route_after_claim"),
        ("C05", "route_after_final_read"),
        ("C06", "stop_after_claim"),
        ("C06", "stop_after_final_read"),
    }
)
CLAIM_ALLOWED_FAULTS = ONE_ENTRY_FAULTS | FULL_EXPOSURE_FAULTS
NO_ASSIGNMENT_FAULTS = frozenset(
    {
        *(
            (case, fault)
            for case in ("C01", "C02", "C08", "C09")
            for fault in COHORT_FAULTS[case]
        ),
        ("C06", "recovery_reentry"),
        ("C07", "replacement_draw"),
    }
)
REQUIRED_ASSIGNMENT_FAULTS = frozenset({("C03", "killed_assignment")})
STOP_FAULTS = frozenset(
    {
        ("C04", "stop_inflight"),
        *(("C06", fault) for fault in COHORT_FAULTS["C06"][:3]),
    }
)
REQUIRED_CASES = (*tuple(f"O{n:02d}" for n in range(1, 11)), *tuple(COHORT_FAULTS))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("operating-gate time must use explicit UTC")
    return value


class OperatingLimits(Contract):
    max_assignments: Annotated[int, Field(gt=0, le=256)]
    max_concurrent: Annotated[int, Field(gt=0, le=256)]
    task_ceiling_microusd: Annotated[int, Field(gt=0)]
    session_ceiling_microusd: Annotated[int, Field(gt=0)]
    cohort_ceiling_microusd: Annotated[int, Field(gt=0)]
    request_maximum_microusd: Annotated[int, Field(gt=0)]
    warning_exposure_microusd: Annotated[int, Field(gt=0)]
    hard_stop_exposure_microusd: Annotated[int, Field(gt=0)]
    observation_cadence_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    queue_capacity: Annotated[int, Field(gt=0)]
    retention_seconds: Annotated[int, Field(gt=0)]
    max_stop_latency_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    max_alert_latency_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    post_final_read_inflight_max: Literal[1] = 1
    paid_provider_calls: Literal[0] = 0

    @model_validator(mode="after")
    def ordered_limits(self) -> Self:
        if (
            self.max_concurrent > self.max_assignments
            or self.request_maximum_microusd
            > min(
                self.task_ceiling_microusd,
                self.session_ceiling_microusd,
                self.cohort_ceiling_microusd,
            )
            or not self.warning_exposure_microusd
            < self.hard_stop_exposure_microusd
            <= self.cohort_ceiling_microusd
        ):
            raise ValueError("operating-gate limits are inconsistent")
        return self


class CohortFaultOracle(Contract):
    case_id: Identifier
    fault_id: Identifier
    expected_status: Literal["deny", "one_entry"]
    expected_state_sha256: Digest
    max_assignments_created: Annotated[int, Field(ge=0, le=1)]
    max_claims_created: Annotated[int, Field(ge=0, le=1)]
    max_intents_created: Annotated[int, Field(ge=0, le=1)]
    max_transport_entries: Annotated[int, Field(ge=0, le=1)]
    min_retained_exposure_microusd: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def coherent_bounds(self) -> Self:
        if (
            self.max_transport_entries > self.max_intents_created
            or self.max_intents_created > self.max_claims_created
            or self.max_claims_created > self.max_assignments_created
            or self.max_transport_entries
            != (1 if self.expected_status == "one_entry" else 0)
        ):
            raise ValueError("cohort fault bounds are inconsistent")
        return self


class CohortDrillProtocol(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    qualification_packet_sha256: Digest
    g6_05_go_sha256: Digest
    broker_build_sha256: Digest
    target_host_id: Identifier
    witness_epoch_id: Digest
    host_protocol_sha256: Digest
    host_evidence_sha256: Digest
    test_protocol_sha256: Digest
    operator_id: Identifier
    checker_id: Identifier
    frozen_at: datetime
    valid_until: datetime
    max_workers: Annotated[int, Field(gt=0)]
    max_crash_cases: Annotated[int, Field(gt=0)]
    max_synthetic_admissions: Annotated[int, Field(gt=0)]
    limits: OperatingLimits
    oracles: Annotated[
        tuple[CohortFaultOracle, ...], Field(min_length=1, max_length=100)
    ]

    @field_validator("frozen_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def fixed_faults(self) -> Self:
        expected = tuple(
            (case, fault) for case, faults in COHORT_FAULTS.items() for fault in faults
        )
        actual = tuple((item.case_id, item.fault_id) for item in self.oracles)
        if (
            actual != expected
            or self.valid_until <= self.frozen_at
            or self.operator_id == self.checker_id
        ):
            raise ValueError("cohort drill matrix, window or roles are invalid")
        for item in self.oracles:
            key = (item.case_id, item.fault_id)
            if (
                item.expected_status
                != ("one_entry" if key in ONE_ENTRY_FAULTS else "deny")
                or (
                    key in FULL_EXPOSURE_FAULTS
                    and item.min_retained_exposure_microusd
                    < self.limits.request_maximum_microusd
                )
                or item.max_claims_created != (1 if key in CLAIM_ALLOWED_FAULTS else 0)
                or item.max_assignments_created
                != (0 if key in NO_ASSIGNMENT_FAULTS else 1)
            ):
                raise ValueError("cohort fault oracle was weakened")
        return self

    @property
    def protocol_sha256(self) -> str:
        return digest(canonical_bytes(self))


class CohortFaultObservation(Contract):
    case_id: Identifier
    fault_id: Identifier
    status: Literal["pass", "fail", "unavailable"]
    observed_status: Literal["deny", "one_entry"]
    expected_state_sha256: Digest
    source_sha256: Digest | None = None
    producer_id: Identifier
    checker_id: Identifier
    observed_at: datetime
    assignments_created: Annotated[int, Field(ge=0)]
    claims_created: Annotated[int, Field(ge=0)]
    intents_created: Annotated[int, Field(ge=0)]
    transport_entries: Annotated[int, Field(ge=0)]
    retained_exposure_microusd: Annotated[int, Field(ge=0)]
    checkpoint_generation_before: Annotated[int, Field(ge=0)]
    checkpoint_generation_after: Annotated[int, Field(ge=0)]
    paid_provider_calls: Literal[0] = 0

    @field_validator("observed_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class CohortDrillEvidenceIndex(Contract):
    schema_version: Literal[1] = 1
    protocol_sha256: Digest
    manifest_sha256: Digest
    broker_build_sha256: Digest
    target_host_id: Identifier
    witness_epoch_id: Digest
    assembled_at: datetime
    workers_used: Annotated[int, Field(gt=0)]
    crash_cases_run: Annotated[int, Field(gt=0)]
    synthetic_admissions: Annotated[int, Field(gt=0)]
    measured_max_stop_latency_ms: Annotated[int, Field(ge=0)]
    measured_max_alert_latency_ms: Annotated[int, Field(ge=0)]
    paid_provider_calls: Literal[0] = 0
    observations: Annotated[tuple[CohortFaultObservation, ...], Field(max_length=100)]

    @field_validator("assembled_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def unique_observations(self) -> Self:
        keys = tuple((item.case_id, item.fault_id) for item in self.observations)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("cohort drill observations must be unique and sorted")
        return self

    @property
    def evidence_sha256(self) -> str:
        return digest(canonical_bytes(self))


class FrozenOperatingGateAnchor(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    qualification_packet_sha256: Digest
    g6_05_go_sha256: Digest
    g5_claim_sha256: Digest
    g6_01_04_review_sha256: Digest
    broker_build_sha256: Digest
    target_host_id: Identifier
    witness_epoch_id: Digest
    witness_deployment_id: Identifier
    expected_reviewer_id: Identifier
    host_protocol_sha256: Digest
    host_evidence_sha256: Digest
    cohort_protocol_sha256: Digest
    frozen_at: datetime
    valid_until: datetime

    @field_validator("frozen_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class CaseSourceReview(Contract):
    case_id: Identifier
    decision: Literal["accept", "reject", "unavailable"]
    case_observations_sha256: Digest
    reviewer_id: Identifier
    reviewed_at: datetime
    valid_until: datetime

    @field_validator("reviewed_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class OperatingGateReviewPacket(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    broker_build_sha256: Digest
    host_evidence_sha256: Digest
    cohort_evidence_sha256: Digest
    g5_claim_sha256: Digest
    g6_01_04_review_sha256: Digest
    g6_05_go_sha256: Digest
    reviews: Annotated[tuple[CaseSourceReview, ...], Field(max_length=19)]

    @model_validator(mode="after")
    def canonical_cases(self) -> Self:
        if tuple(item.case_id for item in self.reviews) != REQUIRED_CASES:
            raise ValueError("operating-gate case reviews are incomplete")
        return self


class OperatingGateAssessment(Contract):
    schema_version: Literal[1] = 1
    status: Literal["reviewable", "blocked"]
    reasons: tuple[str, ...]
    anchor_sha256: Digest
    manifest_sha256: Digest
    host_protocol_sha256: Digest
    host_evidence_sha256: Digest
    cohort_protocol_sha256: Digest
    cohort_evidence_sha256: Digest
    review_packet_sha256: Digest
    host_case_count: int
    cohort_case_count: int
    target_host_verified: Literal[False] = False
    independent_reviews_authenticated: Literal[False] = False
    g6_05_go_verified: Literal[False] = False
    cohort_release_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False
    assessment_authorized: Literal[False] = False


def case_observations_digest(items: tuple[Contract, ...]) -> str:
    return digest(
        b"g60604-case-observations-v1\0"
        + b"".join(digest(canonical_bytes(item)).encode("ascii") for item in items)
    )


def validate_operating_gate(
    *,
    anchor: FrozenOperatingGateAnchor,
    manifest: CohortManifest,
    host_protocol: HostDrillProtocol,
    host_evidence: HostDrillEvidenceIndex,
    cohort_protocol: CohortDrillProtocol,
    cohort_evidence: CohortDrillEvidenceIndex,
    reviews: OperatingGateReviewPacket,
    now: datetime,
) -> OperatingGateAssessment:
    """Check exact metadata joins and fault oracles; authenticate no source or host."""
    _utc(now)
    reasons: set[str] = set()
    if not manifest.valid_from <= now < min(manifest.valid_until, anchor.valid_until):
        reasons.add("window_invalid")
    host_result = validate_inert_host_drill_index(
        protocol=host_protocol, evidence=host_evidence, now=now
    )
    if not host_result.reviewable:
        reasons.add("host_drills_blocked")
    if (
        anchor.manifest_sha256 != manifest.manifest_sha256
        or anchor.broker_build_sha256 != manifest.broker_build_sha256
        or anchor.target_host_id != manifest.target_host_id
        or anchor.witness_epoch_id != manifest.witness_epoch_id
    ):
        reasons.add("manifest_mismatch")
    if (
        anchor.host_protocol_sha256 != host_protocol.protocol_sha256
        or anchor.host_evidence_sha256 != host_evidence.evidence_sha256
        or anchor.qualification_packet_sha256
        != host_protocol.qualification_packet_sha256
        or anchor.broker_build_sha256 != host_protocol.broker_build_sha256
        or anchor.target_host_id != host_protocol.target_host_id
        or anchor.witness_deployment_id != host_protocol.witness_deployment_id
    ):
        reasons.add("host_binding_mismatch")
    if (
        anchor.cohort_protocol_sha256 != cohort_protocol.protocol_sha256
        or cohort_protocol.manifest_sha256 != manifest.manifest_sha256
        or cohort_protocol.qualification_packet_sha256
        != anchor.qualification_packet_sha256
        or cohort_protocol.g6_05_go_sha256 != anchor.g6_05_go_sha256
        or cohort_protocol.broker_build_sha256 != anchor.broker_build_sha256
        or cohort_protocol.target_host_id != anchor.target_host_id
        or cohort_protocol.witness_epoch_id != anchor.witness_epoch_id
        or cohort_protocol.host_protocol_sha256 != host_protocol.protocol_sha256
        or cohort_protocol.host_evidence_sha256 != host_evidence.evidence_sha256
    ):
        reasons.add("cohort_binding_mismatch")
    limits = cohort_protocol.limits
    if (
        limits.max_assignments > manifest.max_assignments
        or limits.max_concurrent > manifest.max_concurrent
        or limits.request_maximum_microusd != host_protocol.request_maximum_microusd
        or limits.max_stop_latency_ms > host_protocol.max_stop_latency_ms
        or limits.max_alert_latency_ms > host_protocol.max_alert_latency_ms
        or cohort_protocol.max_workers > host_protocol.max_workers
        or cohort_protocol.max_crash_cases > host_protocol.max_crash_cases
        or cohort_protocol.max_synthetic_admissions
        > host_protocol.max_synthetic_admissions
    ):
        reasons.add("limit_exceeded")
    if (
        not host_protocol.frozen_at
        <= cohort_protocol.frozen_at
        < cohort_protocol.valid_until
        <= min(host_protocol.valid_until, anchor.valid_until)
        or host_evidence.assembled_at > cohort_protocol.frozen_at
        or not cohort_protocol.frozen_at
        <= anchor.frozen_at
        < cohort_evidence.assembled_at
        or not cohort_protocol.frozen_at <= cohort_evidence.assembled_at <= now
        or now >= cohort_protocol.valid_until
    ):
        reasons.add("cohort_window_invalid")
    if (
        cohort_evidence.protocol_sha256 != cohort_protocol.protocol_sha256
        or cohort_evidence.manifest_sha256 != anchor.manifest_sha256
        or cohort_evidence.broker_build_sha256 != anchor.broker_build_sha256
        or cohort_evidence.target_host_id != anchor.target_host_id
        or cohort_evidence.witness_epoch_id != anchor.witness_epoch_id
    ):
        reasons.add("cohort_evidence_binding_mismatch")
    if (
        cohort_evidence.workers_used > cohort_protocol.max_workers
        or cohort_evidence.crash_cases_run > cohort_protocol.max_crash_cases
        or cohort_evidence.synthetic_admissions
        > cohort_protocol.max_synthetic_admissions
        or cohort_evidence.measured_max_stop_latency_ms > limits.max_stop_latency_ms
        or cohort_evidence.measured_max_alert_latency_ms > limits.max_alert_latency_ms
    ):
        reasons.add("cohort_limit_exceeded")
    observed = {
        (item.case_id, item.fault_id): item for item in cohort_evidence.observations
    }
    if any(
        item.observed_at <= anchor.frozen_at for item in cohort_evidence.observations
    ):
        reasons.add("cohort_window_invalid")
    expected = {(item.case_id, item.fault_id) for item in cohort_protocol.oracles}
    if set(observed) != expected:
        reasons.add("cohort_coverage_invalid")
    for oracle in cohort_protocol.oracles:
        key = (oracle.case_id, oracle.fault_id)
        item = observed.get(key)
        if item is None:
            continue
        if (
            item.status != "pass"
            or item.observed_status != oracle.expected_status
            or item.expected_state_sha256 != oracle.expected_state_sha256
            or item.source_sha256 is None
        ):
            reasons.add("cohort_oracle_not_met")
        if (
            not cohort_protocol.frozen_at
            <= item.observed_at
            <= cohort_evidence.assembled_at
            or item.producer_id != cohort_protocol.operator_id
            or item.checker_id != cohort_protocol.checker_id
            or item.producer_id == item.checker_id
        ):
            reasons.add("cohort_observation_invalid")
        if (
            item.assignments_created > oracle.max_assignments_created
            or item.claims_created > oracle.max_claims_created
            or item.intents_created > oracle.max_intents_created
            or item.transport_entries > oracle.max_transport_entries
            or item.transport_entries > item.intents_created
            or item.intents_created > item.claims_created
            or item.claims_created > item.assignments_created
            or item.retained_exposure_microusd < oracle.min_retained_exposure_microusd
            or item.checkpoint_generation_after < item.checkpoint_generation_before
            or (oracle.expected_status == "one_entry" and item.transport_entries != 1)
            or (key in FULL_EXPOSURE_FAULTS and item.claims_created != 1)
            or (key in REQUIRED_ASSIGNMENT_FAULTS and item.assignments_created != 1)
            or (
                key in STOP_FAULTS
                and item.checkpoint_generation_after
                <= item.checkpoint_generation_before
            )
        ):
            reasons.add("cohort_state_invariant_failed")
    if (
        reviews.manifest_sha256 != anchor.manifest_sha256
        or reviews.broker_build_sha256 != anchor.broker_build_sha256
        or reviews.host_evidence_sha256 != host_evidence.evidence_sha256
        or reviews.cohort_evidence_sha256 != cohort_evidence.evidence_sha256
        or reviews.g5_claim_sha256 != anchor.g5_claim_sha256
        or reviews.g6_01_04_review_sha256 != anchor.g6_01_04_review_sha256
        or reviews.g6_05_go_sha256 != anchor.g6_05_go_sha256
    ):
        reasons.add("review_packet_binding_mismatch")
    for review in reviews.reviews:
        items: tuple[Contract, ...] = (
            tuple(
                item
                for item in host_evidence.observations
                if item.case_id == review.case_id
            )
            if review.case_id.startswith("O")
            else tuple(
                item
                for item in cohort_evidence.observations
                if item.case_id == review.case_id
            )
        )
        if (
            review.decision != "accept"
            or not items
            or review.case_observations_sha256 != case_observations_digest(items)
            or review.reviewer_id != anchor.expected_reviewer_id
            or review.reviewer_id
            in (host_protocol.operator_id, cohort_protocol.operator_id)
            or not max(host_evidence.assembled_at, cohort_evidence.assembled_at)
            <= review.reviewed_at
            <= now
            < min(review.valid_until, anchor.valid_until)
        ):
            reasons.add("case_review_invalid")
    return OperatingGateAssessment(
        status="blocked" if reasons else "reviewable",
        reasons=tuple(sorted(reasons)),
        anchor_sha256=digest(canonical_bytes(anchor)),
        manifest_sha256=manifest.manifest_sha256,
        host_protocol_sha256=host_protocol.protocol_sha256,
        host_evidence_sha256=host_evidence.evidence_sha256,
        cohort_protocol_sha256=cohort_protocol.protocol_sha256,
        cohort_evidence_sha256=cohort_evidence.evidence_sha256,
        review_packet_sha256=digest(canonical_bytes(reviews)),
        host_case_count=len({item.case_id for item in host_evidence.observations}),
        cohort_case_count=len({item.case_id for item in cohort_evidence.observations}),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "anchor",
        "manifest",
        "host_protocol",
        "host_evidence",
        "cohort_protocol",
        "cohort_evidence",
        "reviews",
        "output",
    ):
        parser.add_argument(name, type=Path)
    parser.add_argument("--now", help="explicit UTC assessment time")
    args = parser.parse_args(argv)
    try:
        anchor = FrozenOperatingGateAnchor.model_validate_json(args.anchor.read_bytes())
        manifest = CohortManifest.model_validate_json(args.manifest.read_bytes())
        host_protocol = HostDrillProtocol.model_validate_json(
            args.host_protocol.read_bytes()
        )
        host_evidence = HostDrillEvidenceIndex.model_validate_json(
            args.host_evidence.read_bytes()
        )
        cohort_protocol = CohortDrillProtocol.model_validate_json(
            args.cohort_protocol.read_bytes()
        )
        cohort_evidence = CohortDrillEvidenceIndex.model_validate_json(
            args.cohort_evidence.read_bytes()
        )
        reviews = OperatingGateReviewPacket.model_validate_json(
            args.reviews.read_bytes()
        )
        now = _utc(datetime.fromisoformat(args.now)) if args.now else datetime.now(UTC)
    except (OSError, ValueError, ValidationError):
        print("blocked: invalid input")
        return 1
    result = validate_operating_gate(
        anchor=anchor,
        manifest=manifest,
        host_protocol=host_protocol,
        host_evidence=host_evidence,
        cohort_protocol=cohort_protocol,
        cohort_evidence=cohort_evidence,
        reviews=reviews,
        now=now,
    )
    private_write(args.output, (result.model_dump_json(indent=2) + "\n").encode())
    print(f"{result.status}: {len(result.reasons)} mismatch categories")
    return 0 if result.status == "reviewable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
