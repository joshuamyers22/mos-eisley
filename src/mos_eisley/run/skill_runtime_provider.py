"""Provider-owning, pre-reserved skill-runtime transaction with no retry path."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, TypeAdapter, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_http import MAX_OPENAI_RESPONSE_BYTES
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.activation_control import RoutingControlAnchor
from mos_eisley.run.routing_preflight import (
    RoutingRuntimePreflight,
    guard_routing_runtime_sources,
)
from mos_eisley.run.skill_default import SkillDefaultStore
from mos_eisley.run.skill_release_control import SkillReleaseControlAnchor
from mos_eisley.run.skill_runtime_grant import (
    IssuedSkillRuntimeBrokerGrant,
    SkillRuntimeBrokerCapability,
    SkillRuntimeBrokerGrantStore,
)
from mos_eisley.run.skill_runtime_preflight import (
    PreparedSkillRuntimeRequest,
    SkillRuntimeSources,
)
from mos_eisley.run.spend_ledger import LedgerSettlement, SpendLedger
from mos_eisley.run.store import private_write

_TRANSACTION_DOMAIN = b"mos-eisley/skill-runtime-provider-transaction/v1\x00"
_STORE_WRITER = object()
_RESPONSE = TypeAdapter(dict[str, JsonValue])
UtcTimestamp = Annotated[datetime, Field()]
Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


def _provider_request_sha256(payload: dict[str, JsonValue]) -> str:
    normalized = dict(payload)
    normalized["store"] = False
    normalized["truncation"] = "disabled"
    normalized["service_tier"] = "default"
    return digest(
        json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def skill_runtime_provider_response_sha256(payload: dict[str, JsonValue]) -> str:
    """Hash the exact bounded JSON representation used by runtime persistence."""

    return digest(skill_runtime_provider_response_bytes(payload))


def skill_runtime_provider_response_bytes(payload: dict[str, JsonValue]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class SkillRuntimeProviderTransport(Protocol):
    """Credential-owning transport; implementations must disable retries."""

    provider: Literal["openai"]
    automatic_retries: Literal[0]

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...


class SkillRuntimeProviderTransactionStorePolicy(Contract):
    schema_version: Literal[2] = 2
    mode: Literal["skill_runtime_provider_transaction_store_policy"] = (
        "skill_runtime_provider_transaction_store_policy"
    )
    store_id: Digest
    broker_grant_store_id: Digest
    routing_control_anchor_policy_sha256: Digest
    skill_control_anchor_policy_sha256: Digest
    default_store_policy_sha256: Digest
    spend_ledger_id: Digest
    response_store_policy_sha256: Digest
    max_transactions: Annotated[int, Field(ge=1, le=100_000)] = 10_000
    max_provider_wait_seconds: Annotated[int, Field(ge=1, le=60)] = 60
    may_own_one_pre_reserved_provider_request: Literal[True] = True
    before_send_commit_required: Literal[True] = True
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeProviderSendIntent(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_provider_send_intent"] = (
        "skill_runtime_provider_send_intent"
    )
    transaction_store_policy_sha256: Digest
    transaction_id: Digest
    issuance_sha256: Digest
    issuance_id: Digest
    grant_store_policy_sha256: Digest
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
    recorded_at: UtcTimestamp
    capability_redeemed: Literal[True] = True
    existing_reservation_claimed: Literal[True] = True
    second_reservation_created: Literal[False] = False
    before_send_committed: Literal[True] = True
    provider_transfer_may_have_started: Literal[True] = True
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @model_validator(mode="after")
    def utc_timestamp(self) -> Self:
        _require_utc(self.recorded_at)
        return self

    @property
    def intent_sha256(self) -> str:
        return digest(canonical_bytes(self))


ProviderOutcome = Literal["response_received", "uncertain", "violation"]


class SkillRuntimeProviderOutcome(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_provider_outcome"] = "skill_runtime_provider_outcome"
    transaction_id: Digest
    intent_sha256: Digest
    status: ProviderOutcome
    charged_microusd: Money
    provider_response_observed: bool
    provider_response_sha256: Digest | None = None
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None
    completed_at: UtcTimestamp
    provider_transport_invoked_once: Literal[True] = True
    retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @model_validator(mode="after")
    def coherent_outcome(self) -> Self:
        _require_utc(self.completed_at)
        observed = self.provider_response_sha256 is not None
        if self.provider_response_observed != observed:
            raise ValueError("provider response observation is inconsistent")
        complete_usage = (
            self.input_tokens is not None and self.output_tokens is not None
        )
        if (self.input_tokens is None) != (self.output_tokens is None):
            raise ValueError("provider outcome requires both usage values")
        if self.status == "response_received" and (not observed or not complete_usage):
            raise ValueError("received provider outcome requires response and usage")
        if self.status != "response_received" and complete_usage:
            raise ValueError("non-settled provider outcome cannot claim exact usage")
        return self

    @property
    def outcome_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeProviderReply(Contract):
    intent: SkillRuntimeProviderSendIntent
    outcome: SkillRuntimeProviderOutcome
    response: dict[str, JsonValue]


class SkillRuntimeProviderTransactionStatus(Contract):
    schema_version: Literal[1] = 1
    transaction_store_policy_sha256: Digest
    issuance_sha256: Digest
    transaction_id: Digest
    phase: Literal["absent", "before_send", "finished"]
    outcome: ProviderOutcome | None = None
    ledger_status: Literal["absent", "held", "settled", "uncertain", "violation"]
    before_send_committed: bool
    provider_transfer_may_have_started: bool
    retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("provider transaction store must be a regular file")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("provider transaction store must be private and locally owned")


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
            raise ValueError("provider transaction store requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


def _load_policy(
    connection: sqlite3.Connection,
) -> SkillRuntimeProviderTransactionStorePolicy:
    rows = connection.execute("SELECT policy_json FROM store_policy").fetchall()
    if len(rows) != 1:
        raise ValueError("provider transaction store policy is invalid")
    policy = SkillRuntimeProviderTransactionStorePolicy.model_validate_json(rows[0][0])
    if rows[0][0] != canonical_bytes(policy):
        raise ValueError("provider transaction store policy is not canonical")
    return policy


def _transaction_id(issuance: IssuedSkillRuntimeBrokerGrant) -> str:
    return digest(_TRANSACTION_DOMAIN + bytes.fromhex(issuance.issuance_sha256))


def _intent_matches(
    policy: SkillRuntimeProviderTransactionStorePolicy,
    intent: SkillRuntimeProviderSendIntent,
    issuance: IssuedSkillRuntimeBrokerGrant,
) -> bool:
    return (
        intent.transaction_store_policy_sha256 == policy.policy_sha256
        and intent.transaction_id == _transaction_id(issuance)
        and intent.issuance_sha256 == issuance.issuance_sha256
        and intent.issuance_id == issuance.issuance_id
        and intent.grant_store_policy_sha256 == issuance.grant_store_policy_sha256
        and intent.prepared_runtime_request_sha256
        == issuance.prepared_runtime_request_sha256
        and intent.runtime_request_sha256 == issuance.runtime_request_sha256
        and intent.route_candidate_id == issuance.route_candidate_id
        and intent.provider_request_sha256 == issuance.provider_request_sha256
        and intent.broker_request_sha256 == issuance.broker_request_sha256
        and intent.spend_ledger_id == issuance.spend_ledger_id
        and intent.ledger_entry_id == issuance.ledger_entry_id
        and intent.spend_reservation_sha256 == issuance.spend_reservation_sha256
        and intent.routing_control_entry_sha256 == issuance.routing_control_entry_sha256
        and intent.skill_control_entry_sha256 == issuance.skill_control_entry_sha256
        and intent.default_pointer_sha256 == issuance.default_pointer_sha256
        and issuance.issued_at <= intent.recorded_at < issuance.valid_until
    )


class SkillRuntimeProviderTransactionStore:
    """Durable send boundary and outcome metadata; never stores prompts or responses."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _load_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: SkillRuntimeProviderTransactionStorePolicy,
        grant_store: SkillRuntimeBrokerGrantStore,
        routing_control_anchor: RoutingControlAnchor,
        skill_control_anchor: SkillReleaseControlAnchor,
        default_store: SkillDefaultStore,
        ledger: SpendLedger,
    ) -> SkillRuntimeProviderTransactionStore:
        if (
            grant_store.policy.provider_transaction_store_policy_sha256
            != policy.policy_sha256
            or policy.broker_grant_store_id != grant_store.policy.store_id
            or policy.routing_control_anchor_policy_sha256
            != routing_control_anchor.policy.policy_sha256
            or policy.skill_control_anchor_policy_sha256
            != skill_control_anchor.policy.policy_sha256
            or policy.default_store_policy_sha256 != default_store.policy.policy_sha256
            or policy.spend_ledger_id != ledger.policy.ledger_id
        ):
            raise ValueError(
                "provider transaction store policy does not match controls"
            )
        policy = SkillRuntimeProviderTransactionStorePolicy.model_validate_json(
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
                "CREATE TABLE transactions (transaction_id TEXT PRIMARY KEY, "
                "issuance_sha256 TEXT NOT NULL UNIQUE, ledger_entry_id TEXT NOT NULL "
                "UNIQUE, intent_sha256 TEXT NOT NULL UNIQUE, intent_json BLOB NOT "
                "NULL, "
                "issuance_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "CREATE TABLE outcomes (transaction_id TEXT PRIMARY KEY REFERENCES "
                "transactions(transaction_id), outcome_sha256 TEXT NOT NULL UNIQUE, "
                "outcome_json BLOB NOT NULL) STRICT"
            )
        return cls(path)

    def _records(
        self, connection: sqlite3.Connection
    ) -> tuple[
        tuple[SkillRuntimeProviderSendIntent, IssuedSkillRuntimeBrokerGrant], ...
    ]:
        rows = connection.execute(
            "SELECT transaction_id, issuance_sha256, ledger_entry_id, intent_sha256, "
            "intent_json, issuance_json FROM transactions ORDER BY rowid"
        ).fetchall()
        records: list[
            tuple[SkillRuntimeProviderSendIntent, IssuedSkillRuntimeBrokerGrant]
        ] = []
        for row in rows:
            intent = SkillRuntimeProviderSendIntent.model_validate_json(row[4])
            issuance = IssuedSkillRuntimeBrokerGrant.model_validate_json(row[5])
            if (
                row[0] != intent.transaction_id
                or row[1] != intent.issuance_sha256
                or row[2] != intent.ledger_entry_id
                or row[3] != intent.intent_sha256
                or row[4] != canonical_bytes(intent)
                or row[5] != canonical_bytes(issuance)
                or not _intent_matches(self.policy, intent, issuance)
            ):
                raise ValueError("provider transaction store record is invalid")
            records.append((intent, issuance))
        if len(records) > self.policy.max_transactions:
            raise ValueError("provider transaction store exceeds policy")
        return tuple(records)

    def _outcome(
        self, connection: sqlite3.Connection, intent: SkillRuntimeProviderSendIntent
    ) -> SkillRuntimeProviderOutcome | None:
        rows = connection.execute(
            "SELECT outcome_sha256, outcome_json FROM outcomes WHERE "
            "transaction_id = ?",
            (intent.transaction_id,),
        ).fetchall()
        if len(rows) > 1:
            raise ValueError("provider transaction outcome identity is not unique")
        if not rows:
            return None
        outcome = SkillRuntimeProviderOutcome.model_validate_json(rows[0][1])
        if (
            rows[0][0] != outcome.outcome_sha256
            or rows[0][1] != canonical_bytes(outcome)
            or outcome.transaction_id != intent.transaction_id
            or outcome.intent_sha256 != intent.intent_sha256
            or outcome.completed_at < intent.recorded_at
        ):
            raise ValueError("provider transaction outcome is invalid")
        return outcome

    def get(
        self, issuance_sha256: str
    ) -> (
        tuple[SkillRuntimeProviderSendIntent, SkillRuntimeProviderOutcome | None] | None
    ):
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("provider transaction store identity changed")
            matches = [
                item
                for item in self._records(connection)
                if item[0].issuance_sha256 == issuance_sha256
            ]
            if len(matches) > 1:
                raise ValueError("provider transaction issuance identity is not unique")
            if not matches:
                return None
            intent, _ = matches[0]
            return intent, self._outcome(connection, intent)

    def record_before_send(
        self,
        intent: SkillRuntimeProviderSendIntent,
        issuance: IssuedSkillRuntimeBrokerGrant,
        *,
        writer: object,
    ) -> None:
        if writer is not _STORE_WRITER:
            raise ValueError(
                "provider send intent must be committed by its transaction"
            )
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _load_policy(connection) != self.policy:
                raise ValueError("provider transaction store identity changed")
            records = self._records(connection)
            if len(records) >= self.policy.max_transactions:
                raise ValueError("provider transaction store limit reached")
            if not _intent_matches(self.policy, intent, issuance):
                raise ValueError("provider transaction intent provenance mismatch")
            if any(
                stored.transaction_id == intent.transaction_id
                or stored.issuance_sha256 == intent.issuance_sha256
                or stored.ledger_entry_id == intent.ledger_entry_id
                for stored, _ in records
            ):
                raise ValueError("provider transaction was already committed")
            connection.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    intent.transaction_id,
                    intent.issuance_sha256,
                    intent.ledger_entry_id,
                    intent.intent_sha256,
                    canonical_bytes(intent),
                    canonical_bytes(issuance),
                ),
            )

    def finish(self, outcome: SkillRuntimeProviderOutcome, *, writer: object) -> None:
        if writer is not _STORE_WRITER:
            raise ValueError("provider outcome must be committed by its transaction")
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _load_policy(connection) != self.policy:
                raise ValueError("provider transaction store identity changed")
            matches = [
                item
                for item in self._records(connection)
                if item[0].transaction_id == outcome.transaction_id
            ]
            if len(matches) != 1:
                raise ValueError("provider transaction intent is absent")
            intent, _ = matches[0]
            if (
                outcome.intent_sha256 != intent.intent_sha256
                or outcome.completed_at < intent.recorded_at
                or self._outcome(connection, intent) is not None
            ):
                raise ValueError("provider transaction outcome provenance mismatch")
            connection.execute(
                "INSERT INTO outcomes VALUES (?, ?, ?)",
                (
                    outcome.transaction_id,
                    outcome.outcome_sha256,
                    canonical_bytes(outcome),
                ),
            )


