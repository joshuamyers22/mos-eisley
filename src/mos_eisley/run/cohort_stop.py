"""Read-only synthetic G6-06 stop and re-entry inventory."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier
from mos_eisley.run.routing_transaction import (
    FrozenCohortRecoveryAnchor,
    OfflineTransactionStore,
    SyntheticCohortAuditSink,
    inspect_offline_cohort_recovery,
)
from mos_eisley.run.witnessed_admission import SyntheticWitnessedAdmission

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


class OfflineCohortStopInventory(Contract):
    schema_version: Literal[1] = 1
    owner_id: Identifier
    cohort_id: Identifier
    witness_epoch_id: Digest
    stop_control_entry_sha256: Digest
    control_sequence: Annotated[int, Field(ge=1)]
    stop_issued_at: datetime
    stop_witnessed_at: datetime
    checkpoint_generation: Annotated[int, Field(ge=1)]
    assignment_count: Annotated[int, Field(ge=0)]
    claim_count: Annotated[int, Field(ge=0)]
    intent_count: Annotated[int, Field(ge=0)]
    audit_count: Annotated[int, Field(ge=0)]
    possible_in_flight_count: Annotated[int, Field(ge=0)]
    conservative_exposure_microusd: Money
    stop_acknowledged: Literal[True] = True
    reentry_authorized: Literal[False] = False

    @model_validator(mode="after")
    def ordered_utc_stop(self) -> Self:
        for value in (self.stop_issued_at, self.stop_witnessed_at):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError("synthetic stop time must use explicit UTC")
        if self.stop_witnessed_at < self.stop_issued_at:
            raise ValueError("synthetic stop was witnessed before issuance")
        return self


def inspect_offline_cohort_stop(
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
    audit: SyntheticCohortAuditSink,
    *,
    recovery_anchor: FrozenCohortRecoveryAnchor,
) -> OfflineCohortStopInventory:
    """Require an acknowledged stop and preserve all possible exposure."""
    recovery = inspect_offline_cohort_recovery(
        admission, store, audit, anchor=recovery_anchor
    )
    if recovery.status != "consistent":
        raise ValueError("synthetic stop inventory has inconsistent recovery sources")
    state = admission.read_current()
    cohort = state.cohort
    control = state.control.signed_control.control
    if cohort is None or not control.emergency_stop:
        raise ValueError("synthetic cohort has no witnessed stop")
    checkpoint = admission.checkpoint.read_current()
    intents = store.list_intents()
    events = audit.read_current()
    intent_keys = {item.attempt_key for item in intents}
    return OfflineCohortStopInventory(
        owner_id=cohort.manifest.owner_id,
        cohort_id=cohort.manifest.cohort_id,
        witness_epoch_id=state.epoch_id,
        stop_control_entry_sha256=state.control.anchor_entry_sha256,
        control_sequence=control.sequence,
        stop_issued_at=control.issued_at,
        stop_witnessed_at=state.control.anchored_at,
        checkpoint_generation=checkpoint.generation,
        assignment_count=len(cohort.assignments),
        claim_count=len(state.attempts),
        intent_count=len(intents),
        audit_count=len(events),
        possible_in_flight_count=sum(
            row.attempt.attempt_key in intent_keys and row.status != "settled"
            for row in state.attempts
        ),
        conservative_exposure_microusd=recovery.conservative_exposure_microusd,
    )
