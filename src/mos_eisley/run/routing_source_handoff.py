"""Metadata-only G6-05 source-evidence handoff; never opens source artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.routing_host_drills import (
    HostDrillEvidenceIndex,
    HostDrillProtocol,
    drill_case_sha256,
    validate_joined_inert_host_drill_index,
)
from mos_eisley.run.routing_qualification import (
    OfflineQualificationEvidence,
    OfflineQualificationPacket,
)

AccessMode = Literal["audited_g5", "owner_isolated", "provider_primary"]
CheckMethod = Literal[
    "audited_source_review", "independent_source_read", "separate_host_observation"
]
CheckerRole = Literal["statistical", "security"]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("source handoff time must use explicit UTC")
    return value


class SourceRequirement(Contract):
    source_id: Identifier
    source_sha256: Digest
    access_mode: AccessMode
    check_method: CheckMethod
    checker_role: CheckerRole


class SourceEvidenceReference(SourceRequirement):
    custody_domain_id: Identifier
    custodian_id: Identifier
    locator_id: Identifier
    producer_id: Identifier
    checker_id: Identifier
    status: Literal["available", "unavailable", "disputed"]
    captured_at: datetime
    valid_until: datetime

    @field_validator("captured_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def separate_checker(self) -> Self:
        if self.valid_until <= self.captured_at or self.checker_id in (
            self.producer_id,
            self.custodian_id,
        ):
            raise ValueError("source handoff custody or checker is invalid")
        return self


class G605SourceEvidenceHandoff(Contract):
    schema_version: Literal[1] = 1
    packet_sha256: Digest
    qualification_evidence_sha256: Digest
    drill_protocol_sha256: Digest
    drill_index_sha256: Digest
    inspection_protocol_sha256: Digest
    reviewer_roster_sha256: Digest
    assembled_at: datetime
    references: Annotated[
        tuple[SourceEvidenceReference, ...], Field(min_length=1, max_length=4096)
    ]

    @field_validator("assembled_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def canonical_references(self) -> Self:
        ids = tuple(item.source_id for item in self.references)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("source handoff references must be unique and sorted")
        return self

    @property
    def handoff_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G605SourceHandoffAssessment(Contract):
    schema_version: Literal[1] = 1
    handoff_sha256: Digest
    required_source_count: Annotated[int, Field(ge=0)]
    handoff_ready: bool
    reasons: tuple[Identifier, ...]
    source_authenticated: Literal[False] = False
    target_host_verified: Literal[False] = False
    qualification_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def required_source_references(
    *,
    packet: OfflineQualificationPacket,
    evidence: OfflineQualificationEvidence,
    drill_protocol: HostDrillProtocol,
    drill_index: HostDrillEvidenceIndex,
    inspection_protocol_sha256: Digest,
    reviewer_roster_sha256: Digest,
) -> tuple[SourceRequirement, ...]:
    """Enumerate safe digest slots; no source file or protected store is opened."""
    expected: dict[str, SourceRequirement] = {}

    def add(
        source_id: str,
        source_sha256: str,
        access_mode: AccessMode,
        check_method: CheckMethod,
        checker_role: CheckerRole,
    ) -> None:
        if source_id in expected:
            raise ValueError("duplicate source handoff requirement")
        expected[source_id] = SourceRequirement(
            source_id=source_id,
            source_sha256=source_sha256,
            access_mode=access_mode,
            check_method=check_method,
            checker_role=checker_role,
        )

    add(
        "m.packet",
        packet.packet_sha256,
        "owner_isolated",
        "independent_source_read",
        "security",
    )
    add(
        "m.evidence",
        evidence.evidence_sha256,
        "owner_isolated",
        "independent_source_read",
        "security",
    )
    add(
        "m.drill-protocol",
        drill_protocol.protocol_sha256,
        "owner_isolated",
        "independent_source_read",
        "security",
    )
    add(
        "m.drill-index",
        drill_index.evidence_sha256,
        "owner_isolated",
        "independent_source_read",
        "security",
    )
    add(
        "m.inspection-protocol",
        inspection_protocol_sha256,
        "owner_isolated",
        "independent_source_read",
        "security",
    )
    add(
        "m.reviewer-roster",
        reviewer_roster_sha256,
        "owner_isolated",
        "independent_source_read",
        "security",
    )

    audited = {
        "g5-claim": packet.candidate.g5_claim_sha256,
        "g5-holdout": packet.candidate.g5_holdout_report_sha256,
        "g5-use-claim": packet.candidate.g5_use_claim_sha256,
        "sealed-study": packet.candidate.sealed_study_sha256,
        "candidate-policy": packet.candidate.candidate_policy_sha256,
    }
    for name, source_sha256 in audited.items():
        add(
            f"p.{name}",
            source_sha256,
            "audited_g5",
            "audited_source_review",
            "statistical",
        )

    packet_artifacts = {
        "plan": packet.candidate.plan_sha256,
        "feature-partition": packet.candidate.feature_partition_sha256,
        "promotion-authority": packet.authority.promotion_authority_policy_sha256,
        "promotion-receipt": packet.authority.promotion_receipt_sha256,
        "activation-authority": packet.authority.activation_authority_policy_sha256,
        "activation-policy": packet.authority.activation_policy_sha256,
        "activation-eligibility": packet.authority.activation_eligibility_sha256,
        "anchor-policy": packet.authority.control_anchor_policy_sha256,
        "control-entry": packet.authority.latest_control_entry_sha256,
        "preflight": packet.authority.preflight_sha256,
        "witness-enrollment": packet.witness.enrollment_sha256,
        "budget-policy": packet.witness.budget_policy_sha256,
        "persistence-design": packet.witness.persistence_design_sha256,
        "recovery-runbook": packet.witness.recovery_runbook_sha256,
        "broker-build": packet.runtime.broker_build_sha256,
        "network-policy": packet.runtime.witness_network_policy_sha256,
        "stop-runbook": packet.runtime.stop_runbook_sha256,
        "task-enrollment": packet.scope.task_enrollment_sha256,
        "test-protocol": packet.verification.test_protocol_sha256,
        "severity-rubric": packet.verification.severity_rubric_sha256,
        "retention-policy": packet.verification.retention_policy_sha256,
    }
    for name, source_sha256 in packet_artifacts.items():
        add(
            f"p.{name}",
            source_sha256,
            "owner_isolated",
            "independent_source_read",
            "security",
        )
    for prerequisite in packet.prerequisites:
        add(
            f"p.{prerequisite.milestone}.applicability",
            prerequisite.applicability_basis_sha256,
            "owner_isolated",
            "independent_source_read",
            "security",
        )

    for record in evidence.records:
        if record.source_sha256 is None:
            continue
        audited_g5 = record.evidence_id == "Q1"
        add(
            f"q.{record.evidence_id}",
            record.source_sha256,
            "audited_g5" if audited_g5 else "owner_isolated",
            "audited_source_review" if audited_g5 else "independent_source_read",
            "statistical" if audited_g5 else "security",
        )

    for observation in evidence.route_observations:
        prefix = f"r.{observation.identity.candidate_id}"
        route_sources = {
            "catalog": observation.catalog_evidence_sha256,
            "pricing": observation.pricing_evidence_sha256,
            "conform": observation.conformance_evidence_sha256,
            "drift": observation.drift_evidence_sha256,
            "method": observation.method_sha256,
            "prompt": observation.identity.prompt_asset_sha256,
            "registry": observation.identity.registry_sha256,
            "capability": observation.identity.capabilities_sha256,
        }
        for kind, source_sha256 in route_sources.items():
            access_mode: AccessMode = "owner_isolated"
            if kind in ("catalog", "pricing"):
                access_mode = "provider_primary"
            add(
                f"{prefix}.{kind}",
                source_sha256,
                access_mode,
                "independent_source_read",
                "security",
            )

    for observation in drill_index.observations:
        if observation.source_sha256 is None:
            continue
        add(
            f"f.{observation.case_id}.{observation.fault_id}",
            observation.source_sha256,
            "owner_isolated",
            "separate_host_observation",
            "security",
        )
    return tuple(expected[key] for key in sorted(expected))


def validate_g605_source_handoff(
    *,
    handoff: G605SourceEvidenceHandoff,
    packet: OfflineQualificationPacket,
    evidence: OfflineQualificationEvidence,
    drill_protocol: HostDrillProtocol,
    drill_index: HostDrillEvidenceIndex,
    expected_inspection_protocol_sha256: Digest,
    expected_reviewer_roster_sha256: Digest,
    now: datetime,
) -> G605SourceHandoffAssessment:
    """Check handoff pointers and assignments without authenticating sources."""
    _utc(now)
    reasons: set[str] = set()
    required = required_source_references(
        packet=packet,
        evidence=evidence,
        drill_protocol=drill_protocol,
        drill_index=drill_index,
        inspection_protocol_sha256=handoff.inspection_protocol_sha256,
        reviewer_roster_sha256=handoff.reviewer_roster_sha256,
    )
    joined = validate_joined_inert_host_drill_index(
        packet=packet, protocol=drill_protocol, evidence=drill_index, now=now
    )
    if not joined.reviewable:
        reasons.add("drill_index_invalid")
    if (
        evidence.packet_sha256 != packet.packet_sha256
        or evidence.drill_protocol_sha256 != drill_protocol.protocol_sha256
        or evidence.drill_index_sha256 != drill_index.evidence_sha256
        or handoff.packet_sha256 != packet.packet_sha256
        or handoff.qualification_evidence_sha256 != evidence.evidence_sha256
        or handoff.drill_protocol_sha256 != drill_protocol.protocol_sha256
        or handoff.drill_index_sha256 != drill_index.evidence_sha256
        or handoff.inspection_protocol_sha256 != expected_inspection_protocol_sha256
        or handoff.reviewer_roster_sha256 != expected_reviewer_roster_sha256
    ):
        reasons.add("handoff_binding_mismatch")
    if (
        not packet.frozen_at <= now < packet.decision_deadline
        or not packet.scope.valid_from <= now < packet.scope.valid_until
        or evidence.assembled_at < packet.frozen_at
        or not max(evidence.assembled_at, drill_index.assembled_at)
        <= handoff.assembled_at
        <= now
    ):
        reasons.add("handoff_window_invalid")
    if (
        evidence.drill_summary.workers_used != drill_index.workers_used
        or evidence.drill_summary.crash_cases_run != drill_index.crash_cases_run
        or evidence.drill_summary.synthetic_admissions
        != drill_index.synthetic_admissions
        or evidence.drill_summary.measured_max_stop_latency_ms
        != drill_index.measured_max_stop_latency_ms
        or evidence.drill_summary.measured_max_alert_latency_ms
        != drill_index.measured_max_alert_latency_ms
    ):
        reasons.add("drill_summary_mismatch")
    if any(
        item.status != "pass" or item.source_sha256 is None for item in evidence.records
    ):
        reasons.add("qualification_source_unavailable")
    if any(
        item.status != "pass" or item.source_sha256 is None
        for item in drill_index.observations
    ):
        reasons.add("drill_source_unavailable")
    required_record_ids = {
        "G6-01",
        "G6-02",
        "G6-03",
        "G6-04",
        *(f"Q{number}" for number in range(1, 7)),
        *(f"O{number:02d}" for number in range(1, 11)),
        *(item.milestone for item in packet.prerequisites if item.required),
    }
    records = {item.evidence_id: item for item in evidence.records}
    if set(records) != required_record_ids:
        reasons.add("qualification_coverage_invalid")
    if any(
        item.collected_at > evidence.assembled_at
        or not item.collected_at <= now < item.valid_until
        for item in evidence.records
    ):
        reasons.add("qualification_record_stale")
    for case_id in ("Q6", *(f"O{number:02d}" for number in range(1, 11))):
        record = records.get(case_id)
        if record is None:
            continue
        expected_digest = (
            drill_index.evidence_sha256
            if case_id == "Q6"
            else drill_case_sha256(drill_index, case_id)
        )
        if (
            record.source_sha256 != expected_digest
            or record.producer_id != drill_protocol.operator_id
            or record.checker_id != drill_protocol.independent_checker_id
            or record.collected_at < drill_index.assembled_at
        ):
            reasons.add("drill_record_mismatch")
    route_ids = {item.identity.candidate_id for item in packet.candidate.routes}
    route_observations = {
        item.identity.candidate_id: item for item in evidence.route_observations
    }
    if set(route_observations) != route_ids:
        reasons.add("route_coverage_invalid")
    for route in packet.candidate.routes:
        observation = route_observations.get(route.identity.candidate_id)
        if observation is None:
            continue
        if (
            observation.identity != route.identity
            or observation.pricing_basis != route.pricing_basis
            or observation.normalized_cost_microusd > route.max_normalized_cost_microusd
            or observation.catalog_status != "available"
            or observation.conformance_status != "passed"
            or observation.drift_status != "passed"
            or observation.observed_at > evidence.assembled_at
            or not observation.observed_at <= now < observation.valid_until
        ):
            reasons.add("route_observation_invalid")
    actual = {item.source_id: item for item in handoff.references}
    expected = {item.source_id: item for item in required}
    if set(actual) != set(expected):
        reasons.add("source_coverage_invalid")
    for source_id, item in actual.items():
        requirement = expected.get(source_id)
        if requirement is None:
            continue
        if (
            item.source_sha256 != requirement.source_sha256
            or item.access_mode != requirement.access_mode
            or item.check_method != requirement.check_method
            or item.checker_role != requirement.checker_role
        ):
            reasons.add("source_binding_mismatch")
        if item.status != "available":
            reasons.add("source_unavailable")
        if not item.captured_at <= handoff.assembled_at <= now < item.valid_until:
            reasons.add("source_stale")
    return G605SourceHandoffAssessment(
        handoff_sha256=handoff.handoff_sha256,
        required_source_count=len(required),
        handoff_ready=not reasons,
        reasons=tuple(sorted(reasons)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a metadata-only G6-05 source-evidence handoff"
    )
    parser.add_argument("packet", type=Path)
    parser.add_argument("qualification_evidence", type=Path)
    parser.add_argument("drill_protocol", type=Path)
    parser.add_argument("drill_index", type=Path)
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--inspection-protocol-sha256", required=True)
    parser.add_argument("--reviewer-roster-sha256", required=True)
    parser.add_argument("--now", required=True, help="Explicit ISO-8601 UTC time")
    args = parser.parse_args()
    for path in (
        args.packet,
        args.qualification_evidence,
        args.drill_protocol,
        args.drill_index,
        args.handoff,
    ):
        if path.stat().st_size > 2_000_000:
            parser.error("handoff JSON exceeds the 2 MB metadata limit")
    packet = OfflineQualificationPacket.model_validate_json(args.packet.read_bytes())
    evidence = OfflineQualificationEvidence.model_validate_json(
        args.qualification_evidence.read_bytes()
    )
    protocol = HostDrillProtocol.model_validate_json(args.drill_protocol.read_bytes())
    index = HostDrillEvidenceIndex.model_validate_json(args.drill_index.read_bytes())
    handoff = G605SourceEvidenceHandoff.model_validate_json(args.handoff.read_bytes())
    result = validate_g605_source_handoff(
        handoff=handoff,
        packet=packet,
        evidence=evidence,
        drill_protocol=protocol,
        drill_index=index,
        expected_inspection_protocol_sha256=args.inspection_protocol_sha256,
        expected_reviewer_roster_sha256=args.reviewer_roster_sha256,
        now=datetime.fromisoformat(args.now),
    )
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0 if result.handoff_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
