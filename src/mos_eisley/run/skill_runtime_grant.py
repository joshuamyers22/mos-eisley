"""Ephemeral skill-runtime bearer issuance without provider transport."""

from __future__ import annotations

import os
import secrets
import sqlite3
import stat
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.registry import ModelRegistry
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.activation_control import RoutingControlAnchor
from mos_eisley.run.provider_broker import BrokerClaim
from mos_eisley.run.routing_preflight import (
    RoutingRuntimePreflight,
    guard_routing_runtime_sources,
)
from mos_eisley.run.skill_default import SkillDefaultStore
from mos_eisley.run.skill_release_control import SkillReleaseControlAnchor
from mos_eisley.run.skill_runtime_admission import (
    SkillRuntimeAdmissionStore,
    SkillRuntimeBrokerAdmission,
)
from mos_eisley.run.skill_runtime_dispatch import (
    ConsumedSkillRuntimeDispatchAuthority,
    SignedSkillRuntimeDispatchDecision,
    SkillRuntimeDispatchAuthorityPolicy,
    SkillRuntimeDispatchClaimStore,
    verify_consumed_skill_runtime_dispatch_authority,
    verify_signed_skill_runtime_dispatch_decision,
)
from mos_eisley.run.skill_runtime_preflight import (
    PreparedSkillRuntimeRequest,
    SignedSkillRuntimeDecision,
    SkillRuntimeAuthorityPolicy,
    SkillRuntimeRequest,
    SkillRuntimeSources,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write

_ISSUANCE_DOMAIN = b"mos-eisley/skill-runtime-broker-grant-issuance/v1\x00"
_CAPABILITY_DOMAIN = b"mos-eisley/skill-runtime-broker-capability/v1\x00"
_CAPABILITY_FACTORY = object()
UtcTimestamp = Annotated[datetime, Field()]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


def _capability_sha256(capability: str) -> str:
    try:
        raw = bytes.fromhex(capability)
    except ValueError:
        raise ValueError("broker capability must be canonical hexadecimal") from None
    if len(raw) != 32 or raw.hex() != capability:
        raise ValueError("broker capability must contain exactly 256 bits")
    return digest(_CAPABILITY_DOMAIN + raw)


class SkillRuntimeBrokerGrantStorePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_broker_grant_store_policy"] = (
        "skill_runtime_broker_grant_store_policy"
    )
    store_id: Digest
    dispatch_claim_store_policy_sha256: Digest
    admission_store_policy_sha256: Digest
    routing_control_anchor_policy_sha256: Digest
    skill_control_anchor_policy_sha256: Digest
    default_store_policy_sha256: Digest
    spend_ledger_id: Digest
    max_grants: Annotated[int, Field(ge=1, le=100_000)] = 10_000
    may_issue_one_request_bound_broker_grant: Literal[True] = True
    direct_provider_dispatch_authorized: Literal[False] = False
    provider_request_sent: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class IssuedSkillRuntimeBrokerGrant(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["issued_skill_runtime_broker_grant"] = (
        "issued_skill_runtime_broker_grant"
    )
    grant_store_policy_sha256: Digest
    issuance_id: Digest
    dispatch_claim_sha256: Digest
    signed_dispatch_decision_sha256: Digest
    dispatch_decision_sha256: Digest
    admission_sha256: Digest
    admission_id: Digest
    prepared_runtime_request_sha256: Digest
    runtime_request_sha256: Digest
    route_candidate_id: Digest
    provider_request_sha256: Digest
    broker_request_sha256: Digest
    spend_ledger_id: Digest
    ledger_entry_id: Digest
    spend_reservation_sha256: Digest
    routing_control_entry_sha256: Digest
    skill_control_entry_sha256: Digest
    default_pointer_sha256: Digest
    capability_sha256: Digest
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    broker_grant_issued: Literal[True] = True
    request_bound_broker_redemption_authorized: Literal[True] = True
    direct_provider_dispatch_authorized: Literal[False] = False
    provider_request_sent: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("broker grant issuance window must be positive")
        return self

    @property
    def issuance_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeBrokerGrantStatus(Contract):
    schema_version: Literal[1] = 1
    grant_store_policy_sha256: Digest
    dispatch_decision_sha256: Digest
    phase: Literal["absent", "issued"]
    ledger_status: Literal["absent", "held", "settled", "uncertain", "violation"]
    broker_grant_issued: bool
    direct_provider_dispatch_authorized: Literal[False] = False
    provider_request_sent: Literal[False] = False
    retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False


class SkillRuntimeBrokerCapability:
    """Process-local bearer envelope; never serialize, log, or persist this object."""

    __slots__ = (
        "_capability",
        "_delivered",
        "_expires",
        "_issuance",
        "_lock",
        "_redeemed",
    )

    def __init__(
        self,
        issuance: IssuedSkillRuntimeBrokerGrant,
        capability: str,
        lifetime_seconds: float,
        *,
        started_monotonic: float | None = None,
        factory: object,
    ) -> None:
        if factory is not _CAPABILITY_FACTORY:
            raise ValueError("broker capability must be constructed by its issuer")
        if _capability_sha256(capability) != issuance.capability_sha256:
            raise ValueError("broker capability does not match issuance")
        if not 0 < lifetime_seconds <= 30:
            raise ValueError("broker capability lifetime must be at most 30 seconds")
        self._issuance = issuance
        self._capability = capability
        started = time.monotonic() if started_monotonic is None else started_monotonic
        self._expires = started + lifetime_seconds
        self._delivered = False
        self._redeemed = False
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return "SkillRuntimeBrokerCapability(<redacted>)"

    @property
    def issuance(self) -> IssuedSkillRuntimeBrokerGrant:
        return self._issuance

    def claim(self) -> BrokerClaim:
        """Deliver the bearer once to a private broker channel; never log it."""

        with self._lock:
            if self._delivered or time.monotonic() >= self._expires:
                raise ValueError("skill runtime broker capability is unavailable")
            self._delivered = True
            return BrokerClaim(
                capability=self._capability,
                request_sha256=self._issuance.broker_request_sha256,
                authorization_sha256=self._issuance.issuance_sha256,
            )

    def redeem(self, wire: bytes) -> IssuedSkillRuntimeBrokerGrant:
        """Authenticate and burn the bearer; return metadata, never request bytes."""

        try:
            if len(wire) > 1024:
                raise ValueError("oversize claim")
            claim = BrokerClaim.model_validate_json(wire)
        except ValueError:
            raise ValueError("skill runtime broker capability rejected") from None
        with self._lock:
            if (
                self._redeemed
                or time.monotonic() >= self._expires
                or not secrets.compare_digest(claim.capability, self._capability)
                or claim.request_sha256 != self._issuance.broker_request_sha256
                or claim.authorization_sha256 != self._issuance.issuance_sha256
            ):
                raise ValueError("skill runtime broker capability rejected")
            self._redeemed = True
            return self._issuance


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("broker grant store must be a regular file")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("broker grant store must be private and locally owned")


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
            raise ValueError("broker grant store requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


def _load_policy(connection: sqlite3.Connection) -> SkillRuntimeBrokerGrantStorePolicy:
    rows = connection.execute("SELECT policy_json FROM store_policy").fetchall()
    if len(rows) != 1:
        raise ValueError("broker grant store policy is invalid")
    policy = SkillRuntimeBrokerGrantStorePolicy.model_validate_json(rows[0][0])
    if rows[0][0] != canonical_bytes(policy):
        raise ValueError("broker grant store policy is not canonical")
    return policy


def _issuance_id(claim: ConsumedSkillRuntimeDispatchAuthority) -> str:
    return digest(_ISSUANCE_DOMAIN + bytes.fromhex(claim.claim_sha256))


def _issuance_matches(
    policy: SkillRuntimeBrokerGrantStorePolicy,
    issuance: IssuedSkillRuntimeBrokerGrant,
    claim: ConsumedSkillRuntimeDispatchAuthority,
    signed: SignedSkillRuntimeDispatchDecision,
) -> bool:
    decision = signed.decision
    return (
        issuance.grant_store_policy_sha256 == policy.policy_sha256
        and issuance.issuance_id == _issuance_id(claim)
        and issuance.dispatch_claim_sha256 == claim.claim_sha256
        and issuance.signed_dispatch_decision_sha256
        == claim.signed_dispatch_decision_sha256
        == signed.signed_decision_sha256
        and issuance.dispatch_decision_sha256
        == claim.dispatch_decision_sha256
        == decision.decision_sha256
        and issuance.admission_sha256
        == claim.admission_sha256
        == decision.admission_sha256
        and issuance.admission_id == claim.admission_id == decision.admission_id
        and issuance.prepared_runtime_request_sha256
        == decision.prepared_runtime_request_sha256
        and issuance.runtime_request_sha256 == decision.runtime_request_sha256
        and issuance.route_candidate_id == decision.route_candidate_id
        and issuance.provider_request_sha256
        == claim.provider_request_sha256
        == decision.provider_request_sha256
        and issuance.broker_request_sha256
        == claim.broker_request_sha256
        == decision.broker_request_sha256
        and issuance.spend_ledger_id
        == claim.spend_ledger_id
        == decision.spend_ledger_id
        and issuance.ledger_entry_id
        == claim.ledger_entry_id
        == decision.ledger_entry_id
        and issuance.spend_reservation_sha256
        == claim.spend_reservation_sha256
        == decision.spend_reservation_sha256
        and issuance.routing_control_entry_sha256
        == decision.routing_control_entry_sha256
        and issuance.skill_control_entry_sha256 == decision.skill_control_entry_sha256
        and issuance.default_pointer_sha256 == decision.default_pointer_sha256
        and claim.consumed_at <= issuance.issued_at < issuance.valid_until
        and issuance.valid_until <= claim.valid_until
    )


class SkillRuntimeBrokerGrantStore:
    """Durable issuance records contain a capability hash, never the bearer secret."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _load_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: SkillRuntimeBrokerGrantStorePolicy,
        dispatch_claim_store: SkillRuntimeDispatchClaimStore,
        admission_store: SkillRuntimeAdmissionStore,
        routing_control_anchor: RoutingControlAnchor,
        skill_control_anchor: SkillReleaseControlAnchor,
        default_store: SkillDefaultStore,
        ledger: SpendLedger,
    ) -> SkillRuntimeBrokerGrantStore:
        if (
            policy.dispatch_claim_store_policy_sha256
            != dispatch_claim_store.policy.policy_sha256
            or policy.admission_store_policy_sha256
            != admission_store.policy.policy_sha256
            or policy.routing_control_anchor_policy_sha256
            != routing_control_anchor.policy.policy_sha256
            or policy.skill_control_anchor_policy_sha256
            != skill_control_anchor.policy.policy_sha256
            or policy.default_store_policy_sha256 != default_store.policy.policy_sha256
            or policy.spend_ledger_id != ledger.policy.ledger_id
        ):
            raise ValueError("broker grant store policy does not match local controls")
        policy = SkillRuntimeBrokerGrantStorePolicy.model_validate_json(
            canonical_bytes(policy)
        )
        private_write(path, b"")
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE store_policy (singleton INTEGER PRIMARY KEY "
                "CHECK(singleton = 1), policy_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO store_policy VALUES (1, ?)", (canonical_bytes(policy),)
            )
            connection.execute(
                "CREATE TABLE grants (dispatch_decision_sha256 TEXT PRIMARY KEY, "
                "dispatch_claim_sha256 TEXT NOT NULL UNIQUE, "
                "admission_id TEXT NOT NULL UNIQUE, "
                "ledger_entry_id TEXT NOT NULL UNIQUE, "
                "capability_sha256 TEXT NOT NULL UNIQUE, issuance_sha256 TEXT NOT NULL "
                "UNIQUE, issuance_json BLOB NOT NULL, claim_json BLOB NOT NULL, "
                "signed_json BLOB NOT NULL) STRICT"
            )
        return cls(path)

    def _records(
        self, connection: sqlite3.Connection
    ) -> tuple[IssuedSkillRuntimeBrokerGrant, ...]:
        rows = connection.execute(
            "SELECT dispatch_decision_sha256, dispatch_claim_sha256, admission_id, "
            "ledger_entry_id, capability_sha256, issuance_sha256, issuance_json, "
            "claim_json, signed_json FROM grants ORDER BY rowid"
        ).fetchall()
        records: list[IssuedSkillRuntimeBrokerGrant] = []
        for row in rows:
            issuance = IssuedSkillRuntimeBrokerGrant.model_validate_json(row[6])
            claim = ConsumedSkillRuntimeDispatchAuthority.model_validate_json(row[7])
            signed = SignedSkillRuntimeDispatchDecision.model_validate_json(row[8])
            if (
                row[0] != issuance.dispatch_decision_sha256
                or row[1] != issuance.dispatch_claim_sha256
                or row[2] != issuance.admission_id
                or row[3] != issuance.ledger_entry_id
                or row[4] != issuance.capability_sha256
                or row[5] != issuance.issuance_sha256
                or row[6] != canonical_bytes(issuance)
                or row[7] != canonical_bytes(claim)
                or row[8] != canonical_bytes(signed)
                or not _issuance_matches(self.policy, issuance, claim, signed)
            ):
                raise ValueError("broker grant store record is invalid")
            records.append(issuance)
        if len(records) > self.policy.max_grants:
            raise ValueError("broker grant store exceeds policy")
        return tuple(records)

    def get(
        self, dispatch_decision_sha256: str
    ) -> IssuedSkillRuntimeBrokerGrant | None:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("broker grant store identity changed")
            matches = [
                item
                for item in self._records(connection)
                if item.dispatch_decision_sha256 == dispatch_decision_sha256
            ]
            if len(matches) > 1:
                raise ValueError("broker grant issuance identity is not unique")
            return matches[0] if matches else None

    def issue(
        self,
        issuance: IssuedSkillRuntimeBrokerGrant,
        claim: ConsumedSkillRuntimeDispatchAuthority,
        signed: SignedSkillRuntimeDispatchDecision,
    ) -> None:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _load_policy(connection) != self.policy:
                raise ValueError("broker grant store identity changed")
            records = self._records(connection)
            if len(records) >= self.policy.max_grants:
                raise ValueError("broker grant store limit reached")
            if not _issuance_matches(self.policy, issuance, claim, signed):
                raise ValueError("broker grant issuance provenance mismatch")
            if any(
                item.dispatch_decision_sha256 == issuance.dispatch_decision_sha256
                or item.dispatch_claim_sha256 == issuance.dispatch_claim_sha256
                or item.admission_id == issuance.admission_id
                or item.ledger_entry_id == issuance.ledger_entry_id
                for item in records
            ):
                raise ValueError("skill runtime broker grant was already issued")
            connection.execute(
                "INSERT INTO grants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    issuance.dispatch_decision_sha256,
                    issuance.dispatch_claim_sha256,
                    issuance.admission_id,
                    issuance.ledger_entry_id,
                    issuance.capability_sha256,
                    issuance.issuance_sha256,
                    canonical_bytes(issuance),
                    canonical_bytes(claim),
                    canonical_bytes(signed),
                ),
            )


def _validate_store_provenance(
    sources: SkillRuntimeSources,
    ledger: SpendLedger,
    admission_store: SkillRuntimeAdmissionStore,
    claim_store: SkillRuntimeDispatchClaimStore,
    grant_store: SkillRuntimeBrokerGrantStore,
    dispatch_policy: SkillRuntimeDispatchAuthorityPolicy,
) -> None:
    policy = grant_store.policy
    if (
        dispatch_policy.broker_grant_store_policy_sha256 != policy.policy_sha256
        or policy.dispatch_claim_store_policy_sha256 != claim_store.policy.policy_sha256
        or policy.admission_store_policy_sha256 != admission_store.policy.policy_sha256
        or policy.routing_control_anchor_policy_sha256
        != sources.routing.control_anchor.policy.policy_sha256
        or policy.skill_control_anchor_policy_sha256
        != sources.control_anchor.policy.policy_sha256
        or policy.default_store_policy_sha256
        != sources.default_store.policy.policy_sha256
        or policy.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime broker grant store provenance mismatch")


def issue_skill_runtime_broker_capability(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    signed_runtime: SignedSkillRuntimeDecision,
    prepared: PreparedSkillRuntimeRequest,
    admission: SkillRuntimeBrokerAdmission,
    admission_store: SkillRuntimeAdmissionStore,
    claim_store: SkillRuntimeDispatchClaimStore,
    dispatch_policy: SkillRuntimeDispatchAuthorityPolicy,
    signed_dispatch: SignedSkillRuntimeDispatchDecision,
    dispatch_claim: ConsumedSkillRuntimeDispatchAuthority,
    grant_store: SkillRuntimeBrokerGrantStore,
    now: datetime,
    lifetime_seconds: int = 15,
) -> SkillRuntimeBrokerCapability:
    """Issue one memory-only bearer under all guards; never dispatch a request."""

    current = _require_utc(now)
    started = time.monotonic()
    if not 1 <= lifetime_seconds <= 30:
        raise ValueError("broker grant lifetime must be between 1 and 30 seconds")
    verify_consumed_skill_runtime_dispatch_authority(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        signed_runtime,
        prepared,
        admission,
        admission_store,
        claim_store,
        dispatch_policy,
        signed_dispatch,
        dispatch_claim,
        current,
    )
    _validate_store_provenance(
        sources,
        ledger,
        admission_store,
        claim_store,
        grant_store,
        dispatch_policy,
    )
    valid_until = min(
        dispatch_claim.valid_until, current + timedelta(seconds=lifetime_seconds)
    )
    actual_lifetime = (valid_until - current).total_seconds()
    if actual_lifetime <= 0:
        raise ValueError("broker grant authority expired before issuance")
    capability = secrets.token_hex(32)
    decision = signed_dispatch.decision
    issuance = IssuedSkillRuntimeBrokerGrant(
        grant_store_policy_sha256=grant_store.policy.policy_sha256,
        issuance_id=_issuance_id(dispatch_claim),
        dispatch_claim_sha256=dispatch_claim.claim_sha256,
        signed_dispatch_decision_sha256=signed_dispatch.signed_decision_sha256,
        dispatch_decision_sha256=decision.decision_sha256,
        admission_sha256=admission.admission_sha256,
        admission_id=admission.admission_id,
        prepared_runtime_request_sha256=prepared.preflight_sha256,
        runtime_request_sha256=request.request_sha256,
        route_candidate_id=request.route.candidate_id,
        provider_request_sha256=decision.provider_request_sha256,
        broker_request_sha256=decision.broker_request_sha256,
        spend_ledger_id=ledger.policy.ledger_id,
        ledger_entry_id=prepared.ledger_entry.entry_id,
        spend_reservation_sha256=prepared.ledger_entry.reservation_sha256,
        routing_control_entry_sha256=decision.routing_control_entry_sha256,
        skill_control_entry_sha256=decision.skill_control_entry_sha256,
        default_pointer_sha256=decision.default_pointer_sha256,
        capability_sha256=_capability_sha256(capability),
        issued_at=current,
        valid_until=valid_until,
    )
    with (
        guard_routing_runtime_sources(sources.routing, routing_preflight, current),
        sources.control_anchor.guard_latest(
            sources.control, sources.control_policy, current
        ) as skill_control,
    ):
        if skill_control.anchor_entry_sha256 != issuance.skill_control_entry_sha256:
            raise ValueError("skill runtime broker grant skill control changed")
        with sources.default_store.guard_current(
            sources.default_policy,
            sources.installed_store,
            sources.installation_policy,
        ) as pointer:
            if pointer.pointer_sha256 != issuance.default_pointer_sha256:
                raise ValueError("skill runtime broker grant default changed")
            with (
                ledger.guard_held(prepared.ledger_entry),
                admission_store.guard_admission(admission),
                claim_store.guard_claim(dispatch_claim),
            ):
                grant_store.issue(issuance, dispatch_claim, signed_dispatch)
    remaining = actual_lifetime - (time.monotonic() - started)
    if remaining <= 0:
        raise ValueError("broker grant expired during durable issuance")
    return SkillRuntimeBrokerCapability(
        issuance,
        capability,
        actual_lifetime,
        started_monotonic=started,
        factory=_CAPABILITY_FACTORY,
    )


def inspect_skill_runtime_broker_grant(
    signed_dispatch: SignedSkillRuntimeDispatchDecision,
    dispatch_policy: SkillRuntimeDispatchAuthorityPolicy,
    grant_store: SkillRuntimeBrokerGrantStore,
    ledger: SpendLedger,
) -> SkillRuntimeBrokerGrantStatus:
    """Inspect durable issuance without recovering a bearer or authorizing retry."""

    verify_signed_skill_runtime_dispatch_decision(signed_dispatch, dispatch_policy)
    decision = signed_dispatch.decision
    if (
        decision.authority_policy_sha256 != dispatch_policy.policy_sha256
        or dispatch_policy.broker_grant_store_policy_sha256
        != grant_store.policy.policy_sha256
        or decision.spend_ledger_id != ledger.policy.ledger_id
        or grant_store.policy.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime broker grant status provenance mismatch")
    issuance = grant_store.get(decision.decision_sha256)
    if (
        issuance is not None
        and issuance.signed_dispatch_decision_sha256
        != signed_dispatch.signed_decision_sha256
    ):
        raise ValueError("skill runtime broker grant status signed decision mismatch")
    entry = ledger.entry_status(decision.ledger_entry_id)
    if (
        entry is not None
        and entry.reservation_sha256 != decision.spend_reservation_sha256
    ):
        raise ValueError("skill runtime broker grant status reservation mismatch")
    return SkillRuntimeBrokerGrantStatus(
        grant_store_policy_sha256=grant_store.policy.policy_sha256,
        dispatch_decision_sha256=decision.decision_sha256,
        phase="absent" if issuance is None else "issued",
        ledger_status="absent" if entry is None else entry.status,
        broker_grant_issued=issuance is not None,
    )