def _validate_transaction_provenance(
    sources: SkillRuntimeSources,
    ledger: SpendLedger,
    grant_store: SkillRuntimeBrokerGrantStore,
    store: SkillRuntimeProviderTransactionStore,
) -> None:
    policy = store.policy
    if (
        grant_store.policy.provider_transaction_store_policy_sha256
        != policy.policy_sha256
        or policy.broker_grant_store_id != grant_store.policy.store_id
        or policy.routing_control_anchor_policy_sha256
        != sources.routing.control_anchor.policy.policy_sha256
        or policy.skill_control_anchor_policy_sha256
        != sources.control_anchor.policy.policy_sha256
        or policy.default_store_policy_sha256
        != sources.default_store.policy.policy_sha256
        or policy.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime provider transaction provenance mismatch")


def _validate_exact_request(
    prepared: PreparedSkillRuntimeRequest,
    issuance: IssuedSkillRuntimeBrokerGrant,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
) -> None:
    payload = prepared.provider_request.payload
    if (
        prepared.preflight_sha256 != issuance.prepared_runtime_request_sha256
        or prepared.runtime_request_sha256 != issuance.runtime_request_sha256
        or prepared.route.candidate_id != issuance.route_candidate_id
        or digest(canonical_bytes(prepared.provider_request))
        != issuance.broker_request_sha256
        or _provider_request_sha256(payload) != issuance.provider_request_sha256
        or prepared.spend_reservation.policy_sha256 != spend_policy.policy_sha256
        or prepared.spend_reservation.request_sha256 != issuance.provider_request_sha256
        or prepared.ledger_entry.entry_id != issuance.ledger_entry_id
        or prepared.ledger_entry.reservation_sha256 != issuance.spend_reservation_sha256
        or prepared.ledger_entry.reserved_microusd
        != prepared.spend_reservation.reserved_microusd
        or issuance.spend_ledger_id != ledger.policy.ledger_id
        or payload.get("model") != spend_policy.model
        or prepared.spend_reservation.max_output_tokens
        != payload.get("max_output_tokens")
        or prepared.spend_reservation.reserved_microusd
        != spend_policy.cost(
            prepared.spend_reservation.input_tokens,
            prepared.spend_reservation.max_output_tokens,
        )
    ):
        raise ValueError("skill runtime provider request provenance mismatch")


def _intent(
    store: SkillRuntimeProviderTransactionStore,
    issuance: IssuedSkillRuntimeBrokerGrant,
    recorded_at: datetime,
) -> SkillRuntimeProviderSendIntent:
    return SkillRuntimeProviderSendIntent(
        transaction_store_policy_sha256=store.policy.policy_sha256,
        transaction_id=_transaction_id(issuance),
        issuance_sha256=issuance.issuance_sha256,
        issuance_id=issuance.issuance_id,
        grant_store_policy_sha256=issuance.grant_store_policy_sha256,
        prepared_runtime_request_sha256=issuance.prepared_runtime_request_sha256,
        runtime_request_sha256=issuance.runtime_request_sha256,
        route_candidate_id=issuance.route_candidate_id,
        provider_request_sha256=issuance.provider_request_sha256,
        broker_request_sha256=issuance.broker_request_sha256,
        spend_ledger_id=issuance.spend_ledger_id,
        ledger_entry_id=issuance.ledger_entry_id,
        spend_reservation_sha256=issuance.spend_reservation_sha256,
        routing_control_entry_sha256=issuance.routing_control_entry_sha256,
        skill_control_entry_sha256=issuance.skill_control_entry_sha256,
        default_pointer_sha256=issuance.default_pointer_sha256,
        recorded_at=recorded_at,
    )


def _outcome(
    intent: SkillRuntimeProviderSendIntent,
    status: ProviderOutcome,
    charged: int,
    response: dict[str, JsonValue] | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> SkillRuntimeProviderOutcome:
    return SkillRuntimeProviderOutcome(
        transaction_id=intent.transaction_id,
        intent_sha256=intent.intent_sha256,
        status=status,
        charged_microusd=charged,
        provider_response_observed=response is not None,
        provider_response_sha256=(
            skill_runtime_provider_response_sha256(response)
            if response is not None
            else None
        ),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        # A backward wall-clock step must not make an otherwise valid durable
        # outcome contradict its already committed send boundary.
        completed_at=max(datetime.now(UTC), intent.recorded_at),
    )


def _settle_and_finish(
    ledger: SpendLedger,
    store: SkillRuntimeProviderTransactionStore,
    intent: SkillRuntimeProviderSendIntent,
    outcome: SkillRuntimeProviderOutcome,
) -> None:
    ledger.settle(
        LedgerSettlement(
            entry_id=intent.ledger_entry_id,
            reservation_sha256=intent.spend_reservation_sha256,
            status=(
                "settled" if outcome.status == "response_received" else outcome.status
            ),
            charged_microusd=outcome.charged_microusd,
        )
    )
    # Ledger first is conservative: if this commit fails, spend remains accounted.
    store.finish(outcome, writer=_STORE_WRITER)


async def execute_skill_runtime_provider_transaction(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    prepared: PreparedSkillRuntimeRequest,
    capability: SkillRuntimeBrokerCapability,
    claim_wire: bytes,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    grant_store: SkillRuntimeBrokerGrantStore,
    transaction_store: SkillRuntimeProviderTransactionStore,
    transport: SkillRuntimeProviderTransport,
    now: datetime,
) -> SkillRuntimeProviderReply:
    """Commit intent, invoke one exact provider request, and settle conservatively."""

    current = _require_utc(now)
    issuance = capability.issuance
    prepared.check_current(current)
    spend_policy.check_current(current)
    if not issuance.issued_at <= current < issuance.valid_until:
        raise ValueError("skill runtime broker grant is not current")
    _validate_transaction_provenance(sources, ledger, grant_store, transaction_store)
    _validate_exact_request(prepared, issuance, spend_policy, ledger)
    if transport.provider != "openai" or transport.automatic_retries != 0:
        raise ValueError("skill runtime provider transport is not zero-retry OpenAI")
    if (
        routing_preflight.anchored_control_entry_sha256
        != issuance.routing_control_entry_sha256
    ):
        raise ValueError("skill runtime provider routing control mismatch")

    intent = _intent(transaction_store, issuance, current)
    with (
        guard_routing_runtime_sources(sources.routing, routing_preflight, current),
        sources.control_anchor.guard_latest(
            sources.control, sources.control_policy, current
        ) as skill_control,
    ):
        if skill_control.anchor_entry_sha256 != issuance.skill_control_entry_sha256:
            raise ValueError("skill runtime provider skill control changed")
        with sources.default_store.guard_current(
            sources.default_policy,
            sources.installed_store,
            sources.installation_policy,
        ) as pointer:
            if pointer.pointer_sha256 != issuance.default_pointer_sha256:
                raise ValueError("skill runtime provider default changed")
            with (
                ledger.guard_held(prepared.ledger_entry),
                grant_store.guard_grant(issuance),
            ):
                redeemed = capability.redeem(claim_wire)
                if redeemed != issuance:
                    raise ValueError(
                        "skill runtime broker capability provenance mismatch"
                    )
                transaction_store.record_before_send(
                    intent, issuance, writer=_STORE_WRITER
                )

    payload = copy.deepcopy(prepared.provider_request.payload)
    payload["store"] = False
    payload["truncation"] = "disabled"
    payload["service_tier"] = "default"
    reserved = prepared.ledger_entry.reserved_microusd
    try:
        async with asyncio.timeout(transaction_store.policy.max_provider_wait_seconds):
            raw_response = await transport.create_response(payload)
            response = copy.deepcopy(
                _RESPONSE.validate_python(raw_response, strict=True)
            )
            if (
                len(skill_runtime_provider_response_bytes(response))
                > MAX_OPENAI_RESPONSE_BYTES
            ):
                raise ProviderError("provider response exceeds byte limit")
    except asyncio.CancelledError:
        outcome = _outcome(intent, "uncertain", reserved)
        _settle_and_finish(ledger, transaction_store, intent, outcome)
        raise
    except BaseException as error:
        outcome = _outcome(intent, "uncertain", reserved)
        try:
            _settle_and_finish(ledger, transaction_store, intent, outcome)
        except BaseException as settlement_error:
            raise ProviderError(
                "provider outcome settlement unavailable"
            ) from settlement_error
        raise ProviderError("skill runtime provider response unavailable") from error

    response_hash = skill_runtime_provider_response_sha256(response)
    usage = response.get("usage")
    if not isinstance(usage, dict):
        outcome = _outcome(intent, "uncertain", reserved, response)
        _settle_and_finish(ledger, transaction_store, intent, outcome)
        raise ProviderError("provider response omitted billable usage")
    actual_input = usage.get("input_tokens")
    actual_output = usage.get("output_tokens")
    if (
        type(actual_input) is not int
        or type(actual_output) is not int
        or actual_input < 0
        or actual_output < 0
    ):
        outcome = _outcome(intent, "uncertain", reserved, response)
        _settle_and_finish(ledger, transaction_store, intent, outcome)
        raise ProviderError("provider response returned invalid billable usage")
    if (
        actual_input > prepared.spend_reservation.input_tokens
        or actual_output > prepared.spend_reservation.max_output_tokens
        or response.get("service_tier") != "default"
        or response.get("model") != spend_policy.model
    ):
        outcome = _outcome(intent, "violation", reserved, response)
        _settle_and_finish(ledger, transaction_store, intent, outcome)
        raise ProviderError("provider response violated reserved pricing assumptions")
    charged = spend_policy.cost(actual_input, actual_output)
    if charged > reserved:
        outcome = _outcome(intent, "violation", reserved, response)
        _settle_and_finish(ledger, transaction_store, intent, outcome)
        raise ProviderError("provider response exceeded reserved spend")
    outcome = _outcome(
        intent,
        "response_received",
        charged,
        response,
        actual_input,
        actual_output,
    )
    _settle_and_finish(ledger, transaction_store, intent, outcome)
    # Recheck our hash before returning provider-controlled content to the caller.
    if outcome.provider_response_sha256 != response_hash:
        raise ProviderError("provider response changed during settlement")
    return SkillRuntimeProviderReply(intent=intent, outcome=outcome, response=response)


def inspect_skill_runtime_provider_transaction(
    issuance: IssuedSkillRuntimeBrokerGrant,
    grant_store: SkillRuntimeBrokerGrantStore,
    transaction_store: SkillRuntimeProviderTransactionStore,
    ledger: SpendLedger,
) -> SkillRuntimeProviderTransactionStatus:
    """Correlate durable send intent, outcome, and spend without permitting retry."""

    if (
        issuance.grant_store_policy_sha256 != grant_store.policy.policy_sha256
        or grant_store.policy.provider_transaction_store_policy_sha256
        != transaction_store.policy.policy_sha256
        or transaction_store.policy.broker_grant_store_id != grant_store.policy.store_id
        or issuance.spend_ledger_id != ledger.policy.ledger_id
        or transaction_store.policy.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime provider status provenance mismatch")
    stored = grant_store.get(issuance.dispatch_decision_sha256)
    if stored != issuance:
        raise ValueError("skill runtime provider status grant mismatch")
    transaction = transaction_store.get(issuance.issuance_sha256)
    entry = ledger.entry_status(issuance.ledger_entry_id)
    if (
        entry is not None
        and entry.reservation_sha256 != issuance.spend_reservation_sha256
    ):
        raise ValueError("skill runtime provider status reservation mismatch")
    intent = transaction[0] if transaction is not None else None
    outcome = transaction[1] if transaction is not None else None
    if outcome is not None and (
        entry is None
        or entry.status
        != ("settled" if outcome.status == "response_received" else outcome.status)
        or entry.charged_microusd != outcome.charged_microusd
    ):
        raise ValueError("skill runtime provider outcome and ledger disagree")
    return SkillRuntimeProviderTransactionStatus(
        transaction_store_policy_sha256=transaction_store.policy.policy_sha256,
        issuance_sha256=issuance.issuance_sha256,
        transaction_id=_transaction_id(issuance),
        phase=(
            "absent"
            if intent is None
            else "before_send"
            if outcome is None
            else "finished"
        ),
        outcome=None if outcome is None else outcome.status,
        ledger_status="absent" if entry is None else entry.status,
        before_send_committed=intent is not None,
        provider_transfer_may_have_started=intent is not None,
    )
