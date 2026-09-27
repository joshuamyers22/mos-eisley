"""Offline G6-06 cohort controller around the synthetic witnessed journal."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from mos_eisley.run.activation_control import AnchoredRoutingControl
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from mos_eisley.run.witnessed_admission import (
    CohortManifest,
    SignedCohortRelease,
    SyntheticCohortTrust,
    SyntheticWitnessedAdmission,
    WitnessedAdmissionReceipt,
    WitnessedAssignment,
    WitnessedAttempt,
    WitnessedCohortState,
)


class OfflineCohortController:
    """One fixture lineage; no provider credential or live release authority."""

    def __init__(self, admission: SyntheticWitnessedAdmission):
        self.admission = admission

    def enroll_shadow(
        self,
        *,
        manifest: CohortManifest,
        trust: SyntheticCohortTrust,
        signed_release: SignedCohortRelease,
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedCohortState:
        return self.admission.enroll_cohort(
            manifest=manifest,
            trust=trust,
            signed_release=signed_release,
            now=now,
            fault=fault,
        )

    def advance_release(
        self,
        *,
        signed_release: SignedCohortRelease,
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedCohortState:
        return self.admission.advance_cohort_release(
            signed_release=signed_release, now=now, fault=fault
        )

    def assign(
        self,
        *,
        owner_id: str,
        cohort_id: str,
        task_id: str,
        session_id: str,
        stage_id: str,
        candidate_policy_sha256: str,
        expected_release_sha256: str,
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedAssignment:
        return self.admission.assign_cohort_task(
            owner_id=owner_id,
            cohort_id=cohort_id,
            task_id=task_id,
            session_id=session_id,
            stage_id=stage_id,
            candidate_policy_sha256=candidate_policy_sha256,
            expected_release_sha256=expected_release_sha256,
            now=now,
            fault=fault,
        )

    def claim(
        self,
        *,
        attempt: WitnessedAttempt,
        expected_control: AnchoredRoutingControl,
        current_preflight: RoutingRuntimePreflight,
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedAdmissionReceipt:
        return self.admission.claim_with_budget(
            attempt=attempt,
            expected_control=expected_control,
            current_preflight=current_preflight,
            now=now,
            fault=fault,
        )

    def inspect(self, *, owner_id: str, cohort_id: str) -> WitnessedCohortState | None:
        return self.admission.inspect_cohort(owner_id=owner_id, cohort_id=cohort_id)
