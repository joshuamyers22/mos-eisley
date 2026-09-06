"""Durable one-use broker admission for an already-reserved runtime request."""

from __future__ import annotations

import os
import sqlite3
import stat
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.registry import ModelRegistry
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.activation_control import RoutingControlAnchor
from mos_eisley.run.routing_preflight import (
    RoutingRuntimePreflight,
    guard_routing_runtime_sources,
)
from mos_eisley.run.skill_default import SkillDefaultStore
from mos_eisley.run.skill_release_control import SkillReleaseControlAnchor
from mos_eisley.run.skill_runtime_preflight import (
    PreparedSkillRuntimeRequest,
    SignedSkillRuntimeDecision,
    SkillRuntimeAuthorityPolicy,
    SkillRuntimeRequest,
    SkillRuntimeSources,
    verify_prepared_skill_runtime_request,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write

_ADMISSION_DOMAIN = b"mos-eisley/skill-runtime-broker-admission/v1\x00"
UtcTimestamp = Annotated[datetime, Field()]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class SkillRuntimeAdmissionStorePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_admission_store_policy"] = (
        "skill_runtime_admission_store_policy"
    )
    store_id: Digest
    routing_control_anchor_policy_sha256: Digest
    skill_control_anchor_policy_sha256: Digest
    default_store_policy_sha256: Digest
    spend_ledger_id: Digest
    may_record_one_use_admission: Literal[True] = True
    broker_grant_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    provider_request_authorized: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeBrokerAdmission(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_broker_admission"] = "skill_runtime_broker_admission"
    admission_store_policy_sha256: Digest
    admission_id: Digest
    prepared_runtime_request_sha256: Digest
    signed_runtime_decision_sha256: Digest
    decision_sha256: Digest
    runtime_request_sha256: Digest
    routing_preflight_sha256: Digest
    routing_control_entry_sha256: Digest
    skill_control_entry_sha256: Digest
    default_pointer_sha256: Digest
    provider_request_sha256: Digest
    broker_request_sha256: Digest
    spend_ledger_id: Digest
    ledger_entry_id: Digest
    spend_reservation_sha256: Digest
    admitted_at: UtcTimestamp
    valid_until: UtcTimestamp
    authorization_already_consumed: Literal[True] = True
    existing_reservation_claimed: Literal[True] = True
    second_reservation_created: Literal[False] = False
    one_use_admission_recorded: Literal[True] = True
    broker_grant_issued: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    provider_request_sent: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @field_validator("admitted_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.admitted_at:
            raise ValueError("skill runtime broker admission window must be positive")
        return self

    @property
    def admission_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeAdmissionStatus(Contract):
    schema_version: Literal[1] = 1
    store_policy_sha256: Digest
    admission_id: Digest
    phase: Literal["absent", "admitted"]
    ledger_status: Literal["absent", "held", "settled", "uncertain", "violation"]
    retry_permitted: Literal[False] = False
    broker_grant_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("skill runtime admission store must be a regular file")
    if metadata.st_uid != os.getuid():
        raise ValueError("skill runtime admission store must belong to current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("skill runtime admission store must be private")


def _connect(path: Path) -> sqlite3.Connection:
    _validate_private_database(path)
    connection = sqlite3.connect(
        path.absolute().as_uri() + "?mode=rw",
        uri=True,
        timeout=0.25,
        isolation_level=None,
    )
    try:
        connection.execute("PRAGMA synchronous=EXTRA")
        connection.execute("PRAGMA trusted_schema=OFF")
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise ValueError(
                "skill runtime admission store requires rollback journaling"
            )
        return connection
    except BaseException:
        connection.close()
        raise


def _load_policy(connection: sqlite3.Connection) -> SkillRuntimeAdmissionStorePolicy:
    rows = connection.execute("SELECT policy_json FROM store_policy").fetchall()
    if len(rows) != 1:
        raise ValueError("skill runtime admission store policy is invalid")
    policy = SkillRuntimeAdmissionStorePolicy.model_validate_json(rows[0][0])
    if rows[0][0] != canonical_bytes(policy):
        raise ValueError("skill runtime admission store policy is not canonical")
    return policy


class SkillRuntimeAdmissionStore:
    """Private append-only readiness records; contains no prompt or credential."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _load_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: SkillRuntimeAdmissionStorePolicy,
        routing_control_anchor: RoutingControlAnchor,
        skill_control_anchor: SkillReleaseControlAnchor,
        default_store: SkillDefaultStore,
        ledger: SpendLedger,
    ) -> SkillRuntimeAdmissionStore:
        if (
            policy.routing_control_anchor_policy_sha256
            != routing_control_anchor.policy.policy_sha256
            or policy.skill_control_anchor_policy_sha256
            != skill_control_anchor.policy.policy_sha256
            or policy.default_store_policy_sha256 != default_store.policy.policy_sha256
            or policy.spend_ledger_id != ledger.policy.ledger_id
        ):
            raise ValueError("admission store policy does not match local controls")
        policy = SkillRuntimeAdmissionStorePolicy.model_validate_json(
            canonical_bytes(policy)
        )
        private_write(path, b"")
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE store_policy ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
                "policy_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO store_policy VALUES (1, ?)",
                (canonical_bytes(policy),),
            )
            connection.execute(
                "CREATE TABLE admissions ("
                "admission_id TEXT PRIMARY KEY, "
                "prepared_sha256 TEXT NOT NULL UNIQUE, "
                "decision_sha256 TEXT NOT NULL UNIQUE, "
                "ledger_entry_id TEXT NOT NULL UNIQUE, "
                "admission_sha256 TEXT NOT NULL UNIQUE, "
                "admission_json BLOB NOT NULL) STRICT"
            )
        return cls(path)

    def _records(
        self, connection: sqlite3.Connection
    ) -> tuple[SkillRuntimeBrokerAdmission, ...]:
        rows = connection.execute(
            "SELECT admission_id, prepared_sha256, decision_sha256, ledger_entry_id, "
            "admission_sha256, admission_json FROM admissions ORDER BY rowid"
        ).fetchall()
        records: list[SkillRuntimeBrokerAdmission] = []
        for row in rows:
            record = SkillRuntimeBrokerAdmission.model_validate_json(row[5])
            if (
                row[0] != record.admission_id
                or row[1] != record.prepared_runtime_request_sha256
                or row[2] != record.decision_sha256
                or row[3] != record.ledger_entry_id
                or row[4] != record.admission_sha256
                or row[5] != canonical_bytes(record)
                or record.admission_store_policy_sha256 != self.policy.policy_sha256
            ):
                raise ValueError("skill runtime admission record is invalid")
            records.append(record)
        return tuple(records)

    def commit_admission(self, admission: SkillRuntimeBrokerAdmission) -> None:
        """Insert a non-authorizing readiness record; duplicates fail closed."""

        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _load_policy(connection) != self.policy:
                raise ValueError("skill runtime admission store identity changed")
            self._records(connection)
            if admission.admission_store_policy_sha256 != self.policy.policy_sha256:
                raise ValueError("skill runtime admission store policy mismatch")
            connection.execute(
                "INSERT INTO admissions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    admission.admission_id,
                    admission.prepared_runtime_request_sha256,
                    admission.decision_sha256,
                    admission.ledger_entry_id,
                    admission.admission_sha256,
                    canonical_bytes(admission),
                ),
            )

    def get(self, admission_id: str) -> SkillRuntimeBrokerAdmission | None:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("skill runtime admission store identity changed")
            records = self._records(connection)
            matches = [item for item in records if item.admission_id == admission_id]
            if len(matches) > 1:
                raise ValueError("skill runtime admission identity is not unique")
            return matches[0] if matches else None


def _admission_id(prepared: PreparedSkillRuntimeRequest) -> str:
    return digest(_ADMISSION_DOMAIN + bytes.fromhex(prepared.preflight_sha256))


def make_skill_runtime_broker_admission(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    signed: SignedSkillRuntimeDecision,
    prepared: PreparedSkillRuntimeRequest,
    store: SkillRuntimeAdmissionStore,
    now: datetime,
) -> SkillRuntimeBrokerAdmission:
    """Record readiness under every local guard without issuing dispatch authority."""

    current = _require_utc(now)
    verify_prepared_skill_runtime_request(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        signed,
        prepared,
        current,
    )
    policy = store.policy
    if (
        runtime_policy.admission_store_policy_sha256 != policy.policy_sha256
        or policy.routing_control_anchor_policy_sha256
        != sources.routing.control_anchor.policy.policy_sha256
        or policy.skill_control_anchor_policy_sha256
        != sources.control_anchor.policy.policy_sha256
        or policy.default_store_policy_sha256
        != sources.default_store.policy.policy_sha256
        or policy.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime admission store provenance mismatch")
    decision = signed.decision
    admission = SkillRuntimeBrokerAdmission(
        admission_store_policy_sha256=policy.policy_sha256,
        admission_id=_admission_id(prepared),
        prepared_runtime_request_sha256=prepared.preflight_sha256,
        signed_runtime_decision_sha256=signed.signed_decision_sha256,
        decision_sha256=decision.decision_sha256,
        runtime_request_sha256=request.request_sha256,
        routing_preflight_sha256=routing_preflight.preflight_sha256,
        routing_control_entry_sha256=(routing_preflight.anchored_control_entry_sha256),
        skill_control_entry_sha256=(
            sources.signed_health_policy.policy.control_anchor_entry_sha256
        ),
        default_pointer_sha256=decision.default_pointer_sha256,
        provider_request_sha256=decision.provider_request_sha256,
        broker_request_sha256=decision.broker_request_sha256,
        spend_ledger_id=ledger.policy.ledger_id,
        ledger_entry_id=prepared.ledger_entry.entry_id,
        spend_reservation_sha256=prepared.ledger_entry.reservation_sha256,
        admitted_at=current,
        valid_until=prepared.valid_until,
    )
    with (
        guard_routing_runtime_sources(sources.routing, routing_preflight, current),
        sources.control_anchor.guard_latest(
            sources.control, sources.control_policy, current
        ) as skill_control,
    ):
        if skill_control.anchor_entry_sha256 != admission.skill_control_entry_sha256:
            raise ValueError("skill runtime admission skill control changed")
        with sources.default_store.guard_current(
            sources.default_policy,
            sources.installed_store,
            sources.installation_policy,
        ) as pointer:
            if pointer.pointer_sha256 != admission.default_pointer_sha256:
                raise ValueError("skill runtime admission default changed")
            with ledger.guard_held(prepared.ledger_entry):
                try:
                    store.commit_admission(admission)
                except sqlite3.IntegrityError:
                    if store.get(admission.admission_id) is not None:
                        raise ValueError(
                            "skill runtime broker admission was already recorded"
                        ) from None
                    raise
    return admission


def inspect_skill_runtime_admission(
    prepared: PreparedSkillRuntimeRequest,
    store: SkillRuntimeAdmissionStore,
    ledger: SpendLedger,
) -> SkillRuntimeAdmissionStatus:
    """Inspect readiness without granting, dispatching, retrying, or releasing."""

    if store.policy.spend_ledger_id != ledger.policy.ledger_id:
        raise ValueError("skill runtime admission status ledger mismatch")
    admission_id = _admission_id(prepared)
    record = store.get(admission_id)
    if record is not None and (
        record.prepared_runtime_request_sha256 != prepared.preflight_sha256
        or record.ledger_entry_id != prepared.ledger_entry.entry_id
        or record.spend_reservation_sha256 != prepared.ledger_entry.reservation_sha256
    ):
        raise ValueError("skill runtime admission status provenance mismatch")
    entry = ledger.entry_status(prepared.ledger_entry.entry_id)
    if entry is not None and (
        entry.reservation_sha256 != prepared.ledger_entry.reservation_sha256
        or entry.reserved_microusd != prepared.ledger_entry.reserved_microusd
    ):
        raise ValueError("skill runtime admission status reservation mismatch")
    return SkillRuntimeAdmissionStatus(
        store_policy_sha256=store.policy.policy_sha256,
        admission_id=admission_id,
        phase="absent" if record is None else "admitted",
        ledger_status="absent" if entry is None else entry.status,
    )
